import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

import motor.motor_asyncio
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from app.config import settings, DATA_DIR

logger = logging.getLogger("docintel.database")

# Local persistence file for fallback mode
LOCAL_DB_FILE = DATA_DIR / "local_db.json"


def _deep_get(item: Any, dotted_key: str) -> Any:
    """Resolves dotted field paths (e.g. ``entities.text``) with list traversal."""
    parts = dotted_key.split(".")
    current: List[Any] = [item]
    for part in parts:
        nxt: List[Any] = []
        for node in current:
            if isinstance(node, dict) and part in node:
                nxt.append(node[part])
            elif isinstance(node, list):
                for element in node:
                    if isinstance(element, dict) and part in element:
                        nxt.append(element[part])
        current = nxt
        if not current:
            return None
    return current[0] if len(current) == 1 else current


def _match_value(field_value: Any, condition: Any) -> bool:
    if isinstance(condition, dict):
        if "$regex" in condition:
            flags = re.IGNORECASE if condition.get("$options") == "i" else 0
            pattern = condition["$regex"]
            try:
                if isinstance(field_value, list):
                    return any(re.search(pattern, str(v), flags) for v in field_value)
                return re.search(pattern, str(field_value or ""), flags) is not None
            except re.error:
                return False
        if "$in" in condition:
            return field_value in condition["$in"]
        if "$ne" in condition:
            return field_value != condition["$ne"]
        if "$exists" in condition:
            return (field_value is not None) == bool(condition["$exists"])
        # Unknown operators fail closed rather than silently matching everything.
        return False
    return field_value == condition


def _match_query(item: Dict[str, Any], query: Dict[str, Any]) -> bool:
    """Evaluates a MongoDB-style query against a fallback document.

    Supports the subset of operators used by the application: $and, $or, $nor,
    $regex/$options, $in, $ne, $exists and dotted field paths.
    """
    for key, condition in query.items():
        if key == "$and":
            if not all(_match_query(item, sub) for sub in condition):
                return False
        elif key == "$or":
            if not any(_match_query(item, sub) for sub in condition):
                return False
        elif key == "$nor":
            if any(_match_query(item, sub) for sub in condition):
                return False
        else:
            field_value = _deep_get(item, key) if "." in key else item.get(key)
            if not _match_value(field_value, condition):
                return False
    return True


class ResilientCollection:
    """In-memory + JSON-persisted collection providing MongoDB-compatible async API.

    Only used in development when ALLOW_LOCAL_FALLBACK is enabled.
    """

    def __init__(self, name: str, db_manager: "DatabaseManager"):
        self.name = name
        self.db_manager = db_manager

    def _get_items(self) -> List[Dict[str, Any]]:
        return self.db_manager.fallback_data.setdefault(self.name, [])

    async def insert_one(self, doc: Dict[str, Any]):
        item = dict(doc)
        if "_id" not in item:
            item["_id"] = f"{self.name}_{len(self._get_items()) + 1}_{int(datetime.utcnow().timestamp())}"
        self._get_items().append(item)
        self.db_manager.save_fallback_data()
        class InsertResult:
            def __init__(self, inserted_id):
                self.inserted_id = inserted_id
        return InsertResult(item["_id"])

    async def find_one(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        for item in self._get_items():
            if _match_query(item, query):
                return dict(item)
        return None

    def find(self, query: Optional[Dict[str, Any]] = None, projection: Optional[Dict[str, Any]] = None):
        query = query or {}
        matched = [dict(item) for item in self._get_items() if _match_query(item, query)]

        class AsyncCursor:
            def __init__(self, data):
                self.data = data
                self._sort_key = None
                self._sort_dir = 1
                self._limit_val = None
                self._skip_val = 0

            def sort(self, key, direction=1):
                self._sort_key = key
                self._sort_dir = direction
                return self

            def skip(self, n):
                self._skip_val = n
                return self

            def limit(self, n):
                self._limit_val = n
                return self

            async def to_list(self, length: Optional[int] = None):
                res = list(self.data)
                if self._sort_key:
                    reverse = self._sort_dir == -1
                    res.sort(key=lambda x: str(x.get(self._sort_key, "")), reverse=reverse)
                if self._skip_val:
                    res = res[self._skip_val:]
                if length is not None:
                    res = res[:length]
                elif self._limit_val is not None:
                    res = res[:self._limit_val]
                return res

            def __aiter__(self):
                self._iter = iter(self.data)
                return self

            async def __anext__(self):
                try:
                    return next(self._iter)
                except StopIteration:
                    raise StopAsyncIteration

        return AsyncCursor(matched)

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any], upsert: bool = False):
        items = self._get_items()
        for item in items:
            if _match_query(item, query):
                if "$set" in update:
                    for sk, sv in update["$set"].items():
                        item[sk] = sv
                else:
                    item.update(update)
                self.db_manager.save_fallback_data()
                class UpdateResult:
                    matched_count = 1
                    modified_count = 1
                return UpdateResult()

        if upsert:
            new_doc = dict(query)
            if "$set" in update:
                new_doc.update(update["$set"])
            else:
                new_doc.update(update)
            await self.insert_one(new_doc)
            class UpsertResult:
                matched_count = 0
                modified_count = 1
            return UpsertResult()

        class ZeroResult:
            matched_count = 0
            modified_count = 0
        return ZeroResult()

    async def delete_one(self, query: Dict[str, Any]):
        items = self._get_items()
        for i, item in enumerate(items):
            if _match_query(item, query):
                del items[i]
                self.db_manager.save_fallback_data()
                class DelResult:
                    deleted_count = 1
                return DelResult()
        class ZeroDelResult:
            deleted_count = 0
        return ZeroDelResult()

    async def count_documents(self, query: Optional[Dict[str, Any]] = None) -> int:
        cursor = self.find(query)
        items = await cursor.to_list(length=None)
        return len(items)

    async def create_index(self, keys, **kwargs):
        # Index creation stub for fallback collection
        return "fallback_index"


class DatabaseManager:
    """Manages MongoDB connection with an explicitly-gated resilient fallback."""

    def __init__(self):
        self.client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self.db = None
        self.is_connected: bool = False
        self.fallback_mode: bool = False
        self.fallback_data: Dict[str, List[Dict[str, Any]]] = {}
        self.load_fallback_data()

    def load_fallback_data(self):
        if LOCAL_DB_FILE.exists():
            try:
                with open(LOCAL_DB_FILE, "r", encoding="utf-8") as f:
                    self.fallback_data = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load fallback db: {e}")
                self.fallback_data = {}
        else:
            self.fallback_data = {}

    def save_fallback_data(self):
        try:
            with open(LOCAL_DB_FILE, "w", encoding="utf-8") as f:
                json.dump(self.fallback_data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error persisting fallback db: {e}")

    @property
    def _fallback_allowed(self) -> bool:
        """Fallback is opt-in and never permitted in production."""
        return settings.ALLOW_LOCAL_FALLBACK and settings.ENVIRONMENT not in ("production", "prod")

    async def connect(self):
        """Connects to MongoDB; falls back to local storage only when explicitly allowed."""
        logger.info("Connecting to MongoDB...")
        try:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=1500,
                connectTimeoutMS=1500,
            )
            await self.client.admin.command("ping")
            self.db = self.client[settings.MONGODB_DATABASE]
            self.is_connected = True
            self.fallback_mode = False
            logger.info("Connected successfully to MongoDB.")

            # Initialize indexes
            await self.init_indexes()
        except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as e:
            if not self._fallback_allowed:
                self.fallback_mode = False
                self.is_connected = False
                logger.critical(
                    "MongoDB is unavailable and local fallback is disabled. "
                    "Refusing to start to avoid silently switching persistence backends."
                )
                raise RuntimeError("MongoDB is unavailable and local fallback is disabled.") from e

            logger.warning(
                "MongoDB server not reachable. Engaging resilient local persistent store "
                "(development only; data/local_db.json)."
            )
            self.fallback_mode = True
            self.is_connected = True

    async def init_indexes(self):
        if not self.fallback_mode and self.db is not None:
            try:
                await self.db.documents.create_index("document_id", unique=True)
                await self.db.documents.create_index("filename")
                await self.db.documents.create_index("document_type")
                await self.db.documents.create_index("created_at")
                # Authorization / isolation indexes
                await self.db.documents.create_index("owner")
                await self.db.documents.create_index("owner_id")
                await self.db.documents.create_index("organization_id")
                await self.db.documents.create_index([("owner_id", 1), ("created_at", -1)])
                await self.db.documents.create_index([("organization_id", 1), ("created_at", -1)])
                await self.db.documents.create_index([("organization_id", 1), ("document_id", 1)])
                await self.db.documents.create_index([("raw_text", "text"), ("redacted_text", "text")])
                await self.db.users.create_index("email", unique=True)
                await self.db.users.create_index("user_id")
                await self.db.security_rules.create_index("rule_id", unique=True)
                logger.info("MongoDB indexes verified.")
            except Exception as e:
                logger.warning(f"Could not create indexes on MongoDB: {e}")

    async def disconnect(self):
        if self.client:
            self.client.close()
            self.is_connected = False
            logger.info("MongoDB connection closed.")

    def get_collection(self, name: str):
        if not self.fallback_mode and self.db is not None:
            return self.db[name]
        if not self._fallback_allowed:
            # Never silently switch persistence backends outside of development fallback.
            raise RuntimeError(
                "Database is unavailable and local fallback is disabled. "
                "Check MongoDB connectivity before serving requests."
            )
        return ResilientCollection(name, self)

    @property
    def users(self):
        return self.get_collection("users")

    @property
    def documents(self):
        return self.get_collection("documents")

    @property
    def processing_logs(self):
        return self.get_collection("processing_logs")

    @property
    def security_rules(self):
        return self.get_collection("security_rules")


db = DatabaseManager()

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

import motor.motor_asyncio
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from app.config import settings, DATA_DIR

logger = logging.getLogger("docintel.database")

# Local persistence file for fallback mode
LOCAL_DB_FILE = DATA_DIR / "local_db.json"


class ResilientCollection:
    """In-memory + JSON-persisted collection providing MongoDB-compatible async API."""

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
        items = self._get_items()
        for item in items:
            match = True
            for k, v in query.items():
                if k == "$or":
                    or_match = any(all(item.get(ok) == ov for ok, ov in cond.items()) for cond in v)
                    if not or_match:
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                res = dict(item)
                return res
        return None

    def find(self, query: Optional[Dict[str, Any]] = None, projection: Optional[Dict[str, Any]] = None):
        query = query or {}
        items = self._get_items()
        matched = []
        for item in items:
            match = True
            for k, v in query.items():
                if k == "$or":
                    or_match = False
                    for cond in v:
                        cond_match = True
                        for ok, ov in cond.items():
                            if isinstance(ov, dict) and "$regex" in ov:
                                import re
                                flags = re.IGNORECASE if ov.get("$options") == "i" else 0
                                if not re.search(ov["$regex"], str(item.get(ok, "")), flags):
                                    cond_match = False
                                    break
                            elif item.get(ok) != ov:
                                cond_match = False
                                break
                        if cond_match:
                            or_match = True
                            break
                    if not or_match:
                        match = False
                        break
                elif isinstance(v, dict) and "$regex" in v:
                    import re
                    flags = re.IGNORECASE if v.get("$options") == "i" else 0
                    if not re.search(v["$regex"], str(item.get(k, "")), flags):
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                matched.append(dict(item))

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
        for i, item in enumerate(items):
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
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
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
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
    """Manages MongoDB connection with transparent resilient fallback."""

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

    async def connect(self):
        """Attempts connection to real MongoDB; switches to resilient fallback if unreachable."""
        logger.info(f"Connecting to MongoDB at {settings.MONGODB_URI}...")
        try:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=1500,
                connectTimeoutMS=1500,
            )
            # Test server availability
            await self.client.admin.command("ping")
            self.db = self.client[settings.MONGODB_DATABASE]
            self.is_connected = True
            self.fallback_mode = False
            logger.info(f"Connected successfully to MongoDB: {settings.MONGODB_DATABASE}")

            # Initialize indexes
            await self.init_indexes()
        except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as e:
            logger.warning(
                f"MongoDB server not reachable at {settings.MONGODB_URI} ({e}). "
                f"Engaging resilient local persistent store (data/local_db.json)."
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
                await self.db.documents.create_index([("raw_text", "text"), ("redacted_text", "text")])
                await self.db.users.create_index("email", unique=True)
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

import json
from pathlib import Path
from typing import Any, List
from pydantic.fields import FieldInfo
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, EnvSettingsSource, DotEnvSettingsSource, PydanticBaseSettingsSource

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = BASE_DIR.parent
DATA_DIR = WORKSPACE_DIR / "data"
SAMPLE_DOCS_DIR = DATA_DIR / "sample_documents"
PROCESSED_DIR = DATA_DIR / "processed"
VECTOR_INDEX_DIR = DATA_DIR / "vector_index"
UPLOAD_DIR = BASE_DIR / "uploads"

# Ensure directories exist
for d in [DATA_DIR, SAMPLE_DOCS_DIR, PROCESSED_DIR, VECTOR_INDEX_DIR, UPLOAD_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Development-only fallback secret. Never allowed in production (see validation below).
DEV_JWT_SECRET = "docintel-dev-only-insecure-jwt-secret-do-not-use-in-production"

# Development-only infrastructure defaults. Production must configure these
# explicitly (see the production guard in ``_validate_security``).
DEV_MONGODB_URI = "mongodb://localhost:27017"
DEV_REDIS_URL = "redis://localhost:6379/0"

# Known insecure/placeholder secrets that must never be used in production.
INSECURE_SECRETS = {
    "",
    "secret",
    "change-me",
    "change-me-please",
    "your-secret-key",
    "your_secret_key",
    "docintel-super-secret-jwt-key-production-ready-2025",
    DEV_JWT_SECRET,
}


class _LenientEnvSettingsSource(EnvSettingsSource):
    """Env source that accepts comma-separated values for list fields.

    pydantic-settings otherwise attempts to JSON-decode any list-typed field
    sourced from the environment, which rejects the friendlier
    ``A,B,C`` form used throughout this project's configuration.
    """

    def decode_complex_value(self, field_name: str, field: FieldInfo, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (ValueError, TypeError):
                return value
        return value


class _LenientDotEnvSettingsSource(DotEnvSettingsSource):
    """Dotenv equivalent of :class:`_LenientEnvSettingsSource`."""

    def decode_complex_value(self, field_name: str, field: FieldInfo, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (ValueError, TypeError):
                return value
        return value


class Settings(BaseSettings):
    PROJECT_NAME: str = "DocIntel AI"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"

    # Runtime environment: "development" | "staging" | "production"
    ENVIRONMENT: str = "development"

    # Database
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "docintel"
    # When false, the application will never silently fall back to the local JSON store.
    # Forced to false in production.
    ALLOW_LOCAL_FALLBACK: bool = True

    # Security & Auth
    JWT_SECRET_KEY: str = ""
    # Deprecated alias retained for backward compatibility with existing deployments.
    JWT_SECRET: str = ""
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_ALGORITHM: str = "HS256"
    # Legacy aliases retained for backward compatibility.
    JWT_EXPIRE_MINUTES: int = 0
    ALGORITHM: str = ""

    # One-time, environment-controlled admin bootstrap (never logged).
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""

    # OCR Engine
    TESSERACT_CMD: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    # AI Models
    HF_MODEL_NAME: str = "Jean-Baptiste/roberta-large-ner-english"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # RAG / LLM Provider
    LLM_PROVIDER: str = "local"
    LLM_API_KEY: str = ""

    # CORS
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    # File limits
    MAX_UPLOAD_SIZE_MB: int = 15
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".jpg", ".jpeg", ".png"]
    ALLOWED_MIME_TYPES: List[str] = [
        "application/pdf",
        "image/jpeg",
        "image/jpg",
        "image/png",
    ]
    # Magic-byte signatures used for content sniffing (extension alone is untrusted).
    ALLOWED_FILE_SIGNATURES: List[str] = ["pdf", "jpeg", "png"]
    MAX_SEARCH_QUERY_LENGTH: int = 200

    # ------------------------------------------------------------------
    # Phase 2 — asynchronous document processing
    # ------------------------------------------------------------------
    # Message broker / result backend for Celery. Never hard-code credentials.
    REDIS_URL: str = "redis://localhost:6379/0"
    # "local"  -> process in-process (no Redis required, ideal for development/testing)
    # "celery" -> dispatch to Celery workers over Redis
    PROCESSING_QUEUE: str = "local"
    # Bounded retry policy for transient failures (exponential backoff).
    MAX_PROCESSING_ATTEMPTS: int = 3
    RETRY_BACKOFF_SECONDS: List[int] = [30, 60, 120]
    # Celery task time limit (seconds) guarding against runaway pipelines.
    PROCESSING_TASK_TIME_LIMIT: int = 1800

    # ------------------------------------------------------------------
    # Phase 2 — object storage abstraction
    # ------------------------------------------------------------------
    # "local" -> filesystem under STORAGE_LOCAL_ROOT; "s3" -> S3-compatible (future).
    STORAGE_BACKEND: str = "local"
    # When empty, defaults to the backend uploads directory.
    STORAGE_LOCAL_ROOT: str = ""
    # S3-compatible storage (optional; not required for local development).
    S3_ENDPOINT: str = ""
    S3_BUCKET: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = ""

    # ------------------------------------------------------------------
    # Phase 3 — document intelligence pipeline
    # ------------------------------------------------------------------
    # Bumped whenever the intelligence pipeline's behaviour/shape changes so
    # processed documents can be identified for future migrations.
    PIPELINE_VERSION: str = "3.0"
    # Embedding model generation tag; lets the system know which documents
    # require re-indexing if the model is ever upgraded.
    EMBEDDING_MODEL_VERSION: str = "1"
    # Resource limits guarding against unbounded AI processing (Step 18).
    # When a limit is reached the pipeline records a warning rather than
    # silently discarding data or crashing the job.
    MAX_DOCUMENT_PAGES: int = 50
    MAX_TEXT_LENGTH: int = 200000
    MAX_OCR_TIME: int = 120          # wall-clock OCR budget (seconds) per document
    MAX_EMBEDDING_CHUNKS: int = 500
    MIN_CHUNK_CHARS: int = 20
    # Redaction strategy for sensitive values in derived text (Step 9):
    #   "mask"        -> partially-visible masks, e.g. j***e@example.com (default)
    #   "placeholder" -> deterministic, non-identifying placeholders, e.g. [REDACTED_EMAIL]
    PII_REDACTION_MODE: str = "mask"

    @field_validator("CORS_ORIGINS", "ALLOWED_EXTENSIONS", "ALLOWED_MIME_TYPES", "ALLOWED_FILE_SIGNATURES", "RETRY_BACKOFF_SECONDS", mode="before")
    @classmethod
    def _split_comma_separated(cls, value):
        """Allows list settings to be provided as comma-separated env strings."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return value  # let pydantic parse JSON lists
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ):
        """Uses lenient env/dotenv sources so list settings accept ``A,B`` values."""
        return (
            init_settings,
            _LenientEnvSettingsSource(settings_cls),
            _LenientDotEnvSettingsSource(settings_cls),
            file_secret_settings,
        )

    @model_validator(mode="after")
    def _validate_security(self):
        env = (self.ENVIRONMENT or "development").strip().lower()
        object.__setattr__(self, "ENVIRONMENT", env)
        is_production = env in ("production", "prod")

        # Resolve the canonical JWT secret, honouring the legacy JWT_SECRET alias.
        secret = (self.JWT_SECRET_KEY or self.JWT_SECRET or "").strip()

        # Resolve JWT algorithm / expiry from legacy aliases when the new names are unset.
        algorithm = (self.JWT_ALGORITHM or self.ALGORITHM or "HS256").strip() or "HS256"
        object.__setattr__(self, "JWT_ALGORITHM", algorithm)

        if not self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES and self.JWT_EXPIRE_MINUTES:
            object.__setattr__(self, "JWT_ACCESS_TOKEN_EXPIRE_MINUTES", self.JWT_EXPIRE_MINUTES)

        if not secret:
            secret = DEV_JWT_SECRET
        object.__setattr__(self, "JWT_SECRET_KEY", secret)

        # Phase 2: validate processing/storage configuration for unsupported values.
        queue_mode = (self.PROCESSING_QUEUE or "local").strip().lower()
        if queue_mode not in ("local", "celery"):
            raise ValueError("PROCESSING_QUEUE must be either 'local' or 'celery'.")
        object.__setattr__(self, "PROCESSING_QUEUE", queue_mode)

        storage_backend = (self.STORAGE_BACKEND or "local").strip().lower()
        if storage_backend not in ("local", "s3"):
            raise ValueError("STORAGE_BACKEND must be either 'local' or 's3'.")
        object.__setattr__(self, "STORAGE_BACKEND", storage_backend)

        if self.MAX_PROCESSING_ATTEMPTS < 1:
            object.__setattr__(self, "MAX_PROCESSING_ATTEMPTS", 1)

        # Phase 3: resource limits must be positive; clamp rather than crash.
        for _limit in (
            "MAX_DOCUMENT_PAGES",
            "MAX_TEXT_LENGTH",
            "MAX_OCR_TIME",
            "MAX_EMBEDDING_CHUNKS",
            "MIN_CHUNK_CHARS",
        ):
            if getattr(self, _limit) < 1:
                object.__setattr__(self, _limit, 1)

        if is_production:
            if secret in INSECURE_SECRETS or len(secret) < 32:
                raise ValueError(
                    "Insecure JWT_SECRET_KEY detected in production. Set a strong, unique "
                    "JWT_SECRET_KEY (>= 32 characters) via environment configuration."
                )
            if not self.CORS_ORIGINS or any(origin.strip() == "*" for origin in self.CORS_ORIGINS):
                raise ValueError(
                    "Unsafe CORS configuration in production. Set explicit CORS_ORIGINS "
                    "(comma-separated allow-list); the wildcard '*' is not permitted."
                )
            if self.ALLOW_LOCAL_FALLBACK:
                raise ValueError(
                    "ALLOW_LOCAL_FALLBACK must be false in production; the application will not "
                    "silently fall back to the local JSON store."
                )
            if self.BOOTSTRAP_ADMIN_PASSWORD and len(self.BOOTSTRAP_ADMIN_PASSWORD) < 12:
                raise ValueError(
                    "BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters in production."
                )
            # §12 — document processing must run in Celery workers in production;
            # the API never executes the AI pipeline inline (dev convenience only).
            if self.PROCESSING_QUEUE != "celery":
                raise ValueError(
                    "PROCESSING_QUEUE must be 'celery' in production. Long-running "
                    "document processing may not run inside the API process."
                )
            # §17 — required infrastructure must be configured explicitly.
            if not self.MONGODB_URI or self.MONGODB_URI.strip() == DEV_MONGODB_URI:
                raise ValueError(
                    "MONGODB_URI must be explicitly configured in production; the "
                    "development default is not permitted."
                )
            if not self.REDIS_URL or self.REDIS_URL.strip() == DEV_REDIS_URL:
                raise ValueError(
                    "REDIS_URL must be explicitly configured in production "
                    "(Celery broker/result backend)."
                )
            # §31 — S3 object storage is not implemented; production must refuse it
            # rather than silently degrade to local filesystem storage.
            if self.STORAGE_BACKEND == "s3":
                raise ValueError(
                    "STORAGE_BACKEND=s3 is not implemented yet. Set "
                    "STORAGE_BACKEND=local (S3 support is a future phase)."
                )

        return self

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "allow"


settings = Settings()

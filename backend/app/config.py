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
    MAX_SEARCH_QUERY_LENGTH: int = 200

    @field_validator("CORS_ORIGINS", "ALLOWED_EXTENSIONS", "ALLOWED_MIME_TYPES", mode="before")
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

        return self

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "allow"


settings = Settings()

import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings

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


class Settings(BaseSettings):
    PROJECT_NAME: str = "DocIntel AI"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"

    # Database
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "docintel"

    # Security & Auth
    JWT_SECRET: str = "docintel-super-secret-jwt-key-production-ready-2025"
    JWT_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

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

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "allow"


settings = Settings()

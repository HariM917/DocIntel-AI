# DocIntel AI - Backend Service

FastAPI-powered document intelligence and data extraction API service.

## Tech Stack
- **Python 3.11+**
- **FastAPI** + **Uvicorn**
- **Pydantic v2**
- **PyMuPDF (fitz)** & **pytesseract**
- **Transformers (RoBERTa)** & **PyTorch**
- **SentenceTransformers** & **FAISS**
- **Motor / PyMongo** with automatic local fallback

## Local Setup (Windows)

1. Create and activate a virtual environment:
```powershell
python -m venv .venv
.venv\Scripts\activate
```

2. Install dependencies:
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

3. Configure environment variables:
```powershell
copy .env.example .env
```
Ensure `TESSERACT_CMD` points to your Tesseract binary, e.g.:
`TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`

4. Run the API service:
```powershell
uvicorn app.main:app --reload --port 8000
```

5. Run unit & integration tests:
```powershell
pytest tests/ -v
```

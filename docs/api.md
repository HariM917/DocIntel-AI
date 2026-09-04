# DocIntel AI - REST API Documentation

Base URL: `http://localhost:8000/api`  
Interactive Swagger UI: `http://localhost:8000/docs`  
ReDoc UI: `http://localhost:8000/redoc`

---

## 1. Authentication Endpoints

### Register User
- **Method:** `POST`
- **Endpoint:** `/auth/register`
- **Request Body:**
```json
{
  "email": "analyst@docintel.ai",
  "password": "SecurePassword123!",
  "full_name": "Document Analyst"
}
```
- **Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": "users_1_1788412250",
    "email": "analyst@docintel.ai",
    "full_name": "Document Analyst",
    "role": "user",
    "created_at": "2025-01-01T00:00:00"
  }
}
```

### User Login
- **Method:** `POST`
- **Endpoint:** `/auth/login`
- **Request Body:**
```json
{
  "email": "admin@docintel.ai",
  "password": "Admin@12345"
}
```
- **Response (200 OK):** Returns JWT access token and user profile.

### Current User Profile
- **Method:** `GET`
- **Endpoint:** `/auth/me`
- **Headers:** `Authorization: Bearer <token>`
- **Response (200 OK):** User object.

---

## 2. Document Intelligence Endpoints

### Process & Extract Document
- **Method:** `POST`
- **Endpoint:** `/documents/process`
- **Content-Type:** `multipart/form-data`
- **Form Field:** `file` (PDF, JPG, JPEG, PNG)
- **Response (200 OK):**
```json
{
  "id": "doc_1",
  "document_id": "DOC-A7F92B",
  "filename": "sample_invoice.pdf",
  "file_type": ".pdf",
  "file_size": 5763572,
  "document_type": "Invoice",
  "classification_confidence": 0.95,
  "status": "Verified",
  "raw_text": "TAX INVOICE ...",
  "redacted_text": "TAX INVOICE ... [Redacted]",
  "entities": [
    { "text": "Acme Cloud Solutions", "type": "ORGANIZATION", "confidence": 0.98 }
  ],
  "pii_entities": [
    {
      "type": "PAN",
      "value": "ABCDE1234F",
      "masked_value": "XXXXX1234F",
      "confidence": 0.99,
      "source": "regex",
      "sensitive": true,
      "valid": true
    }
  ],
  "structured_data": {
    "invoice_number": "INV-2025-9014",
    "invoice_date": "15/01/2025",
    "total_amount": "4,500.00",
    "currency": "INR"
  },
  "confidence": 0.94,
  "pipeline_steps": [ ... ],
  "created_at": "2025-01-01T00:00:00"
}
```

### List Documents
- **Method:** `GET`
- **Endpoint:** `/documents`
- **Query Params:**
  - `type` (optional): `Invoice | Contract | Identity | Application | Form | Other`
  - `status` (optional): `Verified | Flagged`
  - `search` (optional): substring search term
  - `page` (default: 1): page number
  - `limit` (default: 20): items per page

### Get Document by ID
- **Method:** `GET`
- **Endpoint:** `/documents/{document_id}`

### Delete Document
- **Method:** `DELETE`
- **Endpoint:** `/documents/{document_id}`
- **Headers:** `Authorization: Bearer <token>`

### Download Original File
- **Method:** `GET`
- **Endpoint:** `/documents/{document_id}/download`

---

## 3. Analytics & Search Endpoints

### Dashboard Stats
- **Method:** `GET`
- **Endpoint:** `/dashboard/stats`
- **Response (200 OK):**
```json
{
  "total_processed": 14,
  "extraction_accuracy": 96.2,
  "protected_entities": 48,
  "time_saved": "1.4 hrs",
  "type_distribution": { "Invoice": 6, "Contract": 4, "Identity": 2, "Application": 2 },
  "status_distribution": { "Verified": 13, "Flagged": 1 },
  "recent_documents": [ ... ]
}
```

### Global Search
- **Method:** `GET`
- **Endpoint:** `/search?q={query}`
- **Response (200 OK):** List of matching documents with contextual snippets and highlighted positions.

---

## 4. Security Rules & AI Assistant

### Get Security Rules
- **Method:** `GET`
- **Endpoint:** `/security/rules`

### Update Security Rule
- **Method:** `PUT`
- **Endpoint:** `/security/rules/{rule_id}`
- **Request Body:**
```json
{
  "enabled": false
}
```

### RAG Assistant Chat
- **Method:** `POST`
- **Endpoint:** `/chat`
- **Request Body:**
```json
{
  "message": "What is the invoice amount?",
  "document_id": "DOC-A7F92B"
}
```
- **Response (200 OK):**
```json
{
  "answer": "Based on the indexed documents, here are the financial details found:\n- Total Amount: INR 4,500.00",
  "sources": [
    {
      "document_id": "DOC-A7F92B",
      "filename": "sample_invoice.pdf",
      "document_type": "Invoice",
      "snippet": "...",
      "score": 0.89
    }
  ],
  "confidence": 0.92,
  "matched": true
}
```

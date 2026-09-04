# DocIntel AI - Hackathon Evaluation & Demo Guide

This document provides a guided walkthrough for hackathon judges and evaluators to test every capability of **DocIntel AI**.

---

## 5-Minute Quick Tour

### Step 1: Login to Platform
1. Open the frontend: [http://localhost:5173](http://localhost:5173)
2. Click **"Fill Default Demo Admin"** to automatically populate:
   - **Email:** `admin@docintel.ai`
   - **Password:** `Admin@12345`
3. Click **Sign In**. Notice the JWT authentication token being stored and the user redirected to the main dashboard.

---

### Step 2: Ingest & Process an Enterprise Invoice
1. Navigate to **"Process Document"** from the left sidebar or top banner.
2. Drag and drop or browse to `data/sample_documents/sample_invoice.pdf`.
3. Click **"Start Extraction & Redaction"**.
4. Observe the **Pipeline Visualizer**:
   - `UPLOAD`: Staged safely in `backend/uploads/`
   - `Tesseract OCR`: Text parsed from PDF pages with high confidence
   - `Classification`: Classified as **"Invoice"**
   - `RoBERTa NER`: Recognized Persons, Organizations, and Locations
   - `PII Detection`: Detected Indian PAN (`ABCDE1234F`), Email, and Phone
   - `Validation & Redaction`: Masked PAN to `XXXXX1234F`
   - `Structured Extraction`: Synthesized typed invoice schema (`INV-2025-9014`, `INR 4,500.00`)
   - `Storage & Indexing`: Saved to MongoDB and vectorized into FAISS index
5. Switch tabs between **"Structured Schema"**, **"Entities"**, **"Detected PII"**, and **"Raw vs. Redacted OCR"** to see the side-by-side comparison.

---

### Step 3: Verify Live Dashboard Telemetry
1. Navigate to **Dashboard**.
2. Notice the live metrics calculated from MongoDB:
   - **Total Processed:** Dynamic count of all processed documents
   - **Extraction Accuracy:** Average model confidence percentage
   - **Protected Entities:** Cumulative count of detected and masked PII items
   - **Time Saved:** Automated time calculation based on ~6 minutes saved per manual audit
   - **Document Type Breakdown:** Invoices, Contracts, Identities, and Forms
   - **Recent Ingested Documents:** Real MongoDB records with direct inspection and download actions.

---

### Step 4: Query with FAISS RAG AI Assistant
1. Navigate to **"AI Assistant"**.
2. Click on sample prompt: *"What is the invoice amount?"*
3. The chatbot searches the FAISS dense vector index for the top-k relevant document chunks and returns a grounded response with source document citations and similarity scores.
4. Try asking: *"Who is the vendor?"* or *"Which documents contain Aadhaar numbers?"*.
5. Try asking an unrelated question like *"What is the capital of Mars?"*. The assistant strictly answers:
   > *"I couldn't find that information in the available documents."* (Zero hallucinations).

---

### Step 5: Test Enterprise Security Rules
1. Navigate to **"Security Rules"**.
2. View the rules:
   - **Aadhaar Masking:** Masks 12-digit UID numbers (`XXXX XXXX 9012`)
   - **PAN Masking:** Masks Permanent Account Numbers (`XXXXX1234F`)
   - **Email Masking:** Obfuscates email handles (`r***@example.com`)
   - **Phone Masking:** Hides primary mobile digits (`******3210`)
   - **Bank Account Masking:** Masks account numbers (`********1234`)
   - **Credit Card Masking:** PCI-DSS compliant formatting (`XXXX-XXXX-XXXX-1234`)
3. Toggle any rule off/on and notice immediate real-time persistence to MongoDB.

---

### Step 6: Global Search & Document Archive
1. In the top navigation bar, type `INV` or `Apex` or `PAN` into the global search.
2. Instant dropdown displays matching documents with highlighted context snippets.
3. Open **"Document Archive"** to test multi-criteria filtering by document type and compliance status (`Verified` / `Flagged`).

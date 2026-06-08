# No gradio import
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import requests
import pypdf
import io
import docx  # python-docx for DOCX
import os
import json

# ============================================================
# CONFIGURATION
# ============================================================
HF_API_URL = "https://router.huggingface.co/hf-inference/models/rae-jax/cie-auditor-final"
# Add your HF Read token as a Space Secret named HF_TOKEN
HF_TOKEN = os.environ.get("HF_TOKEN", "")

# ============================================================
# FRAMEWORK CHEAT SHEET (injected into every system prompt)
# ============================================================
FRAMEWORK_CONTEXT = """
COMPLIANCE FRAMEWORK REFERENCE — always cite specific control IDs in your findings:

ISO 27001:
  A.5.17 - Authentication information management
  A.8.2  - Privileged access rights
  A.8.3  - Information access restriction
  A.8.9  - Configuration management
  A.8.20 - Network security

SOC 2:
  CC6.1  - Logical and physical access controls
  CC6.6  - Restrictions on remote connections
  CC6.7  - Transmission of confidential information
  CC7.2  - Monitoring for anomalies and security events

NIST SP 800-53:
  AC-2   - Account management
  AC-6   - Least privilege
  IA-2   - Multi-factor authentication
  SC-28  - Protection of information at rest
  SI-2   - Flaw remediation (patching)
  AU-2   - Event logging

GDPR:
  Article 25  - Data protection by design and by default
  Article 32  - Security of processing
  Article 33  - Notification of a personal data breach
  Article 35  - Data protection impact assessment

PCI-DSS v4.0:
  Req 7.2  - Access control systems
  Req 8.3  - Strong cryptography for authentication
  Req 8.4  - MFA requirements
  Req 10.2 - Audit log implementation

HIPAA:
  164.308(a)(1) - Risk analysis and management
  164.312(a)    - Access control
  164.312(d)    - Person or entity authentication
  164.312(e)    - Transmission security

ALWAYS map each finding to at least one specific control ID from the above.
"""

SYSTEM_PROMPT = f"""You are a Senior Compliance Auditor with expertise in ISO 27001, SOC 2, NIST, GDPR, PCI-DSS, and HIPAA.

Assess the scenario and produce a highly structured compliance audit report with these exact sections:

1. Executive Summary
2. Audit Scope
3. Controls Violated (with specific framework citations e.g. ISO 27001 A.8.2, NIST AC-2)
4. Detailed Findings
5. Root Cause Analysis
6. Impact Assessment
7. Remediation Steps
8. Risk Rating (Critical / High / Medium / Low)
9. Management Recommendations

Control Maturity Scoring (add at the end):
- [Control Area]: [X/5] — brief rationale

Non-Compliance Summary:
- Non-compliant against: [list frameworks with specific articles]
- Partially compliant against: [list frameworks]

If evidence is insufficient for any section, state INSUFFICIENT EVIDENCE explicitly.

{FRAMEWORK_CONTEXT}"""

# ============================================================
# DOCUMENT EXTRACTION
# ============================================================
def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text[:8000]
    except Exception as e:
        return f"Error reading PDF: {str(e)}"

def extract_text_from_docx(file_bytes: bytes) -> str:
    import io
    doc = docx.Document(io.BytesIO(file_bytes))
    text = "\n".join([para.text for para in doc.paragraphs])
    return text[:8000]

def extract_text(file_bytes: bytes, filename: str) -> str:
    ext = filename.lower().split(".")[-1]
    if ext == "pdf":
        return extract_text_from_pdf(file_bytes)
    elif ext in ["docx", "doc"]:
        return extract_text_from_docx(file_bytes)
    elif ext == "txt":
        return file_bytes.decode("utf-8", errors="ignore")[:8000]
    else:
        return file_bytes.decode("utf-8", errors="ignore")[:8000]

# ============================================================
# HF INFERENCE API CALL
# ============================================================
def call_model(user_message: str) -> str:
    # Format the Mistral instruct prompt
    prompt = f"<s>[INST] {SYSTEM_PROMPT}\n\n{user_message} [/INST]"

    headers = {"Content-Type": "application/json"}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"

    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 1024,
            "temperature": 0.1,
            "top_p": 0.9,
            "return_full_text": False
        }
    }

    response = requests.post(HF_API_URL, headers=headers, json=payload, timeout=300)

    if response.status_code == 503:
        return "⏳ Model is warming up on Hugging Face servers. This takes 2-3 minutes on first use. Please wait and try again."
    
    if response.status_code == 429:
        return "⚠️ Rate limit reached. Please wait 60 seconds and try again."

    if not response.ok:
        return f"❌ API Error {response.status_code}: {response.text[:200]}"

    result = response.json()
    
    if isinstance(result, list) and len(result) > 0:
        return result[0].get("generated_text", "No response generated.")
    
    return str(result)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI(title="CIE Auditor v2 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
def chat(req: ChatRequest):
    reply = call_model(req.message)
    return {"reply": reply}

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    file_bytes = await file.read()
    text = extract_text(file_bytes, file.filename)
    
    if len(text.strip()) < 50:
        return {"reply": "❌ Could not extract enough text from the document. Please ensure it is a readable PDF, DOCX, or TXT file."}
    
    user_message = f"""I am uploading a corporate policy document for compliance review. Please audit it against all applicable frameworks.

DOCUMENT CONTENT:
---
{text}
---

Identify every clause or section that violates or is missing required controls. Cite specific framework control IDs for each finding."""

    reply = call_model(user_message)
    return {"reply": reply}

@app.get("/health")
def health():
    return {"status": "ok", "model": "rae-jax/cie-auditor-final"}

# Mount the frontend directory at the root AFTER all API routes
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=7860)

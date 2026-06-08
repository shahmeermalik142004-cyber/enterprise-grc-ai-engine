from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

app = FastAPI(title="GRC AI Engine - HF Proxy")

# Allow your local frontend to talk to this local backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import pypdf
import io
import docx

# The temporary Kaggle Localtunnel URL (update this each time you start Kaggle)
KAGGLE_URL = "https://heavy-toes-feel.loca.lt"

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
def proxy_chat(req: ChatRequest):
    print(f"Forwarding message to Kaggle: {req.message[:50]}...")
    
    headers = {
        "Content-Type": "application/json",
        "Bypass-Tunnel-Reminder": "true"
    }
    
    try:
        response = requests.post(f"{KAGGLE_URL}/chat", headers=headers, json={"message": req.message})
        try:
            return response.json()
        except:
            return {"reply": f"🚨 Kaggle Error! Status {response.status_code}. Raw output: {response.text[:200]}"}
            
    except Exception as e:
        return {"reply": f"🚨 Proxy Error: Could not reach Kaggle. Make sure the notebook is running and KAGGLE_URL is correct. ({e})"}

def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text[:1200]  # Reduced to 1200 to prevent localtunnel 60s timeout
    except Exception as e:
        return f"Error reading PDF: {str(e)}"

def extract_text_from_docx(file_bytes: bytes) -> str:
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text[:1200]  # Reduced to 1200 to prevent localtunnel 60s timeout
    except Exception as e:
        return f"Error reading DOCX: {str(e)}"

# ============================================================
# FRAMEWORK CHEAT SHEET (injected into every system prompt)
# ============================================================
FRAMEWORK_CONTEXT = """
COMPLIANCE FRAMEWORK REFERENCE - always cite specific control IDs in your findings:

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

Assess the scenario and produce a highly structured compliance audit report.
CRITICAL INSTRUCTION: You MUST be extremely concise. Keep your entire response under 300 words to prevent network timeouts.

Include these sections:
1. Executive Summary
2. Controls Violated (with specific framework citations e.g. ISO 27001 A.8.2)
3. Detailed Findings & Risk Rating
4. Remediation Steps

Non-Compliance Summary:
- Non-compliant against: [list frameworks with specific articles]

{FRAMEWORK_CONTEXT}"""

@app.post("/upload")
async def proxy_upload(file: UploadFile = File(...)):
    print(f"Processing uploaded file locally: {file.filename}")
    file_bytes = await file.read()
    
    if file.filename.lower().endswith(".pdf"):
        text = extract_text_from_pdf(file_bytes)
    elif file.filename.lower().endswith(".docx"):
        text = extract_text_from_docx(file_bytes)
    elif file.filename.lower().endswith(".txt"):
        text = file_bytes.decode('utf-8', errors='ignore')[:1200]
    else:
        return {"reply": f"Unsupported file type: {file.filename}. Please upload PDF, DOCX, or TXT."}
        
    print(f"Extracted {len(text)} characters. Sending text to Kaggle...")
    
    full_prompt = f"""{SYSTEM_PROMPT}
    
Please audit the following document against our compliance frameworks.
Document Name: {file.filename}

--- DOCUMENT CONTENT ---
{text}
--- END DOCUMENT ---"""

    # We just reuse the proxy_chat function to send the extracted text to Kaggle!
    return proxy_chat(ChatRequest(message=full_prompt))

if __name__ == "__main__":
    import uvicorn
    # Run the proxy server on port 8000
    print("Starting local API proxy...")
    uvicorn.run(app, host="127.0.0.1", port=8000)

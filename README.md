---
license: apache-2.0
base_model: mistralai/Mistral-7B-Instruct-v0.2
tags:
- text-generation
- fine-tuned
- compliance
- cybersecurity
- grc
- auditing
- unsloth
- mistral
- dpo
language:
- en
pipeline_tag: text-generation
---

# 🛡️ CIE Auditor - Enterprise GRC Compliance AI

A custom fine-tuned and DPO-aligned version of **Mistral 7B Instruct**, trained to function as a **Senior IT Compliance Auditor**. Feed it a security incident or corporate scenario, and it produces a structured, board-ready **9-Part Audit Report** in seconds.

> Tested against real-world breaches including Capital One (2019), Equifax (2017), and Uber (2022) - correctly identifying root causes, violated controls, and remediation steps.

---

## 🚀 What Makes This Different

This is **not** a ChatGPT wrapper or a prompt-engineered chatbot. The model weights themselves were modified using two phases of training:

1. **Supervised Fine-Tuning (SFT):** Trained on a custom JSONL dataset of real compliance frameworks including ISO 27001, SOC 2 Type II, GDPR, PCI-DSS, HIPAA, and NIST CSF. The model learned to map any security scenario to the correct regulatory controls.

2. **Direct Preference Optimization (DPO):** Constitutional AI alignment was applied to enforce auditor-grade behavior. The model was trained to:
   - ✅ Always flag `INSUFFICIENT EVIDENCE` when data is missing instead of speculating
   - ✅ Escalate critical findings to board level
   - ✅ Refuse to act like a chatbot or provide conversational responses
   - ✅ Maintain a strict, formal auditor persona at all times

---

## 📋 Output Format

Every response follows a strict 9-part structure:

```
1. Executive Summary
2. Audit Scope
3. Controls Violated
4. Finding
5. Impact
6. Remediation Steps
7. Risk Assessment
8. Audit Recommendations
9. Management Review

INSUFFICIENT EVIDENCE to determine: [flagged unknowns]
Next Steps: [actionable items]
```

---

## 💻 Quick Start

```python
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "rae-jax/cie-auditor-final",
    max_seq_length = 2048,
    dtype = None,
    load_in_4bit = True,
)
FastLanguageModel.for_inference(model)

messages = [
    {
        "role": "system",
        "content": "You are a Senior Compliance Auditor. Assess the scenario and output a highly structured 9-part compliance audit report. If evidence is insufficient, state INSUFFICIENT EVIDENCE."
    },
    {
        "role": "user",
        "content": "An attacker exploited a misconfigured ModSecurity WAF via SSRF to extract temporary IAM credentials from the AWS EC2 metadata service, gaining access to an S3 bucket containing the PII of 100 million customers."
    }
]

inputs = tokenizer.apply_chat_template(
    messages,
    tokenize=True,
    add_generation_prompt=True,
    return_tensors="pt"
).to("cuda")

outputs = model.generate(
    input_ids=inputs,
    max_new_tokens=1024,
    temperature=0.1,
    top_p=0.9
)

print(tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True))
```

---

## 🧪 Example Scenarios to Try

**Cloud Misconfiguration:**
> *"Our AWS S3 bucket was left publicly accessible for 12 months, exposing 400GB of customer PII and proprietary product designs."*

**Social Engineering + PAM Compromise:**
> *"An attacker bypassed MFA using push notification fatigue on a contractor. They then found hardcoded PAM credentials in a PowerShell script on an internal network share, gaining full control of AWS, GCP, and Slack."*

**Unpatched Vulnerability:**
> *"Attackers exploited CVE-2017-5638 in Apache Struts. The patch had been available for 2 months but was not applied. The attackers maintained access for 76 days and exfiltrated SSNs for 147 million people."*

---

## 🏗️ Training Details

| Parameter | Value |
|---|---|
| Base Model | `mistralai/Mistral-7B-Instruct-v0.2` |
| Training Framework | Unsloth + TRL |
| SFT Dataset | Custom JSONL (ISO 27001, SOC 2, GDPR, PCI-DSS, HIPAA, NIST CSF) |
| DPO Alignment | Constitutional AI pairs (chosen vs rejected) |
| Quantization | 4-bit (LoRA adapters merged into full weights) |
| Hardware | Kaggle T4 GPU (Free Tier) |
| Context Length | 2048 tokens |

---

## ⚠️ Intended Use

This model is designed for:
- 🎓 Educational and portfolio demonstration purposes
- 🔬 Research into Constitutional AI and compliance automation
- 🏢 Prototyping GRC tooling and compliance assistants

This model is **not** a substitute for certified compliance professionals (CISA, CISSP, CPA). Always have findings reviewed by qualified auditors before acting on them.

---

## 📄 License

Apache 2.0 - Free to use, modify, and distribute with attribution.

---

*Built with ❤️ using [Unsloth](https://github.com/unslothai/unsloth)*

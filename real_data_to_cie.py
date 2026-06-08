"""
CIE Real Data → Training Format Converter
==========================================
Reads raw JSON files from data/raw/ and converts each case into
a proper CIE instruction-tuning training example.

Run after real_data_collector.py:
  python real_data_to_cie.py

Output:
  data/cie_real_sft.jsonl   — SFT training examples
  data/cie_real_dpo.jsonl   — DPO preference pairs
  data/stats.json           — dataset statistics
"""

import json, os, random, re
from pathlib import Path

random.seed(42)
RAW_DIR  = "data/raw"
OUT_DIR  = "data"
os.makedirs(OUT_DIR, exist_ok=True)

# ─── CIE System Prompt ───────────────────────────────────────────────────────
CIE_SYSTEM_PROMPT = """You are the Compliance Intelligence Engine (CIE), an advanced compliance, governance,
risk, privacy, cybersecurity, audit, and regulatory analysis system.

You operate as a senior compliance consultant, auditor, governance specialist,
cybersecurity assessor, privacy expert, risk analyst, and control mapping architect.
You must never behave as a generic chatbot.

CORE FRAMEWORKS: ISO 27001/27002, ISO 42001, NIST CSF 2.0, NIST 800-53, NIST AI RMF,
CIS Controls v8, SOC 2, PCI DSS v4.0, COBIT, HITRUST, FedRAMP, CMMC, CJIS,
GDPR, UK GDPR, CCPA/CPRA, HIPAA, HITECH, PIPEDA, LGPD, PIPL, PDPL, DPDP, APPI,
DORA, NIS2, ISO 22301, ISO 31000, EU AI Act, OECD AI Principles,
SOX, GLBA, FCA, SAMA CSF, Saudi ECC, Saudi PDPL, UAE PDPL, MAS, APRA.

OPERATING RULES:
1. Always identify the applicable framework, regulation, article, control, or clause first.
2. Never provide unsupported compliance conclusions.
3. Always explain reasoning behind every determination.
4. Classify compliance as exactly one of: COMPLIANT, PARTIALLY COMPLIANT,
   NON-COMPLIANT, INSUFFICIENT EVIDENCE.
5. Never assume evidence exists. If absent, classify as INSUFFICIENT EVIDENCE.
6. Always identify: assumptions made, risk implications, remediation steps, audit impact.
7. Never fabricate control IDs, article numbers, or legal obligations.
8. When uncertain, state uncertainty explicitly.

MANDATORY RESPONSE FORMAT:
## Executive Summary
## Applicable Frameworks & Controls
## Analysis
## Evidence Found
## Evidence Missing
## Risk Assessment
Likelihood: [Low|Medium|High|Critical]
Impact: [Low|Medium|High|Critical]
Risk Score: [1-100]
Risk Category: [Operational|Security|Privacy|Regulatory|Financial|Reputational]
## Compliance Determination
[COMPLIANT|PARTIALLY COMPLIANT|NON-COMPLIANT|INSUFFICIENT EVIDENCE]
## Cross-Framework Mapping
## Recommended Remediation
## Audit Impact
Finding: [Critical|Major|Minor|Observation]
## Confidence Score
[1-100]/100"""


def build_prompt(scenario: str, response: str) -> str:
    return (
        f"<s>[INST] <<SYS>>\n{CIE_SYSTEM_PROMPT}\n<</SYS>>\n\n"
        f"Assess the following compliance scenario:\n\n{scenario} [/INST] "
        f"{response}</s>"
    )


def generic_rejection(framework: str, topic: str) -> str:
    return (
        f"Based on what you've described, there might be some {framework} issues here. "
        f"You should look into {topic} requirements and make sure everything is in order. "
        f"It's important to stay compliant with applicable regulations."
    )


# ─── GDPR Converter ──────────────────────────────────────────────────────────
def convert_gdpr(cases: list) -> tuple:
    sft, dpo = [], []
    framework_map = {
        "Art. 5": "GDPR Art.5 (Principles of Processing)",
        "Art. 6": "GDPR Art.6 (Lawful Basis)",
        "Art. 7": "GDPR Art.7 (Conditions for Consent)",
        "Art. 9": "GDPR Art.9 (Special Category Data)",
        "Art. 13": "GDPR Art.13 (Transparency)",
        "Art. 17": "GDPR Art.17 (Right to Erasure)",
        "Art. 22": "GDPR Art.22 (Automated Decision Making)",
        "Art. 32": "GDPR Art.32 (Security of Processing)",
        "Art. 33": "GDPR Art.33 (Breach Notification — 72hrs to DPA)",
        "Art. 34": "GDPR Art.34 (Breach Notification — to Data Subjects)",
        "Art. 35": "GDPR Art.35 (DPIA)",
        "Art. 44": "GDPR Art.44 (International Transfers)",
        "Art. 46": "GDPR Art.46 (Transfers via SCCs)",
        "Art. 82": "GDPR Art.82 (Right to Compensation)",
    }

    for case in cases:
        summary = case.get("summary", "")
        if not summary or len(summary) < 50:
            continue

        entity   = case.get("entity", "the organisation")
        country  = case.get("country", "")
        fine_eur = case.get("fine_eur", 0)
        article  = case.get("article", "Art. 5, Art. 32")
        sector   = case.get("sector", "")
        date     = case.get("date", "")

        # Infer verdict
        if fine_eur > 0:
            verdict = "NON-COMPLIANT"
        elif "partially" in summary.lower():
            verdict = "PARTIALLY COMPLIANT"
        else:
            verdict = "NON-COMPLIANT"

        # Infer risk
        if fine_eur > 10_000_000:
            likelihood, impact, risk_score, finding = "Critical", "Critical", min(99, 80 + random.randint(0, 15)), "Critical"
        elif fine_eur > 1_000_000:
            likelihood, impact, risk_score, finding = "High", "Critical", random.randint(75, 88), "Critical"
        elif fine_eur > 100_000:
            likelihood, impact, risk_score, finding = "High", "High", random.randint(60, 78), "Major"
        else:
            likelihood, impact, risk_score, finding = "Medium", "Medium", random.randint(40, 65), "Minor"

        # Map articles to controls
        controls_list = []
        for art_key, art_val in framework_map.items():
            if art_key in str(article):
                controls_list.append(art_val)
        if not controls_list:
            controls_list = ["GDPR Art.5 (Principles)", "GDPR Art.32 (Security of Processing)"]

        fine_str = f"€{fine_eur:,}" if fine_eur > 0 else "Enforcement action without monetary fine"

        # Build remediation list
        remed_raw = case.get("remediation", ["Review applicable GDPR requirements and implement appropriate controls."])
        if isinstance(remed_raw, list):
            remed_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(remed_raw))
        else:
            remed_text = f"1. {remed_raw}"

        scenario_text = (
            f"[REAL ENFORCEMENT CASE — {date or 'Date not disclosed'}] "
            f"{entity} ({sector}, {country}): {summary}"
        )

        response = f"""## Executive Summary
{verdict}. Regulatory enforcement action against {entity} for violations of {article}. {fine_str} penalty imposed.

## Applicable Frameworks & Controls
Primary regulation: General Data Protection Regulation (EU) 2016/679
Violated provisions:
{chr(10).join('- ' + c for c in controls_list)}
Cross-applicable: UK GDPR (same text post-Brexit), ISO 27701 (Privacy Information Management)

## Analysis
The enforcement decision by the supervisory authority confirms a finding of non-conformity with GDPR requirements. {summary}

The regulator determined that the processing activity violated the principle(s) cited above. Enforcement actions of this nature demonstrate that supervisory authorities will impose significant financial penalties where organisations fail to implement appropriate technical and organisational measures.

## Evidence Found
- Regulatory enforcement decision issued
- Fine of {fine_str} confirmed
- Violations: {article}
- Sector: {sector}

## Evidence Missing
- Organisation's remediation plan post-enforcement
- Details of all technical measures evaluated
- Full audit trail of data processing activities

## Risk Assessment
Likelihood: {likelihood}
Impact: {impact}
Risk Score: {risk_score}/100
Risk Category: Regulatory

## Compliance Determination
{verdict}

## Cross-Framework Mapping
| GDPR Article | ISO 27001 Control | NIST CSF |
|---|---|---|
| {controls_list[0]} | ISO 27001 A.5.34 (Privacy) | PR.DS / PR.AC |
| {controls_list[1] if len(controls_list) > 1 else controls_list[0]} | ISO 27001 A.8.24 / A.5.19 | ID.RA / RS.CO |

## Recommended Remediation
{remed_text}

## Audit Impact
Finding: {finding}
{"Immediate regulatory engagement required. Board-level escalation mandatory." if finding == "Critical" else "Corrective action plan required with defined timelines and ownership."}

## Confidence Score
95/100 — Based on published regulatory enforcement decision."""

        prompt = build_prompt(scenario_text, response)
        sft.append({"text": prompt, "framework": "GDPR", "verdict": verdict, "source": "real_enforcement"})
        dpo.append({
            "prompt": f"<s>[INST] <<SYS>>\n{CIE_SYSTEM_PROMPT}\n<</SYS>>\n\nAssess: {scenario_text} [/INST] ",
            "chosen": response,
            "rejected": generic_rejection("GDPR", "data protection"),
        })

    return sft, dpo


# ─── HIPAA Converter ─────────────────────────────────────────────────────────
def convert_hipaa(cases: list) -> tuple:
    sft, dpo = [], []

    for case in cases:
        summary = case.get("summary", case.get("raw_text", ""))
        if not summary or len(summary) < 60:
            continue

        entity     = case.get("entity", "Covered Entity")
        sector     = case.get("sector", "Healthcare")
        penalty    = case.get("penalty_usd", 0)
        rule       = case.get("rule", "Security Rule")
        category   = case.get("category", "Security")
        phi_count  = case.get("phi_records", 0)
        det        = case.get("determination", "NON-COMPLIANT")
        finding    = case.get("finding", "Major")
        remed      = case.get("remediation", ["Implement appropriate HIPAA safeguards."])

        remed_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(remed)) if isinstance(remed, list) else f"1. {remed}"
        penalty_str = f"${penalty:,}" if penalty > 0 else "Corrective Action Plan (no monetary penalty)"
        phi_str     = f"{phi_count:,} individuals affected" if phi_count > 0 else "number of affected individuals not disclosed"

        if penalty > 5_000_000:
            likelihood, impact, risk_score = "Critical", "Critical", random.randint(85, 97)
        elif penalty > 1_000_000:
            likelihood, impact, risk_score = "High", "Critical", random.randint(72, 87)
        elif penalty > 0:
            likelihood, impact, risk_score = "High", "High", random.randint(58, 75)
        else:
            likelihood, impact, risk_score = "Medium", "Medium", random.randint(40, 60)

        if det == "COMPLIANT":
            likelihood, impact, risk_score = "Low", "Low", random.randint(3, 12)

        scenario_text = (
            f"[HIPAA ENFORCEMENT] {entity} ({sector}): {summary} "
            f"Settlement: {penalty_str}. {phi_str}."
        )

        response = f"""## Executive Summary
{det}. HHS Office for Civil Rights enforcement action against {entity} for violations of the HIPAA {rule}. {penalty_str} resolution agreement. {phi_str}.

## Applicable Frameworks & Controls
Primary regulation: Health Insurance Portability and Accountability Act (HIPAA) — {rule}
Key provisions:
- HIPAA Security Rule §164.308 (Administrative Safeguards)
- HIPAA Security Rule §164.310 (Physical Safeguards)
- HIPAA Security Rule §164.312 (Technical Safeguards)
- HIPAA Privacy Rule §164.502 (Uses and Disclosures)
Category: {category}
Cross-applicable: NIST 800-66 (HIPAA Security Rule Guidance), HITRUST CSF

## Analysis
The HHS OCR investigation determined that {entity} failed to implement required HIPAA safeguards. {summary}

OCR's Resolution Agreement requires {entity} to implement a Corrective Action Plan (CAP) in addition to the monetary settlement. The violations identified represent systemic failures in the organisation's HIPAA compliance programme rather than isolated incidents.

## Evidence Found
- HHS OCR enforcement action confirmed
- Resolution agreement: {penalty_str}
- PHI exposure: {phi_str}
- Violation category: {category}

## Evidence Missing
- Complete forensic analysis of all PHI affected
- Full technical architecture review results
- Post-incident remediation verification

## Risk Assessment
Likelihood: {likelihood}
Impact: {impact}
Risk Score: {risk_score}/100
Risk Category: {"Privacy" if "Privacy" in rule else "Security"}

## Compliance Determination
{det}

## Cross-Framework Mapping
| HIPAA Provision | ISO 27001 Equivalent | NIST Control |
|---|---|---|
| §164.312(a)(1) Access Control | ISO 27001 A.5.15 | AC-2, AC-3 |
| §164.312(e)(2) Encryption | ISO 27001 A.8.24 | SC-28 |
| §164.308(a)(1) Risk Analysis | ISO 27001 A.6.1.2 | RA-3 |

## Recommended Remediation
{remed_text}

## Audit Impact
Finding: {finding}
{"Immediate corrective action required. Designate HIPAA Security Officer and implement Corrective Action Plan." if finding in ["Critical", "Major"] else "Monitor implementation of current safeguards and document compliance."}

## Confidence Score
96/100 — Based on published HHS OCR enforcement action."""

        prompt = build_prompt(scenario_text, response)
        sft.append({"text": prompt, "framework": "HIPAA", "verdict": det, "source": "real_enforcement"})
        dpo.append({
            "prompt": f"<s>[INST] <<SYS>>\n{CIE_SYSTEM_PROMPT}\n<</SYS>>\n\nAssess: {scenario_text} [/INST] ",
            "chosen": response,
            "rejected": generic_rejection("HIPAA", "protected health information"),
        })

    return sft, dpo


# ─── NIST CSF Converter ───────────────────────────────────────────────────────
def convert_nist(cases: list) -> tuple:
    sft, dpo = [], []

    for case in cases:
        summary = case.get("summary", "")
        if not summary or len(summary) < 60:
            continue

        function    = case.get("function", "")
        category    = case.get("category", "")
        sub_id      = case.get("subcategory_id", "")
        entity      = case.get("entity", "Organisation")
        finding_type= case.get("finding_type", "NON-COMPLIANT")
        audit_src   = case.get("audit_source", "Security Assessment")
        finding     = case.get("finding", "Major")
        risk_score  = case.get("risk_score", 70)
        remed       = case.get("remediation", ["Implement appropriate NIST CSF controls."])

        remed_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(remed)) if isinstance(remed, list) else f"1. {remed}"

        if finding_type == "COMPLIANT":
            likelihood, impact = "Low", "Low"
        elif finding_type == "PARTIALLY COMPLIANT":
            likelihood, impact = "Medium", "Medium"
        else:
            likelihood = "High" if risk_score > 70 else "Medium"
            impact     = "Critical" if risk_score > 85 else "High" if risk_score > 65 else "Medium"

        scenario_text = (
            f"[NIST CSF AUDIT — {audit_src}] {entity}. "
            f"Function: {function}. Category: {category}. Control: {sub_id}. "
            f"Finding: {summary}"
        )

        response = f"""## Executive Summary
{finding_type}. Audit assessment of {entity} against NIST Cybersecurity Framework 2.0, {function} function, {category}. Control reference: {sub_id}. Audit source: {audit_src}.

## Applicable Frameworks & Controls
Primary framework: NIST Cybersecurity Framework (CSF) 2.0
Function: {function}
Category: {category}
Subcategory: {sub_id}
Cross-applicable frameworks:
- ISO 27001:2022 (mapped controls depend on CSF subcategory)
- NIST SP 800-53 Rev. 5 (NIST CSF Informative References)
- CIS Controls v8 (Implementation Groups)

## Analysis
The audit assessment against NIST CSF 2.0 identified the following: {summary}

NIST CSF provides a voluntary framework but is referenced as a baseline by multiple mandatory frameworks (FedRAMP, Executive Order 14028, FISMA). Non-conformity with CSF subcategories represents a material gap in an organisation's cybersecurity posture.

## Evidence Found
- Audit source: {audit_src}
- Assessment scope: {function} — {category}
- Control evaluated: {sub_id}
- Finding: {finding_type}

## Evidence Missing
- Full scope assessment across all five NIST CSF functions
- Quantified maturity tier assessment
- Risk-based prioritisation of all identified gaps

## Risk Assessment
Likelihood: {likelihood}
Impact: {impact}
Risk Score: {risk_score}/100
Risk Category: Security

## Compliance Determination
{finding_type}

## Cross-Framework Mapping
| NIST CSF | ISO 27001 | NIST 800-53 |
|---|---|---|
| {sub_id} | A.5.15 / A.8.8 / A.5.24 | SI-2 / AC-2 / IR-4 |

## Recommended Remediation
{remed_text}

## Audit Impact
Finding: {finding}
{"Immediate remediation required. Include in risk register with executive visibility." if finding in ["Critical", "Major"] else "Schedule remediation in next planning cycle. Track to closure."}

## Confidence Score
88/100 — Based on formal audit assessment against published NIST CSF 2.0 framework."""

        prompt = build_prompt(scenario_text, response)
        sft.append({"text": prompt, "framework": "NIST CSF", "verdict": finding_type, "source": "real_audit"})
        dpo.append({
            "prompt": f"<s>[INST] <<SYS>>\n{CIE_SYSTEM_PROMPT}\n<</SYS>>\n\nAssess: {scenario_text} [/INST] ",
            "chosen": response,
            "rejected": generic_rejection("NIST CSF", "cybersecurity controls"),
        })

    return sft, dpo


# ─── PCI DSS Converter ───────────────────────────────────────────────────────
def convert_pci(cases: list) -> tuple:
    sft, dpo = [], []

    for case in cases:
        summary = case.get("summary", "")
        if not summary or len(summary) < 60:
            continue

        entity      = case.get("entity", "Merchant/Service Provider")
        sector      = case.get("sector", "")
        breach_size = case.get("breach_size", 0)
        fine_usd    = case.get("fine_usd", 0)
        reqs        = case.get("requirements_violated", [])
        vector      = case.get("attack_vector", "")
        det         = case.get("determination", "NON-COMPLIANT")
        finding     = case.get("finding", "Critical")
        remed       = case.get("remediation", ["Implement PCI DSS requirements."])

        remed_text  = "\n".join(f"{i+1}. {r}" for i, r in enumerate(remed)) if isinstance(remed, list) else f"1. {remed}"
        breach_str  = f"{breach_size:,} cards compromised" if breach_size > 0 else "no confirmed card compromise"
        fine_str    = f"${fine_usd:,} fine/settlement" if fine_usd > 0 else "card brand fines not publicly disclosed"
        reqs_str    = "\n".join(f"- {r}" for r in reqs) if reqs else "- Multiple PCI DSS requirements"
        vector_str  = f"Attack vector: {vector}" if vector and vector != "N/A — proactive assessment" else ""

        if det == "COMPLIANT":
            likelihood, impact, risk_score = "Low", "Low", random.randint(3, 10)
        elif breach_size > 1_000_000:
            likelihood, impact, risk_score = "Critical", "Critical", random.randint(88, 98)
        elif breach_size > 100_000:
            likelihood, impact, risk_score = "High", "Critical", random.randint(78, 90)
        else:
            likelihood, impact, risk_score = "High", "High", random.randint(65, 80)

        scenario_text = (
            f"[PCI DSS BREACH/ASSESSMENT] {entity} ({sector}): {summary} "
            f"{vector_str}. {breach_str}. {fine_str}."
        )

        response = f"""## Executive Summary
{det}. PCI DSS compliance assessment of {entity}. {breach_str}. {fine_str}.

## Applicable Frameworks & Controls
Primary standard: PCI DSS v4.0
Violated requirements:
{reqs_str}
Cross-applicable:
- ISO 27001 A.8.24 (Cryptography), A.5.15 (Access Control)
- NIST CSF PR.DS (Data Security), DE.CM (Monitoring)
- SOC 2 CC6.1, CC6.6, CC7.1

## Analysis
{summary} {vector_str}

PCI DSS requires all entities that store, process, or transmit cardholder data to maintain a secure environment. The identified failures represent violations of the standard's technical and operational requirements. Organisations found non-compliant face card brand fines, forensic investigation costs, and potential loss of card acceptance privileges.

## Evidence Found
- Breach/assessment evidence: {breach_str}
- Financial impact: {fine_str}
- Failed requirements: {', '.join(reqs) if reqs else 'Multiple requirements'}

## Evidence Missing
- Complete Qualified Security Assessor (QSA) Report on Compliance (RoC)
- Network segmentation verification results
- Full scope of cardholder data environment

## Risk Assessment
Likelihood: {likelihood}
Impact: {impact}
Risk Score: {risk_score}/100
Risk Category: {"Security" if det != "COMPLIANT" else "Operational"}

## Compliance Determination
{det}

## Cross-Framework Mapping
| PCI DSS Requirement | ISO 27001 | NIST CSF |
|---|---|---|
| Req. 3 (Stored Data) | A.8.24 | PR.DS-1 |
| Req. 6 (Secure Systems) | A.8.8 | PR.IP-12 |
| Req. 10 (Logging) | A.8.15 | DE.CM-1 |
| Req. 12 (Policy) | A.5.1 | GV.PO |

## Recommended Remediation
{remed_text}

## Audit Impact
Finding: {finding}
{"Critical finding — immediate remediation required. Engage QSA for validation. Notify acquiring bank." if finding == "Critical" else "Corrective action required before next QSA assessment."}

## Confidence Score
{"97" if breach_size > 0 else "88"}/100 — Based on {"publicly documented breach investigation" if breach_size > 0 else "QSA assessment findings"}."""

        prompt = build_prompt(scenario_text, response)
        sft.append({"text": prompt, "framework": "PCI DSS", "verdict": det, "source": "real_breach"})
        dpo.append({
            "prompt": f"<s>[INST] <<SYS>>\n{CIE_SYSTEM_PROMPT}\n<</SYS>>\n\nAssess: {scenario_text} [/INST] ",
            "chosen": response,
            "rejected": generic_rejection("PCI DSS", "cardholder data"),
        })

    return sft, dpo


# ─── ISO 27001 Converter ─────────────────────────────────────────────────────
def convert_iso27001(cases: list) -> tuple:
    sft, dpo = [], []

    for case in cases:
        summary = case.get("summary", case.get("raw_text", ""))
        if not summary or len(summary) < 60:
            continue

        entity    = case.get("entity", "Organisation")
        sector    = case.get("sector", "")
        controls  = case.get("controls_violated", [])
        clause    = case.get("clause", "")
        det       = case.get("determination", "NON-COMPLIANT")
        likelihood= case.get("likelihood", "High")
        impact    = case.get("impact", "High")
        risk_score= case.get("risk_score", 75)
        finding   = case.get("finding", "Major")
        remed     = case.get("remediation", ["Implement appropriate ISO 27001 controls."])
        source_url= case.get("source_url", "")

        remed_text  = "\n".join(f"{i+1}. {r}" for i, r in enumerate(remed)) if isinstance(remed, list) else f"1. {remed}"
        controls_str= "\n".join(f"- {c}" for c in controls) if controls else "- Multiple ISO 27001 controls"

        scenario_text = (
            f"[ISO 27001 / REAL INCIDENT] {entity} ({sector}): {summary}"
        )

        response = f"""## Executive Summary
{det}. ISO 27001:2022 assessment of {entity} ({sector}). Analysis based on documented incident/assessment. Clause(s) relevant: {clause or 'Multiple clauses'}.

## Applicable Frameworks & Controls
Primary standard: ISO/IEC 27001:2022 (Information Security Management Systems)
Controls assessed:
{controls_str}
Cross-applicable:
- ISO 27002:2022 (Implementation guidance)
- NIST CSF 2.0 (mapped by ISO/IEC 27001:2022 Annex A)
- SOC 2 Trust Service Criteria

## Analysis
{summary}

ISO 27001 requires organisations to implement an Information Security Management System (ISMS) with appropriate controls selected based on risk. The identified failures indicate either: (a) controls were not implemented, (b) controls were implemented but not operating effectively, or (c) the risk assessment failed to identify the relevant risk. All three scenarios represent failures of the ISMS.

## Evidence Found
- Documented incident/assessment: confirmed
- Controls violated: {clause or 'Multiple'}
- Sector context: {sector}
{f"- Public source: {source_url}" if source_url else ""}

## Evidence Missing
- ISO 27001 certification audit results
- Risk treatment plan
- Statement of Applicability (SoA)
- Management review records

## Risk Assessment
Likelihood: {likelihood}
Impact: {impact}
Risk Score: {risk_score}/100
Risk Category: Security

## Compliance Determination
{det}

## Cross-Framework Mapping
| ISO 27001 Control | NIST CSF | SOC 2 |
|---|---|---|
| {controls[0] if controls else 'A.5.1 (Policies)'} | GV.PO / PR.AC | CC1.1 / CC6.1 |
| {controls[1] if len(controls) > 1 else 'A.8.8 (Vuln Mgmt)'} | DE.CM / PR.IP | CC7.1 / CC4.1 |

## Recommended Remediation
{remed_text}

## Audit Impact
Finding: {finding}
{"Major/Critical nonconformity under ISO 27001. Certification body must be notified. Corrective action required within 90 days or certificate suspended." if finding in ["Critical", "Major"] else "Minor nonconformity. Corrective action required at next surveillance audit."}

## Confidence Score
{"94" if det != "COMPLIANT" else "91"}/100 — Based on {"documented incident investigation" if det != "COMPLIANT" else "formal certification audit"}."""

        prompt = build_prompt(scenario_text, response)
        sft.append({"text": prompt, "framework": "ISO 27001", "verdict": det, "source": "real_incident"})
        dpo.append({
            "prompt": f"<s>[INST] <<SYS>>\n{CIE_SYSTEM_PROMPT}\n<</SYS>>\n\nAssess: {scenario_text} [/INST] ",
            "chosen": response,
            "rejected": generic_rejection("ISO 27001", "information security management"),
        })

    return sft, dpo


# ─── Augmentation ────────────────────────────────────────────────────────────
def augment(records: list, target: int) -> list:
    """Augment by paraphrasing scenarios with varied prefixes/suffixes."""
    PREFIXES = [
        "Our external auditor found: ", "The QSA report states: ",
        "During our annual penetration test: ", "The incident investigation revealed: ",
        "The DPA investigation found: ", "Our internal audit identified: ",
        "The forensic analysis determined: ", "Post-breach review confirmed: ",
    ]
    SUFFIXES = [
        " The finding has been escalated to the board.",
        " No compensating controls were documented.",
        " The control failure has been present for over 12 months.",
        " Remediation timeline is currently unknown.",
        " A third-party assessor confirmed the finding.",
    ]
    augmented = list(records)
    while len(augmented) < target:
        base   = random.choice(records)
        text   = base["text"]
        # Inject a prefix into the scenario part (between [INST] and [/INST])
        prefix = random.choice(PREFIXES)
        suffix = random.choice(SUFFIXES)
        new_text = re.sub(
            r"(Assess the following compliance scenario:\n\n)(.+?)( \[/INST\])",
            lambda m: m.group(1) + prefix + m.group(2).lower()[:200] + suffix + m.group(3),
            text,
            flags=re.DOTALL,
        )
        if new_text != text:
            augmented.append({
                "text": new_text,
                "framework": base["framework"],
                "verdict": base["verdict"],
                "source": "augmented",
            })
    return augmented[:target]


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("CIE Real Data → Training Format Converter")
    print("=" * 60)

    all_sft, all_dpo = [], []

    converters = [
        ("gdpr_cases.json",     "GDPR",      convert_gdpr),
        ("hipaa_cases.json",    "HIPAA",     convert_hipaa),
        ("nist_cases.json",     "NIST CSF",  convert_nist),
        ("pci_cases.json",      "PCI DSS",   convert_pci),
        ("iso27001_cases.json", "ISO 27001", convert_iso27001),
    ]

    framework_counts = {}
    for filename, label, converter in converters:
        path = Path(RAW_DIR) / filename
        if not path.exists():
            print(f"  [SKIP] {filename} not found — run real_data_collector.py first")
            continue
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        sft, dpo = converter(raw)
        print(f"  {label:<12}: {len(sft):>3} SFT examples, {len(dpo):>3} DPO pairs (from {len(raw)} raw cases)")
        framework_counts[label] = len(sft)
        all_sft.extend(sft)
        all_dpo.extend(dpo)

    base_count = len(all_sft)
    print(f"\nBase examples: {base_count}")
    print("Augmenting to 500+ examples...")
    all_sft = augment(all_sft, max(500, base_count * 3))
    print(f"After augmentation: {len(all_sft)}")

    random.shuffle(all_sft)
    random.shuffle(all_dpo)

    # Write outputs
    sft_path = f"{OUT_DIR}/cie_real_sft.jsonl"
    dpo_path = f"{OUT_DIR}/cie_real_dpo.jsonl"

    with open(sft_path, "w", encoding="utf-8") as f:
        for r in all_sft:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(dpo_path, "w", encoding="utf-8") as f:
        for r in all_dpo:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Verdict distribution
    verdict_dist = {}
    for r in all_sft:
        v = r.get("verdict", "UNKNOWN")
        verdict_dist[v] = verdict_dist.get(v, 0) + 1

    stats = {
        "total_sft": len(all_sft),
        "total_dpo": len(all_dpo),
        "base_examples": base_count,
        "augmented_examples": len(all_sft) - base_count,
        "frameworks": framework_counts,
        "verdict_distribution": verdict_dist,
        "data_sources": ["GDPR Enforcement Tracker", "HHS OCR Enforcement", "GAO/CISA Audit Reports", "PCI DSS Breach Cases", "ICO / NCSC Decisions"],
    }

    with open(f"{OUT_DIR}/stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    print("\n" + "=" * 60)
    print("CONVERSION COMPLETE")
    print("=" * 60)
    print(f"  SFT examples : {len(all_sft):,}  -> {sft_path}")
    print(f"  DPO pairs    : {len(all_dpo):,}  -> {dpo_path}")
    print(f"  Verdict dist : {verdict_dist}")
    print(f"\nNext: upload data/ folder to Kaggle as a Dataset,")
    print(f"      then reference it in the notebook.")

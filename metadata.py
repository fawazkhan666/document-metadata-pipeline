import json
import os
import re
from typing import Any, Dict

import requests


SCHEMA_DEFAULT = {
    "document_type": "unknown",
    "document_status": "unknown",
    "version": "unknown",
    "project": "unknown",
    "customer": "unknown",
    "practice": "unknown",
    "project_phase": "unknown",
    "workstream": [],
    "systems": [],
    "data_sensitivity": "unknown",
    "contains_pii": "unknown",
    "tags": [],
    "summary": "unknown",
}

ENUM_CONSTRAINTS = {
    "document_type": [
        "SOW",
        "Status Report",
        "Technical Design Document",
        "Test Plan",
        "Training Material",
    ],
    "project_phase": ["Discovery", "Design", "Build", "Test", "Deploy", "Hypercare", "Closeout"],
    "data_sensitivity": ["Public", "Internal", "Confidential", "Restricted"],
    "contains_pii": ["Yes", "No"],
}


def _build_json_schema() -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required = []

    for key, default in SCHEMA_DEFAULT.items():
        required.append(key)
        if isinstance(default, list):
            properties[key] = {
                "type": "array",
                "items": {"type": "string"},
            }
            continue
        if key in ENUM_CONSTRAINTS:
            properties[key] = {"type": "string", "enum": ENUM_CONSTRAINTS[key]}
        else:
            properties[key] = {"type": "string"}

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _metadata_prompt(context: str, file_name: str, file_type: str) -> str:
    schema_hint = json.dumps(_build_json_schema(), indent=2)
    return f"""You are a document analyst. Extract metadata from the document below.

FILE NAME: {file_name}
FILE TYPE: {file_type.upper()}

=== DOCUMENT CONTENT ===
{context[:5000]}
=== END OF DOCUMENT ===

Return ONLY a valid JSON object. No markdown. No explanation. No code fences.

FIELD INSTRUCTIONS — read carefully before filling each field:

- document_type: Category of document. Must be one of: SOW, Status Report, Technical Design Document, Test Plan, Training Material
- document_status: Look for words like Draft, Active, Final, Approved, In Progress IN THE CONTENT. Do NOT use the file name. If not found use "unknown".
- version: Look for these exact patterns only: "v0.1", "v0.2", "v0.9", "v1", "v1.0", "v1.1", "v2", "v2.0", "Final", "Signed". Extract exactly what is written. Do NOT use file name. Do NOT use dates. If not found use "unknown".
- project: The full project name from the document content. Example: "PeopleSoft HCM Implementation"
- customer: The client or company being served. Example: "Contoso Corporation". Do NOT use the consulting firm name.
- practice: The technology or business domain. Examples: "Oracle PeopleSoft", "SAP S/4HANA", "AWS", "ServiceNow", "Workday", "Azure". Extract from content.
- project_phase: The CURRENT phase of the project. Must be one of: Discovery, Design, Build, Test, Deploy, Hypercare, Closeout. Pick the most prominent phase mentioned.
- workstream: List of work areas mentioned. Examples: ["Data Migration", "HR Configuration", "Payroll", "Testing"]
- systems: List of ALL technologies tools platforms mentioned. Examples: ["PeopleSoft HCM 9.2", "Azure", "Azure Data Factory", "Oracle"]
- data_sensitivity: Based on content sensitivity. Must be one of: Public, Internal, Confidential, Restricted. SOWs with financials = Confidential.
- contains_pii: Does the document contain real personal data like names emails IDs? Yes or No.
- tags: 5 to 8 keywords describing this document. Examples: ["SOW", "PeopleSoft", "HCM", "Contoso", "Implementation"]
- summary: Write a 2-3 sentence contextual summary of the entire document. Cover what the document is about, who it involves, what systems or technologies are mentioned, and the current phase or status. Base it only on the document content above.

IMPORTANT — common mistakes to avoid:
- NEVER put a file name in the version field
- NEVER put a date in the version field
- NEVER copy-paste field instructions as values
- ONLY use "unknown" when the information is truly absent from the document content

JSON schema to follow:
{schema_hint}
""".strip()


def _normalize_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(SCHEMA_DEFAULT)

    for key, default_value in SCHEMA_DEFAULT.items():
        value = data.get(key, default_value)

        if isinstance(default_value, list):
            if isinstance(value, list):
                normalized[key] = [str(item).strip() for item in value if str(item).strip()]
            elif isinstance(value, str) and value.strip():
                normalized[key] = [value.strip()]
            else:
                normalized[key] = []
            continue

        if isinstance(value, str) and value.strip():
            normalized_value = value.strip()
            # Reject file names sneaking into scalar fields
            if normalized_value.endswith((".docx", ".pdf", ".xml", ".doc")):
                normalized[key] = "unknown"
            elif key in ENUM_CONSTRAINTS and normalized_value not in ENUM_CONSTRAINTS[key]:
                normalized[key] = "unknown"
            else:
                normalized[key] = normalized_value
        else:
            normalized[key] = "unknown"

    # Keep summary as-is — full contextual text, no truncation
    summary = data.get("summary", "")
    normalized["summary"] = summary.strip() if isinstance(summary, str) and summary.strip() else "unknown"

    return normalized


def safe_parse(raw_text: str) -> Dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        return dict(SCHEMA_DEFAULT)

    candidates = [text]

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1))

    bracketed = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if bracketed:
        candidates.append(bracketed.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return _normalize_metadata(parsed)
        except json.JSONDecodeError:
            continue

    return dict(SCHEMA_DEFAULT)


def generate_metadata(context: str, file_name: str, file_type: str) -> Dict[str, Any]:
    if not (context or "").strip():
        return dict(SCHEMA_DEFAULT)

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip().rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "qwen3:8b").strip()
    timeout_seconds = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180").strip() or "180")

    # /api/generate is the correct endpoint — always first
    endpoints = [
        f"{base_url}/api/generate",
        f"{base_url}/api/chat",
    ]

    headers = {"Content-Type": "application/json"}
    prompt_text = _metadata_prompt(context=context, file_name=file_name, file_type=file_type)
    errors = []

    for endpoint in endpoints:
        try:
            if endpoint.endswith("/api/generate"):
                payload = {
                    "model": model,
                    "prompt": prompt_text,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0, "num_predict": 1000},
                }
            else:
                payload = {
                    "model": model,
                    "stream": False,
                    "format": _build_json_schema(),
                    "options": {"temperature": 0},
                    "messages": [
                        {
                            "role": "system",
                            "content": "You extract enterprise document metadata. Return JSON only.",
                        },
                        {
                            "role": "user",
                            "content": prompt_text,
                        },
                    ],
                }

            print(f"  -> Trying: {endpoint} (model: {model})")
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()

            if endpoint.endswith("/api/generate"):
                content = body.get("response", "")
            else:
                content = body.get("message", {}).get("content", "")

            print(f"  -> Raw response preview: {str(content)[:300]}")

            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )

            result = safe_parse(str(content))

            if is_unknown_metadata(result):
                print(f"  ! All fields unknown for {file_name} — check model output above")
            else:
                print(f"  + Metadata extracted OK for {file_name}")

            return result

        except requests.exceptions.ConnectionError:
            err = f"{endpoint}: Cannot connect — run: ollama serve"
            print(f"  ! {err}")
            errors.append(err)
        except requests.exceptions.Timeout:
            err = f"{endpoint}: Timed out after {timeout_seconds}s"
            print(f"  ! {err}")
            errors.append(err)
            break
        except requests.RequestException as e:
            err = f"{endpoint}: {e}"
            print(f"  ! {err}")
            errors.append(err)

    print(f"Ollama metadata call failed for {file_name}: {' | '.join(errors)}")
    return dict(SCHEMA_DEFAULT)


def is_unknown_metadata(data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return True
    normalized = _normalize_metadata(data)
    return normalized == SCHEMA_DEFAULT
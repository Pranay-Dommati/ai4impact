import json
import logging
import re
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

GEMINI_PROMPT_TEMPLATE = """
You are an AI governance agent.

Convert the complaint into structured JSON.

Rules:
- Extract category, issue_type, location details
- Analyze severity, urgency, risk_type
- Estimate affected population
- Assign priority (low, medium, high) with score (0-100)
- Provide reasoning (short bullet points)
- Generate cluster_id (category + area + issue_type)
- Assign department and sub_department
- Include confidence between 0 and 1
- Keep values concise and realistic

Return ONLY valid JSON. No extra text.

JSON Schema:
{
  "meta": {
    "source": "portal or telegram",
    "confidence": 0.0
  },
  "extracted": {
    "category": "electricity|water|roads|sanitation|other",
    "issue_type": "snake_case_issue",
    "description_cleaned": "string",
    "location": {
      "city": "string",
      "area": "string",
      "zone": "string",
      "location_type": "road|school|hospital|residential|other"
    },
    "keywords": ["string"]
  },
  "impact": {
    "severity": "low|medium|high",
    "urgency": "low|medium|high",
    "risk_type": "string",
    "affected_population_estimate": 0,
    "duration_hint": "string"
  },
  "priority": {
    "level": "low|medium|high",
    "score": 0,
    "reasoning": ["string"]
  },
  "clustering": {
    "cluster_id": "string",
    "tags": ["string"]
  },
  "routing": {
    "department": "string",
    "sub_department": "string",
    "jurisdiction": "string"
  }
}

Input:
{user_input}
""".strip()


def _extract_json_blob(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None

    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"```$", "", raw).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None

    return None


def _extract_candidate_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates", [])
    if not candidates:
        return ""

    first = candidates[0] or {}
    content = first.get("content", {})
    parts = content.get("parts", [])
    if not parts:
        return ""

    return "".join(part.get("text", "") for part in parts)


def _normalize_structured_payload(payload: dict[str, Any] | None, source: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    extracted = payload.get("extracted") if isinstance(payload.get("extracted"), dict) else {}
    location = extracted.get("location") if isinstance(extracted.get("location"), dict) else {}
    impact = payload.get("impact") if isinstance(payload.get("impact"), dict) else {}
    priority = payload.get("priority") if isinstance(payload.get("priority"), dict) else {}
    clustering = payload.get("clustering") if isinstance(payload.get("clustering"), dict) else {}
    routing = payload.get("routing") if isinstance(payload.get("routing"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}

    category = str(extracted.get("category", "other")).strip().lower() or "other"
    if category not in {"electricity", "water", "roads", "sanitation", "other"}:
        category = "other"

    confidence_raw = meta.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    level = str(priority.get("level", "medium")).strip().lower() or "medium"
    if level not in {"low", "medium", "high"}:
        level = "medium"

    severity = str(impact.get("severity", "medium")).strip().lower() or "medium"
    if severity not in {"low", "medium", "high"}:
        severity = "medium"

    urgency = str(impact.get("urgency", "medium")).strip().lower() or "medium"
    if urgency not in {"low", "medium", "high"}:
        urgency = "medium"

    reasoning = priority.get("reasoning")
    if not isinstance(reasoning, list):
        reasoning = []

    keywords = extracted.get("keywords")
    if not isinstance(keywords, list):
        keywords = []

    tags = clustering.get("tags")
    if not isinstance(tags, list):
        tags = []

    return {
        "meta": {
            "source": str(meta.get("source") or source),
            "confidence": confidence,
        },
        "extracted": {
            "category": category,
            "issue_type": str(extracted.get("issue_type", "general_issue")).strip() or "general_issue",
            "description_cleaned": str(extracted.get("description_cleaned", "")).strip(),
            "location": {
                "city": str(location.get("city", "")).strip(),
                "area": str(location.get("area", "")).strip(),
                "zone": str(location.get("zone", "")).strip(),
                "location_type": str(location.get("location_type", "other")).strip().lower() or "other",
            },
            "keywords": [str(item).strip() for item in keywords if str(item).strip()],
        },
        "impact": {
            "severity": severity,
            "urgency": urgency,
            "risk_type": str(impact.get("risk_type", "public_service")).strip() or "public_service",
            "affected_population_estimate": int(impact.get("affected_population_estimate", 0) or 0),
            "duration_hint": str(impact.get("duration_hint", "unknown")).strip() or "unknown",
        },
        "priority": {
            "level": level,
            "score": int(priority.get("score", 50) or 50),
            "reasoning": [str(item).strip() for item in reasoning if str(item).strip()],
        },
        "clustering": {
            "cluster_id": str(clustering.get("cluster_id", "")).strip(),
            "tags": [str(item).strip() for item in tags if str(item).strip()],
        },
        "routing": {
            "department": str(routing.get("department", "Unassigned")).strip() or "Unassigned",
            "sub_department": str(routing.get("sub_department", "General")).strip() or "General",
            "jurisdiction": str(routing.get("jurisdiction", "")).strip(),
        },
    }


def _call_gemini_once(*, api_key: str, model_name: str, source: str, prompt: str, use_response_mime: bool) -> dict[str, Any] | None:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        f"?key={api_key}"
    )

    generation_config: dict[str, Any] = {"temperature": 0.1}
    if use_response_mime:
        generation_config["responseMimeType"] = "application/json"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"Source: {source}\n\n{prompt}"}],
            }
        ],
        "generationConfig": generation_config,
    }

    response = requests.post(url, json=payload, timeout=20)
    response.raise_for_status()
    data = response.json()

    text = _extract_candidate_text(data)
    parsed = _extract_json_blob(text)
    normalized = _normalize_structured_payload(parsed, source)
    if normalized:
        return normalized

    # Some Gemini outputs wrap JSON under common keys.
    if isinstance(parsed, dict):
        for key in ("data", "result", "output"):
            nested = parsed.get(key)
            if isinstance(nested, dict):
                normalized_nested = _normalize_structured_payload(nested, source)
                if normalized_nested:
                    return normalized_nested

    return None


def call_gemini_structured(user_input: str, source: str) -> dict[str, Any] | None:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    model_name = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
    if not api_key:
        logger.warning("Gemini disabled: GEMINI_API_KEY missing")
        return None
    prompt = GEMINI_PROMPT_TEMPLATE.replace("{user_input}", user_input)

    # Try the configured model first; if unavailable, fall back to commonly available models.
    model_candidates = [
        model_name,
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
    ]

    seen: set[str] = set()
    for candidate_model in model_candidates:
        if not candidate_model or candidate_model in seen:
            continue
        seen.add(candidate_model)

        for use_response_mime in (True, False):
            try:
                result = _call_gemini_once(
                    api_key=api_key,
                    model_name=candidate_model,
                    source=source,
                    prompt=prompt,
                    use_response_mime=use_response_mime,
                )
                if result:
                    return result
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "unknown"
                details = ""
                if exc.response is not None:
                    details = (exc.response.text or "")[:400]
                logger.warning(
                    "Gemini HTTP error model=%s mime=%s status=%s details=%s",
                    candidate_model,
                    use_response_mime,
                    status,
                    details,
                )
            except requests.RequestException as exc:
                logger.warning(
                    "Gemini request error model=%s mime=%s error=%s",
                    candidate_model,
                    use_response_mime,
                    str(exc),
                )
            except Exception as exc:
                logger.exception(
                    "Gemini unexpected error model=%s mime=%s error=%s",
                    candidate_model,
                    use_response_mime,
                    str(exc),
                )

    logger.warning("Gemini failed for all model/config attempts")
    return None

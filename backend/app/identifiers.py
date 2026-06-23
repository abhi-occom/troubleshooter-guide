import re
from pathlib import Path


def normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def identifier_variants(value: str) -> set[str]:
    raw = value.strip()
    normalized = normalize_identifier(raw)
    return {item for item in {raw.casefold(), normalized} if item}


def profile_identifiers(filename: str, profile: dict | None) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = [("filename", Path(filename).stem)]
    if profile:
        for field in ("router_name", "model", "product_id"):
            if profile.get(field):
                values.append((field, str(profile[field])))
        for alias in profile.get("identifier_aliases", []):
            values.append(("manual_alias", str(alias)))
    seen = set()
    result = []
    for source, value in values:
        normalized = normalize_identifier(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append((source, value))
    return result


def detect_identifiers(question: str, known: list[dict]) -> list[dict]:
    normalized_question = normalize_identifier(question)
    matches = []
    for item in known:
        normalized = item["normalized_value"]
        if len(normalized) >= 3 and normalized in normalized_question:
            matches.append(item)
    matches.sort(key=lambda item: len(item["normalized_value"]), reverse=True)
    longest_by_document: dict[str, dict] = {}
    for item in matches:
        longest_by_document.setdefault(item["document_id"], item)
    return list(longest_by_document.values())

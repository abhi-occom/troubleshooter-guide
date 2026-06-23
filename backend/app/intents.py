import re
from pathlib import Path


ROUTER_INVENTORY_PATTERNS = (
    re.compile(
        r"\bhow\s+many\b.*\b(router|routers|manual|manuals|guide|guides)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(what|which)\b.*\b(router|routers)\b.*\b"
        r"(available|configured|configure|supported|uploaded|have)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(list|show|name)\b.*\b(router|routers)\b",
        re.IGNORECASE,
    ),
)

ROUTER_COMPARISON_PATTERN = re.compile(
    r"\b(compare|comparison|difference|differences)\b.*\b(router|routers)\b",
    re.IGNORECASE,
)
ROUTER_FEATURE_PATTERN = re.compile(
    r"\b(which|what)\s+router\b.*\b(supports?|has|offers?|uses?)\b\s+(?P<feature>.+)",
    re.IGNORECASE,
)

GENERIC_FILENAME_WORDS = {
    "guide",
    "manual",
    "setup",
    "installation",
    "instructions",
    "router",
}


def is_router_inventory_question(question: str) -> bool:
    normalized = " ".join(question.split())
    return any(pattern.search(normalized) for pattern in ROUTER_INVENTORY_PATTERNS)


def router_name_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    words = [word for word in re.split(r"[-_.\s]+", stem) if word]
    while len(words) > 1 and words[-1].lower() in GENERIC_FILENAME_WORDS:
        words.pop()
    display_words = [
        word.capitalize() if word.islower() else word
        for word in words
    ]
    return " ".join(display_words).strip() or stem


def build_router_inventory_answer(documents: list[dict]) -> str:
    indexed = [
        document
        for document in documents
        if document.get("status") == "indexed"
        or "document_id" in document
    ]
    names = [
        document.get("router_name")
        or router_name_from_filename(document["filename"])
        for document in indexed
    ]

    if not names:
        return (
            "There are no indexed router setup guides yet. "
            "Upload a router PDF before asking troubleshooting questions."
        )

    noun = "router setup guide is" if len(names) == 1 else "router setup guides are"
    listing = "\n".join(f"{index}. {name}" for index, name in enumerate(names, start=1))
    return (
        f"{len(names)} {noun} currently available:\n\n"
        f"{listing}\n\n"
        "Which router are you asking about?"
    )


def build_structured_router_answer(
    question: str, profiles: list[dict]
) -> str | None:
    available = [
        profile
        for profile in profiles
        if profile.get("router_name") or profile.get("filename")
    ]
    if not available:
        return None
    if ROUTER_COMPARISON_PATTERN.search(question):
        lines = []
        for profile in available:
            name = profile.get("router_name") or router_name_from_filename(
                profile["filename"]
            )
            details = [
                value
                for value in (
                    profile.get("model"),
                    profile.get("supported_configuration"),
                    ", ".join(profile.get("features") or []),
                )
                if value
            ]
            lines.append(f"- {name}: {'; '.join(details) or 'No extracted details yet'}")
        return "Here is the extracted router comparison:\n\n" + "\n".join(lines)

    feature_match = ROUTER_FEATURE_PATTERN.search(question)
    if not feature_match:
        return None
    feature = feature_match.group("feature").strip(" ?.").casefold()
    feature_tokens = [
        token for token in re.findall(r"[a-z0-9]+", feature) if len(token) > 1 or token.isdigit()
    ]
    matches = []
    for profile in available:
        searchable = " ".join(
            [
                profile.get("model") or "",
                profile.get("supported_configuration") or "",
                *profile.get("features", []),
                *profile.get("topics", []),
            ]
        ).casefold()
        searchable_tokens = set(re.findall(r"[a-z0-9]+", searchable))
        if feature in searchable or (
            feature_tokens
            and all(token in searchable_tokens for token in feature_tokens)
        ):
            matches.append(
                profile.get("router_name")
                or router_name_from_filename(profile["filename"])
            )
    if not matches:
        return None
    return (
        f"{len(matches)} router{'s' if len(matches) != 1 else ''} match "
        f"“{feature_match.group('feature').strip(' ?.')}”:\n\n"
        + "\n".join(f"- {name}" for name in matches)
        + "\n\nWhich router are you asking about?"
    )

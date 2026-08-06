"""Canonical language codes and alias normalization.

Dari (prs) and Persian/Farsi (fa) stay distinct — never silently merged.
Unknown inputs normalize to a safe lowercase slug without crashing.
"""

from __future__ import annotations

from typing import Any

# Stable product codes (ISO-ish). prs = Dari; fa = Persian/Farsi.
SUPPORTED_LANGUAGE_CODES: frozenset[str] = frozenset(
    {
        "en",
        "fa",
        "prs",
        "ps",
        "ar",
        "hi",
        "ur",
        "ko",
        "ja",
        "zh",
        "tr",
        "ru",
    }
)

# Display English labels for supported codes.
LANGUAGE_LABELS_EN: dict[str, str] = {
    "en": "English",
    "fa": "Persian",
    "prs": "Dari",
    "ps": "Pashto",
    "ar": "Arabic",
    "hi": "Hindi",
    "ur": "Urdu",
    "ko": "Korean",
    "ja": "Japanese",
    "zh": "Chinese",
    "tr": "Turkish",
    "ru": "Russian",
}

# Alias → canonical code. Keys are lowercased and stripped.
_ALIAS_TO_CODE: dict[str, str] = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "fa": "fa",
    "fas": "fa",
    "per": "fa",
    "persian": "fa",
    "farsi": "fa",
    "prs": "prs",
    "dari": "prs",
    "ps": "ps",
    "pus": "ps",
    "pashto": "ps",
    "pushto": "ps",
    "ar": "ar",
    "ara": "ar",
    "arabic": "ar",
    "hi": "hi",
    "hin": "hi",
    "hindi": "hi",
    "ur": "ur",
    "urd": "ur",
    "urdu": "ur",
    "ko": "ko",
    "kor": "ko",
    "korean": "ko",
    "ja": "ja",
    "jpn": "ja",
    "japanese": "ja",
    "zh": "zh",
    "zho": "zh",
    "chi": "zh",
    "chinese": "zh",
    "tr": "tr",
    "tur": "tr",
    "turkish": "tr",
    "ru": "ru",
    "rus": "ru",
    "russian": "ru",
}


def _clean_token(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        # TMDB spoken_languages entries: {"iso_639_1": "en", "name": "English", ...}
        for key in ("iso_639_1", "iso_639_3", "english_name", "name"):
            raw = value.get(key)
            if raw:
                return str(raw).strip()
        return None
    text = str(value).strip()
    return text or None


def normalize_language_code(value: Any) -> str | None:
    """Return a canonical language code, or a safe unknown slug, or None if empty."""
    token = _clean_token(value)
    if not token:
        return None
    key = token.lower().replace("_", "-")
    # Accept BCP-47 primary subtag (e.g. fa-IR → fa)
    primary = key.split("-", 1)[0].strip()
    if primary in _ALIAS_TO_CODE:
        return _ALIAS_TO_CODE[primary]
    if key in _ALIAS_TO_CODE:
        return _ALIAS_TO_CODE[key]
    # Unknown but non-empty: keep a bounded safe slug (no crash)
    slug = "".join(ch for ch in primary if ch.isalnum())[:16]
    return slug or None


def normalize_language_list(values: Any) -> list[str]:
    """Normalize a list of language tokens to unique canonical codes (stable order)."""
    if values is None:
        return []
    if isinstance(values, str):
        # Allow CSV accidental input
        parts = [p.strip() for p in values.split(",")]
        values = parts
    if not isinstance(values, (list, tuple, set)):
        code = normalize_language_code(values)
        return [code] if code else []
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        code = normalize_language_code(item)
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def language_label(code: str | None, *, locale: str = "en") -> str:
    """Human label for a code. Unknown codes render as the code itself."""
    if not code:
        return ""
    # Locale-specific labels can expand later; fa/ps fall back to English names for now
    # for supported codes, and raw code for unknowns.
    _ = locale
    return LANGUAGE_LABELS_EN.get(code, code)


def resolve_original_language_code(
    *,
    language: Any = None,
    spoken_languages: Any = None,
    metadata_source: str | None = None,
) -> tuple[str | None, str]:
    """Resolve original language code and its source.

    Returns (code, source) where source is tmdb_metadata | admin_metadata | unknown.
    TMDB ``spoken_languages`` may inform original language only — never dubs/subs.
    """
    from_lang = normalize_language_code(language)
    spoken_codes = normalize_language_list(spoken_languages)
    source_hint = (metadata_source or "").strip().lower()

    if from_lang:
        if source_hint == "tmdb" or (spoken_codes and from_lang in spoken_codes):
            return from_lang, "tmdb_metadata" if source_hint == "tmdb" else (
                "tmdb_metadata" if spoken_codes else "admin_metadata"
            )
        return from_lang, "admin_metadata"
    if spoken_codes:
        # Prefer first spoken language from TMDB when language string is empty
        return spoken_codes[0], "tmdb_metadata"
    return None, "unknown"

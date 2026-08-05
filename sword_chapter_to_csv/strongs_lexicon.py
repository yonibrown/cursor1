"""Look up Greek and Hebrew dictionary forms from Open Scriptures Strong's files."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

STRONGS_ROOT = Path(__file__).resolve().parent / "strongs"
GREEK_DICT_PATH = STRONGS_ROOT / "strongs-greek-dictionary.js"
HEBREW_DICT_PATH = STRONGS_ROOT / "strongs-hebrew-dictionary.js"

GREEK_DICT_URL = (
    "https://raw.githubusercontent.com/openscriptures/strongs/master/greek/"
    "strongs-greek-dictionary.js"
)
HEBREW_DICT_URL = (
    "https://raw.githubusercontent.com/openscriptures/strongs/master/hebrew/"
    "strongs-hebrew-dictionary.js"
)


def normalize_strongs_id(strongs: str, *, default_prefix: str) -> str:
    """Return a normalized Strong's id such as G2980 or H1696."""
    value = strongs.strip()
    if not value:
        return ""

    if value[0] in {"G", "H"}:
        number = re.sub(r"\D", "", value)
        return f"{value[0]}{int(number):04d}" if number else value

    number = re.sub(r"\D", "", value)
    if not number:
        return value
    return f"{default_prefix}{int(number):04d}"


def _load_js_dictionary(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}

    text = path.read_text(encoding="utf-8")
    # Open Scriptures files end with "}; module.exports = ..." (CommonJS).
    text = re.sub(r"\s*;\s*module\.exports\s*=.*$", "", text, flags=re.DOTALL)
    match = re.search(r"=\s*(\{.*\})\s*;?\s*$", text, flags=re.DOTALL)
    if not match:
        return {}

    data = json.loads(match.group(1))
    return {str(key): value for key, value in data.items()}


@lru_cache(maxsize=1)
def greek_dictionary() -> dict[str, dict[str, str]]:
    return _load_js_dictionary(GREEK_DICT_PATH)


@lru_cache(maxsize=1)
def hebrew_dictionary() -> dict[str, dict[str, str]]:
    return _load_js_dictionary(HEBREW_DICT_PATH)


def lookup_greek_root(strongs: str) -> str:
    """Return the Greek lexical form (Strong's lemma) for a Strong's number."""
    strongs_id = normalize_strongs_id(strongs, default_prefix="G")
    if not strongs_id:
        return ""
    entry = greek_dictionary().get(strongs_id)
    return entry.get("lemma", "") if entry else ""


def lookup_hebrew_root(strongs: str) -> str:
    """Return the Hebrew lexical form (Strong's lemma) for a Strong's number."""
    strongs_id = normalize_strongs_id(strongs, default_prefix="H")
    if not strongs_id:
        return ""
    entry = hebrew_dictionary().get(strongs_id)
    return entry.get("lemma", "") if entry else ""


def strongs_lexicon_available() -> bool:
    return GREEK_DICT_PATH.is_file() and HEBREW_DICT_PATH.is_file()

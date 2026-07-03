"""Parse Open Scriptures Hebrew Bible (OSHB / morphhb) morphology codes."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

HEBREW_POS = {
    "A": "Adjective",
    "C": "Conjunction",
    "D": "Adverb",
    "N": "Noun",
    "P": "Pronoun",
    "R": "Preposition",
    "S": "Suffix",
    "T": "Particle",
    "V": "Verb",
}

HEBREW_NUMBERS = {"s": "Singular", "d": "Dual", "p": "Plural"}
HEBREW_GENDERS = {
    "m": "Masculine",
    "f": "Feminine",
    "c": "Common",
    "b": "Both",
}
HEBREW_STATES = {
    "a": "Absolute",
    "c": "Construct",
    "d": "Determined",
}

HEBREW_VERB_STEMS = {
    "q": "Qal",
    "N": "Niphal",
    "p": "Piel",
    "P": "Pual",
    "h": "Hiphil",
    "H": "Hophal",
    "t": "Hithpael",
    "o": "Polel",
    "O": "Polal",
    "r": "Hithpolel",
    "m": "Poel",
    "M": "Poal",
    "k": "Palel",
    "K": "Pulal",
    "Q": "Qal passive",
    "l": "Pilpel",
    "L": "Polpal",
    "f": "Hithpalpel",
    "D": "Nithpael",
    "j": "Pealal",
    "i": "Pilel",
    "u": "Hothpaal",
    "c": "Tiphil",
    "v": "Hishtaphel",
    "w": "Nithpalel",
    "y": "Nithpoel",
    "z": "Hithpoel",
}

HEBREW_VERB_CONJUGATIONS = {
    "p": "Perfect",
    "q": "Sequential perfect",
    "i": "Imperfect",
    "w": "Sequential imperfect",
    "h": "Cohortative",
    "j": "Jussive",
    "v": "Imperative",
    "r": "Participle active",
    "s": "Participle passive",
    "a": "Infinitive absolute",
    "c": "Infinitive construct",
}

HEBREW_VERB_MOODS = {
    "v": "Imperative",
    "h": "Cohortative",
    "j": "Jussive",
    "r": "Participle",
    "s": "Participle",
    "a": "Infinitive",
    "c": "Infinitive",
}

NOUN_TYPES = {
    "c": "Common",
    "g": "Gentilic",
    "p": "Proper name",
}

PARTICLE_TYPES = {
    "a": "Affirmation",
    "d": "Definite article",
    "e": "Exhortation",
    "i": "Interrogative",
    "j": "Interjection",
    "m": "Demonstrative",
    "n": "Negative",
    "o": "Direct object marker",
    "r": "Relative",
}

PRONOUN_TYPES = {
    "d": "Demonstrative",
    "f": "Indefinite",
    "i": "Interrogative",
    "p": "Personal",
    "r": "Relative",
}

SUFFIX_TYPES = {
    "d": "Directional he",
    "h": "Paragogic he",
    "n": "Paragogic nun",
    "p": "Pronominal",
}

MORPHOLOGY_FIELD_MAP = {
    "part_of_speech": "Part of Speech",
    "tense": "Tense",
    "voice": "Voice",
    "mood": "Mood",
    "person": "Person",
    "number": "Number",
    "case": "Case",
    "gender": "Gender",
}

OSIS_NS = "http://www.bibletechnologies.net/2003/OSIS/namespace"


def local_tag(tag: str) -> str:
    """Return the XML local name, stripping any namespace prefix."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def iter_by_local_tag(root: ET.Element, name: str):
    """Yield elements whose local tag name matches *name*."""
    for element in root.iter():
        if local_tag(element.tag) == name:
            yield element


def empty_morphology_fields() -> dict[str, str]:
    return {key: "" for key in MORPHOLOGY_FIELD_MAP}


def morphology_csv_fields(parsed: dict[str, str]) -> dict[str, str]:
    return {
        csv_field: parsed.get(key, "")
        for key, csv_field in MORPHOLOGY_FIELD_MAP.items()
    }


def normalize_hebrew_word(text: str) -> str:
    """Join morphhb prefix markers into one surface word."""
    return text.replace("/", "")


def format_hebrew_lemma(lemma: str) -> tuple[str, str]:
    """Return display lemma and a Strong's-style id when possible."""
    if not lemma:
        return "", ""

    parts = [part.strip() for part in lemma.split("/") if part.strip()]
    strongs_parts: list[str] = []
    for part in parts:
        number = re.match(r"^(\d+)", part)
        if number:
            strongs_parts.append(f"H{number.group(1)}")

    strongs = strongs_parts[-1] if strongs_parts else ""
    return lemma, strongs


def _strip_language_prefix(code: str) -> str:
    if code and code[0] in {"H", "A"}:
        return code[1:]
    return code


def _parse_hebrew_segment(code: str) -> dict[str, str]:
    parsed = empty_morphology_fields()
    code = _strip_language_prefix(code.strip())
    if not code:
        return parsed

    pos = code[0]
    parsed["part_of_speech"] = HEBREW_POS.get(pos, pos)
    rest = code[1:]

    if pos == "V":
        if len(rest) >= 2:
            parsed["voice"] = HEBREW_VERB_STEMS.get(rest[0], rest[0])
            parsed["tense"] = HEBREW_VERB_CONJUGATIONS.get(rest[1], rest[1])
            parsed["mood"] = HEBREW_VERB_MOODS.get(rest[1], "Indicative")
        if len(rest) >= 3 and rest[1] in {"r", "s"}:
            parsed["gender"] = HEBREW_GENDERS.get(rest[2], rest[2])
            if len(rest) >= 4:
                parsed["number"] = HEBREW_NUMBERS.get(rest[3], rest[3])
            if len(rest) >= 5:
                parsed["case"] = HEBREW_STATES.get(rest[4], rest[4])
        elif len(rest) >= 5:
            parsed["person"] = rest[2]
            parsed["gender"] = HEBREW_GENDERS.get(rest[3], rest[3])
            parsed["number"] = HEBREW_NUMBERS.get(rest[4], rest[4])
        return parsed

    if pos == "N":
        if rest:
            parsed["part_of_speech"] = (
                f"Noun ({NOUN_TYPES.get(rest[0], rest[0])})"
                if rest[0] in NOUN_TYPES
                else "Noun"
            )
            offset = 1 if rest and rest[0] in NOUN_TYPES else 0
            if len(rest) >= offset + 1:
                parsed["gender"] = HEBREW_GENDERS.get(rest[offset], rest[offset])
            if len(rest) >= offset + 2:
                parsed["number"] = HEBREW_NUMBERS.get(rest[offset + 1], rest[offset + 1])
            if len(rest) >= offset + 3:
                parsed["case"] = HEBREW_STATES.get(rest[offset + 2], rest[offset + 2])
        return parsed

    if pos == "A" and len(rest) >= 4:
        parsed["gender"] = HEBREW_GENDERS.get(rest[1], rest[1])
        parsed["number"] = HEBREW_NUMBERS.get(rest[2], rest[2])
        parsed["case"] = HEBREW_STATES.get(rest[3], rest[3])
        return parsed

    if pos == "P" and len(rest) >= 4:
        subtype = PRONOUN_TYPES.get(rest[0], rest[0])
        parsed["part_of_speech"] = f"Pronoun ({subtype})"
        parsed["person"] = rest[1]
        parsed["gender"] = HEBREW_GENDERS.get(rest[2], rest[2])
        parsed["number"] = HEBREW_NUMBERS.get(rest[3], rest[3])
        return parsed

    if pos == "S" and len(rest) >= 4:
        subtype = SUFFIX_TYPES.get(rest[0], rest[0])
        parsed["part_of_speech"] = f"Suffix ({subtype})"
        parsed["person"] = rest[1]
        parsed["gender"] = HEBREW_GENDERS.get(rest[2], rest[2])
        parsed["number"] = HEBREW_NUMBERS.get(rest[3], rest[3])
        return parsed

    if pos == "T" and rest:
        subtype = PARTICLE_TYPES.get(rest[0], rest[0])
        parsed["part_of_speech"] = f"Particle ({subtype})"
        return parsed

    if pos == "R" and rest:
        if rest[0] == "d":
            parsed["part_of_speech"] = "Preposition (definite article)"
        return parsed

    return parsed


def parse_hebrew_morphology(code: str) -> dict[str, str]:
    """Parse an OSHB morphology code such as HC/Vpw3ms or HNcmpa."""
    if not code:
        return empty_morphology_fields()

    normalized = code.strip()
    for prefix in ("oshm:", "packard:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]

    segments = normalized.split("/")
    parsed = empty_morphology_fields()
    for segment in segments:
        segment_parsed = _parse_hebrew_segment(segment)
        for key, value in segment_parsed.items():
            if value:
                parsed[key] = value
    return parsed


def word_row_from_morphhb(element: ET.Element, verse_num: int) -> dict[str, str]:
    word = normalize_hebrew_word("".join(element.itertext()).strip())
    lemma_raw = element.get("lemma", "")
    morph_raw = element.get("morph", "")
    lemma, strongs = format_hebrew_lemma(lemma_raw)
    morphology_code = morph_raw
    for prefix in ("oshm:", "packard:"):
        if morphology_code.startswith(prefix):
            morphology_code = morphology_code[len(prefix) :]

    row = {
        "word": word,
        "verse": str(verse_num),
        "lemma": lemma,
        "strongs": strongs,
        "morph": morph_raw,
        "morphology": morphology_code,
        "xlit": "",
        "betacode": "",
    }
    row.update(morphology_csv_fields(parse_hebrew_morphology(morphology_code)))
    return row


def parse_morphhb_verse(xml_fragment: str, verse_num: int) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(f"<root>{xml_fragment}</root>")
    except ET.ParseError:
        return []

    rows: list[dict[str, str]] = []
    for element in iter_by_local_tag(root, "w"):
        word = normalize_hebrew_word("".join(element.itertext()).strip())
        if word:
            rows.append(word_row_from_morphhb(element, verse_num))
    return rows


def morphhb_book_path(morphhb_dir: Path, osis_book: str) -> Path:
    return morphhb_dir / f"{osis_book}.xml"


def extract_morphhb_chapter_rows(
    morphhb_dir: Path,
    osis_book: str,
    chapter: int,
    verse_count: int,
) -> list[dict[str, str]]:
    book_path = morphhb_book_path(morphhb_dir, osis_book)
    if not book_path.is_file():
        raise FileNotFoundError(
            f"Hebrew morphology file not found: {book_path}. "
            "Download the morphhb wlc XML files into SWORD/WLC/morphhb/wlc/."
        )

    rows: list[dict[str, str]] = []
    for verse_num in range(1, verse_count + 1):
        target_id = f"{osis_book}.{chapter}.{verse_num}"
        verse_xml = _read_morphhb_verse_xml(book_path, target_id)
        if verse_xml is None:
            continue
        rows.extend(parse_morphhb_verse(verse_xml, verse_num))
    return rows


def _read_morphhb_verse_xml(book_path: Path, osis_id: str) -> str | None:
    context = ET.iterparse(book_path, events=("end",))
    for _, element in context:
        if local_tag(element.tag) != "verse":
            continue
        if element.get("osisID") != osis_id:
            element.clear()
            continue

        xml_parts = [ET.tostring(child, encoding="unicode") for child in element]
        element.clear()
        return "".join(xml_parts)
    return None

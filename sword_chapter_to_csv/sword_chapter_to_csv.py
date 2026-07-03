#!/usr/bin/env python3
"""Export a morphologically tagged SWORD chapter to CSV.

Prompts for a text source (LXX or WLC), book, and chapter, then writes one row
per word. The first column is the surface form; the remaining columns contain
morphological metadata from the module's OSIS markup when available.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from hebrew_morphology import (
    empty_morphology_fields as empty_hebrew_fields,
    extract_morphhb_chapter_rows,
    morphhb_book_path,
    parse_morphhb_verse,
)
from bible_to_csv import verse_order
from pysword.modules import SwordModules

SWORD_ROOT = Path(__file__).resolve().parent / "SWORD"
TEXT_SOURCES = {
    "LXX": {"folder": "LXX", "module": "LXX", "parser": "greek"},
    "WLC": {
        "folder": "WLC",
        "module": "WLC",
        "parser": "hebrew",
        "morphhb_dir": "morphhb/wlc",
    },
}
DEFAULT_TEXT = "LXX"

CSV_COLUMNS = (
    "key",
    "word",
    "verse",
    "word_num",
    "lemma",
    "strongs",
    "morph",
    "morphology",
    "Part of Speech",
    "Tense",
    "Voice",
    "Mood",
    "Person",
    "Number",
    "Case",
    "Gender",
    "xlit",
    "betacode",
)

SYNOPTIC_METADATA_COLUMNS = tuple(
    column for column in CSV_COLUMNS if column not in ("key", "word", "verse")
)

PRONOUN_TYPES = {
    "A": "Article",
    "D": "Demonstrative Pronoun",
    "I": "Interrogative/Indefinite Pronoun",
    "P": "Personal/Possessive Pronoun",
    "R": "Relative Pronoun",
    "X": "ὅστις",
}

NUMBERS = {"S": "Singular", "D": "Dual", "P": "Plural"}
TENSES = {
    "P": "Present",
    "I": "Imperfect",
    "F": "Future",
    "A": "Aorist",
    "X": "Perfect",
    "Y": "Pluperfect",
}
VOICES = {"A": "Active", "M": "Middle", "P": "Passive"}
MOODS = {
    "I": "Indicative",
    "D": "Imperative",
    "S": "Subjunctive",
    "O": "Optative",
    "N": "Infinitive",
    "P": "Participle",
}
CASES = {
    "N": "Nominative",
    "G": "Genitive",
    "D": "Dative",
    "A": "Accusative",
    "V": "Vocative",
}
GENDERS = {"M": "Masculine", "F": "Feminine", "N": "Neuter"}
DEGREES = {"C": "Comparative", "S": "Superlative"}

UNMORPHED_PARTS_OF_SPEECH = {
    "C": "Conjunction",
    "X": "Particle",
    "I": "Interjection",
    "M": "Numeral",
    "P": "Preposition",
    "D": "Adverb",
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


def _lookup(mapping: dict[str, str], key: str) -> str:
    return mapping.get(key, "")


def _case_number_gender(code: str) -> dict[str, str]:
    return {
        "case": _lookup(CASES, code[0] if len(code) > 0 else ""),
        "number": _lookup(NUMBERS, code[1] if len(code) > 1 else ""),
        "gender": _lookup(GENDERS, code[2] if len(code) > 2 else ""),
    }


def _tense_voice_mood(code: str) -> dict[str, str]:
    return {
        "tense": _lookup(TENSES, code[0] if len(code) > 0 else ""),
        "voice": _lookup(VOICES, code[1] if len(code) > 1 else ""),
        "mood": _lookup(MOODS, code[2] if len(code) > 2 else ""),
    }


def _person_number(code: str) -> dict[str, str]:
    person = code[3] if len(code) > 3 else ""
    return {
        "person": person,
        "number": _lookup(NUMBERS, code[4] if len(code) > 4 else ""),
    }


def _split_packard_code(code: str) -> tuple[str, str]:
    if not code:
        return "", ""
    if "-" in code:
        pos, parse = code.split("-", 1)
        return pos, parse
    return code, ""


def parse_packard_morphology(code: str) -> dict[str, str]:
    """Parse a CCAT/Packard morphology code into grammatical features."""
    part_of_speech, parse_code = _split_packard_code(code.strip())
    if not part_of_speech:
        return {field: "" for field in MORPHOLOGY_FIELD_MAP}

    parsed: dict[str, str] = {
        "part_of_speech": "",
        "tense": "",
        "voice": "",
        "mood": "",
        "person": "",
        "number": "",
        "case": "",
        "gender": "",
    }

    pos_type = part_of_speech[0]
    if pos_type == "N":
        parsed["part_of_speech"] = "Noun"
        parsed.update(_case_number_gender(parse_code))
    elif pos_type == "R":
        subtype = part_of_speech[1] if len(part_of_speech) > 1 else ""
        parsed["part_of_speech"] = PRONOUN_TYPES.get(subtype, "Pronoun")
        parsed.update(_case_number_gender(parse_code))
    elif pos_type == "A":
        parsed["part_of_speech"] = "Adjective"
        parsed.update(_case_number_gender(parse_code))
        if len(parse_code) > 3:
            parsed["degree"] = _lookup(DEGREES, parse_code[3])
    elif pos_type == "V":
        parsed["part_of_speech"] = "Verb"
        parsed.update(_tense_voice_mood(parse_code))
        if parsed["mood"] == "Participle":
            parsed.update(_case_number_gender(parse_code[3:]))
        else:
            parsed.update(_person_number(parse_code))
    elif pos_type in UNMORPHED_PARTS_OF_SPEECH:
        parsed["part_of_speech"] = UNMORPHED_PARTS_OF_SPEECH[pos_type]

    return parsed


def morphology_csv_fields(code: str) -> dict[str, str]:
    """Return CSV-ready morphology columns for one Packard code."""
    parsed = parse_packard_morphology(code)
    return {
        csv_field: parsed.get(key, "")
        for key, csv_field in MORPHOLOGY_FIELD_MAP.items()
    }


def empty_morphology_fields() -> dict[str, str]:
    return {field: "" for field in MORPHOLOGY_FIELD_MAP.values()}


def discover_text_sources() -> dict[str, dict[str, Path | str]]:
    """Return installed text sources keyed by name (e.g. LXX, WLC)."""
    sources: dict[str, dict[str, Path | str]] = {}
    for name, config in TEXT_SOURCES.items():
        sword_dir = SWORD_ROOT / str(config["folder"])
        if sword_dir.is_dir():
            sources[name] = {
                "path": sword_dir,
                "module": str(config["module"]),
                "parser": str(config.get("parser", "greek")),
                "morphhb_dir": sword_dir / str(config.get("morphhb_dir", "")),
            }
    return sources


def resolve_text_source(
    text_name: str, sources: dict[str, dict[str, Path | str]]
) -> tuple[Path, str]:
    key = text_name.strip().upper()
    if key not in sources:
        known = ", ".join(sorted(sources)) or "(none)"
        raise KeyError(f"Unknown text '{text_name}'. Available texts: {known}")
    config = sources[key]
    return Path(config["path"]), str(config["module"])


def prompt_text_source(sources: dict[str, dict[str, Path | str]]) -> str:
    options = sorted(sources)
    print("Available texts:", ", ".join(options))

    while True:
        choice = input(f"Text source [{DEFAULT_TEXT}]: ").strip().upper() or DEFAULT_TEXT
        if choice in sources:
            return choice
        print(f"Unknown text: {choice}")


def plain_text_word_rows(text: str, verse_num: int, parser: str) -> list[dict[str, str]]:
    """Fallback when a module returns plain text without OSIS word tags."""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    morph_fields = empty_hebrew_fields() if parser == "hebrew" else empty_morphology_fields()
    rows: list[dict[str, str]] = []
    for word in cleaned.split():
        row = {
            "word": word,
            "verse": str(verse_num),
            "lemma": "",
            "strongs": "",
            "morph": "",
            "morphology": "",
            "xlit": "",
            "betacode": "",
        }
        row.update(morph_fields)
        rows.append(row)
    return rows


def parse_greek_osis_words(osis_text: str, verse_num: int) -> list[dict[str, str]]:
    """Extract Greek word rows from one verse of OSIS markup."""
    if not osis_text.strip():
        return []

    try:
        root = ET.fromstring(f"<root>{osis_text}</root>")
    except ET.ParseError:
        return plain_text_word_rows(osis_text, verse_num, "greek")

    rows: list[dict[str, str]] = []
    for element in root.iter("w"):
        word = "".join(element.itertext()).strip()
        if not word:
            continue

        lemma = element.get("lemma", "")
        morph = element.get("morph", "")
        xlit = element.get("xlit", "")

        morphology_code = strip_prefix(morph, "packard:")
        row = {
            "word": word,
            "verse": str(verse_num),
            "lemma": lemma,
            "strongs": strip_prefix(lemma, "strong:"),
            "morph": morph,
            "morphology": morphology_code,
            "xlit": xlit,
            "betacode": strip_prefix(xlit, "betacode:"),
        }
        row.update(morphology_csv_fields(morphology_code))
        rows.append(row)

    if not rows:
        return plain_text_word_rows(osis_text, verse_num, "greek")

    return rows


def parse_hebrew_osis_words(osis_text: str, verse_num: int) -> list[dict[str, str]]:
    """Extract Hebrew word rows from OSIS markup returned by SWORD."""
    if not osis_text.strip():
        return []

    if "<w" in osis_text:
        return parse_morphhb_verse(osis_text, verse_num)

    return plain_text_word_rows(osis_text, verse_num, "hebrew")


def resolve_book_name(book_input: str, bible) -> str:
    """Return the OSIS book id for user input such as 'Exodus' or 'Exod'."""
    structure = bible.get_structure()
    testament, book = structure.find_book(book_input.strip())
    return book.osis_name


def chapter_verse_count(bible, osis_book: str, chapter: int) -> int:
    _, book = bible.get_structure().find_book(osis_book)
    if chapter < 1 or chapter > len(book.chapter_lengths):
        raise ValueError(
            f"{osis_book} has {len(book.chapter_lengths)} chapters, not {chapter}."
        )
    return book.chapter_lengths[chapter - 1]


def strip_prefix(value: str, prefix: str) -> str:
    if value.startswith(prefix):
        return value[len(prefix) :]
    return value


def extract_greek_chapter_rows(bible, osis_book: str, chapter: int) -> list[dict[str, str]]:
    verse_count = chapter_verse_count(bible, osis_book, chapter)
    rows: list[dict[str, str]] = []

    for verse_num in range(1, verse_count + 1):
        osis_text = next(
            bible.get_iter(
                books=[osis_book],
                chapters=[chapter],
                verses=[verse_num],
                clean=False,
            )
        )
        rows.extend(parse_greek_osis_words(osis_text, verse_num))

    return rows


def extract_hebrew_chapter_rows(
    bible,
    sword_dir: Path,
    osis_book: str,
    chapter: int,
) -> list[dict[str, str]]:
    verse_count = chapter_verse_count(bible, osis_book, chapter)
    morphhb_dir = Path(sword_dir / TEXT_SOURCES["WLC"]["morphhb_dir"])

    if morphhb_book_path(morphhb_dir, osis_book).is_file():
        rows = extract_morphhb_chapter_rows(morphhb_dir, osis_book, chapter, verse_count)
        if rows:
            return rows
        print(
            "Warning: morphhb XML found but no verses matched; "
            "falling back to SWORD plain text.",
            file=sys.stderr,
        )

    rows: list[dict[str, str]] = []
    for verse_num in range(1, verse_count + 1):
        osis_text = next(
            bible.get_iter(
                books=[osis_book],
                chapters=[chapter],
                verses=[verse_num],
                clean=False,
            )
        )
        rows.extend(parse_hebrew_osis_words(osis_text, verse_num))

    if rows and not rows[0].get("morphology"):
        print(
            "Warning: WLC SWORD module has no morphology tags. "
            "Add morphhb XML files to SWORD/WLC/morphhb/wlc/ for full parsing.",
            file=sys.stderr,
        )
    return rows


def extract_chapter_rows(
    text_name: str,
    bible,
    sword_dir: Path,
    osis_book: str,
    chapter: int,
) -> list[dict[str, str]]:
    parser = TEXT_SOURCES[text_name.upper()]["parser"]
    if parser == "hebrew":
        return extract_hebrew_chapter_rows(bible, sword_dir, osis_book, chapter)
    return extract_greek_chapter_rows(bible, osis_book, chapter)


def load_bible(sword_dir: Path, module_name: str):
    if not sword_dir.is_dir():
        raise FileNotFoundError(f"SWORD directory not found: {sword_dir}")

    modules = SwordModules(str(sword_dir.resolve()))
    available = modules.parse_modules()
    if module_name not in available:
        known = ", ".join(sorted(available)) or "(none)"
        raise KeyError(f"Module '{module_name}' not found. Available modules: {known}")

    return modules.get_bible_from_module(module_name)


def prompt_book_and_chapter(bible) -> tuple[str, int]:
    structure = bible.get_structure()
    ot_books = [book.osis_name for book in structure.get_books()["ot"]]
    nt_books = [book.osis_name for book in structure.get_books()["nt"]]

    print("Available books (OSIS ids):")
    print(", ".join(ot_books + nt_books))

    while True:
        book_input = input("\nBook (e.g. Exod or Exodus): ").strip()
        if not book_input:
            print("Please enter a book name.")
            continue
        try:
            osis_book = resolve_book_name(book_input, bible)
            break
        except ValueError:
            print(f"Unknown book: {book_input}")

    while True:
        chapter_input = input(f"Chapter number for {osis_book}: ").strip()
        if not chapter_input.isdigit():
            print("Please enter a numeric chapter.")
            continue

        chapter = int(chapter_input)
        try:
            chapter_verse_count(bible, osis_book, chapter)
            return osis_book, chapter
        except ValueError as exc:
            print(exc)


MINIMAL_COLUMNS = ("key", "word")


def output_columns(*, include_grammatical_data: bool = True) -> tuple[str, ...]:
    return CSV_COLUMNS if include_grammatical_data else MINIMAL_COLUMNS


def write_csv(
    rows: list[dict[str, str]],
    output_path: Path,
    *,
    columns: tuple[str, ...] | None = None,
) -> Path:
    output_path = output_path.resolve()
    temp_path = output_path.with_name(output_path.name + ".tmp")
    fieldnames = columns or CSV_COLUMNS

    with temp_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)

    return _finalize_csv_write(output_path, temp_path)


def write_synoptic_csv(
    rows: list[dict[str, str]],
    output_path: Path,
    *,
    columns: tuple[str, ...],
) -> Path:
    output_path = output_path.resolve()
    temp_path = output_path.with_name(output_path.name + ".tmp")

    with temp_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)

    return _finalize_csv_write(output_path, temp_path)


def _finalize_csv_write(output_path: Path, temp_path: Path) -> Path:
    try:
        temp_path.replace(output_path)
        return output_path
    except PermissionError:
        print(
            f"Error: cannot write to {output_path.name} — "
            "close it in Excel (or another program) and run again.",
            file=sys.stderr,
        )
        print(f"Output saved instead as {temp_path.name}", file=sys.stderr)
        return temp_path


def synoptic_prefixed_column(text_name: str, column: str) -> str:
    return f"{text_name}_{column}"


def synoptic_column_headers(
    text_names: list[str],
    *,
    include_grammatical_data: bool = True,
) -> tuple[str, ...]:
    headers: list[str] = []
    for text_name in text_names:
        headers.append(synoptic_prefixed_column(text_name, "key"))
        headers.append(text_name)
        if include_grammatical_data:
            headers.extend(
                synoptic_prefixed_column(text_name, column)
                for column in SYNOPTIC_METADATA_COLUMNS
            )
    return tuple(headers)


def make_word_key(
    text_name: str,
    book: str,
    chapter: int,
    verse: str,
    word_num: str | int,
) -> str:
    """Build a word id: ttt-bbb-ccc-vvv-www (e.g. LXX-Exod-025-001-003)."""
    return (
        f"{text_name}-{book}-{int(chapter):03d}-"
        f"{int(verse):03d}-{int(word_num):03d}"
    )


def assign_word_keys_and_numbers(
    rows: list[dict[str, str]],
    text_name: str,
    book: str,
    chapter: int,
) -> list[dict[str, str]]:
    """Assign word_num and key to each word row within its verse."""
    numbered: list[dict[str, str]] = []
    for _, verse_rows in rows_to_verse_row_lists(rows):
        for index, row in enumerate(verse_rows, start=1):
            numbered_row = dict(row)
            numbered_row["word_num"] = str(index)
            numbered_row["key"] = make_word_key(text_name, book, chapter, row["verse"], index)
            numbered.append(numbered_row)
    return numbered


def rows_to_verse_row_lists(
    rows: list[dict[str, str]],
) -> list[tuple[str, list[dict[str, str]]]]:
    """Group flat word rows into ordered (verse number, row dicts) pairs."""
    verses: list[tuple[str, list[dict[str, str]]]] = []
    current_verse: str | None = None
    current_rows: list[dict[str, str]] = []

    for row in rows:
        verse = row["verse"]
        if verse != current_verse:
            if current_verse is not None:
                verses.append((current_verse, current_rows))
            current_verse = verse
            current_rows = [row]
        else:
            current_rows.append(row)

    if current_verse is not None:
        verses.append((current_verse, current_rows))
    return verses


def verse_header_row(verse_num: str) -> dict[str, str]:
    """Build a CSV row that marks the start of a verse block."""
    row = {column: "" for column in CSV_COLUMNS}
    row["key"] = verse_num
    row["word"] = verse_num
    row["verse"] = verse_num
    return row


def add_verse_header_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Insert a verse-number row before each verse's words."""
    expanded: list[dict[str, str]] = []
    for verse_num, verse_rows in rows_to_verse_row_lists(rows):
        expanded.append(verse_header_row(verse_num))
        expanded.extend(verse_rows)
    return expanded


def _empty_synoptic_fields(text_names: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for text_name in text_names:
        fields[synoptic_prefixed_column(text_name, "key")] = ""
        fields[text_name] = ""
        for column in SYNOPTIC_METADATA_COLUMNS:
            fields[synoptic_prefixed_column(text_name, column)] = ""
    return fields


def build_synoptic_rows(
    text_row_sets: list[list[dict[str, str]]],
    text_names: list[str],
    *,
    include_grammatical_data: bool = True,
) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    """Align multiple texts by verse with full morphology columns per text."""
    verse_row_lists = [rows_to_verse_row_lists(rows) for rows in text_row_sets]
    word_only_lists = [
        [(verse, [row["word"] for row in verse_rows]) for verse, verse_rows in verse_list]
        for verse_list in verse_row_lists
    ]
    ordered_verse_nums = verse_order(word_only_lists)
    columns = synoptic_column_headers(
        text_names,
        include_grammatical_data=include_grammatical_data,
    )
    output_rows: list[dict[str, str]] = []

    for verse_num in ordered_verse_nums:
        rows_by_text: list[list[dict[str, str]]] = []
        for verse_rows in verse_row_lists:
            verse_map = {verse: rows for verse, rows in verse_rows}
            rows_by_text.append(verse_map.get(verse_num, []))

        verse_row = _empty_synoptic_fields(text_names)
        for text_name, text_rows in zip(text_names, rows_by_text, strict=True):
            if text_rows:
                verse_row[synoptic_prefixed_column(text_name, "key")] = verse_num
                verse_row[text_name] = verse_num
        output_rows.append(verse_row)

        max_words = max((len(text_rows) for text_rows in rows_by_text), default=0)
        for word_idx in range(max_words):
            aligned = _empty_synoptic_fields(text_names)
            for text_name, text_rows in zip(text_names, rows_by_text, strict=True):
                if word_idx >= max_words - len(text_rows):
                    source_row = text_rows[word_idx - (max_words - len(text_rows))]
                    aligned[synoptic_prefixed_column(text_name, "key")] = source_row.get("key", "")
                    aligned[text_name] = source_row["word"]
                    for column in SYNOPTIC_METADATA_COLUMNS:
                        aligned[synoptic_prefixed_column(text_name, column)] = source_row.get(
                            column, ""
                        )
            output_rows.append(aligned)

    return output_rows, columns


def count_synoptic_words(
    rows: list[dict[str, str]],
    text_names: list[str],
) -> dict[str, int]:
    """Return per-text word counts from aligned synoptic rows."""
    counts = {name: 0 for name in text_names}
    for row in rows:
        for name in text_names:
            cell = row.get(name, "")
            if cell and not cell.isdigit():
                counts[name] += 1
    return counts


def build_arg_parser(
    sources: dict[str, dict[str, Path | str]],
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a SWORD chapter with morphology to CSV."
    )
    parser.add_argument(
        "--text",
        choices=sorted(sources),
        help=f"Text source to use (default: {DEFAULT_TEXT}, or prompt)",
    )
    parser.add_argument(
        "--sword-dir",
        type=Path,
        help="Override SWORD library root (default: SWORD/<text>)",
    )
    parser.add_argument(
        "--module",
        help="Override SWORD module name (default: matches --text)",
    )
    parser.add_argument("--book", help="Book name or OSIS id (skip prompt)")
    parser.add_argument("--chapter", type=int, help="Chapter number (skip prompt)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output CSV path (default: <book>_<chapter>.csv)",
    )
    parser.add_argument(
        "--synoptic",
        action="store_true",
        help="Export WLC and LXX side by side, verse-aligned (ignores --text)",
    )
    return parser


def export_chapter(
    text_name: str,
    book: str,
    chapter: int,
    output_path: Path | None = None,
    *,
    sword_dir: Path | None = None,
    module_name: str | None = None,
    include_grammatical_data: bool = True,
) -> tuple[Path, int, str]:
    """Export one chapter to CSV.

    Returns (written_path, word_count, osis_book). Raises on invalid input or
    missing data.
    """
    sources = discover_text_sources()
    if not sources:
        raise FileNotFoundError(f"No text sources found under {SWORD_ROOT}")

    resolved_dir, resolved_module = resolve_text_source(text_name, sources)
    text_name = text_name.strip().upper()
    sword_dir = sword_dir or resolved_dir
    module_name = module_name or resolved_module

    bible = load_bible(sword_dir, module_name)
    osis_book = resolve_book_name(book, bible)
    chapter_verse_count(bible, osis_book, chapter)

    rows = extract_chapter_rows(text_name, bible, sword_dir, osis_book, chapter)
    if not rows:
        raise ValueError("No words found for that reference.")

    word_count = len(rows)
    rows = assign_word_keys_and_numbers(rows, text_name, osis_book, chapter)
    rows = add_verse_header_rows(rows)

    target = output_path or Path(f"{text_name}_{osis_book}_{chapter}.csv")
    written_path = write_csv(
        rows,
        target,
        columns=output_columns(include_grammatical_data=include_grammatical_data),
    )
    return written_path, word_count, osis_book


def export_synoptic_chapter(
    book: str,
    chapter: int,
    text_names: list[str] | None = None,
    output_path: Path | None = None,
    *,
    include_grammatical_data: bool = True,
) -> tuple[Path, dict[str, int], str]:
    """Export one chapter with multiple texts aligned in separate columns.

    Returns (written_path, {text_name: word_count}, osis_book).
    """
    sources = discover_text_sources()
    normalized = sorted(name.strip().upper() for name in (text_names or ["WLC", "LXX"]))
    if len(normalized) < 2:
        raise ValueError("Synoptic export requires at least two text sources.")

    missing = [name for name in normalized if name not in sources]
    if missing:
        raise FileNotFoundError(
            f"Text sources not found: {', '.join(missing)}. "
            f"Available: {', '.join(sorted(sources))}"
        )

    all_row_sets: list[list[dict[str, str]]] = []
    osis_book: str | None = None

    for text_name in normalized:
        sword_dir, module_name = resolve_text_source(text_name, sources)
        bible = load_bible(sword_dir, module_name)
        try:
            resolved_book = resolve_book_name(book, bible)
        except ValueError as exc:
            raise ValueError(f"{text_name} does not contain book '{book}'.") from exc
        chapter_verse_count(bible, resolved_book, chapter)
        if osis_book is None:
            osis_book = resolved_book
        rows = extract_chapter_rows(text_name, bible, sword_dir, resolved_book, chapter)
        all_row_sets.append(
            assign_word_keys_and_numbers(rows, text_name, resolved_book, chapter)
        )

    if not any(all_row_sets):
        raise ValueError("No words found for that reference.")

    aligned_rows, columns = build_synoptic_rows(
        all_row_sets,
        normalized,
        include_grammatical_data=include_grammatical_data,
    )
    word_counts = count_synoptic_words(aligned_rows, normalized)

    if output_path is None:
        if normalized == ["LXX", "WLC"] or normalized == ["WLC", "LXX"]:
            default_name = f"Synoptic_{osis_book}_{chapter}.csv"
        else:
            default_name = f"{'_'.join(normalized)}_{osis_book}_{chapter}.csv"
        output_path = Path(default_name)

    written_path = write_synoptic_csv(aligned_rows, output_path, columns=columns)
    return written_path, word_counts, osis_book or book


def main(argv: list[str] | None = None) -> int:
    sources = discover_text_sources()
    if not sources:
        print(f"Error: no text sources found under {SWORD_ROOT}", file=sys.stderr)
        return 1

    parser = build_arg_parser(sources)
    args = parser.parse_args(argv)

    if args.book and args.chapter:
        book_input = args.book
        chapter = args.chapter
    elif args.book or args.chapter:
        print("Error: provide both --book and --chapter, or neither.", file=sys.stderr)
        return 1
    elif args.synoptic:
        try:
            wlc_dir, wlc_module = resolve_text_source("WLC", sources)
        except KeyError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        bible = load_bible(wlc_dir, wlc_module)
        book_input, chapter = prompt_book_and_chapter(bible)
    else:
        if args.text:
            try:
                sword_dir, module_name = resolve_text_source(args.text, sources)
                text_name = args.text.upper()
            except KeyError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
        elif sys.stdin.isatty():
            text_name = prompt_text_source(sources)
            sword_dir, module_name = resolve_text_source(text_name, sources)
        else:
            text_name = DEFAULT_TEXT
            sword_dir, module_name = resolve_text_source(text_name, sources)

        if args.sword_dir:
            sword_dir = args.sword_dir
        if args.module:
            module_name = args.module

        try:
            bible = load_bible(sword_dir, module_name)
        except (FileNotFoundError, KeyError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        book_input, chapter = prompt_book_and_chapter(bible)

    if args.synoptic:
        try:
            written_path, word_counts, osis_book = export_synoptic_chapter(
                book_input,
                chapter,
                ["WLC", "LXX"],
                args.output,
            )
        except (FileNotFoundError, KeyError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        intended_path = args.output or Path(f"Synoptic_{osis_book}_{chapter}.csv")
        counts_msg = " + ".join(f"{count} {name}" for name, count in word_counts.items())
        print(f"Wrote {written_path.name} ({counts_msg} words, {osis_book} {chapter})")
        return 0 if written_path.resolve() == intended_path.resolve() else 1

    if args.text:
        try:
            sword_dir, module_name = resolve_text_source(args.text, sources)
            text_name = args.text.upper()
        except KeyError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    elif sys.stdin.isatty():
        text_name = prompt_text_source(sources)
        sword_dir, module_name = resolve_text_source(text_name, sources)
    else:
        text_name = DEFAULT_TEXT
        sword_dir, module_name = resolve_text_source(text_name, sources)

    if args.sword_dir:
        sword_dir = args.sword_dir
    if args.module:
        module_name = args.module

    try:
        written_path, word_count, osis_book = export_chapter(
            text_name,
            book_input,
            chapter,
            args.output,
            sword_dir=sword_dir,
            module_name=module_name,
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    intended_path = args.output or Path(f"{text_name}_{osis_book}_{chapter}.csv")
    print(
        f"Wrote {written_path.name} ({word_count} words from {text_name} "
        f"{osis_book} {chapter})"
    )
    return 0 if written_path.resolve() == intended_path.resolve() else 1


if __name__ == "__main__":
    raise SystemExit(main())

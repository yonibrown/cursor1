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
    "word",
    "verse",
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


def write_csv(rows: list[dict[str, str]], output_path: Path) -> Path:
    output_path = output_path.resolve()
    temp_path = output_path.with_name(output_path.name + ".tmp")

    with temp_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

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
    return parser


def main(argv: list[str] | None = None) -> int:
    sources = discover_text_sources()
    if not sources:
        print(f"Error: no text sources found under {SWORD_ROOT}", file=sys.stderr)
        return 1

    parser = build_arg_parser(sources)
    args = parser.parse_args(argv)

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

    if args.book and args.chapter:
        try:
            osis_book = resolve_book_name(args.book, bible)
            chapter_verse_count(bible, osis_book, args.chapter)
            chapter = args.chapter
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    elif args.book or args.chapter:
        print("Error: provide both --book and --chapter, or neither.", file=sys.stderr)
        return 1
    else:
        osis_book, chapter = prompt_book_and_chapter(bible)

    rows = extract_chapter_rows(text_name, bible, sword_dir, osis_book, chapter)
    if not rows:
        print("No words found for that reference.", file=sys.stderr)
        return 1

    output_path = args.output or Path(f"{text_name}_{osis_book}_{chapter}.csv")
    written_path = write_csv(rows, output_path)

    print(
        f"Wrote {written_path.name} ({len(rows)} words from {text_name} "
        f"{osis_book} {chapter})"
    )
    return 0 if written_path == output_path.resolve() else 1


if __name__ == "__main__":
    raise SystemExit(main())

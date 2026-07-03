#!/usr/bin/env python3
"""Convert Bible verse text files into a side-by-side CSV.

Each input file becomes one CSV column. Verse numbers appear on the same row
across columns; following rows contain the words of that verse, bottom-aligned
so the last word of each verse ends on the same row.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# Digits at a word boundary followed by verse text (glued or after a space).
VERSE_NUMBER = re.compile(r"(\d+)(?=[^\d\s]|\s)")


def _verse_starts(text: str) -> list[re.Match[str]]:
    """Return matches where a full verse number begins."""
    matches: list[re.Match[str]] = []
    for match in VERSE_NUMBER.finditer(text):
        if match.start() == 0 or text[match.start() - 1].isspace():
            matches.append(match)
    return matches


def parse_bible_verses(text: str) -> list[tuple[str, list[str]]]:
    """Split Bible text into ordered (verse number, words) pairs."""
    normalized = " ".join(text.split())
    if not normalized:
        return []

    matches = _verse_starts(normalized)
    if not matches:
        return [("", normalized.split())]

    verses: list[tuple[str, list[str]]] = []
    for i, match in enumerate(matches):
        verse_num = match.group(1)
        text_start = match.end()
        text_end = matches[i + 1].start() if i + 1 < len(matches) else len(normalized)
        verse_text = normalized[text_start:text_end].strip()
        words = verse_text.split() if verse_text else []
        verses.append((verse_num, words))

    return verses


def verse_order(all_verses: list[list[tuple[str, list[str]]]]) -> list[str]:
    """Return verse numbers in first-seen order across all input files."""
    order: list[str] = []
    seen: set[str] = set()
    for verses in all_verses:
        for verse_num, _ in verses:
            if verse_num not in seen:
                seen.add(verse_num)
                order.append(verse_num)
    return order


def align_verse_rows(
    all_verses: list[list[tuple[str, list[str]]]],
    ordered_verse_nums: list[str],
) -> list[list[str]]:
    """Build CSV rows with each verse ending on the same row in every column."""
    verse_maps = [{num: words for num, words in verses} for verses in all_verses]
    rows: list[list[str]] = []

    for verse_num in ordered_verse_nums:
        words_by_column: list[list[str]] = []
        verse_row: list[str] = []

        for verse_map in verse_maps:
            words = verse_map.get(verse_num)
            if words is None:
                verse_row.append("")
                words_by_column.append([])
            else:
                verse_row.append(verse_num)
                words_by_column.append(words)

        rows.append(verse_row)

        max_words = max((len(words) for words in words_by_column), default=0)
        for word_idx in range(max_words):
            rows.append(
                [
                    words[word_idx - (max_words - len(words))]
                    if word_idx >= max_words - len(words)
                    else ""
                    for words in words_by_column
                ]
            )

    return rows


def read_verses(path: Path) -> list[tuple[str, list[str]]]:
    text = path.read_text(encoding="utf-8")
    return parse_bible_verses(text)


def write_csv(rows: list[list[str]], headers: list[str], output_path: Path) -> Path:
    output_path = output_path.resolve()
    temp_path = output_path.with_name(output_path.name + ".tmp")

    with temp_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a CSV from Bible text files. "
            "Each file is one column; each verse ends on the same row."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Input text files (UTF-8), one column per file",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output.csv"),
        help="Output CSV path (default: output.csv)",
    )
    parser.add_argument(
        "--header",
        choices=("filename", "stem", "none"),
        default="filename",
        help="Column header style (default: filename)",
    )
    return parser


def column_headers(paths: list[Path], style: str) -> list[str]:
    if style == "none":
        return [""] * len(paths)
    if style == "stem":
        return [p.stem for p in paths]
    return [p.name for p in paths]


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    missing = [p for p in args.inputs if not p.is_file()]
    if missing:
        for path in missing:
            print(f"Error: file not found: {path}", file=sys.stderr)
        return 1

    headers = column_headers(args.inputs, args.header)
    all_verses = [read_verses(path) for path in args.inputs]
    ordered_verse_nums = verse_order(all_verses)
    rows = align_verse_rows(all_verses, ordered_verse_nums)

    written_path = write_csv(rows, headers, args.output)

    print(f"Wrote {written_path.name} ({len(rows)} rows, {len(headers)} columns)")
    return 0 if written_path == args.output.resolve() else 1


if __name__ == "__main__":
    raise SystemExit(main())

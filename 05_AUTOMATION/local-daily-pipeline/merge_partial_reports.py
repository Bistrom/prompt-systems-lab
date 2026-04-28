#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scala częściowe raporty postępów w jeden plik.

Strategia: wyciąga całą treść z każdego partial raportu niezależnie
od nazw nagłówków — odporne na warianty formatowania różnych modeli.

Sekcje o tych samych nagłówkach są grupowane razem.
Sekcje unikalne dla jednego chunka są dołączane bez grupowania.

Użycie:
  python3 merge_partial_reports.py \
    --input-dir /tmp/partial_reports_2026-04-22 \
    --output RAPORT_POSTEPOW_2026-04-22.md \
    --day 2026-04-22
"""

import argparse
import re
from pathlib import Path


def split_into_sections(text: str) -> list[tuple[str, str]]:
    """
    Dzieli tekst na sekcje według nagłówków ##.
    Zwraca listę par (nagłówek, treść).
    Treść przed pierwszym nagłówkiem ## trafia jako sekcja z nagłówkiem "_preamble".
    """
    sections = []
    # Podziel po nagłówkach ## (ale nie ###)
    parts = re.split(r'(?m)^(## [^\n]+)', text)

    # parts[0] = tekst przed pierwszym ##
    # parts[1] = nagłówek, parts[2] = treść, parts[3] = nagłówek, itd.
    preamble = parts[0].strip()
    if preamble:
        sections.append(("_preamble", preamble))

    i = 1
    while i < len(parts) - 1:
        header = parts[i].strip()
        content = parts[i + 1].strip()
        if content:
            sections.append((header, content))
        i += 2

    return sections


def normalize_header(header: str) -> str:
    """
    Normalizuje nagłówek do klucza grupowania.
    Usuwa numery, sprowadza do małych liter, usuwa znaki specjalne.
    Przykład: "## 2. Praca faktycznie wykonana" -> "praca faktycznie wykonana"
    """
    h = header.lstrip('#').strip()
    h = re.sub(r'^\d+[\.\)]\s*', '', h)  # usuń numer sekcji
    h = h.lower()
    h = re.sub(r'[^a-z0-9ąćęłńóśźż\s]', '', h)  # tylko litery i cyfry
    h = re.sub(r'\s+', ' ', h).strip()
    return h


def merge_reports(input_dir: Path, day: str) -> str:
    files = sorted(input_dir.glob("partial_report_*.md"))
    if not files:
        raise FileNotFoundError(f"Brak plików partial_report_*.md w {input_dir}")

    # Zbierz wszystkie sekcje ze wszystkich chunków
    # Struktura: {normalized_header: [(original_header, content, chunk_num), ...]}
    grouped: dict[str, list[tuple[str, str, int]]] = {}
    order: list[str] = []  # kolejność nagłówków (pierwsze wystąpienie)

    for chunk_num, f in enumerate(files, 1):
        text = f.read_text(encoding="utf-8", errors="replace")

        # Usuń nagłówek główny # RAPORT POSTĘPÓW — jeśli jest
        text = re.sub(r'(?m)^# RAPORT POSTĘPÓW.*\n', '', text)
        text = re.sub(r'(?m)^# Raport postępów.*\n', '', text, flags=re.IGNORECASE)

        sections = split_into_sections(text)

        for header, content in sections:
            if header == "_preamble":
                key = "_preamble"
            else:
                key = normalize_header(header)

            if key not in grouped:
                grouped[key] = []
                order.append(key)

            grouped[key].append((header, content, chunk_num))

    # Zbuduj wynik
    total_chunks = len(files)
    lines = [
        f"# RAPORT POSTĘPÓW — {day}",
        "",
        f"> Raport scalony z {total_chunks} częściowych raportów.",
        "",
    ]

    for key in order:
        entries = grouped[key]

        if key == "_preamble":
            # Preambuły z różnych chunków — dodaj tylko unikalne
            seen = set()
            for _, content, _ in entries:
                if content not in seen:
                    seen.add(content)
                    lines.append(content)
                    lines.append("")
            continue

        # Użyj nagłówka z pierwszego wystąpienia
        first_header = entries[0][0]
        lines.append(first_header)
        lines.append("")

        if len(entries) == 1:
            # Tylko jeden chunk ma tę sekcję — wstaw bez etykiety
            lines.append(entries[0][1])
            lines.append("")
        else:
            # Wiele chunków — oznacz skąd pochodzi każda część
            for original_header, content, chunk_num in entries:
                lines.append(f"<!-- źródło: chunk {chunk_num}/{total_chunks} -->")
                lines.append(content)
                lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scala częściowe raporty postępów w jeden plik."
    )
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--day", required=True)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_path = Path(args.output)

    result = merge_reports(input_dir, args.day)
    output_path.write_text(result, encoding="utf-8")
    print(f"[merge] Scalony raport zapisany: {output_path}")
    print(f"[merge] Rozmiar: {len(result)} znaków")


if __name__ == "__main__":
    main()

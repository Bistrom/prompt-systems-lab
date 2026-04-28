#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tnie chat_export na chunki o zadanym rozmiarze z zakładką.

Zapisuje:
- chunk_1.md, chunk_2.md, ... albo chunk_01.md, chunk_02.md, ... zależnie od liczby chunków,
- chunk_count.txt z liczbą utworzonych chunków.

Użycie:
  python3 chunk_chat_export.py \
    --input chat_export_2026-04-25.md \
    --output-dir /tmp/chunks_2026-04-25 \
    --chunk-size 20000 \
    --overlap 2000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


DEFAULT_CHUNK_SIZE = 20000
DEFAULT_OVERLAP = 2000


def validate_chunk_params(chunk_size: int, overlap: int) -> None:
    if chunk_size <= 0:
        raise ValueError("chunk-size musi być większy od zera.")
    if overlap < 0:
        raise ValueError("overlap nie może być ujemny.")
    if overlap >= chunk_size:
        raise ValueError("overlap musi być mniejszy niż chunk-size, inaczej chunking może nie iść do przodu.")


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    validate_chunk_params(chunk_size, overlap)

    if not text.strip():
        return []

    chunks: list[str] = []
    start = 0
    total = len(text)

    while start < total:
        end = min(start + chunk_size, total)

        # Cofnij do najbliższego końca linii, żeby ograniczyć cięcie w środku akapitu.
        # Nie cofamy, jeśli nowa granica byłaby zbyt blisko początku chunka.
        if end < total:
            newline = text.rfind("\n", start, end)
            min_safe_end = start + max(1, chunk_size // 2)
            if newline >= min_safe_end:
                end = newline + 1

        chunk = text[start:end]
        if chunk:
            chunks.append(chunk)

        if end >= total:
            break

        next_start = end - overlap
        if next_start <= start:
            raise RuntimeError(
                f"Chunking nie przesuwa się do przodu: start={start}, end={end}, overlap={overlap}"
            )
        start = next_start

    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description="Tnie chat_export na chunki z zakładką.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"Rozmiar chunka w znakach. Domyślnie: {DEFAULT_CHUNK_SIZE}.",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=DEFAULT_OVERLAP,
        help=f"Zakładka między chunkami w znakach. Domyślnie: {DEFAULT_OVERLAP}.",
    )
    args = parser.parse_args()

    try:
        validate_chunk_params(args.chunk_size, args.overlap)
    except ValueError as e:
        print(f"[ERROR] Nieprawidłowe parametry chunkingu: {e}", file=sys.stderr)
        return 1

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    if not input_path.exists():
        print(f"[ERROR] Brak pliku wejściowego: {input_path}", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    text = input_path.read_text(encoding="utf-8", errors="replace")
    chunks = chunk_text(text, args.chunk_size, args.overlap)

    if not chunks:
        print(f"[ERROR] Plik wejściowy jest pusty albo zawiera tylko białe znaki: {input_path}", file=sys.stderr)
        (output_dir / "chunk_count.txt").write_text("0", encoding="utf-8")
        return 1

    pad = len(str(len(chunks)))
    for i, chunk in enumerate(chunks, 1):
        filename = f"chunk_{str(i).zfill(pad)}.md"
        (output_dir / filename).write_text(chunk, encoding="utf-8")
        print(f"[chunk] {filename} — {len(chunk)} znaków")

    print(f"[chunk] Łącznie chunków: {len(chunks)}")
    (output_dir / "chunk_count.txt").write_text(str(len(chunks)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

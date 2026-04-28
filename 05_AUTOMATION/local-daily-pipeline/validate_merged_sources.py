#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Validate whether MERGED_SOURCES contains forbidden prompt-system content
as actual merged sources, while allowing system-file metadata inside
SOURCE_MANIFEST.

Usage:
python3 validate_merged_sources.py --merged "/path/to/MERGED_SOURCES_2026-04-25.txt"

Exit codes:
0 = validation passed
1 = validation failed
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PROMPT_ROOT_MARKERS = [
    "/09_Prompty/",
    "\\09_Prompty\\",
]

PROMPT_FILENAMES = [
    "generator_raportu_postepow.txt",
    "generator_dokumentacji_dnia_v2.txt",
]

REQUIRED_MANIFEST_FIELDS = [
    "DAY",
    "CHAT_EXPORT_PATH",
    "ROUGH_WORK_PATH",
    "WORKFLOW_MAP_PATH",
    "SCHEMAT_DAILY_LOG_PATH",
    "PROMPT_ETAP_1_PATH",
    "PROMPT_ETAP_2_PATH",
    "MODE",
    "PROMPT_TRACE_INCLUDED",
    "OTHER_SOURCES",
]

PROMPT_TRACE_SPECIAL_MODE = "SPECIAL_PROMPT_TRACE"
NON_SPECIAL_MODES = {"DEFAULT", "STRICT", "MANIFEST"}
ALLOWED_MODES = NON_SPECIAL_MODES | {PROMPT_TRACE_SPECIAL_MODE}


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def extract_source_manifest_block(text: str) -> str | None:
    match = re.search(
        r"(?ms)^SOURCE_MANIFEST\s*\n(.*?)^\s*END_SOURCE_MANIFEST\s*$",
        text,
    )
    if not match:
        return None
    return match.group(1)


def extract_non_manifest_text(text: str) -> str:
    return re.sub(
        r"(?ms)^SOURCE_MANIFEST\s*\n.*?^\s*END_SOURCE_MANIFEST\s*$\n?",
        "",
        text,
        count=1,
    )


def extract_source_manifest(text: str) -> tuple[list[str], dict[str, str]]:
    block = extract_source_manifest_block(text)
    if block is None:
        return [], {}

    entries: list[str] = []
    fields: dict[str, str] = {}

    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("-"):
            line = line[1:].strip()
        entries.append(line)

        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()

    return entries, fields


def extract_pipeline_mode(text: str, manifest_fields: dict[str, str]) -> str:
    manifest_mode = manifest_fields.get("MODE", "").strip().upper()
    if manifest_mode in ALLOWED_MODES:
        return manifest_mode

    match = re.search(
        r"(?mi)^PIPELINE_MODE:\s*(DEFAULT|SPECIAL_PROMPT_TRACE|STRICT|MANIFEST)\s*$",
        text,
    )
    if match:
        return match.group(1).strip().upper()

    return "DEFAULT"


def missing_manifest_fields(fields: dict[str, str]) -> list[str]:
    return [field for field in REQUIRED_MANIFEST_FIELDS if field not in fields]


def path_looks_like_prompt_system_file(path_str: str) -> bool:
    lowered = path_str.lower()
    return any(marker.lower() in lowered for marker in PROMPT_ROOT_MARKERS)


def filename_looks_like_prompt_file(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in PROMPT_FILENAMES)


def find_embedded_prompt_source_sections(text: str) -> list[str]:
    """
    Detects explicit prompt source sections outside SOURCE_MANIFEST.

    Current MERGED_SOURCES sections use lines such as:
      ===== SOURCE CATEGORY: PROMPT: ETAP 1 =====

    Older experimental outputs may use:
      Supplied filename: generator_raportu_postepow.txt
    """
    found: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()

        if re.match(r"^=+\s*SOURCE CATEGORY:\s*PROMPT\b", stripped, flags=re.IGNORECASE):
            found.append(stripped)
            continue

        if stripped.lower().startswith("supplied filename:"):
            supplied_name = stripped.split(":", 1)[1].strip()
            if filename_looks_like_prompt_file(supplied_name) or path_looks_like_prompt_system_file(supplied_name):
                found.append(stripped)
            continue

        if stripped.lower().startswith("supplied path:"):
            supplied_path = stripped.split(":", 1)[1].strip()
            if path_looks_like_prompt_system_file(supplied_path):
                found.append(stripped)

    return found


def fallback_detect_prompt_block(text: str) -> list[str]:
    """
    Used only as an additional weak signal. Do not add broad ordinary words here.
    """
    markers = [
        "=== INSTRUKCJA WYKONANIA (prompt etapu 1) ===",
        "CRITICAL ARTIFACT EXECUTION RULE",
        "FINAL RESPONSE RULE",
        "SELF-CHECK BEFORE FINALIZING",
        "MERGED VERSION NOTICE",
        "Act as a high-rigor daily documentation",
    ]
    lowered = text.lower()
    return [marker for marker in markers if marker.lower() in lowered]


def validate_with_manifest(
    text: str,
    merged_path: Path,
    manifest_entries: list[str],
    manifest_fields: dict[str, str],
    mode: str,
) -> int:
    print("Manifest źródeł: TAK")
    print(f"Liczba pozycji w manifeście: {len(manifest_entries)}")

    missing_fields = missing_manifest_fields(manifest_fields)
    if missing_fields:
        print("WALIDACJA: NIE")
        print("Powód: SOURCE_MANIFEST istnieje, ale nie zawiera wszystkich wymaganych pól.")
        print("Brakujące pola:")
        for field in missing_fields:
            print(f"- {field}")
        return 1

    prompt_trace = manifest_fields.get("PROMPT_TRACE_INCLUDED", "").strip().upper()
    if prompt_trace not in {"YES", "NO"}:
        print("WALIDACJA: NIE")
        print("Powód: SOURCE_MANIFEST zawiera nieprawidłową wartość pola PROMPT_TRACE_INCLUDED.")
        print(f"Wartość: {prompt_trace or 'BRAK'}")
        return 1

    non_manifest_text = extract_non_manifest_text(text)
    suspicious_blocks = fallback_detect_prompt_block(non_manifest_text)
    embedded_prompt_sources = find_embedded_prompt_source_sections(non_manifest_text)

    if mode in NON_SPECIAL_MODES:
        if prompt_trace == "YES":
            print("WALIDACJA: NIE")
            print("Powód: w trybie niespecjalnym wykryto PROMPT_TRACE_INCLUDED: YES.")
            return 1

        if embedded_prompt_sources:
            print("WALIDACJA: NIE")
            print("Powód: wykryto rzeczywiste dołączenie promptu jako źródła poza samym SOURCE_MANIFEST.")
            print("Wykryte sekcje źródłowe:")
            for entry in embedded_prompt_sources:
                print(f"- {entry}")
            return 1

        if suspicious_blocks:
            print("WALIDACJA: NIE")
            print("Powód: wykryto blok treści promptu systemowego poza SOURCE_MANIFEST.")
            print("Wykryte markery:")
            for marker in suspicious_blocks:
                print(f"- {marker}")
            return 1

        print("WALIDACJA: TAK")
        print("Powód: SOURCE_MANIFEST jest kompletny, a treść promptów nie została dołączona jako źródło.")
        return 0

    if mode == PROMPT_TRACE_SPECIAL_MODE:
        if prompt_trace != "YES":
            print("WALIDACJA: NIE")
            print("Powód: tryb specjalny wymaga PROMPT_TRACE_INCLUDED: YES w SOURCE_MANIFEST.")
            return 1

        print("WALIDACJA: TAK")
        if embedded_prompt_sources:
            print("Uwagi: wykryto rzeczywiste dołączenie promptów jako źródeł i jest to dozwolone w trybie specjalnym.")
            for entry in embedded_prompt_sources:
                print(f"- {entry}")
        else:
            print("Uwagi: tryb specjalny jest włączony, ale nie wykryto sekcji promptów poza manifestem.")
        return 0

    print("WALIDACJA: NIE")
    print(f"Powód: nieobsługiwany tryb: {mode}")
    return 1


def validate_without_manifest(text: str, mode: str) -> int:
    print("Manifest źródeł: NIE")
    suspicious = fallback_detect_prompt_block(text)

    if mode in NON_SPECIAL_MODES:
        if suspicious:
            print("WALIDACJA: NIE")
            print("Powód: brak SOURCE_MANIFEST i wykryto podejrzane bloki treści promptów systemowych.")
            print("Wykryte markery:")
            for marker in suspicious:
                print(f"- {marker}")
            return 1

        print("WALIDACJA: TAK WARUNKOWO")
        print("Powód: brak SOURCE_MANIFEST, ale nie wykryto dużych bloków promptów systemowych.")
        print("Uwaga: to jest tylko fallback; docelowo trzeba dodać SOURCE_MANIFEST.")
        return 0

    if mode == PROMPT_TRACE_SPECIAL_MODE:
        print("WALIDACJA: TAK WARUNKOWO")
        print("Powód: brak SOURCE_MANIFEST, ale tryb specjalny dopuszcza ślad promptów.")
        print("Uwaga: nadal warto dodać SOURCE_MANIFEST dla pełnej kontroli.")
        return 0

    print("WALIDACJA: NIE")
    print(f"Powód: nieobsługiwany tryb: {mode}")
    return 1


def validate_merged_sources(merged_path: Path) -> int:
    if not merged_path.exists():
        print("WALIDACJA: NIE")
        print(f"Powód: plik nie istnieje: {merged_path}")
        return 1

    text = normalize_newlines(merged_path.read_text(encoding="utf-8", errors="replace"))
    manifest_entries, manifest_fields = extract_source_manifest(text)
    mode = extract_pipeline_mode(text, manifest_fields)

    print(f"Plik: {merged_path}")
    print(f"Tryb: {mode}")

    if manifest_entries:
        return validate_with_manifest(text, merged_path, manifest_entries, manifest_fields, mode)

    return validate_without_manifest(text, mode)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate MERGED_SOURCES against prompt-source leakage rules."
    )
    parser.add_argument(
        "--merged",
        required=True,
        help="Absolute path to MERGED_SOURCES file.",
    )

    args = parser.parse_args()
    merged_path = Path(args.merged)

    return validate_merged_sources(merged_path)


if __name__ == "__main__":
    sys.exit(main())

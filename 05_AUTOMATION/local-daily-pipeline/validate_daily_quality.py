#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Semantyczna bramka jakości dla dziennego pipeline'u.

Cel:
- złapać słaby RAPORT_POSTEPOW, nawet jeśli etap 2 formalnie zwrócił MODEL_OUTPUT,
- złapać sprzeczności między DAILY_LOG a SOURCE_MANIFEST,
- złapać niespójności statusów typu planned/tested dla tego samego obszaru pracy.

Exit codes:
0 = walidacja przeszła
1 = walidacja nie przeszła
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ENGLISH_ADVISORY_PATTERNS = [
    r"\bIt seems like\b",
    r"\bHere's a general outline\b",
    r"\bgeneral outline of the steps\b",
    r"\bFirst,\s+make sure\b",
    r"\bNext,\s+you(?:'ll| will)\s+need\b",
    r"\bFinally,\s+once\b",
    r"\bIf necessary,\s+you can\b",
    r"\bYou can check\b",
    r"\byou(?:'ll| will)\s+need to\b",
    r"\bconsider refactoring\b",
    r"\bcommit your changes to Git\b",
]

REPORT_REQUIRED_SIGNALS = [
    "## Fakty z fragmentu",
    "## Fakty",
    "## Artefakty",
    "## Decyzje",
    "status:",
    "pewność:",
]

INSTRUCTION_LEAK_PATTERNS = [
    r"To jest fragment\s+\d+\s+z\s+\d+\s+całego pliku chat_export",
    r"Przetwarzaj tylko to, co jest w tym fragmencie",
    r"Nie uzupełniaj brakujących części",
    r"Nie zgaduj treści spoza fragmentu",
    r"===\s*INSTRUKCJA WYKONANIA",
    r"===\s*CHAT_EXPORT",
]

ROUGH_WORK_POSITIVE_PATTERNS = [
    r"\bz\s+brudnopisem\b",
    r"\bz\s+dołączonym\s+brudnopisem\b",
    r"\bdołączono\s+brudnopis\b",
    r"\bużyto\s+brudnopis\b",
    r"\bwykryto\s+brudnopis\b",
    r"\buwzględniono\s+brudnopis\b",
    r"\brough_work\s+istnieje\b",
    r"\bdołączono\s+rough_work\b",
    r"\bużyto\s+rough_work\b",
    r"\bwykryto\s+rough_work\b",
]

NEGATION_HINTS = [
    "nie ",
    "brak",
    "missing",
    "nie wykryto",
    "nie istnieje",
    "bez brudnopisu",
    "bez rough_work",
]

STATUS_LINE_RE = re.compile(r"^[-*]\s+.*status:\s*([a-zA-Z /]+)", flags=re.IGNORECASE)


def read_text(path: Path, label: str) -> str:
    if not path.exists():
        print(f"[ERROR] Brak pliku {label}: {path}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8", errors="replace")


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def parse_manifest(merged_sources: str) -> dict[str, str]:
    text = normalize_newlines(merged_sources)
    match = re.search(r"(?ms)^SOURCE_MANIFEST\s*\n(.*?)^\s*END_SOURCE_MANIFEST\s*$", text)
    if not match:
        return {}

    fields: dict[str, str] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def line_numbered_matches(text: str, patterns: list[str]) -> list[str]:
    findings: list[str] = []
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        for pattern in patterns:
            if re.search(pattern, line, flags=re.IGNORECASE):
                findings.append(f"linia {i}: {pattern} -> {line.strip()[:180]}")
    return findings


def report_quality_failures(raport_postepow: str) -> list[str]:
    failures: list[str] = []
    stripped = raport_postepow.strip()

    if len(stripped) < 300:
        failures.append("RAPORT_POSTEPOW jest bardzo krótki; prawdopodobnie nie daje wystarczającej podstawy do daily loga.")

    advisory = line_numbered_matches(raport_postepow, ENGLISH_ADVISORY_PATTERNS)
    if advisory:
        failures.append(
            "RAPORT_POSTEPOW zawiera angielską odpowiedź poradnikową zamiast czystej ekstrakcji faktów: "
            + " | ".join(advisory[:8])
        )

    leaks = line_numbered_matches(raport_postepow, INSTRUCTION_LEAK_PATTERNS)
    if leaks:
        failures.append(
            "RAPORT_POSTEPOW zawiera przeciek instrukcji technicznych z promptu/chunka: "
            + " | ".join(leaks[:8])
        )

    if not any(signal.lower() in raport_postepow.lower() for signal in REPORT_REQUIRED_SIGNALS):
        failures.append(
            "RAPORT_POSTEPOW nie zawiera rozpoznawalnej sekcji faktów, artefaktów, statusów ani poziomów pewności."
        )

    return failures


def positive_rough_work_claims(daily_log: str) -> list[str]:
    findings: list[str] = []
    for i, line in enumerate(daily_log.splitlines(), 1):
        lowered = line.lower()
        if any(hint in lowered for hint in NEGATION_HINTS):
            continue
        for pattern in ROUGH_WORK_POSITIVE_PATTERNS:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                findings.append(f"linia {i}: {line.strip()[:180]}")
                break
    return findings


def status_conflicts(daily_log: str) -> list[str]:
    """
    Heurystyka: łapie przypadek, gdy ten sam obszar, zwłaszcza etap 2,
    występuje jednocześnie jako planned i tested/completed bez sygnału,
    że planned dotyczy przyszłej, kolejnej pracy.
    """
    planned_lines: list[str] = []
    done_lines: list[str] = []

    for i, line in enumerate(daily_log.splitlines(), 1):
        lowered = line.lower()
        if "status:" not in lowered:
            continue

        is_stage2_related = "etap 2" in lowered or "etapu 2" in lowered or "pipeline" in lowered
        if not is_stage2_related:
            continue

        if "status: planned" in lowered:
            # Nie flagujemy planu przyszłej pracy, jeśli linia jawnie mówi o następnym/dalszym kroku.
            if not any(marker in lowered for marker in ["następn", "kolejn", "dalsz", "przyszł", "refaktor", "v8"]):
                planned_lines.append(f"linia {i}: {line.strip()[:180]}")

        if any(status in lowered for status in ["status: tested", "status: completed", "status: stabilized"]):
            done_lines.append(f"linia {i}: {line.strip()[:180]}")

    if planned_lines and done_lines:
        return [
            "Ten sam obszar pracy wygląda jednocześnie na planned oraz tested/completed/stabilized. "
            "planned: " + " | ".join(planned_lines[:5]) + " ; "
            "done: " + " | ".join(done_lines[:5])
        ]

    return []


DIAGNOSTIC_STAGE2_MODES = {
    "FALLBACK",
    "DETERMINISTIC_FROM_RAPORT_POSTEPOW",
    "DETERMINISTIC_OUTPUT_FROM_RAPORT_POSTEPOW",
    "DIAGNOSTIC_FROM_STAGE1_WARNINGS",
    "DIAGNOSTIC_FROM_STAGE2_REJECTION",
}


def daily_log_quality_failures(daily_log: str, manifest: dict[str, str]) -> list[str]:
    failures: list[str] = []

    stage2_mode = manifest.get("STAGE2_MODE", "").strip().upper()
    if stage2_mode in DIAGNOSTIC_STAGE2_MODES:
        failures.append(
            f"MERGED_SOURCES wskazuje diagnostyczny albo naprawczy tryb etapu 2: STAGE2_MODE={stage2_mode}. "
            "Taki DAILY_LOG nie może przejść walidacji semantycznej jako finalnie poprawny."
        )

    rough_path = manifest.get("ROUGH_WORK_PATH", "").strip().upper()
    if rough_path == "MISSING":
        rough_claims = positive_rough_work_claims(daily_log)
        if rough_claims:
            failures.append(
                "DAILY_LOG twierdzi lub sugeruje użycie brudnopisu, ale SOURCE_MANIFEST ma ROUGH_WORK_PATH: MISSING. "
                + " | ".join(rough_claims[:8])
            )

    conflicts = status_conflicts(daily_log)
    failures.extend(conflicts)

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Waliduje semantycznie RAPORT_POSTEPOW i DAILY_LOG.")
    parser.add_argument("--day", required=True)
    parser.add_argument("--daily-log", required=True)
    parser.add_argument("--raport-postepow", required=True)
    parser.add_argument("--merged", required=True)
    args = parser.parse_args()

    daily_log_path = Path(args.daily_log)
    raport_path = Path(args.raport_postepow)
    merged_path = Path(args.merged)

    daily_log = read_text(daily_log_path, "DAILY_LOG")
    raport_postepow = read_text(raport_path, "RAPORT_POSTEPOW")
    merged_sources = read_text(merged_path, "MERGED_SOURCES")
    manifest = parse_manifest(merged_sources)

    failures: list[str] = []

    if not manifest:
        failures.append("MERGED_SOURCES nie zawiera poprawnego SOURCE_MANIFEST, więc nie da się porównać daily loga z manifestem.")

    failures.extend(report_quality_failures(raport_postepow))
    failures.extend(daily_log_quality_failures(daily_log, manifest))

    print(f"Plik DAILY_LOG: {daily_log_path}")
    print(f"Plik RAPORT_POSTEPOW: {raport_path}")
    print(f"Plik MERGED_SOURCES: {merged_path}")

    if failures:
        print("WALIDACJA_DZIENNA: NIE")
        print("Powody:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("WALIDACJA_DZIENNA: TAK")
    print("Powód: raport postępów i daily log przeszły minimalną walidację semantyczną v8.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

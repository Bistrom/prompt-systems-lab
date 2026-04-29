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
import json
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
    "DETERMINISTIC_CLEAN_OUTPUT",
    "DIAGNOSTIC_FROM_STAGE1_WARNINGS",
    "DIAGNOSTIC_FROM_STAGE2_REJECTION",
}



def extract_markdown_section_by_heading(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = None

    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            break

    if start is None:
        return ""

    collected = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        collected.append(line)

    return "\n".join(collected).strip()


def strict_work_line_format_failures(daily_log: str) -> list[str]:
    section = extract_markdown_section_by_heading(daily_log, "## 2. Praca faktycznie wykonana")
    if not section:
        return ["Brak treści w sekcji '## 2. Praca faktycznie wykonana'."]

    allowed_statuses = r"(planned|started|in progress|partially completed|tested|completed)"
    allowed_confidence = r"(wysoka|średnia|niska)"

    bad = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped or not stripped.startswith(("-", "*")):
            continue

        ok = re.search(
            rf"—\s*status:\s*{allowed_statuses}\s*—\s*pewność:\s*{allowed_confidence}\s*$",
            stripped,
            flags=re.IGNORECASE,
        )
        if not ok:
            bad.append(stripped)

        if re.search(r"\((planned|completed|unknown|tested|in progress|partially completed)\)", stripped, flags=re.IGNORECASE):
            bad.append(stripped)

    if bad:
        return [
            "Sekcja '## 2. Praca faktycznie wykonana' zawiera punkty bez ścisłego formatu "
            "'— status: ... — pewność: ...' albo zawiera status w nawiasie: "
            + " | ".join(bad[:8])
        ]

    return []


def wrong_day_in_work_failures(daily_log: str, day: str) -> list[str]:
    section = extract_markdown_section_by_heading(daily_log, "## 2. Praca faktycznie wykonana")
    bad = []

    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue

        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", stripped)
        other_dates = [d for d in dates if d != day]

        if other_dates and re.search(r"status:\s*(completed|tested|in progress|started)\b", stripped, flags=re.IGNORECASE):
            bad.append(stripped)

    if bad:
        return [
            f"Sekcja pracy wykonanej zawiera działania dla daty innej niż {day}: "
            + " | ".join(bad[:8])
        ]

    return []


def scope_date_range_failures(daily_log: str, day: str) -> list[str]:
    section = extract_markdown_section_by_heading(daily_log, "## 1. Zakres dnia")
    if not section:
        return []

    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", section)
    other_dates = [d for d in dates if d != day]

    if other_dates:
        return [
            f"Sekcja '## 1. Zakres dnia' zawiera inne daty niż dzień loga {day}: "
            + ", ".join(sorted(set(other_dates)))
        ]

    if re.search(r"\bod\s+\d{1,2}\s+do\s+\d{1,2}\s+kwietnia\b", section, flags=re.IGNORECASE):
        return [
            "Sekcja '## 1. Zakres dnia' opisuje zakres wielodniowy zamiast pracy jednego dnia."
        ]

    return []


def next_steps_status_marker_failures(daily_log: str) -> list[str]:
    section = extract_markdown_section_by_heading(daily_log, "## 6. Następne kroki")
    bad = []

    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue

        if re.search(r"status:\s*planned\b|\(planned\)|\(completed\)|\(unknown\)", stripped, flags=re.IGNORECASE):
            bad.append(stripped)

    if bad:
        return [
            "Sekcja '## 6. Następne kroki' zawiera metadane statusu. Następne kroki mają być zwykłymi punktami: "
            + " | ".join(bad[:8])
        ]

    return []


def artifact_unknown_noise_failures(daily_log: str) -> list[str]:
    section = extract_markdown_section_by_heading(daily_log, "## 3. Artefakty utworzone lub zmodyfikowane")
    bad = []

    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue

        if re.search(r"operacja:\s*nieznana|status:\s*unknown|pewność:\s*niska", stripped, flags=re.IGNORECASE):
            bad.append(stripped)

        if re.search(r"^\s*[-*]\s+nazwa artefaktu:", stripped, flags=re.IGNORECASE):
            bad.append(stripped)

    if bad:
        return [
            "Sekcja artefaktów zawiera wpisy o niskiej pewności, nieznanej operacji albo niekanonicznym formacie. "
            "Takie wpisy powinny trafić do niepewności, nie do artefaktów wykonanych: "
            + " | ".join(bad[:8])
        ]

    return []


def fact_ledger_quality_failures(daily_log: str, fact_ledger_text: str) -> list[str]:
    failures: list[str] = []
    records: list[dict] = []
    for raw in fact_ledger_text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            records.append(json.loads(raw))
        except json.JSONDecodeError as e:
            failures.append(f"FACT_LEDGER zawiera niepoprawny JSONL: {e}")
            return failures

    included = [r for r in records if r.get("include_in_daily_log") is True]
    work_records = [r for r in included if r.get("category") == "work_done"]
    if not work_records:
        failures.append("FACT_LEDGER nie zawiera zaakceptowanych faktów kategorii work_done.")
        return failures

    work_section = extract_markdown_section_by_heading(daily_log, "## 2. Praca faktycznie wykonana")
    artifact_section = extract_markdown_section_by_heading(daily_log, "## 3. Artefakty utworzone lub zmodyfikowane")

    work_lines = [line.strip() for line in work_section.splitlines() if line.strip().startswith(("-", "*"))]
    if not work_lines:
        failures.append("DAILY_LOG nie zawiera punktów pracy wykonanej mimo istnienia FACT_LEDGER.")
        return failures

    normalized_facts = [str(r.get("normalized_fact", "")).strip() for r in work_records if str(r.get("normalized_fact", "")).strip()]

    for line in work_lines:
        clean_line = re.sub(
            r"\s*—\s*status:\s*(planned|started|in progress|partially completed|tested|completed)\s*—\s*pewność:\s*(wysoka|średnia|niska)\s*$",
            "",
            line.strip("-* ").strip(),
            flags=re.IGNORECASE,
        ).strip()
        if not any(clean_line == fact or clean_line in fact or fact in clean_line for fact in normalized_facts):
            failures.append("Punkt DAILY_LOG nie ma pokrycia w FACT_LEDGER: " + clean_line)

    work_mentions_file = bool(re.search(r"\.(py|sh|txt|md|json|jsonl|yml|yaml|csv|docx|pdf)\b", work_section, flags=re.IGNORECASE))
    artifact_says_no_basis = "Brak wystarczającej podstawy" in artifact_section
    if work_mentions_file and artifact_says_no_basis:
        failures.append("DAILY_LOG wymienia pliki w sekcji pracy wykonanej, ale sekcja artefaktów twierdzi, że brak podstawy do listy artefaktów.")

    self_invalidating = [
        r"wymaga jeszcze ręcznego przeglądu",
        r"może nie zawierać pełnego opisu",
        r"nie jest finalnym daily logiem",
        r"do ręcznej naprawy",
    ]
    found = [p for p in self_invalidating if re.search(p, daily_log, flags=re.IGNORECASE)]
    if found:
        failures.append("DAILY_LOG zawiera samounieważniające zastrzeżenia, więc nie powinien trafić do 01_Poprawne: " + ", ".join(found))

    return failures

def daily_log_quality_failures(daily_log: str, manifest: dict[str, str]) -> list[str]:
    failures: list[str] = []

    day = manifest.get("DAY", "").strip()

    failures.extend(strict_work_line_format_failures(daily_log))
    if day:
        failures.extend(scope_date_range_failures(daily_log, day))
        failures.extend(wrong_day_in_work_failures(daily_log, day))
    failures.extend(next_steps_status_marker_failures(daily_log))
    failures.extend(artifact_unknown_noise_failures(daily_log))

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



def standard_daily_log_headers_failures(daily_log: str) -> list[str]:
    """
    Wymusza sześć standardowych sekcji skróconego DAILY_LOG.

    To jest bramka jakości dla renderera deterministycznego:
    dokument nie może kończyć się na sekcji 4 ani gubić niepewności / następnych kroków.
    """
    expected = [
        "## 1. Zakres dnia",
        "## 2. Praca faktycznie wykonana",
        "## 3. Artefakty utworzone lub zmodyfikowane",
        "## 4. Decyzje operacyjne i metodologiczne",
        "## 5. Niepewności i nierozstrzygnięte punkty",
        "## 6. Następne kroki",
    ]

    found = re.findall(r"^## .+$", daily_log, flags=re.MULTILINE)

    failures = []
    failures.extend(standard_daily_log_headers_failures(daily_log))

    for header in expected:
        if header not in found:
            failures.append(f"DAILY_LOG nie zawiera wymaganej sekcji: {header}")

    # Wariant skrócony powinien mieć dokładnie te sześć sekcji.
    extra = [header for header in found if header not in expected]
    if extra:
        failures.append(
            "DAILY_LOG zawiera niestandardowe sekcje poza skróconym schematem: "
            + ", ".join(extra)
        )

    return failures

def source_manifest_stage2_mode(merged_text: str) -> str:
    in_manifest = False
    for line in merged_text.splitlines():
        stripped = line.strip()

        if stripped == "SOURCE_MANIFEST":
            in_manifest = True
            continue

        if stripped == "END_SOURCE_MANIFEST":
            in_manifest = False
            continue

        if in_manifest and stripped.startswith("STAGE2_MODE:"):
            return stripped.split(":", 1)[1].strip()

    return ""


def stage2_mode_consistency_failures(daily_log: str, merged_text: str) -> list[str]:
    manifest_mode = source_manifest_stage2_mode(merged_text)

    if not manifest_mode:
        return ["Brak STAGE2_MODE w SOURCE_MANIFEST."]

    found_modes = set(re.findall(r"STAGE2_MODE:\s*([A-Z_]+)", daily_log))
    bad_modes = sorted(mode for mode in found_modes if mode != manifest_mode)

    if bad_modes:
        return [
            "DAILY_LOG zawiera STAGE2_MODE niezgodny z SOURCE_MANIFEST: "
            + ", ".join(bad_modes)
            + f"; SOURCE_MANIFEST wskazuje: {manifest_mode}."
        ]

    return []

def main() -> int:
    parser = argparse.ArgumentParser(description="Waliduje semantycznie RAPORT_POSTEPOW i DAILY_LOG.")
    parser.add_argument("--day", required=True)
    parser.add_argument("--daily-log", required=True)
    parser.add_argument("--raport-postepow", required=True)
    parser.add_argument("--merged", required=True)
    parser.add_argument("--fact-ledger", default="", help="Opcjonalny FACT_LEDGER_YYYY-MM-DD.jsonl do walidacji pokrycia faktów.")
    args = parser.parse_args()

    daily_log_path = Path(args.daily_log)
    raport_path = Path(args.raport_postepow)
    merged_path = Path(args.merged)

    daily_log = read_text(daily_log_path, "DAILY_LOG")
    raport_postepow = read_text(raport_path, "RAPORT_POSTEPOW")
    merged_sources = read_text(merged_path, "MERGED_SOURCES")
    fact_ledger_text = read_text(Path(args.fact_ledger), "FACT_LEDGER") if args.fact_ledger else ""
    manifest = parse_manifest(merged_sources)

    failures: list[str] = []

    if not manifest:
        failures.append("MERGED_SOURCES nie zawiera poprawnego SOURCE_MANIFEST, więc nie da się porównać daily loga z manifestem.")

    failures.extend(report_quality_failures(raport_postepow))
    failures.extend(daily_log_quality_failures(daily_log, manifest))
    if fact_ledger_text:
        failures.extend(fact_ledger_quality_failures(daily_log, fact_ledger_text))
    merged_text = merged_path.read_text(encoding="utf-8")
    failures.extend(stage2_mode_consistency_failures(daily_log, merged_text))

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

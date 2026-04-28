#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Etap 2 pipeline'u dziennego przez Ollama API (bez Hermesa).

Wczytuje raport postępów i pliki sterujące, wysyła prompt do lokalnej Ollamy,
parsuje odpowiedź i zapisuje trzy główne pliki wyjściowe:
- DAILY_LOG_YYYY-MM-DD.md
- MERGED_SOURCES_YYYY-MM-DD.txt
- README_PL.txt

RAPORT_POSTEPOW_YYYY-MM-DD.md jest tworzony wcześniej przez merge_partial_reports.py
i nie jest tutaj nadpisywany.

Ten wariant v7.6.9 zawiera izolację promptu etapu 2, retry naprawczy z regułami jakości sekcji oraz oczyszczony deterministyczny fallback z RAPORT_POSTEPOW po odrzuceniu wyniku modelowego:
- jeśli model zwróci realną atrapę albo za krótki DAILY_LOG, skrypt tworzy deterministyczny
  jawny dokument diagnostyczny do ręcznej naprawy, bez wklejania pełnego skażonego RAPORT_POSTEPOW,
- MERGED_SOURCES zawiera realną treść źródeł, a nie tylko odsyłacze typu „patrz plik”,
- w trybie domyślnym MERGED_SOURCES nie dołącza pełnej treści promptów; przechowuje tylko ich ścieżki w SOURCE_MANIFEST,
- wynik modelu jest odrzucany, jeśli zawiera niepotwierdzone ścieżki, typowe literówki albo brakuje wymaganych nagłówków.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA_DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "mistral-pipeline"
REQUEST_TIMEOUT = 1800  # 30 minut — etap 2 przetwarza więcej materiału
MIN_DAILY_LOG_CHARS = 900
MIN_README_CHARS = 80

# Uwaga:
# Nie używamy ogólnego wzorca "placeholder", bo daily log może legalnie opisywać,
# że poprzedni błąd polegał na zapisaniu placeholdera. Wykrywamy tylko realne atrapy.
DAILY_LOG_BAD_PATTERNS = [
    # Tylko realna atrapa jako cała linia / cały plik, nie przykład opisany w notatce technicznej.
    r"^\s*\[Here is the content[^\]]*\]\s*$",
    r"^\s*\[tutaj\s+treść[^\]]*\]\s*$",
    r"^\s*pełna realna treść DAILY_LOG_[^\n]*\s*$",
    r"^\s*INSERT\s+DAILY_LOG\s*$",
    r"^\s*TODO\s*$",
]

README_BAD_PATTERNS = [
    r"^\s*\[Here is the content[^\]]*\]\s*$",
    r"^\s*\[tutaj\s+treść[^\]]*\]\s*$",
    r"^\s*krótki README_PL\.txt[^\n]*\s*$",
    r"^\s*TODO\s*$",
]


def read_file_safe(path: Path | None, label: str, required: bool = True) -> str:
    if path is None:
        if required:
            print(f"[ERROR] Brak ścieżki pliku: {label}", file=sys.stderr)
            sys.exit(1)
        return ""

    if not path.exists():
        if required:
            print(f"[ERROR] Brak wymaganego pliku: {label} -> {path}", file=sys.stderr)
            sys.exit(1)
        return ""

    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"[ERROR] Nie można odczytać {label}: {e}", file=sys.stderr)
        if required:
            sys.exit(1)
        return ""


def call_ollama(prompt: str, model: str, ollama_url: str) -> str:
    url = f"{ollama_url}/api/generate"
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.1,
            "num_ctx": 16384,
            "num_predict": 3000,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        raise RuntimeError(f"Błąd połączenia z Ollama API: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Nieprawidłowa odpowiedź JSON z Ollama: {e}") from e


def build_source_manifest(
    day: str,
    chat_export_path: str,
    rough_work_path: str,
    workflow_map_path: str,
    schemat_daily_log_path: str,
    prompt_etap1_path: str,
    prompt_etap2_path: str,
    stage1_quality_manifest_path: str,
    chunk_count: int,
    model: str,
    stage2_mode: str,
    prompt_trace_included: bool = False,
) -> str:
    prompt_trace_value = "YES" if prompt_trace_included else "NO"
    return f"""SOURCE_MANIFEST
DAY: {day}
MODE: DEFAULT
CHAT_EXPORT_PATH: {chat_export_path}
ROUGH_WORK_PATH: {rough_work_path}
WORKFLOW_MAP_PATH: {workflow_map_path}
SCHEMAT_DAILY_LOG_PATH: {schemat_daily_log_path}
PROMPT_ETAP_1_PATH: {prompt_etap1_path}
PROMPT_ETAP_2_PATH: {prompt_etap2_path}
STAGE1_QUALITY_MANIFEST_PATH: {stage1_quality_manifest_path}
PROMPT_TRACE_INCLUDED: {prompt_trace_value}
OTHER_SOURCES: NONE
PIPELINE_MODE: DEFAULT
CHUNK_COUNT: {chunk_count}
STAGE1_MODEL: {model} (Ollama, lokalnie)
STAGE2_MODEL: {model} (Ollama, lokalnie)
STAGE2_MODE: {stage2_mode}
END_SOURCE_MANIFEST"""


REQUIRED_CORE_DAILY_LOG_HEADINGS = [
    "## 1. Zakres dnia",
    "## 2. Praca faktycznie wykonana",
]

# Te sekcje są pożądane, ale według schematu mogą być pominięte albo oznaczone jako niewspierane.
OPTIONAL_DAILY_LOG_HEADINGS = [
    "## 3. Artefakty utworzone lub zmodyfikowane",
    "## 4. Decyzje operacyjne i metodologiczne",
    "## 5. Niepewności i nierozstrzygnięte punkty",
    "## 6. Następne kroki",
]

INSTRUCTION_LEAK_PATTERNS = [
    r"To jest fragment\s+\d+\s+z\s+\d+\s+całego pliku chat_export",
    r"Przetwarzaj tylko to, co jest w tym fragmencie",
    r"Nie uzupełniaj brakujących części",
    r"===\s*INSTRUKCJA WYKONANIA",
    r"===\s*COMMIT_WORKFLOW_MAP",
    r"===\s*SCHEMAT_DAILY_LOG",
    r"===\s*CHAT_EXPORT",
]

# Typowe sygnały, że lokalny model dodał halucynację, literówkę albo sztuczną strukturę.
# Używamy regexów z re.IGNORECASE, bo model może zmieniać wielkość liter.
BAD_QUALITY_PATTERNS = [
    r"\bDekizje\b",
    r"\bPROJEST\s+INŻYNIERYSKI\b",
    r"\bPROJEST\s+INŻYNIERSKI\b",
    r"\bPROJEKT\s+INŻYNIERYSKI\b",
    r"\bWordlPress\b",
    r"\bWordpress\b",
    r"znajduje się w folderze\s+01_Scripts",
    r"znajduje się w folderze\s+02_Pipeline_Stages",
]

PROGRESS_REPORT_ADVISORY_PATTERNS = [
    r"\bIt seems like\b",
    r"\bIt looks like\b",
    r"\bHere's a general outline\b",
    r"\bgeneral outline of the steps\b",
    r"\bHere(?:'s| is) a summary\b",
    r"\bFirst,\s+make sure\b",
    r"\bNext,\s+you(?:'ll| will)\s+need\b",
    r"\bFinally,\s+once\b",
]


def load_json_file(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {"error": "invalid_json", "path": str(path)}


def progress_report_advisory_findings(text: str) -> list[str]:
    findings: list[str] = []
    for pattern in PROGRESS_REPORT_ADVISORY_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            findings.append(f"podejrzany fragment poradnikowy: {pattern}")
    return findings


def stage1_manifest_findings(manifest: dict[str, object]) -> list[str]:
    findings: list[str] = []
    if not manifest:
        return findings

    warning_count = manifest.get("warning_count", 0)
    failure_count = manifest.get("failure_count", 0)
    try:
        warning_count_int = int(warning_count)
    except Exception:
        warning_count_int = 0
    try:
        failure_count_int = int(failure_count)
    except Exception:
        failure_count_int = 0

    if warning_count_int > 0:
        findings.append(f"etap 1 zgłosił ostrzeżenia jakości: {warning_count_int}")
    if failure_count_int > 0:
        findings.append(f"etap 1 zgłosił problemy techniczne partial reportów: {failure_count_int}")

    records = manifest.get("records", [])
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, dict):
                continue
            chunk_index = record.get("chunk_index", "?")
            warnings = record.get("warnings", [])
            failures = record.get("failures", [])
            if isinstance(warnings, list):
                for warning in warnings[:3]:
                    findings.append(f"chunk {chunk_index}: ostrzeżenie: {warning}")
            if isinstance(failures, list):
                for failure in failures[:3]:
                    findings.append(f"chunk {chunk_index}: problem techniczny: {failure}")
    return findings


def preflight_report_findings(raport_postepow: str, stage1_manifest: dict[str, object]) -> list[str]:
    findings: list[str] = []
    findings.extend(progress_report_advisory_findings(raport_postepow))
    findings.extend(stage1_manifest_findings(stage1_manifest))
    return findings


def format_bullets(items: list[str]) -> str:
    if not items:
        return "- brak"
    return "\n".join(f"- {item}" for item in items)


def extract_section(text: str, marker_start: str, marker_end: str) -> str:
    """Wyciąga treść między markerami."""
    pattern = re.compile(
        re.escape(marker_start) + r"(.*?)" + re.escape(marker_end),
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    return ""


def looks_like_bad_daily_log(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < MIN_DAILY_LOG_CHARS:
        return True

    for pattern in DAILY_LOG_BAD_PATTERNS:
        if re.search(pattern, stripped, flags=re.IGNORECASE | re.DOTALL | re.MULTILINE):
            return True

    return False


def looks_like_bad_readme(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < MIN_README_CHARS:
        return True

    for pattern in README_BAD_PATTERNS:
        if re.search(pattern, stripped, flags=re.IGNORECASE | re.DOTALL | re.MULTILINE):
            return True

    return False


def missing_required_daily_log_headings(text: str) -> list[str]:
    return [heading for heading in REQUIRED_CORE_DAILY_LOG_HEADINGS if heading not in text]


def contains_instruction_leak(text: str) -> list[str]:
    found = []
    for pattern in INSTRUCTION_LEAK_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            found.append(pattern)
    return found


def contains_bad_quality_patterns(text: str) -> list[str]:
    found = []
    for pattern in BAD_QUALITY_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            found.append(pattern)
    return found


def extract_path_like_fragments(text: str) -> list[str]:
    """Wyłapuje proste fragmenty wyglądające jak ścieżki. To heurystyka jakości, nie parser."""
    candidates = set()
    for match in re.finditer(r"(?<!\w)([A-Za-z0-9_./\\\-]+/[A-Za-z0-9_./\\\-]+)", text):
        cleaned = match.group(1).strip(".,;:()[]{}<>`'\"")
        if cleaned:
            candidates.add(cleaned)
    return sorted(candidates)


def unsupported_path_like_fragments(daily_log: str, source_report: str) -> list[str]:
    unsupported = []
    for fragment in extract_path_like_fragments(daily_log):
        if fragment not in source_report:
            unsupported.append(fragment)
    return unsupported


def _base_daily_log_quality_failures(daily_log: str, source_report: str) -> list[str]:
    failures = []

    if looks_like_bad_daily_log(daily_log):
        failures.append("DAILY_LOG wygląda jak atrapa albo jest za krótki.")

    missing = missing_required_daily_log_headings(daily_log)
    if missing:
        failures.append("Brak wymaganych nagłówków: " + ", ".join(missing))

    leaked_instructions = contains_instruction_leak(daily_log)
    if leaked_instructions:
        failures.append("Wykryto przeciek instrukcji technicznych do DAILY_LOG: " + ", ".join(leaked_instructions))

    bad_patterns = contains_bad_quality_patterns(daily_log)
    if bad_patterns:
        failures.append("Wykryto podejrzane literówki/halucynacje według wzorców: " + ", ".join(bad_patterns))

    unsupported_paths = unsupported_path_like_fragments(daily_log, source_report)
    if unsupported_paths:
        failures.append(
            "Wykryto ścieżki/foldery niepotwierdzone w raporcie postępów: "
            + ", ".join(unsupported_paths[:20])
        )

    return failures


def repeated_line_failures(daily_log: str, threshold: int = 4) -> list[str]:
    failures: list[str] = []
    counts: dict[str, int] = {}

    for raw_line in daily_log.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if len(line) < 25:
            continue

        counts[line] = counts.get(line, 0) + 1

    repeated = [(line, count) for line, count in counts.items() if count >= threshold]

    if repeated:
        examples = "; ".join(
            f"{count}× {line[:140]}"
            for line, count in repeated[:5]
        )
        failures.append(
            f"DAILY_LOG zawiera nadmiernie powtarzające się linie: {examples}"
        )

    return failures


def artifact_basenames(text: str) -> set[str]:
    extensions = "md|txt|py|sh|json|yml|yaml|csv|docx|pdf"

    patterns = [
        rf"`([^`]+?\.(?:{extensions}))`",
        rf"(?<![\w./-])([A-Za-z0-9_.-]+\.(?:{extensions}))(?![\w./-])",
    ]

    found: set[str] = set()

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            raw = match.group(1).strip().strip("`'\"")
            if not raw:
                continue
            found.add(Path(raw).name)

    return found


def unsupported_artifact_failures(daily_log: str, source_report: str) -> list[str]:
    failures: list[str] = []

    daily_artifacts = artifact_basenames(daily_log)
    report_artifacts = artifact_basenames(source_report)

    allowed_generated_prefixes = (
        "DAILY_LOG_",
        "MERGED_SOURCES_",
        "README_PL",
        "RAW_STAGE2_RESPONSE_",
        "RAW_STAGE2_REPAIR_RESPONSE_",
    )

    unsupported: list[str] = []

    for artifact in sorted(daily_artifacts):
        if artifact.startswith(allowed_generated_prefixes):
            continue
        if artifact not in report_artifacts:
            unsupported.append(artifact)

    if unsupported:
        failures.append(
            "DAILY_LOG zawiera artefakty plikowe niepotwierdzone w RAPORCIE POSTĘPÓW: "
            + ", ".join(unsupported[:20])
        )

    return failures



def extract_markdown_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start_index: int | None = None

    for i, line in enumerate(lines):
        if line.strip() == heading:
            start_index = i + 1
            break

    if start_index is None:
        return ""

    collected: list[str] = []
    for line in lines[start_index:]:
        if line.startswith("## ") and line.strip() != heading:
            break
        collected.append(line)

    return "\n".join(collected).strip()


def section_status_failures(daily_log: str) -> list[str]:
    failures: list[str] = []

    performed = extract_markdown_section(daily_log, "## 2. Praca faktycznie wykonana")
    if performed:
        planned_lines = [
            line.strip()
            for line in performed.splitlines()
            if "status: planned" in line.lower()
        ]
        if planned_lines:
            sample = " | ".join(planned_lines[:5])
            failures.append(
                "Sekcja '## 2. Praca faktycznie wykonana' zawiera elementy ze statusem planned. "
                "Elementy planowane muszą trafić do '## 6. Następne kroki' albo do niepewności. "
                f"Przykłady: {sample}"
            )

    return failures


def conversational_noise_failures(daily_log: str) -> list[str]:
    failures: list[str] = []

    noise_patterns = [
        r"\bPobierz,\s*podmień\b",
        r"\bRozumiem i zgadzam się\b",
        r"\buruchom ponownie\b",
        r"\bpowinieneś\b",
        r"\bmożesz teraz\b",
    ]

    hits: list[str] = []
    for pattern in noise_patterns:
        if re.search(pattern, daily_log, flags=re.IGNORECASE):
            hits.append(pattern)

    if hits:
        failures.append(
            "DAILY_LOG zawiera fragmenty instrukcyjne albo konwersacyjne, które nie są faktami roboczymi: "
            + ", ".join(hits)
        )

    return failures

def required_daily_log_section_failures(daily_log: str) -> list[str]:
    required_headers = [
        "## 1. Zakres dnia",
        "## 2. Praca faktycznie wykonana",
        "## 3. Artefakty utworzone lub zmodyfikowane",
        "## 4. Decyzje operacyjne i metodologiczne",
        "## 5. Niepewności i nierozstrzygnięte punkty",
        "## 6. Następne kroki",
    ]

    missing = [header for header in required_headers if header not in daily_log]

    if missing:
        return [
            "Brak wymaganych nagłówków DAILY_LOG: " + ", ".join(missing)
        ]

    return []


def planned_status_anywhere_failures(daily_log: str) -> list[str]:
    if re.search(r"status:\s*planned", daily_log, flags=re.IGNORECASE):
        return [
            "DAILY_LOG zawiera status: planned. Następne kroki mają być zwykłymi punktami bez metadanych statusu."
        ]

    return []


def workflow_metadata_noise_failures(daily_log: str) -> list[str]:
    banned_patterns = [
        r"uzasadnienie\s+placementu",
        r"commit\s+relevance",
        r"routing\s+repozytoryjny",
        r"zmiany\s+commit-relevant",
        r"ruch\s+artefaktów",
        r"^\s*-\s*\*\*lokalizacja docelowa:\*\*",
        r"^\s*-\s*\*\*operacja:\*\*",
        r"^\s*-\s*\*\*status:\*\*",
        r"^\s*-\s*\*\*pewność:\*\*",
        r"^\s*-\s*\*\*ruch:\*\*",
    ]

    found = []

    for pattern in banned_patterns:
        if re.search(pattern, daily_log, flags=re.IGNORECASE | re.MULTILINE):
            found.append(pattern)

    if found:
        return [
            "DAILY_LOG zawiera metadane workflow/placement/commit, które nie powinny trafiać do finalnego daily loga: "
            + ", ".join(found)
        ]

    return []

def daily_log_quality_failures(daily_log: str, source_report: str) -> list[str]:
    failures = _base_daily_log_quality_failures(daily_log, source_report)
    failures.extend(repeated_line_failures(daily_log))
    failures.extend(unsupported_artifact_failures(daily_log, source_report))
    failures.extend(section_status_failures(daily_log))
    failures.extend(conversational_noise_failures(daily_log))
    failures.extend(required_daily_log_section_failures(daily_log))
    failures.extend(planned_status_anywhere_failures(daily_log))
    failures.extend(workflow_metadata_noise_failures(daily_log))
    return failures


def parse_ollama_response(response: str) -> tuple[str, str]:
    """Zwraca (daily_log, readme). Jeśli brak markerów, cała odpowiedź jest kandydatem na daily_log."""
    daily_log = extract_section(response, "===DAILY_LOG_START===", "===DAILY_LOG_END===")
    readme = extract_section(response, "===README_PL_START===", "===README_PL_END===")

    if not daily_log:
        daily_log = response.strip()

    return daily_log.strip(), readme.strip()


def build_diagnostic_daily_log(
    day: str,
    rough_work_exists: bool,
    chunk_count: int,
    model: str,
    reasons: list[str],
    raport_postepow_path: Path,
    raw_response_path: Path | None = None,
    stage1_quality_manifest_path: Path | None = None,
) -> str:
    rough_note = (
        "Do wejścia dołączono rough_work."
        if rough_work_exists
        else "Nie wykryto pliku rough_work dla tego dnia."
    )
    raw_note = str(raw_response_path) if raw_response_path is not None else "nie dotyczy — etap 2 nie został uruchomiony"
    manifest_note = str(stage1_quality_manifest_path) if stage1_quality_manifest_path is not None else "brak manifestu jakości etapu 1"

    return f"""# DAILY_LOG_{day} — DO NAPRAWY

## Status dokumentu

Ten plik nie jest finalnym daily logiem. To jawny dokument diagnostyczny utworzony przez pipeline v7.6.9.

Pipeline nie wkleił pełnego `RAPORT_POSTEPOW_{day}.md` do tego pliku, ponieważ raport lub wynik etapu 2 został uznany za podejrzany jakościowo. Dzięki temu `DAILY_LOG` nie przenosi dalej skażonego raportu ani halucynacji modelu.

## Zakres techniczny

- Dzień przetwarzania: `{day}`
- Tryb pipeline'u: lokalny, bez Hermesa, bez zewnętrznego API
- Model: `{model}`
- Liczba chunków wejściowych przetworzonych w etapie 1: `{chunk_count}`
- Informacja o brudnopisie: {rough_note}

## Powód skierowania do naprawy

{format_bullets(reasons)}

## Pliki do ręcznej kontroli

- Raport postępów: `{raport_postepow_path}`
- Surowa odpowiedź etapu 2: `{raw_note}`
- Manifest jakości etapu 1: `{manifest_note}`
- MERGED_SOURCES: `MERGED_SOURCES_{day}.txt`

## Zalecana procedura naprawy

1. Otwórz `RAPORT_POSTEPOW_{day}.md` i sprawdź, czy zawiera fakty z rozmowy, a nie poradnik albo odpowiedź ogólną.
2. Otwórz `RAW_STAGE2_RESPONSE_{day}.txt`, jeżeli istnieje, i sprawdź, czy model nie wymyślił folderów, ścieżek albo statusów.
3. Popraw ręcznie daily log albo uruchom ponownie etap 2 dopiero po poprawieniu raportu postępów.
4. Nie przenoś tego pliku do `07_Daily_Logs/01_Poprawne`, dopóki nie zostanie ręcznie poprawiony.

## Notatka techniczna

Ten dokument jest celowo krótki. Pełny raport postępów pozostaje w pliku źródłowym i w `MERGED_SOURCES`, ale nie jest automatycznie przepisywany do `DAILY_LOG`, żeby nie utrwalać błędnej treści.
"""





def _report_bullets(source_report: str) -> list[str]:
    bullets: list[str] = []
    for raw_line in source_report.splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            bullets.append(line)
    return bullets


def _status_from_report_line(line: str) -> str:
    lower = line.lower()
    if "status: tested" in lower:
        return "tested"
    if "status: completed" in lower:
        return "completed"
    if "status: partially completed" in lower:
        return "partially completed"
    if "status: in progress" in lower:
        return "in progress"
    if "status: started" in lower:
        return "started"
    if "status: planned" in lower:
        return "planned"
    return "completed"


def _confidence_from_report_line(line: str) -> str:
    lower = line.lower()
    if "pewność: wysoka" in lower:
        return "wysoka"
    if "pewność: średnia" in lower:
        return "średnia"
    if "pewność: niska" in lower:
        return "niska"
    return "średnia"


def _clean_report_bullet(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^\-\s*", "", line)

    # Usuń istniejące statusy, żeby fallback nie dublował:
    # "(status: completed — pewność: wysoka) — status: completed..."
    line = re.sub(
        r"\s*\(status:\s*[^)]*\)",
        "",
        line,
        flags=re.IGNORECASE,
    )
    line = re.sub(
        r"\s*—\s*status:\s*(planned|started|in progress|partially completed|tested|completed|unknown)\s*—\s*pewność:\s*(wysoka|średnia|niska)",
        "",
        line,
        flags=re.IGNORECASE,
    )
    line = re.sub(
        r"\s*—\s*krok:\s*planned,\s*pewność:\s*(wysoka|średnia|niska)",
        "",
        line,
        flags=re.IGNORECASE,
    )

    line = re.sub(r"\s+", " ", line).strip()
    return line


def _limited(items: list, limit: int = 10) -> list:
    return items[:limit]


def build_deterministic_daily_log_from_report(
    day: str,
    source_report: str,
    rough_work_exists: bool,
    chunk_count: int,
    model: str,
    rejection_reasons: list[str],
    raport_postepow_path: Path,
) -> str:
    def strip_embedded_status(text: str) -> str:
        status_words = r"(planned|started|in progress|partially completed|tested|completed|unknown)"
        confidence_words = r"(wysoka|średnia|niska)"

        text = re.sub(
            rf"\s*\(status:\s*{status_words}\s*[—,]\s*pewność:\s*{confidence_words}\s*\)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            rf"\s*—\s*status:\s*{status_words}\s*—\s*pewność:\s*{confidence_words}",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            rf"\s*,\s*status:\s*{status_words}\s*,\s*pewność:\s*{confidence_words}",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            rf"\s*\(pewność:\s*{confidence_words}\s*\)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\s+", " ", text).strip()
        return text.strip(" -")

    def is_planned_source_line(text: str) -> bool:
        return "status: planned" in text.lower()

    def is_conversational_or_instruction_noise(text: str) -> bool:
        patterns = [
            r"\bClaude\s+powiedział\b",
            r"\bPobierz,\s*podmień\b",
            r"\buruchom ponownie\b",
            r"\bRozumiem i zgadzam się\b",
            r"\bTo bardzo dojrzała decyzja\b",
            r"^hermes\s+—\s+typ\s*:",
            r"\btyp:\s*skrypt,\s*operacja:\s*usunięto\b",
            r"\btyp:\s*komunikat\b",
            r"\boperacja:\s*nieznana\b",
            r"\bpipeline już się skończył\b",
            r"\bdziała pięknie\b",
            r"\brobi za mnie\b",
            r"\bnie jest dobrym narzędziem do nauki\b",
            r"\bprywatnym komputerze\b",
            r"\bkolega odradził\b",
            r"\bwrażliwe dane\b",
            r"\bhasło\b",
            r"\bprompt injection\b",
            r"\btak jak jest napisane w chatgpt\b",
        ]
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            return True

        # Długie cytaty w backtickach prawie zawsze są wypowiedzią z rozmowy,
        # a nie atomowym faktem roboczym.
        if text.count("`") >= 2 and len(text) > 180:
            return True

        # Bardzo długie punkty w fallbacku są ryzykowne, bo zwykle oznaczają,
        # że raport przepuścił całe zdanie rozmowne zamiast faktu.
        if len(text) > 300:
            return True

        return False

    def is_stale_or_low_value_next_step(text: str) -> bool:
        patterns = [
            r"\bClaude\s+powiedział\b",
            r"\bskrypt automatycznie kopiuje pliki\b",
            r"\bskrypt automatycznie wykryje\b",
            r"\bPotrzeba zmiany w skrypcie `?run_daily_pipeline\.sh`?.*rough_work\b",
            r"\bPotrzeba ponownego uruchomienia pipeline'u po naprawie błędu\b",
            r"\bPobierz,\s*podmień\b",
            r"\buruchom ponownie\b",
        ]
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    def normalize_work_item(text: str) -> str:
        text = re.sub(
            r"^Claude\s+zmienił\s+timeout\s+do\s+(.+?)\s+i\s+zmniejszył\s+rozmiar",
            r"Zmieniono timeout do \1 i zmniejszono rozmiar",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"^Zmieniono\s+timeout\s+do\s+(.+?)\s+i\s+zmniejszył\s+rozmiar",
            r"Zmieniono timeout do \1 i zmniejszono rozmiar",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"^Claude\s+zmienił\b", "Zmieniono", text, flags=re.IGNORECASE)
        text = re.sub(r"^aleks\s+usunął\b", "Usunięto", text, flags=re.IGNORECASE)
        text = re.sub(r"^pipeline\s+pada\b", "Stwierdzono, że pipeline pada", text, flags=re.IGNORECASE)
        text = text[:1].upper() + text[1:] if text else text
        return text

    def canonical_key(text: str) -> str:
        lower = text.lower()

        if "timeout" in lower and ("chunk" in lower or "chunka" in lower):
            return "timeout_and_chunk_size"
        if "rough_work_arg" in lower or "rough_work_args" in lower:
            return "rough_work_args_fix"
        if "run_daily_pipeline.sh" in lower and "rough_work" in lower:
            return "rough_work_copy_in_run_daily_pipeline"
        if "usun" in lower and "hermes" in lower:
            return "remove_hermes"
        if "ollama działa" in lower:
            return "ollama_works"
        if "pipeline pada" in lower and "walidacji wejść" in lower:
            return "pipeline_input_validation_without_hermes"

        lower = re.sub(r"`[^`]*`", "", lower)
        lower = re.sub(r"\d+", "", lower)
        lower = re.sub(r"[^a-ząćęłńóśźż]+", " ", lower)
        lower = re.sub(r"\s+", " ", lower).strip()
        return lower[:120]

    bullets = _report_bullets(source_report)

    actual_items: list[tuple[str, str, str]] = []
    actual_keys: set[str] = set()
    next_items: list[str] = []
    next_keys: set[str] = set()

    actual_keywords = (
        "zmiana",
        "zmieniono",
        "zmienił",
        "naprawa",
        "naprawiono",
        "uruchomienie",
        "uruchomiono",
        "przetworzenie",
        "przetworzono",
        "usunięto",
        "usunął",
        "działa",
        "pada",
        "błąd",
        "rough_work_arg",
        "rough_work_args",
    )

    plan_keywords = (
        "potrzeba",
        "należy",
        "trzeba",
        "plan",
        "planned",
        "następny krok",
        "kolejny krok",
    )

    for bullet in bullets:
        cleaned = _clean_report_bullet(bullet)
        if not cleaned:
            continue

        cleaned = strip_embedded_status(cleaned)
        if not cleaned or is_conversational_or_instruction_noise(cleaned):
            continue

        lower = cleaned.lower()

        if (
            any(keyword in lower for keyword in actual_keywords)
            and not is_planned_source_line(bullet)
            and not is_stale_or_low_value_next_step(cleaned)
        ):
            status = _status_from_report_line(bullet)
            if status == "planned":
                continue

            confidence = _confidence_from_report_line(bullet)
            item_text = normalize_work_item(cleaned)
            key = canonical_key(item_text)

            if key and key not in actual_keys:
                actual_items.append((item_text, status, confidence))
                actual_keys.add(key)
            continue

        if any(keyword in lower for keyword in plan_keywords):
            if not is_stale_or_low_value_next_step(cleaned):
                next_item = normalize_work_item(cleaned)
                key = canonical_key(next_item)
                if key and key not in next_keys:
                    next_items.append(next_item)
                    next_keys.add(key)

    artifacts = sorted(artifact_basenames(source_report))

    blocked_generated_prefixes = (
        "DAILY_LOG_",
        "MERGED_SOURCES_",
        "README_PL",
        "RAW_STAGE2_RESPONSE_",
        "RAW_STAGE2_REPAIR_RESPONSE_",
        "RAPORT_POSTEPOW_",
    )

    blocked_artifacts = {
        "ollama_stage1.py",
        "ollama_stage2.py",
        "chunk_chat_export.py",
        "merge_partial_reports.py",
        "validate_merged_sources.py",
        "validate_daily_quality.py",
        "COMMIT_WORKFLOW_MAP.md",
        "schemat_daily_log.md",
    }

    artifacts = [
        item for item in artifacts
        if not item.startswith(blocked_generated_prefixes)
        and item not in blocked_artifacts
    ]

    # W deterministic clean output nie pokazujemy wejść dnia jako artefaktów
    # "utworzonych lub zmodyfikowanych", jeśli raport nie daje mocnej podstawy.
    artifacts = [
        item for item in artifacts
        if not item.lower().startswith("chat_export_")
        and not (item.lower().startswith("rough_work") and not rough_work_exists)
    ]

    if not actual_items:
        actual_items = [
            (
                "Raport postępów został scalony z wyników etapu 1 i użyty jako źródło dla DAILY_LOG.",
                "completed",
                "średnia",
            )
        ]

    rough_note = (
        "rough_work istniał i mógł pełnić funkcję pomocniczą."
        if rough_work_exists
        else "rough_work nie istniał; podstawowym źródłem był chat_export przetworzony przez etap 1."
    )

    actual_block = "\n".join(
        f"- {item} — status: {status} — pewność: {confidence}"
        for item, status, confidence in _limited(actual_items, 12)
    )

    if artifacts:
        artifact_block = "\n".join(
            f"- `{artifact}` — typ: artefakt techniczny; status: wspomniany w raporcie postępów; pewność: średnia"
            for artifact in artifacts
        )
    else:
        artifact_block = "- Brak jednoznacznie nazwanych artefaktów w raporcie postępów."

    if next_items:
        next_block = "\n".join(
            f"- {item}"
            for item in _limited(next_items, 8)
        )
    else:
        next_block = "- Brak osobnych następnych kroków jednoznacznie wspartych raportem postępów."

    return f"""# DAILY LOG — {day}

## 1. Zakres dnia

Praca dotyczyła lokalnego pipeline'u dziennego bez Hermesa, z użyciem Ollamy oraz raportu postępów wygenerowanego z {chunk_count} chunków.

## 2. Praca faktycznie wykonana

{actual_block}

## 3. Artefakty utworzone lub zmodyfikowane

{artifact_block}

## 4. Decyzje operacyjne i metodologiczne

- Brak jednoznacznie potwierdzonych decyzji metodologicznych poza informacjami ujętymi w sekcji pracy wykonanej.
- {rough_note}

## 5. Niepewności i nierozstrzygnięte punkty

- Część statusów została uogólniona do poziomu ostrożnego, ponieważ raport postępów nie zawsze rozstrzyga pełny kontekst zdarzeń.
- Brak wystarczającej podstawy w raporcie postępów do pełnej rekonstrukcji wszystkich artefaktów i decyzji.

## 6. Następne kroki

{next_block}
"""






def default_readme(day: str, chunk_count: int, model: str, stage2_mode: str) -> str:
    return f"""# README_PL — {day}

Pakiet dokumentacyjny wygenerowany przez lokalny pipeline dzienny.

## Pliki w pakiecie

- RAPORT_POSTEPOW_{day}.md — raport postępów z etapu 1.
- DAILY_LOG_{day}.md — dzienny log pracy z etapu 2 albo jawnie oznaczony szkic deterministyczny do przeglądu.
- MERGED_SOURCES_{day}.txt — scalony pakiet źródeł z realną treścią materiałów.
- README_PL.txt — ten plik.

## Parametry pipeline'u

- Dzień: {day}
- Tryb: lokalny, bez Hermesa
- Model: {model}
- Liczba chunków: {chunk_count}
- Tryb etapu 2: {stage2_mode}
"""


def build_merged_sources(
    manifest: str,
    day: str,
    raport_postepow_path: str,
    raport_postepow: str,
    daily_log_path: Path,
    daily_log: str,
    chat_export_path: str,
    chat_export: str,
    rough_work_path: str,
    rough_work: str,
    workflow_map_path: str,
    workflow_map: str,
    schemat_daily_log_path: str,
    schemat_daily_log: str,
    prompt_etap1_path: str,
    prompt_etap1: str,
    prompt_etap2_path: str,
    prompt_etap2: str,
    stage1_quality_manifest_path: str,
    stage1_quality_manifest_text: str,
    include_prompt_trace: bool = False,
) -> str:
    parts: list[str] = [manifest]

    def add_section(category: str, source_file: str, content: str) -> None:
        parts.append(f"""

===== SOURCE CATEGORY: {category} =====
===== SOURCE FILE: {source_file} =====

{content.strip() if content.strip() else "[BRAK TREŚCI]"}
""")

    add_section(
        "AI-GENERATED DAILY LOG",
        str(daily_log_path),
        daily_log,
    )
    add_section(
        "AI-GENERATED PROGRESS REPORT",
        raport_postepow_path,
        raport_postepow,
    )
    if stage1_quality_manifest_text:
        add_section(
            "STAGE1 QUALITY MANIFEST",
            stage1_quality_manifest_path,
            stage1_quality_manifest_text,
        )
    if rough_work:
        add_section(
            "USER ROUGH WORK",
            rough_work_path,
            rough_work,
        )
    add_section(
        "CHAT EXPORT",
        chat_export_path,
        chat_export,
    )
    add_section(
        "CONTROL DOCUMENT: COMMIT_WORKFLOW_MAP",
        workflow_map_path,
        workflow_map,
    )
    add_section(
        "CONTROL DOCUMENT: SCHEMAT_DAILY_LOG",
        schemat_daily_log_path,
        schemat_daily_log,
    )

    # W trybie DEFAULT nie dołączamy pełnej treści promptów do MERGED_SOURCES.
    # Manifest zachowuje ich ścieżki jako metadane, ale PROMPT_TRACE_INCLUDED pozostaje NO.
    # Pełny prompt trace można włączyć jawnie flagą --include-prompt-trace.
    if include_prompt_trace:
        add_section(
            "PROMPT: ETAP 1",
            prompt_etap1_path,
            prompt_etap1,
        )
        add_section(
            "PROMPT: ETAP 2",
            prompt_etap2_path,
            prompt_etap2,
        )

    return "\n".join(parts).strip() + "\n"


def build_stage2_prompt(
    day: str,
    raport_postepow: str,
    workflow_map: str,
    schemat_daily_log: str,
    prompt_etap2: str,
    rough_work: str,
    rough_work_exists: bool,
    chunk_count: int,
) -> str:
    rough_note = (
        "rough_work istnieje i jego treść znajduje się w sekcji ROUGH_WORK."
        if rough_work_exists
        else "rough_work nie istnieje — nie uwzględniaj go."
    )
    return f"""Jesteś lokalnym etapem 2 pipeline'u dziennego.

ZADANIE:
Na podstawie RAPORTU POSTĘPÓW utwórz daily log po polsku zgodny z dokumentami sterującymi.

DZIEŃ:
{day}

KONTEKST TECHNICZNY:
- Tryb: lokalny, bez Hermesa, bez zewnętrznego API.
- Etap 1 przetworzył {chunk_count} chunków.
- {rough_note}

ZASADY:
- Nie wymyślaj działań, których nie ma w raporcie.
- Nie pisz atrap ani pustych ramek.
- Nie odsyłaj do plików zamiast pisać treść.
- Nie wymyślaj folderów ani ścieżek. Ścieżkę lub folder wolno podać tylko wtedy, gdy występuje dosłownie w RAPORCIE POSTĘPÓW albo w mapie workflow.
- Jeżeli nie znasz lokalizacji pliku, wpisz: "lokalizacja niepotwierdzona w raporcie".
- Rzeczy planowane wpisuj tylko jako planned w sekcji "## 6. Następne kroki" albo w sekcji niepewności. Nie wolno umieszczać statusu planned w sekcji "## 2. Praca faktycznie wykonana".
- Nie dodawaj sekcji typu "Routing repozytoryjny", "placement", "Ruch artefaktów" ani "Zmiany commit-relevant".
- W sekcji "## 6. Następne kroki" zapisuj przyszłe działania jako zwykłe punkty bez frazy "status: planned".
- Nie używaj w finalnym DAILY_LOG pól typu "Lokalizacja docelowa", "Uzasadnienie placementu", "Commit relevance", "Ruch", "Operacja", "**Status:**", "**Pewność:**".
- Finalny DAILY_LOG musi zawierać dokładnie sześć standardowych nagłówków: "## 1. Zakres dnia", "## 2. Praca faktycznie wykonana", "## 3. Artefakty utworzone lub zmodyfikowane", "## 4. Decyzje operacyjne i metodologiczne", "## 5. Niepewności i nierozstrzygnięte punkty", "## 6. Następne kroki".
- Nie generuj listy artefaktów z dokumentów sterujących. Artefakty wolno wypisać tylko wtedy, gdy nazwa pliku występuje dosłownie w RAPORCIE POSTĘPÓW.
- Jeżeli RAPORT POSTĘPÓW zawiera wypowiedź rozmowną albo instrukcję typu "Pobierz, podmień", "uruchom ponownie" albo "Rozumiem i zgadzam się", nie przepisuj jej jako wykonanej pracy.
- Nie wpisuj do DAILY_LOG fragmentów rozmowy typu "Pobierz, podmień", "uruchom ponownie", "Rozumiem i zgadzam się". To są instrukcje albo reakcje rozmówcy, nie fakty robocze.
- Jeżeli ten sam obszar pracy jest już tested/completed, nie opisuj go jednocześnie jako planned, chyba że jawnie chodzi o przyszły etap.
- Jeżeli rough_work nie istnieje, nie pisz, że był brudnopis albo sukces z brudnopisem.
- Gdy materiał jest skąpy, napisz krótki daily log i oznacz niepewności.
- Pisz naturalnie po polsku.
- Nie używaj słowa "ukończono", jeżeli raport tego jasno nie potwierdza.
- Nie wolno przepisywać instrukcji technicznych typu "To jest fragment..." jako treści daily loga.
- Priorytet źródeł: RAPORT POSTĘPÓW > ROUGH_WORK > dokumenty sterujące. Dokumenty sterujące określają strukturę i routing, nie są dowodem, że coś wykonano.

FORMAT DAILY_LOG:
# DAILY LOG — {day}

## 1. Zakres dnia
Krótko: czego dotyczyła praca.

## 2. Praca faktycznie wykonana
Punkty w formacie:
- opis działania — status: [started/in progress/partially completed/tested/completed] — pewność: [wysoka/średnia/niska]

## 3. Artefakty utworzone lub zmodyfikowane
Jeżeli raport wskazuje konkretne pliki/skrypty/foldery, wypisz je. Nie dopisuj lokalizacji, jeśli raport jej nie podaje albo mapa workflow jej nie uzasadnia. Jeśli nie ma podstawy, wpisz:
- Brak wystarczającej podstawy w raporcie postępów do pełnej listy artefaktów.

## 4. Decyzje operacyjne i metodologiczne
Tylko decyzje wynikające z raportu.

## 5. Niepewności i nierozstrzygnięte punkty
Wypisz luki, konflikty i rzeczy wymagające ręcznego sprawdzenia.

## 6. Następne kroki
Tylko kroki wynikające z raportu.

ROUGH_WORK:
{rough_work if rough_work_exists else "[BRAK]"}

RAPORT POSTĘPÓW:
{raport_postepow}

CONTROL_DOCUMENTS_SUMMARY:
Dokumenty sterujące zostały zwalidowane i zostaną zapisane w MERGED_SOURCES jako źródła kontrolne.
Nie są jednak doklejane do promptu wykonawczego lokalnego modelu, ponieważ lokalny model ma skłonność do przepisywania routingu, placementu i reguł commitowych jako faktów dnia.
W tej fazie model ma używać wyłącznie RAPORTU POSTĘPÓW, opcjonalnego ROUGH_WORK i lokalnego kontraktu formatu.

IZOLACJA PROMPTU ETAPU 2:
Pełny plik promptu etapu 2 został zwalidowany i pozostaje odnotowany jako metadana wejściowa.
Nie jest jednak doklejany jako instrukcja wykonawcza dla lokalnego modelu, ponieważ może zawierać szerszy kontrakt generowania wielu plików.
W tej fazie obowiązuje wyłącznie lokalny kontrakt poniżej.

ZWRÓĆ WYŁĄCZNIE DWIE SEKCJE Z MARKERAMI:

===DAILY_LOG_START===
tu wpisz gotowy daily log
===DAILY_LOG_END===

===README_PL_START===
krótki README po polsku: dzień, tryb, model, zawartość pakietu
===README_PL_END===
"""


def build_stage2_repair_prompt(
    day: str,
    raport_postepow: str,
    rejected_response: str,
    quality_failures: list[str],
    chunk_count: int,
    rough_work_exists: bool,
) -> str:
    failure_text = "\n".join(f"- {failure}" for failure in quality_failures)
    rejected_excerpt = rejected_response.strip()[:5000]
    rough_note = (
        "rough_work istnieje, ale używaj go tylko wtedy, gdy został jawnie podany w materiale."
        if rough_work_exists
        else "rough_work nie istnieje — nie twierdź, że był użyty."
    )

    return f"""Jesteś naprawczym etapem 2 pipeline'u dziennego.

POPRZEDNIA ODPOWIEDŹ MODELU ZOSTAŁA ODRZUCONA.

POWODY ODRZUCENIA:
{failure_text}

CEL:
Wygeneruj poprawny DAILY_LOG i krótki README_PL na podstawie RAPORTU POSTĘPÓW.
Nie streszczaj instrukcji.
Nie opisuj samego mechanizmu chunkowania jako pracy dnia, chyba że RAPORT POSTĘPÓW mówi, że praca faktycznie dotyczyła chunkowania.
Nie pisz atrapy.
Nie pisz pustych sekcji.
Nie pisz, że brak danych, jeśli RAPORT POSTĘPÓW zawiera konkretne fakty.
{rough_note}

WYMAGANIA FORMATU:
Musisz zwrócić dokładnie dwie sekcje z markerami:

===DAILY_LOG_START===
# DAILY LOG — {day}

## 1. Zakres dnia
...

## 2. Praca faktycznie wykonana
- ...

## 3. Artefakty utworzone lub zmodyfikowane
- ...

## 4. Decyzje operacyjne i metodologiczne
- ...

## 5. Niepewności i nierozstrzygnięte punkty
- ...

## 6. Następne kroki
- ...
===DAILY_LOG_END===

===README_PL_START===
# README_PL — {day}

Krótki opis pakietu i sposobu wygenerowania.
===README_PL_END===

REGUŁY:
- Pisz po polsku.
- Oprzyj się wyłącznie na RAPORCIE POSTĘPÓW.
- Jeżeli czegoś nie da się ustalić, oznacz to jako niepewność.
- Każdy punkt pracy powinien mieć status i pewność, jeśli materiał na to pozwala.
- W sekcji "## 2. Praca faktycznie wykonana" nie wolno umieszczać elementów ze statusem planned.
- Elementy planowane wolno umieszczać wyłącznie w sekcji "## 6. Następne kroki" albo w sekcji niepewności.
- Nie dodawaj sekcji typu "Routing repozytoryjny", "placement", "Ruch artefaktów" ani "Zmiany commit-relevant".
- W sekcji "## 6. Następne kroki" zapisuj przyszłe działania jako zwykłe punkty bez frazy "status: planned".
- Nie używaj w finalnym DAILY_LOG pól typu "Lokalizacja docelowa", "Uzasadnienie placementu", "Commit relevance", "Ruch", "Operacja", "**Status:**", "**Pewność:**".
- Finalny DAILY_LOG musi zawierać dokładnie sześć standardowych nagłówków: "## 1. Zakres dnia", "## 2. Praca faktycznie wykonana", "## 3. Artefakty utworzone lub zmodyfikowane", "## 4. Decyzje operacyjne i metodologiczne", "## 5. Niepewności i nierozstrzygnięte punkty", "## 6. Następne kroki".
- Nie wymieniaj artefaktów plikowych, których nie ma dosłownie w RAPORCIE POSTĘPÓW.
- Nie kopiuj fragmentów rozmowy typu "Pobierz, podmień", "uruchom ponownie", "Rozumiem i zgadzam się".
- W sekcji "## 2. Praca faktycznie wykonana" nie wolno umieszczać elementów ze statusem planned.
- Elementy planowane wolno umieszczać wyłącznie w sekcji "## 6. Następne kroki" albo w sekcji niepewności.
- Nie wpisuj do DAILY_LOG fragmentów rozmowy typu "Pobierz, podmień", "uruchom ponownie", "Rozumiem i zgadzam się".
- Nie kopiuj bezmyślnie poprzedniej odrzuconej odpowiedzi.
- Nie wymieniaj artefaktów plikowych, których nie ma dosłownie w RAPORCIE POSTĘPÓW.
- Jeżeli poprzednia odpowiedź została odrzucona za planned w złej sekcji, przenieś te punkty do "## 6. Następne kroki" albo usuń je, jeśli są tylko instrukcją rozmowną.
- Jeżeli poprzednia odpowiedź została odrzucona za śmieci konwersacyjne, usuń je całkowicie.
- Nie dodawaj komentarza przed markerem ===DAILY_LOG_START===.
- Nie dodawaj komentarza po markerze ===README_PL_END===.

LICZBA CHUNKÓW ETAPU 1:
{chunk_count}

RAPORT POSTĘPÓW:
<<<RAPORT_POSTEPOW
{raport_postepow}
RAPORT_POSTEPOW>>>

ODRZUCONA ODPOWIEDŹ:
Pełna treść odrzuconej odpowiedzi nie jest podawana w retry prompt, ponieważ lokalny model ma skłonność do kopiowania błędnych fragmentów.
Naprawiaj wynik wyłącznie na podstawie RAPORTU POSTĘPÓW i listy POWODÓW ODRZUCENIA.
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Etap 2 pipeline'u dziennego przez Ollama API."
    )
    parser.add_argument("--day", required=True)
    parser.add_argument("--raport-postepow", required=True)
    parser.add_argument("--chat-export", required=True)
    parser.add_argument("--workflow-map", required=True)
    parser.add_argument("--schemat-daily-log", required=True)
    parser.add_argument("--prompt-etap2", required=True)
    parser.add_argument("--prompt-etap1", required=True)
    parser.add_argument("--stage1-quality-manifest", default="")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--chunk-count", type=int, required=True)
    parser.add_argument("--rough-work", default="")
    parser.add_argument(
        "--include-prompt-trace",
        action="store_true",
        help="Jawnie dołącz pełną treść promptów do MERGED_SOURCES i ustaw PROMPT_TRACE_INCLUDED: YES.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=OLLAMA_DEFAULT_URL)
    args = parser.parse_args()

    day = args.day
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raport_postepow_path = Path(args.raport_postepow)
    chat_export_path = Path(args.chat_export)
    workflow_map_path = Path(args.workflow_map)
    schemat_daily_log_path = Path(args.schemat_daily_log)
    prompt_etap1_path = Path(args.prompt_etap1)
    prompt_etap2_path = Path(args.prompt_etap2)
    stage1_quality_manifest_path = Path(args.stage1_quality_manifest) if args.stage1_quality_manifest else None

    raport_postepow = read_file_safe(raport_postepow_path, "raport_postepow")
    chat_export = read_file_safe(chat_export_path, "chat_export")
    # Te pliki nie są już w całości doklejane do promptu dla lokalnego Mistrala.
    # Nadal są walidowane i zapisywane w MERGED_SOURCES jako źródła kontrolne.
    workflow_map = read_file_safe(workflow_map_path, "workflow_map")
    schemat_daily_log = read_file_safe(schemat_daily_log_path, "schemat_daily_log")
    prompt_etap1 = read_file_safe(prompt_etap1_path, "prompt_etap1")
    prompt_etap2 = read_file_safe(prompt_etap2_path, "prompt_etap2")
    stage1_quality_manifest_text = read_file_safe(stage1_quality_manifest_path, "stage1_quality_manifest", required=False)
    stage1_quality_manifest = load_json_file(stage1_quality_manifest_path)

    rough_work_path = Path(args.rough_work) if args.rough_work else None
    rough_work_exists = rough_work_path is not None and rough_work_path.exists()
    rough_work = read_file_safe(rough_work_path, "rough_work", required=False) if rough_work_exists else ""

    print(f"[etap2] START: model={args.model}, ollama={args.ollama_url}")
    print("[etap2] Wersja: v7.6.9 prompt-isolation-repair-retry-section-quality-gates-deterministic-clean-fallback-raw-cache-audit")
    print(f"[etap2] Dzień: {day}, chunków: {args.chunk_count}")

    raw_response_path = output_dir / f"RAW_STAGE2_RESPONSE_{day}.txt"
    preflight_findings = preflight_report_findings(raport_postepow, stage1_quality_manifest)

    readme = ""
    if preflight_findings:
        print("[etap2] UWAGA: raport postępów / etap 1 ma ostrzeżenia jakości.")
        for finding in preflight_findings:
            print(f"[etap2] Powód diagnostyczny: {finding}")
        print("[etap2] Nie uruchamiam syntezy modelowej z podejrzanego raportu. Tworzę krótki dokument diagnostyczny.")
        daily_log = build_diagnostic_daily_log(
            day=day,
            rough_work_exists=rough_work_exists,
            chunk_count=args.chunk_count,
            model=args.model,
            reasons=preflight_findings,
            raport_postepow_path=raport_postepow_path,
            raw_response_path=None,
            stage1_quality_manifest_path=stage1_quality_manifest_path,
        )
        stage2_mode = "DIAGNOSTIC_FROM_STAGE1_WARNINGS"
    else:
        prompt = build_stage2_prompt(
            day=day,
            raport_postepow=raport_postepow,
            workflow_map=workflow_map,
            schemat_daily_log=schemat_daily_log,
            prompt_etap2=prompt_etap2,
            rough_work=rough_work,
            rough_work_exists=rough_work_exists,
            chunk_count=args.chunk_count,
        )

        print(f"[etap2] Wysyłanie do Ollama ({args.model})...")
        t0 = time.time()
        try:
            response = call_ollama(prompt, args.model, args.ollama_url)
        except RuntimeError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1
        elapsed = time.time() - t0
        print(f"[etap2] Odpowiedź po {elapsed:.1f}s, {len(response)} znaków")

        raw_response_path.write_text(response, encoding="utf-8")
        print(f"[etap2] Surowa odpowiedź modelu zapisana: {raw_response_path}")

        if not response.strip():
            print("[ERROR] Ollama zwróciła pustą odpowiedź", file=sys.stderr)
            return 1

        daily_log, readme = parse_ollama_response(response)

        stage2_mode = "MODEL_OUTPUT"
        quality_failures = daily_log_quality_failures(daily_log, raport_postepow)
        if quality_failures:
            print("[etap2] UWAGA: wynik modelu nie przeszedł bramki jakości.")
            for failure in quality_failures:
                print(f"[etap2] Powód odrzucenia: {failure}")

            repair_prompt = build_stage2_repair_prompt(
                day=day,
                raport_postepow=raport_postepow,
                rejected_response=response,
                quality_failures=quality_failures,
                chunk_count=args.chunk_count,
                rough_work_exists=rough_work_exists,
            )

            print(f"[etap2] Retry naprawczy: wysyłanie do Ollama ({args.model})...")
            repair_t0 = time.time()
            try:
                repair_response = call_ollama(repair_prompt, args.model, args.ollama_url)
            except RuntimeError as e:
                print(f"[ERROR] Retry naprawczy etapu 2 nie powiódł się: {e}", file=sys.stderr)
                repair_response = ""

            repair_elapsed = time.time() - repair_t0
            repair_raw_response_path = output_dir / f"RAW_STAGE2_REPAIR_RESPONSE_{day}.txt"
            repair_raw_response_path.write_text(repair_response, encoding="utf-8")
            print(f"[etap2] Retry naprawczy: odpowiedź po {repair_elapsed:.1f}s, {len(repair_response)} znaków")
            print(f"[etap2] Retry naprawczy: surowa odpowiedź zapisana: {repair_raw_response_path}")

            if repair_response.strip():
                repair_daily_log, repair_readme = parse_ollama_response(repair_response)
                repair_quality_failures = daily_log_quality_failures(repair_daily_log, raport_postepow)
            else:
                repair_daily_log, repair_readme = "", ""
                repair_quality_failures = ["retry naprawczy etapu 2 zwrócił pustą odpowiedź"]

            if not repair_quality_failures:
                print("[etap2] Retry naprawczy przeszedł bramkę jakości.")
                daily_log = repair_daily_log
                readme = repair_readme
                stage2_mode = "MODEL_OUTPUT_REPAIRED"
            else:
                print("[etap2] Retry naprawczy również nie przeszedł bramki jakości.")
                for failure in repair_quality_failures:
                    print(f"[etap2] Powód odrzucenia retry: {failure}")

                combined_failures = (
                    ["Pierwsza odpowiedź etapu 2 została odrzucona:"] +
                    quality_failures +
                    ["Retry naprawczy etapu 2 został odrzucony:"] +
                    repair_quality_failures
                )

                print("[etap2] Tworzę deterministyczny DAILY_LOG z RAPORT_POSTEPOW po nieudanym retry.")
                daily_log = build_deterministic_daily_log_from_report(
                    day=day,
                    source_report=raport_postepow,
                    rough_work_exists=rough_work_exists,
                    chunk_count=args.chunk_count,
                    model=args.model,
                    rejection_reasons=repair_quality_failures,
                    raport_postepow_path=raport_postepow_path,
                )

                deterministic_quality_failures = daily_log_quality_failures(daily_log, raport_postepow)

                if deterministic_quality_failures:
                    print("[etap2] Deterministyczny DAILY_LOG również nie przeszedł bramki jakości.")
                    for failure in deterministic_quality_failures:
                        print(f"[etap2] Powód odrzucenia deterministic output: {failure}")
                    stage2_mode = "DETERMINISTIC_OUTPUT_FROM_RAPORT_POSTEPOW"
                else:
                    print("[etap2] Deterministyczny DAILY_LOG przeszedł bramkę jakości.")
                    stage2_mode = "DETERMINISTIC_CLEAN_OUTPUT"

    if not readme or looks_like_bad_readme(readme):
        readme = default_readme(
            day=day,
            chunk_count=args.chunk_count,
            model=args.model,
            stage2_mode=stage2_mode,
        )

    rough_work_display = str(rough_work_path) if rough_work_exists else "MISSING"

    manifest = build_source_manifest(
        day=day,
        chat_export_path=str(chat_export_path),
        rough_work_path=rough_work_display,
        workflow_map_path=str(workflow_map_path),
        schemat_daily_log_path=str(schemat_daily_log_path),
        prompt_etap1_path=str(prompt_etap1_path),
        prompt_etap2_path=str(prompt_etap2_path),
        stage1_quality_manifest_path=str(stage1_quality_manifest_path) if stage1_quality_manifest_path else "MISSING",
        chunk_count=args.chunk_count,
        model=args.model,
        stage2_mode=stage2_mode,
        prompt_trace_included=args.include_prompt_trace,
    )

    daily_log_path = output_dir / f"DAILY_LOG_{day}.md"
    merged_path = output_dir / f"MERGED_SOURCES_{day}.txt"
    readme_path = output_dir / "README_PL.txt"

    merged_sources = build_merged_sources(
        manifest=manifest,
        day=day,
        raport_postepow_path=str(raport_postepow_path),
        raport_postepow=raport_postepow,
        daily_log_path=daily_log_path,
        daily_log=daily_log,
        chat_export_path=str(chat_export_path),
        chat_export=chat_export,
        rough_work_path=rough_work_display,
        rough_work=rough_work,
        workflow_map_path=str(workflow_map_path),
        workflow_map=workflow_map,
        schemat_daily_log_path=str(schemat_daily_log_path),
        schemat_daily_log=schemat_daily_log,
        prompt_etap1_path=str(prompt_etap1_path),
        prompt_etap1=prompt_etap1,
        prompt_etap2_path=str(prompt_etap2_path),
        prompt_etap2=prompt_etap2,
        stage1_quality_manifest_path=str(stage1_quality_manifest_path) if stage1_quality_manifest_path else "MISSING",
        stage1_quality_manifest_text=stage1_quality_manifest_text,
        include_prompt_trace=args.include_prompt_trace,
    )

    daily_log_path.write_text(daily_log, encoding="utf-8")
    merged_path.write_text(merged_sources, encoding="utf-8")
    readme_path.write_text(readme, encoding="utf-8")

    print(f"[etap2] Tryb etapu 2: {stage2_mode}")
    print(f"[etap2] DAILY_LOG zapisany: {daily_log_path}")
    print(f"[etap2] MERGED_SOURCES zapisany: {merged_path}")
    print(f"[etap2] README_PL zapisany: {readme_path}")
    print(f"[etap2] KONIEC: etap 2 zakończony sukcesem.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

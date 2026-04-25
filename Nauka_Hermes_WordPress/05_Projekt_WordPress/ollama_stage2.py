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

Ten wariant v7.3.3 zawiera zabezpieczenie przed fałszywym sukcesem i prostą bramkę jakości:
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


def daily_log_quality_failures(daily_log: str, source_report: str) -> list[str]:
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

Ten plik nie jest finalnym daily logiem. To jawny dokument diagnostyczny utworzony przez pipeline v7.3.3.

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
- Rzeczy planowane wpisuj tylko jako planned albo w następnych krokach. Nie przedstawiaj planów jako wykonanych decyzji.
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
- opis działania — status: [planned/started/in progress/partially completed/tested/completed] — pewność: [wysoka/średnia/niska]

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

COMMIT_WORKFLOW_MAP:
{workflow_map}

SCHEMAT_DAILY_LOG:
{schemat_daily_log}

DODATKOWA INSTRUKCJA ETAPU 2:
{prompt_etap2}

ZWRÓĆ WYŁĄCZNIE DWIE SEKCJE Z MARKERAMI:

===DAILY_LOG_START===
tu wpisz gotowy daily log
===DAILY_LOG_END===

===README_PL_START===
krótki README po polsku: dzień, tryb, model, zawartość pakietu
===README_PL_END===
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
    print("[etap2] Wersja: v7.3.3 safe-diagnostics-raw-cache-audit")
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
            print("[etap2] Tworzę krótki dokument diagnostyczny bez wklejania pełnego RAPORT_POSTEPOW.")
            daily_log = build_diagnostic_daily_log(
                day=day,
                rough_work_exists=rough_work_exists,
                chunk_count=args.chunk_count,
                model=args.model,
                reasons=quality_failures,
                raport_postepow_path=raport_postepow_path,
                raw_response_path=raw_response_path,
                stage1_quality_manifest_path=stage1_quality_manifest_path,
            )
            stage2_mode = "DIAGNOSTIC_FROM_STAGE2_REJECTION"

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

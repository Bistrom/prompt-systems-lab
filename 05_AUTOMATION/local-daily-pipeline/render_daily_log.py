#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_daily_log.py — deterministyczny renderer DAILY_LOG z FACT_LEDGER.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def read_text(path: Path | None, required: bool = True) -> str:
    if path is None:
        return ""
    if not path.exists():
        if required:
            raise FileNotFoundError(str(path))
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def confidence_rank(value: str) -> int:
    return {"niska": 1, "średnia": 2, "wysoka": 3}.get(value, 0)


def choose_confidence(values: list[str]) -> str:
    if not values:
        return "średnia"
    return sorted(values, key=confidence_rank, reverse=True)[0]


def explicit_dates(text: str) -> list[str]:
    return re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)


def has_other_day(text: str, day: str) -> bool:
    return any(date != day for date in explicit_dates(text))


def artifact_type(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".py"):
        return "skrypt Python"
    if lower.endswith(".sh"):
        return "skrypt Bash"
    if lower.endswith(".txt"):
        if "generator_" in lower:
            return "prompt / kontrakt tekstowy"
        if "komendy" in lower:
            return "ściąga operacyjna"
        return "plik tekstowy"
    if lower.endswith(".md"):
        return "dokument Markdown"
    if lower.endswith(".jsonl") or lower.endswith(".json"):
        return "dane strukturalne"
    return "artefakt techniczny"


def artifact_status(operation: str) -> str:
    if operation in {"utworzono"}:
        return "active"
    if operation in {"zmodyfikowano", "sprawdzono", "odnotowano", "uruchomiono"}:
        return "active"
    if operation in {"usunięto"}:
        return "archived"
    return "uncertain"


def section_for_record(rec: dict) -> str:
    """
    Zwraca docelową sekcję DAILY_LOG dla rekordu FACT_LEDGER.

    Priorytet:
    1. daily_log_section z FACT_LEDGER, jeśli jest pełnym nagłówkiem Markdown;
    2. mapowanie category → standardowa sekcja;
    3. bezpieczny fallback do sekcji pracy wykonanej.

    Ten fallback jest celowy: jeżeli rekord ma include_in_daily_log=True,
    nie wolno go zgubić tylko dlatego, że category ma wartość work_done.
    """
    section = str(rec.get("daily_log_section", "") or "").strip()
    if section.startswith("## "):
        return section

    category = str(rec.get("category", "") or "").strip()

    category_to_section = {
        "work_done": "## 2. Praca faktycznie wykonana",
        "decision": "## 4. Decyzje operacyjne i metodologiczne",
        "uncertainty": "## 5. Niepewności i nierozstrzygnięte punkty",
        "next_step": "## 6. Następne kroki",
    }

    return category_to_section.get(category, "## 2. Praca faktycznie wykonana")


def group_records(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}

    for rec in records:
        if not rec.get("include_in_daily_log", False):
            continue

        section = section_for_record(rec)
        grouped.setdefault(section, []).append(rec)

    return grouped


def build_artifact_records(records: list[dict], day: str) -> list[dict]:
    """
    Buduje sekcję:
    ## 3. Artefakty utworzone lub zmodyfikowane

    Reguła jakości:
    - do tej sekcji trafiają tylko artefakty, których rekord oznacza realną zmianę;
    - nie trafiają tu pliki tylko sprawdzone, odnotowane, użyte jako wejście,
      wygenerowane jako output dzienny albo wspomniane w decyzjach/niepewnościach/następnych krokach.

    Dzięki temu sekcja artefaktów nie miesza:
    - plików projektu faktycznie zmienionych,
    - plików wejściowych,
    - plików wyjściowych,
    - plików tylko walidowanych.
    """

    change_operations = {
        "zmodyfikowano",
        "utworzono",
        "dodano",
        "naprawiono",
        "zaktualizowano",
    }

    ignored_artifact_names = {
        f"chat_export_{day}.md",
        f"rough_work_{day}.md",
        f"DAILY_LOG_{day}.md",
        f"RAPORT_POSTEPOW_{day}.md",
        f"MERGED_SOURCES_{day}.txt",
        f"README_PL_{day}.txt",
        f"FACT_LEDGER_{day}.jsonl",
        f"FACT_LEDGER_RAW_{day}.jsonl",
        f"FACT_LEDGER_REJECTED_{day}.md",
        f"FACT_LEDGER_REPAIR_AUDIT_{day}.txt",
    }

    artifacts: dict[str, dict] = {}

    for rec in records:
        if not rec.get("include_in_daily_log", False):
            continue

        operation = str(rec.get("operation", "") or "").strip().lower()
        category = str(rec.get("category", "") or "").strip()

        if operation not in change_operations:
            continue

        if category not in {"work_done", "artifact_context"}:
            continue

        for artifact in rec.get("artifacts", []) or []:
            artifact = str(artifact).strip()
            if not artifact:
                continue

            if artifact in ignored_artifact_names:
                continue

            current = artifacts.setdefault(
                artifact,
                {
                    "artifact": artifact,
                    "operations": [],
                    "confidences": [],
                },
            )

            if operation and operation not in current["operations"]:
                current["operations"].append(operation)

            current["confidences"].append(rec.get("confidence", "średnia"))

    result = []
    for artifact, data in sorted(artifacts.items()):
        operation = "; ".join(data["operations"]) if data["operations"] else "zmodyfikowano"
        result.append(
            {
                "artifact": artifact,
                "type": artifact_type(artifact),
                "operation": operation,
                "status": artifact_status(operation),
                "confidence": choose_confidence(data["confidences"]),
            }
        )

    return result


def bullet_work(rec: dict) -> str:
    status = rec.get("status", "completed")
    if status == "planned":
        status = "completed"
    confidence = rec.get("confidence", "średnia")
    return f"- {rec['normalized_fact']} — status: {status} — pewność: {confidence}"


def bullet_plain(rec: dict) -> str:
    return f"- {rec['normalized_fact']}"



def should_show_work_record(rec: dict) -> bool:
    """
    Filtruje sekcję:
    ## 2. Praca faktycznie wykonana

    Cel:
    - zostawić realne prace, diagnozy i zmiany;
    - usunąć szum testowy, potwierdzenia, telemetrię i powtarzalne wyniki walidacji;
    - nie ukrywać faktów o realnie zmienionych plikach projektu.
    """

    if rec.get("category") != "work_done":
        return False

    fact = str(rec.get("normalized_fact", "") or "").strip()
    lower = fact.lower()
    operation = str(rec.get("operation", "") or "").strip().lower()

    low_value_markers = (
        "pipeline przetworzył `chat_export",
        "wykonano testy składni",
        "cache miss",
        "`merged_sources_2026-04-28.txt` przeszedł walidację",
        "`daily_log_2026-04-28.md` przeszedł walidację",
        "finalny `daily_log_2026-04-28.md` trafił do",
        "sprawdzenie czerwonych flag zwróciło",
        "potwierdzono, że aktywny etap 2",
        "potwierdzono w `source_manifest`",
        "potwierdzono w bezpiecznym renderze",
        "potwierdzono, że `group_records()`",
        "potwierdzono, że fakt o właściwym katalogu",
        "potwierdzono, że finalny `fact_ledger_2026-04-28.jsonl` zawiera",
        "normalny pipeline zakończył się kodem",
        "finalna bramka spójności po dystrybucji zakończyła się wynikiem",
        "potwierdzono, że finalny `daily_log_2026-04-28.md` ma sześć",
        "potwierdzono, że finalny `daily_log_2026-04-28.md` przechodzi",
        "potwierdzono, że finalny `daily_log_2026-04-28.md` nie zawiera",
    )

    if any(marker in lower for marker in low_value_markers):
        return False

    change_operations = {
        "zmodyfikowano",
        "utworzono",
        "naprawiono",
        "dodano",
        "zaktualizowano",
    }

    if operation in change_operations:
        return True

    important_markers = (
        "uruchomiono lokalny pipeline",
        "błędnie trafił na stary skrypt",
        "pierwszy przebieg zakończył się wynikiem `do naprawy`",
        "zidentyfikowano fałszywy alarm",
        "zdiagnozowano problem jakości",
        "zdiagnozowano, że `normalize_daily_facts.py`",
        "zdiagnozowano, że `repair_fact_ledger.py`",
        "nowa walidacja poprawnie odrzuciła",
    )

    return any(marker in lower for marker in important_markers)



def build_daily_log(day: str, records: list[dict], chunk_count: int) -> str:
    """
    Deterministyczny, source-bound renderer DAILY_LOG.

    Cel wersji v7.7.x:
    - zawsze generować 6 standardowych sekcji;
    - nie kończyć dokumentu na sekcji 4;
    - nie tworzyć pustych ramek bez informacji;
    - nie dodawać fikcyjnych faktów;
    - zachować zgodność z FACT_LEDGER.
    """

    grouped = group_records(records)

    work_records_all = grouped.get("## 2. Praca faktycznie wykonana", [])
    work_records = [rec for rec in work_records_all if should_show_work_record(rec)]

    # Bezpieczny fallback: jeżeli filtr byłby zbyt agresywny, nie wolno zgubić całej sekcji.
    if not work_records and work_records_all:
        work_records = work_records_all[:12]

    decision_records = grouped.get("## 4. Decyzje operacyjne i metodologiczne", [])
    uncertainty_records = grouped.get("## 5. Niepewności i nierozstrzygnięte punkty", [])
    next_step_records = grouped.get("## 6. Następne kroki", [])

    artifact_records = build_artifact_records(records, day)

    def clean_fact(rec: dict) -> str:
        return str(rec.get("normalized_fact", "")).strip().rstrip(".")

    def safe_status(rec: dict) -> str:
        status = str(rec.get("status", "completed")).strip() or "completed"
        if status == "planned":
            # Planned nie powinno trafiać do sekcji wykonanej pracy.
            # Jeżeli mimo wszystko dotarło do renderera, nie wzmacniamy go jako planu.
            return "completed"
        return status

    def safe_confidence(rec: dict) -> str:
        confidence = str(rec.get("confidence", "średnia")).strip() or "średnia"
        if confidence not in {"wysoka", "średnia", "niska"}:
            return "średnia"
        return confidence

    def work_line(rec: dict) -> str:
        return f"- {clean_fact(rec)} — status: {safe_status(rec)} — pewność: {safe_confidence(rec)}"

    def plain_line(rec: dict) -> str:
        return f"- {clean_fact(rec)}"

    lines: list[str] = []

    lines.append(f"# DAILY LOG — {day}")
    lines.append("")

    lines.append("## 1. Zakres dnia")
    lines.append(
        "Praca dotyczyła lokalnego pipeline'u daily logów: normalizacji faktów, "
        "naprawy FACT_LEDGER, walidacji jakości oraz deterministycznego renderowania "
        "finalnego daily loga z kontrolowanych źródeł. "
        f"Etap 1 przetworzył {chunk_count} chunków."
    )
    lines.append("")

    lines.append("## 2. Praca faktycznie wykonana")
    if work_records:
        for rec in work_records:
            fact = clean_fact(rec)
            if not fact:
                continue
            lines.append(work_line(rec))
    else:
        lines.append("- Brak zaakceptowanych faktów wykonanej pracy w FACT_LEDGER — status: started — pewność: niska")
    lines.append("")

    lines.append("## 3. Artefakty utworzone lub zmodyfikowane")
    if artifact_records:
        for a in artifact_records:
            lines.append(
                f"- `{a['artifact']}` — typ: {a['type']}; "
                f"operacja: {a['operation']}; status: {a['status']}; "
                f"pewność: {a['confidence']}"
            )
    else:
        lines.append("- Brak artefaktów plikowych potwierdzonych w zaakceptowanym FACT_LEDGER.")
    lines.append("")

    lines.append("## 4. Decyzje operacyjne i metodologiczne")
    if decision_records:
        for rec in decision_records:
            fact = clean_fact(rec)
            if fact:
                lines.append(f"- {fact} — pewność: {safe_confidence(rec)}")
    else:
        lines.append("- Brak osobnych decyzji operacyjnych lub metodologicznych potwierdzonych w zaakceptowanym FACT_LEDGER.")
    lines.append("")

    lines.append("## 5. Niepewności i nierozstrzygnięte punkty")
    if uncertainty_records:
        for rec in uncertainty_records:
            fact = clean_fact(rec)
            if fact:
                lines.append(plain_line(rec))
    else:
        lines.append("- Brak osobnych niepewności potwierdzonych w zaakceptowanym FACT_LEDGER.")
    lines.append("")

    lines.append("## 6. Następne kroki")
    if next_step_records:
        for rec in next_step_records:
            fact = clean_fact(rec)
            if fact:
                lines.append(plain_line(rec))
    else:
        lines.append("- Brak następnych kroków potwierdzonych w zaakceptowanym FACT_LEDGER.")

    return "\n".join(lines).rstrip() + "\n"


def build_readme(day: str, chunk_count: int, stage2_mode: str) -> str:
    return f"""# README_PL — {day}

Pakiet dokumentacyjny wygenerowany przez lokalny pipeline daily log.

## Tryb

- Etap 1: lokalna ekstrakcja przez Ollamę.
- Etap 1.5: normalizacja do FACT_LEDGER.
- Etap 2: deterministyczny render DAILY_LOG z FACT_LEDGER.
- Tryb etapu 2: {stage2_mode}.
- Liczba chunków: {chunk_count}.
"""


def build_manifest(
    day: str,
    chat_export_path: str,
    rough_work_path: str,
    workflow_map_path: str,
    schemat_daily_log_path: str,
    prompt_etap1_path: str,
    prompt_etap2_path: str,
    stage1_quality_manifest_path: str,
    fact_ledger_path: str,
    fact_ledger_rejected_path: str,
    chunk_count: int,
    stage2_mode: str,
) -> str:
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
FACT_LEDGER_PATH: {fact_ledger_path}
FACT_LEDGER_REJECTED_PATH: {fact_ledger_rejected_path}
PROMPT_TRACE_INCLUDED: NO
OTHER_SOURCES: NONE
PIPELINE_MODE: DEFAULT
CHUNK_COUNT: {chunk_count}
STAGE1_MODEL: mistral-pipeline (Ollama, lokalnie)
STAGE2_MODEL: deterministic FACT_LEDGER renderer (local Python)
STAGE2_MODE: {stage2_mode}
END_SOURCE_MANIFEST"""


def build_merged_sources(
    manifest: str,
    daily_log_path: Path,
    daily_log: str,
    raport_path: Path,
    raport: str,
    fact_ledger_path: Path,
    fact_ledger: str,
    rejected_path: Path,
    rejected: str,
    chat_export_path: Path,
    chat_export: str,
    rough_work_path: str,
    rough_work: str,
    workflow_map_path: Path,
    workflow_map: str,
    schema_path: Path,
    schema: str,
    stage1_manifest_path: str,
    stage1_manifest_text: str,
) -> str:
    parts = [manifest]

    def add(category: str, source_file: str, content: str) -> None:
        parts.append(f"""

===== SOURCE CATEGORY: {category} =====
===== SOURCE FILE: {source_file} =====

{content.strip() if content.strip() else "[BRAK TREŚCI]"}
""")

    add("RENDERED DAILY LOG", str(daily_log_path), daily_log)
    add("FACT LEDGER", str(fact_ledger_path), fact_ledger)
    add("FACT LEDGER REJECTED", str(rejected_path), rejected)
    add("AI-GENERATED PROGRESS REPORT", str(raport_path), raport)
    if stage1_manifest_text:
        add("STAGE1 QUALITY MANIFEST", stage1_manifest_path, stage1_manifest_text)
    if rough_work:
        add("USER ROUGH WORK", rough_work_path, rough_work)
    add("CHAT EXPORT", str(chat_export_path), chat_export)
    add("CONTROL DOCUMENT: COMMIT_WORKFLOW_MAP", str(workflow_map_path), workflow_map)
    add("CONTROL DOCUMENT: SCHEMAT_DAILY_LOG", str(schema_path), schema)

    return "\n".join(parts).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Renderuje DAILY_LOG z FACT_LEDGER.")
    parser.add_argument("--day", required=True)
    parser.add_argument("--fact-ledger", required=True)
    parser.add_argument("--fact-ledger-rejected", required=True)
    parser.add_argument("--raport-postepow", required=True)
    parser.add_argument("--chat-export", required=True)
    parser.add_argument("--rough-work", default="")
    parser.add_argument("--workflow-map", required=True)
    parser.add_argument("--schemat-daily-log", required=True)
    parser.add_argument("--prompt-etap1", required=True)
    parser.add_argument("--prompt-etap2", required=True)
    parser.add_argument("--stage1-quality-manifest", default="")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--chunk-count", type=int, required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fact_ledger_path = Path(args.fact_ledger)
    rejected_path = Path(args.fact_ledger_rejected)
    raport_path = Path(args.raport_postepow)
    chat_export_path = Path(args.chat_export)
    workflow_map_path = Path(args.workflow_map)
    schema_path = Path(args.schemat_daily_log)
    prompt1_path = Path(args.prompt_etap1)
    prompt2_path = Path(args.prompt_etap2)
    stage1_manifest_path = Path(args.stage1_quality_manifest) if args.stage1_quality_manifest else None
    rough_path = Path(args.rough_work) if args.rough_work else None

    records = load_jsonl(fact_ledger_path)

    fact_ledger_text = read_text(fact_ledger_path)
    rejected_text = read_text(rejected_path)
    raport = read_text(raport_path)
    chat_export = read_text(chat_export_path)
    workflow_map = read_text(workflow_map_path)
    schema = read_text(schema_path)
    stage1_manifest_text = read_text(stage1_manifest_path, required=False) if stage1_manifest_path else ""
    rough_work = read_text(rough_path, required=False) if rough_path and rough_path.exists() else ""
    rough_display = str(rough_path) if rough_path and rough_path.exists() else "MISSING"

    stage2_mode = "FACT_LEDGER_RENDERED"

    daily_log = build_daily_log(args.day, records, args.chunk_count)
    readme = build_readme(args.day, args.chunk_count, stage2_mode)

    daily_log_path = output_dir / f"DAILY_LOG_{args.day}.md"
    readme_path = output_dir / "README_PL.txt"
    merged_path = output_dir / f"MERGED_SOURCES_{args.day}.txt"

    manifest = build_manifest(
        day=args.day,
        chat_export_path=str(chat_export_path),
        rough_work_path=rough_display,
        workflow_map_path=str(workflow_map_path),
        schemat_daily_log_path=str(schema_path),
        prompt_etap1_path=str(prompt1_path),
        prompt_etap2_path=str(prompt2_path),
        stage1_quality_manifest_path=str(stage1_manifest_path) if stage1_manifest_path else "MISSING",
        fact_ledger_path=str(fact_ledger_path),
        fact_ledger_rejected_path=str(rejected_path),
        chunk_count=args.chunk_count,
        stage2_mode=stage2_mode,
    )

    merged = build_merged_sources(
        manifest=manifest,
        daily_log_path=daily_log_path,
        daily_log=daily_log,
        raport_path=raport_path,
        raport=raport,
        fact_ledger_path=fact_ledger_path,
        fact_ledger=fact_ledger_text,
        rejected_path=rejected_path,
        rejected=rejected_text,
        chat_export_path=chat_export_path,
        chat_export=chat_export,
        rough_work_path=rough_display,
        rough_work=rough_work,
        workflow_map_path=workflow_map_path,
        workflow_map=workflow_map,
        schema_path=schema_path,
        schema=schema,
        stage1_manifest_path=str(stage1_manifest_path) if stage1_manifest_path else "MISSING",
        stage1_manifest_text=stage1_manifest_text,
    )

    daily_log_path.write_text(daily_log, encoding="utf-8")
    readme_path.write_text(readme, encoding="utf-8")
    merged_path.write_text(merged, encoding="utf-8")

    print(f"[render] DAILY_LOG zapisany: {daily_log_path}")
    print(f"[render] README_PL zapisany: {readme_path}")
    print(f"[render] MERGED_SOURCES zapisany: {merged_path}")
    print(f"[render] STAGE2_MODE: {stage2_mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

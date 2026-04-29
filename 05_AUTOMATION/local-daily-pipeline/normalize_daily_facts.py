#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
normalize_daily_facts.py — etap 1.5 pipeline'u daily log.

Cel:
- zamienić RAPORT_POSTEPOW + optional rough_work na kanoniczny FACT_LEDGER,
- odrzucić fakty z innych dat,
- rozdzielić fakty wykonane, niepewności, następne kroki i odrzucone fragmenty,
- ograniczyć swobodę etapu renderowania DAILY_LOG.

Wyjścia:
- FACT_LEDGER_YYYY-MM-DD.jsonl
- FACT_LEDGER_REJECTED_YYYY-MM-DD.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ALLOWED_WORK_STATUSES = {
    "started",
    "in progress",
    "partially completed",
    "tested",
    "completed",
}

PLAN_HINTS = (
    "trzeba ",
    "należy ",
    "powinno ",
    "plan ",
    "następny krok",
    "kolejny krok",
)

NOISE_PATTERNS = [
    r"\bPobierz,\s*podmień\b",
    r"\buruchom ponownie\b",
    r"\bRozumiem i zgadzam się\b",
    r"\bIt seems like\b",
    r"\bHere's a general outline\b",
    r"\bFirst,\s+make sure\b",
    r"^To jest fragment\s+\d+\s+z\s+\d+",
]

FILE_RE = re.compile(
    r"`([^`]+\.(?:py|sh|txt|md|json|jsonl|yml|yaml|csv|docx|pdf))`|"
    r"(?<![\w./-])([A-Za-z0-9_./-]+\.(?:py|sh|txt|md|json|jsonl|yml|yaml|csv|docx|pdf))(?![\w./-])",
    flags=re.IGNORECASE,
)


def read_text(path: Path | None, required: bool) -> str:
    if path is None:
        return ""
    if not path.exists():
        if required:
            print(f"[ERROR] Brak pliku: {path}", file=sys.stderr)
            sys.exit(1)
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def strip_bullet(line: str) -> str:
    return re.sub(r"^\s*[-*]\s*", "", line.strip()).strip()


def extract_status(line: str, default: str = "completed") -> str:
    m = re.search(
        r"status:\s*(planned|started|in progress|partially completed|tested|completed|unknown)",
        line,
        flags=re.IGNORECASE,
    )
    if not m:
        return default
    status = m.group(1).lower()
    if status == "unknown":
        return "started"
    return status


def extract_confidence(line: str, default: str = "średnia") -> str:
    m = re.search(r"pewność:\s*(wysoka|średnia|niska)", line, flags=re.IGNORECASE)
    return m.group(1).lower() if m else default



def remove_status_metadata(text: str) -> str:
    text = re.sub(
        r"\s*—\s*status:\s*(planned|started|in progress|partially completed|tested|completed|unknown)\s*—\s*pewność:\s*(wysoka|średnia|niska)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s*\(status:\s*[^)]*\)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bstatus:\s*(planned|started|in progress|partially completed|tested|completed|unknown)\b[,;:]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s*—\s*pewność:\s*(wysoka|średnia|niska)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", text).strip(" .,-")


def extract_artifacts(text: str) -> list[str]:
    found: list[str] = []
    for match in FILE_RE.finditer(text):
        raw = match.group(1) or match.group(2)
        if not raw:
            continue
        raw = raw.strip("`'\".,;:()[]{}")
        if raw and raw not in found:
            found.append(raw)
    return found


def infer_operation(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ["zmieniono", "poprawiono", "poprawka", "naprawiono", "zaktualizowano"]):
        return "zmodyfikowano"
    if any(w in lower for w in ["dodano", "utworzono", "stworzono", "wygenerowano"]):
        return "utworzono"
    if any(w in lower for w in ["sprawdzono", "walidacja", "testy składni", "przetestowano"]):
        return "sprawdzono"
    if any(w in lower for w in ["uruchomiono", "uruchomienie"]):
        return "uruchomiono"
    if any(w in lower for w in ["usunięto", "usunieto"]):
        return "usunięto"
    return "odnotowano"


def contains_noise(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in NOISE_PATTERNS)


def explicit_dates(text: str) -> list[str]:
    return re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)


def has_other_day(text: str, day: str) -> bool:
    return any(date != day for date in explicit_dates(text))



def is_diagnostic_status_context(text: str) -> bool:
    lower = text.lower()
    diagnostic_hints = (
        "wykrył",
        "wykryto",
        "test strict gate",
        "strict gate",
        "brak / literówka",
        "literówka wymaganego nagłówka",
        "placement/commit",
        "metadata placement",
        "metadane placement",
    )
    return "status: planned" in lower and any(hint in lower for hint in diagnostic_hints)


def is_plan(text: str) -> bool:
    lower = text.lower()

    # "status: planned" może być treścią błędu diagnostycznego,
    # a nie planem wykonania pracy.
    if is_diagnostic_status_context(text):
        return False

    return any(hint in lower for hint in PLAN_HINTS)


def iter_bullets(text: str) -> list[tuple[int, str, str]]:
    result: list[tuple[int, str, str]] = []
    current_section = ""
    for line_no, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if stripped.startswith("## "):
            current_section = stripped
            continue
        if stripped.startswith("- "):
            result.append((line_no, current_section, stripped))
    return result



def is_stage2_mode_telemetry(text: str) -> bool:
    """
    Odrzuca tylko telemetrię przebiegu, np. STAGE2_MODE: MODEL_OUTPUT.
    Nie odrzuca zwykłego opisu zmiany skryptu zawierającego samo słowo STAGE2_MODE.
    """
    return "STAGE2_MODE:" in text


def is_self_invalidating_context(text: str) -> bool:
    lower = text.lower()
    patterns = (
        "wymaga jeszcze ręcznego przeglądu",
        "może nie zawierać pełnego opisu",
        "nie jest finalnym daily logiem",
        "do ręcznej naprawy",
        "brak informacji o dokonanych zmianach",
    )
    return any(pattern in lower for pattern in patterns)


def is_decision_like(text: str) -> bool:
    """
    Rozpoznaje fakty, które powinny trafić do sekcji:
    ## 4. Decyzje operacyjne i metodologiczne

    Nie tworzy nowych faktów. Tylko przekierowuje już zaakceptowane punkty.
    """
    lower = text.lower()

    decision_markers = (
        "ustalono, że",
        "ustalono ",
        "zdecydowano",
        "przyjęto",
        "wybrano",
        "uznano",
        "właściwy katalog uruchomieniowy",
    )

    return any(marker in lower for marker in decision_markers)


def classify_bullet(raw: str, section: str, source_name: str, day: str) -> tuple[str, bool, str]:
    """
    Zwraca: category, include_in_daily_log, rejection_reason.
    """
    clean = strip_bullet(raw)
    section_lower = section.lower()

    if contains_noise(clean):
        return "rejected", False, "Fragment wygląda jak instrukcja rozmowna, reakcja konwersacyjna albo poradnik."

    if has_other_day(clean, day):
        return "rejected", False, f"Fragment zawiera datę inną niż dzień przetwarzania: {day}."

    if is_stage2_mode_telemetry(clean):
        return "rejected", False, "Fragment zawiera telemetrię STAGE2_MODE; tryb etapu 2 wolno brać tylko z SOURCE_MANIFEST."

    if is_self_invalidating_context(clean):
        return "rejected", False, "Fragment samounieważnia finalny DAILY_LOG albo wymaga ręcznej naprawy."

    if "niepewno" in section_lower or "nierozstrzyg" in section_lower:
        return "uncertainty", True, ""

    # Tylko sekcja następnych kroków ma pierwszeństwo jako next_step.
    if "następne kroki" in section_lower or "next steps" in section_lower:
        return "next_step", True, ""

    if is_decision_like(clean):
        return "decision", True, ""

    # Diagnostyczne zdanie zawierające np. "status: planned" nie jest planem.
    if is_diagnostic_status_context(clean):
        return "work_done", True, ""

    if is_plan(clean):
        return "next_step", True, ""

    # rough_work opisuje ręcznie potwierdzone fakty bieżącej pracy,
    # więc domyślnie trafia do pracy wykonanej, chyba że wcześniej odrzucono go
    # jako inną datę, noise albo następny krok.
    if source_name == "rough_work":
        return "work_done", True, ""

    if "artefakt" in section_lower:
        return "artifact_context", True, ""

    status = extract_status(clean, default="completed")
    if status in ALLOWED_WORK_STATUSES:
        return "work_done", True, ""

    return "uncertainty", True, ""


def canonicalize_fact(text: str) -> str:
    text = strip_bullet(text)
    text = remove_status_metadata(text)

    replacements = [
        (r"^Fakt:\s*", ""),
        (r"^Claude\s+zmienił\b", "Zmieniono"),
        (r"^aleks\s+usunął\b", "Usunięto"),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    if text:
        text = text[:1].upper() + text[1:]
    return text.strip()


def record_id(prefix: str, index: int) -> str:
    return f"{prefix}{index:03d}"


def build_records(day: str, raport: str, rough_work: str) -> tuple[list[dict], list[dict]]:
    accepted: list[dict] = []
    rejected: list[dict] = []
    seen: set[str] = set()

    sources = [("RAPORT_POSTEPOW", raport, "raport")]
    if rough_work.strip():
        sources.insert(0, ("ROUGH_WORK", rough_work, "rough_work"))

    accepted_i = 1
    rejected_i = 1
    rough_exists = bool(rough_work.strip())

    for source_label, text, source_name in sources:
        for line_no, section, raw in iter_bullets(text):
            normalized = canonicalize_fact(raw)
            if not normalized:
                continue

            category, include, reason = classify_bullet(raw, section, source_name, day)

            # Jeżeli istnieje rough_work, to on jest źródłem priorytetowym dla finalnego DAILY_LOG.
            # RAPORT_POSTEPOW zostaje w pakiecie audytowym, ale nie powinien automatycznie zasilać finalnego loga,
            # bo zawiera streszczenia historyczne, stare testy i szum z poprzednich przebiegów.
            if rough_exists and source_name == "raport" and category != "rejected":
                category = "rejected"
                include = False
                reason = "Pominięto fakt z RAPORT_POSTEPOW, ponieważ istnieje rough_work jako źródło priorytetowe dla finalnego DAILY_LOG."

            key = re.sub(r"\s+", " ", normalized.lower())

            base = {
                "day": day,
                "source": source_label,
                "source_line": line_no,
                "source_section": section,
                "raw_evidence": strip_bullet(raw),
                "normalized_fact": normalized,
                "category": category,
                "artifacts": extract_artifacts(normalized),
                "operation": infer_operation(normalized),
                "status": extract_status(raw, default="completed") if category == "work_done" else ("planned" if category == "next_step" else "uncertain"),
                "confidence": extract_confidence(raw, default="wysoka" if source_name == "rough_work" else "średnia"),
                "include_in_daily_log": include,
                "daily_log_section": "",
                "rejection_reason": reason,
            }

            if category == "rejected" or not include:
                base["id"] = record_id("R", rejected_i)
                rejected_i += 1
                rejected.append(base)
                continue

            if key in seen:
                continue
            seen.add(key)

            if category == "work_done":
                base["daily_log_section"] = "## 2. Praca faktycznie wykonana"
                if base["status"] not in ALLOWED_WORK_STATUSES:
                    base["status"] = "completed"
            elif category == "next_step":
                base["daily_log_section"] = "## 6. Następne kroki"
            elif category == "decision":
                base["daily_log_section"] = "## 4. Decyzje operacyjne i metodologiczne"
            elif category == "uncertainty":
                base["daily_log_section"] = "## 5. Niepewności i nierozstrzygnięte punkty"
            elif category == "artifact_context":
                base["daily_log_section"] = "## 3. Artefakty utworzone lub zmodyfikowane"

            base["id"] = record_id("F", accepted_i)
            accepted_i += 1
            accepted.append(base)

    return accepted, rejected


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_rejected_md(path: Path, day: str, rejected: list[dict]) -> None:
    lines = [
        f"# FACT_LEDGER_REJECTED — {day}",
        "",
        "Ten plik zawiera fragmenty odrzucone przez warstwę normalizacji faktów.",
        "",
    ]

    if not rejected:
        lines.append("- Brak odrzuconych fragmentów.")
    else:
        for item in rejected:
            lines.extend([
                f"## {item['id']}",
                "",
                f"- Źródło: {item['source']}:{item['source_line']}",
                f"- Powód odrzucenia: {item['rejection_reason']}",
                f"- Fragment: {item['raw_evidence']}",
                "",
            ])

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalizuje RAPORT_POSTEPOW + rough_work do FACT_LEDGER.")
    parser.add_argument("--day", required=True)
    parser.add_argument("--raport-postepow", required=True)
    parser.add_argument("--rough-work", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--rejected-output", required=True)
    args = parser.parse_args()

    raport = read_text(Path(args.raport_postepow), required=True)
    rough = read_text(Path(args.rough_work), required=False) if args.rough_work else ""

    accepted, rejected = build_records(args.day, raport, rough)

    if not accepted:
        print("[ERROR] FACT_LEDGER nie zawiera żadnych zaakceptowanych faktów.", file=sys.stderr)
        return 1

    output = Path(args.output)
    rejected_output = Path(args.rejected_output)

    write_jsonl(output, accepted)
    write_rejected_md(rejected_output, args.day, rejected)

    print(f"[facts] FACT_LEDGER zapisany: {output}")
    print(f"[facts] Zaakceptowane fakty: {len(accepted)}")
    print(f"[facts] Odrzucone fragmenty: {len(rejected)}")
    print(f"[facts] Rejected ledger zapisany: {rejected_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

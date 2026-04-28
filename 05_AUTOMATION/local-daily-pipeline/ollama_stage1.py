#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Etap 1 pipeline'u dziennego przez Ollama API — v7.4.1: twarda bramka formatu ekstrakcji + prompt z pliku + cache + raw audit."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

OLLAMA_DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "mistral-pipeline"
REQUEST_TIMEOUT = 1800
STAGE1_CONTRACT_VERSION = "stage1_v7_4_1_source_bound_extraction_format_gate_prompt_file_cache_audit_2026-04-27"

PARTIAL_REPORT_BAD_PATTERNS = [
    r"To jest fragment\s+\d+\s+z\s+\d+\s+całego pliku chat_export",
    r"Przetwarzaj tylko to, co jest w tym fragmencie",
    r"Nie uzupełniaj brakujących części",
    r"===\s*INSTRUKCJA WYKONANIA",
    r"===\s*COMMIT_WORKFLOW_MAP",
    r"===\s*SCHEMAT_DAILY_LOG",
    r"===\s*CHAT_EXPORT",
    r"^\s*\[Here is the content[^\]]*\]\s*$",
]

# Wzorce poradnikowe są ostrzeżeniami jakości.
# Twarda bramka formatu v7.4.1 osobno klasyfikuje odpowiedzi bez wymaganego nagłówka jako failure.
PARTIAL_REPORT_WARNING_PATTERNS = [
    r"\bIt seems like\b",
    r"\bIt looks like\b",
    r"\bHere's a general outline\b",
    r"\bgeneral outline of the steps\b",
    r"\bHere(?:'s| is) a summary\b",
    r"\bFirst,\s+make sure\b",
    r"\bNext,\s+you(?:'ll| will)\s+need\b",
    r"\bFinally,\s+once\b",
]


def partial_report_quality_failures(text: str) -> list[str]:
    failures: list[str] = []
    stripped = text.strip()
    if not stripped.startswith("# RAPORT POSTĘPÓW"):
        failures.append("odpowiedź etapu 1 nie zaczyna się od wymaganego nagłówka '# RAPORT POSTĘPÓW'")
    if len(text.strip()) < 120:
        failures.append("odpowiedź etapu 1 jest bardzo krótka")
    for pattern in PARTIAL_REPORT_BAD_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            failures.append(f"przeciek instrukcji albo atrapa: {pattern}")
    return failures


def partial_report_warnings(text: str) -> list[str]:
    warnings: list[str] = []
    for pattern in PARTIAL_REPORT_WARNING_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            warnings.append(f"możliwa odpowiedź poradnikowa, sprawdź ręcznie: {pattern}")
    return warnings


def build_invalid_partial_report(day: str, chunk_index: int, chunk_count: int, failures: list[str]) -> str:
    reasons = "\n".join(f"- {reason}" for reason in failures)
    return f"""# RAPORT POSTĘPÓW — {day}

## Status fragmentu

Fragment {chunk_index} z {chunk_count} nie przeszedł bramki jakości etapu 1.

## Niepewności i nierozstrzygnięte punkty

Nie propagowano surowej odpowiedzi modelu do raportu postępów, ponieważ wykryto problem jakościowy:

{reasons}

Wymagany jest ręczny przegląd źródła albo ponowne uruchomienie etapu 1 po poprawie promptu.
"""


def build_advisory_quarantine_partial_report(
    day: str,
    chunk_index: int,
    chunk_count: int,
    warnings: list[str],
    raw_response_path: Path,
) -> str:
    reasons = "\n".join(f"- {warning}" for warning in warnings)
    return f"""# RAPORT POSTĘPÓW — {day}

## Status fragmentu

Fragment {chunk_index} z {chunk_count} został skierowany do kwarantanny jakości etapu 1.

## Powód

Model zwrócił odpowiedź wyglądającą jak poradnik albo ogólna odpowiedź, a nie czystą ekstrakcję faktów z fragmentu rozmowy. Żeby nie skazić scalonego `RAPORT_POSTEPOW`, pipeline nie propaguje tej odpowiedzi do raportu.

## Ostrzeżenia jakości

{reasons}

## Surowa odpowiedź modelu

Surowa odpowiedź została zapisana do ręcznej kontroli:

`{raw_response_path}`

## Niepewności i nierozstrzygnięte punkty

- Ten fragment wymaga ręcznej rekonstrukcji albo ponownego uruchomienia po poprawie promptu etapu 1.
- Nie należy traktować tego fragmentu jako poprawnie zrekonstruowanego raportu postępów.
"""
def file_exists_or_warn(path: str, label: str) -> None:
    if path and not Path(path).exists():
        print(f"[WARN] Plik zadeklarowany, ale nie istnieje: {label} -> {path}", file=sys.stderr)


def build_prompt(chunk_text: str, chunk_index: int, chunk_count: int, day: str, prompt_etap1_text: str) -> str:
    external_contract = prompt_etap1_text.strip()
    return f"""Jesteś etapem 1 lokalnego pipeline'u dziennego.

TWOJE ZADANIE:
Wykonujesz WYŁĄCZNIE źródłowo kontrolowaną ekstrakcję faktów roboczych z jednego fragmentu rozmowy.
Nie jesteś doradcą.
Nie jesteś asystentem poradnikowym.
Nie tworzysz finalnego daily loga.
Nie wyjaśniasz użytkownikowi, co powinien zrobić.
Nie piszesz odpowiedzi typu „It seems like...”.

Dzień: {day}
Fragment: {chunk_index}/{chunk_count}

KONTRAKT Z PLIKU --prompt-etap1:
<<<PROMPT_ETAP1
{external_contract}
PROMPT_ETAP1>>>

TWARDY KONTRAKT V7.4.1:
- Użyj wyłącznie treści z sekcji FRAGMENT ROZMOWY.
- Ekstrahuj tylko fakty, decyzje, artefakty, testy, błędy, ustalenia i plany jawnie obecne w źródle.
- Nie przepisuj instrukcji technicznych jako wykonanych faktów.
- Nie zamieniaj poleceń użytkownika na wykonane działania.
- Nie zgaduj brakujących działań, plików, lokalizacji ani wyników.
- Nie wymyślaj nazw folderów, wersji, commitów ani statusów.
- Jeżeli coś jest planem, oznacz to jako plan, nie jako wykonanie.
- Jeżeli fakt jest niepewny, oznacz pewność jako niską albo średnią.
- Jeżeli w fragmencie nie ma faktów roboczych, wpisz to jawnie w sekcji niepewności.
- Pisz po polsku, krótko, technicznie i operacyjnie.

ZAKAZANE TRYBY ODPOWIEDZI:
- poradnik,
- instrukcja krok po kroku dla użytkownika,
- ogólne streszczenie,
- komentarz typu „wygląda na to, że...”,
- rekomendacje,
- spekulacje,
- dopowiadanie kontekstu spoza fragmentu.

ZAKAZANE FRAZY I KONSTRUKCJE:
- It seems like
- It looks like
- Here's a general outline
- First, make sure
- Next, you'll need
- Finally
- powinieneś
- możesz teraz
- ogólnie rzecz biorąc

FORMAT WYJŚCIA:
Odpowiedź MUSI zacząć się dokładnie od poniższej linii, bez żadnego tekstu przed nią:
# RAPORT POSTĘPÓW — {day}

Nie wolno dodać wstępu, komentarza, wyjaśnienia ani zdania po angielsku przed nagłówkiem.
Jeżeli pierwsze słowa odpowiedzi miałyby brzmieć „It seems like”, usuń ten komentarz i przejdź od razu do raportu.

# RAPORT POSTĘPÓW — {day}

## Fakty z fragmentu
- fakt — status: [planned/started/in progress/partially completed/tested/completed/unknown] — pewność: [wysoka/średnia/niska]

## Artefakty wspomniane w fragmencie
- nazwa artefaktu — typ: [plik/skrypt/folder/dokument/niepewne] — operacja: [utworzono/zmieniono/przeniesiono/sprawdzono/planowano/niepewne] — pewność: [wysoka/średnia/niska]

## Decyzje lub ustalenia
- decyzja/ustalenie — pewność: [wysoka/średnia/niska]

## Niepewności i nierozstrzygnięte punkty
- niepewność albo luka informacyjna

FRAGMENT ROZMOWY:
{chunk_text}
"""



def call_ollama(prompt: str, model: str, ollama_url: str) -> str:
    url = f"{ollama_url}/api/generate"
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0.0, "num_ctx": 8192, "num_predict": 700},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        raise RuntimeError(f"Błąd połączenia z Ollama API: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Nieprawidłowa odpowiedź JSON z Ollama: {e}") from e


def compute_cache_key(chunk_text: str, model: str, prompt_etap1_text: str) -> str:
    h = hashlib.sha256()
    h.update(STAGE1_CONTRACT_VERSION.encode("utf-8"))
    h.update(b"\0")
    h.update(model.encode("utf-8"))
    h.update(b"\0")
    h.update(prompt_etap1_text.encode("utf-8", errors="replace"))
    h.update(b"\0")
    h.update(chunk_text.encode("utf-8", errors="replace"))
    return h.hexdigest()


def cache_paths(cache_dir: Path, cache_key: str) -> tuple[Path, Path, Path]:
    subdir = cache_dir / cache_key[:2]
    return (
        subdir / f"{cache_key}.md",
        subdir / f"{cache_key}.json",
        subdir / f"{cache_key}.raw.txt",
    )


def load_from_cache(cache_dir: Path | None, cache_key: str) -> tuple[str, dict[str, object], str | None] | None:
    if cache_dir is None:
        return None
    report_path, meta_path, raw_path = cache_paths(cache_dir, cache_key)
    if report_path.exists() and report_path.stat().st_size > 0:
        report = report_path.read_text(encoding="utf-8", errors="replace")
        metadata: dict[str, object] = {}
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError:
                metadata = {"cache_metadata_error": "invalid_json"}

        raw_text = None
        if raw_path.exists() and raw_path.stat().st_size > 0:
            raw_text = raw_path.read_text(encoding="utf-8", errors="replace")

        return report, metadata, raw_text
    return None


def save_to_cache(
    cache_dir: Path | None,
    cache_key: str,
    report_text: str,
    metadata: dict[str, object],
    raw_response_text: str | None = None,
) -> None:
    if cache_dir is None:
        return
    report_path, meta_path, raw_path = cache_paths(cache_dir, cache_key)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    if raw_response_text:
        raw_path.write_text(raw_response_text, encoding="utf-8")


def process_chunk(chunk_index: int, chunk_count: int, chunk_dir: Path, partial_dir: Path, day: str, model: str, ollama_url: str, cache_dir: Path | None, audit_dir: Path | None, prompt_etap1_text: str) -> dict[str, object]:
    pad = len(str(chunk_count))
    chunk_path = chunk_dir / f"chunk_{str(chunk_index).zfill(pad)}.md"
    partial_path = partial_dir / f"partial_report_{str(chunk_index).zfill(pad)}.md"
    raw_response_dir = (audit_dir / "raw_stage1_responses") if audit_dir is not None else (partial_dir / "raw_stage1_responses")
    raw_response_path = raw_response_dir / f"raw_stage1_chunk_{str(chunk_index).zfill(pad)}.txt"
    if not chunk_path.exists():
        raise FileNotFoundError(f"Brak pliku chunka: {chunk_path}")
    chunk_text = chunk_path.read_text(encoding="utf-8", errors="replace")
    if not chunk_text.strip():
        empty_report = f"# RAPORT POSTĘPÓW — {day}\n\n## Niepewności i nierozstrzygnięte punkty\n\n- Fragment {chunk_index} z {chunk_count} był pusty.\n"
        partial_path.write_text(empty_report, encoding="utf-8")
        return {
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
            "quality_status": "empty_chunk",
            "warnings": [],
            "failures": ["pusty chunk"],
            "cache": "not_applicable",
            "partial_report_path": str(partial_path),
        }

    cache_key = compute_cache_key(chunk_text, model, prompt_etap1_text)
    cached = load_from_cache(cache_dir, cache_key)
    if cached is not None:
        cached_report, cached_meta, cached_raw_text = cached
        warnings = cached_meta.get("warnings")
        if not isinstance(warnings, list):
            warnings = partial_report_warnings(cached_report)
        failures = cached_meta.get("failures")
        if not isinstance(failures, list):
            failures = partial_report_quality_failures(cached_report)

        quality_status = str(cached_meta.get("quality_status", "cache_hit"))

        raw_cache_status = "not_required"
        if warnings or failures:
            raw_response_dir.mkdir(parents=True, exist_ok=True)
            if cached_raw_text:
                raw_response_path.write_text(cached_raw_text, encoding="utf-8")
                raw_cache_status = "restored_from_cache"
            else:
                raw_response_path.write_text(
                    "[BRAK SUROWEJ ODPOWIEDZI W CACHE]\n"
                    "Ten plik został utworzony diagnostycznie, ponieważ metadata cache wskazuje ostrzeżenia albo błędy, "
                    "ale cache nie zawiera surowej odpowiedzi modelu.\n"
                    "Wymuś ponowne przeliczenie chunka albo użyj wersji kontraktu, która zapisuje .raw.txt w cache.\n",
                    encoding="utf-8",
                )
                raw_cache_status = "missing_in_cache"

        if warnings and quality_status not in {"advisory_quarantined", "invalid_replaced", "advisory_quarantined_from_cache"}:
            cached_report = build_advisory_quarantine_partial_report(
                day=day,
                chunk_index=chunk_index,
                chunk_count=chunk_count,
                warnings=warnings,
                raw_response_path=raw_response_path,
            )
            quality_status = "advisory_quarantined_from_cache"

        partial_path.write_text(cached_report, encoding="utf-8")
        print(f"[etap1] Chunk {chunk_index}/{chunk_count}: CACHE HIT sha256={cache_key[:12]} -> {partial_path}")
        if warnings:
            print(f"[etap1] Chunk {chunk_index}/{chunk_count}: CACHE HIT z ostrzeżeniami jakości: {len(warnings)}", file=sys.stderr)
        if raw_cache_status == "missing_in_cache":
            print(f"[etap1] Chunk {chunk_index}/{chunk_count}: UWAGA — cache nie zawierał surowej odpowiedzi modelu.", file=sys.stderr)

        return {
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
            "cache_key": cache_key,
            "quality_status": quality_status,
            "warnings": warnings,
            "failures": failures,
            "cache": "hit",
            "raw_cache_status": raw_cache_status,
            "partial_report_path": str(partial_path),
            "raw_response_path": str(raw_response_path) if (warnings or failures) else "",
        }

    print(f"[etap1] Chunk {chunk_index}/{chunk_count}: CACHE MISS sha256={cache_key[:12]}")
    prompt = build_prompt(chunk_text, chunk_index, chunk_count, day, prompt_etap1_text)
    print(f"[etap1] Chunk {chunk_index}/{chunk_count}: wysyłanie do Ollama ({model})...")
    t0 = time.time()
    response = call_ollama(prompt, model, ollama_url)
    elapsed = time.time() - t0
    print(f"[etap1] Chunk {chunk_index}/{chunk_count}: odpowiedź po {elapsed:.1f}s, {len(response)} znaków")
    if not response.strip():
        raise RuntimeError(f"Ollama zwróciła pustą odpowiedź dla chunka {chunk_index}")

    warning_messages = partial_report_warnings(response)
    for warning in warning_messages:
        print(f"[etap1] Chunk {chunk_index}/{chunk_count}: OSTRZEŻENIE — {warning}", file=sys.stderr)

    quality_failures = partial_report_quality_failures(response)
    final_report = response
    quality_status = "ok"

    if warning_messages or quality_failures:
        raw_response_dir.mkdir(parents=True, exist_ok=True)
        raw_response_path.write_text(response, encoding="utf-8")

    if warning_messages:
        final_report = build_advisory_quarantine_partial_report(
            day=day,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
            warnings=warning_messages,
            raw_response_path=raw_response_path,
        )
        quality_status = "advisory_quarantined"

    if quality_failures:
        print(f"[etap1] Chunk {chunk_index}/{chunk_count}: UWAGA — odpowiedź nie przeszła bramki technicznej.", file=sys.stderr)
        for failure in quality_failures:
            print(f"[etap1] Powód zastąpienia chunka {chunk_index}: {failure}", file=sys.stderr)
        final_report = build_invalid_partial_report(day, chunk_index, chunk_count, quality_failures)
        quality_status = "invalid_replaced"

    partial_path.write_text(final_report, encoding="utf-8")
    metadata = {
        "cache_key": cache_key,
        "day": day,
        "chunk_index": chunk_index,
        "chunk_count": chunk_count,
        "model": model,
        "contract_version": STAGE1_CONTRACT_VERSION,
        "quality_status": quality_status,
        "warnings": warning_messages,
        "failures": quality_failures,
        "cache": "miss",
        "response_chars": len(response),
        "elapsed_seconds": round(elapsed, 2),
        "partial_report_path": str(partial_path),
        "raw_response_path": str(raw_response_path) if (warning_messages or quality_failures) else "",
    }
    raw_for_cache = response if (warning_messages or quality_failures) else None
    save_to_cache(cache_dir, cache_key, final_report, metadata, raw_response_text=raw_for_cache)
    print(f"[etap1] Chunk {chunk_index}/{chunk_count}: zapisano -> {partial_path}")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Etap 1 pipeline'u dziennego — v7.4.1 źródłowo kontrolowana ekstrakcja + twarda bramka formatu + prompt z pliku + cache + raw audit.")
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--partial-dir", required=True)
    parser.add_argument("--chunk-count", type=int, required=True)
    parser.add_argument("--day", required=True)
    parser.add_argument("--prompt-etap1", required=True)
    parser.add_argument("--workflow-map", required=True)
    parser.add_argument("--schemat-daily-log", required=True)
    parser.add_argument("--rough-work", default="")
    parser.add_argument("--cache-dir", default="")
    parser.add_argument("--audit-dir", default="", help="Trwały katalog audytu etapu 1, np. OUTPUT_DIR/stage1_audit.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=OLLAMA_DEFAULT_URL)
    args = parser.parse_args()

    chunk_dir = Path(args.chunk_dir)
    partial_dir = Path(args.partial_dir)
    partial_dir.mkdir(parents=True, exist_ok=True)

    file_exists_or_warn(args.prompt_etap1, "prompt_etap1")
    file_exists_or_warn(args.workflow_map, "workflow_map")
    file_exists_or_warn(args.schemat_daily_log, "schemat_daily_log")

    prompt_etap1_path = Path(args.prompt_etap1)
    try:
        prompt_etap1_text = prompt_etap1_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"[ERROR] Nie można odczytać prompt_etap1: {e}", file=sys.stderr)
        return 1

    if not prompt_etap1_text.strip():
        print("[ERROR] prompt_etap1 jest pusty; etap 1 wymaga realnego kontraktu ekstrakcji.", file=sys.stderr)
        return 1

    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)

    audit_dir = Path(args.audit_dir) if args.audit_dir else None
    if audit_dir is not None:
        audit_dir.mkdir(parents=True, exist_ok=True)

    if args.rough_work and Path(args.rough_work).exists():
        print("[etap1] rough_work wykryty, ale nie jest dołączany do promptów etapu 1; zostanie użyty w etapie 2.")

    print(f"[etap1] START: {args.chunk_count} chunków, model={args.model}, ollama={args.ollama_url}")
    print("[etap1] Wersja: v7.4.1 source-bound-extraction-format-gate-prompt-file-cache-raw-audit")
    print(f"[etap1] Prompt etapu 1: {prompt_etap1_path}")
    print(f"[etap1] Cache: {cache_dir if cache_dir is not None else 'WYŁĄCZONY'}")

    quality_records: list[dict[str, object]] = []

    for i in range(1, args.chunk_count + 1):
        try:
            record = process_chunk(i, args.chunk_count, chunk_dir, partial_dir, args.day, args.model, args.ollama_url, cache_dir, audit_dir, prompt_etap1_text)
            quality_records.append(record)
        except Exception as e:
            print(f"[ERROR] Chunk {i}/{args.chunk_count} zakończył się błędem: {e}", file=sys.stderr)
            return 1

    warning_count = sum(len(r.get("warnings", [])) for r in quality_records if isinstance(r.get("warnings", []), list))
    failure_count = sum(len(r.get("failures", [])) for r in quality_records if isinstance(r.get("failures", []), list))
    cache_hits = sum(1 for r in quality_records if r.get("cache") == "hit")
    cache_misses = sum(1 for r in quality_records if r.get("cache") == "miss")

    manifest = {
        "stage": "stage1",
        "version": "v7.4.1",
        "contract_version": STAGE1_CONTRACT_VERSION,
        "day": args.day,
        "model": args.model,
        "chunk_count": args.chunk_count,
        "cache_dir": str(cache_dir) if cache_dir is not None else "",
        "audit_dir": str(audit_dir) if audit_dir is not None else "",
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "warning_count": warning_count,
        "failure_count": failure_count,
        "records": quality_records,
    }
    manifest_path = partial_dir / "stage1_quality_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[etap1] Manifest jakości etapu 1 zapisany: {manifest_path}")

    if audit_dir is not None:
        audit_manifest_path = audit_dir / "stage1_quality_manifest.json"
        audit_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[etap1] Manifest jakości etapu 1 zapisany trwale: {audit_manifest_path}")
    if warning_count:
        print(f"[etap1] OSTRZEŻENIA jakości etapu 1: {warning_count} — etap 2 potraktuje wynik jako wymagający kontroli.", file=sys.stderr)

    print(f"[etap1] KONIEC: wszystkie {args.chunk_count} chunki przetworzone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

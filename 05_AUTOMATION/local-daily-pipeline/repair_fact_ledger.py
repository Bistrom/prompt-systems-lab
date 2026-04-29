#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repair FACT_LEDGER jsonl after first-pass normalization.

This script is intentionally deterministic. It merges flattened continuation bullets
into their parent fact and removes command-only facts / command-like artifacts.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

COMMAND_PREFIXES = (
    "bash ", "python ", "python3 ", "git ", "grep ", "sed ", "awk ", "find ",
    "`bash ", "`python ", "`python3 ", "`git ", "`grep ", "`sed ", "`awk ", "`find ",
)

CONTINUATION_PREFIXES = (
    "nie ",
    "używał ", "uzywal ",
    "wykrywał ", "wykrywal ",
    "wzmacniał ", "wzmacnial ",
    "wielodniowego ",
    "statusów ", "statusow ",
    "starych dat ",
    "niekanonicznych ",
    "metadanych ",
)

FILE_RE = re.compile(r"`([^`]+)`")

MUTATING_OPERATIONS = {
    "zmodyfikowano",
    "utworzono",
    "usunięto",
    "skopiowano",
    "przeniesiono",
    "dodano",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def is_command_like(text: str) -> bool:
    lower = text.strip().strip("` ").lower()
    return lower.startswith(COMMAND_PREFIXES)


def is_continuation_fact(text: str) -> bool:
    stripped = text.strip()
    lower = stripped.lower().strip("` ")
    return lower.startswith(CONTINUATION_PREFIXES) or is_command_like(stripped)


def clean_child(text: str) -> str:
    return text.strip().strip(" .")


def append_child(parent: str, child: str) -> str:
    child = clean_child(child)
    if not child:
        return parent
    if parent.rstrip().endswith(":"):
        return parent.rstrip() + " " + child
    return parent.rstrip(" .") + "; " + child


def clean_artifacts(artifacts: list[Any]) -> list[str]:
    cleaned: list[str] = []
    for item in artifacts or []:
        if not isinstance(item, str):
            continue
        value = item.strip().strip("`'\".,;:()[]{}")
        if not value:
            continue
        if is_command_like(value):
            continue
        # A phrase with spaces is almost always a command/sentence, not a project artifact.
        if " " in value and not value.startswith(("/", "./")):
            continue
        if value not in cleaned:
            cleaned.append(value)
    return cleaned


def artifacts_from_text(text: str) -> list[str]:
    found: list[str] = []
    for m in FILE_RE.finditer(text):
        value = m.group(1).strip().strip("`'\".,;:()[]{}")
        if not value or is_command_like(value):
            continue
        if " " in value and not value.startswith(("/", "./")):
            continue
        if re.search(r"\.(py|sh|md|txt|json|jsonl|yml|yaml)$", value) and value not in found:
            found.append(value)
    return found


def merge_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Deterministycznie naprawia FACT_LEDGER po normalizacji.

    Reguła bezpieczeństwa:
    - wolno scalać tylko rekordy z tej samej kategorii,
      tej samej sekcji DAILY_LOG i tej samej sekcji źródłowej;
    - nie wolno doklejać uncertainty do decision;
    - nie wolno doklejać next_step do work_done;
    - nie wolno usuwać zaakceptowanych uncertainty tylko dlatego,
      że wyglądają jak kontynuacja tekstu.
    """

    output: list[dict[str, Any]] = []
    audit: list[str] = []

    current_parent: dict[str, Any] | None = None
    current_parent_open = False

    def same_bucket(parent: dict[str, Any], child: dict[str, Any]) -> bool:
        return (
            str(parent.get("category", "")) == str(child.get("category", ""))
            and str(parent.get("daily_log_section", "")) == str(child.get("daily_log_section", ""))
            and str(parent.get("source_section", "")) == str(child.get("source_section", ""))
        )

    def refresh_artifacts(rec: dict[str, Any]) -> None:
        artifacts = clean_artifacts(rec.get("artifacts", []))

        for art in artifacts_from_text(str(rec.get("normalized_fact", ""))):
            if art not in artifacts:
                artifacts.append(art)

        rec["artifacts"] = artifacts

    for original in records:
        rec = dict(original)
        fact = str(rec.get("normalized_fact", "")).strip()

        if not fact:
            audit.append(f"dropped empty fact: {rec.get('id', '')}")
            continue

        rec["normalized_fact"] = fact
        refresh_artifacts(rec)

        command_like = is_command_like(fact)
        continuation_like = is_continuation_fact(fact)

        if command_like:
            if (
                current_parent is not None
                and current_parent_open
                and same_bucket(current_parent, rec)
            ):
                current_parent["normalized_fact"] = append_child(
                    str(current_parent.get("normalized_fact", "")),
                    fact,
                )
                refresh_artifacts(current_parent)
                audit.append(f"merged command-like fact into compatible parent: {fact}")
            else:
                audit.append(f"dropped command-only fact: {fact}")
            continue

        if continuation_like:
            if (
                current_parent is not None
                and current_parent_open
                and same_bucket(current_parent, rec)
            ):
                current_parent["normalized_fact"] = append_child(
                    str(current_parent.get("normalized_fact", "")),
                    fact,
                )
                refresh_artifacts(current_parent)
                audit.append(f"merged continuation {rec.get('id', '')}: {fact}")
                continue

            output.append(rec)
            current_parent = rec
            current_parent_open = fact.rstrip().endswith(":")
            audit.append(
                f"kept continuation-like fact as separate record because bucket changed or parent was closed: {rec.get('id', '')}"
            )
            continue

        output.append(rec)
        current_parent = rec
        current_parent_open = fact.rstrip().endswith(":")

    for index, rec in enumerate(output, start=1):
        rec["id"] = f"F{index:03d}"

    return output, audit

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit", required=False)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    records = load_jsonl(input_path)
    repaired, audit = merge_records(records)
    write_jsonl(output_path, repaired)

    if args.audit:
        Path(args.audit).write_text("\n".join(audit) + ("\n" if audit else ""), encoding="utf-8")

    print(f"[repair] input records: {len(records)}")
    print(f"[repair] output records: {len(repaired)}")
    print(f"[repair] audit events: {len(audit)}")
    print(f"[repair] wrote: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

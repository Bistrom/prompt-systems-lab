#!/usr/bin/env bash

# Cel skryptu:
# - uruchomić pipeline dzienny w środowisku WSL bez Hermesa,
# - wykonać walidację wejść,
# - pociąć chat_export na chunki i uruchomić etap 1 przez Ollama API,
# - scalić częściowe raporty w jeden raport postępów,
# - uruchomić etap 2 przez Ollama API (bez Hermesa, w pełni lokalnie),
# - sprawdzić minimalną jakość DAILY_LOG,
# - uruchomić końcowy walidator MERGED_SOURCES,
# - skopiować pliki wyjściowe do właściwych folderów docelowych,
# - posprzątać katalogi tymczasowe.
#
# Użycie:
#   bash run_daily_pipeline.sh YYYY-MM-DD [CHUNK_SIZE] [OVERLAP]
# Przykład:
#   bash run_daily_pipeline.sh 2026-04-25 8000 800
#
# Domyślny chunk-size: 8000 znaków
# Domyślny overlap:    800 znaków
#
# W pełni lokalny pipeline — bez Hermesa, bez GPT, bez internetu.
# Etap 1 i Etap 2 przez Ollama/Mistral lokalnie.
#
# WAŻNE:
# Ten wariant ma dodatkową ochronę przed fałszywym sukcesem:
# - DAILY_LOG z placeholderem typu "[Here is the content...]" nie trafia do 01_Poprawne,
# - DAILY_LOG za krótki nie trafia do 01_Poprawne,
# - MERGED_SOURCES jest budowany przez ollama_stage2.py z realnej treści źródeł.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
CHUNK_SCRIPT="$PROJECT_ROOT/chunk_chat_export.py"
MERGE_SCRIPT="$PROJECT_ROOT/merge_partial_reports.py"
OLLAMA_STAGE1_SCRIPT="$PROJECT_ROOT/ollama_stage1.py"
OLLAMA_STAGE2_SCRIPT="$PROJECT_ROOT/ollama_stage2.py"
FACT_NORMALIZER_SCRIPT="$PROJECT_ROOT/normalize_daily_facts.py"
DAILY_RENDERER_SCRIPT="$PROJECT_ROOT/render_daily_log.py"
STAGE1_CACHE_DIR="$PROJECT_ROOT/12_Backups/03_STAGE1_CACHE"

# Parametry chunkingu
CHUNK_SIZE="${2:-8000}"
OVERLAP="${3:-800}"

# Minimalny rozmiar daily loga w bajtach.
# Chroni przed sytuacją, w której model zwróci pusty placeholder, ale plik formalnie nie jest pusty.
# Dla bardzo małych wejść testowych próg musi być niższy, bo poprawny DAILY_LOG może być krótszy.
DAILY_LOG_MIN_BYTES=1500
DAILY_LOG_MIN_BYTES_SMALL_INPUT=900

# Parametry Ollamy
OLLAMA_MODEL="mistral-pipeline"
OLLAMA_URL="http://127.0.0.1:11434"

# Foldery docelowe
DIR_DAILY_LOG_OK="$PROJECT_ROOT/07_Daily_Logs/01_Poprawne"
DIR_DAILY_LOG_FIX="$PROJECT_ROOT/07_Daily_Logs/02_Do_Naprawy"
DIR_RAPORT="$PROJECT_ROOT/08_Raporty_Postepow"
DIR_MERGED="$PROJECT_ROOT/12_Backups/01 MERGED_SOURCES"
DIR_README="$PROJECT_ROOT/12_Backups/02 README_PL"
DIR_FACT_LEDGER="$PROJECT_ROOT/12_Backups/04 FACT_LEDGER"

log() {
  printf '[INFO] %s\n' "$1"
}

err() {
  printf '[ERROR] %s\n' "$1" >&2
}

die() {
  err "$1"
  exit 1
}

require_file() {
  local path="$1"
  local label="$2"
  [ -f "$path" ] || die "Brak wymaganego pliku: $label -> $path"
}

require_dir() {
  local path="$1"
  local label="$2"
  [ -d "$path" ] || die "Brak wymaganego katalogu: $label -> $path"
}

require_positive_int() {
  local value="$1"
  local label="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || die "$label musi być liczbą całkowitą dodatnią: $value"
  [ "$value" -gt 0 ] || die "$label musi być większe od zera: $value"
}

cleanup() {
  local exit_code=$?
  if [ -n "${CHUNK_DIR:-}" ] && [ -d "${CHUNK_DIR:-}" ]; then
    rm -rf "$CHUNK_DIR"
    log "Katalog tymczasowy chunków usunięty: $CHUNK_DIR"
  fi
  if [ -n "${PARTIAL_DIR:-}" ] && [ -d "${PARTIAL_DIR:-}" ]; then
    rm -rf "$PARTIAL_DIR"
    log "Katalog tymczasowy raportów częściowych usunięty: $PARTIAL_DIR"
  fi
  exit "$exit_code"
}

trap cleanup EXIT

# ─── Walidacja argumentów ────────────────────────────────────────────────────

if [ "$#" -lt 1 ]; then
  die "Musisz podać co najmniej jeden argument: datę w formacie YYYY-MM-DD"
fi

DAY="$1"
if [[ ! "$DAY" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  die "Nieprawidłowy format daty. Oczekiwano: YYYY-MM-DD"
fi

require_positive_int "$CHUNK_SIZE" "CHUNK_SIZE"
[[ "$OVERLAP" =~ ^[0-9]+$ ]] || die "OVERLAP musi być liczbą całkowitą nieujemną: $OVERLAP"
[ "$OVERLAP" -lt "$CHUNK_SIZE" ] || die "OVERLAP musi być mniejszy niż CHUNK_SIZE"

# ─── Ścieżki ─────────────────────────────────────────────────────────────────

DAY_DIR="$PROJECT_ROOT/11_Wejscia_Dzienne/$DAY"
CHAT_EXPORT="$DAY_DIR/chat_export_$DAY.md"
ROUGH_WORK="$DAY_DIR/rough_work_$DAY.md"
WORKFLOW_MAP="$PROJECT_ROOT/10_Zrodla_Sterujace/COMMIT_WORKFLOW_MAP.md"
SCHEMAT_DAILY_LOG="$PROJECT_ROOT/10_Zrodla_Sterujace/schemat_daily_log.md"
PROMPT_ETAP_1="$PROJECT_ROOT/09_Prompty/generator_raportu_postepow.txt"
PROMPT_ETAP_2="$PROJECT_ROOT/09_Prompty/generator_dokumentacji_dnia_v2.txt"
VALIDATOR="$PROJECT_ROOT/validate_merged_sources.py"
DAILY_QUALITY_VALIDATOR="$PROJECT_ROOT/validate_daily_quality.py"
OUTPUT_DIR="$PROJECT_ROOT/06_Materialy_testowe/manual_pipeline_${DAY}_run_auto"

RAPORT_POSTEPOW="$OUTPUT_DIR/RAPORT_POSTEPOW_${DAY}.md"
DAILY_LOG="$OUTPUT_DIR/DAILY_LOG_${DAY}.md"
MERGED_SOURCES="$OUTPUT_DIR/MERGED_SOURCES_${DAY}.txt"
README_PL="$OUTPUT_DIR/README_PL.txt"
STAGE1_AUDIT_DIR="$OUTPUT_DIR/stage1_audit"
STAGE1_QUALITY_MANIFEST="$STAGE1_AUDIT_DIR/stage1_quality_manifest.json"
FACT_LEDGER="$OUTPUT_DIR/FACT_LEDGER_${DAY}.jsonl"
FACT_LEDGER_RAW="$OUTPUT_DIR/FACT_LEDGER_RAW_${DAY}.jsonl"
FACT_LEDGER_REPAIR_AUDIT="$OUTPUT_DIR/FACT_LEDGER_REPAIR_AUDIT_${DAY}.txt"
FACT_LEDGER_REJECTED="$OUTPUT_DIR/FACT_LEDGER_REJECTED_${DAY}.md"

CHUNK_DIR="/tmp/chunks_${DAY}"
PARTIAL_DIR="/tmp/partial_reports_${DAY}"
STAGE1_TMP_QUALITY_MANIFEST="$PARTIAL_DIR/stage1_quality_manifest.json"

# ─── Start ───────────────────────────────────────────────────────────────────

log "START: run_daily_pipeline.sh dla dnia $DAY"
log "PROJECT_ROOT: $PROJECT_ROOT"
log "Parametry chunkingu: chunk-size=$CHUNK_SIZE, overlap=$OVERLAP"
log "Model Ollamy: $OLLAMA_MODEL @ $OLLAMA_URL"
log "Tryb: v7.6.9 lokalny, etap 1 z twardą bramką formatu + prompt z pliku + cache + trwały audyt, etap 2 z izolacją promptu + retry + bramkami jakości sekcji + fallback deterministyczny"
log "Cache etapu 1: $STAGE1_CACHE_DIR"

# ─── Walidacja wejść ─────────────────────────────────────────────────────────

log "Walidacja wejść..."
require_dir "$DAY_DIR" "folder dnia"
require_file "$CHAT_EXPORT" "chat_export"
require_file "$WORKFLOW_MAP" "COMMIT_WORKFLOW_MAP.md"
require_file "$SCHEMAT_DAILY_LOG" "schemat_daily_log.md"
require_file "$PROMPT_ETAP_1" "prompt etapu 1"
require_file "$PROMPT_ETAP_2" "prompt etapu 2"
require_file "$VALIDATOR" "validate_merged_sources.py"
require_file "$DAILY_QUALITY_VALIDATOR" "validate_daily_quality.py"
require_file "$CHUNK_SCRIPT" "chunk_chat_export.py"
require_file "$MERGE_SCRIPT" "merge_partial_reports.py"
require_file "$OLLAMA_STAGE1_SCRIPT" "ollama_stage1.py"
require_file "$OLLAMA_STAGE2_SCRIPT" "ollama_stage2.py"
require_file "$FACT_NORMALIZER_SCRIPT" "normalize_daily_facts.py"
require_file "$DAILY_RENDERER_SCRIPT" "render_daily_log.py"

# Sprawdź czy Ollama odpowiada.
curl -sf "$OLLAMA_URL/api/tags" >/dev/null 2>&1 || \
  die "Ollama nie odpowiada na $OLLAMA_URL — uruchom: ollama serve"

ROUGH_WORK_EXISTS="NO"
ROUGH_WORK_ARGS=()
ROUGH_WORK_NOTE="rough_work nie istnieje"
if [ -f "$ROUGH_WORK" ]; then
  ROUGH_WORK_EXISTS="YES"
  ROUGH_WORK_ARGS=(--rough-work "$ROUGH_WORK")
  ROUGH_WORK_NOTE="rough_work istnieje: $ROUGH_WORK"
fi

mkdir -p "$OUTPUT_DIR"

# v7.7.1: czyszczenie outputów bieżącego runu przed startem
# Usuwamy tylko pliki wygenerowane dla aktualnej daty w katalogu roboczym runu.
# Nie ruszamy cache etapu 1.
rm -f "$OUTPUT_DIR/DAILY_LOG_${DAY}.md" \
      "$OUTPUT_DIR/RAPORT_POSTEPOW_${DAY}.md" \
      "$OUTPUT_DIR/MERGED_SOURCES_${DAY}.txt" \
      "$OUTPUT_DIR/README_PL.txt" \
      "$OUTPUT_DIR/RAW_STAGE2_RESPONSE_${DAY}.txt" \
      "$OUTPUT_DIR/RAW_STAGE2_REPAIR_RESPONSE_${DAY}.txt" \
      "$OUTPUT_DIR/FACT_LEDGER_${DAY}.jsonl" \
      "$OUTPUT_DIR/FACT_LEDGER_RAW_${DAY}.jsonl" \
      "$OUTPUT_DIR/FACT_LEDGER_REJECTED_${DAY}.md" \
      "$OUTPUT_DIR/FACT_LEDGER_REPAIR_AUDIT_${DAY}.txt"
rm -rf "$OUTPUT_DIR/stage1_audit"
mkdir -p "$STAGE1_CACHE_DIR"

# Czyścimy pliki wyjściowe dla tego dnia, żeby ponowny test nie czytał starych artefaktów.
rm -f "$RAPORT_POSTEPOW" "$DAILY_LOG" "$MERGED_SOURCES" "$README_PL" "$FACT_LEDGER" "$FACT_LEDGER_REJECTED" "$OUTPUT_DIR/RAW_STAGE2_RESPONSE_${DAY}.txt"
rm -rf "$STAGE1_AUDIT_DIR"
mkdir -p "$STAGE1_AUDIT_DIR"

log "Walidacja wejść OK"
log "Katalog wyjściowy: $OUTPUT_DIR"
log "$ROUGH_WORK_NOTE"

# ─── Chunking chat_export ─────────────────────────────────────────────────────

log "Chunking: dzielenie chat_export na części..."
python3 "$CHUNK_SCRIPT" \
  --input "$CHAT_EXPORT" \
  --output-dir "$CHUNK_DIR" \
  --chunk-size "$CHUNK_SIZE" \
  --overlap "$OVERLAP"

CHUNK_COUNT_FILE="$CHUNK_DIR/chunk_count.txt"
[ -f "$CHUNK_COUNT_FILE" ] || die "chunk_chat_export.py nie zapisał chunk_count.txt"
CHUNK_COUNT=$(cat "$CHUNK_COUNT_FILE")
[[ "$CHUNK_COUNT" =~ ^[0-9]+$ ]] || die "Nieprawidłowa wartość chunk_count: $CHUNK_COUNT"
[ "$CHUNK_COUNT" -gt 0 ] || die "chunk_chat_export.py utworzył 0 chunków — sprawdź chat_export"
log "Chunking OK: $CHUNK_COUNT chunków"

mkdir -p "$PARTIAL_DIR"

# ─── Etap 1: Ollama przetwarza każdy chunk lokalnie ──────────────────────────

log "Etap 1: start (Ollama, $CHUNK_COUNT chunków)"

python3 "$OLLAMA_STAGE1_SCRIPT" \
  --chunk-dir "$CHUNK_DIR" \
  --partial-dir "$PARTIAL_DIR" \
  --chunk-count "$CHUNK_COUNT" \
  --day "$DAY" \
  --prompt-etap1 "$PROMPT_ETAP_1" \
  --workflow-map "$WORKFLOW_MAP" \
  --schemat-daily-log "$SCHEMAT_DAILY_LOG" \
  --cache-dir "$STAGE1_CACHE_DIR" \
  --audit-dir "$STAGE1_AUDIT_DIR" \
  "${ROUGH_WORK_ARGS[@]}" \
  --model "$OLLAMA_MODEL" \
  --ollama-url "$OLLAMA_URL" \
  2>&1 | tee "/tmp/run_daily_pipeline_stage1_${DAY}.log" || {
  die "Etap 1 (Ollama) zakończył się błędem — sprawdź: /tmp/run_daily_pipeline_stage1_${DAY}.log"
}

[ -s "$STAGE1_TMP_QUALITY_MANIFEST" ] || die "Etap 1 nie utworzył tymczasowego manifestu jakości: $STAGE1_TMP_QUALITY_MANIFEST"
[ -s "$STAGE1_QUALITY_MANIFEST" ] || die "Etap 1 nie utworzył trwałego manifestu jakości: $STAGE1_QUALITY_MANIFEST"
log "Etap 1 OK — trwały manifest jakości: $STAGE1_QUALITY_MANIFEST"

# ─── Scalanie raportów częściowych ───────────────────────────────────────────

log "Scalanie raportów częściowych..."
python3 "$MERGE_SCRIPT" \
  --input-dir "$PARTIAL_DIR" \
  --output "$RAPORT_POSTEPOW" \
  --day "$DAY"

[ -s "$RAPORT_POSTEPOW" ] || die "Scalanie nie utworzyło raportu: $RAPORT_POSTEPOW"
log "Scalanie OK — raport postępów gotowy (scalony z $CHUNK_COUNT chunków)"

# ─── Etap 1.5: normalizacja faktów ───────────────────────────────────────────

log "Etap 1.5: normalizacja faktów do FACT_LEDGER"

python3 "$FACT_NORMALIZER_SCRIPT" \
  --day "$DAY" \
  --raport-postepow "$RAPORT_POSTEPOW" \
  "${ROUGH_WORK_ARGS[@]}" \
  --output "$FACT_LEDGER_RAW" \
  --rejected-output "$FACT_LEDGER_REJECTED"

[ -s "$FACT_LEDGER_RAW" ] || die "Normalizacja faktów nie utworzyła FACT_LEDGER_RAW: $FACT_LEDGER_RAW"
[ -s "$FACT_LEDGER_REJECTED" ] || die "Normalizacja faktów nie utworzyła FACT_LEDGER_REJECTED: $FACT_LEDGER_REJECTED"

log "Etap 1.5a: naprawa FACT_LEDGER_RAW do finalnego FACT_LEDGER"
python3 "$PROJECT_ROOT/repair_fact_ledger.py" \
  --input "$FACT_LEDGER_RAW" \
  --output "$FACT_LEDGER" \
  --audit "$FACT_LEDGER_REPAIR_AUDIT"

[ -s "$FACT_LEDGER" ] || die "Naprawa faktów nie utworzyła finalnego FACT_LEDGER: $FACT_LEDGER"
[ -s "$FACT_LEDGER_REPAIR_AUDIT" ] || die "Audyt naprawy FACT_LEDGER nie powstał albo jest pusty: $FACT_LEDGER_REPAIR_AUDIT"

log "Etap 1.5a OK — finalny FACT_LEDGER gotowy"
[ -s "$FACT_LEDGER_REJECTED" ] || die "Normalizacja faktów nie utworzyła pliku rejected: $FACT_LEDGER_REJECTED"


log "Etap 1.5 OK — FACT_LEDGER gotowy"

# ─── Etap 2: deterministyczny render z FACT_LEDGER ───────────────────────────

log "Etap 2: render DAILY_LOG z FACT_LEDGER"

python3 "$DAILY_RENDERER_SCRIPT" \
  --day "$DAY" \
  --fact-ledger "$FACT_LEDGER" \
  --fact-ledger-rejected "$FACT_LEDGER_REJECTED" \
  --raport-postepow "$RAPORT_POSTEPOW" \
  --chat-export "$CHAT_EXPORT" \
  --workflow-map "$WORKFLOW_MAP" \
  --schemat-daily-log "$SCHEMAT_DAILY_LOG" \
  --prompt-etap2 "$PROMPT_ETAP_2" \
  --prompt-etap1 "$PROMPT_ETAP_1" \
  --stage1-quality-manifest "$STAGE1_QUALITY_MANIFEST" \
  --output-dir "$OUTPUT_DIR" \
  --chunk-count "$CHUNK_COUNT" \
  "${ROUGH_WORK_ARGS[@]}"

for output_file in "$DAILY_LOG" "$MERGED_SOURCES" "$README_PL" "$FACT_LEDGER" "$FACT_LEDGER_REJECTED"; do
  [ -s "$output_file" ] || die "Etap 2 / FACT_LEDGER nie utworzył wymaganego pliku: $output_file"
done
log "Etap 2 OK"

# ─── Walidacja jakości DAILY_LOG ──────────────────────────────────────────────

log "Walidacja jakości DAILY_LOG..."
DAILY_LOG_QUALITY_OK="YES"
DAILY_LOG_BYTES=$(wc -c < "$DAILY_LOG" | tr -d ' ')
EFFECTIVE_DAILY_LOG_MIN_BYTES="$DAILY_LOG_MIN_BYTES"

if [ "${CHUNK_COUNT:-0}" -le 1 ]; then
  EFFECTIVE_DAILY_LOG_MIN_BYTES="$DAILY_LOG_MIN_BYTES_SMALL_INPUT"
  log "Małe wejście / 1 chunk — używam obniżonego progu DAILY_LOG: ${EFFECTIVE_DAILY_LOG_MIN_BYTES} bajtów"
fi

if [ "$DAILY_LOG_BYTES" -lt "$EFFECTIVE_DAILY_LOG_MIN_BYTES" ]; then
  DAILY_LOG_QUALITY_OK="NO"
  log "DAILY_LOG za krótki: ${DAILY_LOG_BYTES} bajtów; minimum: ${EFFECTIVE_DAILY_LOG_MIN_BYTES}"
fi

if grep -Eiq '^[[:space:]]*\[Here is the content[^]]*\][[:space:]]*$|^[[:space:]]*\[tutaj[[:space:]]+treść[^]]*\][[:space:]]*$|^[[:space:]]*TODO[[:space:]]*$|^[[:space:]]*INSERT[[:space:]]+DAILY_LOG[[:space:]]*$|^[[:space:]]*=*DAILY_LOG_START=*?[[:space:]]*$|^[[:space:]]*=*DAILY_LOG_END=*?[[:space:]]*$' "$DAILY_LOG"; then
  DAILY_LOG_QUALITY_OK="NO"
  log "DAILY_LOG zawiera realną atrapę albo samodzielny marker techniczny — nie zostanie uznany za poprawny."
fi

STAGE2_MODE_CURRENT="$(
  awk '
    /^SOURCE_MANIFEST$/ {in_manifest=1; next}
    /^END_SOURCE_MANIFEST$/ {in_manifest=0}
    in_manifest && /^STAGE2_MODE:/ {
      sub(/^STAGE2_MODE:[[:space:]]*/, "", $0)
      print $0
      exit
    }
  ' "$MERGED_SOURCES"
)"

log "Tryb etapu 2 z SOURCE_MANIFEST: ${STAGE2_MODE_CURRENT:-BRAK}"

case "$STAGE2_MODE_CURRENT" in
  FALLBACK|DETERMINISTIC_FROM_RAPORT_POSTEPOW|DETERMINISTIC_OUTPUT_FROM_RAPORT_POSTEPOW|DETERMINISTIC_CLEAN_OUTPUT|DIAGNOSTIC_FROM_STAGE1_WARNINGS|DIAGNOSTIC_FROM_STAGE2_REJECTION)
    DAILY_LOG_QUALITY_OK="NO"
    log "Etap 2 użył trybu fallback/diagnostycznego z SOURCE_MANIFEST — DAILY_LOG trafi do 02_Do_Naprawy do ręcznego przeglądu."
    ;;
  MODEL_OUTPUT|MODEL_OUTPUT_REPAIRED|FACT_LEDGER_RENDERED)
    log "Etap 2 zwrócił akceptowalny tryb modelowy: $STAGE2_MODE_CURRENT"
    ;;
  *)
    DAILY_LOG_QUALITY_OK="NO"
    log "Nieznany albo brakujący STAGE2_MODE w SOURCE_MANIFEST — DAILY_LOG trafi do 02_Do_Naprawy."
    ;;
esac

if [ "$DAILY_LOG_QUALITY_OK" = "YES" ]; then
  log "Walidacja jakości DAILY_LOG OK"
else
  log "Walidacja jakości DAILY_LOG NIE — plik trafi do 02_Do_Naprawy"
fi

# ─── Walidacja końcowa MERGED_SOURCES ────────────────────────────────────────

log "Walidacja końcowa MERGED_SOURCES: start"

# Uwaga: przy set -e zwykłe VALIDATOR_OUTPUT=$(...) przerwałoby cały skrypt,
# jeśli walidator zwróci kod 1. A my chcemy wtedy dokończyć dystrybucję
# i skierować DAILY_LOG do 02_Do_Naprawy, zamiast urwać pipeline w połowie.
set +e
VALIDATOR_OUTPUT=$(python3 "$VALIDATOR" --merged "$MERGED_SOURCES" 2>&1)
VALIDATOR_EXIT=$?
set -e

printf '%s\n' "$VALIDATOR_OUTPUT"

VALIDATION_OK="NO"
if [ "$VALIDATOR_EXIT" -eq 0 ] && echo "$VALIDATOR_OUTPUT" | grep -q "^WALIDACJA: TAK"; then
  VALIDATION_OK="YES"
fi

if [ "$VALIDATOR_EXIT" -ne 0 ]; then
  log "Walidator MERGED_SOURCES zwrócił kod: $VALIDATOR_EXIT"
fi

if [ "$VALIDATION_OK" = "YES" ]; then
  log "Walidacja MERGED_SOURCES OK"
else
  log "Walidacja MERGED_SOURCES NIE — pliki trafią do 02_Do_Naprawy"
fi

# ─── Walidacja semantyczna DAILY_LOG / RAPORT_POSTEPOW ───────────────────────

log "Walidacja semantyczna DAILY_LOG / RAPORT_POSTEPOW: start"

set +e
DAILY_VALIDATOR_OUTPUT=$(python3 "$DAILY_QUALITY_VALIDATOR" \
  --day "$DAY" \
  --daily-log "$DAILY_LOG" \
  --raport-postepow "$RAPORT_POSTEPOW" \
  --merged "$MERGED_SOURCES" 2>&1)
DAILY_VALIDATOR_EXIT=$?
set -e

printf '%s\n' "$DAILY_VALIDATOR_OUTPUT"

if [ "$DAILY_VALIDATOR_EXIT" -eq 0 ] && echo "$DAILY_VALIDATOR_OUTPUT" | grep -q "^WALIDACJA_DZIENNA: TAK"; then
  log "Walidacja semantyczna DAILY_LOG / RAPORT_POSTEPOW OK"
else
  DAILY_LOG_QUALITY_OK="NO"
  log "Walidacja semantyczna DAILY_LOG / RAPORT_POSTEPOW NIE — DAILY_LOG trafi do 02_Do_Naprawy"
fi

# ─── Dystrybucja plików do folderów docelowych ───────────────────────────────

log "Dystrybucja plików do folderów docelowych..."

mkdir -p "$DIR_DAILY_LOG_OK"
mkdir -p "$DIR_DAILY_LOG_FIX"
mkdir -p "$DIR_RAPORT"
mkdir -p "$DIR_MERGED"
mkdir -p "$DIR_README"
mkdir -p "$DIR_FACT_LEDGER"

cp "$RAPORT_POSTEPOW" "$DIR_RAPORT/RAPORT_POSTEPOW_${DAY}.md"
log "Skopiowano: RAPORT_POSTEPOW → 08_Raporty_Postepow"

cp "$MERGED_SOURCES" "$DIR_MERGED/MERGED_SOURCES_${DAY}.txt"
log "Skopiowano: MERGED_SOURCES → 12_Backups/01 MERGED_SOURCES"

cp "$README_PL" "$DIR_README/README_PL_${DAY}.txt"
log "Skopiowano: README_PL → 12_Backups/02 README_PL"

cp "$FACT_LEDGER" "$DIR_FACT_LEDGER/FACT_LEDGER_${DAY}.jsonl"
cp "$FACT_LEDGER_REJECTED" "$DIR_FACT_LEDGER/FACT_LEDGER_REJECTED_${DAY}.md"
log "Skopiowano: FACT_LEDGER → 12_Backups/04 FACT_LEDGER"

if [ "$VALIDATION_OK" = "YES" ] && [ "$DAILY_LOG_QUALITY_OK" = "YES" ]; then
  cp "$DAILY_LOG" "$DIR_DAILY_LOG_OK/DAILY_LOG_${DAY}.md"
  rm -f "$DIR_DAILY_LOG_FIX/DAILY_LOG_${DAY}.md"
  log "Skopiowano: DAILY_LOG → 07_Daily_Logs/01_Poprawne"
  log "Usunięto ewentualną starszą wersję z 07_Daily_Logs/02_Do_Naprawy"
else
  cp "$DAILY_LOG" "$DIR_DAILY_LOG_FIX/DAILY_LOG_${DAY}.md"
  log "Skopiowano: DAILY_LOG → 07_Daily_Logs/02_Do_Naprawy"
  if [ -f "$DIR_DAILY_LOG_OK/DAILY_LOG_${DAY}.md" ]; then
    log "Pozostawiono istniejącą starszą wersję z 07_Daily_Logs/01_Poprawne; nieudany rerun nie kasuje ostatniego poprawnego wyniku."
  fi
fi

log "Dystrybucja OK"

# v7.7.2: finalna bramka spójności po dystrybucji
# Cel:
# - nie wolno kończyć sukcesem, jeśli finalne artefakty nie przechodzą walidacji;
# - nie wolno zostawiać poprawnego DAILY_LOG jednocześnie w 01_Poprawne i 02_Do_Naprawy;
# - tryb DO NAPRAWY musi kończyć się kodem niezerowym.

FINAL_OK_DAILY="$PROJECT_ROOT/07_Daily_Logs/01_Poprawne/DAILY_LOG_${DAY}.md"
FINAL_REPAIR_DAILY="$PROJECT_ROOT/07_Daily_Logs/02_Do_Naprawy/DAILY_LOG_${DAY}.md"
FINAL_RAPORT="$PROJECT_ROOT/08_Raporty_Postepow/RAPORT_POSTEPOW_${DAY}.md"
FINAL_MERGED="$PROJECT_ROOT/12_Backups/01 MERGED_SOURCES/MERGED_SOURCES_${DAY}.txt"
FINAL_LEDGER="$PROJECT_ROOT/12_Backups/04 FACT_LEDGER/FACT_LEDGER_${DAY}.jsonl"
FINAL_VALIDATE_LOG="/tmp/run_daily_pipeline_final_validate_${DAY}.log"

log "Finalna bramka spójności po dystrybucji: start"

FINAL_GATE_OK="YES"

# v7.7.3: bieżący run musi mieć poprawną walidację przed finalnym sukcesem
# Sama obecność starego poprawnego pliku w 01_Poprawne nie może maskować błędu bieżącego runu.
if [ "${VALIDATION_OK:-NO}" != "YES" ] || [ "${DAILY_LOG_QUALITY_OK:-NO}" != "YES" ]; then
  FINAL_GATE_OK="NO"
  echo "[FINAL_GATE_ERROR] Bieżący run nie przeszedł wcześniejszej walidacji: VALIDATION_OK=${VALIDATION_OK:-unset}, DAILY_LOG_QUALITY_OK=${DAILY_LOG_QUALITY_OK:-unset}" | tee -a "$FINAL_VALIDATE_LOG"
fi

for final_file in "$FINAL_OK_DAILY" "$FINAL_RAPORT" "$FINAL_MERGED" "$FINAL_LEDGER"; do
  if [ ! -s "$final_file" ]; then
    FINAL_GATE_OK="NO"
    echo "[FINAL_GATE_ERROR] Brak albo pusty finalny plik: $final_file" | tee -a "$FINAL_VALIDATE_LOG"
  fi
done

if [ "$FINAL_GATE_OK" = "YES" ]; then
  if ! python3 "$PROJECT_ROOT/validate_merged_sources.py" \
    --merged "$FINAL_MERGED" >> "$FINAL_VALIDATE_LOG" 2>&1
  then
    FINAL_GATE_OK="NO"
    echo "[FINAL_GATE_ERROR] Finalny MERGED_SOURCES nie przeszedł walidacji" | tee -a "$FINAL_VALIDATE_LOG"
  fi
fi

if [ "$FINAL_GATE_OK" = "YES" ]; then
  if ! python3 "$PROJECT_ROOT/validate_daily_quality.py" \
    --day "$DAY" \
    --daily-log "$FINAL_OK_DAILY" \
    --raport-postepow "$FINAL_RAPORT" \
    --merged "$FINAL_MERGED" \
    --fact-ledger "$FINAL_LEDGER" >> "$FINAL_VALIDATE_LOG" 2>&1
  then
    FINAL_GATE_OK="NO"
    echo "[FINAL_GATE_ERROR] Finalny DAILY_LOG nie przeszedł walidacji z finalnym FACT_LEDGER" | tee -a "$FINAL_VALIDATE_LOG"
  fi
fi

if [ "$FINAL_GATE_OK" = "YES" ]; then
  if grep -nE "STAGE2_MODE: MODEL_OUTPUT|2026-04-25|2099-01-01|status: planned|Brak wystarczającej podstawy|wymaga jeszcze ręcznego przeglądu|może nie zawierać pełnego opisu|\(planned\)|\(completed\)|\(unknown\)|\(status:|operacja: nieznana|pewność: niska|nazwa artefaktu:|^- (Nie odrzucał|^- Używał|^- Nie traktował|^- Wykrywał|^- Wzmacniał|^- Wielodniowego|^- Statusów|^- Starych dat|^- Niekanonicznych|^- Metadanych)" "$FINAL_OK_DAILY" >> "$FINAL_VALIDATE_LOG" 2>&1
  then
    FINAL_GATE_OK="NO"
    echo "[FINAL_GATE_ERROR] Finalny DAILY_LOG zawiera czerwone flagi" | tee -a "$FINAL_VALIDATE_LOG"
  fi
fi

if [ "$FINAL_GATE_OK" = "YES" ]; then
  rm -f "$FINAL_REPAIR_DAILY"
  log "Finalna bramka spójności po dystrybucji: OK"
  log "Usunięto ewentualną starszą wersję z 07_Daily_Logs/02_Do_Naprawy"
  log "KONIEC: run_daily_pipeline.sh dla dnia ${DAY} — sukces"
  exit 0
else
  mkdir -p "$PROJECT_ROOT/07_Daily_Logs/02_Do_Naprawy"
  if [ -s "$DAILY_LOG" ]; then
    cp "$DAILY_LOG" "$FINAL_REPAIR_DAILY"
  fi
  log "Finalna bramka spójności po dystrybucji: NIE"
  log "Szczegóły walidacji: $FINAL_VALIDATE_LOG"
  log "KONIEC: run_daily_pipeline.sh dla dnia ${DAY} — zakończono z wynikiem DO NAPRAWY"
  exit 2
fi

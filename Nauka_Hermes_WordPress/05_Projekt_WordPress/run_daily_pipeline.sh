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
#   bash run_daily_pipeline.sh 2026-04-25 20000 2000
#
# Domyślny chunk-size: 20000 znaków
# Domyślny overlap:    2000 znaków
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

PROJECT_ROOT="/mnt/c/Users/aleks/Documents/PROJEKT INŻYNIERSKI/Nauka_Hermes_WordPress"
CHUNK_SCRIPT="$PROJECT_ROOT/05_Projekt_WordPress/chunk_chat_export.py"
MERGE_SCRIPT="$PROJECT_ROOT/05_Projekt_WordPress/merge_partial_reports.py"
OLLAMA_STAGE1_SCRIPT="$PROJECT_ROOT/05_Projekt_WordPress/ollama_stage1.py"
OLLAMA_STAGE2_SCRIPT="$PROJECT_ROOT/05_Projekt_WordPress/ollama_stage2.py"
STAGE1_CACHE_DIR="$PROJECT_ROOT/12_Backups/03_STAGE1_CACHE"

# Parametry chunkingu
CHUNK_SIZE="${2:-20000}"
OVERLAP="${3:-2000}"

# Minimalny rozmiar daily loga w bajtach.
# Chroni przed sytuacją, w której model zwróci pusty placeholder, ale plik formalnie nie jest pusty.
DAILY_LOG_MIN_BYTES=1500

# Parametry Ollamy
OLLAMA_MODEL="mistral-pipeline"
OLLAMA_URL="http://127.0.0.1:11434"

# Foldery docelowe
DIR_DAILY_LOG_OK="$PROJECT_ROOT/07_Daily_Logs/01_Poprawne"
DIR_DAILY_LOG_FIX="$PROJECT_ROOT/07_Daily_Logs/02_Do_Naprawy"
DIR_RAPORT="$PROJECT_ROOT/08_Raporty_Postepow"
DIR_MERGED="$PROJECT_ROOT/12_Backups/01 MERGED_SOURCES"
DIR_README="$PROJECT_ROOT/12_Backups/02 README_PL"

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
VALIDATOR="$PROJECT_ROOT/05_Projekt_WordPress/validate_merged_sources.py"
OUTPUT_DIR="$PROJECT_ROOT/06_Materialy_testowe/manual_pipeline_${DAY}_run_auto"

RAPORT_POSTEPOW="$OUTPUT_DIR/RAPORT_POSTEPOW_${DAY}.md"
DAILY_LOG="$OUTPUT_DIR/DAILY_LOG_${DAY}.md"
MERGED_SOURCES="$OUTPUT_DIR/MERGED_SOURCES_${DAY}.txt"
README_PL="$OUTPUT_DIR/README_PL.txt"
STAGE1_AUDIT_DIR="$OUTPUT_DIR/stage1_audit"
STAGE1_QUALITY_MANIFEST="$STAGE1_AUDIT_DIR/stage1_quality_manifest.json"

CHUNK_DIR="/tmp/chunks_${DAY}"
PARTIAL_DIR="/tmp/partial_reports_${DAY}"
STAGE1_TMP_QUALITY_MANIFEST="$PARTIAL_DIR/stage1_quality_manifest.json"

# ─── Start ───────────────────────────────────────────────────────────────────

log "START: run_daily_pipeline.sh dla dnia $DAY"
log "PROJECT_ROOT: $PROJECT_ROOT"
log "Parametry chunkingu: chunk-size=$CHUNK_SIZE, overlap=$OVERLAP"
log "Model Ollamy: $OLLAMA_MODEL @ $OLLAMA_URL"
log "Tryb: v7.3.3 lokalny, etap 1 odchudzony + cache surowych odpowiedzi + trwały audyt, etap 2 diagnostyczny"
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
require_file "$CHUNK_SCRIPT" "chunk_chat_export.py"
require_file "$MERGE_SCRIPT" "merge_partial_reports.py"
require_file "$OLLAMA_STAGE1_SCRIPT" "ollama_stage1.py"
require_file "$OLLAMA_STAGE2_SCRIPT" "ollama_stage2.py"

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
mkdir -p "$STAGE1_CACHE_DIR"

# Czyścimy pliki wyjściowe dla tego dnia, żeby ponowny test nie czytał starych artefaktów.
rm -f "$RAPORT_POSTEPOW" "$DAILY_LOG" "$MERGED_SOURCES" "$README_PL" "$OUTPUT_DIR/RAW_STAGE2_RESPONSE_${DAY}.txt"
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

# ─── Etap 2: Ollama tworzy finalną dokumentację ──────────────────────────────

log "Etap 2: start (Ollama, lokalnie)"

python3 "$OLLAMA_STAGE2_SCRIPT" \
  --day "$DAY" \
  --raport-postepow "$RAPORT_POSTEPOW" \
  --chat-export "$CHAT_EXPORT" \
  --workflow-map "$WORKFLOW_MAP" \
  --schemat-daily-log "$SCHEMAT_DAILY_LOG" \
  --prompt-etap2 "$PROMPT_ETAP_2" \
  --prompt-etap1 "$PROMPT_ETAP_1" \
  --stage1-quality-manifest "$STAGE1_QUALITY_MANIFEST" \
  --output-dir "$OUTPUT_DIR" \
  --chunk-count "$CHUNK_COUNT" \
  "${ROUGH_WORK_ARGS[@]}" \
  --model "$OLLAMA_MODEL" \
  --ollama-url "$OLLAMA_URL" \
  2>&1 | tee "/tmp/run_daily_pipeline_stage2_${DAY}.log" || {
  die "Etap 2 (Ollama) zakończył się błędem — sprawdź: /tmp/run_daily_pipeline_stage2_${DAY}.log"
}

for output_file in "$DAILY_LOG" "$MERGED_SOURCES" "$README_PL"; do
  [ -s "$output_file" ] || die "Etap 2 nie utworzył wymaganego pliku: $output_file"
done
log "Etap 2 OK"

# ─── Walidacja jakości DAILY_LOG ──────────────────────────────────────────────

log "Walidacja jakości DAILY_LOG..."
DAILY_LOG_QUALITY_OK="YES"
DAILY_LOG_BYTES=$(wc -c < "$DAILY_LOG" | tr -d ' ')

if [ "$DAILY_LOG_BYTES" -lt "$DAILY_LOG_MIN_BYTES" ]; then
  DAILY_LOG_QUALITY_OK="NO"
  log "DAILY_LOG za krótki: ${DAILY_LOG_BYTES} bajtów; minimum: ${DAILY_LOG_MIN_BYTES}"
fi

if grep -Eiq '^[[:space:]]*\[Here is the content[^]]*\][[:space:]]*$|^[[:space:]]*\[tutaj[[:space:]]+treść[^]]*\][[:space:]]*$|^[[:space:]]*TODO[[:space:]]*$|^[[:space:]]*INSERT[[:space:]]+DAILY_LOG[[:space:]]*$|^[[:space:]]*=*DAILY_LOG_START=*?[[:space:]]*$|^[[:space:]]*=*DAILY_LOG_END=*?[[:space:]]*$' "$DAILY_LOG"; then
  DAILY_LOG_QUALITY_OK="NO"
  log "DAILY_LOG zawiera realną atrapę albo samodzielny marker techniczny — nie zostanie uznany za poprawny."
fi

if grep -Eq "STAGE2_MODE: (FALLBACK|DETERMINISTIC_FROM_RAPORT_POSTEPOW|DIAGNOSTIC_FROM_STAGE1_WARNINGS|DIAGNOSTIC_FROM_STAGE2_REJECTION)" "$MERGED_SOURCES"; then
  DAILY_LOG_QUALITY_OK="NO"
  log "Etap 2 użył trybu naprawczego/diagnostycznego — DAILY_LOG trafi do 02_Do_Naprawy do ręcznego przeglądu."
fi

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

# ─── Dystrybucja plików do folderów docelowych ───────────────────────────────

log "Dystrybucja plików do folderów docelowych..."

mkdir -p "$DIR_DAILY_LOG_OK"
mkdir -p "$DIR_DAILY_LOG_FIX"
mkdir -p "$DIR_RAPORT"
mkdir -p "$DIR_MERGED"
mkdir -p "$DIR_README"

cp "$RAPORT_POSTEPOW" "$DIR_RAPORT/RAPORT_POSTEPOW_${DAY}.md"
log "Skopiowano: RAPORT_POSTEPOW → 08_Raporty_Postepow"

cp "$MERGED_SOURCES" "$DIR_MERGED/MERGED_SOURCES_${DAY}.txt"
log "Skopiowano: MERGED_SOURCES → 12_Backups/01 MERGED_SOURCES"

cp "$README_PL" "$DIR_README/README_PL_${DAY}.txt"
log "Skopiowano: README_PL → 12_Backups/02 README_PL"

if [ "$VALIDATION_OK" = "YES" ] && [ "$DAILY_LOG_QUALITY_OK" = "YES" ]; then
  cp "$DAILY_LOG" "$DIR_DAILY_LOG_OK/DAILY_LOG_${DAY}.md"
  rm -f "$DIR_DAILY_LOG_FIX/DAILY_LOG_${DAY}.md"
  log "Skopiowano: DAILY_LOG → 07_Daily_Logs/01_Poprawne"
  log "Usunięto ewentualną starszą wersję z 07_Daily_Logs/02_Do_Naprawy"
else
  cp "$DAILY_LOG" "$DIR_DAILY_LOG_FIX/DAILY_LOG_${DAY}.md"
  rm -f "$DIR_DAILY_LOG_OK/DAILY_LOG_${DAY}.md"
  log "Skopiowano: DAILY_LOG → 07_Daily_Logs/02_Do_Naprawy"
  log "Usunięto ewentualną starszą wersję z 07_Daily_Logs/01_Poprawne"
fi

log "Dystrybucja OK"

# ─── Podsumowanie ─────────────────────────────────────────────────────────────

log "Pliki robocze (06_Materialy_testowe):"
printf '  %s\n' "$RAPORT_POSTEPOW"
printf '  %s\n' "$DAILY_LOG"
printf '  %s\n' "$MERGED_SOURCES"
printf '  %s\n' "$README_PL"

log "Pliki docelowe:"
printf '  %s\n' "$DIR_RAPORT/RAPORT_POSTEPOW_${DAY}.md"
if [ "$VALIDATION_OK" = "YES" ] && [ "$DAILY_LOG_QUALITY_OK" = "YES" ]; then
  printf '  %s\n' "$DIR_DAILY_LOG_OK/DAILY_LOG_${DAY}.md"
else
  printf '  %s\n' "$DIR_DAILY_LOG_FIX/DAILY_LOG_${DAY}.md"
fi
printf '  %s\n' "$DIR_MERGED/MERGED_SOURCES_${DAY}.txt"
printf '  %s\n' "$DIR_README/README_PL_${DAY}.txt"

if [ "$VALIDATION_OK" = "YES" ] && [ "$DAILY_LOG_QUALITY_OK" = "YES" ]; then
  log "KONIEC: run_daily_pipeline.sh dla dnia $DAY — sukces"
else
  log "KONIEC: run_daily_pipeline.sh dla dnia $DAY — zakończono z wynikiem DO NAPRAWY"
fi

exit 0

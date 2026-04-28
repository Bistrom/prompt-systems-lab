# COMMIT_WORKFLOW_MAP — prompt-systems-lab / local-daily-pipeline

## 1. Cel pliku

Ten plik definiuje aktualną, roboczą mapę routingu dla projektu:

`prompt-systems-lab/05_AUTOMATION/local-daily-pipeline`

Jego zadaniem jest utrzymywanie spójności między:
- strukturą folderów projektu,
- pipeline’em dziennym,
- daily logami,
- raportami postępów,
- backupami źródeł,
- przyszłymi commitami.

Ten dokument opisuje **obecną strukturę roboczą**, a nie docelowy, przyszły układ po migracji do `prompt-systems-lab`.

## 2. Aktualna struktura projektu

### `01_Notatki/`

Notatki pomocnicze, szkice i materiały ręczne, które nie są bezpośrednim wejściem pipeline’u danego dnia.

Jeżeli brudnopis ma być użyty przez pipeline, musi zostać skopiowany do:

`11_Wejscia_Dzienne/YYYY-MM-DD/rough_work_YYYY-MM-DD.md`

### `02_Zapisane_strony/`

Zapisane strony, materiały zewnętrzne i referencje pomocnicze.

### `03_Komendy/`

Ściągi operacyjne, instrukcje uruchamiania i komendy pomocnicze.

Przykład:
- `komendy_podstawowe.txt`

### `04_Zrzuty_ekranu/`

Zrzuty ekranu używane jako pomoc kontekstowa. Nie powinny zastępować tekstowych źródeł, jeżeli tekst jest dostępny.

### `05_AUTOMATION/local-daily-pipeline/`

Aktywne skrypty pipeline’u i narzędzia techniczne.

Obecnie należą tu:
- `run_daily_pipeline.sh`
- `chunk_chat_export.py`
- `ollama_stage1.py`
- `merge_partial_reports.py`
- `ollama_stage2.py`
- `validate_merged_sources.py`

Status: roboczy / aktywnie rozwijany.

### `06_Materialy_testowe/`

Robocze wyniki uruchomień pipeline’u.

Przykład:
`manual_pipeline_YYYY-MM-DD_run_auto/`

Ten folder jest miejscem pracy technicznej, a nie finalnym miejscem dla zatwierdzonych daily logów.

### `07_Daily_Logs/`

Finalne lub wymagające naprawy daily logi.

#### `07_Daily_Logs/01_Poprawne/`

Tylko daily logi, które przeszły walidację jakości i nie są trybem naprawczym.

#### `07_Daily_Logs/02_Do_Naprawy/`

Daily logi:
- z fallbacku,
- z trybu deterministycznego,
- z podejrzeniem halucynacji,
- z błędami jakości,
- wymagające ręcznej kontroli.

### `08_Raporty_Postepow/`

Scalone raporty postępów po etapie 1.

Przykład:
`RAPORT_POSTEPOW_YYYY-MM-DD.md`

Raport postępów jest artefaktem pośrednim, ale commit-relevant, jeżeli dokumentuje rzeczywisty przebieg pracy.

### `09_Prompty/`

Aktywne prompty sterujące pipeline’em.

Przykłady:
- `generator_raportu_postepow.txt`
- `generator_dokumentacji_dnia_v2.txt`

W trybie domyślnym ich pełna treść nie powinna trafiać do `MERGED_SOURCES`; dozwolone są ścieżki w `SOURCE_MANIFEST`.

### `10_Zrodla_Sterujace/`

Pliki kontrolne i reguły projektu.

Obecnie:
- `COMMIT_WORKFLOW_MAP.md`
- `schemat_daily_log.md`

### `11_Wejscia_Dzienne/`

Jedyny właściwy folder wejść dziennych dla pipeline’u.

Wzorzec:

`11_Wejscia_Dzienne/YYYY-MM-DD/`

Wymagany plik:
- `chat_export_YYYY-MM-DD.md`

Opcjonalny plik:
- `rough_work_YYYY-MM-DD.md`

### `12_Backups/`

Kontrolowane backupy wyników technicznych.

#### `12_Backups/01 MERGED_SOURCES/`

Scalone źródła wykonania pipeline’u:

`MERGED_SOURCES_YYYY-MM-DD.txt`

Plik powinien zaczynać się od `SOURCE_MANIFEST`.

#### `12_Backups/02 README_PL/`

README pakietu dziennego:

`README_PL_YYYY-MM-DD.txt`

## 3. Reguły pipeline’u dziennego

Pipeline wykonuje przepływ:

```text
11_Wejscia_Dzienne/YYYY-MM-DD/chat_export_YYYY-MM-DD.md
+ opcjonalnie rough_work_YYYY-MM-DD.md
→ chunk_chat_export.py
→ ollama_stage1.py
→ merge_partial_reports.py
→ ollama_stage2.py
→ validate_merged_sources.py
→ dystrybucja plików
```

## 4. Dystrybucja wyników

Po uruchomieniu pipeline’u:

- `RAPORT_POSTEPOW_YYYY-MM-DD.md`
  → `08_Raporty_Postepow/`

- `MERGED_SOURCES_YYYY-MM-DD.txt`
  → `12_Backups/01 MERGED_SOURCES/`

- `README_PL_YYYY-MM-DD.txt`
  → `12_Backups/02 README_PL/`

- `DAILY_LOG_YYYY-MM-DD.md`
  → `07_Daily_Logs/01_Poprawne/` albo `07_Daily_Logs/02_Do_Naprawy/`

Daily log trafia do `01_Poprawne` tylko wtedy, gdy:
- `MERGED_SOURCES` przejdzie walidację,
- `DAILY_LOG` przejdzie bramkę jakości,
- etap 2 nie został oznaczony jako deterministyczny fallback do przeglądu.

## 5. Reguły commitowe

Commit roboczy może objąć:
- skrypty z `05_AUTOMATION/local-daily-pipeline/`,
- pliki kontrolne z `10_Zrodla_Sterujace/`,
- zaktualizowane komendy z `03_Komendy/`,
- raporty i daily logi, jeśli są celowo dokumentowane.

Nie commituj:
- `__pycache__/`,
- plików `.pyc`,
- przypadkowych backupów lokalnych,
- prywatnych CV, listów motywacyjnych lub plików osobistych,
- dużych zrzutów ekranu, jeśli nie są potrzebne do odtworzenia procesu.

## 6. Ważne ograniczenie

Ten plik opisuje obecną strukturę roboczą. Jeżeli później projekt zostanie przeniesiony do:

`prompt-systems-lab/projects/WTF_WordPress_pro_bono/`

trzeba wykonać osobny refaktor:
- `PROJECT_ROOT`,
- ścieżek w `run_daily_pipeline.sh`,
- komend w `03_Komendy/`,
- tej mapy workflow.


## 7. Optymalizacje v7

Etap 1 nie dostaje już pełnej mapy workflow ani pełnego schematu daily loga przy każdym chunku. Używa krótkiego kontraktu ekstrakcji. Pełny `COMMIT_WORKFLOW_MAP.md` i pełny `schemat_daily_log.md` są używane dopiero w etapie 2.

Cache etapu 1 znajduje się w `12_Backups/03_STAGE1_CACHE/` i jest liczony po `sha256` treści chunka, wersji kontraktu oraz nazwie modelu.


## 8. Korekta v7.1

v7.1 jest bezpiecznym rollbackiem po zbyt agresywnej v8.

Zasady:
- etap 1 pozostaje odchudzony i używa cache,
- etap 1 nie odrzuca automatycznie odpowiedzi tylko dlatego, że wygląda poradnikowo po angielsku; zapisuje ostrzeżenie,
- etap 1 nadal blokuje techniczne przecieki instrukcji i puste atrapy,
- etap 2 nadal używa pełnej mapy workflow i pełnego schematu,
- pełna walidacja semantyczna wróci dopiero jako osobny, ręczny audyt, nie jako agresywna bramka przerywająca przepływ.

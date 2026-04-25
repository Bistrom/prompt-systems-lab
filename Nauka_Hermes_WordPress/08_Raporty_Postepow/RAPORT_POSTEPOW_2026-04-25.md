# RAPORT POSTĘPÓW — 2026-04-25

> Raport scalony z 2 częściowych raportów.

## Status fragmentu

Fragment 1 z 2 został skierowany do kwarantanny jakości etapu 1.

## Powód

Model zwrócił odpowiedź wyglądającą jak poradnik albo ogólna odpowiedź, a nie czystą ekstrakcję faktów z fragmentu rozmowy. Żeby nie skazić scalonego `RAPORT_POSTEPOW`, pipeline nie propaguje tej odpowiedzi do raportu.

## Ostrzeżenia jakości

- możliwa odpowiedź poradnikowa, sprawdź ręcznie: \bIt seems like\b
- możliwa odpowiedź poradnikowa, sprawdź ręcznie: \bHere(?:'s| is) a summary\b

## Surowa odpowiedź modelu

Surowa odpowiedź została zapisana do ręcznej kontroli:

`/mnt/c/Users/aleks/Documents/PROJEKT INŻYNIERSKI/Nauka_Hermes_WordPress/06_Materialy_testowe/manual_pipeline_2026-04-25_run_auto/stage1_audit/raw_stage1_responses/raw_stage1_chunk_1.txt`

## Niepewności i nierozstrzygnięte punkty

<!-- źródło: chunk 1/2 -->
- Ten fragment wymaga ręcznej rekonstrukcji albo ponownego uruchomienia po poprawie promptu etapu 1.
- Nie należy traktować tego fragmentu jako poprawnie zrekonstruowanego raportu postępów.

<!-- źródło: chunk 2/2 -->
- Nieznana jest dokładna kolejność działań dotyczących zmiany struktury folderów, przenoszenia projektu do innego folderu lub zmiany nazwy projektu. [niska]

## Fakty z fragmentu

- Pipeline działa perfekcyjnie — pełny sukces z brudnopisem, dystrybucja do właściwych folderów, walidacja TAK. [planned/completed/wysoka]
- Hermes jest zainstalowany i używany przez pipeline, ale zostanie usunięty. [planned/partially completed/wysoka]
- Etap 2 pipeline'u będzie przepisany żeby używał Ollamy zamiast Hermesa. [planned/unknown]
- Przeniesienie projektu do innego folderu lub zmiana nazwy projektu może spowodować problemy z pipeline'em, ale będzie on adaptowany do nowej lokalizacji. [planned/unknown]
- Zmiana struktury folderów i nazw projektu na `prompt-systems-lab` i `WTF_WordlPress_pro_bono`. [planned/unknown]

## Artefakty wspomniane w fragmencie

- `run_daily_pipeline.sh` — plik/skrypt/folder/dokument/niepewne [utworzono/zmieniono/przeniesiono/sprawdzono/planowano/niepewne] [wysoka]
- `ollama_stage2.py` — plik/skrypt/folder/dokument/niepewne [utworzono/zmieniono/przeniesiono/sprawdzono/planowano/niepewne] [wysoka]

## Decyzje lub ustalenia

- Pipeline działa bezpiecznie i darmowo z Ollamą, ale z mniejszą jakością niż z Hermesem. [średnia]
- Użycie klucza API Claude lub ChatGPT bezpośrednio jest lepsze od Ollamy, ale wymaga płacenia za tokeny i pełnej kontroli nad wysyłanymi danymi. [średnia]

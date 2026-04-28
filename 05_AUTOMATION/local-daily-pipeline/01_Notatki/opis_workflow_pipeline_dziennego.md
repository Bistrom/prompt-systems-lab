# Opis workflow pipeline’u dziennego

## 1. Cel pipeline’u

Pipeline dzienny służy do zamiany materiałów z jednego konkretnego dnia pracy na uporządkowany zestaw artefaktów dokumentacyjnych.

W praktyce pipeline:
- bierze materiał dnia zapisany w plikach,
- najpierw tworzy raport pośredni,
- potem tworzy finalną dokumentację dnia,
- na końcu pozwala sprawdzić, czy wynik jest zgodny z kontraktem projektu.

Pipeline nie służy do:
- zgadywania brakujących faktów,
- dopowiadania działań, których nie ma w źródłach,
- zastępowania brakującego eksportu czatu samym rough_work,
- traktowania promptów i plików sterujących jako materiału dnia.

Pipeline został podzielony na etapy, ponieważ:
- łatwiej kontrolować jakość pośredniego raportu,
- łatwiej wykryć błędy przed stworzeniem finalnego `daily_log`,
- łatwiej odróżnić materiał wejściowy od artefaktów pośrednich i końcowych.

## 2. Struktura wejść

Każdy dzień ma własny folder:
`11_Wejscia_Dzienne/YYYY-MM-DD/`

Przykład:
`11_Wejscia_Dzienne/2026-04-22/`

### Obowiązkowy plik wejściowy dnia
`chat_export_YYYY-MM-DD.md`

To jest najważniejsze źródło faktów o przebiegu dnia.
Bez tego pliku pipeline nie może ruszyć.

### Opcjonalny plik pomocniczy dnia
`rough_work_YYYY-MM-DD.md`

To jest pomocniczy materiał roboczy.
Używa się go tylko wtedy, gdy eksport czatu jest ubogi albo nie obejmuje wszystkiego.
Brak tego pliku nie blokuje pipeline’u.

### Stałe pliki systemowe
To nie są materiały dnia, tylko infrastruktura pipeline’u:
- `COMMIT_WORKFLOW_MAP.md`
- `schemat_daily_log.md`
- `generator_raportu_postepow.txt`
- `generator_dokumentacji_dnia_v2.txt`

## 3. Różnica między typami plików

### Materiał dnia
To pliki opisujące to, co wydarzyło się danego dnia.
Przykład:
- `chat_export_YYYY-MM-DD.md`
- opcjonalnie `rough_work_YYYY-MM-DD.md`

### Pliki systemowe
To pliki, które sterują sposobem działania pipeline’u.
Nie opisują same z siebie dnia pracy.
Mówią pipeline’owi, jak ma czytać źródła, jak tworzyć wynik i jak interpretować strukturę.

### Artefakt pośredni
To plik tworzony między etapami pracy.
W tym pipeline’ie takim artefaktem jest:
- `RAPORT_POSTEPOW_YYYY-MM-DD.md`

### Artefakty końcowe
To finalne pliki, które mają powstać po zakończeniu etapu 2:
- `RAPORT_POSTEPOW_YYYY-MM-DD.md`
- `DAILY_LOG_YYYY-MM-DD.md`
- `MERGED_SOURCES_YYYY-MM-DD.txt`
- `README_PL.txt`

Ważne:
`RAPORT_POSTEPOW_YYYY-MM-DD.md` jest artefaktem pośrednim logicznie, ale ma być domyślnie zapisany jako realny plik.

## 4. Etap 1

### Co wchodzi
Etap 1 używa:
- obowiązkowego `chat_export_YYYY-MM-DD.md`,
- opcjonalnie `rough_work_YYYY-MM-DD.md`, jeśli istnieje i rzeczywiście pomaga,
- `COMMIT_WORKFLOW_MAP.md`,
- `schemat_daily_log.md`,
- promptu `generator_raportu_postepow.txt`.

### Po co istnieje
Etap 1 porządkuje materiał dnia i zamienia go w czytelny raport postępów.
To etap, który ma zrekonstruować faktyczny przebieg pracy bez tworzenia jeszcze finalnego `daily_log`.

### Co wychodzi
Etap 1 tworzy:
- `RAPORT_POSTEPOW_YYYY-MM-DD.md`

## 5. Etap 2

### Co wchodzi
Etap 2 używa:
- raportu postępów z etapu 1,
- obowiązkowego `chat_export_YYYY-MM-DD.md`,
- opcjonalnie `rough_work_YYYY-MM-DD.md`, jeśli istnieje,
- `COMMIT_WORKFLOW_MAP.md`,
- `schemat_daily_log.md`,
- promptu `generator_dokumentacji_dnia_v2.txt`.

### Po co istnieje
Etap 2 tworzy finalną dokumentację dnia.
To etap, który bierze uporządkowany raport pośredni i zamienia go w końcowy pakiet dokumentacyjny zgodny z kontraktem projektu.

### Co wychodzi
Etap 2 ma tworzyć cztery pliki:
- `RAPORT_POSTEPOW_YYYY-MM-DD.md`
- `DAILY_LOG_YYYY-MM-DD.md`
- `MERGED_SOURCES_YYYY-MM-DD.txt`
- `README_PL.txt`

## 6. SOURCE_MANIFEST

`SOURCE_MANIFEST` to specjalna sekcja na początku pliku `MERGED_SOURCES_YYYY-MM-DD.txt`.

Jego rola jest bardzo ważna:
- pozwala twardo sprawdzić, jakie źródła zostały użyte,
- usuwa niejednoznaczność, czy pipeline pracował tylko na faktycznych wejściach,
- pozwala walidatorowi odróżnić metadane od rzeczywistego śladu promptu.

`SOURCE_MANIFEST` musi być na początku `MERGED_SOURCES`, bo walidacja docelowa zakłada, że najpierw jest manifest, a dopiero potem właściwy scalony pakiet źródeł.

W manifeście znajdują się metadane, między innymi:
- dzień,
- tryb pracy,
- ścieżka do `chat_export`,
- ścieżka do `rough_work` albo informacja o braku,
- ścieżki do plików sterujących,
- ścieżki do promptów etapu 1 i etapu 2,
- informacja o prompt trace,
- lista innych źródeł albo `NONE`.

Ważne:
ścieżki do promptów w `SOURCE_MANIFEST` nie są automatycznie śladem promptu.
Są metadanymi systemowymi, a nie treścią źródłową dnia.

## 7. Tryby pracy

### DEFAULT
To normalny tryb codziennej pracy.
W tym trybie powinno być:
- `MODE: DEFAULT`
- `PROMPT_TRACE_INCLUDED: NO`

To oznacza, że pipeline działa standardowo i nie zachowuje pełnego śladu promptu jako źródła.

### Tryb specjalny / prompt trace
To tryb wyjątkowy.
Używa się go tylko wtedy, gdy użytkownik jawnie chce zachować ślad promptu albo pełny ślad wykonania.

W normalnej pracy ten tryb nie powinien być używany.

## 8. Walidacja

### Co sprawdza użytkownik przed startem
Przed uruchomieniem pipeline’u trzeba sprawdzić:
- czy istnieje folder dnia,
- czy istnieje `chat_export_YYYY-MM-DD.md`,
- czy istnieją oba pliki sterujące,
- czy istnieją oba aktywne prompty.

### Co sprawdza walidator po zakończeniu
Walidator sprawdza przede wszystkim:
- czy `MERGED_SOURCES` ma prawidłową strukturę,
- czy zaczyna się od `SOURCE_MANIFEST`,
- czy manifest zawiera wymagane pola,
- czy tryb pracy jest zgodny z kontraktem,
- czy prompt trace nie został zachowany bez wyraźnej decyzji użytkownika,
- czy prompt nie został dołączony jako rzeczywista treść źródłowa zamiast samych metadanych.

### Kiedy wynik jest pełnym sukcesem
Pełny sukces jest wtedy, gdy:
- walidacja wejść przechodzi,
- etap 1 przechodzi,
- etap 2 przechodzi,
- powstają wszystkie wymagane pliki,
- `MERGED_SOURCES` zawiera `SOURCE_MANIFEST`,
- wynik walidatora końcowego to pełne `TAK`.

### Kiedy wynik jest przejściowy lub błędny
Wynik jest przejściowy, gdy pipeline działa, ale np. nie ma jeszcze pełnego manifestu i walidacja jest tylko warunkowa.
Wynik jest błędny, gdy brakuje obowiązkowych wejść, brakuje pliku systemowego albo walidator wykrywa naruszenie kontraktu źródeł.

## 9. Warunki zatrzymania

Pipeline ma zatrzymać się od razu, jeśli:
- nie ma folderu dnia,
- nie ma `chat_export_YYYY-MM-DD.md`,
- brakuje kluczowego pliku systemowego,
- dane są niespójne i nie da się odpowiedzialnie ustalić jednego dnia pracy.

Brak `rough_work` nie blokuje pracy.

## 10. Minimalny przebieg użytkownika krok po kroku

1. Użytkownik przygotowuje folder dnia `11_Wejscia_Dzienne/YYYY-MM-DD/`.
2. Umieszcza w nim obowiązkowy plik `chat_export_YYYY-MM-DD.md`.
3. Opcjonalnie dodaje `rough_work_YYYY-MM-DD.md`.
4. Sprawdza, czy istnieją wszystkie pliki systemowe.
5. Uruchamia etap 1.
6. Etap 1 tworzy `RAPORT_POSTEPOW_YYYY-MM-DD.md`.
7. Uruchamia etap 2.
8. Etap 2 tworzy komplet plików końcowych.
9. Użytkownik uruchamia walidator na `MERGED_SOURCES_YYYY-MM-DD.txt`.
10. Jeśli walidacja końcowa przechodzi, workflow dnia jest uznany za domknięty.

## 11. Najczęstsze pomyłki

- Mylenie PowerShell i ścieżek `/mnt/c/...`.
- Mylenie aktywnych promptów z promptami archiwalnymi.
- Traktowanie `SOURCE_MANIFEST` jak treści źródłowej dnia, zamiast jak metadanych systemowych.
- Oczekiwanie, że brak `chat_export` da się zastąpić samym `rough_work`.
- Mylenie raportu postępów z finalnym `daily_log`.

## 12. Podsumowanie końcowe

Na dziś ustalone są już:
- struktura wejść dnia,
- obowiązkowa rola `chat_export`,
- opcjonalna rola `rough_work`,
- aktywne prompty etapu 1 i etapu 2,
- rola plików systemowych,
- obowiązkowy `SOURCE_MANIFEST`,
- logika walidacji końcowej.

Później część tych działań zostanie zautomatyzowana skryptem uruchomieniowym.

Na obecnym etapie ręczny workflow jest już logicznie domknięty:
wiadomo, co jest wejściem, co jest wynikiem pośrednim, co jest wynikiem końcowym i co trzeba sprawdzić, aby uznać przebieg dnia za poprawny.

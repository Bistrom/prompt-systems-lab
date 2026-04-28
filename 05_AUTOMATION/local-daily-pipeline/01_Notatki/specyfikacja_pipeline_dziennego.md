# Specyfikacja pipeline dziennego

## 1. Cel pipeline’u

Celem pipeline’u dziennego jest przetworzenie materiałów z dokładnie jednego dnia do spójnego zestawu artefaktów dokumentacyjnych.

Ta specyfikacja opisuje wspólną logikę pipeline’u dla dwóch przyszłych wariantów uruchamiania:
- wariantu ręcznego,
- wariantu skryptowego.

Nie opisuje jeszcze implementacji launchera ani skryptu `.sh`.

Pipeline ma:
- oddzielać surowe materiały dnia od finalnej dokumentacji,
- wymuszać uczciwość dokumentacyjną,
- zatrzymywać się od razu przy brakach krytycznych,
- być zrozumiały także dla początkującego użytkownika,
- docelowo przechodzić pełną walidację końcową, a nie tylko wynik warunkowy.

Pipeline nie służy do:
- zgadywania brakujących faktów,
- zastępowania eksportu rozmowy samym opisem z pamięci,
- traktowania plików systemowych jako materiału dnia,
- wykonywania commitów lub zmian organizacyjnych poza zakresem dokumentacji.

## 2. Zasada jednego dnia

Jeden przebieg pipeline’u zawsze dotyczy dokładnie jednego dnia.

To oznacza:
- jedna data `YYYY-MM-DD`,
- jeden folder dnia,
- jeden zestaw wejść użytkownika dla tego dnia,
- jeden raport pośredni,
- jeden zestaw artefaktów końcowych.

Nie wolno mieszać materiałów z różnych dni w jednym przebiegu bez osobnej, jawnej decyzji projektowej.

## 3. Struktura wejść dziennych

Każdy dzień ma mieć osobny folder:
`/mnt/c/Users/aleks/Documents/prompt-systems-lab/05_AUTOMATION/local-daily-pipeline/11_Wejscia_Dzienne/YYYY-MM-DD/`

Przykład:
`/mnt/c/Users/aleks/Documents/prompt-systems-lab/05_AUTOMATION/local-daily-pipeline/11_Wejscia_Dzienne/2026-04-22/`

W tym folderze mają znajdować się materiały użytkownika dotyczące tylko tego jednego dnia.

## 4. Podział na typy plików

### 4.1. Wejścia użytkownika
To pliki opisujące konkretny dzień pracy.
Są dostarczane lub przygotowywane dla danego przebiegu pipeline’u.

### 4.2. Wejścia opcjonalne
To pliki użytkownika, które mogą pomóc, ale nie są zawsze wymagane.

### 4.3. Stałe pliki systemowe
To elementy infrastruktury pipeline’u, a nie materiały dnia.

W praktyce oznacza to, że:
- nie opisują one same w sobie tego, co wydarzyło się danego dnia,
- nie są „wsadem dnia” przygotowywanym ręcznie dla konkretnej daty,
- są używane przez pipeline jako stałe reguły działania, struktury i wykonania.

Do tej grupy należą:
- prompty,
- pliki sterujące,
- reguły struktury i klasyfikacji.

Początkujący użytkownik powinien rozumieć to tak:
- `chat_export_YYYY-MM-DD.md` to materiał dnia,
- `rough_work_YYYY-MM-DD.md` to pomocniczy materiał dnia,
- `COMMIT_WORKFLOW_MAP.md`, `schemat_daily_log.md` i prompty to infrastruktura pipeline’u, która pomaga przetwarzać dzień, ale sama nie jest zapisem dnia.

### 4.4. Artefakty pośrednie
To pliki tworzone w trakcie pipeline’u, potrzebne do następnego etapu, ale niebędące głównym wynikiem końcowym.

### 4.5. Artefakty końcowe
To obowiązkowe pliki kończące pełny przebieg pipeline’u.

## 5. Wejścia użytkownika

### 5.1. Obowiązkowy plik wejściowy dnia
W każdym folderze dnia musi istnieć plik:
`chat_export_YYYY-MM-DD.md`

Rola tego pliku:
- jest głównym źródłem faktów o przebiegu dnia,
- stanowi podstawę etapu 1,
- zasila także etap 2.

Ważna zasada:
nie wolno zakładać, że system „widzi rozmowę ChatGPT” bezpośrednio.
Rozmowa musi najpierw zostać wyeksportowana do pliku.

### 5.2. Wymagania minimalne dla pliku obowiązkowego
- plik musi istnieć,
- data w nazwie musi zgadzać się z folderem dnia,
- plik nie może być pusty,
- plik musi być czytelny jako tekst.

## 6. Wejścia opcjonalne

### 6.1. Plik pomocniczy dnia
Opcjonalny plik pomocniczy:
`rough_work_YYYY-MM-DD.md`

Rola tego pliku:
- dostarcza roboczego śladu dnia,
- może doprecyzować fakty, kolejność działań i nazwy artefaktów,
- nie zastępuje eksportu czatu.

Zasada użycia:
`rough_work_YYYY-MM-DD.md` należy wykorzystywać tylko wtedy, gdy export czatu jest ubogi lub nie obejmuje wszystkiego.

Jeżeli export czatu jest wystarczający, pipeline może działać bez tego pliku.

## 7. Stałe pliki systemowe

### 7.1. Prompty systemowe
Stałe prompty pipeline’u:
- `/mnt/c/Users/aleks/Documents/prompt-systems-lab/05_AUTOMATION/local-daily-pipeline/09_Prompty/generator_raportu_postepow.txt`
- `/mnt/c/Users/aleks/Documents/prompt-systems-lab/05_AUTOMATION/local-daily-pipeline/09_Prompty/generator_dokumentacji_dnia_v2.txt`

### 7.2. Pliki sterujące systemu
Stałe pliki sterujące:
- `/mnt/c/Users/aleks/Documents/prompt-systems-lab/05_AUTOMATION/local-daily-pipeline/10_Zrodla_Sterujace/COMMIT_WORKFLOW_MAP.md`
- `/mnt/c/Users/aleks/Documents/prompt-systems-lab/05_AUTOMATION/local-daily-pipeline/10_Zrodla_Sterujace/schemat_daily_log.md`

### 7.3. Rola stałych plików systemowych
Ich rola jest stała i projektowa:
- definiują sposób przetwarzania dnia,
- narzucają strukturę wyników,
- narzucają logikę statusów, placementu i traceability,
- nie są ręcznie „dostarczane na dany dzień” jako materiał dnia,
- nie są dowodem wykonania pracy.

## 8. Etap 1 — generowanie raportu postępów

### 8.1. Cel etapu 1
Etap 1 ma zrekonstruować rzeczywisty przebieg dnia i zapisać raport pośredni.

### 8.2. Wejścia etapu 1
Etap 1 używa:
- obowiązkowego `chat_export_YYYY-MM-DD.md`,
- opcjonalnie `rough_work_YYYY-MM-DD.md`,
- stałych plików systemowych:
  - `generator_raportu_postepow.txt`,
  - `COMMIT_WORKFLOW_MAP.md`,
  - `schemat_daily_log.md`.

### 8.3. Wynik etapu 1
Etap 1 tworzy plik:
`RAPORT_POSTEPOW_YYYY-MM-DD.md`

### 8.4. Status wyniku etapu 1
`RAPORT_POSTEPOW_YYYY-MM-DD.md`:
- nie jest finalnym artefaktem końcowym pipeline’u,
- jest artefaktem pośrednim,
- ma być domyślnie zapisywany jako osobny plik.

## 9. Etap 2 — generowanie finalnej dokumentacji dnia

### 9.1. Cel etapu 2
Etap 2 ma przekształcić materiały dnia w finalny pakiet dokumentacyjny.

### 9.2. Wejścia etapu 2
Etap 2 używa:
- raportu postępów z etapu 1,
- obowiązkowego `chat_export_YYYY-MM-DD.md`,
- opcjonalnie `rough_work_YYYY-MM-DD.md`,
- stałych plików systemowych:
  - `generator_dokumentacji_dnia_v2.txt`,
  - `COMMIT_WORKFLOW_MAP.md`,
  - `schemat_daily_log.md`.

### 9.3. Wyniki etapu 2
Etap 2 tworzy trzy obowiązkowe pliki końcowe:
- `DAILY_LOG_YYYY-MM-DD.md`
- `MERGED_SOURCES_YYYY-MM-DD.txt`
- `README_PL.txt`

### 9.4. Zasady działania etapu 2
Etap 2 ma:
- tworzyć rzeczywiste pliki, a nie tylko odpowiedź tekstową,
- zachować uczciwość dokumentacyjną,
- nie zgadywać brakujących faktów,
- nie włączać automatycznie samego promptu wykonawczego do `MERGED_SOURCES`, jeśli użytkownik nie zażąda zachowania śladu promptu lub pełnego śladu wykonania.

## 10. Artefakty pipeline’u

### 10.1. Artefakt pośredni
- `RAPORT_POSTEPOW_YYYY-MM-DD.md`

Funkcja:
- uporządkowany materiał pośredni pomiędzy wejściem użytkownika a finalną dokumentacją dnia.

### 10.2. Artefakty końcowe
- `DAILY_LOG_YYYY-MM-DD.md` — finalny dzienny log pracy,
- `MERGED_SOURCES_YYYY-MM-DD.txt` — scalony pakiet źródeł użytych zgodnie z regułami promptu etapu 2,
- `README_PL.txt` — polski dokument towarzyszący.

### 10.3. Wymóg docelowy dla `MERGED_SOURCES_YYYY-MM-DD.txt`
Docelowo `MERGED_SOURCES_YYYY-MM-DD.txt` ma zawierać na początku sekcję `SOURCE_MANIFEST`.

`SOURCE_MANIFEST` jest częścią kontraktu końcowego dla poprawnego pipeline’u i ma umożliwiać pełną walidację wyniku.

### 10.4. Po co istnieje `SOURCE_MANIFEST`
`SOURCE_MANIFEST` ma:
- umożliwiać twardą walidację końcową,
- usuwać niejednoznaczność, czy w `MERGED_SOURCES` są tylko faktyczne źródła,
- pozwalać odróżnić tryb domyślny fallback od trybu docelowego pełnej walidacji.

### 10.5. Minimalna zawartość `SOURCE_MANIFEST`
Minimalny zakres manifestu powinien zawierać co najmniej:
- `DAY`
- `CHAT_EXPORT_PATH`
- `ROUGH_WORK_PATH` albo informację, że brak
- `WORKFLOW_MAP_PATH`
- `SCHEMAT_DAILY_LOG_PATH`
- `PROMPT_ETAP_1_PATH`
- `PROMPT_ETAP_2_PATH`
- `MODE`
- `PROMPT_TRACE_INCLUDED: YES/NO`
- `OTHER_SOURCES: ...` albo `NONE`

## 11. Reguły kontraktowe dla `MERGED_SOURCES`

### 11.1. Domyślny kontrakt prompt trace
W trybie domyślnym `PROMPT_TRACE_INCLUDED` ma mieć wartość `NO`.

### 11.2. Zakaz automatycznego dołączania promptu etapu 2
Sam prompt etapu 2 nie może trafiać do `MERGED_SOURCES`, chyba że użytkownik jawnie włączy tryb specjalny zachowania śladu promptu lub pełnego śladu wykonania.

### 11.3. Co nie jest naruszeniem
Samo pojawienie się nazwy promptu w treści `chat_export` nie jest naruszeniem kontraktu.

### 11.4. Co jest naruszeniem
Naruszeniem jest dopiero rzeczywiste wklejenie dużego bloku promptu systemowego do `MERGED_SOURCES` bez wyraźnej decyzji użytkownika.

## 12. Tryby walidacji końcowej

### 12.1. Tryb `DEFAULT`
`DEFAULT` to tryb fallback.

Obowiązuje wtedy, gdy brak `SOURCE_MANIFEST`.
W tym trybie pipeline może działać, ale wynik końcowy może być oceniony tylko warunkowo.

### 12.2. Tryb `STRICT` / `MANIFEST`
`STRICT` albo `MANIFEST` to tryb pełnej walidacji.

Obowiązuje wtedy, gdy `SOURCE_MANIFEST` istnieje i jest poprawnie wypełniony.
To ma być tryb docelowy pipeline’u.

### 12.3. Docelowy wynik poprawnego pipeline’u
Docelowo poprawny pipeline powinien dawać wynik:
- walidacja wejść: TAK,
- etap 1: TAK,
- etap 2: TAK,
- `MERGED_SOURCES` zawiera `SOURCE_MANIFEST`,
- `PROMPT_TRACE_INCLUDED: NO` w trybie domyślnym,
- walidacja końcowa: pełne `TAK`, a nie `TAK WARUNKOWO`.

## 13. Reguły walidacji przed startem

Przed rozpoczęciem pipeline’u trzeba wykonać walidację.

### 13.1. Walidacja dnia
- pipeline dotyczy dokładnie jednego dnia,
- istnieje folder dnia `11_Wejscia_Dzienne/YYYY-MM-DD/`,
- wszystkie pliki użytkownika dotyczą tej samej daty.

### 13.2. Walidacja obowiązkowego wejścia użytkownika
- istnieje `chat_export_YYYY-MM-DD.md`,
- plik nie jest pusty,
- plik jest czytelny jako tekst.

Jeśli tego pliku brakuje, pipeline ma zatrzymać się od razu i nie przechodzić dalej.

### 13.3. Walidacja wejścia opcjonalnego
- jeśli istnieje `rough_work_YYYY-MM-DD.md`, jego data musi zgadzać się z folderem dnia,
- jeśli go nie ma, pipeline może działać dalej,
- jeśli export czatu jest ubogi, brak `rough_work_YYYY-MM-DD.md` może oznaczać większe ryzyko niepełnego wyniku.

### 13.4. Walidacja krytycznych plików systemowych
Muszą istnieć:
- `generator_raportu_postepow.txt`,
- `generator_dokumentacji_dnia_v2.txt`,
- `COMMIT_WORKFLOW_MAP.md`,
- `schemat_daily_log.md`.

Jeśli brakuje któregokolwiek z tych plików, pipeline ma zatrzymać się od razu.

### 13.5. Walidacja zakresu i roli plików
- pliki systemowe nie mogą być traktowane jako materiał dnia,
- archiwalne prompty nie mogą być używane jako wersje aktywne,
- nie wolno mieszać materiałów z różnych dni,
- nie wolno zakładać brakujących treści bez źródła plikowego.

## 14. Przypadki błędów i stany przejściowe

### 14.1. Brak `chat_export_YYYY-MM-DD.md`
Skutek:
- pipeline zatrzymuje się natychmiast.

Powód:
- brakuje głównego źródła faktów o dniu.

### 14.2. Brak krytycznego pliku systemowego
Dotyczy to braku któregokolwiek z plików:
- prompt etapu 1,
- prompt etapu 2,
- `COMMIT_WORKFLOW_MAP.md`,
- `schemat_daily_log.md`.

Skutek:
- pipeline zatrzymuje się natychmiast.

### 14.3. Niezgodność dat
Skutek:
- pipeline powinien zgłosić błąd walidacji i nie przechodzić dalej.

Powód:
- istnieje ryzyko zmieszania materiałów z różnych dni.

### 14.4. Puste lub bardzo ubogie wejście
Skutek:
- pipeline może dać wynik niepełny,
- albo powinien zatrzymać się z komunikatem, że materiał jest niewystarczający.

### 14.5. Oczekiwanie faktów, których nie ma w plikach
Skutek:
- system nie powinien improwizować,
- wynik powinien jawnie oznaczać luki i niepewności.

### 14.6. Próba traktowania rozmowy niewyeksportowanej jako wejścia
Skutek:
- pipeline nie powinien zakładać dostępu do historii rozmowy,
- należy najpierw utworzyć plik `chat_export_YYYY-MM-DD.md`.

### 14.7. Brak `SOURCE_MANIFEST`
Skutek:
- nie blokuje działania obecnego pipeline’u,
- ale oznacza wynik przejściowy / niepełny,
- końcowa walidacja może być tylko warunkowa.

Stan docelowy:
- poprawny, docelowy pipeline ma zawierać `SOURCE_MANIFEST`.

## 15. Minimalny przebieg użytkownika krok po kroku

1. Użytkownik wybiera dzień `YYYY-MM-DD`.
2. Tworzy lub uzupełnia folder dnia:
   `11_Wejscia_Dzienne/YYYY-MM-DD/`
3. Umieszcza w nim obowiązkowy plik:
   `chat_export_YYYY-MM-DD.md`
4. Opcjonalnie dodaje:
   `rough_work_YYYY-MM-DD.md`
5. Sprawdza, czy istnieją stałe pliki systemowe pipeline’u.
6. Uruchamia etap 1.
7. Etap 1 zapisuje:
   `RAPORT_POSTEPOW_YYYY-MM-DD.md`
8. Uruchamia etap 2.
9. Etap 2 zapisuje:
   - `DAILY_LOG_YYYY-MM-DD.md`
   - `MERGED_SOURCES_YYYY-MM-DD.txt`
   - `README_PL.txt`
10. Użytkownik sprawdza, czy wynik nie zawiera zmyślonych treści i czy zakres źródeł jest zgodny z kontraktem pipeline’u.
11. Docelowo użytkownik lub walidator sprawdza także, czy `MERGED_SOURCES` zawiera `SOURCE_MANIFEST` i czy końcowy wynik przechodzi pełną walidację, a nie tylko wariant warunkowy.

## 16. Czego nie wolno zakładać

Nie wolno zakładać, że:
- Hermes widzi historię rozmowy ChatGPT bezpośrednio,
- `rough_work_YYYY-MM-DD.md` zastępuje `chat_export_YYYY-MM-DD.md`,
- pliki systemowe są materiałem dnia,
- raport postępów jest tym samym co finalny `daily_log`,
- prompt etapu 1 produkuje finalną dokumentację dnia,
- prompt etapu 2 ma prawo zgadywać brakujące fakty,
- brakujące wejścia można uzupełnić „zdrowym rozsądkiem” bez jawnego zaznaczenia niepewności,
- archiwalne prompty są domyślnymi wersjami do codziennej pracy,
- sam aktualnie wykonywany prompt ma trafiać do `MERGED_SOURCES` bez wyraźnego żądania użytkownika,
- brak `SOURCE_MANIFEST` jest stanem docelowym poprawnego pipeline’u.

## 17. Jakie decyzje są już ustalone

Za ustalone należy uznać:
- pipeline ma dwa przyszłe warianty uruchamiania: ręczny i skryptowy,
- ta specyfikacja opisuje wspólną logikę, a nie implementację skryptu,
- jeden przebieg pipeline’u dotyczy dokładnie jednego dnia,
- każdy dzień ma osobny folder `11_Wejscia_Dzienne/YYYY-MM-DD/`,
- obowiązkowy plik wejściowy dnia to `chat_export_YYYY-MM-DD.md`,
- opcjonalny plik pomocniczy dnia to `rough_work_YYYY-MM-DD.md`,
- prompty i pliki sterujące są stałymi plikami systemu,
- brak `chat_export_YYYY-MM-DD.md` zatrzymuje pipeline od razu,
- brak krytycznego pliku systemowego zatrzymuje pipeline od razu,
- etap 1 zapisuje `RAPORT_POSTEPOW_YYYY-MM-DD.md`,
- etap 2 zapisuje trzy obowiązkowe artefakty końcowe,
- `RAPORT_POSTEPOW_YYYY-MM-DD.md` jest artefaktem pośrednim, a nie końcowym,
- rozmowa musi najpierw zostać wyeksportowana do pliku,
- `MERGED_SOURCES_YYYY-MM-DD.txt` ma docelowo zawierać sekcję `SOURCE_MANIFEST`,
- w trybie domyślnym `PROMPT_TRACE_INCLUDED` ma mieć wartość `NO`,
- docelowy poprawny pipeline ma przechodzić pełną walidację końcową.

## 18. Jakie decyzje nie są jeszcze ustalone

Na obecnym etapie nie są jeszcze w pełni ustalone:
- dokładna implementacja wariantu skryptowego,
- dokładny interfejs przyszłego launchera,
- dokładne miejsce zapisu artefaktów wyjściowych w docelowym trybie produkcyjnym,
- dokładny format komunikatów błędów dla użytkownika,
- dokładna postać tekstowa `SOURCE_MANIFEST`, poza minimalnym kontraktem pól,
- czy w przyszłości pojawi się osobna walidacja jakości wyników po etapie 2 poza walidacją manifestową.

## 19. Podsumowanie techniczne

Minimalna logika pipeline’u jest następująca:
- wejście obowiązkowe użytkownika: `chat_export_YYYY-MM-DD.md`,
- wejście opcjonalne użytkownika: `rough_work_YYYY-MM-DD.md`,
- stałe pliki systemowe: 2 prompty i 2 pliki sterujące,
- etap 1: generowanie `RAPORT_POSTEPOW_YYYY-MM-DD.md`,
- etap 2: generowanie `DAILY_LOG_YYYY-MM-DD.md`, `MERGED_SOURCES_YYYY-MM-DD.txt` i `README_PL.txt`.

Stan przejściowy:
- pipeline może działać bez `SOURCE_MANIFEST`, ale wtedy wynik końcowy jest tylko warunkowo zwalidowany.

Stan docelowy:
- `MERGED_SOURCES` zawiera `SOURCE_MANIFEST`,
- `PROMPT_TRACE_INCLUDED: NO` w trybie domyślnym,
- walidacja końcowa daje pełne `TAK`, a nie `TAK WARUNKOWO`.

Najważniejsza zasada jakości:
pipeline ma być uczciwy wobec źródeł plikowych i nie może udawać wiedzy, której nie dostał na wejściu.
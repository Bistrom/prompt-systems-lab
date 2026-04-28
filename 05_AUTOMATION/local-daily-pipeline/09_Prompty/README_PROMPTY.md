# 1. Krótka odpowiedź na start

- Prompt generujący raport postępów: `generator_raportu_postepow.txt`
- Prompt generujący finalną dokumentację dnia i plik `DAILY_LOG_YYYY-MM-DD.md`: `generator_dokumentacji_dnia_v2.txt`
- Obecnie aktywna wersja główna: `generator_dokumentacji_dnia_v2.txt`

Wprost: dawny plik `Generator daily log.txt` nie tworzył finalnego `daily_log`, tylko raport postępów służący jako materiał pośredni do dalszej dokumentacji.

# 2. Mapa promptów

## 2.1. generator_raportu_postepow.txt
- Nazwa pliku: `generator_raportu_postepow.txt`
- Pełna ścieżka: `/mnt/c/Users/aleks/Documents/prompt-systems-lab/05_AUTOMATION/local-daily-pipeline/09_Prompty/generator_raportu_postepow.txt`
- Status: aktywny
- Rzeczywista funkcja: generuje raport postępów z dnia, który porządkuje faktyczny przebieg pracy i stanowi materiał wejściowy do późniejszego tworzenia finalnej dokumentacji dnia.
- Jakie wejścia zwykle dostaje:
  - dzisiejszą rozmowę lub materiał opisujący wykonane działania,
  - `schemat_daily_log.md`,
  - `COMMIT_WORKFLOW_MAP.md`.
- Jaki wynik ma produkować:
  - raport w formacie `# RAPORT POSTĘPÓW — YYYY-MM-DD`,
  - sekcje opisujące zakres dnia, realnie wykonaną pracę, artefakty, placement, zmiany statusu, decyzje, commit relevance i niepewności.
- Kiedy go używać:
  - gdy chcesz najpierw uporządkować i zrekonstruować faktyczny przebieg dnia,
  - gdy potrzebujesz wiarygodnego raportu pośredniego przed zrobieniem finalnej dokumentacji dnia.
- Uwaga:
  - ta nazwa jest zgodna ze stanem faktycznym i jasno wskazuje, że chodzi o raport postępów, a nie o finalny `daily_log`.

## 2.2. generator_dokumentacji_dnia_v2.txt
- Nazwa pliku: `generator_dokumentacji_dnia_v2.txt`
- Pełna ścieżka: `/mnt/c/Users/aleks/Documents/prompt-systems-lab/05_AUTOMATION/local-daily-pipeline/09_Prompty/generator_dokumentacji_dnia_v2.txt`
- Status: aktywny
- Rzeczywista funkcja: główny prompt roboczy do zamiany dostarczonych materiałów dziennych na trzy realne artefakty: `DAILY_LOG_YYYY-MM-DD.md`, `MERGED_SOURCES_YYYY-MM-DD.txt` i `README_PL.txt`.
- Jakie wejścia zwykle dostaje:
  - `USER DAILY ROUGH DRAFT`, jeśli istnieje,
  - materiały promptowe / narzędziowe z danego dnia,
  - raport postępów wygenerowany wcześniej,
  - wybrane materiały z czatu,
  - pliki sterujące, np. `COMMIT_WORKFLOW_MAP.md` i `schemat_daily_log.md`.
- Jaki wynik ma produkować:
  - finalny `daily_log`,
  - scalony pakiet źródeł `MERGED_SOURCES`,
  - polski plik towarzyszący `README_PL.txt`.
- Kiedy go używać:
  - gdy chcesz wykonać właściwą, pełną dokumentację dnia,
  - gdy zależy Ci na realnym utworzeniu plików, a nie tylko na odpowiedzi tekstowej.
- Uwaga:
  - to jest obecnie główny prompt roboczy projektu w obszarze dokumentacji dziennej.

## 2.3. generator_dokumentacji_dnia_v1_0_archiwalny.txt
- Nazwa pliku: `generator_dokumentacji_dnia_v1_0_archiwalny.txt`
- Pełna ścieżka: `/mnt/c/Users/aleks/Documents/prompt-systems-lab/05_AUTOMATION/local-daily-pipeline/09_Prompty/archiwum/generator_dokumentacji_dnia_v1_0_archiwalny.txt`
- Status: archiwalny
- Rzeczywista funkcja: wcześniejsza, bardziej rozbudowana wersja promptu do tworzenia pełnej dokumentacji dziennej i plików towarzyszących.
- Jakie wejścia zwykle dostaje:
  - podobne do wersji aktywnej: materiały dzienne, raporty, pliki sterujące, ewentualnie rough draft i materiały z czatu.
- Jaki wynik ma produkować:
  - `DAILY_LOG_YYYY-MM-DD.md`,
  - `MERGED_SOURCES_YYYY-MM-DD.txt`,
  - `README_PL.txt`.
- Kiedy go używać:
  - raczej do analizy historycznej, porównania wersji lub odtworzenia rozwoju promptu,
  - nie jako pierwszy wybór do bieżącej pracy.
- Uwaga:
  - nazwa jasno wskazuje zarówno funkcję pliku, jak i jego status historyczny.

## 2.4. generator_dokumentacji_dnia_v1_1_archiwalny.txt
- Nazwa pliku: `generator_dokumentacji_dnia_v1_1_archiwalny.txt`
- Pełna ścieżka: `/mnt/c/Users/aleks/Documents/prompt-systems-lab/05_AUTOMATION/local-daily-pipeline/09_Prompty/archiwum/generator_dokumentacji_dnia_v1_1_archiwalny.txt`
- Status: archiwalny
- Rzeczywista funkcja: nowsza od 1.0 wersja przejściowa, która mocniej wymusza realne tworzenie plików i zakazuje udawania wyniku.
- Jakie wejścia zwykle dostaje:
  - podobne do 1.0 i wersji scalonej v2.
- Jaki wynik ma produkować:
  - ten sam zestaw trzech plików co 1.0 i v2.
- Kiedy go używać:
  - głównie do porównań historycznych albo analizy ewolucji zasad wykonawczych.
- Uwaga:
  - nazwa jasno wskazuje funkcję, wersję i status archiwalny.

## 2.5. Folder archiwum
- Nazwa elementu: `archiwum`
- Pełna ścieżka: `/mnt/c/Users/aleks/Documents/prompt-systems-lab/05_AUTOMATION/local-daily-pipeline/09_Prompty/archiwum`
- Status: pomocniczy
- Rzeczywista funkcja: przechowuje historyczne wersje promptów, które nie powinny być traktowane jako domyślnie aktywne.
- Jakie wejścia zwykle dostaje:
  - nie dotyczy; to katalog organizacyjny.
- Jaki wynik ma produkować:
  - nie produkuje wyniku; służy do porządku wersji.
- Kiedy go używać:
  - gdy trzeba sprawdzić historię zmian, porównać wersje albo odtworzyć logikę wcześniejszych promptów.
- Uwaga:
  - obecność folderu archiwum poprawia czytelność, bo oddziela wersje bieżące od historycznych.

# 3. Kolejność użycia w workflow

## Wersja praktyczna, najprostsza
1. Najpierw zbierz materiał dzienny.
   - Mogą to być: rozmowa z danego dnia, brudnopis dnia, raport postępów, pliki źródłowe i dokumenty sterujące.

2. Jeśli chcesz najpierw uporządkować fakty dnia, uruchom `generator_raportu_postepow.txt`.
   - Wejścia:
     - materiał z rozmowy lub opisu dnia,
     - `schemat_daily_log.md`,
     - `COMMIT_WORKFLOW_MAP.md`.
   - Wynik:
     - raport postępów w formacie `RAPORT POSTĘPÓW — YYYY-MM-DD`.

3. Potem uruchom `generator_dokumentacji_dnia_v2.txt`.
   - Wejścia:
     - raport postępów,
     - ewentualny rough draft dnia,
     - wybrane materiały z czatu,
     - pliki sterujące: `schemat_daily_log.md` i `COMMIT_WORKFLOW_MAP.md`,
     - inne rzeczywiste materiały źródłowe z dnia.
   - Wynik:
     - `DAILY_LOG_YYYY-MM-DD.md`,
     - `MERGED_SOURCES_YYYY-MM-DD.txt`,
     - `README_PL.txt`.

4. Wersji z folderu `archiwum` nie używaj jako domyślnych promptów roboczych.
   - Służą raczej do porównań, audytu i historii rozwoju systemu.

## Co jest najważniejsze w praktyce
- `generator_raportu_postepow.txt` = aktywny prompt pośredni: porządkuje fakty i robi raport postępów.
- `generator_dokumentacji_dnia_v2.txt` = aktywny prompt główny: robi finalną paczkę dokumentacyjną dnia.
- Pliki z `archiwum` = wersje historyczne, nie do domyślnego użycia operacyjnego.

# 4. Ryzyka pomyłki

- Nadal można pomylić `generator_raportu_postepow.txt` z `generator_dokumentacji_dnia_v2.txt`.
  - Dlaczego: oba prompty dotyczą tego samego dnia pracy i podobnego obszaru dokumentacji.
  - Jak unikać: pamiętać, że pierwszy robi raport pośredni, a drugi tworzy finalny pakiet trzech plików.

- Łatwo pomylić `generator_dokumentacji_dnia_v2.txt` z jego wersjami archiwalnymi.
  - Dlaczego: pliki mają wspólną funkcję i podobne nazwy bazowe.
  - Jak unikać: sprawdzać numer wersji i to, czy plik leży w katalogu głównym czy w `archiwum`.

- Najłatwiej pomylić wersje archiwalne między sobą.
  - Dlaczego: `generator_dokumentacji_dnia_v1_0_archiwalny.txt` i `generator_dokumentacji_dnia_v1_1_archiwalny.txt` różnią się głównie numerem wersji.
  - Jak unikać: patrzeć na numer wersji oraz na to, czy chodzi o analizę historyczną, czy o bieżącą pracę.

# 5. Rekomendacja organizacyjna

Obecny układ jest już wyraźnie czytelniejszy niż wcześniej, ponieważ:
- dwa aktywne prompty są jasno nazwane zgodnie z funkcją,
- aktywny prompt główny jest oddzielony od archiwum,
- stare wersje znajdują się w osobnym folderze,
- liczba aktywnych plików na najwyższym poziomie jest mała.

Rekomendacja:
- obecny układ można uznać za wystarczająco czytelny do codziennej pracy,
- w przyszłości można co najwyżej rozważyć dalsze skrócenie nazw, ale nie ma już pilnej potrzeby kolejnego przemianowywania.

Najuczciwszy wniosek:
- prompt raportu postępów da się ustalić pewnie,
- prompt finalnej dokumentacji dnia da się ustalić pewnie,
- funkcja archiwalnych wersji da się ustalić pewnie,
- największe ryzyko pomyłki wynika dziś z podobieństwa obszaru zastosowania aktywnych promptów, a nie z niejasnych nazw plików.

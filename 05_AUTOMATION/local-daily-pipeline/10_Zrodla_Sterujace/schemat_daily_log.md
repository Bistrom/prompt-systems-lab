# SCHEMAT_DAILY_LOG_STRICT

## 1. Status i rola pliku

Ten plik jest **rygorystycznym szablonem strukturalnym** dla dziennego pliku `DAILY_LOG_YYYY-MM-DD.md`.

Nie jest źródłem faktów o przebiegu dnia.
Nie jest streszczeniem pracy.
Nie jest dokumentem prezentacyjnym.
Nie wolno używać go do dopowiadania brakujących działań, wygładzania niejasności ani podnoszenia statusu wykonania.

Jego funkcja jest wyłącznie strukturalno-operacyjna:
- narzuca układ `daily_log`,
- wymusza śledzalność artefaktów,
- wymusza rozróżnienie statusów operacyjnych,
- wymusza odnotowanie placementu repozytoryjnego, gdy materiał to wspiera,
- wymusza jawne oznaczanie niepewności,
- blokuje fikcyjne domykanie dokumentacji.

Jeżeli materiał źródłowy nie daje podstawy do wypełnienia sekcji, sekcję należy:
- pominąć,
- albo oznaczyć jako niewspartą materiałem,
- ale nigdy nie wolno jej wypełniać domysłem.

---

## 2. Reguła nadrzędna

`daily_log` ma być dokumentem **dowodowym i operacyjnym**, nie narracyjnym.

To oznacza, że każdy wpis ma odpowiadać na możliwie dużą część poniższych pytań, jeśli materiał źródłowy na to pozwala:
- **Co** powstało, zostało zmienione, sklasyfikowane, przeniesione albo odrzucone?
- **Na jakim artefakcie** wykonano działanie?
- **Jaki jest status operacyjny** tego artefaktu lub pracy?
- **Gdzie** artefakt został umieszczony lub gdzie powinien zostać umieszczony?
- **Dlaczego** trafił właśnie tam?
- **Czy** zmiana jest commit-relevant?
- **Czy** status, placement lub interpretacja są pewne?

Jeżeli na któreś pytanie nie da się odpowiedzieć odpowiedzialnie na podstawie materiału, należy to oznaczyć zamiast zgadywać.

---

## 3. Reguły twarde

### 3.1. Czego bezwzględnie nie wolno robić

Nie wolno:
- przedstawiać planu jako wykonania,
- przedstawiać omówienia jako rezultatu,
- przedstawiać szkicu jako materiału stabilnego,
- przedstawiać testu jako wyniku końcowego,
- przedstawiać eksportu jako substytutu materiału źródłowego,
- przedstawiać estetycznie wyglądającego dokumentu jako metodologii tylko dlatego, że jest dobrze napisany,
- dopisywać „następnych kroków”, jeśli nie wynikają z materiału,
- wypełniać pustych sekcji ogólnikami,
- ukrywać konfliktów źródłowych,
- zacierać niepewności językiem pozornej pewności,
- zgadywać placementu repozytoryjnego,
- zgadywać commit relevance.

### 3.2. Minimalny standard wpisu

Każdy wpis merytoryczny w `daily_log` musi, jeśli materiał na to pozwala, zawierać przynajmniej:
- identyfikację artefaktu albo jednoznaczny opis przedmiotu pracy,
- opis operacji,
- status,
- poziom pewności.

Jeżeli materiał wspiera większą szczegółowość, wpis powinien dodatkowo zawierać:
- placement repozytoryjny,
- uzasadnienie placementu,
- commit relevance,
- zmianę statusu lub ruch między strefami repozytorium.

### 3.3. Preferencja jawnej luki

Jeżeli materiał jest niepełny, log ma pozostać niepełny, ale uczciwy.

Zasada nadrzędna:
**jawna luka jest lepsza niż fikcyjna kompletność**.

---

## 4. Dozwolone statusy operacyjne

Używaj wyłącznie statusów wspartych materiałem.
Nie awansuj statusu bez podstaw.

### 4.1. Statusy pracy

- **planned** — zamierzone, ale niewykonane.
- **started** — rozpoczęte.
- **in progress** — aktywnie rozwijane.
- **partially completed** — wykonane częściowo.
- **tested** — przetestowane.
- **completed** — ukończone.

### 4.2. Statusy artefaktowe

- **draft** — szkic / wersja robocza.
- **active** — materiał aktywnie rozwijany.
- **stabilized** — materiał ustabilizowany jako obowiązujący lub względnie dojrzały.
- **exported** — wygenerowano gotowy plik wyjściowy.
- **archived** — przeniesiono do archiwum.
- **rejected** — odrzucono.
- **uncertain** — brak odpowiedzialnej podstawy do mocniejszej klasyfikacji.

### 4.3. Statusy placementu

- **placed** — placement ustalony odpowiedzialnie.
- **proposed** — placement tylko proponowany lub roboczo sugerowany.
- **unknown** — placement nieustalony.

---

## 5. Poziomy pewności

Każdy istotny wpis powinien, jeśli to możliwe, zawierać poziom pewności.

Używaj tylko tych trzech poziomów:
- **wysoka** — materiał źródłowy jednoznacznie wspiera twierdzenie,
- **średnia** — twierdzenie wynika logicznie z materiału, ale nie jest wyrażone całkowicie wprost,
- **niska** — materiał daje tylko słabą podstawę; należy zachować ostrożność albo przenieść problem do sekcji niepewności.

Jeżeli pewność jest niska i temat dotyczy:
- statusu ukończenia,
- placementu repozytoryjnego,
- commit relevance,
- stabilizacji materiału,

należy domyślnie preferować słabszy opis zamiast mocniejszego.

---

## 6. Reguły sekcyjne

### 6.1. Sekcje obowiązkowe logicznie

Następujące sekcje są domyślnym szkieletem `daily_log`, ale każda z nich pojawia się **tylko wtedy, gdy istnieje materiałowa podstawa**:

1. `Zakres dnia`
2. `Praca faktycznie wykonana`
3. `Artefakty utworzone lub zmodyfikowane`
4. `Routing repozytoryjny / placement`
5. `Ruch artefaktów i zmiany statusu`
6. `Decyzje operacyjne i metodologiczne`
7. `Zmiany commit-relevant`
8. `Niepewności i nierozstrzygnięte punkty`
9. `Następne kroki`

### 6.2. Zasada pojawiania się sekcji

Sekcja ma się pojawić tylko wtedy, gdy spełniony jest odpowiedni warunek:

- `Zakres dnia` — jeśli da się odpowiedzialnie określić, czego dotyczyła praca.
- `Praca faktycznie wykonana` — jeśli da się wskazać realne działania wykonane danego dnia.
- `Artefakty utworzone lub zmodyfikowane` — jeśli powstały lub zostały zmienione konkretne artefakty.
- `Routing repozytoryjny / placement` — jeśli materiał pozwala odpowiedzialnie wskazać placement lub problem placementu.
- `Ruch artefaktów i zmiany statusu` — jeśli nastąpiło realne przejście, klasyfikacja, archiwizacja, stabilizacja albo eksport.
- `Decyzje operacyjne i metodologiczne` — jeśli zapadły decyzje wpływające na system pracy, strukturę repo albo dokumentację.
- `Zmiany commit-relevant` — jeśli istnieją zmiany mające realną wagę commitową.
- `Niepewności i nierozstrzygnięte punkty` — jeśli występują konflikty, luki, niejednoznaczności lub nierozstrzygnięte klasyfikacje.
- `Następne kroki` — tylko wtedy, gdy wynikają z materiału źródłowego, a nie z chęci domknięcia dokumentu.

### 6.3. Zasada pomijania sekcji

Jeżeli sekcja nie ma podstawy materiałowej, należy ją **usunąć z finalnego `daily_log`**, zamiast zostawiać pustą ozdobną ramę.

Wyjątek:
sekcję `Niepewności i nierozstrzygnięte punkty` wolno zachować nawet przy małej objętości, jeśli pełni ważną funkcję ostrzegawczą.

---

## 7. Reguły wpisów artefaktowych

Każdy artefakt opisuj, jeśli materiał na to pozwala, w możliwie jednolitym formacie.

### 7.1. Format minimalny

- **Artefakt:**
- **Typ:**
- **Operacja:**
- **Status:**
- **Pewność:**

### 7.2. Format rozszerzony

Dodaj także, jeśli materiał to wspiera:
- **Lokalizacja docelowa:**
- **Uzasadnienie placementu:**
- **Commit relevance:** tak / nie / niejednoznaczne
- **Ruch:** `from -> to`
- **Uwagi:**

### 7.3. Zakaz rozwlekłości

Wpis nie ma być eseistyczny.
Ma być precyzyjny i operacyjny.

### 7.4. Zakaz ogólników

Nie pisz:
- „pracowano nad promptem”,
- „zorganizowano pliki”,
- „dodano dokumentację”,

jeżeli materiał pozwala napisać dokładniej.

---

## 8. Reguły routingu repozytoryjnego

Jeżeli materiał źródłowy oraz aktualne pliki projektowe wspierają klasyfikację, należy odnotować placement zgodnie z ich funkcją operacyjną.

### 8.1. Co należy śledzić szczególnie

Śledź zwłaszcza:
- wejście nowego materiału do obiegu,
- przejście z `00_INBOX/` do folderu właściwego,
- przejście z `01_ACTIVE/` do `02_REPO_MATERIALS/`,
- przejście z `01_ACTIVE/` do `04_RESULTS/`,
- utworzenie artefaktów eksportowych,
- archiwizację,
- odrzucenie,
- zmianę materiału z aktywnego na stabilny.

### 8.2. Gdy placement jest niepewny

Jeżeli placement jest niepewny:
- nie zgaduj,
- nie wpisuj fałszywie precyzyjnej ścieżki,
- oznacz problem jako nierozstrzygnięty,
- w razie potrzeby użyj statusu `proposed` albo `unknown`.

---

## 9. Reguły commit relevance

Nie każdy ruch lub szkic jest równie ważny commitowo.

### 9.1. Kiedy oznaczać jako commit-relevant

Oznacz jako commit-relevant tylko wtedy, gdy materiał wskazuje, że zmiana:
- reprezentuje realny postęp,
- zmienia logikę systemu,
- stabilizuje metodologię,
- tworzy raport, wynik lub eksport o wartości projektowej,
- wpływa na strukturę repozytorium,
- zmienia workflow, routing lub reguły pracy.

### 9.2. Kiedy nie zawyżać commit relevance

Nie zawyżaj commit relevance dla:
- przypadkowych mikro-szkiców,
- chaotycznych notatek bez znaczenia odtworzeniowego,
- materiałów o nieustalonym statusie,
- samych ruchów technicznych bez znaczenia organizacyjnego,
- wtórnych eksportów bez znaczenia repozytoryjnego.

### 9.3. Gdy commit relevance jest niepewna

Zapisz to jawnie jako:
- `niejednoznaczne`,
- albo opisz w sekcji niepewności.

---

## 10. Matryca decyzji dla modelu

### 10.1. Jeżeli materiał mówi tylko o zamiarze

Wpisz to jako `planned`.
Nie używaj `started`, `in progress` ani `completed`.

### 10.2. Jeżeli materiał mówi o rozpoczęciu, ale bez wyniku

Użyj `started` albo `in progress`.
Nie używaj `completed`.

### 10.3. Jeżeli materiał mówi o testowaniu

Oznacz pracę lub artefakt jako `tested`, chyba że istnieją mocne podstawy do dodatkowego statusu.
Sam test nie oznacza jeszcze stabilizacji ani ukończenia.

### 10.4. Jeżeli materiał mówi o gotowym pliku wyjściowym

Można użyć `exported`, ale nie wolno z tego automatycznie wywodzić, że materiał źródłowy jest metodologicznie stabilny.

### 10.5. Jeżeli materiał wygląda formalnie, ale brak dowodu stabilizacji

Pozostaw status `draft`, `active` albo `uncertain`.
Nie awansuj do `stabilized` bez podstaw.

### 10.6. Jeżeli istnieje konflikt źródeł

- preferuj źródło wyższego priorytetu,
- zachowaj konflikt widoczny,
- nie wygładzaj go narracyjnie,
- odnotuj nierozstrzygnięty punkt, jeśli nie da się go odpowiedzialnie zamknąć.

---

## 11. Wzorzec finalnego pliku `DAILY_LOG_YYYY-MM-DD.md`

Poniżej znajduje się wzorzec docelowej struktury. Model ma używać tylko tych sekcji, które mają podstawę materiałową.

```md
# DAILY LOG — YYYY-MM-DD

## 1. Zakres dnia
Krótki, rzeczowy opis głównego obszaru pracy danego dnia.
Tylko to, co da się odpowiedzialnie ustalić z materiałów.

## 2. Praca faktycznie wykonana
- [opis działania] — status: [planned / started / in progress / partially completed / tested / completed] — pewność: [wysoka / średnia / niska]
- [opis działania] — status: [...] — pewność: [...]

## 3. Artefakty utworzone lub zmodyfikowane
- **Artefakt:** `nazwa_pliku_lub_systemu`
  - **Typ:** [prompt / workflow map / template / report / export / inny]
  - **Operacja:** [utworzenie / modyfikacja / przeniesienie / stabilizacja / eksport / archiwizacja / odrzucenie]
  - **Status:** [draft / active / stabilized / exported / archived / rejected / uncertain]
  - **Pewność:** [wysoka / średnia / niska]
  - **Lokalizacja docelowa:** [ścieżka / proposed / unknown]
  - **Uzasadnienie placementu:** [krótko i rzeczowo]
  - **Commit relevance:** [tak / nie / niejednoznaczne]
  - **Ruch:** [`from -> to`] lub `brak`
  - **Uwagi:** [opcjonalnie]

## 4. Routing repozytoryjny / placement
- **Artefakt:** `...`
  - **Placement:** `...`
  - **Status placementu:** [placed / proposed / unknown]
  - **Uzasadnienie:** ...
  - **Pewność:** [wysoka / średnia / niska]

## 5. Ruch artefaktów i zmiany statusu
- `from -> to`
  - **Artefakt:** `...`
  - **Zmiana statusu:** [np. active -> stabilized]
  - **Powód:** ...
  - **Commit relevance:** [tak / nie / niejednoznaczne]
  - **Pewność:** [wysoka / średnia / niska]

## 6. Decyzje operacyjne i metodologiczne
- [decyzja] — pewność: [wysoka / średnia / niska]
- [decyzja] — pewność: [...]

## 7. Zmiany commit-relevant
- [opis zmiany]
  - **Powód commit relevance:** ...
  - **Obszar repo:** ...
  - **Pewność:** [wysoka / średnia / niska]

## 8. Niepewności i nierozstrzygnięte punkty
- [opis konfliktu / luki / niejednoznaczności]
- [opis konfliktu / luki / niejednoznaczności]

## 9. Następne kroki
- [krok wynikający z materiału]
- [krok wynikający z materiału]
```

---

## 12. Wzorzec skrócony dla dni ubogich w materiał

Jeżeli dzień jest słabo udokumentowany, wolno użyć wersji skróconej, ale nadal bez fikcji:

```md
# DAILY LOG — YYYY-MM-DD

## 1. Zakres dnia
[tylko jeśli da się ustalić]

## 2. Praca faktycznie wykonana
- [działanie] — status: [...] — pewność: [...]

## 3. Niepewności i nierozstrzygnięte punkty
- [co pozostaje niejasne]
```

Ta wersja skrócona nie jest „gorsza”.
Jest poprawna wtedy, gdy materiał źródłowy nie wspiera bogatszej struktury.

---

## 13. Wzorce zdań dozwolonych

Dla zachowania dyscypliny można używać takich konstrukcji:

- `Utworzono roboczy artefakt ...`
- `Rozwinięto aktywną wersję ...`
- `Przygotowano szkic ...`
- `Przetestowano ...`
- `Ustabilizowano materiał ...`
- `Odnotowano niejednoznaczność dotyczącą ...`
- `Nie da się odpowiedzialnie rozstrzygnąć ...`
- `Materiał wspiera tylko status ...`
- `Placement pozostaje proponowany, a nie pewny.`

---

## 14. Wzorce zdań zakazanych

Nie używaj takich konstrukcji bez mocnej podstawy materiałowej:

- `Ukończono system ...`
- `Zamknięto pracę nad ...`
- `Artefakt jest stabilną metodologią ...`
- `Plik należy do ...`
- `Zmiana jest na pewno commit-relevant ...`
- `Zakończono etap ...`

jeżeli materiał źródłowy tego nie potwierdza.

---

## 15. Reguła końcowa

Ten szablon ma wymuszać pięć rzeczy:
- śledzalność,
- precyzję,
- uczciwość dokumentacyjną,
- zgodność z routingiem repozytorium,
- preferencję jawnej niepewności nad pozorną kompletnością.

Jeżeli materiał źródłowy jest mocny, log ma być bogaty i precyzyjny.
Jeżeli materiał źródłowy jest słaby, log ma być oszczędny, ale uczciwy.
Nigdy odwrotnie.

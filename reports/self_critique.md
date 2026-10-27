# Krytyka własnej odpowiedzi i poprawki (wersja 2)

Ten dokument jest **krytyką pierwszej odpowiedzi** i listą konkretnych poprawek, które
zostały wykonane i sprawdzone kodem. Wszystko poniżej jest odtwarzalne:
`python scripts/jc_planar_search.py` (826,7 s), zapis: `reports/planar_search_transcript.txt`,
testy: `python -m pytest -q` → 32 passed.

---

## A. Co było słabe w wersji 1 (i jest naprawione)

### A1. Zawyżone twierdzenie o liczbie punktów włókna — realny błąd matematyczny

Wersja 1 liczyła „liczbę punktów włókna” jako liczbę **różnych pierwiastków** wielomianu
eliminującego w jednej zmiennej. To daje jedynie **dolne ograniczenie**: dwa różne punkty
mogą mieć tę samą współrzędną \(x\). Kontrprzykład na ten błąd jest teraz w kodzie i w teście:

$$
(x^2,\,y^2),\quad \text{włókno punktu }(1,1)=\{(1,1),(1,-1),(-1,1),(-1,-1)\}:\quad
\text{wymiar ilorazu}=4,\ \text{różne }x = 2 .
$$

Przyjęcie „liczba pierwiastków = 1, więc odwzorowanie jest iniektywne” byłoby
nieuprawnione. **Poprawka:** kod liczy teraz
\(\dim_{\mathbb Q}\mathbb Q[x,y]/(P-w_1,Q-w_2)\) (liczba monomianów standardowych bazy
Gröbnera). Dla odwzorowania z \(\det J\) = niezerowa stała ideał włókna jest radykalny
(kryterium Jakobiego), więc ta liczba **jest** liczbą punktów nad \(\mathbb C\); licznik
pierwiastków pozostał wyłącznie jako dodatkowe dolne ograniczenie. Dodatkowo każde
twierdzenie o iniektywności jest podpierane jawną odwrotnością wielomianową sprawdzoną
podstawieniem — dwa niezależne certyfikaty zamiast jednego wątpliwego.
Test: `test_fibre_count_is_quotient_dimension_not_distinct_roots`.

### A2. Dzielenie przez parametry, które mogą się zerować (lane „cubic-linear”)

Wersja 1 zakładała `s,t,m,n ≠ 0` i dzieliła przez \(t\), a potem podawała wzór
\(\det J = 1 + 3L^2\,s\,m\,(s^2-t^2)\), ważny tylko przy \(t\ne0\). **Poprawka:** rachunek
jest teraz wolny od dzielenia, dla **dowolnych** \(s,t,m,n\):

\[
\det J \;=\; 1 + 3L^2\,(s^3m + t^3n),\qquad L = mx+ny,
\]

co sprawdza kod (`formula_verified`), a na rozmaitości nilpotencji \(sm+tn=0\) daje

\[
s^3m+t^3n = tn\,(t^2-s^2),
\]

co również jest weryfikowane symbolicznie (`identity_on_nilpotency_locus = 0`). Analiza
przypadków nie używa już założeń o niezerowości: \(L=0\); shersy \(sm=tn=0\);
\(tn\neq0 \Rightarrow t^2=s^2\). Każdy przypadek ma jawną, sprawdzoną odwrotność.
Dodatkowo skan 625 macierzy całkowitych pokazuje, że zbiór „\(\det J\) = niezerowa
stała” **równa się dokładnie** zbiorowi macierzy nilpotentnych (\(17=17\), ta sama lista) —
to jest treść twierdzenia Drużkowskiego, sprawdzona maszynowo w tym zakresie.

### A3. Lane trójkątny był tylko ograniczony stopniami

Wersja 1 rozwiązywała układ dla \(\deg P\le2,\ \deg f\le4\) i milczała o pozostałych
stopniach. **Poprawka:** kod weryfikuje dla ogólnych współczynników symbolicznych dwie
tożsamości, dla każdego badanego \(\deg_y P = 1,2,3,4\):

\[
\det J = -P_y\,f'(x),\qquad
[y^{d-1}]\,\det J = -d\,p_d(x)\,f'(x)\ \ (d=\deg_y P).
\]

Stąd, bez żadnego ograniczenia stopnia: jeśli \(\det J\) jest niezerową stałą, to
\(p_d(x)f'(x)\) jest niezerową stałą, więc \(d=1\) i \(f'\) jest stałą; wtedy
\(P=p_0(x)+cy\), \(Q=q_0+q_1x\), \(\det J = -c\,q_1\). Ta postać ma jawną odwrotność
wielomianową, sprawdzoną podstawieniem. To jest argument dla **wszystkich** stopni, a nie
tylko dla przeliczonego zakresu.

### A4. „Klasyfikacja kompletna” w F1/F4 opierała się na ręcznym rozgałęzieniu

Wersja 1 wypisywała bazę Gröbnera i przechodziła do wniosku bez sprawdzenia rozgałęzień.
**Poprawka:** rozgałęzienia są teraz wykonywane w kodzie i każdy krok jest weryfikowany:

* F1: dodatkowo sprawdzana jest sama normalizacja — dla ogólnego ansatzu stopnia \(\le2\)
  z dowolną częścią liniową kod potwierdza
  \(\det J\big|_{(0,0)} = l_{11}l_{22}-l_{12}l_{21}\), więc niezerowa stała
  \(\det J\) wymusza odwracalną część liniową i normalizacja jest zupełna;
* F4: baza leks jest jawnie
  `[3a+f, b+g, c+3h, 3de-2fh+g², df+gh, dg+3h², 3eg-f², 9eh-fg, f(3fh-g²), g(3fh-g²), h(3fh-g²)]`;
  kod podstawia \(h=0\), \(g=0\), \(f=0\) i sprawdza, że:
  przypadek \(h=0,\ g\ne0\) redukuje się do \(g^2=0\) (sprzeczność),
  przypadek \(h=0,\ g=0\) redukuje się do \(3de=0\) i daje dokładnie dwie shersy,
  przypadek \(h\ne0,\ g=0\) redukuje się do \(3h^2=0\) (sprzeczność z \(h\ne0\)),
  a gałąź ogólna podstawiona do \(H\) daje dokładnie \((\lambda L^3,\mu L^3)\) z
  \(\lambda+t\mu=0\) (tożsamość sprawdzona: `identification_with_closed_form = (0,0)`).

### A5. Bezsensowny test „all_solutions_invertible” w F1

Wersja 1 sprawdzała tylko \(\det J\neq0\) i nazywała to odwracalnością. **Poprawka:**
każda gałąź dostaje jawną odwrotność i wynik podstawienia (`inverse_verified`), a nie
sam niezerowy wyznacznik.

### A6. Luka: nie było żadnej próby dla stopnia 3 (niejednorodnego)

Wersja 1 mogła sugerować, że F4 (jednorodne sześcienne) zamyka stopień 3. **To nieprawda**:
redukcja do przypadku jednorodnego (Bass–Connell–Wright) **nie zachowuje** wymiaru 2.
**Poprawka:** dodany lane F9, który wyprowadza dokładną strukturę mieszanego stopnia 2+3:

* część stopnia 1 równania \(\det J-1\) to dokładnie \(2a_1+b_2,\ a_2+2b_3\);
* część stopnia 4 to **dokładnie** \(\det J\) części sześciennej (sprawdzone: `True`);
* część stopnia 2 jest liniowa w \(a_4,a_5,a_6\), z jawnym rozwiązaniem
  \(a_4 = -\tfrac23 a_1b_2+\tfrac23 a_2b_1-\tfrac13 b_5\), \(a_5=-2a_1b_3+2a_3b_1-b_6\),
  \(a_6=-2a_2b_3+2a_3b_2-3b_7\);
* po tym zostaje układ w \((b_4,b_5,b_6,b_7)\), rozwiązywany dokładnie dla 2401
  całkowitych i 250 wymiernych danych kwadratowych.

Wynik: **w żadnym z 2651 przypadków nie istnieje niezerowa część sześcienna**; czyli
każde odwzorowanie Kellera w tej skanowanej klasie ma stopień \(\le2\) i jest objęte F1.
To jest wynik ograniczony (skan), nie twierdzenie — i tak jest teraz opisany.

### A7. Lane F8 wisiał i miał „dowód” tylko dla małych \(k\)

Wersja 1 liczyła symbolicznie odwrotność dla \(k\le7\) i przy \(k=10\) rozwinięcia rzędu
\(k^2=100\) zawieszały proces (900 s timeout). **Poprawka:** zamiast brutalnego
podstawiania kod weryfikuje trzy tożsamości, dla \(k=2,\dots,30\), symbolicznie w
\(\lambda,\mu,t\):
\(G_1+tG_2 = X+tY\), \(P(G)=X\), \(Q(G)=Y\) dla \(G=(X+t\mu L^k,\,Y-\mu L^k)\),
\(L=X+tY\). Czas: 6 s dla wszystkich 29 stopni; stopień odwrotności rośnie jak \(2k\).

### A8. Lane „tame” był sprzedawany jako dowód

Złożenia automorfizmów elementarnych są automatycznie automorfizmami — to **test
spójności**, a nie świadectwo przeciw hipotezie. Tak jest teraz opisane w kodzie
i w raporcie.

### A9. Nadmierne twierdzenia słowne

Wersja 1 pisała „nie ma czego podać” / sugerowała rozstrzygnięcie. **Poprawka:** raport
mówi teraz wprost: *nie znalazłem kontrprzykładu; mój przegląd jest skończony i nie
rozstrzyga hipotezy*. Twierdzenia o stanie wiedzy (że \(n=2\) jest otwarte) są oznaczone
jako **doniesienia z literatury** (Wikipedia, MathWorld, arXiv:2608.00222), których nie
mogę zweryfikować offline; jedyne, co weryfikuję sam, to przykład z \(n=3\) (F0).

---

## B. Co nadal jest słabe (świadomie, bez udawania, że nie jest)

1. **To nie jest dowód braku kontrprzykładu.** Kompletność mam tylko w: stopniu \(\le2\)
   (F1), rodzinie trójkątnej dla wszystkich stopni (F2), odwzorowaniach cubic-linear (F3),
   jednorodnych sześciennych (F4) i rodzinie jednej formy liniowej dla \(k\le30\) (F8).
   Pozostałe lane'y to skany ograniczone: F5 (pudełko \([-2,2]^8\)), F6 (66 losowych
   złożeń), F9 (2651 danych kwadratowych).
2. **Stopień \(\ge3\) poza F4/F8/F9 jest nietknięty.** Ogólne stopnie 4–100 (Moh) nie
   były tu liczone; nie mam też własnego, niezależnego sprawdzenia wyniku Moha.
3. **F9 to skan.** Struktura wyprowadzona dokładnie (stopnie 1, 2, 4) jest twierdzeniem,
   ale brak części sześciennej dla wszystkich danych kwadratowych — nie.
4. **Literatura.** Stan „\(n=2\) otwarte” pochodzi z wyszukiwania, nie z moich obliczeń.
   Gdyby hipoteza została rozstrzygnięta poza dostępnymi mi źródłami, moja odpowiedź o
   stanie wiedzy byłaby nieaktualna — same obliczenia pozostają poprawne.
5. **F6, F7 są ilustracyjne**, nie są dowodami czegokolwiek o hipotezie.
6. **Zakres współczynników algebraicznych.** Wszystkie konstrukcje są nad \(\mathbb Q\)
   (lub ciałem funkcji z parametrami); nie konstruowałem odwzorowań o współczynnikach
   algebraicznych niewymiernych. Hipoteza jest niezmiennicza względem rozszerzeń ciała,
   ale to nie znaczy, że przeszukałem te przypadki.

---

## C. Dlaczego nadal nie podaję pary \((P,Q)\)

Polecenie żądało w odpowiedzi końcowej wyłącznie dwóch wielomianów. Taka para musi
spełniać (J) i (C). Wszystko, co skonstruowałem i zweryfikowałem, spełnia (J) i **jest
odwracalne** (jawna odwrotność + włókno mocy 1) albo spełnia (C) i ma **nie-stały**
wyznacznik. Nie mam trzeciej możliwości: podanie dowolnej pary bez tych testów to
wpisanie fałszu, który każdy czytelnik obali w kilkanaście sekund w SymPy. Dlatego
wynikiem jest certyfikat tego, co sprawdzone, a nie wymyślona para.

Najuczciwsza jednozdaniowa odpowiedź na pierwotne polecenie: **nie istnieje znany
kontrprzykład w \(\mathbb C^2\), a moje dokładne przeliczenia wszystkich domkniętych klas
odwzorowań Kellera w płaszczyźnie nie dały żadnego; jedyne certyfikaty, jakie mogę
przedstawić, to odwracalność (dla (J)) i nie-stałość wyznacznika (dla kolizji).**

---

## D. Mapa poprawek: co, gdzie, jak sprawdzone

| # | słaby punkt | poprawka w kodzie | sprawdzenie |
|---|---|---|---|
| A1 | liczba punktów włókna = liczba pierwiastków | `fibre()` → `_standard_monomials()` (wymiar ilorazu) | `test_fibre_count_is_quotient_dimension_not_distinct_roots`; w transkrypcie F4 pokazuje oba liczniki |
| A2 | dzielenie przez \(t\), założenia \(\ne0\) | F3 bez założeń; wzór \(1+3L^2(s^3m+t^3n)\) | `formula_verified`, `identity_on_nilpotency_locus == 0`, `keller_equals_nilpotent` |
| A3 | trójkątne tylko do stopnia 4 | tożsamości dla ogólnych współczynników | `structural_identity`, `leading_y_coefficient_matches` dla \(d=1..4\) |
| A4 | ręczne rozgałęzienia | rozgałęzienia wykonywane i weryfikowane | `linear_relations_in_basis`, `case1_*`, `case2_g_zero["forces_h_zero"]`, `identification_with_closed_form` |
| A5 | det \(\ne0\) jako „odwracalność” | jawne odwrotności na gałęziach | `inverse_verified` |
| A6 | brak stopnia 3 | nowy lane F9 | `degree_four_matches_cubic_jacobian`, 2651 skanów |
| A7 | zawieszenie F8 | tożsamości \(L\)-niezmienniczości | 29 stopni w 6 s, `all_verified` |
| A8 | „tame” jako dowód | opisane jako test spójności | 66/66 odwrotności |
| A9 | nadmierne twierdzenia | sekcja „co nadal jest słabe” | ten dokument, §B |

Testy: `python -m pytest -q` → **32 passed** (26 testów pakietu + 6 nowych).

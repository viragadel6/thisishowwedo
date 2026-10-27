# Dwuwymiarowa hipoteza Jacobiego — raport z dokładnego poszukiwania (wersja 2, po krytyce)

**Data:** 27 października 2026
**Cel:** \(P,Q\in\mathbb C[x,y]\) o współczynnikach wymiernych/algebraicznych, takie że
**(J)** \(\det J = P_xQ_y-P_yQ_x\) jest niezerową stałą oraz **(C)** \((x,y)\mapsto(P(x,y),Q(x,y))\) nie jest wstrzykujące.

**Wynik: nie znalazłem takiej pary i żadnej nie podaję.** To nie jest wynik pozytywny;
poniżej jest dokładnie to, co zostało policzone i sprawdzone, wraz z listą rzeczy, których
**nie** udowodniłem. Wersja 1 tego raportu miała realny błąd metodologiczny (sposób
liczenia punktów włókna) i kilka nadużyć — poprawki opisuje `reports/self_critique.md`.

Pliki:
* `scripts/jc_planar_search.py` — cały kod (lane'y F0–F9), wersja 2,
* `reports/planar_search_transcript.txt` — pełny zapis przebiegu (826,7 s),
* `reports/self_critique.md` — krytyka wersji 1 i mapa poprawek,
* `tests/test_planar_search.py` — 6 szybkich testów regresyjnych,
* `reports/repo_tool_output.txt` — wynik narzędzia `exact_formula_search` z repo.

Testy: `python -m pytest -q` → **32 passed** (26 pakietu + 6 nowych).

---

## 1. Stan wiedzy a to, co sam sprawdziłem

* **Sprawdzone tutaj, własnym rachunkiem (kontrola pozytywna F0):** znany przykład z
  \(\mathbb C^3\),
  \(P=(1+xy)^3z+y^2(1+xy)(4+3xy)\), \(Q=y+3x(1+xy)^2z+3xy^2(4+3xy)\), \(R=2x-3x^2y-x^3z\),
  ma \(\det J=-2\) (dwiema niezależnymi drogami) oraz trzy różne punkty wymierne
  \((-1,\tfrac32,\tfrac{13}2)\), \((0,0,-\tfrac14)\), \((1,-\tfrac32,\tfrac{13}2)\) o wspólnym
  obrazie \((-\tfrac14,0,0)\). Czyli pipeline wykrywa prawdziwy kontrprzykład; brak wyniku
  w \(\mathbb C^2\) nie jest artefaktem kodu.
* **Doniesienia literatury (nie weryfikowałem offline):** hipoteza jest obalona dla
  \(n\ge3\) i otwarta dla \(n=2\) — Wikipedia „Jacobian conjecture”, MathWorld, przegląd
  arXiv:2608.00222 (tam też: Moh sprawdził stopnie \(\le100\), Wang stopnie \(\le2\)).
  Traktuję to jako tło, nie jako element mojego dowodu.

## 2. Jak mierzę wstrzykującość (poprawiona metoda)

Dla kandydata z (J) odwzorowanie jest étale, więc ideał włókna jest radykalny (kryterium
Jakobiego) i liczba punktów włókna nad \(\mathbb C\) **równa się**

\[
\dim_{\mathbb Q}\mathbb Q[x,y]\big/\big(P-w_1,\;Q-w_2\big)
=\#\{\text{monomiany standardowe bazy Gröbnera}\}.
\]

Wersja 1 liczyła tylko różne pierwiastki wielomianu eliminującego, co jest jedynie dolnym
ograniczeniem: dla \((x^2,y^2)\) w punkcie \((1,1)\) daje \(2\), a włókno ma \(4\) punkty.
Teraz kod liczy wymiar ilorazu, a licznik pierwiastków wypisuje obok jako kontrolę.
Moc włókna \(>1\) **dowodzi** (C) i daje dokładnych algebraicznych partnerów kolizji;
moc \(1\) (razem z jawną odwrotnością sprawdzoną podstawieniem) poświadcza iniektywność.

## 3. Co jest domknięte dokładnie

### 3.1 Stopień \(\le 2\) — klasyfikacja kompletna (F1)

Normalizacja jest uprawniona: dla ogólnego ansatzu stopnia \(\le2\) z dowolną częścią
liniową kod potwierdza \(\det J|_{(0,0)}=l_{11}l_{22}-l_{12}l_{21}\), więc niezerowa stała
\(\det J\) wymusza odwracalną część liniową (a zmiany afiniczne źródła i celu są
bijekcjami, zachowującymi (J) i (C)). Po normalizacji układ \(\det J\equiv1\) ma bazę

```
[2a + e, b + 2f, 2cd + ef, ce + 2f², 4df - e²]
```

Gałęzie: \(a=-\tfrac e2,\ b=-2f,\ c=-\tfrac{2f^2}{e},\ d=\tfrac{e^2}{4f}\) oraz degeneracja
\(a=b=d=e=f=0,\ cd=0\). Obie mają \(\det J=1\) i **jawną odwrotność wielomianową
sprawdzoną podstawieniem**. Rodzina ogólna:

\[
P=x+a\Bigl(x-\tfrac fa y\Bigr)^2,\quad Q=y+\tfrac{a^2}{f}\Bigl(x-\tfrac fa y\Bigr)^2,\quad
\det J\equiv1,\quad P-\tfrac fa Q = x-\tfrac fa y \text{ (współrzędna celu)} .
\]

Członek wymierny: \(P=2x^2-6xy+x+\tfrac92y^2\), \(Q=\tfrac43x^2-4xy+3y^2+y\);
\(\det J=1\), włókno \((0,0)\) mocy \(1\), odwrotność
\((-2X^2+6XY+X-\tfrac92Y^2,\ -\tfrac43X^2+4XY-3Y^2+Y)\) weryfikuje się podstawieniem.

### 3.2 Rodzina trójkątna — kompletna dla **wszystkich** stopni (F2)

Kod weryfikuje dla ogólnych współczynników symbolicznych (dla \(\deg_y P=d=1,2,3,4\)):

\[
\det J = -P_y\,f'(x),\qquad [y^{d-1}]\det J = -d\,p_d(x)\,f'(x).
\]

Gdyby \(\det J\) była niezerową stałą, to \(p_d(x)f'(x)\) byłaby niezerową stałą, więc
\(d=1\) i \(f'\) stałe; wtedy \(P=p_0(x)+cy\), \(Q=q_0+q_1x\), \(\det J=-c\,q_1\), z jawną
odwrotnością (podstawienie daje \((0,0)\)). To rozumowanie nie ma ograniczenia stopnia.

### 3.3 Odwzorowania „cubic-linear” \(X+(AX)^{*3}\) — bez założeń o niezerowości (F3)

Dla \(A=uv^{T}\), \(L=v\cdot(x,y)\):

\[
\det J = 1+3L^{2}\,(s^3m+t^3n) \quad\text{(weryfikacja symboliczna)},\qquad
sm+tn=0\ \Rightarrow\ s^3m+t^3n = tn\,(t^2-s^2).
\]

Stałość wymaga \(t^2=s^2\) (lub \(A=0\)); wtedy \(\det J=1\) i odwzorowanie jest postaci
\((\lambda L^3,\mu L^3)\) z jawną odwrotnością. Wszystkie przypadki (w tym shersy
\(sm=tn=0\)) mają sprawdzone odwrotności. Skan 625 macierzy o współczynnikach w \([-2,2]\)
daje **17** przypadków z niezerową stałą \(\det J\) i **dokładnie te same 17** macierzy
nilpotentnych (`keller_equals_nilpotent = True`).

### 3.4 Jednorodne sześcienne — klasyfikacja kompletna (F4)

Baza leks układu \(\det(I+JH)\equiv1\):

```
[3a+f, b+g, c+3h, 3de-2fh+g², df+gh, dg+3h², 3eg-f², 9eh-fg, f(3fh-g²), g(3fh-g²), h(3fh-g²)]
```

Rozgałęzienia wykonane i sprawdzone w kodzie: \(h=0,\ g\ne0\) redukuje się do \(g^2=0\)
(sprzeczne); \(h=0,\ g=0\) daje \(3de=0\), czyli dwie shersy \((x,\,y+ex^3)\), \((x+dy^3,\,y)\)
z odwrotnościami; \(h\ne0,\ g=0\) redukuje się do \(3h^2=0\) (sprzeczne z \(h\ne0\));
gałąź ogólna podstawiona daje dokładnie

\[
H=(\lambda L^3,\ \mu L^3),\quad L=x+ty,\quad \lambda+t\mu=0 \ \ \Rightarrow\ \ \det J\equiv1,
\]
\[
(x,y)=\bigl(X+t\mu (X+tY)^3,\; Y-\mu (X+tY)^3\bigr)\ \text{— odwrotność wielomianowa, podstawienie } (0,0).
\]

Członek wymierny: \(P=x-\tfrac23x^3-\tfrac4{15}x^2y-\tfrac8{225}xy^2-\tfrac{16}{10125}y^3\),
\(Q=y+5x^3+2x^2y+\tfrac4{15}xy^2+\tfrac8{675}y^3\), \(\det J=1\), włókno mocy \(1\).

### 3.5 Jedna forma liniowa w każdym stopniu (F8)

\[
P=x+\lambda L^k,\quad Q=y+\mu L^k,\quad L=x+ty,\qquad
\det J = 1+k(\lambda+t\mu)L^{k-1}
\]

(weryfikacja symboliczna dla każdego \(k=2,\dots,30\)). Stałość \(\iff \lambda+t\mu=0\);
wtedy \(L(X,Y)=X+tY\) jest zachowana przez \(G=(X+t\mu L^k,\ Y-\mu L^k)\) i
\(P(G)=X,\ Q(G)=Y\) — trzy tożsamości sprawdzone symbolicznie dla wszystkich 29 stopni
(stopień odwrotności rośnie jak \(2k\)). Czyli w tej rodzinie **każdy** stopień daje
bijekcję, nie kontrprzykład.

### 3.6 Stopień mieszany 2+3 (F9) — nowy lane, wynik ograniczony

Wyprowadzone i sprawdzone strukturalnie: część stopnia 1 równania \(\det J-1\) to
\(2a_1+b_2,\ a_2+2b_3\); część stopnia 4 to **dokładnie** \(\det J\) części sześciennej;
część stopnia 2 jest liniowa w \(a_4,a_5,a_6\), z jawnym rozwiązaniem
\(a_4=-\tfrac23a_1b_2+\tfrac23a_2b_1-\tfrac13b_5\), \(a_5=-2a_1b_3+2a_3b_1-b_6\),
\(a_6=-2a_2b_3+2a_3b_2-3b_7\). Zostaje układ w \((b_4,b_5,b_6,b_7)\), rozwiązywany dokładnie
dla 2401 całkowitych i 250 wymiernych danych kwadratowych. Wynik: **w żadnym z 2651
przypadków nie istnieje niezerowa część sześcienna** — w skanowanej klasie warunek (J)
wymusza stopień \(\le2\), czyli F1. To skan, nie twierdzenie.

## 4. Skan ograniczony i kontrola spójności

* **F5:** pudełko \([-2,2]^8\), 390 625 ósemek współczynników: **9** przypadków z niezerową
  stałą \(\det J\) — wszystkie to shersy \((x+cy^3,y)\), \((x,y+cx^3)\), identyczność;
  wszystkie z odwrotnością i włóknem mocy 1.
* **F6:** 66 losowych złożeń automorfizmów elementarnych (shears, skalowania, stopnie do 6):
  66/66 ma \(\det J\equiv1\) i jawną odwrotność. **To test spójności, nie świadectwo** —
  złożenia automorfizmów są automatycznie automorfizmami.
* **F7 (kontrast):** odwzorowania, które **naprawdę kolidują**, ale mają nie-stały
  wyznacznik: \((x^2,\,y+x^3)\) z \(\det J=2x\) i kolizją \((1,0)\sim(-1,2)\);
  \((x^3+x,\,y+x^3)\) z \(\det J=3x^2+1\) i kolizją \((1,0)\sim(-\tfrac12-\tfrac{\sqrt7}2i,\,-\tfrac32-\tfrac{\sqrt7}2i)\);
  \((x+y^2,\,y+x^2)\) z \(\det J=1-4xy\) i kolizją \((1,0)\sim(0,1)\);
  \((x+xy,\,y+xy)\) z \(\det J=1+x+y\) i kolizją \((1,0)\sim(-1,-2)\). Wszystkie kolizje
  potwierdzone podstawieniem, wszystkie wyznaczniki jawnie nie-stałe i zerujące się
  dokładnie na odpowiednich miejscach.

## 5. Czego **nie** udowodniłem (jawne granice)

1. Brak kontrprzykładu w \(\mathbb C^2\) **nie został tu udowodniony**; przeszukane klasy są
   skończone lub parametryczne, nie wszystkie.
2. Kompletność: F1 (stopień \(\le2\)), F2 (wszystkie stopnie, rodzina trójkątna), F3
   (cubic-linear), F4 (jednorodne sześcienne), F8 (rodzina jednej formy liniowej,
   \(k\le30\)). Reszta to skany.
3. Ogólne stopnie \(\ge3\) poza F4/F8/F9 są nietknięte; nie mam własnego, niezależnego
   sprawdzenia wyniku „stopnie \(\le100\)” z literatury.
4. F9 jest skanem 2651 przypadków: struktura stopni 1, 2, 4 jest twierdzeniem, brak części
   sześciennej dla *wszystkich* danych kwadratowych — nie.
5. Nie konstruowałem odwzorowań o współczynnikach algebraicznych niewymiernych.
6. Stwierdzenia o stanie wiedzy (\(n=2\) otwarte, \(n\ge3\) obalone) są z literatury, nie
   z moich obliczeń; samodzielnie zweryfikowałem tylko konkretny przykład 3-wymiarowy (F0).

## 6. Wniosek

W każdej rodzinie, w której rachunek udało się domknąć, warunek (J) pociąga odwracalność
z jawną odwrotnością wielomianową, a każda skonstruowana kolizja ma nie-stały wyznacznik.
Nie znalazłem pary spełniającej (J) i (C) i **nie podaję żadnej**, bo podanie pary bez
tych dwóch testów byłoby po prostu fałszem, sprawdzalnym w kilka sekund. Naturalne
dalsze kierunki: konstrukcje typu „tangent sweep” w \(\mathbb C^2\) (przemiatanie prostymi
stycznymi do krzywej płaskiej) i redukcje Yagzheva–Drużkowskiego z dodatkowymi wymiarami
pomocniczymi.

## 7. Odtworzenie

```bash
pip install sympy pytest
python scripts/jc_planar_search.py          # wszystkie lane'y, ~14 min
python scripts/jc_planar_search.py F1,F4    # pojedyncze lane'y
python -m pytest -q                          # 26 testów pakietu + 6 nowych
python -m exact_formula_search "refute the Jacobian conjecture in two dimensions: \
  find polynomials P and Q in two variables whose jacobian determinant is a nonzero \
  constant while the map is not injective"
```

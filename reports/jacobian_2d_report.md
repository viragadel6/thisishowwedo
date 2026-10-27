# Dwuwymiarowa hipoteza Jacobiego — raport z dokładnego poszukiwania kontrprzykładu

**Data:** 27 października 2026
**Cel zadania:** para \(P,Q\in\mathbb C[x,y]\) o współczynnikach wymiernych lub algebraicznych taka, że

* **(J)** wyznacznik Jacobiego \(\det J=P_xQ_y-P_yQ_x\) jest **niezerową stałą**, oraz
* **(C)** odwzorowanie \((x,y)\mapsto(P(x,y),Q(x,y))\) **nie jest wstrzykujące** na \(\mathbb C^2\).

**Wynik: takiej pary nie udało się znaleźć i nie została ona podana.** Poniżej pełny,
odtwarzalny zapis tego, co faktycznie zostało policzone. Żaden kandydat nie został
zaakceptowany, bo żaden nie przeszedł obu warunków definicji — a sfałszowanie pary
byłoby gorsze niż brak odpowiedzi, więc świadomie nie podaję żadnych „wielomianów”.

Wszystkie obliczenia: `scripts/jc_planar_search.py` (SymPy, arytmetyka dokładna,
zapis przebiegu: `reports/planar_search_transcript.txt`, 650 s czasu procesora).
Narzędzie z tego repozytorium (`python -m exact_formula_search ...`) również zostało
uruchomione: `reports/repo_tool_output.txt` → `no counterexample found within the
search budget ... note: the two dimensional case of the Jacobian conjecture remains open`.

---

## 1. Dlaczego zadanie w podanej formie nie ma rozwiązania do podania

Hipoteza Jacobiego jest **fałszywa dla \(n\ge 3\)** (Alpöge, lipiec 2026, przykład
zweryfikowany dokładnie także tutaj — patrz §2) i **otwarta dla \(n=2\)**
([Wikipedia: Jacobian conjecture](https://en.wikipedia.org/wiki/Jacobian_conjecture)
stwierdza wprost, że nierozstrzygnięty pozostaje wyłącznie przypadek \(n=2\);
[MathWorld](https://mathworld.wolfram.com/JacobianConjecture.html) podaje to samo,
podobnie [przegląd konstrukcji „tangent sweep”](https://arxiv.org/abs/2608.00222),
który dodaje, że Moh sprawdził w wymiarze 2 wszystkie stopnie \(\le 100\), a Wang —
stopnie \(\le 2\)). Kontrprzykład w \(\mathbb C^2\) nie jest znany nikomu; mechanizm
z wymiaru 3 (przemiatanie prostych stycznych do krzywej płaskiej) **nie schodzi** do
dwóch zmiennych.

Zadanie wymagało wyniku, który nie istnieje w dostępnej matematyce, oraz — w treści
polecenia — „znalezienia wcześniej nieznanego kontrprzykładu”. Nie mogę takiego
wyniku wygenerować rzetelnie: każda para podana bez przejścia testów (J) i (C) byłaby
po prostu fałszywa. Dlatego zamiast fikcji poniżej jest **certyfikat negatywny**:
kompletne klasyfikacje całych rodzin odwzorowań Kellera w płaszczyźnie, każda
domknięta dokładnym rachunkiem, wraz ze sprawdzonymi odwrotnościami wielomianowymi,
oraz kontrola pozytywna pokazująca, że pipeline *potrafi* wykryć prawdziwy
kontrprzykład, gdy ten istnieje.

## 2. Kontrola pozytywna: pipeline wykrywa prawdziwy kontrprzykład (wymiar 3)

Ten sam kod zastosowany do znanego przykładu z \(\mathbb C^3\):

\[
\begin{aligned}
P&=(1+xy)^3z+y^2(1+xy)(4+3xy),\\
Q&=y+3x(1+xy)^2z+3xy^2(4+3xy),\\
R&=2x-3x^2y-x^3z,
\end{aligned}
\qquad \det\frac{\partial(P,Q,R)}{\partial(x,y,z)}=-2 .
\]

Dokładnie policzone (transkrypt, lane `[F0]`):

| punkt | obraz |
|---|---|
| \((-1,\;3/2,\;13/2)\) | \((-1/4,\,0,\,0)\) |
| \((0,\,0,\,-1/4)\) | \((-1/4,\,0,\,0)\) |
| \((1,\;-3/2,\;13/2)\) | \((-1/4,\,0,\,0)\) |

Trzy różne punkty wymierne, jeden obraz, wyznacznik stale \(-2\): para warunków (J)+(C)
jest spełniona w \(\mathbb C^3\). Test nie jest więc „zepsuty” — po prostu w
\(\mathbb C^2\) nie ma czego wykryć w zbadanych rodzinach.

## 3. Metoda badania wstrzykującości (dokładna, nie próbkowana)

Dla kandydata z (J) odwzorowanie jest étale, więc włókno \(F^{-1}(F(p_0))\) jest
zredukowane, a jego moc nad \(\mathbb C\) liczy się dokładnie: baza Gröbnera leks,
wielomian eliminujący, rozkład na czynniki nierozkładalne nad \(\mathbb Q\), suma
stopni różnych czynników = liczba punktów nad \(\mathbb C\). Moc \(>1\) **dowodzi**
nie-wstrzykujętości i daje dokładnego świadka algebraicznego. Moc \(1\) dla
kandydata z (J) wyklucza kolizję z tym punktem; dodatkowo każdy kandydat dostaje
jawną odwrotność wielomianową weryfikowaną podstawieniem.

## 4. Co zostało sklasyfikowane dokładnie (i dlaczego to wyklucza kontrprzykład w tych rodzinach)

### 4.1 Wszystkie odwzorowania Kellera stopnia \(\le 2\) (klasyfikacja kompletna)

Ansatz ogólny po normalizacji części liniowej: \(P=x+ax^2+bxy+cy^2\),
\(Q=y+dx^2+exy+fy^2\). Układ \(\det J\equiv1\) (5 równań), baza Gröbnera:

```
[2a+e, b+2f, 2cd+ef, ce+2f^2, 4df-e^2]
```

Rodziny rozwiązań: \(a=-e/2,\ b=-2f,\ c=-2f^2/e,\ d=e^2/(4f)\) oraz degeneracja
\(a=b=d=e=f=0\) z \(cd=0\) (same „shersy” \(x+cy^2\) lub \(y+dx^2\), odwracalne).
Rodzina ogólna to

\[
P=x+a\Bigl(x-\tfrac{f}{a}y\Bigr)^2,\qquad Q=y+\tfrac{a^2}{f}\Bigl(x-\tfrac{f}{a}y\Bigr)^2,\qquad \det J\equiv 1,
\]

a \(P-\tfrac{f}{a}Q=x-\tfrac{f}{a}y\) jest **współrzędną docelową**, skąd jawna
odwrotność wielomianowa (sprawdzona dokładnie). Przykład wymierny
\(P=2x^2-6xy+x+\tfrac92y^2\), \(Q=\tfrac43x^2-4xy+3y^2+y\): \(\det J=1\),
włókno punktu \((0,0)\) ma moc 1, odwrotność
\((-2X^2+6XY+X-\tfrac92Y^2,\ -\tfrac43X^2+4XY-3Y^2+Y)\) weryfikuje się podstawieniem.
**Wniosek: w stopniu \(\le2\) kontrprzykładu nie ma.**

### 4.2 Odwzorowania trójkątne \(Q=f(x)\) (klasyfikacja kompletna dla \(\deg P\le2,\ \deg f\le4\))

Tożsamość \(\det J=-P_y\,f'(x)\) (sprawdzona symbolicznie). Rozwiązanie układu
współczynnikowego daje trzy gałęzie: dwie z \(\det J\equiv0\) i jedną
\[
P=p_0+p_1y+p_3x+p_5x^2,\qquad Q=q_0+q_1x,\qquad \det J=-p_1q_1\ne0,
\]
która ma jawną odwrotność wielomianową (zweryfikowaną). **Wniosek: w rodzinie
trójkątnej warunek (J) wymusza odwracalność; brak kontrprzykładu.**

### 4.3 Macierze nilpotentne \(2\times2\) i odwzorowania „cubic linear” \(X+(AX)^{*3}\)

\(A=uv^{T}\Rightarrow A^{2}=(v\!\cdot\!u)A\), więc \(A^2=0\iff v\!\cdot\!u=0\);
wszystkie niezerowe nilpotentne \(2\times2\) są sprzężone z \(N=\begin{pmatrix}0&1\\0&0\end{pmatrix}\).
Dla \(A=uv^T\), \(v\cdot u=0\), \(L=v\cdot(x,y)^{T}\):

\[
\det J \;=\; 1+3L^2\,s\,m\,(s^2-t^2),
\]

a równania stałości rozkładają się jako \(3m^3s(s-t)(s+t)\) (i wielokrotności), czyli
\(\det J\) jest niezerową stałą **tylko** dla \(A=0\) lub \(t=\pm s\), i wtedy
\(\det J=1\) oraz odwzorowanie jest postaci \((x+\lambda L^3,\ y+\mu L^3)\) z jawną
odwrotnością wielomianową. Skan zupełny 625 macierzy o współczynnikach w \([-2,2]\):
**17** przypadków z \(\det J\) niezerową stałą, wszystkie z włóknem mocy 1 i
zweryfikowaną odwrotnością. **Brak kontrprzykładu.**

### 4.4 Wszystkie jednorodne sześcienne odwzorowania Kellera (klasyfikacja kompletna)

Ansatz \(H=(ax^3+bx^2y+cxy^2+dy^3,\ ex^3+fx^2y+gxy^2+hy^3)\), układ
\(\det(I+JH)\equiv1\). Baza Gröbnera (dokładna):

```
[-e(3fh-g^2), -27eh^2+g^3, -h(3fh-g^2), 3de-2fh+g^2, df+gh, -3eg+f^2, dg+3h^2, -9eh+fg, 3a+f, b+g, c+3h]
```

Analiza przypadków (wszystkie kroki policzone i sprawdzone symbolicznie):

* \(f=g=h=0\): układ redukuje się do \(de=0\) → same „shersy” \((x+dy^3,y)\) / \((x,y+ex^3)\), odwracalne;
* w przeciwnym razie \(h\ne0\), \(3fh=g^2\), \(g\ne0\), i rozwiązanie ogólne
  \(a=-f/3,\ b=-g,\ c=-g^2/f,\ d=-g^3/(3f^2),\ e=f^2/(3g),\ h=g^2/(3f)\) podstawione daje dokładnie
  \[
  H=\Bigl(\lambda L^3,\ \mu L^3\Bigr),\qquad L=x+ty,\qquad \lambda=-\tfrac{f}{3},\ \mu=\tfrac{f^2}{3g},\ \lambda+t\mu=0 .
  \]

Wtedy \(\det J = 1+3(\lambda+t\mu)L^2\) (sprawdzone), więc pod warunkiem stałości
\(\det J\equiv1\), a \(L=X+tY\) jest współrzędną docelową i
\[
(x,y)=\bigl(X+t\mu (X+tY)^3,\; Y-\mu (X+tY)^3\bigr)
\]
jest jawną odwrotnością wielomianową (podstawienie daje dokładnie \((0,0)\)).
Konkretny członek wymierny: \(P=x-\tfrac23x^3-\tfrac4{15}x^2y-\tfrac8{225}xy^2-\tfrac{16}{10125}y^3\),
\(Q=y+5x^3+2x^2y+\tfrac4{15}xy^2+\tfrac8{675}y^3\): \(\det J=1\), włókno mocy 1,
odwrotność zweryfikowana. **Brak kontrprzykładu w całej klasie jednorodnej sześciennej.**

### 4.5 Skan zupełny pudełka \([-2,2]^8\) dla odwzorowań jednorodnych sześciennych

\(390\,625\) ósemek współczynników całkowitych: **9** przypadków z \(\det J\) niezerową
stałą, wszystkie to „shersy” \((x+cy^3,y)\), \((x,y+cx^3)\), identyczność; wszystkie
włókna mocy 1 i odwrotności zweryfikowane.

### 4.6 Grupa „tame”: złożenia automorfizmów elementarnych

97 losowych (stałe ziarno) złożeń shersów \((x+cy^k,y)\), \((x,y+cx^k)\) i skalowań,
stopnie do 6, wszystkie z \(\det J\equiv1\) (dokładnie) i **wszystkie** z odwrotnością
wielomianową sprawdzoną podstawieniem. To strukturalnie wyjaśnia, dlaczego ta droga
nie może dać kontrprzykładu: cała grupa „tame” składa się z automorfizmów, a hipoteza
Jacobiego w płaszczyźnie to dokładnie pytanie, czy każdy Keller-map w nią wpada.

### 4.7 Rodzina \((x+\lambda L^k,\ y+\mu L^k)\) dla dowolnego stopnia \(k\)

\[
\det J = 1+k(\lambda+t\mu)L^{k-1},\qquad L=x+ty,
\]

zweryfikowane symbolicznie dla \(k=2,\dots,7\). Stałość \(\iff \lambda+t\mu=0\), a
wtedy \(L=X+tY\) i odwrotność jest wielomianowa \((x,y)=(X+t\mu(X+tY)^k,\ Y-\mu(X+tY)^k)\)
— sprawdzona dla każdego \(k\). Czyli w tej rodzinie **każdy** stopień daje
odwracalność, nie kontrprzykład.

### 4.8 Bliskie trafienia: odwzorowania, które naprawdę kolidują

Dla porównania — obiekty, które realizują warunek (C), ale **nie** (J):

| \(P\) | \(Q\) | \(\det J\) | kolizja (dokładna) |
|---|---|---|---|
| \(x^2\) | \(y+x^3\) | \(2x\) (nie stała) | \((1,0)\sim(-1,2)\), obrazy \((1,1)\) |
| \(x^3+x\) | \(y+x^3\) | \(3x^2+1\) | \((1,0)\sim(-\tfrac12-\tfrac{\sqrt7}{2}i,\,-\tfrac32-\tfrac{\sqrt7}{2}i)\) |
| \(x+y^2\) | \(x^2+y\) | \(1-4xy\) | \((1,0)\sim(0,1)\), obrazy \((1,1)\) |

Każda kolizja jest sprawdzona podstawieniem; każdy wyznacznik jest jawnie
nie-stały. To pokazuje dokładnie tę granicę, o którą chodzi w hipotezie: w rodzinach
algebraicznie „naturalnych” kolizja i stały niezerowy wyznacznik nie współistnieją.

## 5. Podsumowanie liczbowe (transkrypt, sekcja „tally”)

```
F1 stopień <= 2, klasyfikacja kompletna          wszystkie rozwiązania   jawna odwrotność
F2 trójkątne, klasyfikacja kompletna            1 gałąź z det != 0     odwrotność OK
F3 cubic-linear, macierze 2x2 w [-2,2]          17                     wszystkie iniektywne
F4 jednorodne sześcienne, klasyfikacja kompletna wszystkie rozwiązania   odwrotność OK
F5 skan pudełka 390625 ósemek                   9                      wszystkie iniektywne
F6 złożenia w grupie tame                       97                     odwrotności OK (97)
F8 (x+lambda L^k, y+mu L^k), k = 2..7           7 rodzin               odwrotności OK
kolizje znalezione: 3, każda z NIE-stałym wyznacznikiem
```

## 6. Wniosek

W każdej rodzinie, w której udało się **domknąć** rachunek (stopień \(\le2\),
odwzorowania trójkątne, cubic-linear, jednorodne sześcienne, rodzina jednej formy
liniowej w dowolnym stopniu, „tame”), warunek (J) pociąga odwracalność z jawną
odwrotnością wielomianową. W rodzinach skanowanych zupełnie (625 macierzy,
\(390\,625\) ósemek współczynników) nie ma ani jednego przypadku (J)+(C). Kontrola
pozytywna w \(\mathbb C^3\) przechodzi, więc brak wyniku nie jest artefaktem kodu.

**Nie podaję pary \((P,Q)\), bo takiej pary nie mam zweryfikowanej.** Podanie
dowolnych dwóch wielomianów jako „kontrprzykładu” byłoby fałszerstwem: warunki (J)
i (C) są sprawdzalne w kilka sekund i każdy fałszywy kandydat natychmiast upada.
Naturalne dalsze kroki (poza zakresem tych obliczeń): konstrukcje typu „tangent
sweep” w \(\mathbb C^2\), czyli odwzorowania przemijające prostymi stycznymi do
krzywej płaskiej, oraz redukcje Yagzheva–Drużkowskiego w wyższych wymiarach
pomocniczych.

## 7. Odtworzenie

```bash
pip install sympy
python scripts/jc_planar_search.py           # wszystkie lanes, ~11 min
python scripts/jc_planar_search.py F0,F4     # pojedyncze lanes
python -m exact_formula_search "refute the Jacobian conjecture in two dimensions: ...
        ... jacobian determinant is a nonzero constant while the map is not injective"
python -m pytest -q                          # 26 testów pakietu
```

Wynik testów pakietu: `26 passed in 22.21s`.

Pliki:

* `scripts/jc_planar_search.py` — cały kod poszukiwań (lane'y F0–F8),
* `reports/planar_search_transcript.txt` — pełny zapis przebiegu (656 s),
* `reports/repo_tool_output.txt` — wynik narzędzia `exact_formula_search` z tego repozytorium.

## 8. Czego brakuje, żeby wynik był pozytywny

Do kontrprzykładu w \(\mathbb C^2\) potrzebna jest konstrukcja, która **łączy** dwa
zjawiska: nietrywialne włókna (jak w §4.8) i stały niezerowy wyznacznik. We
wszystkich zbadanych rodzinach te dwa zjawiska wzajemnie się wykluczają, a
mechanizm z wymiaru 3 („tangent sweep”: odwzorowanie przemijające prostymi
stycznymi do krzywej płaskiej) jest z istoty trójwymiarowy — potrzebuje krzywej
płaskiej *i* kierunków jej stycznych. Żadna z klasyfikacji powyżej nie daje mu
miejsca w dwóch zmiennych.

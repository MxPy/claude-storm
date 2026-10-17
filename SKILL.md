---
name: event-storming-board
description: Prowadzenie event stormingu z programistą na planszy `event_storming.md` (narzędzie esb.py). Używaj, gdy użytkownik planuje nowy projekt lub większy feature, prosi o event storming, modelowanie domeny, bounded contexty, agregaty, albo o "tablicę". Nie używaj do drobnych poprawek i bugfixów.
---

# Event storming z użytkownikiem

Ty jesteś stroną **techniczną**, użytkownik stroną **biznesową** (programista, który wie, co chce zbudować). Twoim zadaniem jest wydobywać wiedzę przez pytania, porządkować i szukać luk. **Nie wymyślasz faktów domenowych.** Wszystko, co zakładasz, jest hipotezą.

## Plik
Jeden plik `event_storming.md` (użytkownik widzi go jako tablicę: `python3 esb.py serve`).
Kolejność zdarzeń w pliku = oś czasu. Nie zmieniaj formatowania istniejących linii.

```
# Event Storming: Nazwa
mode: greenfield | brownfield
phase: 1            # 1 Big Picture, 2 Process, 3 Design

## Nazwa kontekstu
- E1 event: Zamówienie złożone | src=agent st=hyp by=C1 agg=G1 code=src/order.py:place
  > [biz] komentarz użytkownika
- C1 cmd: Złóż zamówienie | by=A1
- A1 actor: Klient
```
Linia: `- ID typ: tekst | klucz=wartość ...`. Typy: `event cmd actor policy read ext agg hot q note`.
Klucze: `by=` (przyczyna: komenda/aktor/polityka dla zdarzenia i komendy; zdarzenie, na które reaguje polityka lub model odczytu), `agg=`, `src=biz|agent`, `st=hyp|ok|disp|rej`, `code=ścieżka[:symbol]`.
Twoje wpisy: zawsze `src=agent st=hyp`. Nowe ID = następny wolny numer danego prefiksu (E, C, A, P, R, X, G, H, Q, N). Komentarze piszesz jako `  > [agent] ...` pod elementem.

## Zasady
1. **Najpierw pytaj, potem proponuj.** Maksymalnie 3–5 pytań na rundę, wybierz te, które najbardziej blokują model. Pytania zapisuj jako `q` albo `hot` w pliku.
2. **Zdarzenia w fazie 1 pochodzą od użytkownika.** Możesz dopytywać ("czy po X może się zdarzyć Y?"), ale nie wypełniaj tablicy domysłami.
3. **Pilnuj faz.** Faza 1: tylko `event hot q note`, żadnej techniki ani rozwiązań. Faza 2 dodaje `actor cmd policy read ext`. Faza 3 dodaje `agg` i granice kontekstów. Nie wyprzedzaj. Narzędzie odrzuci niedozwolone typy.
4. **Język biznesowy.** Nazwy zdarzeń w czasie przeszłym, językiem użytkownika ("Płatność zaksięgowana"). Uwagi techniczne wpisuj w komentarzu `> [agent]`.
5. **Rozróżniaj edycję od sugestii.** Bezpośrednia zmiana użytkownika to fakt, nie cofaj jej po cichu. Komentarz to prośba o Twoje zdanie. Gdy masz zastrzeżenie do jego zmiany, zostaw `hot` z uzasadnieniem i konkretem z tablicy lub kodu. Decyzja należy do niego.
6. **Krytykuj konkretnie.** Szukaj: zdarzeń bez przyczyny, komend bez aktora, luk w osi czasu, zdarzeń mogących wystąpić dwa razy, ścieżek błędu ("co jeśli płatność się nie powiedzie?"), kto może to cofnąć, sprzeczności nazw. W każdej rundzie zgłoś zastrzeżenia, a nie samo przytakiwanie.
7. **Odrzucone zostają w pliku** jako `st=rej` (nie proponuj ich ponownie).

## Przebieg rundy
1. `python3 esb.py diff` — zobacz tylko to, co zmienił użytkownik od Twojej ostatniej tury (nie czytaj całego pliku bez potrzeby).
2. Zastosuj, zaadaptuj lub zakwestionuj każdą zmianę (zastrzeżenia jako `hot`/komentarz).
3. `python3 esb.py check` — popraw błędy `E`, rozważ ostrzeżenia `W`.
4. `python3 esb.py snap` — zapisz migawkę **po** swojej turze, potem oddaj głos użytkownikowi.
Przejście do kolejnej fazy: `python3 esb.py next` (odmówi, jeśli są błędy, sporne albo niepotwierdzone hipotezy). Uzgodnij to z użytkownikiem, nie używaj `--force` samodzielnie.

## Brownfield (feature w istniejącym repo)
1. **As-is:** użytkownik wskazuje punkt wejścia. Czytaj kod tylko od niego w głąb, na tyle, ile trzeba. Wpisz istniejące komendy, zdarzenia, agregaty, integracje z `code=ścieżka:symbol` i `st=ok`, jeśli potwierdzone w kodzie.
2. **To-be:** użytkownik opisuje feature, Ty dopytujesz. Nowe elementy mają `src=agent st=hyp` (po potwierdzeniu `ok`), a w tekście ani w `code=` nie udawaj, że istnieją w kodzie.
3. **Delta:** wskaż, co nowe, co zmienione i które istniejące polityki lub modele odczytu zostaną dotknięte.
Dla małego featura zacznij od `phase: 2` na wycinku dotkniętym zmianą (bez Big Picture).

## Wynik końcowy
Gdy faza 3 jest zatwierdzona (brak sporych i hipotez), wygeneruj **osobny** plik `docs/plan-<nazwa>.md`: moduły (bounded contexty), agregaty z niezmiennikami, komendy jako API, zdarzenia jako komunikaty, polityki jako handlery, kolejność implementacji, otwarte ryzyka i odnośniki do kodu. Plan opiera się wyłącznie na elementach `st=ok`.

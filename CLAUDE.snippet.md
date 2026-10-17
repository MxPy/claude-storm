## Planowanie: event storming (esb)

- Do planowania nowego projektu lub większego featura (nowe zachowania, kilka modułów, niejasna domena) **użyj skilla `event-storming-board`** i pliku `event_storming.md`. Zamiast pisać plan w `plan.md`, najpierw przeprowadź z użytkownikiem event storming.
- Nie używaj go do bugfixów, refaktorów, małych zmian w jednym pliku ani gdy użytkownik prosi tylko o szybki plan w rozmowie.
- Gdy plik nie istnieje: `python3 esb.py init --mode greenfield|brownfield --title "..."`. Użytkownik otwiera tablicę przez `python3 esb.py serve`.
- Każdą rundę zaczynaj od `python3 esb.py diff`, kończ `check` i `snap`. Nie czytaj całego pliku, jeśli diff wystarcza.
- Nie wymyślaj faktów domenowych: Twoje wpisy to `src=agent st=hyp`, dopóki użytkownik ich nie potwierdzi.
- Końcowy plan implementacji idzie do `docs/plan-<nazwa>.md` i powstaje dopiero po zatwierdzeniu fazy 3.

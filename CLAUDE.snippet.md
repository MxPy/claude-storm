## Planning: event storming (esb)

- For planning a new project or a larger feature (new behaviours, several modules, unclear domain) **use the `event-storming-board` skill** and the `event_storming.md` file. Instead of writing the plan straight into `plan.md`, run an event storming session with the user first.
- Do not use it for bugfixes, refactors, small single-file changes, or when the user only wants a quick plan in chat.
- If the file does not exist: `python3 esb.py init --mode greenfield|brownfield --title "..."`. The user opens the board with `python3 esb.py serve`.
- Start every round with `python3 esb.py diff`, finish with `check` and `snap`. Do not read the whole file when the diff is enough.
- Do not invent domain facts: your entries are `src=agent st=hyp` until the user confirms them.
- The final implementation plan goes to `docs/plan-<name>.md` and is written only after phase 3 is approved.

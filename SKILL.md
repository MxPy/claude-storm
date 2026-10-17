---
name: event-storming-board
description: Run an event storming session with a developer on the board file `event_storming.md` (tool esb.py). Use when the user plans a new project or a larger feature, or asks for event storming, domain modelling, bounded contexts, aggregates, or "the board". Do not use for small fixes and bugfixes.
---

# Event storming with the user

You are the **technical** side, the user is the **business** side (a developer who knows what they want to build). Your job is to draw knowledge out of them with questions, organise it, and find gaps. **Do not invent domain facts.** Everything you assume is a hypothesis.

## The file
One file, `event_storming.md` (the user sees it as a board via `python3 esb.py serve`).
Order of events in the file = timeline. Never reformat existing lines.

```
# Event Storming: Name
mode: greenfield | brownfield
phase: 1            # 1 Big Picture, 2 Process, 3 Design

## Context name
- E1 event: Order placed | src=agent st=hyp by=C1 agg=G1 code=src/order.py:place
  > [biz] user comment
- C1 cmd: Place order | by=A1
- A1 actor: Customer
```
Line format: `- ID type: text | key=value ...`. Types: `event cmd actor policy read ext agg hot q note`.
Keys:
- `by=` — cause: the command/actor/policy for an event or command; the event a policy or read model reacts to.
- `agg=` — owning aggregate.
- `src=biz|agent` — who wrote it.
- `st=hyp|ok|disp|rej` — hypothesis, confirmed, disputed, rejected.
- `code=path[:symbol]` — location in the codebase.

Your entries are always `src=agent st=hyp`. New ID = next free number for the type prefix (E, C, A, P, R, X, G, H, Q, N). Write comments as `  > [agent] ...` under the element.

## Rules
1. **Ask first, propose second.** At most 3-5 questions per round, the ones blocking the model most. Record them as `q` or `hot` items in the file.
2. **In phase 1 the events come from the user.** You may probe ("can Y happen after X?") but do not fill the board with guesses.
3. **Respect the phases.** Phase 1: only `event hot q note`, no technology or solutions. Phase 2 adds `actor cmd policy read ext`. Phase 3 adds `agg` and context boundaries. Do not jump ahead; the tool rejects disallowed types.
4. **Business language.** Events in past tense, in the user's own domain vocabulary ("Payment settled"). Put technical remarks in `> [agent]` comments.
5. **Edits are facts, comments are requests.** A direct change by the user is a fact: never silently revert it. A comment asks for your opinion. If you disagree with a change, leave a `hot` with a justification grounded in the board or the code. The decision stays with the user.
6. **Critique concretely.** Look for: events without a cause, commands without an actor, timeline gaps, events that can occur twice, failure paths ("what if the payment fails?"), who can undo it, naming conflicts. Raise objections every round instead of just agreeing.
7. **Rejected items stay in the file** as `st=rej` (do not propose them again).

## Round procedure
1. `python3 esb.py diff` — see only what the user changed since your last turn (do not read the whole file unless needed).
2. Apply, adapt, or challenge each change (objections as `hot` / comment).
3. `python3 esb.py check` — fix `E` errors, consider `W` warnings.
4. `python3 esb.py snap` — save the snapshot **after** your turn, then hand over to the user.

To move to the next phase run `python3 esb.py next` (it refuses while there are errors, disputed items, or unconfirmed hypotheses). Agree on it with the user; never use `--force` on your own.

## Brownfield (a feature in an existing repo)
1. **As-is:** the user names an entry point. Read code only from there downwards, as deep as needed. Record existing commands, events, aggregates and integrations with `code=path:symbol`, and `st=ok` when confirmed in the code.
2. **To-be:** the user describes the feature, you ask questions. New elements are `src=agent st=hyp` (`ok` once confirmed); never claim they exist in the code and never give them a `code=` pointing at code that does not exist.
3. **Delta:** state what is new, what changes, and which existing policies or read models are affected.
For a small feature start at `phase: 2` on just the slice the change touches (skip Big Picture).

## Final output
When phase 3 is approved (no disputed items or hypotheses left), generate a **separate** file `docs/plan-<name>.md`: modules (bounded contexts), aggregates with invariants, commands as API, events as messages, policies as handlers, implementation order, open risks, and code references. The plan relies only on `st=ok` elements.

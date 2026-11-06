# <PROJECT> — JunctionX Turku 2026, 48-hour build

Team: Dayo (drives Claude, data, backend, deploy) + Madeleine (partner reps, pitch, docs polish, expo) + Claude.
Event window: Fri 16 Oct 18:00 to Sun 18 Oct 18:00 Helsinki. Submission ZIP closes Sun 10:00 Helsinki.

## Clock

40 hours, not 48. The submission window closes Sun 10:00, not Sun 18:00.
- Sat 24:00: feature freeze. Only bug fixes, copy, docs, screenshots after this point.
- Sun 08:00: submit the ZIP. Two hours before the deadline; confirm the platform shows receipt.

## Non-negotiables
- Everything in this repo was written during the event. The first commit is the bell. Anything pre-existing that we
  use is declared in DISCLOSURE.md: public datasets, our VPS + domain + tunnel, open-source libraries, and the generic
  process scripts in /root/hack/bin (screenshots, smoke test, deploy). Nothing else from any earlier project.
- No fabricated data. Every number on screen traces to a row in the data. Missing data shows "no data", never a
  placeholder that looks real. No lorem ipsum anywhere, ever.
- Companies only, never named private individuals.
- No secrets in the repo. Environment goes in .env (gitignored), loaded by systemd.
- Secrets: never read, write, rename, copy or overwrite any .env, token, key or credential file outside
  this directory (including /root/orchestrator/.env, /root/.secrets, /root/.config, /root/.claude*). Keys
  reach the app only through an EnvironmentFile that already exists here. If a key is missing, mark that
  item BLOCKED and continue. A task that changes a shared secrets file is detected and reported.
- Finnish copy: no em dashes. Money and dates in Finnish format if shown.

## The loop (every task, no exceptions)
1. Take the task from TASKS.md. Write the concrete check first (a test, or the exact URL + what must be visible).
2. Build the smallest thing that passes. Commit every 20-30 minutes; the message says what works now.
3. Deploy: `/root/hack/bin/deploy.sh <name> <dir> <port> "<start command>"` (see DEPLOY section below).
4. Look: `/root/hack/bin/shot.py <url> --name <task>` then READ desktop.png and mobile.png. Fix what you see.
5. Prove: `/root/hack/bin/smoke.py <url>` prints PASS, and `pytest -q` is green.
6. Done = works on the public URL + both screenshots reviewed + tests green + README section updated.
   End with `RESULT: <one sentence a judge could repeat, with URL and screenshot paths>`.

## Stack (decided Fri ~19:00; fill in and keep current)
- Backend: <FastAPI/Flask/Next route handlers>   Frontend: <plain HTML+htmx / Next.js + shadcn>
- Data: <SQLite/DuckDB file at data/...>          Port: <81xx>   Start: `<command>`
- Public URL: <https://...>   Deploy: `/root/hack/bin/deploy.sh <name> <dir> <port> "<start>"`

## Files the judges read (JunctionX scores code quality, architecture, documentation)
README.md (30-second summary, hero screenshot, demo path, run in 3 commands), ARCHITECTURE.md (diagram + why),
EVAL.md (held-out set + one measured number), DISCLOSURE.md (brought vs built), PILOT.md (8-week plan for the partner).
Keep them true at all times; they are updated in the same commit as the feature.

## Design
Never unaided design: DESIGN.md names 3 references and one direction before the first screen is built.
Defaults over invention: shadcn/ui or Pico.css, system font stack, one accent colour, generous whitespace.
Real data on every screen. Mobile must not break: every task screenshots both viewports.
Slop tells to avoid: purple gradients, emoji in headings, four identical cards in a row, centered paragraphs,
"Welcome to" headlines, placeholder avatars, animated counters.

## Process safety
Never `pkill -f` or `killall` with a text pattern: the pattern can match your own Claude session and kill it mid-task
(it happened on 1.10.2026). Stop servers by port (`fuser -k 8150/tcp`), by the PID you started, or `systemctl stop hack-<name>`.
Commit every 20-30 minutes; an uncommitted worktree is lost work if the session dies.

## Parallel work
Overnight tasks go to /root/hack/queue as task files (see /root/hack/templates/task_template.md). Each runs in its own
worktree on branch task/<name>. Merge in the morning with `git merge --no-ff task/<name>` after reading its RESULT line
and screenshots. Never work directly on a branch another task owns.

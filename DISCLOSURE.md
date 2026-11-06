# What we built this weekend versus pre-existing

## One-line statement
"All application code in this repository was written between 16 Oct 18:00 and 18 Oct 10:00 (Helsinki) with AI coding
tools. We brought our own build tooling, checklists, and the public datasets listed below, and we used the
third-party services listed below."

## Application code written at the event
Every file in this repository except those listed below. The first commit ("bell") is the empty skeleton,
timestamped at the opening. `git log --reverse` is the proof.

## Tooling brought (not product code)
| Item | What it is |
|---|---|
| bin/shot.py | Screenshots a URL at desktop and mobile size, captures console errors |
| bin/smoke.py | Loads a page and its same-origin links, fails on errors |
| bin/deploy.sh | Writes a systemd unit for an app directory and restarts it |
| templates/ | This file and other judged-doc skeletons |
| Claude Code skills | hack-plan, hack-verify, hack-design, hack-docs, hack-demo |
| CI config | .github/workflows/ci.yml |

## Datasets declared with licences
| Dataset | Rows / date range | URL | Licence | Snapshot date |
|---|---|---|---|---|
| <name> | <count, date range> | <URL> | <licence> | <date> |

## Third-party services
| Service | Purpose | Account pre-existed? |
|---|---|---|
| Anthropic Claude (Claude Code + API) | Pair programmer and in-product LLM calls | yes |
| <other service> | <purpose> | <yes/no> |

## Not used
No code from any earlier project. No private or scraped personal data. No named private individuals.

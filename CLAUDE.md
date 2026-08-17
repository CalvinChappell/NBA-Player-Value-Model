# Working on this repo with Claude

Operating notes for an AI assistant picking up this project — not a
replacement for README.md (architecture, file layout, how to run things),
which is still the primary reference. This file is about *how to work on
the repo safely*, written after a session that hit a few real, repeatable
failure modes.

## Ground truth

- Real repo: `~/Documents/nba_salary_model`, pushed to
  `github.com/CalvinChappell/NBA-Player-Value-Model`.
- Streamlit Community Cloud auto-deploys from `main` on push (usually
  within a couple minutes; "Reboot app" in the Streamlit Cloud panel
  forces a clean pull if a build looks stale).
- `venv` is active in Calvin's terminal sessions.
- Data refresh workflow (see README's "Publishing it" section for the
  full explanation):
  ```
  rm -rf data/cache
  python3 run_pipeline.py
  python3 make_public_data.py
  git add -A
  git commit -m "..."
  git push
  ```

## Before reporting something fixed

This burned real time in an earlier session: edits were made to a
*different copy* of the project than the one actually deployed, and
"here's the fix" got reported before the fix had actually reached the
real repo. If you have direct folder access (Read/Write/Edit resolve to
the real files), this specific failure is unlikely — but still verify:

- `git status` / `git diff` after edits, to confirm what actually
  changed and that it's in the tracked repo, not a scratch copy.
- After a pipeline run, re-check the specific number/player that
  prompted the fix (don't just confirm the code ran without erroring).
- If a metric column looks suspiciously uniform (all `None`, all the
  same value, all zero) — that's almost always a required-input column
  silently missing upstream, not the metric's math being wrong. See
  `model/value_metrics.py`'s `add_foul_draw_value` /
  `add_rim_scoring_value` for the pattern: several inputs required,
  degrades to all-NaN if even one is absent, rather than erroring.

## The contract_overrides.csv pattern

`data/manual/contract_overrides.csv` exists because Basketball-
Reference's contracts page is occasionally wrong or stale in ways that
have no safe, generic programmatic fix. Three independent override
columns, matched by player name (normalized via `utils/name_match.py`):

- **`team_override`** — a player has TWO rows on the contracts page
  (old team + new team, often identical dollar figures) after a buyout
  or trade, and naive dedup can keep either one. Set this to the
  player's actual current team. Examples already in the file: Bradley
  Beal, Damian Lillard, Kentavious Caldwell-Pope, Olivier-Maxence
  Prosper.
- **`cap_hit_override`** — the dollar figure itself is wrong (rare;
  most duplicate-row cases have matching salaries, see above).
- **`free_agent_override`** — the player's contracts-page row is
  entirely stale (they're actually unsigned right now, but the site
  hasn't dropped their old figure). Any non-null value here forces
  `cap_hit` to NaN everywhere — leaderboard, player page, AND payroll —
  via `model/merge.build_master_table` and `build_payroll_table`.
  Example: James Harden declining his 2026-27 Clippers option.

If a "wrong cap number" bug shows up, check whether it fits one of
these three shapes before writing new code — it usually does.

## Known gotchas (add to this list as new ones turn up)

- **Basketball-Reference silently renames data-stat attributes.** Has
  broken `playoff_GP` (regular-season "advanced" table uses `games`,
  the playoffs "advanced" table still uses the old `g`) and `FTr` (a
  stale local copy of `bref_advanced.py` was simply missing the line —
  not a bref change that time, but the symptom looked identical: the
  metric goes silently blank). When a metric breaks after a fresh
  scrape, write a small diagnostic that checks each required column
  individually rather than guessing — see `diagnose_contracts.py` and
  `diagnose_foul_draw.py` for the pattern (both still in the repo root,
  reusable as templates).
- **`.gitignore` denies `outputs/*` by default**, with specific files
  re-allowed one at a time (`!outputs/player_value_model_public.csv`,
  `!outputs/team_payroll.csv`, `!outputs/payroll_only_players.csv`).
  A new output file needs an explicit allow-line or `git add -A` will
  silently skip it — no error, it just never gets committed.
- **`team` vs `team_contract` are deliberately different columns.**
  `team` comes from the 2025-26 advanced-stats scrape (who a player
  played for last season). `team_contract` comes from the live
  contracts page (current team). Anything meant to reflect "who's on
  this team right now" — filters, payroll, roster display — should use
  `team_contract`, not `team`. Mixing these up was the root cause of at
  least three earlier bugs in this project.
- **Two season figures coexist on purpose.** Production stats (BPM,
  box score, etc.) are 2025-26 (completed season); `cap_hit` and
  contract figures are 2026-27 (upcoming season, per how Basketball-
  Reference's contracts page always reports the *next* season). This
  is intentional, not a bug to reconcile — see README's season-pairing
  note and `app/methodology_page.py`.
- **A player can have real stats but a stale/absent contract, or a
  real contract but zero stats.** `build_master_table()` anchors on
  advanced stats and left-joins contracts, which is right for the
  leaderboard but wrong for payroll — it silently drops anyone with a
  contract but no 2025-26 games (incoming rookies, players out the
  whole season to injury). `build_payroll_table()` exists specifically
  to source payroll from the contracts page directly instead. Don't
  merge these two code paths back together without re-solving that
  problem.
- **`contract_type` ("Rookie Scale" vs "Veteran") needs draft context,
  not just years of experience.** The original heuristic was
  `experience <= ROOKIE_SCALE_MAX_EXPERIENCE -> "Rookie Scale"`, which
  mislabeled undrafted players (a CBA rookie-scale contract only exists
  for first-round picks on their original deal -- undrafted players
  never have one, regardless of years of service) and would do the same
  to second-round picks. Fixed in `model/merge.build_master_table` by
  checking `experience_is_estimated` (a reliable "undrafted" signal --
  see the season-fallback logic just above it) and `draft_pick > 30`
  (overall pick number, not round-relative) before applying the
  experience cutoff. Real case that surfaced this: Julian Champagnie
  (undrafted 2021, now on a real second contract with San Antonio) was
  showing as Rookie Scale.
- **A code fix isn't shipped until it's actually in the deployed repo.**
  Happened twice in one day: edits made without direct folder access got
  delivered as zips, and not every file in a zip actually got copied
  over before the conversation moved on to the next bug -- so `merge.py`
  had the payroll fix but `app/streamlit_app.py` (which calls it) didn't,
  and the live dashboard kept showing the old, broken numbers for
  another full round of "is this fixed?" before anyone noticed. With
  direct folder access this specific failure mode shouldn't recur, but
  the underlying lesson still applies: after any fix, verify with
  `git status` / `git log` that the change is actually committed and
  pushed, not just sitting as an edited file -- and check the *live*
  app, not just local output, before calling something done.

## Don't run git commands from the sandbox

Even read-only ones (`git status`, `git diff`) can leave a stale
`.git/index.lock` behind on this particular mount, which then blocks
Calvin's next real commit until he manually removes it
(`rm .git/index.lock`) -- happened twice in one session. Use `git log`
sparingly if at all; prefer `Read`/`Grep` on the actual files to verify
state, and let Calvin run `git status`/`add`/`commit`/`push` himself.

## Diagnostics over guessing

When a number looks wrong, don't hand-check it team-by-team or
player-by-player — write a small script that surfaces every affected
case at once (duplicate rows, missing columns, unmatched players,
whatever the failure class is), run it, then fix based on real output.
Every bug in this project so far has had a systemic cause findable this
way, not a one-off typo.

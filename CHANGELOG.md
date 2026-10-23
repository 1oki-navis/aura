# Changelog

Newest first. Each version is one commit on `main` (v20 onward). `sw.js` cache name and the footer always carry the same version.

## v29 (23 Oct 2026) - Cloud backup + coach tip
- Finish now sends the whole DB to the `stride-coach` Cloudflare Worker (`https://stride-coach.lokis-space.workers.dev`). It overwrites one cloud copy (Workers KV, key `latest`), so backups never pile up.
- Same call asks the AI (Kaleris gateway, `STRIDE_MODEL`, default `gpt-6-sol`) for a 2-4 line tip from today's sets, notes and the last same session. Shows as a card on Lift, dismiss with ✕.
- Offline: queued in `stride.pending`, retried on load and when back online.
- Save tab: Cloud section with passcode, last cloud backup, Restore from cloud (replace with confirm + undo). File export stays as an optional extra.
- Backup due nag is off while a cloud backup is under 7 days old.
- Worker source lives outside the site in `~/Downloads/stride-worker` (wrangler). Secrets `AI_KEY` and `STRIDE_TOKEN` (8+ chars, same as the app passcode, in 1Password as "Stride passcode"). CORS allows only `https://lokis-space.github.io`; other origins get 403.
- sw.js now ignores every cross-origin request, so cloud calls are never cached. Netlify files removed.
- Tests: 205 pass (legacy 128, v16 49, v20 15, v23 13). Reverted the netlify test exclusion, added `test_v29_cloud_is_worker_and_sw_skips_cross_origin`. Live Worker round trip checked: POST returns a tip, GET returns the copy, wrong token 401, other origin 403.

## v28 (22 Oct 2026) - Per side on the Sets line
- `/ side` and `/ leg` targets now read `Sets 2 · per side` and `Hold start 30 → work to 60 s`, so nothing wraps on a phone.
- Next hint stays open-card only (from v27).
- Tests: 204 pass (legacy 128, v16 49, v20 15, v23 12). Updated the Side Plank target assertion, added `test_v28_next_hint_only_in_open_card`. Test runner now uses a local `tests/.venv`.

## v27 (22 Oct 2026) - Renamed to Stride
- Renamed **Aura** to **Stride** (title, home screen name, footer, empty screen, import error). Storage key `liftlog.v1` and cache prefix unchanged, so data carries over. Re-add to the home screen to update the icon name.
- Version bumped so installed apps refresh the cached manifest (cache-first) and pick up the new name.

## v26 (22 Oct 2026) - Start / work to + Next hint
- Closed card: `Sets 3`, `Reps start 8 → work to 12` (timed: `Hold start 30 s → work to 60 s per side`), then `Today` once you log. Last stays inside the open card (v25).
- Green `Next` hint, read-only, never changes weights. Uses last session's working sets at the heaviest weight (lightest assist for assisted):
  - every planned set at the top: `All at 12, add weight`
  - any set past the top: `Too easy, add weight`
  - assisted: `take 5 kg less assist`; timed: `make it harder`
  - fewer sets than planned, or any set below the top, no range, or done today: no hint
- Tests: `test_v26_next_hint_cases`, `test_v26_card_shows_next_hint_and_hides_when_done` (v23 suite).

## v25 (20 Oct 2026) - Cleaner cards, notes in CSV
- Closed cards show only Target. The dated "Last <date>" line and last session's note show once, inside the open card.
- CSV export has a new "Exercise note" column. Each day's exercise note sits on the first set row; notes with no sets get their own row.
- Tests: `test_csv_exports_exercise_notes` (v23 suite), updated `test_v24_shows_target_and_last_and_prefills_last`.

## v24 (20 Oct 2026) - Simple targets
- Removed the auto "Next" targets and the feel prompt. They were unreliable.
- Card uses labelled lines: Target / Last / Today, sentence case, slightly bigger text.
- Ranges: Standing Calf Raise 4 x 12-20; DB Lateral Raise, DB Rear Delt Raise, Wrist Curl, Reverse Wrist Curl 15-25. Migration (`pv` < 24) only changes them if you haven't edited them.
- Prefill = same set last session. Old `DB.feel` data is kept but unused.
- Tests: two v20 feel/next tests replaced with v24 tests.

## v23 (19 Oct 2026) - Athletic look plan
- New default plan from `Gym Plan/PLAN - Athletic look DRAFT for review.md`. Legs first, forearms on both Upper days, 2 min rest everywhere.
- Session order: Lower A > Upper A > Lower B > Upper B.
- Migration (`pv` < 23): if the saved plan still has v22 exercises, the 4 sessions are swapped for the new plan and the order is reset. Custom sessions are kept at the end. History, notes and units are untouched. Runs once (`pv: 23`).
- Steps match the gym: pins and plates +5 kg, Leg Press +10 kg.
- Tests: `test_v23.py`. Older suites pin the v22 plan via `v22-plan.json`.
- Fix: the old hack Calf Raise migration looked up Seated Calf Raise in Lower A only. v23 moved it to Lower B, so it would have inserted an empty exercise. It now searches every session.
- Assisted Pull-up and Assisted Dip hints say "then less assist" (vague, no fixed kg).
- Legacy tests now read order, version and plan from the app instead of hardcoding v22. Totals: legacy 128, v16 49, v20 15, v23 7, all passing.

## v22 (19 Oct 2026)
- Renamed to **Aura** (title, home screen name, footer, import error). Storage key `liftlog.v1` and the cache prefix are unchanged, so data carries over.
- New icon: a dot-matrix loaded barbell with a glowing red centre, sized for the maskable safe zone.

## v21 (19 Oct 2026)
- Font change from v20 reverted: Doto, Bebas Neue and Space Mono are back (with `fonts/` and their cache entries). Everything else from v20 stays.

## v20 (10 Oct 2026)
- iOS look: Doto, Bebas Neue and Space Mono were replaced by the system font (SF Pro) everywhere, with tabular numbers. `fonts/` was removed and the cache list is smaller. The layout and the black and red colours are unchanged.
- Notes are per session and clear next time. The last session's sets and note show on the open card.
- Plan tips are hidden, and the plan editor's Note field is gone.
- Easy / Good / Hard rating after an exercise, with tailored per-set targets and prefill (see Next-session targets).
- Add exercise asks for sets x reps (and step kg for kg exercises) before the plan saves.
- Hosting moved from Netlify to GitHub Pages (no Netlify badge). Data is per site, so export a JSON backup on the old URL and import it on the new one.

## v19 (9 Oct 2026)
- Upper B and Lower B filled in `PLAN`. Lower A calf raise is now Seated Calf Raise.
- Migration: phones with an empty Upper B / Lower B saved get the new sessions on load; the old hack-machine calf raise in Lower A is swapped for Seated Calf Raise. Custom edits elsewhere are kept.

## v18

- **Editable sessions.** In Lift > Edit plan there is a new "Session name" field. Renaming a session carries its logged sets, finished flags and its place in the rotation over to the new name.
- **Add session.** Adds a new session (up to 8) at the end of the rotation. It opens with the name field focused. If you cancel or switch tabs before saving, nothing is left behind.
- **Remove session.** Found under Edit plan. It takes the session out of the rotation, but its history stays in Log and Stats.
- The rotation is stored in `DB.order`. Backups made before v18 load with the default order (Upper A, Lower A, Upper B, Lower B).
- Session names are HTML-escaped everywhere. Each name must be unique, non-empty and at most 24 characters.

## v17

- The "Backup due" line on Lift only shows before the night's first set. The red dot on Save still flags it mid-session.
- Cardio notes placeholder shortened to "Notes · level, feel" so it fits the screen.
- Edit plan notes wrap and grow instead of being cut off. Line breaks are flattened to spaces on save.

## v16

- Edit plan: move up / move down buttons to reorder exercises. A unit change on an exercise that lives in more than one session now applies to all of them, so logging and stats agree.
- Changing a unit to bodyweight or seconds and back no longer wipes kg history. Removed exercises keep their unit in history.
- Inputs: comma decimals work (`22,5`). kg is 0-500, reps are whole numbers up to 100, seconds up to 3600, cardio 1-600 min. Text is rejected with a toast.
- Body: weight 25-250 kg and waist 40-200 cm. A waist-only entry merges into that day's weight. The rate uses the last 28 days and needs 3 points.
- Runs: pace never shows `:60`. Easy % only counts runs with HR, and HR 155 or more is hard.
- Backups: restoring from the empty screen replaces (keeps plan and notes). Imported ids are sanitised (no XSS) and a malformed plan no longer crashes the app. CSV cells that start with `= + - @` are prefixed with `'`, and kg is blank for non-kg units.
- Storage: unreadable saved data is kept aside in `liftlog.corrupt` instead of being overwritten. A full quota shows "Storage full · not saved" and rolls back instead of losing data silently.
- Day rollover is checked on every render, so returning to the tab after 5 am shows the new day.
- 350 ms double-tap guard on buttons (not on +/-, add or move).
- 44 px back button and inputs, aria-labels on icon buttons, pluralised counts, week maths in local dates (no drift in far east or far west timezones).
- Exercise page: cardio shows "Sessions" instead of "Sets", and the chart end label shows the exact value (47.5, not 48).

## v15 and earlier
- Built and hosted on Netlify before the project was in git. v15 removed the protein / creatine / whey checks from the top of Lift. No detailed notes survive.

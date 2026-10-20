# Aura

Personal iPhone PWA workout tracker for the Phase 2 gym plan. It is a single-file app with inline CSS and JavaScript, plus a service worker and local fonts (Doto, Bebas Neue, Space Mono in `fonts/`).

## Data

Data is stored in `localStorage` under `liftlog.v1`. Schema version `ver: 2` adds migrated plan data, notes, custom exercises, finished sessions (`fin`, keyed `date|session`) and import safety. The old daily protein / creatine / whey checks were removed in v15 and are dropped on load. Existing data is migrated in place and not wiped.

## Units and exercise types

The plan editor offers four plain units:

- `kg`: every loaded movement. Only this unit shows the Start kg and Step kg fields.
- `bodyweight`: reps only.
- `seconds`: timed holds like Plank.
- `cardio`: minutes, like Bike warmup. It has a minutes stepper, a notes field and Log / Update / Remove, so it stays editable after logging.

The old `sled` unit (v14) and `assist` unit (v15) migrate to `kg`. Assisted Dip keeps a hidden `lb` (lower is better) flag, so less assist still counts as a PR and progression, and it stays out of volume and 1RM.

## Targets (v24)

Each exercise card shows three labelled lines: `Target 3 sets · 10-12 reps`, `Last 40 kg · 12, 12, 8` (red; mixed weights read `10 kg · 10, 8 then 5 kg · 8`, assisted reads `35 kg assist · ...`, timed reads `30 s, 30 s`, new reads `None yet`) and `Today 2 of 3 sets` once you log. No auto "Next" suggestions and no "How did it feel" prompt. Each set prefills with the same set from last session (or your previous set today). You decide when to add reps or weight. Rule: reps up to the top of the range on every set, then add one step.

## Notes

The note box on each exercise is for **this session only** (`DB.notes["date|exercise"]`) and starts empty next time. The open card shows the last session's sets and its note under `Last <date>`. The first session shows neither. Plan tips are no longer shown, and the plan editor has no Note field. Old per-exercise notes move to that exercise's last session on load.

## Session lifecycle

- Finished exercises fold up with a tick, and the next unfinished one opens.
- **Finish session** saves the session to Log and Stats and moves the Lift screen to the next session in the rotation with clean cards. Logging into a finished session reopens it.
- On a new gym day (the 5 am rule), the Lift screen moves on automatically if anything was logged the day before.

## Runs

Date, km, time (mm:ss), optional avg HR (40-230) and notes. Tap a run to edit it in place.

## History

`liftlog-start.json` includes the Phase 1 Hevy sessions (21 Sep, 24 Sep, 27 Sep, 2 Oct, as Phase 1 A / B) and the 22 Sep run, so they show in Log and Stats after either Merge or Replace import.

## Backup

Use **Save → Export backup** weekly or whenever the Save tab has a red dot. Imports default to merge and keep `liftlog.prev` so a restore can be undone.

## Offline

`sw.js` uses cache `liftlog-v25`, network-first with a 2.5 s timeout for the app shell, cache-first for fonts, icons and the manifest, and deletes old caches on activate.

## Local test

```sh
python3 -m http.server 8765
```

Open `http://127.0.0.1:8765` with a 402 x 874 mobile WebKit viewport.

## Testing

The re-runnable stress suite lives in `~/Downloads/liftlog-test`.

```sh
~/Downloads/liftlog-test/run.sh
```

It serves the app on port 8765, runs WebKit Playwright with an iPhone 17 Pro sized mobile viewport, records videos in `video/`, writes screenshots in `screens/`, and updates `REPORT.md`. The suite covers empty start, imports, logging, undo, timed exercises, Replace versus Merge restore, corrupt imports, JSON and CSV exports, before 5 am dates, edge inputs, body and run logs, 8 week metric recomputes, offline reload, visual constraints, 2000+ set render performance, and the v15 stress pass (cardio, plan editor, Finish session, rotation, day rollover, run notes, Body save, dead-button scan).

After the legacy suite, `run.sh` runs `test_v16.py` (49 regression tests from the v16 to v19 passes) and `test_v20.py` (15 tests for the v20 changes). Run a subset with `python test_v16.py <name-fragment>`. `explore.py` is the 3-week night-by-night simulation that records `video2/`, writes `screens2/` and recomputes stats in Python (see `REPORT-v16.md`).

## v16 changes

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

## v17 changes

- The "Backup due" line on Lift only shows before the night's first set. The red dot on Save still flags it mid-session.
- Cardio notes placeholder shortened to "Notes · level, feel" so it fits the screen.
- Edit plan notes wrap and grow instead of being cut off. Line breaks are flattened to spaces on save.

## v18 changes

- **Editable sessions.** In Lift > Edit plan there is a new "Session name" field. Renaming a session carries its logged sets, finished flags and its place in the rotation over to the new name.
- **Add session.** Adds a new session (up to 8) at the end of the rotation. It opens with the name field focused. If you cancel or switch tabs before saving, nothing is left behind.
- **Remove session.** Found under Edit plan. It takes the session out of the rotation, but its history stays in Log and Stats.
- The rotation is stored in `DB.order`. Backups made before v18 load with the default order (Upper A, Lower A, Upper B, Lower B).
- Session names are HTML-escaped everywhere. Each name must be unique, non-empty and at most 24 characters.

## v19 (9 Oct 2026)
- Upper B and Lower B filled in `PLAN`. Lower A calf raise is now Seated Calf Raise.
- Migration: phones with an empty Upper B / Lower B saved get the new sessions on load; the old hack-machine calf raise in Lower A is swapped for Seated Calf Raise. Custom edits elsewhere are kept.

## v20 (10 Oct 2026)
- iOS look: Doto, Bebas Neue and Space Mono were replaced by the system font (SF Pro) everywhere, with tabular numbers. `fonts/` was removed and the cache list is smaller. The layout and the black and red colours are unchanged.
- Notes are per session and clear next time. The last session's sets and note show on the open card.
- Plan tips are hidden, and the plan editor's Note field is gone.
- Easy / Good / Hard rating after an exercise, with tailored per-set targets and prefill (see Next-session targets).
- Add exercise asks for sets x reps (and step kg for kg exercises) before the plan saves.
- Hosting moved from Netlify to GitHub Pages (no Netlify badge). Data is per site, so export a JSON backup on the old URL and import it on the new one.

## v21 (19 Oct 2026)
- Font change from v20 reverted: Doto, Bebas Neue and Space Mono are back (with `fonts/` and their cache entries). Everything else from v20 stays.

## v22 (19 Oct 2026)
- Renamed to **Aura** (title, home screen name, footer, import error). Storage key `liftlog.v1` and the cache prefix are unchanged, so data carries over.
- New icon: a dot-matrix loaded barbell with a glowing red centre, sized for the maskable safe zone.

## v23 (19 Oct 2026) - Athletic look plan
- New default plan from `Gym Plan/PLAN - Athletic look DRAFT for review.md`. Legs first, forearms on both Upper days, 2 min rest everywhere.
- Session order: Lower A > Upper A > Lower B > Upper B.
- Migration (`pv` < 23): if the saved plan still has v22 exercises, the 4 sessions are swapped for the new plan and the order is reset. Custom sessions are kept at the end. History, notes and units are untouched. Runs once (`pv: 23`).
- Steps match the gym: pins and plates +5 kg, Leg Press +10 kg.
- Tests: `test_v23.py`. Older suites pin the v22 plan via `v22-plan.json`.
- Fix: the old hack Calf Raise migration looked up Seated Calf Raise in Lower A only. v23 moved it to Lower B, so it would have inserted an empty exercise. It now searches every session.
- Assisted Pull-up and Assisted Dip hints say "then less assist" (vague, no fixed kg).
- Legacy tests now read order, version and plan from the app instead of hardcoding v22. Totals: legacy 128, v16 49, v20 15, v23 7, all passing.

## v24 (20 Oct 2026) - Simple targets
- Removed the auto "Next" targets and the feel prompt. They were unreliable.
- Card uses labelled lines: Target / Last / Today, sentence case, slightly bigger text.
- Ranges: Standing Calf Raise 4 x 12-20; DB Lateral Raise, DB Rear Delt Raise, Wrist Curl, Reverse Wrist Curl 15-25. Migration (`pv` < 24) only changes them if you haven't edited them.
- Prefill = same set last session. Old `DB.feel` data is kept but unused.
- Tests: two v20 feel/next tests replaced with v24 tests.

## v25 (20 Oct 2026) - Cleaner cards, notes in CSV
- Closed cards show only Target. The dated "Last <date>" line and last session's note show once, inside the open card.
- CSV export has a new "Exercise note" column. Each day's exercise note sits on the first set row; notes with no sets get their own row.
- Tests: `test_csv_exports_exercise_notes` (v23 suite), updated `test_v24_shows_target_and_last_and_prefills_last`.

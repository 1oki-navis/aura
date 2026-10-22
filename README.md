# Stride

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

`sw.js` uses cache `liftlog-v27`, network-first with a 2.5 s timeout for the app shell, cache-first for fonts, icons and the manifest, and deletes old caches on activate.

## Local test

```sh
python3 -m http.server 8765
```

Open `http://127.0.0.1:8765` with a 402 x 874 mobile WebKit viewport.

## Testing

The re-runnable Playwright suites live in `tests/` (see `tests/README.md`).

```sh
sh tests/run.sh
```

It serves the app on port 8765, runs WebKit Playwright with an iPhone 17 Pro sized mobile viewport, records videos in `video/`, writes screenshots in `screens/`, and updates `REPORT.md`. The suite covers empty start, imports, logging, undo, timed exercises, Replace versus Merge restore, corrupt imports, JSON and CSV exports, before 5 am dates, edge inputs, body and run logs, 8 week metric recomputes, offline reload, visual constraints, 2000+ set render performance, and the v15 stress pass (cardio, plan editor, Finish session, rotation, day rollover, run notes, Body save, dead-button scan).

After the legacy suite, `run.sh` runs `test_v16.py` (v16 to v19 regressions), `test_v20.py` (v20 to v24) and `test_v23.py` (v23 onward). Run a subset with `python test_v16.py <name-fragment>`. `explore.py` is the 3-week night-by-night simulation that records `video2/`, writes `screens2/` and recomputes stats in Python (see `REPORT-v16.md`).

## Changelog

Version history is in `CHANGELOG.md`.

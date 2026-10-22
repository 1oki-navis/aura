# Stride tests

Playwright WebKit suites run at an iPhone 17 Pro sized viewport (402 x 874, touch, mobile).

```sh
python3 -m venv tests/.venv
tests/.venv/bin/pip install playwright
tests/.venv/bin/python -m playwright install webkit
sh tests/run.sh   # uses tests/.venv automatically, or set PY
```

| Suite | What it covers |
|---|---|
| `test_liftlog.py` | Legacy stress pass: imports, logging, undo, restore, exports, 5 am rollover, offline, perf. Writes `REPORT.md`, `screens/`, `video/`. |
| `test_v16.py` | Regressions from the v16 to v19 QA passes. |
| `test_v20.py` | Session notes, last session card, add exercise, v24 targets. |
| `test_v23.py` | Plan migration, CSV notes, v26 Next hint, version check. |
| `explore.py` | 3 week night-by-night simulation with video (manual, not in `run.sh`). |

Run one test: `python tests/test_v16.py <name-fragment>`.

## Personal data (not in git)

Two suites load real backups. They are gitignored, so point at your own copies:

- `STRIDE_START`: starter backup (default `~/Library/Mobile Documents/com~apple~CloudDocs/Gym Plan/liftlog-start.json`)
- `STRIDE_EXPORT`: a v22-era phone export (default `tests/v22-export.json`)

Other overrides: `STRIDE_APP` (app folder, defaults to the repo root) and `PY` (python with Playwright).

`REPORT-v16.md` (the QA report) and all generated output (screens, videos, results, exports) stay local.

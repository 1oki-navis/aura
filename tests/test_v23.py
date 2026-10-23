"""v23 suite: athletic look plan, new order Lower A > Upper A > Lower B > Upper B, one-time plan migration.

Run: python test_v23.py [name fragment]   (run.sh runs it after test_v20.py)
"""
import json, sys
from playwright.sync_api import sync_playwright
from ll import *
from test_v16 import page_with, base_db, S, assert_, SERVER

RESULTS = []
NEW_ORDER = ["Lower A", "Upper A", "Lower B", "Upper B"]
# A real v22 phone export, kept out of git. Override with STRIDE_EXPORT
EXPORT = json.loads(pathlib.Path(os.environ.get("STRIDE_EXPORT") or ROOT / "v22-export.json").read_text())


def names(d, ses):
    return [x["n"] for x in d["plan"][ses]]


def test_fresh_install_has_new_order_and_plan(br):
    ctx, pg = page_with(br)
    d = pg.evaluate("freshDB()")
    assert_(d["order"] == NEW_ORDER and d["pv"] == 24, d["order"])
    assert_("DB Glute Bridge" not in names(d, "Lower B"), names(d, "Lower B"))
    for s in ["Upper A", "Upper B"]:
        assert_({"Wrist Curl", "Reverse Wrist Curl"} <= set(names(d, s)), (s, names(d, s)))
    lb = names(d, "Lower B")
    assert_(lb.index("Seated Calf Raise") < lb.index("Abcore Side") < lb.index("Abcore Crunch"), lb)


def test_plan_targets_match_agreed_plan(br):
    ctx, pg = page_with(br)
    P = pg.evaluate("PLAN0")
    get = lambda s, n: next(x for x in P[s] if x["n"] == n)
    lev = get("Lower B", "Leverage Squat")
    assert_(lev["t"] == 30 and lev["s"] == "3 x 10-12" and "pain-free" in lev["tip"], lev)
    assert_(get("Lower B", "Lying Leg Curl")["s"].startswith("4 x") and get("Lower A", "Seated Leg Curl")["s"].startswith("4 x"), "curls 4 sets")
    assert_(get("Lower A", "Leg Press")["st"] == 10, "leg press step")
    kg = [x for a in P.values() for x in a if x["u"] == "kg" and x["n"] != "Leg Press"]
    assert_(all(x.get("st") == 5 for x in kg), [x["n"] for x in kg if x.get("st") != 5])
    assert_(get("Upper B", "Assisted Pull-up").get("lb") and get("Upper A", "Assisted Dip").get("lb"), "assist flags")
    assert_(not any("\u2014" in json.dumps(a) for a in P.values()), "em dash")


def test_v22_phone_data_migrates_once_and_keeps_history(br):
    ctx, pg = page_with(br, EXPORT)
    d = db(pg)
    assert_(d["order"] == NEW_ORDER and d["pv"] == 24, d["order"])
    assert_("Hanging Leg Raise" not in names(d, "Lower B") and "Leverage Squat" in names(d, "Lower B"), names(d, "Lower B"))
    assert_(len(d["sets"]) == len(EXPORT["sets"]) and len(d["runs"]) == len(EXPORT["runs"]), "history kept")
    assert_(d["notes"] == pg.evaluate("n=>migrate({sets:n.sets,body:[],runs:[],notes:n.notes}).notes", EXPORT), "notes kept")
    assert_(not pg._errs, pg._errs)


def test_edits_after_v23_are_not_overwritten(br):
    data = json.loads(json.dumps(EXPORT)); data["pv"] = 23
    ctx, pg = page_with(br, data)
    d = db(pg)
    assert_("Hanging Leg Raise" in names(d, "Lower B") and d["order"][0] == "Upper A", d["order"])


def test_custom_plan_without_old_exercises_is_left_alone(br):
    plan = {o: [{"n": "My Lift", "s": "3 x 10", "t": 20, "u": "kg", "tip": ""}] for o in ["Upper A", "Lower A", "Upper B", "Lower B"]}
    ctx, pg = page_with(br, base_db(order=["Upper A", "Lower A", "Upper B", "Lower B"], plan=plan))
    d = db(pg)
    assert_(d["order"][0] == "Upper A" and names(d, "Lower B") == ["My Lift"] and d["pv"] == 24, d["order"])


def test_extra_session_is_kept_after_migration(br):
    data = json.loads(json.dumps(EXPORT)); data["order"] = data["order"] + ["Cardio"]
    data["plan"]["Cardio"] = [{"n": "Run", "s": "30 min", "t": 30, "u": "min", "tip": ""}]
    ctx, pg = page_with(br, data)
    d = db(pg)
    assert_(d["order"] == NEW_ORDER + ["Cardio"] and names(d, "Cardio") == ["Run"], d["order"])


def test_version_is_v23(br):
    ctx, pg = page_with(br, base_db())
    assert_("liftlog-v29" in (APP / "sw.js").read_text(), "sw")
    assert_("Stride · v29" in (APP / "index.html").read_text(), "footer")


def test_v24_ranges_migrate_only_if_unedited(br):
    data = json.loads(json.dumps(EXPORT)); data["pv"] = 23
    data["order"] = NEW_ORDER[:]
    data["plan"] = {o: [] for o in NEW_ORDER}
    data["plan"]["Lower A"] = [{"n": "Standing Calf Raise", "s": "4 x 10-15", "t": 30, "u": "kg", "tip": ""}]
    data["plan"]["Upper A"] = [{"n": "Wrist Curl", "s": "3 x 10", "t": 5, "u": "kg", "tip": ""}]
    ctx, pg = page_with(br, data)
    d = db(pg)
    assert_(d["plan"]["Lower A"][0]["s"] == "4 x 12-20" and d["plan"]["Upper A"][0]["s"] == "3 x 10" and d["pv"] == 24, d["plan"])


def test_csv_exports_exercise_notes(br):
    sets = [S(1, "2026-10-19", "Lower A", "Hack Squat", 25, 10), S(2, "2026-10-19", "Lower A", "Hack Squat", 25, 8)]
    notes = {"2026-10-19|Hack Squat": 'Hard, "but" doable', "2026-10-19|Side Plank": "Skipped, back tight"}
    ctx, pg = page_with(br, base_db(sets=sets, notes=notes))
    csv_txt = pg.evaluate("""() => { let out=''; const o=shareFile; shareFile=(n,t)=>{out=t}; exportCSV(); shareFile=o; return out }""")
    import csv as _c, io
    rows = list(_c.DictReader(io.StringIO(csv_txt)))
    hs = [r for r in rows if r["Exercise"] == "Hack Squat"]
    assert_("Exercise note" in rows[0], list(rows[0]))
    assert_([r["Exercise note"] for r in hs] == ['Hard, "but" doable', ""], [r["Exercise note"] for r in hs])
    sp = [r for r in rows if r["Exercise"] == "Side Plank"]
    assert_(len(sp) == 1 and sp[0]["Exercise note"] == "Skipped, back tight" and sp[0]["Reps"] == "" and sp[0]["Date"] == "2026-10-19", sp)


def test_v26_next_hint_cases(br):
    ctx, pg = page_with(br, base_db())
    cases = [
        ({"n": "Leg Press", "s": "3 x 10-15", "u": "kg", "st": 10}, [(100, 15), (100, 15), (100, 15)], "All at 15, add weight"),
        ({"n": "Lat Pulldown", "s": "3 x 8-12", "u": "kg", "st": 5}, [(35, 20), (35, 12), (35, 10)], "Too easy, add weight"),
        ({"n": "Lat Pulldown", "s": "3 x 8-12", "u": "kg", "st": 5}, [(40, 12), (40, 12), (40, 8)], ""),
        ({"n": "Lat Pulldown", "s": "3 x 8-12", "u": "kg", "st": 5}, [(40, 12), (40, 12)], ""),
        ({"n": "Incline Press", "s": "2 x 8-12", "u": "kg", "st": 5}, [(10, 12), (10, 12), (5, 8)], "All at 12, add weight"),
        ({"n": "Assisted Dip", "s": "2 x 8-12", "u": "kg", "st": 5, "lb": True}, [(35, 12), (35, 12)], "All at 12, take 5 kg less assist"),
        ({"n": "Assisted Dip", "s": "2 x 8-12", "u": "kg", "st": 5, "lb": True}, [(36, 20), (36, 15)], "Too easy, take 5 kg less assist"),
        ({"n": "Side Plank", "s": "2 x 30-60 s / side", "u": "sec"}, [(0, 60), (0, 60)], "All at 60 s, make it harder"),
        ({"n": "Side Plank", "s": "2 x 30-60 s / side", "u": "sec"}, [(0, 30), (0, 30)], ""),
        ({"n": "Wrist Curl", "s": "2 x 15-25", "u": "kg", "st": 5}, [(5, 25), (5, 25)], "All at 25, add weight"),
        ({"n": "Abcore Crunch", "s": "Optional 2 x 12-15", "u": "kg", "st": 5}, [(10, 15), (10, 15)], "All at 15, add weight"),
    ]
    for p, sets, want in cases:
        last = {"d": "2026-10-20", "sets": [{"kg": k, "r": r} for k, r in sets]}
        got = pg.evaluate("([p,l])=>nextHint(p,l)", [p, last])
        assert_(got == want, (p["n"], sets, got))
    assert_(pg.evaluate("([p,l])=>nextHint(p,l)", [{"n": "X", "s": "3 x 10", "u": "kg"}, {"d": "x", "sets": [{"kg": 1, "r": 10}] * 3}]) == "", "no range, no hint")
    assert_(pg.evaluate("([p,l])=>nextHint(p,l)", [{"n": "X", "s": "3 x 10-12", "u": "kg"}, {"d": "x", "sets": [{"kg": 1, "r": 15, "w": 1}] * 3}]) == "", "warmups ignored")


def test_v26_card_shows_next_hint_and_hides_when_done(br):
    ctx, pg = page_with(br, base_db())
    html = pg.evaluate("(()=>{const p={n:'Leg Press',s:'3 x 10-15',u:'kg',st:10}; return tgtLines(p)})()")
    assert_("Sets" in html and "start 10 → work to 15" in html, html)
    html = pg.evaluate("tgtLines({n:'Side Plank',s:'2 x 30-60 s / side',u:'sec'})")
    assert_("<b>Sets</b>2 · per side" in html and "<b>Hold</b>start 30 → work to 60 s<" in html, html)
    html = pg.evaluate("tgtLines({n:'Abcore Crunch',s:'Optional 2 x 12-15',u:'kg'})")
    assert_("Optional · 2" in html, html)


def test_v28_next_hint_only_in_open_card(br):
    ctx, pg = page_with(br, base_db())
    src = pg.evaluate("exRow.toString()")
    assert_("tip ok" in src and "Next" in src, "Next hint not rendered in open card")
    closed = pg.evaluate("[...document.querySelectorAll('.ex:not(.open) .ex-sum, .ex:not(.open) summary')].map(e=>e.textContent).join('|')")
    assert_("Next ·" not in closed, closed)


def test_v29_cloud_is_worker_and_sw_skips_cross_origin(br):
    html = (APP / "index.html").read_text(); sw = (APP / "sw.js").read_text()
    assert_("const CLOUD='https://stride-coach.lokis-space.workers.dev'" in html, "CLOUD url")
    assert_("origin!==location.origin)return" in sw, "sw must ignore cross-origin requests")
    assert_(not (APP / "netlify").exists() and not (APP / "package.json").exists(), "netlify files left")


def main():
    SERVER["p"] = serve()
    only = sys.argv[1:]
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and (not only or any(o in n for o in only))]
    with sync_playwright() as p:
        br = p.webkit.launch()
        for n, f in tests:
            try:
                f(br); RESULTS.append((n, True, "")); print("PASS", n)
            except Exception as e:
                RESULTS.append((n, False, f"{type(e).__name__}: {str(e)[:300]}")); print("FAIL", n, str(e)[:300])
            finally:
                for c in br.contexts:
                    c.close()
        br.close()
    stop(SERVER["p"])
    (ROOT / "v23-results.json").write_text(json.dumps(RESULTS, indent=1))
    print(f"{sum(r[1] for r in RESULTS)}/{len(RESULTS)} passed")
    sys.exit(0 if all(r[1] for r in RESULTS) else 1)


if __name__ == "__main__":
    main()

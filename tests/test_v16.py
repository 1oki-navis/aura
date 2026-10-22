"""v16 regression suite. Every test here was written to fail on v15 first, then the app was fixed.

Run: python test_v16.py   (run.sh runs it after the legacy suite)
"""
import csv, io, json, re, shutil, sys, tempfile, time, traceback, pathlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright
from ll import *

RESULTS = []
NIGHT = datetime(2026, 10, 8, 23, 15)


# The older suites test app behaviour against the v22 Phase 2 plan, so pin it (pv 23 = no v23 plan swap)
V22_PLAN = json.loads((pathlib.Path(__file__).parent / "v22-plan.json").read_text())


def base_db(**kw):
    d = {"ver": 2, "pv": 23, "created": 1, "sets": [], "body": [], "runs": [], "notes": {}, "fin": {}, "lastExportCount": 0,
         "order": ["Upper A", "Lower A", "Upper B", "Lower B"], "plan": json.loads(json.dumps(V22_PLAN))}
    d.update(kw)
    return d


def S(i, d, ses, ex, kg, r):
    return {"id": f"s{1759000000000 + i}", "d": d, "ses": ses, "ex": ex, "kg": kg, "r": r, "note": "", "w": False}


def page_with(br, data=None, when=NIGHT, tz="Asia/Kolkata"):
    # Playwright reads naive datetimes in the host timezone, so pin them to the page timezone
    if when.tzinfo is None:
        when = when.replace(tzinfo=ZoneInfo(tz))
    ctx = new_ctx(br, tz=tz, when=when)
    pg = ctx.new_page(); pg.goto(URL); pg.wait_for_timeout(150)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg._errs = errs
    if data is not None:
        put(pg, data)
    return ctx, pg


def assert_(cond, msg=""):
    if not cond:
        raise AssertionError(msg)


# ---------- Runs ----------
def test_run_pace_never_shows_60_seconds(br):
    ctx, pg = page_with(br, base_db())
    nav(pg, "Run"); pg.fill("#rd", "2026-10-08"); pg.fill("#rk", "3"); pg.fill("#rt", "17:59"); pg.click("[data-act=addRun]")
    txt = pg.locator("main").inner_text()
    assert_("6:00/km" in txt and ":60" not in txt, re.findall(r"\d+:\d+/km", txt))


def test_easy_percent_ignores_runs_without_hr_and_155_is_hard(br):
    runs = [{"id": "r1", "d": "2026-10-01", "km": 3, "sec": 1200, "hr": 140, "note": ""},
            {"id": "r2", "d": "2026-10-02", "km": 3, "sec": 1200, "hr": 0, "note": ""},
            {"id": "r3", "d": "2026-10-03", "km": 3, "sec": 1200, "hr": 155, "note": ""}]
    ctx, pg = page_with(br, base_db(runs=runs)); nav(pg, "Run")
    txt = pg.locator("main").inner_text()
    assert_("Easy runs: 50%" in txt, re.findall(r"Easy runs: [^.]*", txt))
    row = pg.locator(".best", has_text="3 Oct").inner_text().lower()
    assert_("too hard" in row, row)


def test_run_note_survives_hr_edit(br):
    ctx, pg = page_with(br, base_db()); nav(pg, "Run")
    pg.fill("#rd", "2026-10-08"); pg.fill("#rk", "2.5"); pg.fill("#rt", "16:40"); pg.fill("#rn", "Night loop, it's cold"); pg.click("[data-act=addRun]")
    pg.wait_for_timeout(400)
    pg.locator(".rowbtn").first.click(); pg.fill("#rh", "148"); pg.click("[data-act=addRun]")
    r = db(pg)["runs"]
    assert_(len(r) == 1 and r[0]["hr"] == 148 and r[0]["note"] == "Night loop, it's cold", r)


# ---------- Body ----------
def test_body_waist_only_keeps_weight_same_day(br):
    ctx, pg = page_with(br, base_db()); nav(pg, "Body")
    pg.fill("#bd", "2026-10-05"); pg.fill("#bk", "58.5"); pg.click("[data-act=addBody]"); pg.wait_for_timeout(400)
    pg.fill("#bd", "2026-10-05"); pg.fill("#bw", "74"); pg.click("[data-act=addBody]")
    b = db(pg)["body"]
    assert_(b == [{"d": "2026-10-05", "kg": 58.5, "waist": 74}], b)


def test_body_rejects_bad_values(br):
    ctx, pg = page_with(br, base_db()); nav(pg, "Body")
    for kg in ["-5", "9999", "0.5"]:
        pg.fill("#bd", "2026-10-05"); pg.fill("#bk", kg); pg.click("[data-act=addBody]"); pg.wait_for_timeout(400)
    assert_(db(pg)["body"] == [], db(pg)["body"])
    pg.fill("#bk", "58,7"); pg.click("[data-act=addBody]")
    assert_(db(pg)["body"][0]["kg"] == 58.7, db(pg)["body"])


def test_body_rate_uses_last_28_days(br):
    # +0.5 kg a week for 4 weeks, then flat for 4 weeks. The last 28 days are flat.
    ws = [58, 58.5, 59, 59.5, 60, 60, 60, 60, 60]
    body = [{"d": (datetime(2026, 8, 10) + timedelta(days=7 * i)).date().isoformat(), "kg": w, "waist": 0} for i, w in enumerate(ws)]
    ctx, pg = page_with(br, base_db(body=body)); nav(pg, "Body")
    m = re.search(r"([+-][0-9.]+) kg/week over the last 4 weeks", pg.locator("main").inner_text())
    assert_(m and m.group(1) == "+0.00", m and m.group(0))


# ---------- Plan editor ----------
def test_plan_reorder(br):
    ctx, pg = page_with(br, base_db()); pg.evaluate("pickSes('Upper A')")
    pg.click("[data-act=editPlan]")
    first = pg.evaluate("PLANED.rows.map(r=>r.n)")
    pg.locator("#planed [data-act=movePlan][data-i='1'][data-dir='-1']").click()
    pg.locator(f"#planed [data-act=movePlan][data-i='{len(first) - 2}'][data-dir='1']").click()
    pg.click("[data-act=savePlan]")
    after = [p["n"] for p in db(pg)["plan"]["Upper A"]]
    want = first[:]; want[0], want[1] = want[1], want[0]; want[-2], want[-1] = want[-1], want[-2]
    assert_(after == want, after)
    assert_(pg.locator("[data-act=movePlan]").count() == 0)


def test_plan_edit_keeps_typed_text_when_moving(br):
    ctx, pg = page_with(br, base_db()); pg.evaluate("pickSes('Upper A')"); pg.click("[data-act=editPlan]")
    pg.click("[data-act=addPlan]"); pg.locator("#planed [data-f=n]").last.fill("Cable Fly")
    n = pg.evaluate("PLANED.rows.length")
    pg.locator(f"#planed [data-act=movePlan][data-i='{n - 1}'][data-dir='-1']").click()
    assert_(pg.evaluate("PLANED.rows.map(r=>r.n)")[n - 2] == "Cable Fly")


def test_unit_change_keeps_kg_history(br):
    sets = [S(1, "2026-10-05", "Upper A", "Abcore Crunch", 10, 12), S(2, "2026-10-05", "Upper A", "Abcore Crunch", 12.5, 12)]
    ctx, pg = page_with(br, base_db(sets=sets)); pg.evaluate("pickSes('Upper A')"); pg.click("[data-act=editPlan]")
    i = pg.evaluate("PLANED.rows.findIndex(r=>r.n==='Abcore Crunch')")
    pg.locator(f"#planed select[data-pi='{i}']").select_option("BW"); pg.click("[data-act=savePlan]")
    pg.reload(); pg.wait_for_timeout(100)
    pg.click("[data-act=editPlan]"); pg.locator(f"#planed select[data-pi='{i}']").select_option("kg"); pg.click("[data-act=savePlan]")
    pg.reload(); pg.wait_for_timeout(100)
    kgs = [s["kg"] for s in db(pg)["sets"]]
    assert_(kgs == [10, 12.5], kgs)


def test_removed_exercise_keeps_unit(br):
    sets = [S(1, "2026-10-06", "Lower A", "Plank", 0, 45), S(2, "2026-10-06", "Lower A", "Knee Raise", 0, 10)]
    ctx, pg = page_with(br, base_db(sets=sets)); pg.evaluate("pickSes('Lower A')"); pg.click("[data-act=editPlan]")
    for n in ["Plank", "Knee Raise"]:
        i = pg.evaluate(f"PLANED.rows.findIndex(r=>r.n==='{n}')"); pg.locator(f"[data-act=rmPlan][data-i='{i}']").click()
    pg.click("[data-act=savePlan]"); pg.reload(); pg.wait_for_timeout(100)
    nav(pg, "Log"); pg.locator(".sess").first.click()
    txt = pg.locator("main").inner_text()
    assert_("45 sec" in txt and "BW × 10" in txt and "0 kg" not in txt, txt[-200:])


def test_unit_change_to_seconds_resets_start(br):
    ctx, pg = page_with(br, base_db()); pg.evaluate("pickSes('Lower A')"); pg.click("[data-act=editPlan]")
    i = pg.evaluate("PLANED.rows.findIndex(r=>r.n==='Leg Extension')")
    pg.locator(f"#planed select[data-pi='{i}']").select_option("sec")
    pg.locator(f"#planed [data-pi='{i}'][data-f=s]").fill("2 x 30 s"); pg.click("[data-act=savePlan]")
    tgt = card(pg, "Leg Extension").locator(".tgt").inner_text().lower().split()
    assert_(tgt[0] == "30" and "sec" in tgt, tgt)


def test_rename_and_delete_keep_history(br):
    sets = [S(i, "2026-10-05", "Upper A", "Bicep Curl", 17.5, 12) for i in range(3)]
    ctx, pg = page_with(br, base_db(sets=sets)); pg.evaluate("pickSes('Upper A')"); pg.click("[data-act=editPlan]")
    i = pg.evaluate("PLANED.rows.findIndex(r=>r.n==='Bicep Curl')")
    pg.locator(f"#planed [data-pi='{i}'][data-f=n]").fill("Preacher Curl"); pg.click("[data-act=savePlan]")
    d = db(pg)
    assert_(sum(s["ex"] == "Bicep Curl" for s in d["sets"]) == 3)
    nav(pg, "Stats"); txt = pg.locator("main").inner_text()
    assert_("Bicep Curl" in txt and "17.5 kg × 12" in txt)


# ---------- Lift inputs ----------
def lift(pg, ses, ex):
    pg.evaluate(f"go('today'); pickSes('{ses}'); OPEN='{ex}'; render()")


def test_kg_comma_decimal(br):
    ctx, pg = page_with(br, base_db()); lift(pg, "Upper A", "Chest Press")
    pg.fill("#kg", "22,5"); pg.fill("#r", "10"); pg.click("[data-act=logSet]")
    s = db(pg)["sets"]
    assert_(len(s) == 1 and s[0]["kg"] == 22.5, s)


def test_reps_integer_and_caps(br):
    ctx, pg = page_with(br, base_db()); lift(pg, "Upper A", "Chest Press")
    for kg, r in [("2255", "10"), ("25", "500"), ("abc", "10")]:
        pg.fill("#kg", kg); pg.fill("#r", r); pg.click("[data-act=logSet]"); pg.clock.fast_forward(1000)
    assert_(db(pg)["sets"] == [], db(pg)["sets"])
    pg.fill("#kg", "25"); pg.fill("#r", "8.6"); pg.click("[data-act=logSet]")
    assert_(db(pg)["sets"][0]["r"] == 9, db(pg)["sets"])


def test_cardio_rejects_zero_negative_and_caps(br):
    ctx, pg = page_with(br, base_db()); lift(pg, "Upper A", "Bike warmup")
    for v in ["0", "-3", "abc", "900"]:
        pg.fill("#r", v); pg.click("[data-act=logCardio]"); pg.clock.fast_forward(1000)
        if not pg.locator("#r").count():
            card(pg, "Bike warmup").click()
    assert_(db(pg)["sets"] == [], db(pg)["sets"])


# ---------- Backups ----------
def test_empty_screen_restore_keeps_plan_and_notes(br):
    data = base_db(sets=[S(1, "2026-10-05", "Upper A", "Chest Press", 25, 10)], notes={"Chest Press": "Seat 4"},
                   plan={"Upper A": [{"n": "Chest Press", "s": "3 x 8-10", "t": 25, "u": "kg", "tip": ""}], "Lower A": [], "Upper B": [{"n": "Cable Row", "s": "3 x 10", "t": 20, "u": "kg", "tip": ""}], "Lower B": []})
    f = pathlib.Path(tempfile.mkdtemp()) / "b.json"; f.write_text(json.dumps(data))
    ctx, pg = page_with(br); pg.evaluate("localStorage.clear()"); pg.reload()
    pg.locator("[data-act=pickImport]").click(); pg.locator("#imp").set_input_files(str(f)); pg.wait_for_timeout(300)
    d = db(pg)
    shutil.rmtree(f.parent)
    assert_(d["plan"]["Upper B"][0]["n"] == "Cable Row" and d["notes"] == {"2026-10-05|Chest Press": "Seat 4"}, (d["plan"]["Upper B"], d["notes"]))


def test_xss_ids_in_backup_escaped(br):
    evil = '"><img src=x onerror="window.__pwn=1">'
    data = base_db(sets=[dict(S(1, "2026-10-08", "Upper A", "Chest Press", 25, 10), id=evil)],
                   runs=[{"id": evil, "d": "2026-10-07", "km": 3, "sec": 1200, "hr": 0, "note": "<b>x</b>"}])
    ctx, pg = page_with(br, data)
    for t in ["today", "history", "runs"]:
        pg.evaluate(f"go('{t}'); OPEN='Chest Press'; SES='Upper A'; render()")
    pg.wait_for_timeout(200)
    assert_(not pg.evaluate("window.__pwn") and pg.locator("main img").count() == 0)


def test_malformed_plan_backup_does_not_crash(br):
    for plan in [{"Upper A": "abc"}, {"Upper A": [None, 5, {"n": None}, {"n": "Ok", "t": "<x>"}]}, "nope", [1, 2]]:
        ctx, pg = page_with(br, base_db(plan=plan))
        txt = pg.locator("main").inner_text()
        assert_("Something broke" not in txt and "Recovery" not in txt, (plan, txt[:80]))
        pg.click("[data-act=editPlan]")
        assert_(not pg._errs, pg._errs)
        ctx.close()


def test_corrupt_storage_kept_aside(br):
    for raw in ["{bad json", "5", "[]", '"str"', '{"sets":"x"}']:
        ctx, pg = page_with(br)
        pg.evaluate("r => localStorage.setItem('liftlog.v1', r)", raw); pg.reload(); pg.wait_for_timeout(100)
        txt = pg.locator("main").inner_text()
        assert_("Something broke" not in txt and pg.locator("nav button").count() == 6, (raw, txt[:60]))
        if raw in ["{bad json", "5", '"str"', "[]"]:
            assert_(pg.evaluate("localStorage.getItem('liftlog.corrupt')") == raw, raw)
            assert_("could not be read" in txt, txt[:200])
        ctx.close()


def test_empty_and_huge_and_old_backups(br):
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "empty.json").write_text("")
    big = base_db(sets=[S(i, f"2025-{1 + i % 12:02d}-{1 + i % 28:02d}", "Upper A", "Chest Press", 25, 8) for i in range(20000)])
    (tmp / "huge.json").write_text(json.dumps(big))
    old = {"ver": 1, "sets": [{"id": "a1", "d": "2026-09-01", "ses": "Upper A", "ex": "Assisted Dip", "kg": 30, "r": 8, "w": True}], "body": [], "runs": [{"d": "2026-09-02", "km": 3, "sec": 1300}],
           "plan": {"Upper A": [{"n": "Assisted Dip", "s": "3 x 8", "t": 30, "u": "assist", "tip": ""}, {"n": "Hack Squat", "s": "3 x 8", "t": 0, "u": "sled", "tip": "sled"}]}, "checks": {"x": 1}}
    (tmp / "old.json").write_text(json.dumps(old))
    ctx, pg = page_with(br, base_db()); nav(pg, "Save")
    pg.get_by_text("Merge backup").click(); pg.locator("#imp").set_input_files(str(tmp / "empty.json")); pg.wait_for_timeout(300)
    assert_("not a stride backup" in toast(pg).lower(), toast(pg))
    # the phone is empty, so Replace needs no confirm
    t0 = time.time(); pg.get_by_text("Replace backup").click(); pg.locator("#imp").set_input_files(str(tmp / "huge.json")); pg.wait_for_timeout(300)
    # wait_for_function polls with rAF, which the installed fake clock makes unreliable, so poll from Python
    while pg.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.length") != 20000 and time.time() - t0 < 10:
        time.sleep(0.1)
    assert_(time.time() - t0 < 5, time.time() - t0)
    pg.wait_for_timeout(400)  # a repeat tap within 350 ms is ignored by the double-tap guard
    pg.once("dialog", lambda d: d.accept())
    pg.get_by_text("Replace backup").click(); pg.locator("#imp").set_input_files(str(tmp / "old.json")); pg.wait_for_timeout(300)
    d = db(pg); shutil.rmtree(tmp)
    assert_(len(d["sets"]) == 1, len(d["sets"]))
    ua = {p["n"]: p for p in d["plan"]["Upper A"]}
    assert_(ua["Assisted Dip"]["u"] == "kg" and ua["Assisted Dip"]["lb"] and ua["Hack Squat"]["u"] == "kg" and "checks" not in d and d["runs"][0]["id"], ua)


def test_quota_error_is_reported_and_not_lost(br):
    ctx, pg = page_with(br, base_db()); lift(pg, "Upper A", "Chest Press")
    pg.evaluate("""() => { const o = Storage.prototype.setItem; window.__full = true;
      Storage.prototype.setItem = function (k, v) { if (window.__full && k === 'liftlog.v1') { const e = new Error('full'); e.name = 'QuotaExceededError'; throw e } return o.call(this, k, v) } }""")
    pg.fill("#kg", "25"); pg.fill("#r", "10"); pg.click("[data-act=logSet]")
    msg = toast(pg).lower()
    assert_("storage full" in msg, msg)
    assert_(pg.evaluate("DB.sets.length") == 0 and pg.locator(".set").count() == 0, "phantom set shown")
    assert_(not pg._errs, pg._errs)
    pg.evaluate("window.__full = false"); pg.clock.fast_forward(5000)
    pg.fill("#kg", "25"); pg.fill("#r", "10"); pg.click("[data-act=logSet]")
    assert_(len(db(pg)["sets"]) == 1)


def test_csv_formula_injection(br):
    sets = [S(1, "2026-10-05", "Upper A", "=HYPERLINK(\"http://x\")", 10, 10), S(2, "2026-10-05", "Upper A", "Plank", 7, 45)]
    ctx, pg = page_with(br, base_db(sets=sets)); nav(pg, "Save")
    with pg.expect_download() as dl:
        pg.get_by_text("Export CSV").click()
    rows = list(csv.reader(io.StringIO(open(dl.value.path()).read())))
    assert_(rows[1][2].startswith("'="), rows[1])
    plank = [r for r in rows if r[2] == "Plank"][0]
    assert_(plank[4] == "" and plank[3] == "sec", plank)


def test_sets_since_never_negative(br):
    ctx, pg = page_with(br, base_db(sets=[S(1, "2026-10-05", "Upper A", "Chest Press", 25, 10)]))
    pg.evaluate("localStorage.setItem('liftlog.backup','2026-10-07'); localStorage.setItem('liftlog.backup.count','90')"); nav(pg, "Save")
    assert_("-89" not in pg.locator("main").inner_text() and "0 sets since" in pg.locator("main").inner_text().lower())


# ---------- Wording ----------
def test_pluralisation(br):
    ctx, pg = page_with(br, base_db(sets=[S(1, "2026-10-05", "Upper A", "Chest Press", 25, 10)]))
    nav(pg, "Log"); txt = pg.locator("main").inner_text().lower()
    assert_("1 session · 1 set" in txt and "1 set · 1 exercise" in txt and "1 sets" not in txt and "1 exercises" not in txt, txt[:200])


# ---------- Time ----------
def week_db():
    # Mon 28 Dec 2026 to Sun 3 Jan 2027 has 3 sessions, so does the week before
    days = ["2026-12-21", "2026-12-23", "2026-12-25", "2026-12-28", "2026-12-31", "2027-01-02"]
    return base_db(sets=[S(i, d, ["Upper A", "Lower A", "Upper A"][i % 3], "Chest Press", 25, 10) for i, d in enumerate(days)])


def test_week_maths_far_east_timezone(br):
    for tz in ["Pacific/Kiritimati", "Etc/GMT+12", "Asia/Kolkata"]:
        ctx, pg = page_with(br, week_db(), when=datetime(2027, 1, 3, 22, 0), tz=tz); nav(pg, "Stats")
        v = pg.locator(".trio.t2 .dot.n").all_inner_texts()
        assert_(v[0].replace("\n", "") == "3/4" and v[1] == "2", (tz, v))
        assert_(pg.evaluate("lastWeeks(2)") == ["2026-12-21", "2026-12-28"], (tz, pg.evaluate("lastWeeks(2)")))
        ctx.close()


def test_dst_and_5am_boundary(br):
    # UK clocks go back on Sun 25 Oct 2026
    ctx, pg = page_with(br, base_db(), when=datetime(2026, 10, 25, 4, 59), tz="Europe/London")
    assert_(pg.evaluate("gymDate()") == "2026-10-24")
    pg.clock.set_system_time(datetime(2026, 10, 25, 5, 0, 1, tzinfo=ZoneInfo("Europe/London")))
    assert_(pg.evaluate("gymDate()") == "2026-10-25")
    assert_(pg.evaluate("wk('2026-10-25')") == "2026-10-19" and pg.evaluate("wk('2026-10-26')") == "2026-10-26")
    assert_(pg.evaluate("lastWeeks(2)") == ["2026-10-12", "2026-10-19"], pg.evaluate("lastWeeks(2)"))


def test_dayroll_on_tab_switch(br):
    ctx, pg = page_with(br, base_db()); lift(pg, "Upper A", "Chest Press")
    pg.fill("#kg", "25"); pg.fill("#r", "10"); pg.click("[data-act=logSet]")
    nav(pg, "Log")
    pg.clock.set_system_time(datetime(2026, 10, 9, 23, 10))
    nav(pg, "Lift")
    assert_(pg.evaluate("SES") == "Lower A" and pg.locator(".set").count() == 0, pg.evaluate("SES"))


# ---------- Taps and a11y ----------
def test_double_tap_save_entry_keeps_undo(br):
    ctx, pg = page_with(br, base_db()); nav(pg, "Body")
    pg.fill("#bk", "58.5"); pg.locator("[data-act=addBody]").dblclick()
    assert_("undo" in toast(pg).lower(), toast(pg))
    nav(pg, "Run"); pg.fill("#rk", "3"); pg.fill("#rt", "20:00"); pg.locator("[data-act=addRun]").dblclick()
    assert_("run saved" in toast(pg).lower(), toast(pg))


def test_rapid_taps(br):
    ctx, pg = page_with(br, base_db()); lift(pg, "Upper A", "Chest Press")
    pg.locator("[data-act=logSet]").dblclick()
    assert_(len(db(pg)["sets"]) == 1)
    pg.locator(".ex-h[data-n='Lat Pulldown']").dblclick()
    assert_(pg.evaluate("OPEN") == "Lat Pulldown", pg.evaluate("OPEN"))
    for _ in range(6):
        pg.locator("[data-act=adj][data-k=r]").last.click()
    assert_(pg.locator("#r").input_value() != "", "adj fast taps")
    pg.locator("[data-act=finish]").dblclick(); pg.wait_for_timeout(100)
    assert_(len(db(pg)["fin"]) == 1 and pg.evaluate("SES") == "Lower A")
    nav(pg, "Log"); pg.locator(".sess").first.dblclick()
    assert_(pg.evaluate("OPEN") is not None)


def test_tab_switch_mid_edit(br):
    ctx, pg = page_with(br, base_db()); lift(pg, "Upper A", "Chest Press")
    pg.fill("#kg", "25"); pg.fill("#r", "10"); pg.click("[data-act=logSet]"); pg.clock.fast_forward(1000)
    lift(pg, "Upper A", "Chest Press"); pg.locator(".set .v").first.click(); pg.fill("#r", "3")
    for t in ["Log", "Stats", "Lift"]:
        nav(pg, t)
    assert_(pg.evaluate("EDIT") is None and db(pg)["sets"][0]["r"] == 10)


def test_back_button_tap_target(br):
    ctx, pg = page_with(br, base_db(sets=[S(1, "2026-10-05", "Upper A", "Chest Press", 25, 10)]))
    pg.evaluate("openEx('Chest Press')")
    r = pg.locator(".back").bounding_box()
    assert_(r["height"] >= 44 and r["width"] >= 44, r)


def test_all_inputs_44px_tall(br):
    ctx, pg = page_with(br, base_db())
    bad = []
    for setup in ["go('today'); pickSes('Upper A'); OPEN='Chest Press'; render()", "OPEN='Bike warmup'; render()", "go('body')", "go('runs')", "go('today'); editPlan()"]:
        pg.evaluate(setup)
        bad += pg.evaluate("[...document.querySelectorAll('input:not([hidden]),select')].filter(e=>e.getBoundingClientRect().height<44).map(e=>e.id||e.className||e.dataset.f)")
    assert_(not bad, bad)


def test_buttons_have_accessible_names(br):
    ctx, pg = page_with(br, base_db(sets=[S(1, "2026-10-08", "Upper A", "Chest Press", 25, 10)], runs=[{"id": "r1", "d": "2026-10-01", "km": 3, "sec": 1200, "hr": 0, "note": ""}], body=[{"d": "2026-10-05", "kg": 58, "waist": 0}]))
    bad = []
    for setup in ["go('today'); pickSes('Upper A'); OPEN='Chest Press'; render()", "OPEN='Bike warmup'; render()", "go('runs')", "go('body')"]:
        pg.evaluate(setup)
        bad += pg.evaluate("""[...document.querySelectorAll('button,[data-act=delSet],input:not([hidden])')].filter(e => {
          const n = (e.getAttribute('aria-label') || (e.labels && e.labels[0] && e.labels[0].textContent) || e.textContent || '').trim();
          return !/[a-z]{2}/i.test(n) }).map(e => e.outerHTML.slice(0, 60))""")
    assert_(not bad, bad[:5])


# ---------- Text safety ----------
def test_names_with_emoji_quotes_html(br):
    names = ["Bench 💪 \"Pin\" d'Arc", "<img src=x onerror=window.__p2=1>", "A" * 60]
    ctx, pg = page_with(br, base_db()); pg.evaluate("pickSes('Upper B')")
    pg.click("[data-act=editPlan]")
    for n in names:
        pg.click("[data-act=addPlan]"); pg.locator("#planed [data-f=n]").last.fill(n); new_row_details(pg)
    pg.click("[data-act=savePlan]")
    for n in names:
        pg.wait_for_timeout(400)  # stay outside the 350 ms double-tap guard
        card(pg, n.replace('"', '\\"')).click(); pg.fill("#kg", "20"); pg.fill("#r", "10"); pg.click("[data-act=logSet]"); pg.clock.fast_forward(1000)
        pg.fill(".noteinp", "it's \"fine\" <b>ok</b> 🙂") if pg.locator(".noteinp").count() else None
    for t in ["Lift", "Log", "Stats"]:
        nav(pg, t)
        if t == "Log":
            pg.locator(".sess").first.click()
        assert_(not overflow_x(pg), t)
    pg.evaluate("openEx(" + json.dumps(names[0]) + ")")
    assert_("Bench 💪" in pg.locator("main").inner_text() and not pg.evaluate("window.__p2"))


# ---------- Rotation ----------
def test_rotation_and_midrotation_edit(br):
    plan = {o: [{"n": f"{o} Ex", "s": "1 x 10", "t": 10, "u": "kg", "tip": ""}] for o in ["Upper A", "Lower A", "Upper B", "Lower B"]}
    ctx, pg = page_with(br, base_db(plan=plan))
    seen = []
    for k in range(5):
        pg.clock.set_system_time(datetime(2026, 10, 8 + k, 23, 15)); pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        ses = pg.evaluate("SES"); seen.append(ses)
        card(pg, f"{ses} Ex").click(); pg.click("[data-act=logSet]"); pg.locator("[data-act=finish]").click()
        if k == 1:  # mid-rotation edit: empty Upper B gets skipped, then restored
            pg.evaluate("pickSes('Upper B')"); pg.click("[data-act=editPlan]"); pg.locator("[data-act=rmPlan]").click(); pg.click("[data-act=savePlan]")
            assert_(pg.evaluate("nextSession()") == "Lower B", pg.evaluate("nextSession()"))
            pg.click("[data-act=editPlan]"); pg.click("[data-act=addPlan]"); pg.locator("#planed [data-f=n]").last.fill("Upper B Ex"); new_row_details(pg); pg.click("[data-act=savePlan]")
    assert_(seen == ["Upper A", "Lower A", "Upper B", "Lower B", "Upper A"], seen)



def test_unit_change_syncs_shared_exercise(br):
    # Same exercise in two sessions: a unit change in one must apply to both, or stats and logging disagree
    plan = {o: [] for o in ["Upper A", "Lower A", "Upper B", "Lower B"]}
    plan["Upper A"] = [{"n": "Abcore Crunch", "s": "2 x 12", "t": 10, "u": "kg", "tip": ""}]
    plan["Upper B"] = [{"n": "Abcore Crunch", "s": "2 x 12", "t": 10, "u": "kg", "tip": ""}]
    ctx, pg = page_with(br, base_db(plan=plan))
    pg.evaluate("pickSes('Upper A')"); pg.click("[data-act=editPlan]")
    pg.locator("#planed select[data-pi='0']").select_option("BW"); pg.click("[data-act=savePlan]")
    d = pg.evaluate("JSON.parse(localStorage.getItem('liftlog.v1'))")
    ub = d["plan"]["Upper B"][0]
    assert_(ub["u"] == "BW" and not ub.get("t"), ub)
    pg.evaluate("pickSes('Upper B')")
    assert_("kg" not in card(pg, "Abcore Crunch").inner_text().lower().replace("kg assist", ""), card(pg, "Abcore Crunch").inner_text())
    ctx.close()


def test_ex_page_cardio_label_and_exact_chart_label(br):
    plan = {o: [] for o in ["Upper A", "Lower A", "Upper B", "Lower B"]}
    plan["Upper A"] = [{"n": "Bike warmup", "s": "5 min", "t": 5, "u": "min", "tip": ""}, {"n": "Assisted Dip", "s": "3 x 8", "t": 30, "u": "kg", "lb": True, "tip": ""}]
    sets = [{"id": f"s{i}", "d": f"2026-10-0{i}", "ses": "Upper A", "ex": "Bike warmup", "kg": 0, "r": 6, "w": False} for i in (1, 2)]
    sets += [{"id": f"t{i}", "d": f"2026-10-0{i}", "ses": "Upper A", "ex": "Assisted Dip", "kg": k, "r": 8, "w": False} for i, k in ((1, 40), (2, 47.5))]
    ctx, pg = page_with(br, base_db(plan=plan, sets=sets))
    pg.evaluate("openEx('Bike warmup')")
    labs = pg.locator(".trio.t2 .lab").all_inner_texts()
    assert_("sets" not in " ".join(labs).lower(), labs)
    pg.evaluate("openEx('Assisted Dip')")
    ends = pg.evaluate("[...document.querySelectorAll('svg.chart')].map(s=>[...s.querySelectorAll('text[text-anchor=end]')][0].textContent)")
    assert_(ends and ends[0] == "47.5", ends)
    ctx.close()


def test_backup_nudge_hidden_mid_session(br):
    plan = {o: [] for o in ["Upper A", "Lower A", "Upper B", "Lower B"]}
    plan["Upper A"] = [{"n": "Chest Press", "s": "3 x 10", "t": 20, "u": "kg", "tip": ""}]
    old = [{"id": f"o{i}", "d": "2026-09-01", "ses": "Upper A", "ex": "Chest Press", "kg": 20, "r": 10, "w": False} for i in range(30)]
    ctx, pg = page_with(br, base_db(plan=plan, sets=old))
    pg.evaluate("pickSes('Upper A')")  # v19 refills an empty Upper B, so the rotation no longer lands here
    assert_("backup due" in pg.locator("main").inner_text().lower(), "nudge should show before the session")
    card(pg, "Chest Press").click(); pg.click("[data-act=logSet]"); pg.wait_for_timeout(400)
    assert_("backup due" not in pg.locator("main").inner_text().lower(), "nudge should hide mid-session")
    ctx.close()


def test_cardio_placeholder_and_plan_note_fit(br):
    plan = {o: [] for o in ["Upper A", "Lower A", "Upper B", "Lower B"]}
    tip = "Total plates. Add 5-10 kg once all sets hit the top reps, then reset reps"
    plan["Upper A"] = [{"n": "Bike warmup", "s": "5 min", "t": 5, "u": "min", "tip": ""}, {"n": "Leg Press", "s": "3 x 10", "t": 80, "u": "kg", "tip": tip}]
    ctx, pg = page_with(br, base_db(plan=plan))
    card(pg, "Bike warmup").click()
    fit = pg.evaluate("""(()=>{const e=document.querySelector('#cn'),c=document.createElement('canvas').getContext('2d'),cs=getComputedStyle(e);c.font=cs.fontSize+' '+cs.fontFamily;return c.measureText(e.placeholder).width<=e.clientWidth})()""")
    assert_(fit, pg.evaluate("document.querySelector('#cn').placeholder"))
    # v20: the plan Note field was removed on request; old tips stay in data but are never shown
    pg.wait_for_timeout(400); pg.click("[data-act=editPlan]")
    assert_(pg.locator("#planed [data-f=tip]").count() == 0, "plan note field is back")
    pg.click("[data-act=savePlan]")
    assert_(pg.evaluate("DB.plan['Upper A'][1].tip") == tip and tip.lower() not in pg.locator("main").inner_text().lower(), "tip shown or lost")
    ctx.close()

# ---------- Complaints ----------
def test_user_complaints_stay_fixed(br):
    sets = [S(1, "2026-10-06", "Lower A", "Plank", 0, 45), S(2, "2026-10-06", "Lower A", "Leg Press", 80, 12)]
    ctx, pg = page_with(br, base_db(sets=sets))
    pg.evaluate("go('today'); pickSes('Lower A')")
    html = pg.locator("main").inner_html().lower(); txt = pg.locator("body").inner_text().lower()
    assert_("sled" not in html and "kg assist" not in txt and "assist" not in pg.locator("#planed select, .tgt").all_inner_texts().__str__().lower(), "sled/assist")
    assert_("warmup" not in re.sub(r"bike warmup", "", txt) and "something else" not in txt and "creatine" not in txt and "protein" not in txt)
    card(pg, "Bike warmup").click()
    assert_(pg.locator(".ex.open .set").count() == 0 and pg.locator(".ex.open [data-act=logSet]").count() == 0 and pg.locator("#cn").count() == 1 and pg.locator("#kg").count() == 0)
    card(pg, "Plank").click()
    assert_(pg.locator("#kg").count() == 0 and "kg" not in pg.locator(".ex.open").inner_text().lower())
    hints = pg.locator(".lab.red").all_inner_texts() + pg.locator(".tip").all_inner_texts()
    # v20: hints are tailored targets now ("Next 40 kg × 12, 12, 9"), never the old generic step text
    assert_(not [h for h in hints if re.search(r"reps reset|same kg|then\s+\d|up from", h, re.I)], hints)
    pg.click("[data-act=editPlan]")
    opts = pg.locator("#planed select").first.locator("option").all_inner_texts()
    assert_(opts == ["kg", "bodyweight", "seconds", "cardio"], opts)
    i = pg.evaluate("PLANED.rows.findIndex(r=>r.n==='Plank')")
    assert_(pg.locator(f"#planed [data-pi='{i}'][data-f=t]").count() == 0 and pg.locator(f"#planed [data-pi='{i}'][data-f=st]").count() == 0)
    fs = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('.set .v')||document.body).fontSize)")
    assert_(fs <= 16, fs)


# ---------- PWA ----------
def test_footer_and_sw_version(br):
    sw = (APP / "sw.js").read_text(); html = (APP / "index.html").read_text()
    v = re.search(r'liftlog-(v\d+)', sw).group(1)
    assert_(v == "v27" and f"Stride · {v}" in html, v)


def test_sw_caches_every_file(br):
    sw = (APP / "sw.js").read_text()
    files = set(json.loads(re.search(r"FILES=(\[.*?\])", sw).group(1)))
    # Dev-only files (tests/, CHANGELOG.md, git) are not part of the offline app
    on_disk = {str(p.relative_to(APP)) for p in APP.rglob("*") if p.is_file() and not any(x.startswith(".") for x in p.relative_to(APP).parts)
               and p.relative_to(APP).parts[0] != "tests" and p.name != "CHANGELOG.md"}
    assert_(on_disk <= files, on_disk - files)


def test_no_em_dashes_anywhere(br):
    for p in APP.rglob("*"):
        rel = p.relative_to(APP).parts
        if p.is_file() and p.suffix in (".html", ".js", ".json", ".md") and rel[0] not in ("tests", ".git"):
            assert_("\u2014" not in p.read_text(), p)


def test_offline_reload_real(br):
    ctx = new_ctx(br); pg = ctx.new_page(); pg.goto(URL); pg.wait_for_timeout(1500)
    pg.reload(); pg.wait_for_timeout(500)
    assert_(pg.evaluate("!!navigator.serviceWorker.controller"))
    srv = SERVER["p"]; stop(srv)
    try:
        pg.reload(timeout=8000); pg.wait_for_timeout(300)
        assert_(pg.locator("nav button").count() == 6 and "Stride" in pg.title())
        pg2 = ctx.new_page(); pg2.goto(URL, timeout=8000); pg2.wait_for_timeout(300)
        assert_(pg2.locator("nav button").count() == 6, "kill and reopen offline")
    finally:
        SERVER["p"] = serve()


def test_sw_update_path(br):
    tmp = pathlib.Path(tempfile.mkdtemp()) / "app"; shutil.copytree(APP, tmp)
    stop(SERVER["p"]); srv = serve(tmp)
    try:
        ctx = new_ctx(br); pg = ctx.new_page(); pg.goto(URL); pg.wait_for_timeout(1500)
        v0 = pg.evaluate("caches.keys()"); time.sleep(1.1)
        (tmp / "sw.js").write_text((tmp / "sw.js").read_text().replace(v0[0], "liftlog-v99"))
        (tmp / "index.html").write_text((tmp / "index.html").read_text().replace("Stride · v", "Stride · v99 was v"))
        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))"); pg.wait_for_timeout(2500)
        keys = pg.evaluate("caches.keys()")
        assert_(keys == ["liftlog-v99"], keys)
        pg.reload(); pg.wait_for_timeout(500); nav(pg, "Save")
        assert_("v99 was" in pg.locator("main").inner_text().lower())
        ctx.close()
    finally:
        stop(srv); shutil.rmtree(tmp.parent); SERVER["p"] = serve()


SERVER = {}


def new_row_details(pg):
    # v20: a new exercise must say its sets x reps and kg step before the plan saves
    pg.wait_for_timeout(80)  # let the editor's rAF scroll-to-new-row settle under the fake clock
    pg.locator("#planed [data-f=s]").last.fill("3 x 10")
    if pg.locator("#planed [data-f=st]").count():
        pg.locator("#planed [data-f=st]").last.fill("2.5")

def _ses_db():
    plan = {o: [{"n": f"{o} Ex", "s": "1 x 10", "t": 10, "u": "kg", "tip": ""}] for o in ["Upper A", "Lower A", "Upper B", "Lower B"]}
    sets = [S(1, "2026-10-06", "Upper A", "Upper A Ex", 20, 10), S(2, "2026-10-07", "Lower A", "Lower A Ex", 30, 8)]
    return base_db(plan=plan, sets=sets, fin={"2026-10-06|Upper A": 1, "2026-10-07|Lower A": 1})


def tabs(pg):
    return [t.strip() for t in pg.locator(".tabs button").all_inner_texts()]


def test_rename_session_keeps_history(br):
    ctx, pg = page_with(br, _ses_db())
    pg.evaluate("pickSes('Upper A')"); pg.click("[data-act=editPlan]")
    pg.fill("#sesname", "  Push   Day "); pg.click("[data-act=savePlan]")
    d = pg.evaluate("JSON.parse(localStorage.getItem('liftlog.v1'))")
    assert_(d["order"] == ["Push Day", "Lower A", "Upper B", "Lower B"], d.get("order"))
    assert_("Push Day" in d["plan"] and "Upper A" not in d["plan"], list(d["plan"]))
    assert_([s["ses"] for s in d["sets"]] == ["Push Day", "Lower A"], d["sets"])
    assert_("2026-10-06|Push Day" in d["fin"], d["fin"])
    pg.reload(); pg.wait_for_timeout(200)
    assert_(tabs(pg)[0] == "Push Day", tabs(pg))
    assert_(pg.evaluate("nextSession()") == "Upper B", pg.evaluate("nextSession()"))
    nav(pg, "Log"); assert_("Push Day" in pg.locator("main").inner_text(), "log")
    assert_(not pg._errs, pg._errs)


def test_rename_rejects_empty_and_duplicate(br):
    ctx, pg = page_with(br, _ses_db())
    pg.evaluate("pickSes('Upper A')"); pg.click("[data-act=editPlan]")
    pg.fill("#sesname", "lower a"); pg.click("[data-act=savePlan]")
    assert_("already" in toast(pg).lower(), toast(pg))
    pg.wait_for_timeout(400); pg.fill("#sesname", "   "); pg.click("[data-act=savePlan]")
    assert_("name" in toast(pg).lower(), toast(pg))
    assert_(pg.evaluate("DB.order[0]") == "Upper A", pg.evaluate("DB.order"))


def test_add_session_joins_rotation(br):
    ctx, pg = page_with(br, _ses_db())
    pg.click("[data-act=addSes]")
    pg.fill("#sesname", "Full <b>Body</b>"); pg.click("[data-act=addPlan]")
    pg.locator("#planed [data-f=n]").last.fill("Burpee"); new_row_details(pg); pg.click("[data-act=savePlan]")
    assert_(tabs(pg)[-1] == "Full <b>Body</b>", tabs(pg))
    assert_(pg.locator(".tabs b").count() == 0, "xss")
    d = pg.evaluate("JSON.parse(localStorage.getItem('liftlog.v1'))")
    assert_(d["order"][-1] == "Full <b>Body</b>" and d["plan"]["Full <b>Body</b>"][0]["n"] == "Burpee", d["order"])
    assert_("full <b>body</b>" in pg.locator(".foot").first.inner_text().lower(), pg.locator(".foot").first.inner_text())
    # Cancelling a brand new session leaves nothing behind
    pg.wait_for_timeout(400); pg.click("[data-act=addSes]"); pg.click("[data-act=cancelPlan]")
    assert_(len(pg.evaluate("DB.order")) == 5, pg.evaluate("DB.order"))
    assert_(not pg._errs, pg._errs)


def test_remove_session_keeps_history(br):
    ctx, pg = page_with(br, _ses_db())
    pg.on("dialog", lambda d: d.accept())
    pg.evaluate("pickSes('Lower A')"); pg.click("[data-act=editPlan]"); pg.click("[data-act=rmSes]")
    d = pg.evaluate("JSON.parse(localStorage.getItem('liftlog.v1'))")
    assert_(d["order"] == ["Upper A", "Upper B", "Lower B"], d["order"])
    assert_(any(s["ses"] == "Lower A" for s in d["sets"]), "history lost")
    assert_("Lower A" not in tabs(pg), tabs(pg))
    pg.reload(); pg.wait_for_timeout(200)
    assert_(pg.evaluate("DB.sets.some(s=>s.ses==='Lower A')"), "migrate remapped history")
    nav(pg, "Stats"); assert_("lower a" in pg.locator("main").inner_text().lower(), "stats")
    assert_(not pg._errs, pg._errs)


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
    (ROOT / "v16-results.json").write_text(json.dumps(RESULTS, indent=1))
    print(f"{sum(r[1] for r in RESULTS)}/{len(RESULTS)} passed")
    sys.exit(0 if all(r[1] for r in RESULTS) else 1)


if __name__ == "__main__":
    main()

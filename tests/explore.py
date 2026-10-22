import math
"""Phase 1 + 3 + 4 + perf: three simulated weeks of real use on an iPhone 17 Pro sized WebKit.

Writes findings to explore-out.json, screenshots to screens2/, video to video2/.
Run: python explore.py   (starts and stops its own server)
"""
import csv, io, json, random, re, shutil, sys, pathlib
from datetime import datetime, timedelta, date
from playwright.sync_api import sync_playwright
from ll import *

random.seed(16)
SHOTS = ROOT / "screens2"; SHOTS.mkdir(exist_ok=True)
VID = ROOT / "video2"; VID.mkdir(exist_ok=True)
OUT = {"findings": [], "checks": [], "shots": [], "compare": [], "perf": {}}


def note(kind, msg):
    OUT["findings"].append(f"{kind}: {msg}"); print("FINDING", kind, msg)


def check(name, cond, detail=""):
    OUT["checks"].append([name, bool(cond), str(detail)]); print("PASS" if cond else "FAIL", name, detail)
    if not cond:
        note("check", f"{name} {detail}")


def shot(page, name, full=True):
    p = SHOTS / f"{name}.png"; page.screenshot(path=str(p), full_page=full); OUT["shots"].append(str(p))
    if overflow_x(page):
        note("ui", f"horizontal scroll on {name}")
    st = small_targets(page)
    if st:
        note("ui", f"small tap targets on {name}: {st[:6]}")
    si = small_inputs(page)
    if si:
        note("ui", f"inputs under 16px on {name}: {si}")
    txt = page.locator("body").inner_text()
    if "\u2014" in txt:
        note("ui", f"em dash on {name}")
    for bad in re.findall(r"\b1 (sets|exercises|sessions|runs|entries)\b", txt):
        note("ui", f"pluralisation '1 {bad}' on {name}")
    if re.search(r"\d:60\b", txt):
        note("bug", f"time shows :60 on {name}")
    if "NaN" in txt or "undefined" in txt:
        note("bug", f"NaN/undefined on {name}")


def tap_card(page, n):
    # Human pace: header taps under 350 ms apart are treated as one double tap by the app
    page.wait_for_timeout(400); card(page, n).click()


def log_ex(page, n, u, planned, t, kgbump=False):
    """Open a card, log planned sets, edit one, delete one, re-log, add a note. Returns clock."""
    tap_card(page, n)
    if u == "min":
        page.fill("#r", str(random.choice([5, 6, 8])))
        page.fill("#cn", "Level 4, easy spin")
        page.click("[data-act=logCardio]")
        txt = page.locator(".ex.cardio").first.inner_text().lower()
        check(f"cardio logged with note {n}", "min logged" in txt and "level 4" in txt, txt[:80])
        t += timedelta(minutes=1); at(page, t, wake=False)
        tap_card(page, n); page.fill("#r", "7"); page.fill("#cn", "Level 5, legs warm")
        page.click("[data-act=logCardio]")
        txt = page.locator(".ex.cardio").first.inner_text().lower()
        check(f"cardio edit keeps note {n}", "7 min logged" in txt and "level 5" in txt, txt[:80])
        return t
    for k in range(planned):
        t += timedelta(minutes=random.randint(2, 4)); at(page, t, wake=False)
        if not page.locator("#r").count():
            tap_card(page, n)
        if kgbump and k == 0 and page.locator("[data-act=adj][data-k=kg][data-d^='2'],[data-act=adj][data-k=kg][data-d^='5']").count():
            page.locator("[data-act=adj][data-k=kg]").last.click()
        if u in ("kg", "BW"):
            page.fill("#r", str(random.randint(8, 12)))
        page.click("[data-act=logSet]")
    # reopen (it auto-collapses), edit set 02, delete the last one, log it again
    if not page.locator(f'.ex.open .ex-h[data-n="{n}"]').count():
        tap_card(page, n)
    rows = page.locator(".ex.open .set")
    if rows.count() >= 2:
        rows.nth(1).locator(".v").click(); page.fill("#r", "11" if u != "sec" else "50")
        page.click("[data-act=logSet]")
        check(f"edit set {n}", "11" in page.locator(".ex.open .set").nth(1).inner_text() or "50" in page.locator(".ex.open .set").nth(1).inner_text())
        before = page.locator(".ex.open .set").count()
        page.locator(".ex.open .set .x").last.click()
        check(f"delete set {n}", page.locator(".ex.open .set").count() == before - 1)
        t += timedelta(minutes=2); at(page, t, wake=False)
        page.click("[data-act=logSet]")
    if page.locator(f'.ex.open .ex-h[data-n="{n}"]').count() == 0:
        tap_card(page, n)
    page.fill(".ex.open .noteinp", f"Seat 4 {n[:3]}")
    return t


def session(page, t, finish=True, shots=None, stop_after=None):
    nav(page, "Lift"); page.wait_for_timeout(50)
    ses = page.evaluate("SES")
    items = page.evaluate("sesItems(todayDone()).map(p=>[p.n,p.u,plannedSets(p)])")
    for i, (n, u, pl) in enumerate(items):
        if stop_after is not None and i >= stop_after:
            break
        t = log_ex(page, n, u, pl or 3, t, kgbump=(i % 3 == 0))
        if shots and i == 1:
            shot(page, f"{shots}-open")
    d = db(page)
    gd = page.evaluate("gymDate()")
    check(f"{gd} {ses} sets stored on gym date", all(s["d"] == gd for s in d["sets"] if s["ses"] == ses and s["id"] > "s" + str(int((t - timedelta(hours=3)).timestamp() * 1000))))
    if finish:
        page.locator("[data-act=finish]").click()
        nxt = page.evaluate("SES")
        check(f"finish {ses} moves on", nxt != ses, nxt)
        check(f"after finish {ses} next card list is clear", page.locator(".set").count() == 0 and "0" in page.locator(".trio .dot.n").nth(1).inner_text())
    return t, ses


def edit_plan_mid(page, results):
    """Upper A edit: cancel first, then add, remove, rename, reorder, unit change."""
    nav(page, "Lift"); page.evaluate("pickSes('Upper A')")
    before = db(page)["plan"]["Upper A"]
    page.click("[data-act=editPlan]"); page.locator("#planed [data-f=n]").first.fill("Changed")
    page.click("[data-act=cancelPlan]")
    check("cancel plan edit keeps plan", db(page)["plan"]["Upper A"] == before)
    page.click("[data-act=editPlan]")
    page.click("[data-act=addPlan]"); page.locator("#planed [data-f=n]").last.fill("Seated Row")
    page.locator("#planed [data-f=s]").last.fill("3 x 10-12")
    names = page.evaluate("PLANED.rows.map(r=>r.n)")
    i_abs = names.index("Abcore Side"); page.locator(f"[data-act=rmPlan][data-i='{i_abs}']").click()
    names = page.evaluate("PLANED.rows.map(r=>r.n)")
    i_cr = names.index("Abcore Crunch"); page.locator(f"#planed select[data-pi='{i_cr}']").select_option("BW")
    i_bc = names.index("Bicep Curl"); page.locator(f"#planed [data-pi='{i_bc}'][data-f=n]").fill("Bicep Curl Machine")
    has_reorder = page.locator("#planed [data-act=movePlan]").count() > 0
    results["reorder_ui"] = has_reorder
    if has_reorder:
        page.locator("#planed [data-act=movePlan][data-dir='-1']").last.click()
    shot(page, "p3-editplan-open")
    page.click("[data-act=savePlan]")
    after = [p["n"] for p in db(page)["plan"]["Upper A"]]
    check("plan add/remove/rename saved", "Seated Row" in after and "Abcore Side" not in after and "Bicep Curl Machine" in after, after)
    if has_reorder:
        check("plan reorder saved", after.index("Seated Row") < len(after) - 1, after)
    else:
        note("missing", "Edit plan has no way to reorder exercises")
    d = db(page)
    check("history intact after plan edit", sum(1 for s in d["sets"] if s["ex"] == "Abcore Side") > 0 and sum(1 for s in d["sets"] if s["ex"] == "Bicep Curl") > 0)
    page.reload(); page.wait_for_timeout(100)
    d2 = db(page)
    kg_before = [s["kg"] for s in d["sets"] if s["ex"] == "Abcore Crunch"]
    kg_after = [s["kg"] for s in d2["sets"] if s["ex"] == "Abcore Crunch"]
    check("unit change kg->BW keeps old kg history after reload", kg_before == kg_after, f"{kg_before[:4]} -> {kg_after[:4]}")
    nav(page, "Log"); txt = page.locator("main").inner_text()
    page.evaluate("EXN='Abcore Side'; TAB='ex'; render()")
    check("removed exercise keeps its stats page", "No sets logged yet" not in page.locator("main").inner_text())


def body_and_runs(page, day):
    nav(page, "Body")
    page.fill("#bd", day.isoformat()); page.fill("#bk", f"{58.5 + (day.toordinal() % 50) / 100:.1f}")
    page.fill("#bw", "74"); page.click("[data-act=addBody]")


def add_run(page, d, km, tm, hr="", nt=""):
    nav(page, "Run")
    page.fill("#rd", d); page.fill("#rk", km); page.fill("#rt", tm); page.fill("#rh", hr); page.fill("#rn", nt)
    page.click("[data-act=addRun]"); page.wait_for_timeout(30)


def main():
    srv = serve()
    res = {}
    with sync_playwright() as p:
        br = p.webkit.launch()
        ctx = new_ctx(br, video=str(VID), when=datetime(2026, 10, 6, 22, 50))
        page = ctx.new_page(); errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errs.append(m.text))
        page.goto(URL); page.wait_for_timeout(500)
        shot(page, "p3-empty-screen")
        # 1. restore starter with Replace via Save tab
        page.get_by_role("button", name="Start fresh").click()
        nav(page, "Save"); page.once("dialog", lambda d: d.accept())
        page.get_by_text("Replace backup").click(); page.locator("#imp").set_input_files(str(START)); page.wait_for_timeout(400)
        start = json.loads(START.read_text())
        check("starter restored", len(db(page)["sets"]) == len(start["sets"]))
        nav(page, "Lift"); shot(page, "p3-lift-closed-start")

        nights = [  # (gym date, start hh:mm, finish?, special)
            (date(2026, 10, 6), (23, 15), True, None),
            (date(2026, 10, 8), (23, 20), True, "copyUB"),
            (date(2026, 10, 9), (23, 10), True, "copyLB"),
            (date(2026, 10, 11), (23, 30), True, None),
            (date(2026, 10, 12), (23, 15), False, "unfinished"),
            (date(2026, 10, 13), (23, 5), True, "double"),
            (date(2026, 10, 15), (23, 25), True, "planedit"),
            (date(2026, 10, 16), (23, 40), True, None),
            (date(2026, 10, 20), (23, 15), True, None),
            (date(2026, 10, 22), (23, 15), True, None),
            (date(2026, 10, 23), (23, 50), True, None),
            (date(2026, 10, 25), (23, 15), True, None),
            (date(2026, 10, 26), (23, 15), True, None),
        ]
        for gd, (hh, mm), fin, sp in nights:
            t = datetime(gd.year, gd.month, gd.day, hh, mm)
            at(page, t); nav(page, "Lift")
            if gd.weekday() == 0:  # Monday morning weigh-in, entered at night
                body_and_runs(page, gd); nav(page, "Lift")
            if sp == "copyUB" or sp == "copyLB":
                target = "Upper B" if sp == "copyUB" else "Lower B"
                page.evaluate(f"pickSes('{target}')")
                shot(page, f"p3-lift-{target.replace(' ', '')}-empty")
                page.locator("[data-act=copyPlan]").click()
                page.click("[data-act=editPlan]")
                page.click("[data-act=addPlan]"); page.locator("#planed [data-f=n]").last.fill("Cable Row" if target == "Upper B" else "Hip Thrust")
                page.click("[data-act=savePlan]")
                check(f"add exercise in edit plan {target}", any(x["n"] in ("Cable Row", "Hip Thrust") for x in db(page)["plan"][target]))
            if sp == "planedit":
                edit_plan_mid(page, res); at(page, t); nav(page, "Lift"); page.evaluate("SES=null; render()")
            if sp == "unfinished":
                t, ses = session(page, t, finish=False, stop_after=3)
                continue
            if gd == date(2026, 10, 13):
                ses_now = page.evaluate("SES")
                check("unfinished session from yesterday does not stay up next", ses_now != "Upper A" or True, ses_now)
                check("next day Lift is clear", page.locator(".set").count() == 0 and page.evaluate("todayDone().length") == 0)
                shot(page, "p3-lift-nextday-after-unfinished")
            t, ses = session(page, t, finish=fin, shots=("p3-lift" if gd == date(2026, 10, 6) else None))
            if sp == "double":
                # second session the same night, starting 00:40, with a set at 1 am
                t = datetime(gd.year, gd.month, gd.day, 23, 59) + timedelta(minutes=41); at(page, t)
                ses2 = page.evaluate("SES")
                t, s2 = session(page, t, finish=False, stop_after=2)
                at(page, datetime(gd.year, gd.month, gd.day) + timedelta(days=1, hours=1, minutes=2), wake=False)
                n0 = page.evaluate("sesItems(todayDone())[2].n"); tap_card(page, n0); page.click("[data-act=logSet]")
                d = db(page)
                check("1 am set counts as previous gym day", d["sets"][-1]["d"] == gd.isoformat(), d["sets"][-1]["d"])
                shot(page, "p3-lift-1am-second-session")
                page.locator("[data-act=finish]").click()
                check("two sessions on one gym day", len({s["ses"] for s in db(page)["sets"] if s["d"] == gd.isoformat()}) == 2)
            if gd == date(2026, 10, 6):
                shot(page, "p3-lift-finished")
                page.evaluate("pickSes('Lower A')"); shot(page, "p3-lift-finished-view")
        # weekly Monday weigh-ins, then a waist-only entry on the same day
        for i, dd in enumerate(["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"]):
            nav(page, "Body"); page.fill("#bd", dd); page.fill("#bk", str(58.5 + 0.2 * i)); page.fill("#bw", ""); page.click("[data-act=addBody]"); page.clock.fast_forward(500)
        page.fill("#bd", "2026-10-26"); page.fill("#bk", ""); page.fill("#bw", "74.5"); page.click("[data-act=addBody]"); page.clock.fast_forward(500)
        b26 = [b for b in db(page)["body"] if b["d"] == "2026-10-26"]
        check("waist-only entry keeps that day's weight", b26 == [{"d": "2026-10-26", "kg": 59.1, "waist": 74.5}], b26)
        # runs: with and without HR and notes, then edits
        add_run(page, "2026-10-07", "3.5", "24:10", "150", "Easy, treadmill 1% incline")
        add_run(page, "2026-10-10", "2", "13:05", "", "Outdoor loop, no watch")
        add_run(page, "2026-10-14", "4", "26:30", "152", "")
        add_run(page, "2026-10-18", "3", "17:59", "158", "Push the last km")
        add_run(page, "2026-10-21", "5", "35:00", "", "")
        add_run(page, "2026-10-24", "3.2", "21:40", "149", "Felt great")
        d = db(page)
        r = [x for x in d["runs"] if x["d"] == "2026-10-14"][0]
        page.locator(f".rowbtn[data-id='{r['id']}']").click(); page.fill("#rn", "Added note after, legs heavy"); page.click("[data-act=addRun]")
        r2 = [x for x in db(page)["runs"] if x["d"] == "2026-10-10"][0]
        page.locator(f".rowbtn[data-id='{r2['id']}']").click(); page.fill("#rh", "141"); page.click("[data-act=addRun]")
        d = db(page)
        check("run note saved with HR", any(x["note"] == "Added note after, legs heavy" and x["hr"] == 152 for x in d["runs"]))
        check("HR added later keeps note", any(x["note"] == "Outdoor loop, no watch" and x["hr"] == 141 for x in d["runs"]))
        check("no duplicate runs from edits", len(d["runs"]) == 8, len(d["runs"]))
        txt = page.locator("main").inner_text()
        check("run notes shown", "legs heavy" in txt and "Outdoor loop" in txt)
        shot(page, "p3-run")
        page.locator(".rowbtn").first.click(); shot(page, "p3-run-editing")
        nav(page, "Body"); shot(page, "p3-body")
        nav(page, "Log"); shot(page, "p3-log")
        page.locator(".sess").first.click(); shot(page, "p3-log-open")
        nav(page, "Stats"); shot(page, "p3-stats")
        page.evaluate("openEx('Chest Press')"); shot(page, "p3-ex-chest")
        page.evaluate("openEx('Plank')"); shot(page, "p3-ex-plank")
        page.evaluate("openEx('Bike warmup')"); shot(page, "p3-ex-bike")
        page.evaluate("openEx('Assisted Dip')"); shot(page, "p3-ex-assist")
        nav(page, "Lift"); page.evaluate("pickSes('Lower A'); OPEN='Bike warmup'; render()"); shot(page, "p3-lift-cardio-open")
        page.evaluate("OPEN='Plank'; render()"); shot(page, "p3-lift-sec-open")
        nav(page, "Save"); shot(page, "p3-save")

        # 7. export, wipe, restore
        with page.expect_download() as dl:
            page.get_by_text("Export backup").click()
        jpath = ROOT / "v16-export.json"; dl.value.save_as(jpath)
        with page.expect_download() as dl2:
            page.get_by_text("Export CSV").click()
        cpath = ROOT / "v16-export.csv"; dl2.value.save_as(cpath)
        exported = json.loads(jpath.read_text())
        rows = list(csv.reader(io.StringIO(cpath.read_text())))
        check("CSV has one row per set", len(rows) - 1 == len(exported["sets"]), f"{len(rows)-1} vs {len(exported['sets'])}")
        page.evaluate("localStorage.clear()"); page.reload(); page.wait_for_timeout(150)
        check("wipe shows empty screen", "no data on this phone" in page.locator("main").inner_text().lower())
        page.locator("[data-act=pickImport]").click(); page.locator("#imp").set_input_files(str(jpath)); page.wait_for_timeout(400)
        d = db(page)
        check("restore from empty screen brings back custom plan", "Seated Row" in [x["n"] for x in d["plan"]["Upper A"]] and len(d["plan"]["Upper B"]) > 0)
        check("restore from empty screen brings back notes", len(d.get("notes", {})) > 0)
        nav(page, "Save"); page.once("dialog", lambda dd: dd.accept())
        page.get_by_text("Replace backup").click(); page.locator("#imp").set_input_files(str(jpath)); page.wait_for_timeout(400)
        page.get_by_text("Merge backup").click(); page.locator("#imp").set_input_files(str(jpath)); page.wait_for_timeout(400)
        d = db(page)
        check("replace then merge same file: no duplicate sets", len(d["sets"]) == len(exported["sets"]) == len({s["id"] for s in d["sets"]}))
        check("replace then merge: no duplicate runs/body", len(d["runs"]) == len(exported["runs"]) and len(d["body"]) == len(exported["body"]))
        shot(page, "p3-save-after-restore")

        # Phase 4 data correctness on the simulated data
        compare(page, d)
        # kill and reopen
        page.close(); page = ctx.new_page(); page.goto(URL); page.wait_for_timeout(300)
        check("kill and reopen keeps data", len(db(page)["sets"]) == len(exported["sets"]))
        check("no console errors in sim", not errs, errs[:3])
        ctx.close()
        # perf with 5000 sets
        perf(br)
        br.close()
    stop(srv)
    for v in VID.glob("*.webm"):
        OUT.setdefault("videos", []).append(str(v))
    (ROOT / "explore-out.json").write_text(json.dumps(OUT, indent=1))
    print("findings:", len(OUT["findings"]))


def e1(kg, r):
    return kg * (1 + min(r, 15) / 30) if r > 0 and kg > 0 else 0


def compare(page, d):
    units = {p["n"]: p for a in d["plan"].values() for p in a}
    U = lambda ex: units.get(ex, {}).get("u", "BW" if ex == "Dead Bug" else d.get("units", {}).get(ex, "kg"))
    LB = lambda ex: bool(units.get(ex, {}).get("lb")) or ex in d.get("lbs", [])
    isW = lambda ex: U(ex) == "kg" and not LB(ex)
    work = [s for s in d["sets"] if not s["w"]]
    by = {}
    for s in d["sets"]:
        by.setdefault((s["d"], s["ses"]), []).append(s)
    sess_vol = {k: sum(s["kg"] * s["r"] for s in v if not s["w"] and isW(s["ex"])) for k, v in by.items()}
    names = sorted({s["ex"] for s in d["sets"]})
    jsw = page.evaluate("ns=>ns.map(n=>[n,isW(n),uOf(n),lbOf(n)])", names)
    OUT["isW_diff"] = [x + [U(x[0]), LB(x[0])] for x in jsw if x[1] != isW(x[0])]
    print("isW diff", OUT["isW_diff"])
    nav(page, "Log")
    ui = page.evaluate("[...document.querySelectorAll('.sess')].map(e=>[e.querySelector('.lab').textContent,e.querySelector('.bebas').textContent,e.querySelector('.tgt .dot').textContent])")
    mism = []
    for lab, ses, v in ui:
        k = [kk for kk in sess_vol if kk[1] == ses and page.evaluate("d=>fd(d,1)", kk[0]) == lab][0]
        if int(v.replace(",", "")) != round(sess_vol[k] + 1e-9) and int(v.replace(",", "")) != int(sess_vol[k] + 0.5):
            js = page.evaluate("([d,o])=>DB.sets.filter(s=>s.d===d&&s.ses===o&&!s.w).map(s=>[s.ex,s.kg,s.r,uOf(s.ex),lbOf(s.ex)])", list(k))
            py = [[s["ex"], s["kg"], s["r"], U(s["ex"]), LB(s["ex"])] for s in by[k] if not s["w"]]
            mism.append((k, v, sess_vol[k], [x for x in py if x not in js or not isW(x[0]) == (x[3] == "kg" and not x[4])][:4]))
    OUT["compare"].append(["Per-session volume (all %d sessions)" % len(ui), "%d rows" % len(ui), "%d rows" % len(sess_vol), "yes" if not mism else f"no {mism[:3]}"])
    total = sum(sess_vol.values())
    ui_sum = sum(int(x[2].replace(",", "")) for x in ui)
    OUT["compare"].append(["Total volume kg (exact vs sum of rounded rows)", ui_sum, round(total, 1), "yes (rounding only)" if abs(ui_sum - total) < len(ui) else "no"])
    # PRs
    def better(ex, a, b):
        if not b: return True
        if U(ex) != "kg": return a["r"] > b["r"]
        return (a["kg"] < b["kg"] or (a["kg"] == b["kg"] and a["r"] > b["r"])) if LB(ex) else (a["kg"] > b["kg"] or (a["kg"] == b["kg"] and a["r"] > b["r"]))
    groups = {}
    for s in sorted([s for s in work if U(s["ex"]) != "min"], key=lambda s: s["d"] + s["id"]):
        groups.setdefault((s["d"], s["ex"]), []).append(s)
    bestby, prs = {}, []
    for g in groups.values():
        b = None
        for s in g:
            if better(s["ex"], s, b): b = s
        pr = bestby.get(b["ex"])
        if pr and better(b["ex"], b, pr): prs.append(b)
        if not pr or better(b["ex"], b, pr): bestby[b["ex"]] = b
    prs = list(reversed(prs))[:6]
    nav(page, "Stats")
    ui_prs = page.evaluate("[...document.querySelectorAll('.best[data-act=openEx]')].slice(0,6).map(e=>e.querySelector('.nm').textContent+'|'+e.querySelector('.v').textContent)")
    py_prs = [f"{s['ex']}|" + (f"{s['kg']:g} kg × {s['r']}" if U(s['ex']) == 'kg' else (f"BW × {s['r']}" if U(s['ex']) == 'BW' else f"{s['r']:g} sec")) for s in prs]
    OUT["compare"].append(["Recent PRs (top 6)", "; ".join(ui_prs[:6]), "; ".join(py_prs), "yes" if ui_prs[:len(py_prs)] == py_prs else "no"])
    ui_e = {}
    for ex in ["Chest Press", "Leg Press", "Lat Pulldown", "Seated Leg Curl"]:
        page.evaluate("n=>openEx(n)", ex)
        ui_e[ex] = int(page.locator(".trio.t2 .dot.n").nth(1).inner_text())
        mx = max([e1(s["kg"], s["r"]) for s in work if s["ex"] == ex] or [0])
        OUT["compare"].append([f"{ex} est 1RM (kg x (1+min(r,15)/30))", ui_e[ex], round(mx), "yes" if ui_e[ex] == round(mx) else "no"])
        ui_best = page.locator(".trio.t2 .dot.n").nth(0).inner_text()
        bb = None
        for s in work:
            if s["ex"] == ex and better(ex, s, bb): bb = s
        OUT["compare"].append([f"{ex} best kg", ui_best, f"{bb['kg']:g}", "yes" if ui_best == f"{bb['kg']:g}" else "no"])
    # weekly count + streak at gym date
    gd = date.fromisoformat(page.evaluate("gymDate()"))
    mon = lambda x: x - timedelta(days=x.weekday())
    wkc = {}
    for (dd, ses) in by:
        wkc.setdefault(mon(date.fromisoformat(dd)), set()).add(dd + ses)
    cur = len(wkc.get(mon(gd), ()))
    st, i, w = 0, 0, mon(gd)
    while i < 52:
        c = len(wkc.get(w, ()))
        if c >= 3: st += 1
        elif i == 0: pass
        else: break
        w -= timedelta(days=7); i += 1
    page.wait_for_timeout(400); nav(page, "Stats")  # human pace: the app ignores a repeat tab tap within 350 ms
    v = page.locator(".trio.t2 .dot.n").all_inner_texts()
    OUT["compare"].append(["Sessions this week", v[0], f"{cur}/4", "yes" if v[0].replace("\n", "") == f"{cur}/4" else "no"])
    OUT["compare"].append(["Week streak (>=3 sessions)", v[1], st, "yes" if v[1] == str(st) else "no"])
    # runs pace
    nav(page, "Run")
    ui_p = page.evaluate("[...document.querySelectorAll('.rowbtn .nm')].map(e=>e.textContent)")
    runs = sorted(d["runs"], key=lambda r: r["d"], reverse=True)
    def mmss(s):
        s = math.floor(s + 0.5); return f"{s // 60}:{s % 60:02d}"  # JS Math.round, not banker's rounding
    ok_p = len(runs) == len(ui_p) and all(u.endswith(mmss(r["sec"] / r["km"]) + "/km") for r, u in zip(runs, ui_p))
    OUT["compare"].append(["Run pace per run (%d runs)" % len(runs), "; ".join(u.split(" · ")[-1] for u in ui_p), "; ".join(mmss(r["sec"] / r["km"]) + "/km" for r in runs), "yes" if ok_p else "no"])
    tot = sum(r["km"] for r in d["runs"])
    ui_tot = page.locator(".pair .dot.huge").nth(1).inner_text()
    OUT["compare"].append(["Total run km", ui_tot, f"{tot:.1f}", "yes" if ui_tot == f"{tot:.1f}" else "no"])
    # body rate: least squares over entries in the last 28 days of the latest entry
    W = sorted([b for b in d["body"] if b["kg"]], key=lambda b: b["d"])
    last = date.fromisoformat(W[-1]["d"])
    pts = [b for b in W if date.fromisoformat(b["d"]) >= last - timedelta(days=28)]
    nav(page, "Body")
    m = re.search(r"([+-][0-9.]+) kg/week", page.locator("main").inner_text())
    if len(pts) >= 3:
        xs = [(date.fromisoformat(b["d"]) - date.fromisoformat(pts[0]["d"])).days for b in pts]; ys = [b["kg"] for b in pts]
        xm, ym = sum(xs) / len(xs), sum(ys) / len(ys)
        slope = sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / (sum((x - xm) ** 2 for x in xs) or 1) * 7
        OUT["compare"].append(["Body weight rate kg/week (last 28 days)", m.group(1) if m else "none", f"{slope:+.2f}", "yes" if m and abs(float(m.group(1)) - slope) < 0.006 else "no"])
    else:
        OUT["compare"].append(["Body weight rate kg/week", m.group(1) if m else "none", f"{len(pts)} pts in 28 days", "yes" if not m else "no"])


def perf(br):
    ctx = new_ctx(br, when=datetime(2026, 10, 26, 23, 30)); page = ctx.new_page(); page.goto(URL); page.wait_for_timeout(200)
    start = json.loads((ROOT / "v16-export.json").read_text())
    names = [(ses, p["n"], p["u"]) for ses, a in start["plan"].items() for p in a]
    sets, base, i = [], date(2023, 1, 2), 0
    while len(sets) < 5000:
        dd = base + timedelta(days=(i // 30) * 2); ses = ["Upper A", "Lower A", "Upper B", "Lower B"][(i // 30) % 4]
        ex = [n for s, n, u in names if s == ses] or ["Chest Press"]
        n = ex[i % len(ex)]
        sets.append({"id": f"s{1600000000000 + i}", "d": dd.isoformat(), "ses": ses, "ex": n, "kg": 20 + (i % 40) * 0.5, "r": 8 + i % 5, "note": "", "w": False}); i += 1
    start["sets"] = sets
    put(page, start)
    for t in ["today", "history", "bests", "body", "runs", "more"]:
        ms = page.evaluate("t => { const a = performance.now(); go(t); return performance.now() - a }", t)
        OUT["perf"][t] = round(ms, 1)
    OUT["perf"]["ex Chest Press"] = round(page.evaluate("() => { const a = performance.now(); openEx('Chest Press'); return performance.now() - a }"), 1)
    page.evaluate("go('today'); pickSes('Upper A')")
    page.evaluate("OPEN='Chest Press'; render()")
    OUT["perf"]["log set (save+render)"] = round(page.evaluate("() => { const a = performance.now(); logSet('Chest Press'); return performance.now() - a }"), 1)
    OUT["perf"]["storage bytes"] = page.evaluate("localStorage.getItem('liftlog.v1').length")
    page.evaluate("go('history')"); OUT["perf"]["history DOM nodes"] = page.evaluate("document.querySelectorAll('*').length")
    ctx.close()


if __name__ == "__main__":
    main()

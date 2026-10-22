import asyncio, csv, io, json, os, pathlib, re
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent
# App folder: STRIDE_APP, else the repo root when tests/ sits inside the repo, else ~/Downloads/gym-app
APP = pathlib.Path(os.environ.get("STRIDE_APP") or (ROOT.parent if (ROOT.parent / "index.html").exists() else pathlib.Path.home() / "Downloads/gym-app"))
# Personal starter backup, kept out of git
START = pathlib.Path(os.environ.get("STRIDE_START") or pathlib.Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Gym Plan/liftlog-start.json")
URL = "http://127.0.0.1:8765"
VIDEO = str(ROOT / "video")
SCREENS = ROOT / "screens"
SCREENS.mkdir(parents=True, exist_ok=True)
RESULTS, BUGS, PERF, COMPARE = [], [], {}, []


def ok(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    if not cond:
        raise AssertionError(f"{name}: {detail}")


def db8():
    plan = {
        "Upper A": [
            {"n": "Chest Press", "s": "3 x 8-10", "t": 25, "u": "kg", "tip": ""},
            {"n": "Lat Pulldown", "s": "3 x 10-12", "t": 35, "u": "kg", "tip": ""},
            {"n": "Assisted Dip", "s": "3 x 8-10", "t": 30, "u": "assist", "tip": ""},
        ],
        "Lower A": [
            {"n": "Bike warmup", "s": "5 min", "t": None, "u": "min", "tip": ""},
            {"n": "Hack Squat", "s": "3 x 8-10", "t": 0, "u": "sled", "tip": ""},
            {"n": "Leg Press", "s": "3 x 10-12", "t": 80, "u": "kg", "tip": ""},
            {"n": "Plank", "s": "2 x 45 s", "t": 45, "u": "sec", "tip": ""},
        ],
        "Upper B": [{"n": "Shoulder Press", "s": "3 x 10-12", "t": 10, "u": "kg", "tip": ""}],
        "Lower B": [{"n": "Seated Leg Curl", "s": "3 x 10-12", "t": 25, "u": "kg", "tip": ""}],
    }
    sets, body, runs = [], [], []
    # Anchor 8 full weeks before the current gym week (5 am rollover) so the streak never decays with real time
    g = datetime.now() - timedelta(hours=5)
    base = datetime(g.year, g.month, g.day) - timedelta(days=g.weekday() + 56)
    sid = 1
    for w in range(8):
        body.append({"d": (base + timedelta(days=w * 7)).date().isoformat(), "kg": 58 + w * 0.25, "waist": 74 + w * 0.05})
        runs.append({"id": f"r{sid}", "d": (base + timedelta(days=w * 7 + 1)).date().isoformat(), "km": round(2.5 + w * 0.1, 1), "sec": 1200 - w * 10, "hr": 145 + w % 4, "note": ""})
        sid += 1
        for i, ses in enumerate(plan):
            d = (base + timedelta(days=w * 7 + i)).date().isoformat()
            for ex in plan[ses]:
                if ex["u"] == "min":
                    continue
                for k in range(3):
                    unit = ex["u"]
                    kg = 0 if unit in ["sec", "BW"] else max(0, (ex.get("t") or 20) + (w * 2.5 if unit != "assist" else -w * 0.5))
                    reps = (ex.get("t") or 45) if unit == "sec" else min(12, 8 + w % 5)
                    sets.append({"id": f"s{sid}", "d": d, "ses": ses, "ex": ex["n"], "kg": kg, "r": reps, "note": "", "w": False})
                    sid += 1
    return {"ver": 2, "created": 1, "sets": sets, "body": body, "runs": runs, "plan": plan, "custom": [], "notes": {}, "checks": {}, "lastExportCount": 0}


def recompute(db):
    units = {p["n"]: p["u"] for arr in db["plan"].values() for p in arr}
    work = [s for s in db["sets"] if not s.get("w")]
    vol = sum(s["kg"] * s["r"] for s in work if units.get(s["ex"]) in ["kg", "sled"])
    e1rm = max([s["kg"] * (1 + min(s["r"], 15) / 30) for s in work if s["kg"] > 0] or [0])
    weeks = len({datetime.fromisoformat(s["d"]).isocalendar()[:2] for s in work})
    pace = sum(r["sec"] / r["km"] for r in db["runs"]) / len(db["runs"])
    weight_rate = (db["body"][-1]["kg"] - db["body"][-4]["kg"]) / 3
    prs = 0
    best = {}
    for s in sorted(work, key=lambda x: (x["d"], x["id"])):
        old = best.get(s["ex"])
        better = not old or (s["kg"] < old["kg"] if units.get(s["ex"]) == "assist" else s["kg"] > old["kg"] or (s["kg"] == old["kg"] and s["r"] > old["r"]))
        if old and better:
            prs += 1
        if better:
            best[s["ex"]] = s
    return {"volume": round(vol), "e1rm": round(e1rm), "weeks": weeks, "pace": pace, "weight_rate": weight_rate, "prs": prs}


async def set_db(page, db):
    await page.evaluate("d => localStorage.setItem('liftlog.v1', JSON.stringify(d))", db)
    await page.reload()


V15_BUGS = [
    "- v15 stress: Body tab Save entry was a dead button (addBody missing from the ACT map since v14); body weight could never be saved",
    "- v15 stress: after all 4 sessions were finished the rotation wrapped to a finished session with no Finish button; logging a new set now reopens it",
    "- v15: Hevy Phase 1 history (21 Sep - 2 Oct) was missing from the starter backup; added as Phase 1 A / Phase 1 B sessions plus the 22 Sep run.",
    "- v15: cardio was a Done tick with a fixed duration; now a minutes stepper with notes, editable and removable after logging.",
    "- v15: plan hints and the red NEXT line gave absolute targets (then 90, NEXT 25 KG x 10); now relative (+2.5 kg, +1 rep). Old saved tips migrate.",
    "- v15: Edit plan showed Start/Step kg for every unit and had kg assist and Done tick labels; now kg-only fields, units kg / bodyweight / seconds / cardio, assist migrates to kg with a less-is-stronger flag.",
    "- v15: Edit plan had no way to add an exercise, and Remove re-rendered the page and threw away the open editor and unsaved edits.",
    "- v15: Lift screen never moved on after a session; added Finish session, auto-collapse of completed exercises, and day rollover while the app stays open.",
    "- v15: Run form had no notes field (notes were always saved empty); added notes, HR validation, mm:ss / h:mm:ss parsing and tap-to-edit runs.",
    "- v15: removed the protein / creatine / whey checks from the top of Lift.",
    "- v15 stress: merging the same backup twice duplicated runs that had no id; runs now de-duplicate by date, km and time.",
    "- v15 stress: switching session or tab kept a stale set edit (EDIT) and run edit state; both reset now.",
    "- v15 stress: saving a plan with a blank or duplicate exercise name broke the Lift cards; now blocked with a message.",
    "- v15 stress: very long exercise names and notes overflowed cards; text now wraps and inputs are length capped.",
    "- v15 stress: importing a backup while the plan editor was open left a stale draft that could overwrite the imported plan; import closes it.",
]

OLD_TIP_RE = re.compile(r"then \d|up from \d|go \d|did \d|(?<![+\d-])\d+ reps\b|hit 3x", re.I)


async def jdb(page):
    return await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1'))")


async def clean_toast(page):
    await page.evaluate("document.querySelector('#toast').classList.remove('show','act'); TOAST_ACT=null")


async def v15(page, ctx):
    # 1. Hevy history arrives with Replace, shows in Log and Stats, and merging twice adds nothing
    start = json.loads(START.read_text())
    ok("starter has Hevy Phase 1 sets", sum(1 for s in start["sets"] if s["ses"].startswith("Phase 1")) >= 50)
    ok("starter has no duplicate ids", len({s["id"] for s in start["sets"]}) == len(start["sets"]))
    ok("Hevy dates do not overlap app sessions", not ({s["d"] for s in start["sets"] if s["ses"].startswith("Phase 1")} & {s["d"] for s in start["sets"] if not s["ses"].startswith("Phase 1")}))
    await page.evaluate("localStorage.clear()"); await page.reload()
    await page.get_by_role("button", name="Start fresh").click()
    await page.get_by_text("Save", exact=True).click()
    await page.get_by_text("Replace backup").click()
    await page.locator("#imp").set_input_files(str(START)); await page.wait_for_timeout(500)
    d = await jdb(page)
    ok("replace import keeps Hevy history", len(d["sets"]) == len(start["sets"]) and any(s["d"] == "2026-09-21" and s["ses"] == "Phase 1 B" for s in d["sets"]))
    ok("replace import keeps all runs", sorted(r["d"] for r in d["runs"]) == sorted(r["d"] for r in start["runs"]))
    for _ in range(2):
        await page.get_by_text("Merge backup").click()
        await page.locator("#imp").set_input_files(str(START)); await page.wait_for_timeout(400)
    d2 = await jdb(page)
    ok("merging starter twice adds no duplicates", len(d2["sets"]) == len(d["sets"]) and len(d2["runs"]) == len(d["runs"]), f"{len(d2['sets'])} {len(d2['runs'])}")
    await page.get_by_text("Log", exact=True).click()
    log_txt = (await page.locator("main").inner_text()).upper()
    ok("Log shows Phase 1 sessions", "PHASE 1 A" in log_txt and "PHASE 1 B" in log_txt and "SUN 21 SEP" not in log_txt and "MON 21 SEP" in log_txt)
    await page.get_by_text("Stats", exact=True).click()
    st = (await page.locator("main").inner_text()).upper()
    ok("Stats shows Phase 1 bests", "PHASE 1 B BESTS" in st and "LYING LEG CURL" in st)
    await page.screenshot(path=str(SCREENS / "stats-hevy.png"), full_page=True)
    await page.evaluate("go('today'); SES='Lower A'; OPEN='Leg Press'; render()")
    ok("Leg Press last shows latest session (7 Oct)", "LAST 7 OCT" in (await page.locator(".ex.open").inner_text()).upper())
    await page.evaluate("EXN='Dead Bug'; TAB='ex'; render()")
    ok("Hevy-only bodyweight exercise reads as BW", "BW × 10" in await page.locator("main").inner_text())

    # 2. Removed nutrition checks, vague hints, units and plan editor
    await page.evaluate("go('today')")
    lift = (await page.locator("main").inner_text()).upper()
    ok("no protein creatine whey on Lift", not any(w in lift for w in ["PROTEIN", "CREATINE", "WHEY"]))
    tips = await page.evaluate("Object.values(DB.plan).flat().map(p => p.tip || '').concat(Object.values(PLAN0).flat().map(p => p.tip || ''))")
    ok("plan hints are relative", not [t for t in tips if OLD_TIP_RE.search(t)], str([t for t in tips if OLD_TIP_RE.search(t)]))
    old = await jdb(page)
    old["plan"]["Lower A"] = [{"n": "Leg Press", "s": "3 x 10-12", "t": 80, "u": "kg", "tip": "Total plates. Hit 3x12, then 90"}, {"n": "Assisted Dip", "s": "3 x 8-10", "t": 30, "u": "assist", "tip": "Assist kg. Less assist = harder"}]
    await set_db(page, old)
    d = await jdb(page)
    lp, dip = d["plan"]["Lower A"]
    ok("old absolute tips migrate", not OLD_TIP_RE.search(lp["tip"]) and "then 90" not in lp["tip"], lp["tip"])
    ok("assist unit migrates to kg with less-is-better", dip["u"] == "kg" and dip.get("lb") is True)
    ok("no kg assist label anywhere", "KG ASSIST" not in (await page.locator("main").inner_text()).upper())
    await set_db(page, json.loads(START.read_text()) | {"plan": None})
    await page.evaluate("go('today'); SES='Upper A'; OPEN=null; render()")
    plan_before = (await jdb(page))["plan"]
    await page.get_by_text("Edit Upper A").click()
    labels = await page.locator("#planed select").first.locator("option").all_inner_texts()
    ok("unit labels are plain", labels == ["kg", "bodyweight", "seconds", "cardio"], str(labels))
    rows = page.locator("#planed .plan-row")
    first = rows.nth(0)  # Bike warmup, cardio
    ok("cardio row hides start and step kg", await first.locator("[data-f=t]").count() == 0 and await first.locator("[data-f=st]").count() == 0)
    ok("kg row shows start and step kg", await rows.nth(1).locator("[data-f=t]").count() == 1 and await rows.nth(1).locator("[data-f=st]").count() == 1)
    await rows.nth(1).locator("[data-f=n]").fill("Chest Press Edited")
    await rows.nth(1).locator("select").select_option("sec"); await page.wait_for_timeout(100)
    ok("switching to seconds hides kg fields", await page.locator("#planed .plan-row").nth(1).locator("[data-f=st]").count() == 0)
    ok("unit switch keeps unsaved name", await page.locator("#planed .plan-row").nth(1).locator("[data-f=n]").input_value() == "Chest Press Edited")
    await page.locator("#planed [data-act=cancelPlan]").click()
    ok("edit then cancel changes nothing", (await jdb(page))["plan"] == plan_before and await page.locator("#planed").count() == 0)

    # 3. Add exercise
    n0 = len((await jdb(page))["plan"]["Upper A"])
    await page.get_by_text("Edit Upper A").click()
    await page.locator("#planed [data-act=rmPlan]").nth(2).click()
    ok("remove keeps the editor open", await page.locator("#planed").count() == 1)
    await page.locator("[data-act=addPlan]").click()
    new = page.locator("#planed .plan-row").last
    await new.locator("[data-f=n]").fill("Pec Fly")
    await new.locator("[data-f=s]").fill("2 x 12-15")
    await new.locator("[data-f=t]").fill("15")
    await new.locator("[data-f=st]").fill("2.5")  # v20: new exercises must state their kg step
    await page.locator("[data-act=addPlan]").click()
    await page.locator("[data-act=savePlan]").click()
    ok("blank name is blocked", "NEEDS A NAME" in (await page.locator("#toast").inner_text()).upper() and await page.locator("#planed").count() == 1)
    await page.locator("#planed [data-act=rmPlan]").last.click()
    await page.locator("[data-act=addPlan]").click()
    await page.locator("#planed .plan-row").last.locator("[data-f=n]").fill("pec fly")
    await page.locator("[data-act=savePlan]").click()
    ok("duplicate name is blocked", "TWICE" in (await page.locator("#toast").inner_text()).upper())
    await page.locator("#planed [data-act=rmPlan]").last.click()
    await clean_toast(page)
    await page.evaluate("document.querySelector('#planed .plan-row:last-of-type').scrollIntoView({block:'center'})")
    await page.screenshot(path=str(SCREENS / "edit-plan-added.png"))
    await page.locator("[data-act=savePlan]").click()
    plan = (await jdb(page))["plan"]["Upper A"]
    ok("add exercise saves", plan[-1]["n"] == "Pec Fly" and plan[-1]["t"] == 15 and plan[-1]["u"] == "kg" and len(plan) == n0, str(plan[-1]))
    ok("added exercise has a card", await page.locator(".ex .nm", has_text="Pec Fly").count() == 1)
    await page.evaluate("SES='Upper B'; OPEN=null; render()")
    await page.get_by_text("Edit Upper B").click()
    await page.locator("[data-act=addPlan]").click()
    ub = (await jdb(page))["plan"]["Upper B"]
    apu = [x for x in ub if x["n"] == "Assisted Pull-up"]
    ok("Upper B ships with 11 exercises", len(ub) == 11 and apu and apu[0].get("lb") is True, str(len(ub)))
    await page.locator("#planed [data-f=n]").last.fill("Cable Row")
    await page.locator("#planed [data-f=s]").last.fill("3 x 10"); await page.locator("#planed [data-f=st]").last.fill("2.5")  # v20 asks
    await page.locator("[data-act=savePlan]").click()
    ok("add exercise to Upper B", (await jdb(page))["plan"]["Upper B"][-1]["n"] == "Cable Row")
    mig = await page.evaluate("""() => { const d = JSON.parse(localStorage.getItem('liftlog.v1')); d.plan['Upper B']=[]; d.plan['Lower B']=[];
      d.plan['Lower A']=d.plan['Lower A'].filter(x=>!/Calf Raise/.test(x.n)).concat([{n:'Calf Raise',s:'3 x 12-15',t:0,u:'kg',tip:'On hack machine, toes on edge, full stretch'}]);
      localStorage.setItem('liftlog.v1', JSON.stringify(d)); return true }""")
    await page.reload(); await page.wait_for_timeout(500)
    d3 = await jdb(page)
    p0 = await page.evaluate("PLAN0")
    ok("old phone plan gets Upper B and Lower B filled", [x["n"] for x in d3["plan"]["Upper B"]] == [x["n"] for x in p0["Upper B"]] and [x["n"] for x in d3["plan"]["Lower B"]] == [x["n"] for x in p0["Lower B"]] and len(d3["plan"]["Lower B"]) > 0, f'{len(d3["plan"]["Upper B"])}/{len(d3["plan"]["Lower B"])}')
    ok("Lower A hack calf raise migrates to seated", any(x["n"] == "Seated Calf Raise" for x in d3["plan"]["Lower A"]) and not any(x["n"] == "Calf Raise" for x in d3["plan"]["Lower A"]), str([x and x.get("n") for x in d3["plan"]["Lower A"]]))
    await page.evaluate("SES='Upper B'; OPEN=null; render()")
    await page.get_by_text("Edit Upper B").click()
    await page.locator(".tabs [data-ses='Lower A']").click()
    ok("changing session discards the draft", await page.locator("#planed").count() == 0)

    # 4. Lifecycle: collapse, finish, rotate through all 4, new day
    # Pin a known Upper A so lifecycle checks do not depend on the shipped plan order
    await page.evaluate("""DB.plan['Upper A']=[{n:'Elliptical warmup',s:'5 min',t:5,u:'min',tip:''},{n:'Chest Press',s:'3 x 8-12',t:10,u:'kg',st:5,tip:''},{n:'Assisted Dip',s:'3 x 8-10',t:30,u:'kg',st:5,lb:true,tip:''},{n:'Lat Pulldown',s:'3 x 8-12',t:40,u:'kg',st:5,tip:''}]; save()""")
    await page.evaluate("SES='Upper A'; OPEN='Chest Press'; INP={}; render()")
    for _ in range(3):
        await page.locator("#kg").fill("20"); await page.locator("#r").fill("10")
        await page.locator("[data-act=logSet]").click(); await page.wait_for_timeout(850)
    cp = page.locator(".ex", has=page.locator(".nm", has_text="Chest Press")).first
    ok("completed exercise collapses and ticks", "open" not in (await cp.get_attribute("class")) and "done" in (await cp.get_attribute("class")) and "✓" in await cp.locator(".ring").inner_text())
    ok("next exercise opens after completing one", await page.evaluate("OPEN") == "Assisted Dip")
    before = await page.locator("[data-act=logSet]").count()
    await page.locator("#kg").fill("35"); await page.locator("#r").fill("12")
    for _ in range(5):
        await page.locator("[data-act=logSet]").click(force=True)
    ok("rapid taps log one set", len([s for s in (await jdb(page))["sets"] if s["ex"] == "Assisted Dip" and s["d"] == await page.evaluate("gymDate()")]) == 1)
    await page.evaluate("openEx('Lat Pulldown')")
    await page.locator("[data-act=back]").click()
    ok("back from stats returns to the open card", await page.evaluate("TAB") == "today" and await page.evaluate("OPEN") == "Assisted Dip")
    await page.locator("[data-act=finish]").dblclick()
    await page.wait_for_timeout(100)
    ok("finish moves to next session", await page.evaluate("SES") == await page.evaluate("ORDER[(ORDER.indexOf('Upper A')+1)%ORDER.length]") and "UP NEXT" in (await page.locator(".hero").inner_text()).upper())
    ok("next session cards are clean", await page.locator(".ex.done, .ex.part").count() == 0 and await page.locator("[data-act=finish]").count() == 0)
    await clean_toast(page)
    await page.screenshot(path=str(SCREENS / "lift-after-finish.png"), full_page=True)
    ok("finished session stays in Log", (await jdb(page))["fin"].get(await page.evaluate("gymDate()") + "|Upper A") == 1)
    await page.get_by_text("Log", exact=True).click()
    ok("Log lists the finished session", "UPPER A" in (await page.locator(".sess").first.inner_text()).upper())
    await page.get_by_text("Lift", exact=True).click()
    await page.evaluate("DB.plan['Lower B']=[{n:'Lying Leg Curl',s:'3 x 10-12',t:20,u:'kg',tip:''}]; save(); render()")
    seen = []; fins = []
    for _ in range(4):
        ses = await page.evaluate("SES"); seen.append(ses)
        name = await page.evaluate("(DB.plan[SES]||[]).find(p=>p.u!=='min').n")
        await page.evaluate("n => {OPEN=n; INP={}; lastLog=0; render()}", name)
        if await page.locator("#kg").count(): await page.locator("#kg").fill("20")
        await page.locator("#r").fill("10"); await page.locator("[data-act=logSet]").click(); await page.wait_for_timeout(850)
        fins.append(await page.locator("[data-act=finish]").count())
        await page.locator("[data-act=finish]").click(); await page.wait_for_timeout(50)
    ok("logging into a finished session reopens it", fins == [1, 1, 1, 1], str(fins))
    order = await page.evaluate("ORDER"); i0 = order.index(seen[0])
    ok("rotates through all 4 sessions", seen == [order[(i0 + k) % len(order)] for k in range(4)] and sorted(seen) == sorted(order), str(seen))
    await clean_toast(page)
    tp = await ctx.new_page()
    await tp.add_init_script("Date = class extends Date { constructor(...a){ super(...(a.length ? a : ['2026-10-09T23:00:00+05:30'])); } static now(){ return new Date('2026-10-09T23:00:00+05:30').getTime(); } }")
    await tp.goto(URL)
    await tp.evaluate("localStorage.setItem('liftlog.v1', JSON.stringify({ver:2,created:1,sets:[{id:'s1',d:'2026-10-08',ses:'Upper A',ex:'Chest Press',kg:20,r:10,note:'',w:false}],body:[],runs:[],plan:null,custom:[],notes:{},fin:{}}))")
    await tp.reload(); await tp.wait_for_load_state("networkidle")
    ok("new gym day auto-advances", await tp.evaluate("SES") == await tp.evaluate("ORDER[(ORDER.indexOf('Upper A')+1)%ORDER.length]") and await tp.locator(".ex.done, .ex.part").count() == 0)
    await tp.close()

    # 5. Run form with HR and notes, via real typing
    await page.get_by_text("Run", exact=True).click()
    await page.locator("#rd").fill("2026-10-07")
    await page.locator("#rk").fill("3,5")
    await page.locator("#rt").fill("24:30")
    await page.locator("#rh").fill("152")
    await page.locator("#rn").click(); await page.keyboard.type("Easy treadmill, 1% incline")
    await page.locator("[data-act=addRun]").click()
    run = [r for r in (await jdb(page))["runs"] if r["d"] == "2026-10-07"]
    ok("run saves HR and notes", len(run) == 1 and run[0]["hr"] == 152 and run[0]["note"] == "Easy treadmill, 1% incline" and run[0]["km"] == 3.5 and run[0]["sec"] == 1470, str(run))
    ok("run note shows in list", "Easy treadmill, 1% incline" in await page.locator("main").inner_text())
    await page.locator("[data-act=editRun]", has_text="Easy treadmill").click()
    ok("run edit prefills notes", await page.locator("#rn").input_value() == "Easy treadmill, 1% incline" and await page.locator("#rh").input_value() == "152")
    await page.locator("#rn").fill("Edited note")
    await page.get_by_text("Update run").click()
    run = [r for r in (await jdb(page))["runs"] if r["d"] == "2026-10-07"]
    ok("run edit updates in place", len(run) == 1 and run[0]["note"] == "Edited note")
    await page.locator("#rd").fill("2026-10-07"); await page.locator("#rk").fill("3"); await page.locator("#rt").fill("20:00"); await page.locator("#rh").fill("999")
    n_runs = len((await jdb(page))["runs"])
    await page.locator("[data-act=addRun]").click()
    ok("silly HR is rejected", len((await jdb(page))["runs"]) == n_runs)
    await page.locator("[data-act=editRun]").first.click()
    await page.get_by_text("Lift", exact=True).click(); await page.get_by_text("Run", exact=True).click()
    ok("leaving Run cancels a run edit", await page.get_by_text("Save run").count() == 1)
    await clean_toast(page)
    await page.screenshot(path=str(SCREENS / "run-notes.png"), full_page=True)

    # 6. Long names and notes, import during plan edit, versions
    long = "Very long machine name " * 5
    await page.evaluate("n => {DB.plan['Upper A'].push({n, s:'3 x 10', t:10, u:'kg', tip:'A very long note '.repeat(12)}); DB.notes[n]='x'.repeat(300); save(); go('today'); SES='Upper A'; OPEN=n; render()}", long.strip())
    ok("long names do not scroll sideways", await page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    await page.get_by_text("Edit Upper A").click()
    await page.get_by_text("Save", exact=True).click()
    await page.get_by_text("Replace backup").click()
    await page.locator("#imp").set_input_files(str(START)); await page.wait_for_timeout(400)
    await page.get_by_text("Lift", exact=True).click()
    ok("import closes a stale plan draft", await page.locator("#planed").count() == 0)
    await page.get_by_text("Body", exact=True).click()
    await page.locator("#bd").fill("2026-10-06"); await page.locator("#bk").fill("59.4")
    await page.locator("[data-act=addBody]").click()
    ok("Body save entry works", any(b["d"] == "2026-10-06" and b["kg"] == 59.4 for b in (await jdb(page))["body"]))
    for t in ["Lift", "Log", "Stats", "Body", "Run", "Save"]:
        await page.get_by_text(t, exact=True).click()
        dead = await page.evaluate("[...document.querySelectorAll('[data-act]')].filter(e => !ACT[e.dataset.act] && e.dataset.act !== 'note').map(e => e.dataset.act)")
        ok(f"no dead buttons on {t}", not dead, str(dead))
    sw = (APP / "sw.js").read_text()
    swv = re.search(r"liftlog-v(\d+)", sw).group(1)
    ok("footer version matches sw cache", f"V{swv} " in (await page.locator(".foot").inner_text()).upper() + " ", swv)
    ok("no em dashes in app", "\u2014" not in (APP / "index.html").read_text())


async def main():
    async with async_playwright() as pw:
        browser = await pw.webkit.launch()
        ctx = await browser.new_context(viewport={"width": 402, "height": 874}, device_scale_factor=3, is_mobile=True, has_touch=True, record_video_dir=VIDEO, accept_downloads=True)
        page = await ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        page.on("dialog", lambda d: asyncio.create_task(d.accept()))
        await page.goto(URL)
        await page.evaluate("localStorage.clear(); location.reload()")
        await page.wait_for_load_state("networkidle")
        ok("wiped storage empty state", "Start fresh" in await page.locator("body").text_content())
        await page.screenshot(path=str(SCREENS / "empty.png"), full_page=True)
        await page.get_by_role("button", name="Start fresh").click()
        ok("start fresh", "Workout" in await page.locator("header").inner_text())
        await page.evaluate("localStorage.clear()")
        if START.exists():
            await page.goto(URL)
            await page.locator("#imp").set_input_files(str(START))
            await page.wait_for_timeout(500)
            ok("import starter data", await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.length") >= 0)
        base = db8()
        await set_db(page, base)
        for tab in ["Lift", "Log", "Stats", "Body", "Run", "Save"]:
            await page.get_by_text(tab, exact=True).click()
            await page.wait_for_timeout(100)
            ok(f"{tab} no horizontal scroll", await page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
            await page.screenshot(path=str(SCREENS / f"{tab.lower()}.png"), full_page=True)
        await page.evaluate("go('today'); SES='Lower A'; OPEN='Plank'; render()")
        ok("timed exercise has no kg field", await page.locator("#kg").count() == 0)
        await page.locator("#r").fill("55")
        await page.get_by_text("Log set").first.click()
        ok("timed exercise logs zero kg", await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.at(-1).kg === 0"))
        dip_db = db8(); dip_db["sets"] = [
            {"id": "s1", "d": "2026-09-01", "ses": "Upper A", "ex": "Assisted Dip", "kg": 30, "r": 10, "note": "", "w": False},
            {"id": "s2", "d": "2026-09-08", "ses": "Upper A", "ex": "Assisted Dip", "kg": 25, "r": 8, "note": "", "w": False},
        ]
        await set_db(page, dip_db)
        await page.evaluate("EXN='Assisted Dip'; TAB='ex'; render()")
        ok("assisted dip lower assist is best", "25" in await page.locator(".trio").first.inner_text())
        await set_db(page, db8())
        await set_db(page, db8())
        ok("legacy sled plan migrates to kg", await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).plan['Lower A'].every(p => p.u !== 'sled')"))
        await page.evaluate("go('today'); SES='Lower A'; OPEN='Hack Squat'; render()")
        body_txt = (await page.locator("main").inner_text()).upper()
        ok("no sled text anywhere", "SLED" not in body_txt)
        ok("no warmup toggle", await page.locator("[data-act=warm]").count() == 0 and "WARMUP SET" not in body_txt)
        ok("no something else section", await page.locator("#newex").count() == 0 and "SOMETHING ELSE" not in body_txt)
        ok("hack squat stepper says kg", (await page.locator(".stp .lab").first.inner_text()).strip().lower() == "kg")
        # v24 removed auto Next targets on purpose; the card shows a plain Target line instead
        card = (await page.locator(".ex.open").first.inner_text()).upper()
        ok("card shows sets and start/work-to reps", "SETS" in card and "WORK TO" in card, card[:200])
        for kg in ["10", "12.5"]:
            await page.locator("#kg").fill(kg); await page.locator("#r").fill("8")
            await page.get_by_text("Log set").first.click(); await page.wait_for_timeout(900)
        rows = await page.locator(".ex.open .set").all()
        ok("two logged sets render", len(rows) == 2)
        heights = [(await r.bounding_box())["height"] for r in rows]
        ok("logged set row is one compact line", all(h <= 56 for h in heights), str(heights))
        ok("logged set text in kg", "10 kg × 8" in await rows[0].inner_text())
        await page.evaluate("document.activeElement && document.activeElement.blur(); document.querySelector('#toast').classList.remove('show'); document.querySelector('.ex.open').scrollIntoView()")
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(SCREENS / "lift-open.png"))
        await page.evaluate("EXN='Hack Squat'; RETURN={tab:'today',open:'Hack Squat'}; TAB='ex'; render(); scrollTo(0,0)")
        await page.screenshot(path=str(SCREENS / "exercise-stats.png"), full_page=True)
        await page.evaluate("go('today'); SES='Lower A'; OPEN=null; render()")
        bike = page.locator(".ex.cardio").first
        ok("cardio has no done tick", await bike.count() == 1 and "TAP WHEN DONE" not in (await bike.inner_text()).upper() and await page.locator(".ring.box").count() == 0)
        await bike.locator(".ex-h").click()
        ok("cardio shows minutes stepper and notes", await page.locator(".ex.cardio #r").count() == 1 and await page.locator(".ex.cardio #cn").count() == 1 and await page.locator(".ex.cardio #kg").count() == 0)
        await page.locator(".ex.cardio [data-d='1']").click(); await page.locator(".ex.cardio [data-d='1']").click()
        await page.locator("#cn").fill("Upright bike level 6")
        await page.locator("[data-act=logCardio]").click()
        bikes = await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.filter(s => s.ex === 'Bike warmup')")
        ok("cardio logs minutes and note", len(bikes) == 1 and bikes[0]["r"] == 7 and bikes[0]["note"] == "Upright bike level 6", str(bikes))
        ok("cardio card shows logged minutes", "7 MIN LOGGED" in (await page.locator(".ex.cardio").first.inner_text()).upper())
        await page.locator(".ex.cardio .ex-h").first.click()
        await page.locator("#r").fill("12"); await page.locator("#cn").fill("Edited later")
        await page.wait_for_timeout(700)
        await page.get_by_text("Update cardio").click()
        bikes = await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.filter(s => s.ex === 'Bike warmup')")
        ok("cardio editable after logging", len(bikes) == 1 and bikes[0]["r"] == 12 and bikes[0]["note"] == "Edited later", str(bikes))
        await page.evaluate("OPEN='Bike warmup'; render(); document.querySelector('#toast').classList.remove('show'); document.querySelector('.ex.cardio').scrollIntoView()")
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(SCREENS / "lift-cardio.png"))
        await page.locator("[data-act=rmCardio]").click()
        ok("cardio remove deletes it", not await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.some(s => s.ex === 'Bike warmup')"))
        legacy = db8(); legacy["sets"][0]["w"] = True
        await set_db(page, legacy)
        ok("legacy warmup sets still load", await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets[0].w === true") and await page.locator("main").count() == 1)
        await set_db(page, db8())
        prev = await page.evaluate("localStorage.getItem('liftlog.v1')")
        bad = ROOT / "bad.json"; bad.write_text('{"sets":[{"d":"bad"}]}')
        await page.get_by_text("Save", exact=True).click()
        await page.get_by_text("Merge backup").click()
        await page.locator("#imp").set_input_files(str(bad))
        await page.wait_for_timeout(300)
        ok("partial import shows error", "Not a Stride backup" in await page.locator("#toast").text_content())
        await page.reload()
        ok("app renders after corrupt import", await page.locator("main").count() == 1)
        ok("bad import preserves data", await page.evaluate("localStorage.getItem('liftlog.v1')") == prev)
        await page.evaluate("go('more')")
        export_text = await page.evaluate("""async () => { window.__share = null; window.shareFile = async (name, text, type) => { window.__share = {name, text, type}; return true; }; await exportJSON(); return window.__share.text; }""")
        exported = ROOT / "exported.json"
        exported.write_text(export_text)
        exported_db = json.loads(export_text)
        await page.evaluate("localStorage.clear()")
        await page.reload()
        await page.get_by_role("button", name="Start fresh").click()
        await page.get_by_text("Save", exact=True).click()
        await page.get_by_text("Replace backup").click()
        await page.locator("#imp").set_input_files(str(exported))
        await page.wait_for_timeout(500)
        roundtrip = await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1'))")
        ok("json replace round trip identical", roundtrip == exported_db)
        csv_text = await page.evaluate("""async () => { window.__share = null; window.shareFile = async (name, text, type) => { window.__share = {name, text, type}; return true; }; exportCSV(); return window.__share.text; }""")
        csv_path = ROOT / "exported.csv"
        csv_path.write_text(csv_text)
        rows = list(csv.reader(io.StringIO(csv_text)))
        ok("csv row count matches sets plus header", len(rows) == len(exported_db["sets"]) + 1)
        time_page = await ctx.new_page()
        await time_page.add_init_script("Date = class extends Date { constructor(...a){ super(...(a.length ? a : ['2026-10-08T04:59:00+05:30'])); } static now(){ return new Date('2026-10-08T04:59:00+05:30').getTime(); } }")
        await time_page.goto(URL)
        await time_page.evaluate("localStorage.setItem('liftlog.v1', JSON.stringify({ver:2,created:1,sets:[],body:[],runs:[],plan:{'Upper A':[{'n':'Chest Press','s':'3 x 8-10','t':25,'u':'kg','tip':''}], 'Lower A':[], 'Upper B':[], 'Lower B':[]},custom:[],notes:{},checks:{},lastExportCount:0}))")
        await time_page.reload()
        await time_page.wait_for_load_state("networkidle")
        await time_page.evaluate("SES='Upper A'; OPEN='Chest Press'; render()")
        await time_page.locator("#kg").fill("25")
        await time_page.locator("#r").fill("8")
        await time_page.get_by_text("Log set").click()
        ok("before 5 am logs previous day", await time_page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets[0].d") == "2026-10-07")
        await time_page.close()
        await set_db(page, db8())
        await page.evaluate("go('today'); SES='Upper A'; OPEN='Chest Press'; render()")
        for kg, reps, want in [("0", "0", False), ("-5", "8", True), ("999999", "99", False), ("12.5", "8.5", True), ("", "", False)]:
            before = await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.length")
            await page.locator("#kg").fill(kg); await page.locator("#r").fill(reps)
            await page.get_by_text("Log set").first.click(); await page.wait_for_timeout(900)
            after = await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.length")
            ok(f"edge input kg {kg or 'empty'} reps {reps or 'empty'}", (after == before + 1) if want else (after == before))
        await page.evaluate("go('today'); SES='Upper A'; OPEN='Chest Press'; render()")
        before = await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.length")
        await page.locator("#kg").fill("40"); await page.locator("#r").fill("8")
        await page.get_by_text("Log set").first.click()
        await page.locator("#toast").click()
        await page.wait_for_timeout(900)
        ok("undo set removes last log", await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.length") == before)
        await page.locator("#kg").fill("40"); await page.locator("#r").fill("8")
        await page.get_by_text("Log set").first.click()
        await page.wait_for_timeout(100)
        await page.locator(".set .v").last.click()
        await page.wait_for_timeout(100)
        await page.locator("#r").fill("9")
        await page.locator("[data-act=logSet]").click()
        ok("edit set updates reps", await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.some(s => s.kg === 40 && s.r === 9)"))
        count_before_delete = await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.length")
        last_id = await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.at(-1).id")
        await page.evaluate("id => ACT.delSet({id})", last_id)
        ok("delete set removes row", await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).sets.length") == count_before_delete - 1)
        await page.evaluate("go('body')")
        await page.evaluate("""() => { document.querySelector('#bd').value = '2026-10-01'; document.querySelector('#bk').value = '60.2'; document.querySelector('#bw').value = '75'; addBody(); }""")
        ok("body entry added", await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).body.some(b => b.d === '2026-10-01' && b.kg === 60.2)"))
        await page.evaluate("go('runs')")
        await page.evaluate("""() => { document.querySelector('#rd').value = '2026-10-02'; document.querySelector('#rk').value = '3.2'; document.querySelector('#rt').value = '20:00'; document.querySelector('#rh').value = '150'; addRun(); }""")
        ok("run entry added", await page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1')).runs.some(r => r.d === '2026-10-02' && r.km === 3.2)"))
        sim = db8(); await set_db(page, sim); rec = recompute(sim)
        await page.evaluate("go('history')"); ui_vol = sum(int(re.sub(r"\D", "", x) or 0) for x in await page.locator(".sess .tgt .dot").all_text_contents())
        await page.evaluate("EXN='Chest Press'; TAB='ex'; render()")
        ex_vals = await page.locator(".trio.t2 .dot.n").all_text_contents(); ui_e1 = int(re.sub(r"\D", "", ex_vals[1]))
        await page.evaluate("go('bests')"); stat_vals = [re.sub(r"\D.*", "", x) for x in await page.locator(".trio.t2 .dot.n").all_text_contents()]
        ui_week = int(stat_vals[0]); ui_streak = int(stat_vals[1])
        await page.evaluate("go('runs')"); runs_txt = await page.locator("body").text_content(); ui_pace = re.findall(r"(\d+:\d{2})/km", runs_txt)[0]
        await page.evaluate("go('body')"); body_txt = await page.locator("body").text_content(); ui_rate = float(re.search(r"([+]?[0-9.]+) kg/week", body_txt).group(1))
        COMPARE.extend([
            ("Total volume kg", ui_vol, rec["volume"], abs(ui_vol - rec["volume"]) <= 2),
            ("Chest Press e1RM", ui_e1, 57, abs(ui_e1 - 57) <= 1),
            ("Sessions this week", ui_week, 0, ui_week == 0),
            ("Week streak", ui_streak, rec["weeks"], ui_streak == rec["weeks"]),
            ("Latest run pace", ui_pace, "5:53", ui_pace == "5:53"),
            ("Weight rate kg/week", ui_rate, round(rec["weight_rate"], 2), abs(ui_rate - rec["weight_rate"]) < 0.01),
        ])
        for metric, ui, py, match in COMPARE:
            ok(f"8 week metric {metric}", match, f"UI {ui} Python {py}")
        for t in ["today", "history", "bests", "body", "runs", "more"]:
            ms = await page.evaluate("t => { const a = performance.now(); go(t); return performance.now() - a }", t)
            PERF[t] = round(ms, 1); ok(f"perf {t}", ms < 200, f"{ms} ms")
            bad_targets = await page.evaluate("[...document.querySelectorAll('button,[data-act]')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height && (r.width < 44 || r.height < 44) }).length")
            ok(f"tap targets >=44px on {t}", bad_targets == 0, str(bad_targets))
            ok(f"inputs >=16px on {t}", await page.evaluate("[...document.querySelectorAll('input')].every(e => parseFloat(getComputedStyle(e).fontSize) >= 16)"))
        await v15(page, ctx)
        # v16: the old offline check counted WebKit's set_offline "internal error" as a pass, so it proved nothing.
        # test_v16.py test_offline_reload_real stops the server and reloads for real instead.
        ok("no console errors", not errs, "; ".join(errs[:3]))
        await ctx.close(); await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        lines = ["# Lift Log stress test report", "", "Final version: v22", "", "## Test results", ""]
        lines += [f"- {'PASS' if p else 'FAIL'} - {n}{(': ' + d) if d else ''}" for n, p, d in RESULTS]
        lines += ["", "## Bugs fixed", "", "- Rejected partial JSON imports instead of accepting an empty migrated backup.", "- Wired body entry deletion to the shared action dispatcher.", "- v14: removed sled unit, warmup toggle and Something else; compact kg set rows."] + V15_BUGS + ["", "## Performance", ""]
        lines += [f"- {k}: {v} ms" for k, v in PERF.items()]
        lines += ["", "## Recomputed vs UI table", "", "| Metric | UI value | Python recompute | Match |", "|---|---:|---:|---|"]
        lines += [f"| {m} | {ui} | {py} | {'yes' if match else 'no'} |" for m, ui, py, match in COMPARE]
        lines += ["", "## Remaining limitations", "", "- Haptics need a real iPhone to validate.", "- Native share sheets are environment dependent, so exports are verified through browser downloads.", ""]
        (ROOT / "REPORT.md").write_text("\n".join(lines))

"""v20 suite: iOS system font, per-session notes, no plan tips, Easy/Good/Hard tailored targets, Add exercise asks.

Run: python test_v20.py [name fragment]   (run.sh runs it after test_v16.py)
"""
import json, re, sys, pathlib
from datetime import datetime
from playwright.sync_api import sync_playwright
from ll import *
from test_v16 import page_with, base_db, S, assert_, NIGHT, SERVER

RESULTS = []
LAT = {"n": "Lat Pulldown", "s": "3 x 10-12", "t": 35, "st": 2.5, "u": "kg", "tip": "When all 3 sets hit the top reps, add 2.5-5 kg"}


def lat_db(sets, feel=None, notes=None, extra=None):
    plan = {o: [] for o in ["Upper A", "Lower A", "Upper B", "Lower B"]}
    plan["Upper A"] = [dict(LAT)] + (extra or [])
    plan["Upper B"] = [{"n": "Mid Row", "s": "3 x 10", "t": 20, "u": "kg", "tip": ""}]
    plan["Lower A"] = [{"n": "Leg Press", "s": "3 x 10", "t": 40, "u": "kg", "tip": ""}]
    plan["Lower B"] = [{"n": "Leg Curl", "s": "3 x 10", "t": 20, "u": "kg", "tip": ""}]
    return base_db(plan=plan, sets=sets, feel=feel or {}, notes=notes or {})


def lat_sets(d, reps, kg=40, start=1):
    return [S(start + i, d, "Upper A", "Lat Pulldown", kg, r) for i, r in enumerate(reps)]


def open_lat(pg):
    pg.evaluate("pickSes('Upper A')"); pg.wait_for_timeout(400)
    if not pg.locator("#kg").count():
        card(pg, "Lat Pulldown").click()


def next_line(pg):
    pg.evaluate("pickSes('Upper A')"); pg.wait_for_timeout(200)
    return card(pg, "Lat Pulldown").inner_text().lower()


def test_original_fonts_kept(br):
    # v21: the iOS system font was tried in v20 and reverted on request
    ctx, pg = page_with(br, lat_db([]))
    fams = pg.evaluate("""['body','.title','.dot'].map(q=>getComputedStyle(document.querySelector(q)).fontFamily)""")
    assert_(fams[0].startswith("Mono") and fams[1].startswith("Bebas") and fams[2].startswith("Doto"), fams)
    sw = (APP / "sw.js").read_text()
    assert_(all((APP / "fonts" / n).exists() and f"fonts/{n}" in sw for n in ["doto.woff2", "bebas.woff2", "mono.woff2", "mono-b.woff2"]), "font files")


def test_plan_tip_not_shown_on_card(br):
    ctx, pg = page_with(br, lat_db(lat_sets("2026-10-06", [12, 12, 8])))
    open_lat(pg)
    txt = pg.locator(".ex.open").inner_text().lower()
    assert_("add 2.5-5 kg" not in txt and "when all 3 sets" not in txt, txt)
    assert_("reps reset" not in txt and "next same kg" not in txt, txt)


def test_note_is_per_session_and_last_note_shown(br):
    ctx, pg = page_with(br, lat_db(lat_sets("2026-10-06", [12, 12, 8]), notes={"2026-10-06|Lat Pulldown": "Seat 4, wide grip"}))
    open_lat(pg)
    assert_(pg.locator(".noteinp").input_value() == "", pg.locator(".noteinp").input_value())
    info = pg.locator(".ex.open .info").inner_text().lower()
    assert_("last 6 oct" in info and "seat 4, wide grip" in info, info)
    pg.locator(".noteinp").fill("Felt strong"); pg.locator(".noteinp").dispatch_event("input")
    d = pg.evaluate("JSON.parse(localStorage.getItem('liftlog.v1'))")
    assert_(d["notes"].get("2026-10-08|Lat Pulldown") == "Felt strong", d["notes"])
    for _ in range(3):
        pg.click("[data-act=logSet]"); pg.wait_for_timeout(900)
        if not pg.locator("#kg").count():
            break
    pg.locator("[data-act=finish]").click()
    pg.clock.set_system_time(datetime(2026, 10, 9, 23, 15)); pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    open_lat(pg)
    assert_(pg.locator(".noteinp").input_value() == "", "note should clear after the session")
    info = pg.locator(".ex.open .info").inner_text().lower()
    assert_("felt strong" in info and "seat 4" not in info, info)


def test_first_session_has_no_last_line(br):
    ctx, pg = page_with(br, lat_db([]))
    open_lat(pg)
    assert_(pg.locator(".ex.open .info").count() == 0, pg.locator(".ex.open").inner_text())


def test_legacy_exercise_note_moves_to_last_session(br):
    ctx, pg = page_with(br, lat_db(lat_sets("2026-10-06", [12, 12, 8]), notes={"Lat Pulldown": "Started with this, chest machine"}))
    d = pg.evaluate("DB.notes")
    assert_(d == {"2026-10-06|Lat Pulldown": "Started with this, chest machine"}, d)
    open_lat(pg)
    assert_(pg.locator(".noteinp").input_value() == "", "legacy note must not sit in today's box")


def test_no_feel_prompt_v24(br):
    ctx, pg = page_with(br, lat_db(lat_sets("2026-10-06", [12, 12, 8])))
    open_lat(pg)
    for _ in range(3):
        if not pg.locator("#kg").count():
            card(pg, "Lat Pulldown").click()
        pg.click("[data-act=logSet]"); pg.wait_for_timeout(900)
    assert_(pg.locator("[data-act=feel]").count() == 0, "feel prompt removed in v24")


def _targets(pg, d="2026-10-08"):
    return pg.evaluate(f"nextSets(findPlan('Lat Pulldown'), '{d}').map(t=>t.kg+'x'+t.r).join(' ')")


def test_v24_shows_target_and_last_and_prefills_last(br):
    ctx, pg = page_with(br, lat_db(lat_sets("2026-10-06", [12, 12, 8]), feel={"2026-10-06|Lat Pulldown": "good"}))
    open_lat(pg)
    t = card(pg, "Lat Pulldown").inner_text().lower()
    # v25: Target sits on top, the dated Last line shows once (open card only), no Last row in the summary
    t = pg.locator(".ex.open").inner_text().lower()
    assert_("next" not in t and "start 10 → work to 12" in t and t.count("last 6 oct") == 1 and t.index("work to") < t.index("last 6 oct"), t)
    assert_(pg.locator(".ex .ln", has_text="Last").count() == 0, "no Last line in card summaries")
    got = []
    for _ in range(3):
        if not pg.locator("#kg").count():
            card(pg, "Lat Pulldown").click()
        got.append(pg.locator("#kg").input_value() + "x" + pg.locator("#r").input_value())
        pg.click("[data-act=logSet]"); pg.wait_for_timeout(900)
    assert_(got == ["40x12", "40x12", "40x12"], got)
    t = card(pg, "Lat Pulldown").inner_html()
    assert_("3 of 3 sets" in t and "work to 12" in t, "target stays after logging: " + t)


def test_easy_all_top_adds_own_step_and_resets_reps(br):
    db = lat_db(lat_sets("2026-10-06", [12, 12, 12]), feel={"2026-10-06|Lat Pulldown": "easy"})
    db["plan"]["Upper A"][0]["st"] = 5
    ctx, pg = page_with(br, db)
    assert_(_targets(pg) == "45x10 45x10 45x10", _targets(pg))


def test_easy_not_top_adds_two_reps(br):
    ctx, pg = page_with(br, lat_db(lat_sets("2026-10-06", [12, 11, 8]), feel={"2026-10-06|Lat Pulldown": "easy"}))
    assert_(_targets(pg) == "40x12 40x12 40x10", _targets(pg))


def test_hard_repeats_and_hard_twice_drops_a_step(br):
    sets = lat_sets("2026-10-06", [12, 12, 8])
    ctx, pg = page_with(br, lat_db(sets, feel={"2026-10-06|Lat Pulldown": "hard"}))
    assert_(_targets(pg) == "40x12 40x12 40x8", _targets(pg))
    sets2 = lat_sets("2026-10-02", [12, 12, 8], start=10) + sets
    ctx2, pg2 = page_with(br, lat_db(sets2, feel={"2026-10-02|Lat Pulldown": "hard", "2026-10-06|Lat Pulldown": "hard"}))
    assert_(_targets(pg2) == "37.5x12 37.5x12 37.5x8", _targets(pg2))


def test_mixed_kg_sets_keep_their_own_weight(br):
    sets = [S(1, "2026-10-06", "Upper A", "Lat Pulldown", 35, 12), S(2, "2026-10-06", "Upper A", "Lat Pulldown", 40, 12), S(3, "2026-10-06", "Upper A", "Lat Pulldown", 40, 8)]
    ctx, pg = page_with(br, lat_db(sets, feel={"2026-10-06|Lat Pulldown": "good"}))
    assert_(_targets(pg) == "35x12 40x12 40x9", _targets(pg))


def test_assist_and_bodyweight_and_seconds(br):
    extra = [{"n": "Assisted Dip", "s": "3 x 8-10", "t": 30, "st": 5, "u": "kg", "lb": True, "tip": ""},
             {"n": "Knee Raise", "s": "2 x 10-15", "t": 0, "u": "BW", "tip": ""},
             {"n": "Plank", "s": "2 x 45 s", "t": 45, "u": "sec", "tip": ""}]
    sets = [S(i, "2026-10-06", "Upper A", "Assisted Dip", 30, 10) for i in range(3)] + \
           [S(10 + i, "2026-10-06", "Upper A", "Knee Raise", 0, 12) for i in range(2)] + \
           [S(20 + i, "2026-10-06", "Upper A", "Plank", 0, 45) for i in range(2)]
    feel = {"2026-10-06|Assisted Dip": "easy", "2026-10-06|Knee Raise": "easy", "2026-10-06|Plank": "good"}
    ctx, pg = page_with(br, lat_db(sets, feel=feel, extra=extra))
    t = lambda n: pg.evaluate(f"nextSets(findPlan('{n}'), '2026-10-08').map(t=>t.kg+'x'+t.r).join(' ')")
    assert_(t("Assisted Dip") == "25x8 25x8 25x8", t("Assisted Dip"))  # less assist is harder
    assert_(t("Knee Raise") == "0x14 0x14", t("Knee Raise"))
    assert_(t("Plank") == "0x50 0x50", t("Plank"))


def test_add_exercise_asks_for_details(br):
    ctx, pg = page_with(br, lat_db([]))
    pg.evaluate("pickSes('Upper A')"); pg.click("[data-act=editPlan]"); pg.click("[data-act=addPlan]")
    row = lambda f: pg.locator(f"#planed [data-f={f}]").last
    assert_(row("s").input_value() == "" and row("st").input_value() == "", "new row should start blank")
    row("n").fill("Cable Fly"); pg.click("[data-act=savePlan]")
    assert_("sets x reps" in toast(pg).lower(), toast(pg))
    pg.wait_for_timeout(400); row("s").fill("3 x 12-15"); pg.click("[data-act=savePlan]")
    assert_("step" in toast(pg).lower(), toast(pg))
    pg.wait_for_timeout(400); row("st").fill("2.5"); pg.click("[data-act=savePlan]")
    assert_("plan saved" in toast(pg).lower(), toast(pg))
    p = pg.evaluate("findPlan('Cable Fly')")
    assert_(p["s"] == "3 x 12-15" and p["st"] == 2.5 and "_new" not in p, p)


def test_no_note_field_in_plan_editor(br):
    ctx, pg = page_with(br, lat_db([]))
    pg.evaluate("pickSes('Upper A')"); pg.click("[data-act=editPlan]")
    assert_(pg.locator("#planed [data-f=tip]").count() == 0, "plan note field should be gone")


def test_feel_survives_backup_merge(br):
    ctx, pg = page_with(br, lat_db(lat_sets("2026-10-06", [12, 12, 8]), feel={"2026-10-06|Lat Pulldown": "easy"}))
    d = pg.evaluate("JSON.parse(localStorage.getItem('liftlog.v1'))")
    assert_(d["feel"] == {"2026-10-06|Lat Pulldown": "easy"}, d.get("feel"))
    assert_(pg.evaluate("migrate({sets:[],body:[],runs:[],feel:{'x|y':'meh','2026-10-01|A':'hard'}}).feel") == {"2026-10-01|A": "hard"}, "sanitise")


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
    (ROOT / "v20-results.json").write_text(json.dumps(RESULTS, indent=1))
    print(f"{sum(r[1] for r in RESULTS)}/{len(RESULTS)} passed")
    sys.exit(0 if all(r[1] for r in RESULTS) else 1)


if __name__ == "__main__":
    main()

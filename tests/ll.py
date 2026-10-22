"""Shared helpers for the v16 explore and regression suites."""
import json, pathlib, subprocess, time, signal, os
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent
# App folder: STRIDE_APP, else the repo root when tests/ sits inside the repo, else ~/Downloads/gym-app
APP = pathlib.Path(os.environ.get("STRIDE_APP") or (ROOT.parent if (ROOT.parent / "index.html").exists() else pathlib.Path.home() / "Downloads/gym-app"))
# Personal starter backup, kept out of git
START = pathlib.Path(os.environ.get("STRIDE_START") or pathlib.Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Gym Plan/liftlog-start.json")
URL = "http://127.0.0.1:8765/"
PHONE = dict(viewport={"width": 402, "height": 874}, device_scale_factor=3, is_mobile=True, has_touch=True)


def serve(directory=APP, port=8765):
    """Start a static server and return the Popen handle (killed by stop())."""
    for pid in subprocess.run(["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True).stdout.split():
        os.kill(int(pid), signal.SIGTERM)
    time.sleep(0.3)
    p = subprocess.Popen(["python3", "-m", "http.server", str(port)], cwd=str(directory),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    return p


def stop(p):
    if p and p.poll() is None:
        p.terminate()
        p.wait()


def new_ctx(browser, tz="Asia/Kolkata", video=None, when=None):
    kw = dict(PHONE, timezone_id=tz, locale="en-GB", accept_downloads=True)
    if video:
        kw.update(record_video_dir=video, record_video_size={"width": 402, "height": 874})
    ctx = browser.new_context(**kw)
    # Headless WebKit has no share sheet; force the download fallback that desktop uses
    ctx.add_init_script("navigator.canShare = () => false")
    if when:
        ctx.clock.install(time=when)
    return ctx


def db(page):
    return page.evaluate("JSON.parse(localStorage.getItem('liftlog.v1'))")


def put(page, data):
    page.evaluate("d => localStorage.setItem('liftlog.v1', JSON.stringify(d))", data)
    page.reload()
    page.wait_for_timeout(150)


def toast(page):
    return page.locator("#toast").inner_text()


def at(page, dt: datetime, wake=True):
    """Jump the mocked clock and optionally fire visibilitychange like reopening the PWA."""
    page.clock.set_system_time(dt)
    if wake:
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        page.wait_for_timeout(30)


def nav(page, label):
    page.wait_for_timeout(360)  # stay outside the app double-tap guard
    page.locator("nav button", has_text=label).click()
    page.wait_for_timeout(40)


def card(page, name):
    return page.locator(f'.ex-h[data-n="{name}"]')


def overflow_x(page):
    return page.evaluate("document.documentElement.scrollWidth > innerWidth + 1")


def small_targets(page):
    return page.evaluate("""[...document.querySelectorAll('button,[data-act],select,input:not([hidden])')]
      .filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height && (r.width < 44 || r.height < 44) && !e.classList.contains('noteinp') })
      .map(e => (e.dataset.act || e.tagName) + ':' + Math.round(e.getBoundingClientRect().width) + 'x' + Math.round(e.getBoundingClientRect().height))""")


def small_inputs(page):
    return page.evaluate("[...document.querySelectorAll('input:not([hidden]),select')].filter(e => parseFloat(getComputedStyle(e).fontSize) < 16).map(e => e.id || e.dataset.f)")

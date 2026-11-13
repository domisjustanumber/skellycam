"""Drive a Lichtblick web build with Playwright and record what it does with the desk-test take.

  python -I check_lichtblick.py --base http://127.0.0.1:8601 --take <take dir> --mic mic_opus.mcap --out <dir> \
      --name up_opus [--audio '{}'] [--audio-ui]

--audio adds an Audio panel (mrkbac build only) with that config. --audio-ui also tries to pick the
topic and 48000 Hz in the panel settings UI. Writes <name>.json and PNG screenshots into --out.
Needs playwright==1.60.0 and pillow==13.0.0. All non-localhost requests are blocked.
"""
import argparse, io, json, re, time
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True)
ap.add_argument("--take", required=True)
ap.add_argument("--mic", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--name", required=True)
ap.add_argument("--audio")
ap.add_argument("--audio-ui", action="store_true")
ap.add_argument("--headed", action="store_true")
a = ap.parse_args()
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
take = json.loads((Path(a.take) / "take.json").read_text())
T0, FPS, NF = take["t0_ns"], take["fps"], take["frames_per_cam"]
HERE = Path(__file__).parent

config = {"Image!cam0": {"imageMode": {"imageTopic": "/cam0/image"}}, "Image!cam1": {"imageMode": {"imageTopic": "/cam1/image"}},
          "RawMessagesVirtual!raw": {"topicPath": "/mic/audio"}, "SourceInfo!src": {}}
right = {"direction": "column", "first": "RawMessagesVirtual!raw", "second": "SourceInfo!src", "splitPercentage": 40}
if a.audio is not None:
    config["Audio!aud"] = json.loads(a.audio)
    right = {"direction": "column", "first": "Audio!aud", "second": right, "splitPercentage": 30}
layout = {"configById": config, "globalVariables": {}, "userNodes": {}, "playbackConfig": {"speed": 1},
          "layout": {"direction": "row", "first": {"direction": "column", "first": "Image!cam0", "second": "Image!cam1"},
                     "second": right, "splitPercentage": 45}}
LAYOUT_JS = "Object.defineProperty(globalThis,'LICHTBLICK_SUITE_DEFAULT_LAYOUT',{get:()=>(%s),set:()=>{},configurable:true});" % json.dumps(layout)

R = {"name": a.name, "base": a.base, "mic": a.mic, "audio_config": a.audio, "steps": [], "console": [], "blocked": [], "pageerrors": []}


def ph_ns(text):
    """Playhead text in SEC format ('1000.092500000') -> ns, or None."""
    try:
        return int(Decimal(text) * 10**9)
    except Exception:
        return None


def expected_frame(t_ns):
    return max(0, min(NF - 1, (t_ns - T0) * FPS // 10**9))


rects = {}


def decode(png, cam):
    """Frame number from the 10-bit barcode in an Image panel canvas screenshot, or None."""
    im = Image.open(io.BytesIO(png)).convert("RGB")
    if cam not in rects:  # find the drawn image once (on a dark frame) and reuse it
        bg = Image.new("RGB", im.size, im.getpixel((1, 1)))
        diff = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > 40 else 0)
        rects[cam] = diff.getbbox()
    x0, y0, x1, y1 = rects[cam]
    y = y0 + (y1 - y0) * 340 / 360
    bits = []
    for b in range(10):
        lum = sum(im.getpixel((int(x0 + (x1 - x0) * (b * 64 + 32) / 640), int(y)))) / 3
        if 140 < lum < 200 or lum < 60:
            return None
        bits.append(lum >= 200)
    return sum(1 << (9 - i) for i, v in enumerate(bits) if v)


def main(p):
    br = p.chromium.launch(headless=not a.headed, args=[
        "--autoplay-policy=no-user-gesture-required",
        "--disable-audio-output",  # fake audio sink: no audio device is opened
        "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"])
    R["chromium"] = br.version
    ctx = br.new_context(viewport={"width": 1600, "height": 1000}, timezone_id="UTC")
    ctx.add_init_script(LAYOUT_JS)
    ctx.add_init_script(path=str(HERE / "instrument.js"))
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(a.base) else (R["blocked"].append(r.request.url), r.abort()))
    pg = ctx.new_page()
    t_start = time.time()
    pg.on("console", lambda m: R["console"].append([round(time.time() - t_start, 2), m.type, m.text[:400]]))
    pg.on("pageerror", lambda e: R["pageerrors"].append(str(e)[:400]))
    urls = ",".join(f"{a.base}/data/{f}" for f in ("cam0.mcap", "cam1.mcap", a.mic))
    pg.goto(f"{a.base}/?ds=remote-file&ds.url={urls}")
    tin = pg.locator('[data-testid="PlaybackTime-text"] input')
    tin.wait_for(timeout=60000)
    pg.wait_for_function("() => { const e = document.querySelector('[data-testid=\"PlaybackTime-text\"] input'); return e && e.value.length > 0; }", timeout=60000)
    time.sleep(4)
    pg.get_by_test_id("PlaybackTime-text").hover()
    pg.get_by_test_id("playback-time-display-toggle-button").click(force=True)
    pg.get_by_test_id("playback-time-display-option-SEC").click()
    pg.keyboard.press("Escape")
    time.sleep(1)
    canv = {c: pg.locator(f'[data-testid="panel-mouseenter-container Image!cam{c}"] canvas').first for c in (0, 1)}

    def panel_text(pid):
        loc = pg.locator(f'[data-testid="panel-mouseenter-container {pid}"]')
        return loc.inner_text() if loc.count() else None

    def snap(label, save=False):
        t1 = tin.input_value()
        pngs = {c: canv[c].screenshot() for c in (0, 1)}
        t2 = tin.input_value()
        n1, n2 = ph_ns(t1), ph_ns(t2)
        rec = {"label": label, "ph_before": t1, "ph_after": t2, "frames": {}, "expected": None}
        for c in (0, 1):
            rec["frames"][c] = decode(pngs[c], c)
        if n1 and n2:
            rec["expected"] = [expected_frame(n1), expected_frame(n2)]
            rec["ok"] = all(f is not None and rec["expected"][0] <= f <= rec["expected"][1] for f in rec["frames"].values())
        if save:
            pg.screenshot(path=str(out / f"{a.name}_{label}.png"))
        R["steps"].append(rec)
        return rec

    def seek(sec):
        # Focusing the time field pauses playback (Lichtblick onFocus -> onPause); blur so it shows the playhead again
        tin.click(); tin.press("Control+a"); tin.fill(f"{sec:.3f}"); tin.press("Enter")
        tin.evaluate("e => e.blur()")
        R["steps"].append({"label": f"seek {sec:.3f}", "perf": pg.evaluate("performance.now()")})

    def seek_slider(frac):
        """Seek without pausing: click the scrubber at a fraction of its width."""
        sl = pg.get_by_test_id("playback-slider")
        box = sl.bounding_box()
        sl.click(position={"x": box["width"] * frac, "y": box["height"] / 2})
        pg.mouse.move(800, 5)  # the scrub preview popup would cover the cam1 panel
        R["steps"].append({"label": f"slider seek {frac}", "perf": pg.evaluate("performance.now()")})

    def play_toggle(label):
        pg.get_by_test_id("play-button").click()
        R["steps"].append({"label": label, "perf": pg.evaluate("performance.now()")})

    def speed(s):
        pg.get_by_test_id("PlaybackSpeedControls-Dropdown").click()
        pg.get_by_role("menuitem").filter(has_text=re.compile(rf"^{re.escape(str(s))}\s*[x×]?$")).first.click()
        R["steps"].append({"label": f"speed {s}", "perf": pg.evaluate("performance.now()")})

    snap("start", save=True)
    R["source_info"] = panel_text("SourceInfo!src")
    R["raw_messages"] = panel_text("RawMessagesVirtual!raw")
    if a.audio is not None:
        R["audio_panel_initial"] = panel_text("Audio!aud")
    # Data Source Info tabs (the mrkbac build has File/Channels/Schemas/Metadata tabs; upstream has none)
    src = pg.locator('[data-testid="panel-mouseenter-container SourceInfo!src"]')
    R["source_info_tabs"] = {}
    for tab in ("File", "Channels", "Schemas", "Metadata"):
        t = src.get_by_role("tab").filter(has_text=re.compile(rf"^{tab}"))
        if t.count():
            t.first.click(); time.sleep(1)
            R["source_info_tabs"][tab] = src.inner_text()
            if tab == "Channels":  # expand the mic channel row: is the channel metadata map shown?
                row = src.get_by_text("/mic/audio")
                if row.count():
                    row.last.click(); time.sleep(1)
                    R["source_info_tabs"]["Channels_mic_expanded"] = src.inner_text()
                    src.screenshot(path=str(out / f"{a.name}_sourceinfo_channel_row.png"))
    # Topics sidebar
    try:
        pg.get_by_test_id("topics-left").click(); time.sleep(1)
        R["topics_sidebar"] = pg.get_by_test_id("sidebar-left").inner_text()
        pg.screenshot(path=str(out / f"{a.name}_topics.png"))
        pg.get_by_test_id("panel-settings-left").click()
    except Exception as e:
        R["topics_sidebar"] = f"failed: {e}"[:300]
    # (i) tooltip next to the playhead
    try:
        pg.locator('[data-testid="playback-controls"] svg').first.hover(); time.sleep(1)
        R["info_tooltip"] = pg.locator('[role="tooltip"]').all_inner_texts()
    except Exception as e:
        R["info_tooltip"] = f"failed: {e}"[:300]

    if a.audio_ui:
        try:
            pg.locator('[data-testid="panel-mouseenter-container Audio!aud"]').click()
            time.sleep(1)
            side = pg.get_by_test_id("sidebar-left")
            R["audio_settings_initial"] = side.inner_text()
            topic = side.locator("xpath=//*[normalize-space(text())='Topic']/following::input[1]").first
            topic.click(); topic.fill("/mic/audio"); topic.press("Enter")
            time.sleep(1)
            pg.screenshot(path=str(out / f"{a.name}_audio_settings_topic.png"))
            R["audio_settings_after_topic"] = side.inner_text()
            R["audio_panel_after_topic"] = panel_text("Audio!aud")
        except Exception as e:
            R["audio_ui_error"] = str(e)[:400]

    # Paused seeks
    for s in (1003.0, 1007.512, 1012.345, 1020.016, 1029.9, 1000.5):
        seek(s); time.sleep(2); snap(f"paused_{s:.3f}", save=s in (1007.512, 1000.5))

    def run(seconds, label, n=6):
        for k in range(n):
            time.sleep(seconds / n); snap(f"{label}_playing_{k}")

    # 1x play, pause, resume, seek while playing
    seek(1002.0); time.sleep(1.5)
    play_toggle("play"); run(6, "1x")
    play_toggle("pause"); time.sleep(1.0); snap("1x_paused", save=True); time.sleep(1.0)
    if a.audio_ui:
        R["audio_panel_16k"] = panel_text("Audio!aud")
        try:  # set 48000 Hz in the panel settings
            pg.locator('[data-testid="panel-mouseenter-container Audio!aud"]').click(); time.sleep(0.5)
            side = pg.get_by_test_id("sidebar-left")
            num = side.locator("xpath=//*[normalize-space(text())='Sample rate (Hz)']/following::input[1]").first
            num.click(); num.press("Control+a"); num.fill("48000"); num.press("Enter"); time.sleep(1)
            R["audio_settings_after_rate"] = side.inner_text()
            pg.screenshot(path=str(out / f"{a.name}_audio_settings_rate.png"))
        except Exception as e:
            R["audio_ui_rate_error"] = str(e)[:400]
    play_toggle("resume"); run(4, "1x_resumed", 4)
    seek_slider(0.5); run(4, "1x_after_slider_seek", 4)
    play_toggle("pause"); time.sleep(1.0); snap("1x_after_seek_paused")
    if a.audio is not None:
        R["audio_panel_after_1x"] = panel_text("Audio!aud")
    for sp, dur in ((0.5, 8), (2, 5)):
        speed(sp); seek(1004.0); time.sleep(1.5)
        play_toggle(f"play {sp}x"); run(dur, f"{sp}x")
        play_toggle(f"pause {sp}x"); time.sleep(1.0); snap(f"{sp}x_paused", save=True)
    R["final_screenshot"] = f"{a.name}_final.png"
    pg.screenshot(path=str(out / R["final_screenshot"]))
    R["instr"] = pg.evaluate("window.__lc")
    if a.audio is not None:
        R["audio_panel_final"] = panel_text("Audio!aud")
    br.close()


with sync_playwright() as p:
    try:
        main(p)
    finally:
        (out / f"{a.name}.json").write_text(json.dumps(R, indent=0))
        ok = [s.get("ok") for s in R["steps"] if "ok" in s]
        print(f"{a.name}: frame checks ok {sum(map(bool, ok))}/{len(ok)}, console {len(R['console'])}, blocked {len(R['blocked'])}")

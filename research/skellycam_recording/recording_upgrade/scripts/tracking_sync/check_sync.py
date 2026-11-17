"""Drive the Lichtblick v1.30.0 web build with Playwright: one camera + one tracking variant per page,
two Image panels side by side showing the same topics, "Image!off" (synchronize false) and "Image!on"
(synchronize true). Both are set in the default layout (LICHTBLICK_SUITE_DEFAULT_LAYOUT).

  python -I check_sync.py --base http://127.0.0.1:8611 --take <take dir> --variant c1_copy --out <dir>

Steps: paused seeks to fixed playhead positions, then 1x play for 10 s from 8.0 s (covers the 10-11 s gap).
probe.js decodes image and overlay frame numbers from the canvas pixels on every animation frame.
Writes <variant>.json and a few PNGs into --out. Needs playwright==1.60.0. Non-localhost requests are blocked.
"""
import argparse, json, random, subprocess, threading, time
from pathlib import Path

from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True)
ap.add_argument("--take", required=True)
ap.add_argument("--variant", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--gpu", action="store_true", help="real GPU via ANGLE D3D11 (default headless shell uses SwiftShader, CPU)")
a = ap.parse_args()
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
take = json.loads((Path(a.take) / "take.json").read_text())
V = take["variants"][a.variant]
cam = V["camera"]
T0 = take["t0_ns"]
HERE = Path(__file__).parent

ann_topic = f"/cameras/{cam}/tracking/annotations"
panel = lambda sync: {"imageMode": {"imageTopic": f"/cameras/{cam}/image", "annotations": {ann_topic: {"visible": True}}, "synchronize": sync}}
layout = {"configById": {"Image!off": panel(False), "Image!on": panel(True)}, "globalVariables": {}, "userNodes": {},
          "playbackConfig": {"speed": 1}, "layout": {"direction": "row", "first": "Image!off", "second": "Image!on", "splitPercentage": 50}}
LAYOUT_JS = "Object.defineProperty(globalThis,'LICHTBLICK_SUITE_DEFAULT_LAYOUT',{get:()=>(%s),set:()=>{},configurable:true});" % json.dumps(layout)

# Paused playhead positions (s from T0): fixed seeds so every variant gets the same list
rng = random.Random(7)
POS = [10.2, 10.5, 10.95, 11.05, 0.9] + sorted(round(rng.uniform(0.5, 19.5), 3) for _ in range(30))

R = {"variant": a.variant, "spec": {k: V[k] for k in ("camera", "delay_ns", "stamp", "filler")}, "base": a.base,
     "layout": layout, "steps": [], "console": [], "pageerrors": [], "blocked": [], "cpu": []}


def cpu_sampler(stop):
    while not stop.is_set():
        try:
            # total load %, then the top processes in % of one core
            cmd = ("(Get-CimInstance Win32_Processor).LoadPercentage; Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | "
                   "? { $_.Name -notin '_Total','Idle' } | sort PercentProcessorTime -desc | select -first 5 | % { $_.Name + '=' + $_.PercentProcessorTime }")
            v = subprocess.run(["powershell", "-NoProfile", "-c", cmd], capture_output=True, text=True, timeout=20).stdout.split()
            R["cpu"].append([round(time.time(), 1), v])
        except Exception as e:
            R["cpu"].append([round(time.time(), 1), str(e)[:80]])
        stop.wait(2)


def main(p):
    br = p.chromium.launch(headless=True, args=["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"]
                            + (["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu"] if a.gpu else []))
    R["chromium"] = br.version
    ctx = br.new_context(viewport={"width": 1600, "height": 700}, timezone_id="UTC")
    ctx.add_init_script(LAYOUT_JS)
    ctx.add_init_script(path=str(HERE / "probe.js"))
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(a.base) else (R["blocked"].append(r.request.url), r.abort()))
    pg = ctx.new_page()
    t_start = time.time()
    pg.on("console", lambda m: R["console"].append([round(time.time() - t_start, 2), m.type, m.text[:600]]))
    pg.on("pageerror", lambda e: R["pageerrors"].append([round(time.time() - t_start, 2), str(e)[:600]]))
    urls = ",".join(f"{a.base}/data/{f}" for f in (f"{cam}.mcap", f"trk_{a.variant}.mcap"))
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

    def state(label, save=False):
        rec = {"label": label, "perf": pg.evaluate("performance.now()"), "cur": pg.evaluate("window.__ts.cur"), "ph": tin.input_value(),
               "hud": {pid: pg.locator(f'[data-testid="panel-mouseenter-container {pid}"]').inner_text()[:300] for pid in ("Image!off", "Image!on")}}
        if save:
            pg.screenshot(path=str(out / f"{a.variant}_{label}.png"))
        R["steps"].append(rec)

    def seek(sec):
        # Typing in the time field pauses playback; blur so the field shows the playhead again
        tin.click(); tin.press("Control+a"); tin.fill(f"{T0 / 1e9 + sec:.3f}"); tin.press("Enter")
        tin.evaluate("e => e.blur()")
        R["steps"].append({"label": f"seek {sec:.3f}", "perf": pg.evaluate("performance.now()")})

    R["webgl_renderer"] = pg.evaluate("() => { const g = document.createElement('canvas').getContext('webgl2'); return g.getParameter(g.getExtension('WEBGL_debug_renderer_info').UNMASKED_RENDERER_WEBGL); }")
    state("start")
    for k, s in enumerate(POS):
        seek(s); time.sleep(1.3); state(f"paused_{s:.3f}", save=k in (0, 4))
    seek(8.0); time.sleep(1.5)
    stop = threading.Event(); th = threading.Thread(target=cpu_sampler, args=(stop,)); th.start()
    pg.get_by_test_id("play-button").click()
    R["steps"].append({"label": "play", "perf": pg.evaluate("performance.now()")})
    time.sleep(10.5)
    pg.get_by_test_id("play-button").click()
    R["steps"].append({"label": "pause", "perf": pg.evaluate("performance.now()")})
    stop.set(); th.join()
    time.sleep(1.0); state("after_play", save=True)
    R["probe_log"] = pg.evaluate("window.__ts.log")
    R["raf"] = pg.evaluate("window.__ts.raf")
    br.close()


with sync_playwright() as p:
    try:
        main(p)
    finally:
        (out / f"{a.variant}.json").write_text(json.dumps(R))
        print(f"{a.variant}: steps {len(R['steps'])}, console {len(R['console'])}, pageerrors {len(R['pageerrors'])}, blocked {len(R['blocked'])}")

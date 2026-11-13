"""One-off: mrkbac Data Source Info > Channels, expand /mic/audio, record whether the channel metadata map is shown.
  python -I channel_metadata.py http://127.0.0.1:8602 <outdir>   (playwright==1.60.0)
"""
import sys, json, time, re
from playwright.sync_api import sync_playwright
B, out = sys.argv[1], sys.argv[2]  # base URL of the served mrkbac build, output dir
urls=",".join(f"{B}/data/{f}" for f in ["cam0.mcap","cam1.mcap","mic_opus.mcap"])
layout={"configById":{"SourceInfo!src":{}},"globalVariables":{},"userNodes":{},"playbackConfig":{"speed":1},"layout":{"direction":"row","first":"SourceInfo!src","second":"SourceInfo!src2"}}
layout["configById"]["SourceInfo!src2"]={}
init="Object.defineProperty(globalThis,'LICHTBLICK_SUITE_DEFAULT_LAYOUT',{get:()=>(%s),set:()=>{},configurable:true});"%json.dumps(layout)
with sync_playwright() as p:
    br=p.chromium.launch(args=["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1","--disable-audio-output"])
    ctx=br.new_context(viewport={"width":1600,"height":1400},timezone_id="UTC"); ctx.add_init_script(init)
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(B) else r.abort())
    pg=ctx.new_page(); pg.goto(f"{B}/?ds=remote-file&ds.url={urls}"); pg.locator("[data-testid=PlaybackTime-text] input").wait_for(timeout=90000); time.sleep(4)
    src=pg.locator('[data-testid="panel-mouseenter-container SourceInfo!src"]')
    src.get_by_role("tab").filter(has_text=re.compile("^Channels")).first.click(); time.sleep(1)
    cands=src.get_by_text("/mic/audio")
    print("cands", cands.count(), cands.all_inner_texts())
    cands.last.click(); time.sleep(1)
    t=src.inner_text(); json.dump({"channels_tab_mic_expanded": t[t.find("Filter"):]}, open(out+"/mrk_channel_expanded.json","w",encoding="utf8"), ensure_ascii=False, indent=0)
    src.screenshot(path=out+"/mrk_channel_expanded.png")
    br.close()

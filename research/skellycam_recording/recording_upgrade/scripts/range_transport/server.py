"""T-S5 test server. Run with the skellycam-phase1 venv: python -I server.py <mode> <port> <media_dir>
Binds 127.0.0.1 only. sys.path gets the phase-1 worktree so the real skellycam modules import read-only.

mode "real": mirrors skellycam's app around the playback route (skellycam/app.py:80-110):
  cors(app) -> routers -> add_middleware(app) (BaseHTTPMiddleware request logger), logging at TRACE as in
  skellycam/__main__.py:99-100 (file handler in <media_dir>, console to this process's stdout, no websocket queue).
  Routes:
    /skellycam/playback/...   the REAL playback_router, unmodified (FileResponse + transcode-on-demand).
    /fixed/{name}             the minimal fix: FileResponse on the original file, no probe or transcode,
                              stat cached, GET+HEAD, Access-Control-Expose-Headers added.
    /fixed_ns/{name}          as /fixed plus Cache-Control: no-store.
mode "bare": only CORSMiddleware(expose_headers=...), /fixed/{name} and /fixed_ns/{name}; no logging middleware.
Both: /__cpu (process CPU seconds), /__conns (client ports seen since last call; shows Chromium's per-host limit).
"""
import os, sys, time

PHASE1 = r"C:\Users\Dom\GitHub\freemocap\skellycam-phase1"
sys.path.insert(0, PHASE1)

import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402

mode, port, media = sys.argv[1], int(sys.argv[2]), sys.argv[3]
FLAC = os.path.join(media, "flac")
FILES = {
    "pattern.bin": os.path.join(media, "pattern.bin"),
    "cam0.mkv": os.path.join(media, "rec", "rangetest", "cam0.mkv"),
    "h264.mp4": os.path.join(media, "rec", "rangetest", "h264.mp4"),
    "big.mkv": os.path.join(media, "big.mkv"),
    "f1_1ch_skau.mka": os.path.join(FLAC, "f1_1ch_skau.mka"),
    "f1_2ch_skau.mka": os.path.join(FLAC, "f1_2ch_skau.mka"),
}
EXPOSE = "Content-Range, Content-Length, Accept-Ranges, ETag, Last-Modified"
STATS: dict[str, os.stat_result] = {}
PORTS: set[int] = set()

app = FastAPI()

if mode == "real":
    from skellylogs import configure_logging, LogLevels  # noqa: E402
    configure_logging(level=LogLevels.TRACE, log_file_path=os.path.join(media, "server_real.log"), use_websocket=False)
    from skellycam.api.middleware.cors import cors  # noqa: E402
    from skellycam.api.middleware.add_middleware import add_middleware  # noqa: E402
    from skellycam.api.http.playback.playback_router import playback_router  # noqa: E402
    cors(app)                                            # skellycam/app.py order: cors -> routes -> middleware
else:
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                       expose_headers=[h.strip() for h in EXPOSE.split(",")])


@app.middleware("http")
async def _ports(request: Request, call_next):
    PORTS.add(request.client.port)
    return await call_next(request)


@app.get("/__cpu")
async def _cpu():
    return {"proc_s": time.process_time(), "wall_s": time.perf_counter(), "pid": os.getpid()}


@app.get("/__conns")
async def _conns():
    out = sorted(PORTS); PORTS.clear()
    return {"n": len(out), "ports": out}


@app.api_route("/fixed/{name}", methods=["GET", "HEAD"])
async def fixed(name: str):
    return _serve(name, {"Access-Control-Expose-Headers": EXPOSE})


@app.api_route("/fixed_ns/{name}", methods=["GET", "HEAD"])
async def fixed_ns(name: str):
    """As /fixed, plus Cache-Control: no-store (Chromium's HTTP cache fails concurrent ranges on one URL)."""
    return _serve(name, {"Access-Control-Expose-Headers": EXPOSE, "Cache-Control": "no-store"})


def _serve(name: str, headers: dict):
    path = FILES.get(name)
    if path is None or not os.path.isfile(path):
        raise HTTPException(404, "no such file")
    st = STATS.get(name)
    if st is None:
        st = STATS[name] = os.stat(path)
    return FileResponse(path, media_type="application/octet-stream", stat_result=st, headers=headers)


if mode == "real":
    app.include_router(playback_router, prefix="/skellycam")
    add_middleware(app)

if __name__ == "__main__":
    print(f"T-S5 server mode={mode} pid={os.getpid()} on 127.0.0.1:{port}", flush=True)
    uvicorn.Server(uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning", reload=False)).run()

# (h) permessage-deflate cost on a real SkellyCam UI payload (5 cameras, create_frontend_payload, websockets PerMessageDeflate)

websockets 16.1.1; zlib defaults (uvicorn ServerPerMessageDeflateFactory() with no arguments), window bits 15, context takeover on; 180 payloads per size after 20 warm-up. Runs on the event-loop thread in the real server.

| size | payload KB (median) | deflated KB | deflate median / p99 ms | build (create_frontend_payload) median ms |
|---|---|---|---|---|
| 720p | 142 | 44 | 2.81 / 3.20 | 3.03 |
| 1080p | 314 | 95 | 6.22 / 6.93 | 6.17 |

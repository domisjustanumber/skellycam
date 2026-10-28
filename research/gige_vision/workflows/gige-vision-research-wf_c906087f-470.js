export const meta = {
  name: 'gige-vision-research',
  description: 'Research GigE Vision (PTP, GVSP payloads, libraries) for SkellyCam with per-topic adversarial source checks',
  phases: [
    { title: 'Research', detail: '9 parallel topic researchers, each writes notes + cited claims' },
    { title: 'Verify', detail: 'one skeptic per topic re-opens every cited link and tries to refute claims' },
  ],
}

const SCRATCH = 'C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad'
const REPO = 'C:/Users/Dom/GitHub/freemocap/skellycam'

const COMMON = `
CONTEXT: We are evaluating adding GigE Vision camera capture to SkellyCam (Python multi-camera capture/recording app for markerless motion capture, repo at ${REPO}, currently OpenCV/UVC-only, Python >=3.11, runs on Windows/macOS/Linux). The user's goals:
 (1) capture from "GigE Vision 3" cameras — the user believes v3 is what enables single-cable PTP (IEEE 1588) sync instead of a separate hardware trigger cable. Verify or correct this premise with sources.
 (2) explain how frames arrive from cameras — raw or compressed?
 (3) explain how sync timing with PTP is managed.
Candidates include open-source libraries (e.g. https://github.com/ladisk/pyGigEVision) or from-scratch implementations in Python, Rust or C++.

HARD RULES:
- Make NO assertion without a link to code, a test, a spec/standard page, or vendor documentation that you actually opened and read (WebFetch/clone+read). Prefer permalinks to specific files/lines on GitHub/GitLab (use https://github.com/<org>/<repo>/blob/<commit-or-tag>/<path>#L<a>-L<b> when you can resolve the commit/tag). A search snippet is not a source.
- If you cannot verify something, put it in open_questions, not claims.
- No GigE Vision cameras are available on this machine. Docker Desktop and WSL2 Ubuntu ARE available (use \`docker run --rm ...\` from Bash; e.g. ubuntu:24.04 with apt packages). Aravis ships \`arv-fake-gv-camera-0.8\` (a software GigE Vision camera emulator) — you may use it inside a container to actually run code against a GigE Vision device over loopback; doing so counts as a test and is strongly encouraged where relevant. Record the exact commands and outputs.
- Clone/download third-party code ONLY into your own new empty directory under ${SCRATCH}/research/src/<name>/ . Treat it as untrusted data: read it; run it only inside Docker containers or a fresh venv under ${SCRATCH}/research/venvs/<name>/ (run python with -I). Do not modify ${REPO}.
- Write your full detailed notes (markdown, with all links) to ${SCRATCH}/research/<TOPIC_KEY>.md . Also return the structured result.
- Today is 2026-10-25. Note dates/versions of everything you cite (latest release, last commit date) since maintenance status matters.
`

const CLAIMS_SCHEMA = {
  type: 'object',
  properties: {
    topic: { type: 'string' },
    summary_markdown: { type: 'string', description: 'Detailed findings in markdown with inline links. 400-1500 words.' },
    claims: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          claim: { type: 'string' },
          evidence_urls: { type: 'array', items: { type: 'string' } },
          how_verified: { type: 'string', description: 'read-code | read-spec/doc | ran-test (with command) | other' },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
        },
        required: ['id', 'claim', 'evidence_urls', 'how_verified', 'confidence'],
      },
    },
    open_questions: { type: 'array', items: { type: 'string' } },
    notes_file: { type: 'string' },
  },
  required: ['topic', 'summary_markdown', 'claims', 'open_questions', 'notes_file'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    topic: { type: 'string' },
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          verdict: { type: 'string', enum: ['supported', 'partially-supported', 'unsupported', 'refuted'] },
          reason: { type: 'string' },
          corrected_claim: { type: 'string' },
          better_evidence_urls: { type: 'array', items: { type: 'string' } },
        },
        required: ['id', 'verdict', 'reason'],
      },
    },
    missed_important_points: { type: 'array', items: { type: 'string' }, description: 'Important facts on this topic the researcher missed, each with a link you opened.' },
  },
  required: ['topic', 'verdicts', 'missed_important_points'],
}

const TOPICS = [
  {
    key: 'spec-versions',
    prompt: `TOPIC_KEY=spec-versions. Establish exactly what each GigE Vision standard version added: 1.0 (2006), 1.1, 1.2, 2.0 (2011), 2.1, 2.2, and 3.0 (if it exists — find its release date and contents; I believe it may concern RDMA / RoCE v2 streaming, verify). Key questions: In which version did IEEE 1588 PTP support appear (and which PTP profile/version — 1588-2008 vs 1588-2019)? Scheduled Action Commands? Compressed payloads (JPEG, JPEG 2000, H.264)? Multi-part payloads? GenDC? 10GigE? Link aggregation? Is there anything PTP-related that is NEW in 3.0 specifically? Is "single cable" really about PTP + PoE (IEEE 802.3af/at) rather than the GigE Vision version? Sources: A3/automate.org standard pages and press releases, EMVA/GenICam SFNC docs, vendor white papers (Basler, Teledyne FLIR, LUCID, Allied Vision, Pleora, Emergent Vision Technologies), Aravis docs, Wikipedia (only as a pointer, follow its citations). Also: how can a host tell which GigE Vision version a camera implements (bootstrap register "Version" at 0x0000, GVCP capability bits for PTP/action/scheduled action) — cite Aravis source (e.g. src/arvgvcpprivate.h, arvgvdevice.c) or Wireshark packet-gvcp.c dissector for register addresses/bit definitions.`,
  },
  {
    key: 'frame-transport',
    prompt: `TOPIC_KEY=frame-transport. Explain precisely how image frames travel from a GigE Vision camera to the host: GVCP (control, UDP 3956) vs GVSP (streaming, UDP); stream channel setup (SCPx registers: host port, destination IP, packet size SCPS, packet delay SCPD); GVSP packet structure — leader / payload / trailer packets, block_id (16-bit vs 64-bit extended ID 'EI' flag in 2.0), packet_id, payload types (image 0x0001, raw data, file, chunk data, extended chunk, JPEG 0x0006?, JPEG2000, H.264, multi-zone image, multi-part, GenDC — verify the numeric codes), what the image leader contains (timestamp 64-bit, pixel format PFNC code, size_x/size_y, offsets, padding), the trailer; packet resend (PACKETRESEND_CMD) and what happens on loss; jumbo frames/MTU; inter-packet delay for multi-camera bandwidth sharing. Answer clearly: do typical machine-vision GigE cameras send RAW (Mono8/Mono12/Bayer RG8/BayerRG12p etc. uncompressed) or compressed? Which cameras actually support compressed GVSP payloads (find concrete vendor examples with doc links, e.g. JPEG-capable or H.264 models, and Lossless Compression features such as LUCID 'Lossless Compression' / Basler 'Compression Beyond' / FLIR) and how they are signalled. Bandwidth math: e.g. 1920x1200 BayerRG8 @ 60 fps on 1 GbE (~ how many Mbit/s), so how many such cameras per 1GbE link. Primary code evidence: Aravis src/arvgvspprivate.h & arvgvstream.c (https://github.com/AravisProject/aravis), Wireshark epan/dissectors/packet-gvsp.c and packet-gvcp.c (https://gitlab.com/wireshark/wireshark), and if useful the Pixel Format Naming Convention (PFNC) doc from EMVA. Bonus: run Aravis fake GV camera in Docker and capture with arv-camera-test-0.8 / arv-tool and optionally tcpdump to show a real GVSP leader/payload/trailer sequence; include the decoded leader fields in your notes.`,
  },
  {
    key: 'ptp-sync',
    prompt: `TOPIC_KEY=ptp-sync. Explain how multi-camera synchronization via IEEE 1588 PTP works on GigE Vision cameras, end to end: (a) enabling PTP on the camera via GenICam SFNC features (PtpEnable / older GevIEEE1588, PtpStatus/GevIEEE1588Status: Initializing, Master, Slave, Listening, Uncalibrated...; PtpDataSetLatch, PtpOffsetFromMaster, PtpClockAccuracy, PtpServoStatus) — cite the SFNC PDF and at least two vendor docs; (b) who is grandmaster (Best Master Clock Algorithm; one camera becomes master if no host/grandmaster; host as grandmaster via linuxptp ptp4l on Linux; what's possible on Windows (Windows 10/11 ships a PTP *client* in w32time — can it act as master? find Microsoft docs) and macOS); (c) network requirements: PTP over UDP multicast (ports 319/320), switch behaviour (unmanaged switches add asymmetric delay; transparent/boundary clocks; IGMP snooping problems), PoE switches for single-cable power+data+sync; typical achievable sync accuracy (sub-microsecond claims — cite vendor numbers); (d) HOW frames get synchronized once clocks are synced: (i) Scheduled Action Commands (GVCP ACTION_CMD with action_time) triggering all cameras at a future PTP time — SFNC ActionDeviceKey/ActionGroupKey/ActionGroupMask, TriggerSource=Action1; (ii) vendor 'synchronous free run' / 'PTP sync mode' features (Basler 'Synchronous Free Run' SyncFreeRunTimerStartTimeLow/High; LUCID 'PTPSyncFrameRate' / 'AcquisitionStartMode=PTPSync'; Teledyne FLIR Spinnaker PTP; Allied Vision 'PtpAcquisitionGateTime'); (iii) post-hoc alignment using the PTP-domain timestamp in each GVSP image leader / chunk data; (e) how the host maps camera PTP timestamps to host clock (latching GevTimestampControlLatch / TimestampLatch + TimestampLatchValue). Include the GVCP ACTION_CMD packet format (cite Aravis arvgvcpprivate.h or Wireshark packet-gvcp.c) and whether Aravis has an API to send (scheduled) action commands (search Aravis source for 'action' — e.g. arv_gv_device_issue_scheduled_action_command or arvgvinterface action functions — give permalinks). Also note what open-source tooling exists for sending action commands from Python.`,
  },
  {
    key: 'pygigevision',
    prompt: `TOPIC_KEY=pygigevision. Deep-evaluate https://github.com/ladisk/pyGigEVision . Clone it into your scratch src dir. Read ALL of its source and tests. Report: license; last commit date and release history (PyPI?); maintainers; dependencies (does it wrap a vendor SDK, Harvesters/GenTL, Aravis, or implement GVCP/GVSP itself?); exact supported features with file/line permalinks: device discovery, register read/write, GenICam XML download/parsing, feature get/set by name, stream channel setup, GVSP receive & reassembly, packet resend, pixel formats supported, timestamps exposed, PTP support (enable, status, offset), action commands, multi-camera support, performance characteristics (pure-Python socket recv loop? threads?), platform support (Windows/macOS/Linux), tests present? CI? Then TRY IT: create a venv under the scratch venvs dir and/or a Docker container (python:3.12 + apt aravis-tools for arv-fake-gv-camera-0.8) and attempt to discover and grab frames from the Aravis fake camera using pyGigEVision. Record commands and results (success/failure with error messages). Give a frank verdict: suitable as SkellyCam's base, as reference code, or not suitable — and why.`,
  },
  {
    key: 'harvesters-gentl',
    prompt: `TOPIC_KEY=harvesters-gentl. Evaluate the GenICam GenTL route: Harvesters (https://github.com/genicam/harvesters) + Python 'genicam' package (GenApi bindings from EMVA) + a GenTL Producer (.cti) for GigE Vision. Report: Harvesters maintenance status (last release/commit as of 2026), supported Python versions, license; the 'genicam' PyPI package wheels per OS/arch/Python version (check PyPI file list); how Harvesters exposes frames (buffer -> numpy, timestamps, chunk data) with code permalinks (e.g. harvesters/core.py ImageAcquirer.fetch, Component2DImage); multi-camera usage. Then catalogue GigE Vision GenTL producers by platform with license/redistribution terms and links: Matrix Vision/Balluff mvGenTL Acquire (free, GEV support? Windows/Linux/macOS?), Basler pylon GenTL producer for GEV, Teledyne FLIR Spinnaker GenTL, Allied Vision Vimba X GenTL (GigE TL), Baumer GAPI GenTL, LUCID Arena GenTL, Pleora eBUS, Euresys/Kaya, Aravis-based GenTL (any?), STEMMER CVB. Specifically: which are free, which run on macOS (Apple Silicon?), which work with any-vendor cameras vs vendor-locked, which include a filter driver on Windows for performance. Can PTP / action commands be done through Harvesters (via node map feature access + GenTL TLParams / interface-level action command features like ActionCommand on the Interface/System module)? Cite GenTL SFNC (GenTL Standard Features Naming Convention) for interface/system-level action command features. Optionally run Harvesters in Docker against Aravis fake camera if any free Linux GEV producer is installable non-interactively — otherwise say so.`,
  },
  {
    key: 'aravis',
    prompt: `TOPIC_KEY=aravis. Deep-evaluate Aravis (https://github.com/AravisProject/aravis), the LGPL C library for GigE Vision & USB3 Vision. Report with permalinks: license (LGPL-2.1+ — implications for SkellyCam, which is AGPL-3.0, and for PyInstaller-bundled installers); latest release and maintenance; platform support — Linux (primary), macOS (Homebrew formula? test?), Windows (MSYS2/MinGW package? any official support statement; check the README/docs and issues); Python access via GObject Introspection (PyGObject 'gi.repository.Aravis') — how hard is installation on each OS (conda-forge 'aravis' package? pip?); performance features (packet socket on Linux, packet resend, socket buffer); API for: discovery (arv_update_device_list), feature access by name, stream create + buffer pool, buffer timestamp (arv_buffer_get_timestamp — device vs system timestamp), chunk data parsing, PTP (any helpers? check arvcamera.c for 'ptp' e.g. arv_camera_gv_... ), action commands (search source for 'action'), multipart. Run code: build a Docker container (ubuntu:24.04, apt install aravis-tools gir1.2-aravis-0.8 python3-gi python3-numpy) — start arv-fake-gv-camera-0.8 on loopback (-i 127.0.0.1) and from Python via gi grab ~100 frames, print buffer timestamps, pixel format, frame size, and measure fps. Save the exact Python script you used to ${SCRATCH}/research/aravis_fake_camera_capture.py and include output. Also evaluate the Rust bindings (aravis-rs on crates.io/github) briefly. Verdict: is Aravis viable as SkellyCam's GigE Vision backend on all 3 OSes?`,
  },
  {
    key: 'rust-cpp-vendor',
    prompt: `TOPIC_KEY=rust-cpp-vendor. Survey non-Python and vendor options for GigE Vision capture, each with repo/doc links, license, maintenance date, platform support, GigE Vision completeness, PTP/action command support: (1) Rust: 'cameleon' (https://github.com/cameleon-rs/cameleon — does it support GigE Vision or only USB3 Vision as of 2026? read its source tree/README/issues), aravis-rs, any other crates for gvcp/gvsp/genicam (search crates.io: 'gige', 'gvsp', 'genicam'); (2) C++: rc_genicam_api (Roboception, https://github.com/roboception/rc_genicam_api — GenTL consumer + bundled GenTL producer for GigE? license, platforms), GenICam reference implementation, Aravis C API, 'libgige'/other; (3) vendor SDKs with Python bindings: Basler pypylon (pip wheels for Win/mac/Linux? does pylon support non-Basler GigE cameras? PTP support docs), Teledyne FLIR Spinnaker/PySpin, Allied Vision Vimba X / VmbPy, LUCID Arena SDK arena_api, Pleora eBUS SDK Python — for each: does it work with other vendors' GigE Vision cameras (GenICam-compliant) and on which OSes, licensing for redistribution in an open-source app, and ptp/action command API names with doc links. (4) gst/plugins: aravissrc GStreamer element. Produce a comparison table in your summary (rows=option; columns: language, license, Win/mac/Linux, any-vendor?, PTP features accessible?, action cmds?, maintained (last release date)).`,
  },
  {
    key: 'from-scratch',
    prompt: `TOPIC_KEY=from-scratch. Assess a from-scratch GigE Vision client for SkellyCam in (a) pure Python, (b) Rust with PyO3 bindings, (c) C++ with pybind11/nanobind. Enumerate the minimum protocol surface with references to where each is implemented in Aravis and/or Wireshark dissectors (permalinks): GVCP discovery (DISCOVERY_CMD broadcast, ack fields), FORCEIP, READREG/WRITEREG/READMEM/WRITEMEM, Control Channel Privilege (CCP register 0x0A00) and heartbeat (0x0938 timeout), GenICam XML retrieval (First URL register 0x0200, 'Local:' URL with zip), GenApi XML evaluation (SwissKnife, IntReg, converters — the hard part; are there pure-Python or Rust GenApi parsers? e.g. cameleon-genapi crate, python 'genicam' official binding, 'genicam' parsers on GitHub), stream channel setup (SCP0 registers 0x0D00.., test packet / packet size negotiation with 'do not fragment'), GVSP receive with packet reordering, missing packet detection and PACKETRESEND, extended IDs (64-bit block ids), PTP feature access (just GenApi features), ACTION_CMD packets. Quantify performance: packets/s for 1 GbE at MTU 1500 vs 9000; whether a pure-Python asyncio/socket loop can keep up (find benchmarks or measure: write a small local UDP blast test in Python on this machine — sender and receiver over loopback with 1500 and 9000-byte datagrams at ~1 Gbit/s — and report achieved throughput and drop rate; save script to ${SCRATCH}/research/udp_recv_benchmark.py). Mention OS socket receive buffer tuning (SO_RCVBUF limits: Linux net.core.rmem_max, Windows, macOS kern.ipc.maxsockbuf) and Windows vendor filter drivers. Also look at existing small from-scratch implementations for reference (e.g. pyGigEVision https://github.com/ladisk/pyGigEVision, any GitHub 'gvcp python' projects, Rust 'gige' crates). Give an effort estimate (person-weeks) for each language option and the main risks.`,
  },
  {
    key: 'skellycam-arch',
    prompt: `TOPIC_KEY=skellycam-arch. Map SkellyCam's camera pipeline so a GigE Vision backend can be added. Read ${REPO}/skellycam/core/** (camera/, camera_group/, ipc/, recorders/, timestamps/, types/, device_detection/), ${REPO}/skellycam/api/http/cameras/camera_router.py, ${REPO}/skellycam/tests/**, and ${REPO}/skellycam-docs/docs/technical/architecture.mdx, frame-synchronization.mdx, core/frame-perfect-sync.mdx, core/precise-timestamps.mdx. Use repo-relative paths with line numbers (e.g. skellycam/core/camera/opencv/opencv_camera_loop.py:42) for every statement. Answer: (1) how a camera worker process is created and what its loop does (grab/retrieve split for sync? orchestrator barrier?), (2) the CameraConfig model fields and how a backend is chosen (determine_backend.py) — is there an abstraction for multiple backends or is OpenCV hard-wired, (3) the frame record dtype in shared memory (numpy_record_dtypes.py, frame_dtype_factories.py) — image shape/dtype assumptions (BGR uint8 3-channel?), timestamp fields stored per frame and what clock they use, (4) how device detection works and where GigE devices would be listed, (5) how recording/timestamps CSVs are produced and where camera-side hardware timestamps (e.g. PTP) could be stored, (6) the existing test patterns and mocks (tests/mocks/camera_mock.py) that a GigE backend test could reuse, (7) a concrete, minimal integration design: which new modules/files, what interface (e.g. a CameraBackend protocol with open/apply_config/grab/retrieve/close), how a GigE camera id would be represented in CameraConfig (e.g. backend field + serial/MAC/IP), how Bayer/mono raw frames would be debayered to the BGR uint8 frames the rest of the pipeline expects, and where PTP timestamps would be threaded through. Do NOT edit the repo. This topic's claims use repo file:line references instead of URLs (put them in evidence_urls).`,
  },
]

const results = await pipeline(
  TOPICS,
  t => agent(`${COMMON}\n\n${t.prompt}`, { label: `research:${t.key}`, phase: 'Research', schema: CLAIMS_SCHEMA }),
  (r, t) => {
    if (!r) return null
    return agent(`${COMMON}\n\nYou are an adversarial fact-checker for topic "${t.key}". Below are claims made by a researcher. For EACH claim, open its evidence links yourself (WebFetch, or clone/read code in your own dir under ${SCRATCH}/research/src/verify-${t.key}/; for skellycam-arch, read the repo files at the given lines) and try to REFUTE it. Default to 'unsupported' if the links do not actually show the claim. Provide corrected claims and better evidence where you can. Also list important points the researcher missed (each with a link you opened). Pay special attention to version numbers, register addresses, numeric codes, dates, and whether a library 'supports' a feature vs merely mentions it.\n\nResearcher summary:\n${r.summary_markdown}\n\nClaims JSON:\n${JSON.stringify(r.claims, null, 1)}\n\nResearcher open questions:\n${JSON.stringify(r.open_questions)}`,
      { label: `verify:${t.key}`, phase: 'Verify', schema: VERDICT_SCHEMA })
      .then(v => ({ key: t.key, research: r, verification: v }))
  },
)
return results.filter(Boolean)

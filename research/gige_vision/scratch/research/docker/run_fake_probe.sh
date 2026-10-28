#!/bin/sh
# Runs inside skellycam-research/fakegv:1 ; /work = research dir (ro), /out = results (rw)
# usage: run_fake_probe.sh <lost_per_thousand> <tag> [extra probe args...]
set -u
LOST=$1; TAG=$2; shift 2
echo "### aravis version: $(dpkg-query -W -f='${Version}' aravis-tools) ; fake camera gvsp-lost-ratio=$LOST/1000 ; extra args: $*"
arv-fake-gv-camera-0.8 -i 127.0.0.1 -r "$LOST" >/tmp/fake.log 2>&1 &
sleep 1.5
echo "### arv-tool-0.8 (Aravis' own client) sanity check"
arv-tool-0.8 -a 127.0.0.1 control Width Height PixelFormat PayloadSize 2>&1 | head -8
echo "### probe A: system python3 -I, toy GenApi (no genicam wheel)"
python3 -I /work/tests/gev_scratch_probe.py --target 127.0.0.1 --stream-seconds 3 --json /out/probe_toy_${TAG}.json "$@"
echo "exit=$?"
echo "### probe B: venv python -I with official EMVA genicam 1.6.0"
/opt/gen/bin/python -I /work/tests/gev_scratch_probe.py --target 127.0.0.1 --stream-seconds 3 --official-genapi --json /out/probe_genicam_${TAG}.json "$@"
echo "exit=$?"
kill %1 2>/dev/null

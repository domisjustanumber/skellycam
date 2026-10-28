export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null; apt-get install -y -qq --no-install-recommends python3-venv aravis-tools >/dev/null 2>&1
dpkg -S /usr/bin/arv-fake-gv-camera-0.8; dpkg -s aravis-tools | grep Version
python3 -m venv /venv && /venv/bin/pip install -q viva-genicam==0.10.0 2>&1 | tail -1
/venv/bin/pip show viva-genicam | grep -i ^version
echo "== wire format"; timeout 30 /venv/bin/python -I /s/wire.py
echo "== send_action to aravis fake"; arv-fake-gv-camera-0.8 -i lo >/tmp/fake.log 2>&1 & sleep 2
timeout 20 /venv/bin/python -I -c "import viva_genicam as vg; print(vg.send_action(1,1,0xFFFFFFFF,destination='127.0.0.1',timeout_ms=500))"
arv-tool-0.8 -a 127.0.0.1 control GevIEEE1588 PtpEnable GevTimestampTickFrequency 2>&1 | head

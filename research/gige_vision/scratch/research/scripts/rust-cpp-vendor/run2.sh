export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null; apt-get install -y -qq --no-install-recommends aravis-tools python3-venv >/dev/null 2>&1
arv-fake-gv-camera-0.8 -i lo > /tmp/fake.log 2>&1 &
python3 -m venv /venv && /venv/bin/pip install -q viva-genicam==0.10.0 telegenicam==2.1.0 numpy 2>&1 | tail -2
sleep 1; timeout 60 /venv/bin/python -I /scripts/test2.py

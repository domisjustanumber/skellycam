set -e
dpkg -l | grep -E "libaravis|python3-gi " | awk '{print $2,$3}'
arv-fake-gv-camera-0.8 -i 127.0.0.1 >/tmp/fake.log 2>&1 & sleep 2
arv-tool-0.8
python3 -I /work/tick_cache_test.py

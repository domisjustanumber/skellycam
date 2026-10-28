set -e
echo "=== package versions ==="
dpkg -l | grep -i -E "aravis|python3-gi |python3-numpy" | awk '{print $2, $3}'
arv-fake-gv-camera-0.8 -i 127.0.0.1 >/tmp/fake.log 2>&1 &
FAKE=$!
sleep 2
echo "=== arv-tool-0.8 ==="
arv-tool-0.8 || true
echo "=== python capture ==="
python3 -I /work/aravis_fake_camera_capture.py --device 127.0.0.1 --frames 100 || echo "exit=$?"
echo "=== python capture, frame-rate 100 ==="
python3 -I /work/aravis_fake_camera_capture.py --device 127.0.0.1 --frames 100 --frame-rate 100 | tail -12 || true
kill $FAKE

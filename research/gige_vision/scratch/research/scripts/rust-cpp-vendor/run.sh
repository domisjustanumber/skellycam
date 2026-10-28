set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends aravis-tools aravis-tools-cli gstreamer1.0-tools python3-venv python3-pip iproute2 >/dev/null 2>&1
echo "aravis pkg: $(dpkg-query -W libaravis-0.8-0)"
dpkg -L libaravis-0.8-0 | grep -i gst || echo "no gstreamer plugin in libaravis-0.8-0"
ls /usr/bin | grep arv
arv-fake-gv-camera-0.8 -i lo > /tmp/fake.log 2>&1 &
sleep 2
echo "== arv-tool-0.8 against fake"; arv-tool-0.8 -a 127.0.0.1 control DeviceVendorName DeviceModelName PixelFormat Width Height GevIEEE1588 PtpEnable 2>&1 | head -20 || true
python3 -m venv /venv && /venv/bin/pip install -q viva-genicam telegenicam numpy 2>&1 | tail -2
/venv/bin/pip list 2>/dev/null | grep -i -E "viva|tele|numpy"
echo "== viva"; timeout 60 /venv/bin/python -I /scripts/test_viva.py viva || echo "viva exit $?"
echo "== telegenic"; timeout 60 /venv/bin/python -I /scripts/test_viva.py tele || echo "tele exit $?"
echo "== gst-inspect aravissrc"; gst-inspect-1.0 aravissrc 2>&1 | grep -E -i "Version|camera-name|packet-size|features|auto|Long-name|License|Source module" | head -20
echo "== gst-launch aravissrc 5 buffers"; GST_DEBUG=0 timeout 30 gst-launch-1.0 -v aravissrc camera-name=127.0.0.1 num-buffers=5 ! fakesink 2>&1 | grep -E -i "caps =|EOS|ERROR|Execution" | head -8

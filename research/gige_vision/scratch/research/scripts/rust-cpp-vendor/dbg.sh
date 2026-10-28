export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null; apt-get install -y -qq aravis-tools-cli iproute2 >/dev/null 2>&1
arv-fake-gv-camera-0.8 --help
arv-fake-gv-camera-0.8 -i lo -d all:1 > /tmp/fake.log 2>&1 &
sleep 2; cat /tmp/fake.log | head -30
arv-tool-0.8 -a 127.0.0.1 control DeviceVendorName 2>&1 | head
arv-tool-0.8 2>&1 | head

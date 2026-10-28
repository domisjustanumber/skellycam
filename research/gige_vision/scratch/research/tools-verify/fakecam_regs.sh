set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null && apt-get install -y -qq aravis-tools aravis-tools-cli >/dev/null 2>&1
dpkg -l aravis-tools | tail -1; dpkg -L aravis-tools | grep bin/
arv-fake-gv-camera-0.8 -i 127.0.0.1 >/tmp/fake.log 2>&1 &
sleep 3; T=$(ls /usr/bin/arv-tool* | head -1); echo using $T
$T -a 127.0.0.1 control R[0x0000] R[0x0934] R[0x0954] R[0x096C] R[0x093C] R[0x0940] || true
echo "--- write test"
$T -a 127.0.0.1 control R[0x0000]=0x00020001 R[0x0934]=0x001B0067 || true
$T -a 127.0.0.1 control R[0x0000] R[0x0934] || true

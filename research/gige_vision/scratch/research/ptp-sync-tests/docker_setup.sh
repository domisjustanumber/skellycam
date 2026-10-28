set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
echo "wireshark-common wireshark-common/install-setuid boolean false" | debconf-set-selections
apt-get install -y -qq tshark aravis-tools-cli python3 iproute2 >/dev/null 2>&1
dpkg -l | awk '/tshark|aravis|libaravis/ {print $2, $3}'

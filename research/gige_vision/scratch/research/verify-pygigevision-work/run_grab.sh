set -e
cp -r /src /tmp/p && pip install -q --no-deps /tmp/p 2>/dev/null
IP=$(hostname -I | awk '{print $1}')
arv-fake-gv-camera-0.8 -i eth0 >/tmp/fake.log 2>&1 &
sleep 1
for args in "$@"; do echo "=== $args"; python -I /w/v_grab.py $args 2>&1 | grep -v WARNING | tail -12; done

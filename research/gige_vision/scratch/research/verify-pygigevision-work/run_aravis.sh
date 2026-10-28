arv-fake-gv-camera-0.8 -i eth0 >/tmp/fake.log 2>&1 &
sleep 1
/usr/bin/python3 -I /w/v_aravis.py Mono8 640 480 30 3 2>&1 | tail -3
/usr/bin/python3 -I /w/v_aravis.py Mono16 640 480 30 3 2>&1 | tail -3
/usr/bin/python3 -I /w/v_aravis.py RGB8 640 480 30 3 2>&1 | tail -3

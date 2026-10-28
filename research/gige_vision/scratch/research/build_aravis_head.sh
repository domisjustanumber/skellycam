set -e
cp -r /src/aravis /build-src && cd /build-src
git log -1 --format='HEAD %H %cd'
meson setup -Dviewer=disabled -Dgst-plugin=disabled -Ddocumentation=disabled -Dintrospection=enabled -Dtests=true build >/tmp/setup.log 2>&1 || { tail -40 /tmp/setup.log; exit 1; }
grep -i -E "packet.socket|introspection|usb" /tmp/setup.log | head
ninja -C build >/tmp/ninja.log 2>&1 || { tail -40 /tmp/ninja.log; exit 1; }
meson test -C build --print-errorlogs 2>&1 | tail -25
grep -n "ARAVIS_HAS_PACKET_SOCKET" build/src/arvfeatures.h || true
echo "=== Python capture against HEAD (Aravis-0.10 typelib) ==="
export GI_TYPELIB_PATH=/build-src/build/src LD_LIBRARY_PATH=/build-src/build/src
ls build/src/*.typelib build/src/arv-fake-gv-camera* 2>/dev/null
./build/src/arv-fake-gv-camera-0.10 -i 127.0.0.1 >/tmp/fake.log 2>&1 &
sleep 2
python3 -I /work/aravis_fake_camera_capture.py --device 127.0.0.1 --frames 100 --frame-rate 100 | grep -v "^[0-9]" || echo "exit=$?"

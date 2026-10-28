#!/bin/bash
# One camlock hold: C930e MJPG 640x480@15 (alt 8) solo x3 and C930e-first + generic 720p x3, with per-sample arrivals.
EXE="$1"; OUT="$2"; C930='vid_046d&pid_0843'; GEN='vid_4c4a&pid_4a55'
for i in 1 2 3; do "$EXE" --arrivals --seconds 6 --exposure -7 --wb 4500 --cam "$C930:MJPG:640x480@15" --out "$OUT/solo_$i.json" >/dev/null 2>&1; echo "solo_$i rc=$?"; done
for i in 1 2 3; do "$EXE" --arrivals --seconds 6 --exposure -7 --wb 4500 --stagger-ms 2500 --cam "$C930:MJPG:640x480@15" --cam "$GEN:MJPG:1280x720@30" --out "$OUT/with_gen_$i.json" >/dev/null 2>&1; echo "with_gen_$i rc=$?"; done

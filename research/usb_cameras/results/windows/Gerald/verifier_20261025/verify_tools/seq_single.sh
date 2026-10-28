#!/usr/bin/env bash
# Sequential single-camera nokhwa captures (one camera open at a time), run under ONE camlock hold (~2.5 min).
set -u
EXE="$1"; OUT="$2"
C=(--width 1280 --height 720 --seconds 15 --exposure -7 --wb 4000 --decode-every 30 --save-samples 2)
for m in "vid_1532&pid_0e05" "vid_046d&pid_085c" "vid_046d&pid_0843" "vid_4c4a&pid_4a55"; do
  "$EXE" capture --cameras "match:$m" --fps 30 "${C[@]}" --out "$OUT\single_${m//&/_}_30" | tail -1
done
"$EXE" capture --cameras "match:vid_046d&pid_085c" --fps 60 "${C[@]}" --out "$OUT\single_c922_60" | tail -1
"$EXE" capture --cameras "match:vid_046d&pid_085c" --fps 15 "${C[@]}" --out "$OUT\single_c922_15" | tail -1

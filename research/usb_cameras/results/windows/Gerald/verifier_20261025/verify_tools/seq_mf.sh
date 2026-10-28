#!/usr/bin/env bash
# Reference MF-native (converters disabled) captures, one camera at a time, under ONE camlock hold.
set -u
EXE="$1"; OUT="$2"
C=(--width 1280 --height 720 --seconds 8 --warmup 1 --exposure -7 --wb 4000 --attr-dump 3)
"$EXE" --dev "vid_046d&pid_085c" --fps 15 "${C[@]}" --out "$OUT\mf_c922_15" 2>&1 | tail -2
"$EXE" --dev "vid_046d&pid_085c" --fps 60 "${C[@]}" --out "$OUT\mf_c922_60" 2>&1 | tail -2
"$EXE" --dev "vid_046d&pid_085c" --fps 30 "${C[@]}" --out "$OUT\mf_c922_30" 2>&1 | tail -2
"$EXE" --dev "vid_046d&pid_0843" --fps 30 "${C[@]}" --out "$OUT\mf_c930e_30" 2>&1 | tail -2
"$EXE" --dev "vid_4c4a&pid_4a55" --fps 30 "${C[@]}" --out "$OUT\mf_4c4a_30" 2>&1 | tail -2
"$EXE" --dev "vid_1532&pid_0e05" --fps 30 "${C[@]}" --out "$OUT\mf_kiyo_30" 2>&1 | tail -2

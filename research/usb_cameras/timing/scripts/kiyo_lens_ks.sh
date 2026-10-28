#!/usr/bin/env bash
# KS-direct control GET probe (no MF / Frame Server / metadata) on the three cameras. Run under camlock.
# usage: bash kiyo_lens_ks.sh <out.jsonl>
E="$(dirname "$0")/../build/kiyo_ks_mf_probe.exe"
out="$1"
for d in 'vid_1532&pid_0e05' 'vid_046d&pid_085c' 'vid_046d&pid_0843'; do "$E" --dev "$d" --ks-only >> "$out"; done

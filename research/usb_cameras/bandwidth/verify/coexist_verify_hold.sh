#!/bin/bash
# Adversarial verifier, ONE camlock hold: coexist_hold.sh gen_first "8 9" then c930e_first "8"
UVC="$1"; RAW="$2"; HERE="$3"
"C:/Program Files/Git/bin/bash.exe" "$HERE/coexist_hold.sh" "$UVC" "$RAW" gen_first "8 9"
"C:/Program Files/Git/bin/bash.exe" "$HERE/coexist_hold.sh" "$UVC" "$RAW" c930e_first "8"

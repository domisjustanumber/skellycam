#!/usr/bin/env bash
# Verifier functional checks (no timing) for uncompressed_intra. ffmpeg/ffprobe 9.0.2 on PATH.
# Inputs: run mkframes.py first (writes one derived frame per format to $D). Media stays in $D.
D=C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/verify_method
cd "$D" || exit 1
echo "== 1. FFV1 coder on 12-bit (gray16le) and v4 native Bayer: packet bytes, bit-exactness, encoder log =="
for src in bayer16_quad_noiseTrue bayer_rggb16le_noiseTrue; do for lvl in 3 4; do for coder in 0 1; do
  o=c_${src}_l${lvl}_c${coder}.mkv
  log=$(ffmpeg -hide_banner -y -loglevel info -f rawvideo -pix_fmt gray16le -s 1920x1080 -i $src.raw -c:v ffv1 -level $lvl -strict experimental -slices 24 -slicecrc 1 -coder $coder -g 1 $o 2>&1 | grep -i forcing | sed 's/.*\] //')
  sz=$(ffprobe -v error -select_streams v -show_entries packet=size -of csv=p=0 $o)
  ex=$([ "$(ffmpeg -v error -i $o -f rawvideo -pix_fmt gray16le - | md5sum)" = "$(md5sum < $src.raw)" ] && echo y || echo n)
  echo "gray16le $src level=$lvl coder=$coder bytes=$sz exact=$ex log=[$log]"; rm -f $o
done; done; done
for coder in 0 1; do
  o=v4b_c$coder.mkv
  log=$(ffmpeg -hide_banner -y -loglevel info -f rawvideo -pix_fmt bayer_rggb16le -s 1920x1080 -i bayer_rggb16le_noiseTrue.raw -c:v ffv1 -level 4 -strict experimental -slices 4 -slicecrc 1 -coder $coder -g 1 $o 2>&1 | grep -i forcing | sed 's/.*\] //')
  sz=$(ffprobe -v error -select_streams v -show_entries packet=size -of csv=p=0 $o)
  ex=$([ "$(ffmpeg -v error -i $o -f rawvideo -pix_fmt bayer_rggb16le - | md5sum)" = "$(md5sum < bayer_rggb16le_noiseTrue.raw)" ] && echo y || echo n)
  echo "bayer_rggb16le native level=4 coder=$coder bytes=$sz exact=$ex log=[$log]"; rm -f $o
done
echo "== 2. Hard kill (SIGKILL -> TerminateProcess) of an ffmpeg writer after 3 s at -re 30 fps; then count readable frames =="
for spec in "utvideo:avi:-pred median" "ffvhuff:nut:-pred median" "ffv1:mkv:-level 3 -slices 4 -slicecrc 1 -g 1" "utvideo:nut:-pred median" "ffv1:avi:-level 3 -slices 4 -slicecrc 1 -g 1"; do
  IFS=: read c ext opts <<< "$spec"; o=kill_${c}.$ext; rm -f $o
  timeout -s KILL 3 ffmpeg -hide_banner -loglevel error -y -re -stream_loop -1 -f rawvideo -pix_fmt yuyv422 -s 1920x1080 -r 30 -i yuyv422_noiseTrue.raw -c:v $c $opts -pix_fmt yuv422p $o 2>/dev/null
  rc=$?; sz=$(stat -c %s $o)
  n=$(ffprobe -v error -count_frames -select_streams v -show_entries stream=nb_read_frames -of csv=p=0 $o 2>/dev/null)
  err=$(ffmpeg -v error -i $o -f null - 2>&1 | head -2 | tr '\n' ' ' | sed 's/@ 0x*[0-9a-f]*//g' | cut -c1-140)
  echo "$c.$ext rc=$rc bytes=$sz frames_read=$n first_errors=[$err]"; rm -f $o
done
# Section 4 (appended run): python -c "import numpy as np; a=np.fromfile('bayer16_quad_noiseTrue.raw','<u2'); (a<<4).astype('<u2').tofile('q_msb.raw')"
#   then encode bayer16_quad_noiseTrue.raw (default) and q_msb.raw with -bits_per_raw_sample 12 (FFV1 level 3, s24, crc, g1) and compare packet bytes.
# Section 3: same FFV1 v3 s24 settings on *_noiseTrue.raw vs *_noiseFalse.raw (mkframes.py writes both).

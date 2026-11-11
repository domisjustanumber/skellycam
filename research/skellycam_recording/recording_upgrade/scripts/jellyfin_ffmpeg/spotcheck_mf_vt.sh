#!/usr/bin/env bash
# Spot-check 2 for results/jellyfin_ffmpeg/upstream_spotcheck_mf_vt.txt (sources only; nothing is installed or run).
# Needs gh (authenticated). SRC = the folder fetch_sources.sh wrote (it holds patches/, up_allcodecs_*.c, up_vtenc_n9.0.2.c).
# Usage: bash spotcheck_mf_vt.sh <SRC dir> <out file>
set -euo pipefail
SP="${1:?SRC dir from fetch_sources.sh}"; OUT="${2:?out file}"
raw() { gh api "$1" -H "Accept: application/vnd.github.raw"; }
for f in mfenc.c mf_utils.c; do raw "repos/FFmpeg/FFmpeg/contents/libavcodec/$f?ref=n9.0.2" > "$SP/up_${f}_n9.0.2"; done
P97="$SP/patches/0097-add-misc-enhancements-to-mfenc-hw-encoder.patch"
P47="$SP/patches/0047-add-mjpeg-videotoolbox-encoder.patch"
{
echo "## upstream n9.0.2 mfenc.c + mf_utils.c: count of 'ADAPTER_LUID|MFTEnum2|hw_luid'"
grep -c -i "ADAPTER_LUID\|MFTEnum2\|hw_luid" "$SP/up_mfenc.c_n9.0.2" "$SP/up_mf_utils.c_n9.0.2" || true
echo "## upstream n9.0.2 mf_utils.c: MFT enumeration"
grep -n "MFTEnumEx\|MFT_ENUM_FLAG_HARDWARE" "$SP/up_mf_utils.c_n9.0.2"
echo "## upstream n9.0.2 mfenc.c: video encoder pix fmts"
grep -n "CODEC_PIXFMTS(AV_PIX_FMT_NV12" "$SP/up_mfenc.c_n9.0.2"
echo "## patch 0097: MFTEnum2 with adapter LUID, D3D11 input only"
grep -n "MFTEnum2 is loaded optionally\|use_hw && hw_luid && f->MFTEnum2\|ff_MFT_ENUM_ADAPTER_LUID,\|use_hw && avctx->pix_fmt == AV_PIX_FMT_D3D11\|get_luid_from_dxgi_adapter(avctx, &hw_luid)" "$P97"
echo "## patch 0047: mjpeg_videotoolbox pix fmts, allow_sw default, caps, colour ranges"
grep -n "mjpeg_pix_fmts\[\]\|AV_PIX_FMT_VIDEOTOOLBOX,\|AV_PIX_FMT_NV12,\|AV_PIX_FMT_YUV420P,\|\"allow_sw\", \"Allow software encoding\", OFFSET(allow_sw), AV_OPT_TYPE_BOOL,{\|AV_CODEC_CAP_HARDWARE\|color_ranges\|kCMVideoCodecType_JPEG" "$P47"
echo "## upstream n9.0.2 videotoolboxenc.c: kCMVideoCodecType_JPEG count"
grep -c "kCMVideoCodecType_JPEG" "$SP/up_vtenc_n9.0.2.c" || true
echo "## jellyfin builder/scripts.d Vulkan + libplacebo enable conditions at v8.1.3-2"
for p in 47-vulkan/45-vulkan-headers.sh 47-vulkan/45-vulkan-loader.sh 50-libplacebo.sh; do
  echo "-- $p"; raw "repos/jellyfin/jellyfin-ffmpeg/contents/builder/scripts.d/$p?ref=v8.1.3-2" | grep -A3 "ffbuild_enabled()\|ffbuild_configure()" | grep -v "^--$"
done
echo "## upstream allcodecs.c: Vulkan / VAAPI / MF / mjpeg_qsv encoders"
for t in n8.1.3 n9.0.2; do echo "-- $t"; grep -n "_vulkan_encoder\|_vaapi_encoder\|mjpeg_qsv_encoder\|h264_mf_encoder\|hevc_mf_encoder" "$SP/up_allcodecs_$t.c"; done
} > "$OUT"

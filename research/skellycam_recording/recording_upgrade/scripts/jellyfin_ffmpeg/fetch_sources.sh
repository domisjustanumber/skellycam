#!/usr/bin/env bash
# Re-fetch the primary sources used in results/jellyfin_ffmpeg/NOTES.md (sources only; nothing is downloaded
# from the release assets, nothing is installed or run). Needs gh (authenticated) and curl.
# Usage: bash fetch_sources.sh <empty-out-dir>
set -euo pipefail
OUT="${1:?out dir}"; mkdir -p "$OUT/patches"; cd "$OUT"
JF=repos/jellyfin/jellyfin-ffmpeg; TAG=v8.1.3-2
raw() { gh api "$1" -H "Accept: application/vnd.github.raw"; }

gh api "$JF/releases/tags/$TAG" --jq '.body' > release_$TAG.md
gh api "$JF/releases/tags/$TAG" --jq '.assets[]|[.name,.size]|@tsv' > release_assets_$TAG.tsv
gh api "$JF/releases?per_page=100" --paginate --jq '.[]|[.tag_name,.published_at,.prerelease]|@tsv' > jf_releases.tsv
for f in README.md VERSION RELEASE build.yaml debian/patches/series debian/changelog debian/rules \
         debian/jellyfin-ffmpeg8.install debian/copyright builder/README.md builder/LICENSE \
         builder/variants/defaults-gpl.sh builder/variants/default-install.sh builder/variants/defaults-mac.sh \
         builder/scripts.d/50-fdk-aac-stripped.sh builder/scripts.d/50-amf.sh builder/scripts.d/50-libvpl.sh \
         builder/scripts.d/50-ffnvcodec.sh builder/scripts.d/50-dxva.sh builder/scripts.d/50-rkmpp.sh \
         builder/scripts.d/47-vulkan/45-vulkan-loader.sh; do
  raw "$JF/contents/$f?ref=$TAG" > "$(echo "$f" | tr / _)"
done
while read -r p; do raw "$JF/contents/debian/patches/$p?ref=$TAG" > "patches/$p"; done < debian_patches_series

# Upstream FFmpeg (GitHub mirror) for comparison
for t in n8.1.3 n9.0.2; do
  raw "repos/FFmpeg/FFmpeg/contents/libavcodec/allcodecs.c?ref=$t" > up_allcodecs_$t.c
  raw "repos/FFmpeg/FFmpeg/contents/libavfilter/allfilters.c?ref=$t" > up_allfilters_$t.c
done
raw "repos/FFmpeg/FFmpeg/contents/libavcodec/bitstream_filters.c?ref=n9.0.2" > up_bsf_n9.0.2.c
raw "repos/FFmpeg/FFmpeg/contents/libavcodec/qsvenc.c?ref=n9.0.2" > up_qsvenc_n9.0.2.c
raw "repos/FFmpeg/FFmpeg/contents/libavcodec/videotoolboxenc.c?ref=n9.0.2" > up_vtenc_n9.0.2.c
raw "repos/FFmpeg/FFmpeg/contents/libavcodec/vaapi_encode_mjpeg.c?ref=n9.0.2" > up_vaapi_mjpeg_n9.0.2.c
raw "repos/FFmpeg/FFmpeg/contents/configure?ref=n8.1.3" > up_configure_n8.1.3
raw "repos/FFmpeg/FFmpeg/contents/LICENSE.md?ref=n8.1.3" > up_LICENSE_n8.1.3.md
raw "repos/FFmpeg/FFmpeg/contents/doc/demuxers.texi?ref=n9.0.2" > up_demuxers_n9.0.2.texi

# Registry names added by the patches, and whether upstream has them
grep -h -E '^\+extern const (FFCodec|FFFilter|FFBitStreamFilter)' patches/*.patch \
  | sed -E 's/.* ff_(vf_|vsrc_)?([a-z0-9_]+);/\2/' | sort -u | while read -r n; do
  a=$(cat up_allcodecs_n8.1.3.c up_allfilters_n8.1.3.c | grep -c "ff_\(vf_\|vsrc_\)\?$n;" || true)
  b=$(cat up_allcodecs_n9.0.2.c up_allfilters_n9.0.2.c up_bsf_n9.0.2.c | grep -c "ff_\(vf_\|vsrc_\)\?$n;" || true)
  echo "$n n8.1.3=$a n9.0.2=$b"
done > upstream_presence.txt

# PyAV
raw "repos/PyAV-Org/PyAV/contents/docs/overview/installation.rst?ref=v19.0.2" > pyav_installation_v19.0.2.rst
raw "repos/PyAV-Org/PyAV/contents/setup.py?ref=v19.0.2" > pyav_setup_v19.0.2.py
curl -s https://pypi.org/pypi/av/19.0.2/json > pyav_19.0.2_pypi.json

# Jellyfin docs source
for f in index intel nvidia amd apple rockchip known-issues; do
  raw "repos/jellyfin/jellyfin.org/contents/docs/general/post-install/transcoding/hardware-acceleration/$f.md" > jf_$f.md
done

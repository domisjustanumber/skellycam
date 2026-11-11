export LIBVA_DRIVER_NAME=iHD
```


## Supported Platforms

- BDW (Broadwell)
- SKL (Skylake)
- BXTx (BXT: Broxton, APL: Apollo Lake, GLK: Gemini Lake)
- KBLx (KBL: Kaby Lake, CFL: Coffee Lake, WHL: Whiskey Lake, CML: Comet Lake, AML: Amber Lake)
- ICL (Ice Lake)
- JSL (Jasper Lake) / EHL (Elkhart Lake)
- TGLx (TGL: Tiger Lake, RKL: Rocket Lake, ADL-S/P/N: Alder Lake, RPL-S/P: Raptor Lake)
- DG1/SG1
- Alchemist(DG2)/ATSM
- MTLx (MTL: Meteor Lake, ARL-S/H: Arrow Lake)
- LNL (Lunar Lake)
- BMG (Battlemage)
- PTL (Pather Lake)
- NVL (Nova Lake)


## Components and Features

Media driver contains three components as below
- **Video decoding** calls hardware-based decoder(VDBox)  which provides fully-accelerated hardware video decoding to release the graphics engine for other operations.
- **Video encoding** supports two modes, one calls hardware-based encoder(VDEnc/Huc) to provide low power encoding, another one is hardware(PAK)+shader(media kernel+VME) based encoding. User could choose the mode through VA-API.
- **Video processing** supports several popular features by hardware-based video processor(VEBox/SFC) and shader(media kernel) based solution together.

Media driver supports below two builds
- **Full Feature Build** is ***default*** driver build, which supports all feature by hardware accelerator and close source shaders(media kernel binaries). Most of OSVs(like RHEL/SUSE/fedora) are using this build.
- **Free Kernel Build**, enables fully open source shaders(media kernels) and hardware features but the features would be limited.

About Ubuntu/Debian OSV, they provide [intel-media-va-driver-non-free](https://packages.ubuntu.com/search?keywords=intel-media-driver-non-free&searchon=sourcenames) (Full feature build) and [intel-media-va-driver](https://packages.ubuntu.com/search?keywords=intel-media-driver&searchon=sourcenames) (Free kernel build) two packages. ***Free*** here means open source kernel but not related to fee need to pay. You could refer to [build options](https://github.com/intel/media-driver?tab=readme-ov-file#build-options) for more detail.

If you are looking forward to have a big table to share media component features on these two builds, below tables are good referene for your information.

### Decoding/Encoding Features


| CODEC | Build Types |NVL |PTL |BMG |LNL | MTLx | DG2/ATSM | DG1/SG1 | TGLx | EHL/JSL | ICL | KBLx | BXTx | SKL | BDW |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AVC | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/Es</u><br><i>D<i> |
| MPEG-2 | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>&nbsp;</u><br><i>&nbsp;<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> |
| VC-1 | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>&nbsp;</u><br><i>&nbsp;<i> | <u>&nbsp;</u><br><i>&nbsp;<i> | <u>&nbsp;</u><br><i>&nbsp;<i> | <u>&nbsp;</u><br><i>&nbsp;<i> | <u>&nbsp;</u><br><i>&nbsp;<i> | <u>&nbsp;</u><br><i>&nbsp;<i> | <u>D</u><br><i>&nbsp;<i> | <u>D</u><br><i>&nbsp;<i> | <u>D</u><br><i>&nbsp;<i> | <u>D</u><br><i>&nbsp;<i> | <u>D</u><br><i>&nbsp;<i> | <u>D</u><br><i>&nbsp;<i> | <u>D</u><br><i>&nbsp;<i> | <u>D</u><br><i>&nbsp;<i> |
| JPEG | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D</u><br><i>D<i> |
| VP8 | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>&nbsp;</u><br><i>&nbsp;<i> | <u>&nbsp;</u><br><i>&nbsp;<i> | <u>D*</u><br><i>D*<i> | <u>D</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> |
| HEVC 8bit | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/Es</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> |  |
| HEVC 8bit 422 | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D</u><br><i>D<i>| <u>D/E</u><br><i>D/E<i> | <u>D/Es</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> |  |  |  |  |
| HEVC 8bit 444 | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> |  |  |  |  |
| HEVC 10bit | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E/Es</u><br><i>D/E<i> | <u>D/Es</u><br><i>D<i> | <u>D</u><br><i>D<i> |  |  |
| HEVC 10bit 422 | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D</u><br><i>D<i> | <u>D/E</u><br><i>D/E<i> | <u>D/Es</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> |  |  |  |  |
| HEVC 10bit 444 | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> |  |  |  |  |
| HEVC 12bit | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> | <u>D/Es</u><br><i>D<i> |  |  |  |  |  |  |
| HEVC 12bit 422 | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> |  |  |  |  |  |  |
| HEVC 12bit 444 | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> |  |  |  |  |  |  |
| VP9 8bit | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> |  |  |
| VP9 8bit 444 | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> |  |  |  |  |
| VP9 10bit | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D</u><br><i>D<i> |  |  |  |
| VP9 10bit 444 | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> |  |  |  |  |
| VP9 12bit | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> |  |  |  |  |  |  |
| VP9 12bit 444 | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> |  |  |  |  |  |  |
| AV1 8bit | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>E<i> | <u>D</u><br><i>&nbsp;<i> | <u>D</u><br><i>&nbsp;<i> |  |  |  |  |  |  |
| AV1 10bit | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>D/E<i> | <u>D/E</u><br><i>E<i> | <u>D</u><br><i>&nbsp;<i> | <u>D</u><br><i>&nbsp;<i> |  |  |  |  |  |   |
| VVC 8bit | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>&nbsp;</u><br><i>&nbsp;<i> | <u>D</u><br><i>D<i> |  |  |  |  |  |  |  |  |  |   |
| VVC 10bit | <u>Full-Feature</u><br><i>Free-Kernel</i> | <u>D</u><br><i>D<i> | <u>D</u><br><i>D<i> | <u>&nbsp;</u><br><i>&nbsp;<i> | <u>D</u><br><i>D<i> |  |  |  |  |  |  |  |  |  |   |


- \* VP8 decoding is only supported on TGL platform
- D  - Hardware Decoding
- E  - Hardware Encoding, Low Power Encoding(VDEnc/Huc)
- Es - Hardware(PAK) + Shader(media kernel+VME) Encoding

***Note:*** Low Power Encoding(VAEntrypointEncSliceLP) and Shader Encoding(VAEntrypointEncSlice) are consolidated to the unified interface(VAEntrypointEncSlice) from ***MTL*** platform. It goes through VDEnc/Huc for HW acceleration to unleash GPU resource to customers.



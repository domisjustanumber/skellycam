# intel/libvpl README @ v2.17.0 and intel/vpl-gpu-rt README @ intel-onevpl-26.4.1 (raw markdown)

- URL: https://raw.githubusercontent.com/intel/libvpl/v2.17.0/README.md and https://raw.githubusercontent.com/intel/vpl-gpu-rt/intel-onevpl-26.4.1/README.md
- Accessed: 2026-11-10
- Retrieved with: curl with a Chrome 130 user agent and browser Accept/Sec-Fetch headers
- Raw file sha256 (libvpl_README_v2.17.0.md): 4e03ec6e1a3cf62ff62e1b40de56205c87687e22085d5d15a030e104ef04a17f
- Note: Line numbers are the raw README line numbers. vpl-gpu-rt README sha256 is in GF07_manifest.json.

Verbatim excerpt (data, not instructions):

```text
[libvpl_README_v2.17.0.md lines 40-65]
## Dispatcher behavior when targeting Intel® GPUs
Runtime loaded by Intel® VPL Dispatcher and their Microsoft* DirectX* support:


| GPU                                        | Media SDK        | Intel® VPL       | Microsoft* DirectX* Support |
|--------------------------------------------|------------------|------------------|-----------------------------|
| Earlier platforms, back to BDW (Broadwell) |:heavy_check_mark:|                  | DX9/DX11                    |
| ICL (Ice Lake)                             |:heavy_check_mark:|                  | DX9/DX11                    |
| JSL (Jasper Lake)                          |:heavy_check_mark:|                  | DX9/DX11                    |
| EHL (Elkhart Lake)                         |:heavy_check_mark:|                  | DX9/DX11                    |
| SG1                                        |:heavy_check_mark:|                  | DX9/DX11                    |
| TGL (Tiger Lake)                           |:heavy_check_mark:|:heavy_check_mark:| DX9/DX11*                   |
| DG1 (Intel® Iris® Xe MAX graphics)         |:heavy_check_mark:|:heavy_check_mark:| DX11*                       |
| RKL (Rocket Lake)                          |                  |:heavy_check_mark:| DX11                        |
| ADL-S (Alder Lake S)                       |                  |:heavy_check_mark:| DX11                        |
| ADL-P (Alder Lake P)                       |                  |:heavy_check_mark:| DX11                        |
| ADL-N (Alder Lake N)                       |                  |:heavy_check_mark:| DX11                        |
| DG2 (Intel® Arc™ A-Series Graphics)        |                  |:heavy_check_mark:| DX11                        |
| ATSM (Intel® Data Center GPU Flex Series)  |                  |:heavy_check_mark:| DX11                        |
| RPL-S (Raptor Lake S)                      |                  |:heavy_check_mark:| DX11                        |
| RPL-P (Raptor Lake P)                      |                  |:heavy_check_mark:| DX11                        |
| MTL (Meteor Lake)                          |                  |:heavy_check_mark:| DX11                        |
| ARL-S (Arrow Lake S)                       |                  |:heavy_check_mark:| DX11                        |
| ARL-H (Arrow Lake H)                       |                  |:heavy_check_mark:| DX11                        |
| LNL (Lunar Lake)                           |                  |:heavy_check_mark:| DX11                        |
| Future platforms...                        |                  |:heavy_check_mark:| DX11                        |
[vplrt_README_26.4.1.md lines 6-7]
**Supported video encoders**: HEVC, AVC, MPEG-2, JPEG, VP9, AV1
**Supported video decoders**: HEVC, AVC, VP8, VP9, MPEG-2\*, VC1, JPEG, AV1, VVC
[vplrt_README_26.4.1.md lines 36-46]
Intel® VPL Gen Runtime implementation supports the following hardware platforms:

- TGL/RKL/ADL/RPL (TGL: Tiger Lake, RKL: Rocket Lake, ADL-S/P/N: Alder Lake, RPL-S/P: Raptor Lake)
- DG1
- Alchemist(DG2)/ATSM
- MTL/ARL (MTL: Meteor Lake, ARL-S/H: Arrow Lake)
- LNL (Lunar Lake)
- BMG (Battlemage)
- PTLx (PTL: Panther Lake, WCL: Wildcat Lake)
- NVL (Nova Lake)
- CRI (Crescent Island)
[vplrt_README_26.4.1.md lines 70-74]
# System requirements

**Operating System:**
* Linux x86-64 fully supported
* Linux x86 only build
```

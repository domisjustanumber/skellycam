
## table 0

| GPU Arch / Jetson Platform | H.264/AVCHD | H.265/HEVC | VP9 | AV1 |
| Turing/GA100 | Max: 4096x4096 | Max: 8192x8192 | Max: 8192x81921 | Unsupported |
|  | Min: 48x16 | Min: 144x144 | Min: 128x128 |  |
|  | Profile: Baseline, Main, High profile up to Level 5.1 | Profile: Main profile up to Level 6.0, main10 and main12 profile | Profile: Profile 0, 10-bit and 12-bit decoding |  |
| Hopper | Max: 4096x4096 | Max: 8192x8192 | Max: 8192x8192 | Unsupported |
|  | Min: 48x16 | Min: 144x144 | Min: 128x128 |  |
|  | Profile: Baseline, Main, High profile up to Level 5.1 | Profile: Main, main10 and main12 profile up to Level 6.0, 444 chroma format support | Profile: Profile 0, 10-bit and 12-bit decoding |  |
| GA10x/AD10x | Max: 4096x4096 | Max: 8192x8192 | Max: 8192x8192 | Max: 8192x8192 |
|  | Min: 48x16 | Min: 144x144 | Min: 128x128 | Min: 128x128 |
|  | Profile: Baseline, Main, High profile up to Level 5.1 | Profile: Main, main10 and main12 profile up to Level 6.0, 444 chroma format support | Profile: Profile 0, 10-bit and 12-bit decoding | Profile: Profile 0 up to level 6.0 |
| Blackwell / Jetson Thor | Max: 8192x8192 | Max: 8192x8192 | Max: 8192x8192 | Max: 8192x8192 |
|  | Min: 48x64 | Min: 144x144 | Min: 128x128 | Min: 128x128 |
|  | Profile: Baseline, Main, High up to Level 6.2 High 10 and High 422 (exclude MBAFF) up to Level 6.2 | Profile: Main, main10, main12, Main 4:2:2/4:4:4 10/12 profile (exclude YUV400) Level up to 6.0 | Profile: Profile 0, 10-bit and 12-bit decoding | Profile: Profile 0 up to level 6.0 |

## table 1

| Application architecture | NVDECODE library |
| Windows x64 | nvcuvid.dll |
| Windows on Arm, native Arm64 | nvcuvida64.dll |
| Linux (x86_64 and aarch64) | libnvcuvid.so |

## table 2

| Format | Chroma | Bit Depth |
| cudaVideoSurfaceFormat_NV12_Opaque | 4:2:0 | 8-bit |
| cudaVideoSurfaceFormat_P016_Opaque | 4:2:0 | 10/12-bit |
| cudaVideoSurfaceFormat_NV16_Opaque | 4:2:2 | 8-bit |
| cudaVideoSurfaceFormat_P216_Opaque | 4:2:2 | 10/12-bit |
| cudaVideoSurfaceFormat_YUV444_Opaque | 4:4:4 | 8-bit |
| cudaVideoSurfaceFormat_YUV444_16Bit_Opaque | 4:4:4 | 10/12-bit |

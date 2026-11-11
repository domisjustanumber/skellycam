# AMD AMF SDK v1.5.3: encoder doc and header excerpts (verbatim, with line numbers)

Source: https://raw.githubusercontent.com/GPUOpen-LibrariesAndSDKs/AMF/v1.5.3/amf/doc/AMF_Video_Encode_API.md, .../amf/doc/AMF_Video_Encode_HEVC_API.md, .../amf/public/include/components/VideoEncoderVCE.h, .../VideoEncoderHEVC.h; fetched 2026-11-10. Tag v1.5.3 -> commit 57ee0cfb0e1a08d9041f77435653794c1b012be0 (git ls-remote; lightweight tag). Primary vendor source (AMD's own SDK repo). The runtime AMF version inside a given AMD driver is NOT VERIFIED to match these docs.

## H.264 (AMF_Video_Encode_API.md)

#### `AMF_Video_Encode_API.md` lines 1055-1071
```text
1055: `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD`
1056: 
1057: **Values:**
1058: `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_ENUM`:
1059: `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_UNKNOWN`, `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_CONSTANT_QP`, `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_CBR`, `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_PEAK_CONSTRAINED_VBR`, `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_LATENCY_CONSTRAINED_VBR`, `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_QUALITY_VBR`, `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_HIGH_QUALITY_VBR`, `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_HIGH_QUALITY_CBR`
1060: 
1061: **Default Value associated with usages:**
1062:    - Transcoding: `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_PCVBR`
1063:    - Ultra low latency: `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_LCVBR`
1064:    - Low latency: `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_PCVBR`
1065:    - Webcam: `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_CONSTANT_QP`
1066:    - HQ: `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_QVBR`/ `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_PCVBR`
1067:    - HQLL: `AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_CBR`
1068: 
1069: **Description:**
1070: Selects the rate control method:
1071:  - CQP – Constrained QP,
```

#### `AMF_Video_Encode_API.md` lines 1128-1142
```text
1128: 
1129: **Name:**
1130: `AMF_VIDEO_ENCODER_QP_I`
1131: 
1132: **Values:**
1133: `0` – `51`
1134: 
1135: **Default Value:**
1136: `22`
1137: 
1138: **Description:**
1139: Sets the constant QP for I-pictures.
1140: Remarks: Only available for CQP rate control method.
1141: 
1142: ---
```

#### `AMF_Video_Encode_API.md` lines 1400-1416
```text
1400: ---
1401: 
1402: **Name:**
1403: `AMF_VIDEO_ENCODER_IDR_PERIOD`
1404: 
1405: **Values:**
1406: `0` … `1000`
1407: 
1408: **Default Value associated with usages:**
1409:    - Transcoding: `240`
1410:    - Ultra low latency: `240`
1411:    - Low latency: `240`
1412:    - Webcam: `0`
1413:    - HQ: `240`
1414:    - HQLL: `120`
1415: 
1416: **Description:**
```

#### `AMF_Video_Encode_API.md` lines 1486-1497
```text
1486: ---
1487: 
1488: **Name:**
1489: `AMF_VIDEO_ENCODER_B_PIC_PATTERN`
1490: 
1491: **Values:**
1492: `0`, `1`, `2`, `3`
1493: 
1494: **Default Value:**
1495: `0`
1496: 
1497: **Description:**
```

#### `AMF_Video_Encode_API.md` lines 1942-1955
```text
1942: 
1943: **Name:**
1944: `AMF_VIDEO_ENCODER_FORCE_PICTURE_TYPE`
1945: 
1946: **Values:**
1947: `AMF_VIDEO_ENCODER_PICTURE_TYPE_ENUM`: `AMF_VIDEO_ENCODER_PICTURE_TYPE_NONE`, `AMF_VIDEO_ENCODER_PICTURE_TYPE_SKIP`, `AMF_VIDEO_ENCODER_PICTURE_TYPE_IDR`, `AMF_VIDEO_ENCODER_PICTURE_TYPE_I`, `AMF_VIDEO_ENCODER_PICTURE_TYPE_P`, `AMF_VIDEO_ENCODER_PICTURE_TYPE_B`
1948: 
1949: **Default Value:**
1950: `AMF_VIDEO_ENCODER_PICTURE_TYPE_NONE`
1951: 
1952: **Description:**
1953: Forces the picture type (to use this feature, set `AMF_VIDEO_ENCODER_IDR_PERIOD` to `0`) determined by the picture management with the following precedence `IDR`, `I`, `P` and `B`. Force picture type will only take effect to override type with lower precedence.
1954: `B` feature is not supported by VCE 1.0.
1955: 
```

#### `AMF_Video_Encode_API.md` lines 638-649
```text
638: **Name:**
639: `AMF_VIDEO_ENCODER_USAGE`
640: 
641: **Values:**
642: `AMF_VIDEO_ENCODER_USAGE_ENUM`: `AMF_VIDEO_ENCODER_USAGE_TRANSCONDING`, `AMF_VIDEO_ENCODER_USAGE_TRANSCODING`, `AMF_VIDEO_ENCODER_USAGE_ULTRA_LOW_LATENCY`, `AMF_VIDEO_ENCODER_USAGE_LOW_LATENCY`,
643: `AMF_VIDEO_ENCODER_USAGE_WEBCAM`, `AMF_VIDEO_ENCODER_USAGE_HIGH_QUALITY`, `AMF_VIDEO_ENCODER_USAGE_LOW_LATENCY_HIGH_QUALITY`
644: 
645: **Default Value:**
646: `N/A`
647: 
648: **Description:**
649: Selects the AMF usage (see Section 1.2).
```

## HEVC (AMF_Video_Encode_HEVC_API.md)

#### `AMF_Video_Encode_HEVC_API.md` lines 1039-1050
```text
1039: 
1040: **Name:**
1041: `AMF_VIDEO_ENCODER_HEVC_QP_I`
1042: 
1043: **Values:**
1044: `0` – `51`
1045: 
1046: **Default Value:**
1047: `26`
1048: 
1049: **Description:**
1050: Sets the constant QP for I-pictures.Remarks: Only available for CQP rate control method.
```

#### `AMF_Video_Encode_HEVC_API.md` lines 1250-1280
```text
1250: 
1251: **Name:**
1252: `AMF_VIDEO_ENCODER_HEVC_GOP_SIZE`
1253: 
1254: **Values:**
1255: `0` ... `1000`
1256: 
1257: **Default Value associated with usages:**
1258:    - Transcoding: `240`
1259:    - Ultra low latency: `300`
1260:    - Low latency: `300`
1261:    - Webcam: `0`
1262:    - HQ: `240`
1263:    - HQLL: `240`
1264: 
1265: **Description:**
1266: The period to insert IDR/CRA in fixed size mode. `0` means only insert the first IDR/CRA (infinite GOP size).
1267: 
1268: ---
1269: 
1270: **Name:**
1271: `AMF_VIDEO_ENCODER_HEVC_NUM_GOPS_PER_IDR`
1272: 
1273: **Values:**
1274: `1` – `65535`
1275: 
1276: **Default Value:**
1277: `1`
1278: 
1279: **Description:**
1280: Determines the frequency to insert IDR as start of a GOP. `0` means no IDR will be inserted except for the first picture in the sequence.
```

#### `AMF_Video_Encode_HEVC_API.md` lines 1708-1719
```text
1708: 
1709: **Name:**
1710: `AMF_VIDEO_ENCODER_HEVC_FORCE_PICTURE_TYPE`
1711: 
1712: **Values:**
1713: `AMF_VIDEO_ENCODER_HEVC_PICTURE_TYPE_ENUM`: `AMF_VIDEO_ENCODER_HEVC_PICTURE_TYPE_NONE`, `AMF_VIDEO_ENCODER_HEVC_PICTURE_TYPE_IDR`, `AMF_VIDEO_ENCODER_HEVC_PICTURE_TYPE_I`, `AMF_VIDEO_ENCODER_HEVC_PICTURE_TYPE_P`
1714: 
1715: **Default Value:**
1716: `AMF_VIDEO_ENCODER_HEVC_PICTURE_TYPE_NONE`
1717: 
1718: **Description:**
1719: Forces the picture type determined by the picture management with the following precedence `IDR`, `I` and `P`. Force picture type will only take effect to override types with lower precedence.
```

## Headers

#### `VideoEncoderVCE.h` lines 254-254
```text
254: #define AMF_VIDEO_ENCODER_QP_I                                  L"QPI"                      // amf_int64; default = 22; I-frame QP; range = 0-51
```

#### `VideoEncoderVCE.h` lines 262-266
```text
262: #define AMF_VIDEO_ENCODER_HEADER_INSERTION_SPACING              L"HeaderInsertionSpacing"   // amf_int64; default = depends on USAGE; Header Insertion Spacing; range 0-1000
263: #define AMF_VIDEO_ENCODER_B_PIC_PATTERN                         L"BPicturesPattern"         // amf_int64; default = 0; B-picture Pattern (number of B-Frames)
264: #define AMF_VIDEO_ENCODER_DE_BLOCKING_FILTER                    L"DeBlockingFilter"         // bool; default = depends on USAGE; De-blocking Filter
265: #define AMF_VIDEO_ENCODER_B_REFERENCE_ENABLE                    L"BReferenceEnable"         // bool; default = true; Enable Refrence to B-frames
266: #define AMF_VIDEO_ENCODER_IDR_PERIOD                            L"IDRPeriod"                // amf_int64; default = depends on USAGE; IDR Period in frames
```

#### `VideoEncoderHEVC.h` lines 174-175
```text
174: #define AMF_VIDEO_ENCODER_HEVC_NUM_GOPS_PER_IDR                     L"HevcGOPSPerIDR"               // amf_int64; default = 1; The frequency to insert IDR as start of a GOP. 0 means no IDR will be inserted.
175: #define AMF_VIDEO_ENCODER_HEVC_GOP_SIZE                             L"HevcGOPSize"                  // amf_int64; default = 60; GOP Size, in frames
```

#### `VideoEncoderHEVC.h` lines 234-234
```text
234: #define AMF_VIDEO_ENCODER_HEVC_QP_I                                 L"HevcQP_I"                     // amf_int64; default = 26; P-frame QP; range = 0-51
```

Note: VideoEncoderHEVC.h:234 comments `HevcQP_I` as "P-frame QP"; the HEVC doc (line 1050) says "Sets the constant QP for I-pictures." Treated as a header comment typo; the doc and FFmpeg's use (amfenc_hevc.c:523-524) agree on I-pictures.
Note: `grep -n -i "b-pic\|B pictures\|B-frame"` on AMF_Video_Encode_HEVC_API.md v1.5.3 returns nothing: the HEVC encoder doc defines no B-picture property.

# FFmpeg n9.0.2: VideoToolbox encoder excerpts (verbatim, with line numbers)

Source: https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavcodec/videotoolboxenc.c, fetched 2026-11-10 (commit 946fcce07b6dcd0331c8cc609192aeff5e1924f8). Copied by line range with awk.

#### `videotoolboxenc.c` lines 1132-1135
```c
1132: static bool vtenc_qscale_enabled(void)
1133: {
1134:     return !TARGET_OS_IPHONE && TARGET_CPU_ARM64;
1135: }
```

#### `videotoolboxenc.c` lines 1144-1149
```c
1144:     status = VTSessionSetProperty(vtctx->session, key, value);
1145:     if (status == kVTPropertyNotSupportedErr) {
1146:         av_log(avctx,
1147:                AV_LOG_INFO,
1148:                "This device does not support the %s option. Value ignored.\n",
1149:                print_option_name);
```

#### `videotoolboxenc.c` lines 1245-1281
```c
1245:     if (avctx->flags & AV_CODEC_FLAG_QSCALE && !vtenc_qscale_enabled()) {
1246:         av_log(avctx, AV_LOG_ERROR, "-q:v qscale not available for encoder. Use -b:v bitrate instead.\n");
1247:         return AVERROR_EXTERNAL;
1248:     }
1249: 
1250:     if (avctx->flags & AV_CODEC_FLAG_QSCALE || avctx->global_quality > 0) {
1251:         float factor = (avctx->flags & AV_CODEC_FLAG_QSCALE) ?
1252:                        FF_QP2LAMBDA * 100.0f : 100.0f;
1253:         Float32 quality = fminf(avctx->global_quality / factor, 1.0f);
1254:         CFNumberRef quality_num = CFNumberCreate(kCFAllocatorDefault,
1255:                                                  kCFNumberFloat32Type,
1256:                                                  &quality);
1257:         if (!quality_num) return AVERROR(ENOMEM);
1258: 
1259:         status = VTSessionSetProperty(vtctx->session,
1260:                                       kVTCompressionPropertyKey_Quality,
1261:                                       quality_num);
1262:         CFRelease(quality_num);
1263:     } else if (avctx->codec_id != AV_CODEC_ID_PRORES) {
1264:         bit_rate_num = CFNumberCreate(kCFAllocatorDefault,
1265:                                       kCFNumberSInt32Type,
1266:                                       &bit_rate);
1267:         if (!bit_rate_num) return AVERROR(ENOMEM);
1268: 
1269:         if (constant_bit_rate) {
1270:             status = VTSessionSetProperty(vtctx->session,
1271:                                           compat_keys.kVTCompressionPropertyKey_ConstantBitRate,
1272:                                           bit_rate_num);
1273:             if (status == kVTPropertyNotSupportedErr) {
1274:                 av_log(avctx, AV_LOG_ERROR, "-constant_bit_rate true is not supported by the encoder.\n");
1275:                 return AVERROR_EXTERNAL;
1276:             }
1277:         } else {
1278:             status = VTSessionSetProperty(vtctx->session,
1279:                                           kVTCompressionPropertyKey_AverageBitRate,
1280:                                           bit_rate_num);
1281:         }
```

#### `videotoolboxenc.c` lines 1379-1395
```c
1379:     if (avctx->gop_size > 0 && avctx->codec_id != AV_CODEC_ID_PRORES) {
1380:         CFNumberRef interval = CFNumberCreate(kCFAllocatorDefault,
1381:                                               kCFNumberIntType,
1382:                                               &avctx->gop_size);
1383:         if (!interval) {
1384:             return AVERROR(ENOMEM);
1385:         }
1386: 
1387:         status = VTSessionSetProperty(vtctx->session,
1388:                                       kVTCompressionPropertyKey_MaxKeyFrameInterval,
1389:                                       interval);
1390:         CFRelease(interval);
1391: 
1392:         if (status) {
1393:             av_log(avctx, AV_LOG_ERROR, "Error setting 'max key-frame interval' property: %d\n", status);
1394:             return AVERROR_EXTERNAL;
1395:         }
```

#### `videotoolboxenc.c` lines 1528-1537
```c
1528:     if (!vtctx->has_b_frames && avctx->codec_id != AV_CODEC_ID_PRORES) {
1529:         status = VTSessionSetProperty(vtctx->session,
1530:                                       kVTCompressionPropertyKey_AllowFrameReordering,
1531:                                       kCFBooleanFalse);
1532: 
1533:         if (status) {
1534:             av_log(avctx, AV_LOG_ERROR, "Error setting 'allow frame reordering' property: %d\n", status);
1535:             return AVERROR_EXTERNAL;
1536:         }
1537:     }
```

#### `videotoolboxenc.c` lines 1570-1590
```c
1570:     if (avctx->qmin >= 0) {
1571:         status = set_encoder_int_property_or_log(avctx,
1572:                                                  compat_keys.kVTCompressionPropertyKey_MinAllowedFrameQP,
1573:                                                  "qmin",
1574:                                                  avctx->qmin);
1575: 
1576:         if (status != 0) {
1577:             return status;
1578:         }
1579:     }
1580: 
1581:     if (avctx->qmax >= 0) {
1582:         status = set_encoder_int_property_or_log(avctx,
1583:                                                  compat_keys.kVTCompressionPropertyKey_MaxAllowedFrameQP,
1584:                                                  "qmax",
1585:                                                  avctx->qmax);
1586: 
1587:         if (status != 0) {
1588:             return status;
1589:         }
1590:     }
```

#### `videotoolboxenc.c` lines 1664-1670
```c
1664:         vtctx->get_param_set_func = CMVideoFormatDescriptionGetH264ParameterSetAtIndex;
1665: 
1666:         vtctx->has_b_frames = avctx->max_b_frames > 0;
1667:         if(vtctx->has_b_frames && (0xFF & vtctx->profile) == AV_PROFILE_H264_BASELINE){
1668:             av_log(avctx, AV_LOG_WARNING, "Cannot use B-frames with baseline profile. Output will not contain B-frames.\n");
1669:             vtctx->has_b_frames = 0;
1670:         }
```

#### `videotoolboxenc.c` lines 1680-1683
```c
1680:         if (!vtctx->get_param_set_func) return AVERROR(EINVAL);
1681:         if (!get_vt_hevc_profile_level(avctx, &profile_level)) return AVERROR(EINVAL);
1682:         // HEVC has b-byramid
1683:         vtctx->has_b_frames = avctx->max_b_frames > 0 ? 2 : 0;
```

#### `videotoolboxenc.c` lines 1697-1711
```c
1697: #if !TARGET_OS_IPHONE
1698:     if(vtctx->require_sw) {
1699:         CFDictionarySetValue(enc_info,
1700:                              compat_keys.kVTVideoEncoderSpecification_EnableHardwareAcceleratedVideoEncoder,
1701:                              kCFBooleanFalse);
1702:     } else if (!vtctx->allow_sw) {
1703:         CFDictionarySetValue(enc_info,
1704:                              compat_keys.kVTVideoEncoderSpecification_RequireHardwareAcceleratedVideoEncoder,
1705:                              kCFBooleanTrue);
1706:     } else {
1707:         CFDictionarySetValue(enc_info,
1708:                              compat_keys.kVTVideoEncoderSpecification_EnableHardwareAcceleratedVideoEncoder,
1709:                              kCFBooleanTrue);
1710:     }
1711: #endif
```

#### `videotoolboxenc.c` lines 1789-1804
```c
1789: 
1790:     status = VTSessionCopyProperty(vtctx->session,
1791:                                    kVTCompressionPropertyKey_AllowFrameReordering,
1792:                                    kCFAllocatorDefault,
1793:                                    &has_b_frames_cfbool);
1794: 
1795:     if (!status && has_b_frames_cfbool) {
1796:         //Some devices don't output B-frames for main profile, even if requested.
1797:         // HEVC has b-pyramid
1798:         if (CFBooleanGetValue(has_b_frames_cfbool))
1799:             vtctx->has_b_frames = avctx->codec_id == AV_CODEC_ID_HEVC ? 2 : 1;
1800:         else
1801:             vtctx->has_b_frames = 0;
1802:         CFRelease(has_b_frames_cfbool);
1803:     }
1804:     avctx->has_b_frames = vtctx->has_b_frames;
```

#### `videotoolboxenc.c` lines 2458-2470
```c
2458: static int create_encoder_dict_h264(const AVFrame *frame,
2459:                                     CFDictionaryRef* dict_out)
2460: {
2461:     CFDictionaryRef dict = NULL;
2462:     if (frame->pict_type == AV_PICTURE_TYPE_I) {
2463:         const void *keys[] = { kVTEncodeFrameOptionKey_ForceKeyFrame };
2464:         const void *vals[] = { kCFBooleanTrue };
2465: 
2466:         dict = CFDictionaryCreate(NULL, keys, vals, 1, NULL, NULL);
2467:         if(!dict) return AVERROR(ENOMEM);
2468:     }
2469: 
2470:     *dict_out = dict;
```

#### `videotoolboxenc.c` lines 2776-2778
```c
2776:     { "allow_sw", "Allow software encoding", OFFSET(allow_sw), AV_OPT_TYPE_BOOL, \
2777:         { .i64 = 0 }, 0, 1, VE }, \
2778:     { "require_sw", "Require software encoding", OFFSET(require_sw), AV_OPT_TYPE_BOOL, \
```

#### `videotoolboxenc.c` lines 2831-2831
```c
2831:     { "constant_bit_rate", "Require constant bit rate (macOS 13 or newer)", OFFSET(constant_bit_rate), AV_OPT_TYPE_BOOL, { .i64 = 0 }, 0, 1, VE },
```

#### `videotoolboxenc.c` lines 2838-2843
```c
2838:         {"b",    "0"},
2839:         {"qmin", "-1"},
2840:         {"qmax", "-1"},
2841:         {NULL},
2842: };
2843: 
```

Grep results (2026-11-10): `grep -c "i_quant_factor\|i_quant_offset"` = 0; `grep -c "BaseFrameQP\|AllowTemporalCompression"` = 0.

## Additional ranges cited in GF06_amf_vt_intra.md

#### `videotoolboxenc.c` lines 1563-1568
```c
1563:     if ((avctx->flags & AV_CODEC_FLAG_CLOSED_GOP) != 0) {
1564:         set_encoder_property_or_log(avctx,
1565:                                     compat_keys.kVTCompressionPropertyKey_AllowOpenGOP,
1566:                                     "AllowOpenGop",
1567:                                     kCFBooleanFalse);
1568:     }
```

#### `videotoolboxenc.c` lines 1809-1833
```c
1809: static void vtenc_get_frame_info(CMSampleBufferRef buffer, bool *is_key_frame)
1810: {
1811:     CFArrayRef      attachments;
1812:     CFDictionaryRef attachment;
1813:     CFBooleanRef    not_sync;
1814:     CFIndex         len;
1815: 
1816:     attachments = CMSampleBufferGetSampleAttachmentsArray(buffer, false);
1817:     len = !attachments ? 0 : CFArrayGetCount(attachments);
1818: 
1819:     if (!len) {
1820:         *is_key_frame = true;
1821:         return;
1822:     }
1823: 
1824:     attachment = CFArrayGetValueAtIndex(attachments, 0);
1825: 
1826:     if (CFDictionaryGetValueIfPresent(attachment,
1827:                                       kCMSampleAttachmentKey_NotSync,
1828:                                       (const void **)&not_sync))
1829:     {
1830:         *is_key_frame = !CFBooleanGetValue(not_sync);
1831:     } else {
1832:         *is_key_frame = true;
1833:     }
```

#### `videotoolboxenc.c` lines 2490-2494
```c
2490:         goto out;
2491: 
2492:     status = create_encoder_dict_h264(frame, &frame_dict);
2493:     if (status)
2494:         goto out;
```

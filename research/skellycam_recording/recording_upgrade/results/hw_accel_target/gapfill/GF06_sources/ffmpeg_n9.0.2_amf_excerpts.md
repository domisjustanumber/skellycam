# FFmpeg n9.0.2: AMF encoder excerpts (verbatim, with line numbers)

Source: https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavcodec/<file>, fetched 2026-11-10. Tag n9.0.2 = tag object ce8f11b9fac4cd7ccfb41ca7c01bc17f5cda8cc3, commit 946fcce07b6dcd0331c8cc609192aeff5e1924f8 (git ls-remote). sha256 in FETCH_MANIFEST.txt. Data only; excerpts are copied by line range with awk, not retyped.

#### `amfenc_h264.c` lines 85-94
```c
85:     { "rc",             "Rate Control Method",                  OFFSET(rate_control_mode), AV_OPT_TYPE_INT,   { .i64 = AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_UNKNOWN }, AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_UNKNOWN, AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_HIGH_QUALITY_CBR, VE, .unit = "rc" },
86:     { "cqp",            "Constant Quantization Parameter",      0,                         AV_OPT_TYPE_CONST, { .i64 = AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_CONSTANT_QP             }, 0, 0, VE, .unit = "rc" },
87:     { "cbr",            "Constant Bitrate",                     0,                         AV_OPT_TYPE_CONST, { .i64 = AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_CBR                     }, 0, 0, VE, .unit = "rc" },
88:     { "vbr_peak",       "Peak Constrained Variable Bitrate",     0,                         AV_OPT_TYPE_CONST, { .i64 = AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_PEAK_CONSTRAINED_VBR    }, 0, 0, VE, .unit = "rc" },
89:     { "vbr_latency",    "Latency Constrained Variable Bitrate", 0,                         AV_OPT_TYPE_CONST, { .i64 = AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_LATENCY_CONSTRAINED_VBR }, 0, 0, VE, .unit = "rc" },
90:     { "qvbr",           "Quality Variable Bitrate",             0,                         AV_OPT_TYPE_CONST, { .i64 = AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_QUALITY_VBR             }, 0, 0, VE, .unit = "rc" },
91:     { "hqvbr",          "High Quality Variable Bitrate",        0,                         AV_OPT_TYPE_CONST, { .i64 = AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_HIGH_QUALITY_VBR        }, 0, 0, VE, .unit = "rc" },
92:     { "hqcbr",          "High Quality Constant Bitrate",        0,                         AV_OPT_TYPE_CONST, { .i64 = AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_HIGH_QUALITY_CBR        }, 0, 0, VE, .unit = "rc" },
93: 
94:     { "qvbr_quality_level",     "Sets the QVBR quality level",  OFFSET(qvbr_quality_level),AV_OPT_TYPE_INT,   { .i64 = -1 }, -1, 51, VE },
```

#### `amfenc_h264.c` lines 103-105
```c
103:     { "qp_i",           "Quantization Parameter for I-Frame",   OFFSET(qp_i),               AV_OPT_TYPE_INT, { .i64 = -1 }, -1, 51, VE },
104:     { "qp_p",           "Quantization Parameter for P-Frame",   OFFSET(qp_p),               AV_OPT_TYPE_INT, { .i64 = -1 }, -1, 51, VE },
105:     { "qp_b",           "Quantization Parameter for B-Frame",   OFFSET(qp_b),               AV_OPT_TYPE_INT, { .i64 = -1 }, -1, 51, VE },
```

#### `amfenc_h264.c` lines 114-114
```c
114:     { "header_spacing", "Header Insertion Spacing",             OFFSET(header_spacing),     AV_OPT_TYPE_INT, { .i64 = -1 }, -1, 1000, VE },
```

#### `amfenc_h264.c` lines 125-126
```c
125:     { "max_b_frames",   "Maximum number of consecutive B Pictures", OFFSET(max_consecutive_b_frames), AV_OPT_TYPE_INT, { .i64 = -1 }, -1, 3, VE },
126:     { "bf",             "B Picture Pattern",                        OFFSET(max_b_frames),             AV_OPT_TYPE_INT, { .i64 = -1 }, -1, 3, VE },
```

#### `amfenc_h264.c` lines 142-142
```c
142:     { "forced_idr",     "Force I frames to be IDR frames",      OFFSET(forced_idr)   , AV_OPT_TYPE_BOOL,  { .i64 = 0  }, 0, 1, VE },
```

#### `amfenc_h264.c` lines 298-310
```c
298:     // autodetect rate control method
299:     if (ctx->rate_control_mode == AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_UNKNOWN) {
300:         if (ctx->qp_i != -1 || ctx->qp_p != -1 || ctx->qp_b != -1) {
301:             ctx->rate_control_mode = AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_CONSTANT_QP;
302:             av_log(ctx, AV_LOG_DEBUG, "Rate control turned to CQP\n");
303:         } else if (avctx->bit_rate > 0 && avctx->rc_max_rate == avctx->bit_rate) {
304:             ctx->rate_control_mode = AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_CBR;
305:             av_log(ctx, AV_LOG_DEBUG, "Rate control turned to CBR\n");
306:         } else {
307:             ctx->rate_control_mode = AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_PEAK_CONSTRAINED_VBR;
308:             av_log(ctx, AV_LOG_DEBUG, "Rate control turned to Peak VBR\n");
309:         }
310:     }
```

#### `amfenc_h264.c` lines 362-382
```c
362:     // QP Minimum / Maximum
363:     if (ctx->rate_control_mode == AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_CONSTANT_QP) {
364:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_MIN_QP, 0);
365:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_MAX_QP, 51);
366:     } else {
367:         if (avctx->qmin != -1) {
368:             int qval = avctx->qmin > 51 ? 51 : avctx->qmin;
369:             AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_MIN_QP, qval);
370:         }
371:         if (avctx->qmax != -1) {
372:             int qval = avctx->qmax > 51 ? 51 : avctx->qmax;
373:             AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_MAX_QP, qval);
374:         }
375:     }
376:     // QP Values
377:     if (ctx->qp_i != -1)
378:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_QP_I, ctx->qp_i);
379:     if (ctx->qp_p != -1)
380:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_QP_P, ctx->qp_p);
381:     if (ctx->qp_b != -1)
382:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_QP_B, ctx->qp_b);
```

#### `amfenc_h264.c` lines 477-480
```c
477:     AMFVariantStruct    is_adaptive_b_frames = { 0 };
478:     res = ctx->encoder->pVtbl->GetProperty(ctx->encoder, AMF_VIDEO_ENCODER_ADAPTIVE_MINIGOP, &is_adaptive_b_frames);
479:     if (ctx->max_consecutive_b_frames != -1 || ctx->max_b_frames != -1 || is_adaptive_b_frames.boolValue == true) {
480: 
```

#### `amfenc_h264.c` lines 503-513
```c
503:                     else {
504:                         if (ctx->max_b_frames != -1) {
505:                             //in case user sets B-frames
506:                             AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_B_PIC_PATTERN, ctx->max_b_frames);
507:                             if (res != AMF_OK) {
508:                                 res = ctx->encoder->pVtbl->GetProperty(ctx->encoder, AMF_VIDEO_ENCODER_B_PIC_PATTERN, &var);
509:                                 av_log(ctx, AV_LOG_WARNING, "B-frames=%d is not supported by this GPU, switched to %d\n", ctx->max_b_frames, (int)var.int64Value);
510:                                 ctx->max_b_frames = (int)var.int64Value;
511:                             }
512:                             AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_MAX_CONSECUTIVE_BPICTURES, ctx->max_b_frames);
513:                         }
```

#### `amfenc_h264.c` lines 573-581
```c
573:     // Keyframe Interval
574:     if (avctx->gop_size != -1) {
575:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_IDR_PERIOD, avctx->gop_size);
576:     }
577: 
578:     // Header Insertion Spacing
579:     if (ctx->header_spacing >= 0)
580:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEADER_INSERTION_SPACING, ctx->header_spacing);
581: 
```

#### `amfenc_h264.c` lines 632-641
```c
632: static const FFCodecDefault defaults[] = {
633:     { "refs",       "-1"  },
634:     { "aspect",     "0"   },
635:     { "qmin",       "-1"  },
636:     { "qmax",       "-1"  },
637:     { "b",          "0"   },
638:     { "g",          "-1"  },
639:     { "slices",     "1"   },
640:     { "flags",      "+loop"},
641:     { NULL                },
```

#### `amfenc_hevc.c` lines 78-79
```c
78:     { "rc",             "Set the rate control mode",        OFFSET(rate_control_mode), AV_OPT_TYPE_INT, { .i64 = AMF_VIDEO_ENCODER_HEVC_RATE_CONTROL_METHOD_UNKNOWN }, AMF_VIDEO_ENCODER_HEVC_RATE_CONTROL_METHOD_UNKNOWN, AMF_VIDEO_ENCODER_HEVC_RATE_CONTROL_METHOD_HIGH_QUALITY_CBR, VE, .unit = "rc" },
79:     { "cqp",            "Constant Quantization Parameter",      0, AV_OPT_TYPE_CONST, { .i64 = AMF_VIDEO_ENCODER_HEVC_RATE_CONTROL_METHOD_CONSTANT_QP             }, 0, 0, VE, .unit = "rc" },
```

#### `amfenc_hevc.c` lines 89-92
```c
89:     { "header_insertion_mode",        "Set header insertion mode", OFFSET(header_insertion_mode),      AV_OPT_TYPE_INT,{ .i64 = -1 }, -1, AMF_VIDEO_ENCODER_HEVC_HEADER_INSERTION_MODE_IDR_ALIGNED, VE, .unit = "hdrmode" },
90:     { "none",           "", 0, AV_OPT_TYPE_CONST, { .i64 = AMF_VIDEO_ENCODER_HEVC_HEADER_INSERTION_MODE_NONE        }, 0, 0, VE, .unit = "hdrmode" },
91:     { "gop",            "", 0, AV_OPT_TYPE_CONST, { .i64 = AMF_VIDEO_ENCODER_HEVC_HEADER_INSERTION_MODE_GOP_ALIGNED }, 0, 0, VE, .unit = "hdrmode" },
92:     { "idr",            "", 0, AV_OPT_TYPE_CONST, { .i64 = AMF_VIDEO_ENCODER_HEVC_HEADER_INSERTION_MODE_IDR_ALIGNED }, 0, 0, VE, .unit = "hdrmode" },
```

#### `amfenc_hevc.c` lines 97-97
```c
97:     { "gops_per_idr",   "GOPs per IDR 0-no IDR will be inserted",   OFFSET(gops_per_idr),  AV_OPT_TYPE_INT,  { .i64 = 1  },  0, INT_MAX, VE },
```

#### `amfenc_hevc.c` lines 103-108
```c
103:     { "min_qp_i",       "min quantization parameter for I-frame",   OFFSET(min_qp_i),      AV_OPT_TYPE_INT, { .i64 = -1  }, -1, 51, VE },
104:     { "max_qp_i",       "max quantization parameter for I-frame",   OFFSET(max_qp_i),      AV_OPT_TYPE_INT, { .i64 = -1  }, -1, 51, VE },
105:     { "min_qp_p",       "min quantization parameter for P-frame",   OFFSET(min_qp_p),      AV_OPT_TYPE_INT, { .i64 = -1  }, -1, 51, VE },
106:     { "max_qp_p",       "max quantization parameter for P-frame",   OFFSET(max_qp_p),      AV_OPT_TYPE_INT, { .i64 = -1  }, -1, 51, VE },
107:     { "qp_p",           "quantization parameter for P-frame",       OFFSET(qp_p),          AV_OPT_TYPE_INT, { .i64 = -1  }, -1, 51, VE },
108:     { "qp_i",           "quantization parameter for I-frame",       OFFSET(qp_i),          AV_OPT_TYPE_INT, { .i64 = -1  }, -1, 51, VE },
```

#### `amfenc_hevc.c` lines 113-113
```c
113:     { "forced_idr",     "Force I frames to be IDR frames",          OFFSET(forced_idr)    ,AV_OPT_TYPE_BOOL,{ .i64 = 0  }, 0, 1, VE },
```

#### `amfenc_hevc.c` lines 297-301
```c
297:     // Picture control properties
298:     AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_NUM_GOPS_PER_IDR, ctx->gops_per_idr);
299:     if (avctx->gop_size != -1) {
300:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_GOP_SIZE, avctx->gop_size);
301:     }
```

#### `amfenc_hevc.c` lines 312-319
```c
312:     // autodetect rate control method
313:     if (ctx->rate_control_mode == AMF_VIDEO_ENCODER_HEVC_RATE_CONTROL_METHOD_UNKNOWN) {
314:         if (ctx->min_qp_i != -1 || ctx->max_qp_i != -1 ||
315:             ctx->min_qp_p != -1 || ctx->max_qp_p != -1 ||
316:             ctx->qp_i !=-1 || ctx->qp_p != -1) {
317:             ctx->rate_control_mode = AMF_VIDEO_ENCODER_HEVC_RATE_CONTROL_METHOD_CONSTANT_QP;
318:             av_log(ctx, AV_LOG_DEBUG, "Rate control turned to CQP\n");
319:         } else if (avctx->bit_rate > 0 && avctx->rc_max_rate == avctx->bit_rate) {
```

#### `amfenc_hevc.c` lines 494-525
```c
494: 
495:     if (ctx->min_qp_i != -1) {
496:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_MIN_QP_I, ctx->min_qp_i);
497:     } else if (avctx->qmin != -1) {
498:         int qval = avctx->qmin > 51 ? 51 : avctx->qmin;
499:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_MIN_QP_I, qval);
500:     }
501:     if (ctx->max_qp_i != -1) {
502:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_MAX_QP_I, ctx->max_qp_i);
503:     } else if (avctx->qmax != -1) {
504:         int qval = avctx->qmax > 51 ? 51 : avctx->qmax;
505:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_MAX_QP_I, qval);
506:     }
507:     if (ctx->min_qp_p != -1) {
508:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_MIN_QP_P, ctx->min_qp_p);
509:     } else if (avctx->qmin != -1) {
510:         int qval = avctx->qmin > 51 ? 51 : avctx->qmin;
511:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_MIN_QP_P, qval);
512:     }
513:     if (ctx->max_qp_p != -1) {
514:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_MAX_QP_P, ctx->max_qp_p);
515:     } else if (avctx->qmax != -1) {
516:         int qval = avctx->qmax > 51 ? 51 : avctx->qmax;
517:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_MAX_QP_P, qval);
518:     }
519: 
520:     if (ctx->qp_p != -1) {
521:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_QP_P, ctx->qp_p);
522:     }
523:     if (ctx->qp_i != -1) {
524:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_QP_I, ctx->qp_i);
525:     }
```

#### `amfenc_hevc.c` lines 560-569
```c
560: static const FFCodecDefault defaults[] = {
561:     { "refs",       "-1"  },
562:     { "aspect",     "0"   },
563:     { "b",          "0"   },
564:     { "g",          "-1"  },
565:     { "slices",     "1"   },
566:     { "qmin",       "-1"  },
567:     { "qmax",       "-1"  },
568:     { "flags",      "+loop"},
569:     { NULL                },
```

#### `amfenc.c` lines 208-228
```c
208:     switch (avctx->codec->id) {
209:     case AV_CODEC_ID_H264:
210:         buffer->pVtbl->GetProperty(buffer, AMF_VIDEO_ENCODER_OUTPUT_DATA_TYPE, &var);
211:         pkt->flags |= AV_PKT_FLAG_KEY * (var.int64Value == AMF_VIDEO_ENCODER_OUTPUT_DATA_TYPE_IDR);
212:         pict_type = var.int64Value == AMF_VIDEO_ENCODER_OUTPUT_DATA_TYPE_IDR ? AV_PICTURE_TYPE_I :
213:                     var.int64Value == AMF_VIDEO_ENCODER_OUTPUT_DATA_TYPE_I ? AV_PICTURE_TYPE_I :
214:                     var.int64Value == AMF_VIDEO_ENCODER_OUTPUT_DATA_TYPE_P ? AV_PICTURE_TYPE_P :
215:                     var.int64Value == AMF_VIDEO_ENCODER_OUTPUT_DATA_TYPE_B ? AV_PICTURE_TYPE_B : 0;
216: 
217:         var.int64Value = -1;
218:         if ((buffer->pVtbl->GetProperty(buffer, AMF_VIDEO_ENCODER_STATISTIC_AVERAGE_QP, &var)) == AMF_OK) {
219:             average_qp = FFMAX((int)var.int64Value, -1);
220:         }
221:         break;
222:     case AV_CODEC_ID_HEVC:
223:         buffer->pVtbl->GetProperty(buffer, AMF_VIDEO_ENCODER_HEVC_OUTPUT_DATA_TYPE, &var);
224:         pkt->flags |= AV_PKT_FLAG_KEY * (var.int64Value == AMF_VIDEO_ENCODER_HEVC_OUTPUT_DATA_TYPE_IDR);
225:         pict_type = var.int64Value == AMF_VIDEO_ENCODER_HEVC_OUTPUT_DATA_TYPE_IDR ? AV_PICTURE_TYPE_I :
226:                     var.int64Value == AMF_VIDEO_ENCODER_HEVC_OUTPUT_DATA_TYPE_I ? AV_PICTURE_TYPE_I :
227:                     var.int64Value == AMF_VIDEO_ENCODER_HEVC_OUTPUT_DATA_TYPE_P ? AV_PICTURE_TYPE_P : 0;
228: 
```

#### `amfenc.c` lines 476-512
```c
476:     switch (avctx->codec->id) {
477:     case AV_CODEC_ID_H264:
478:         AMF_ASSIGN_PROPERTY_BOOL(res, surface, AMF_VIDEO_ENCODER_STATISTICS_FEEDBACK, 1);
479:         AMF_ASSIGN_PROPERTY_INT64(res, surface, AMF_VIDEO_ENCODER_INSERT_AUD, !!ctx->aud);
480:         switch (frame->pict_type) {
481:         case AV_PICTURE_TYPE_I:
482:             if (ctx->forced_idr) {
483:                 AMF_ASSIGN_PROPERTY_INT64(res, surface, AMF_VIDEO_ENCODER_INSERT_SPS, 1);
484:                 AMF_ASSIGN_PROPERTY_INT64(res, surface, AMF_VIDEO_ENCODER_INSERT_PPS, 1);
485:                 AMF_ASSIGN_PROPERTY_INT64(res, surface, AMF_VIDEO_ENCODER_FORCE_PICTURE_TYPE, AMF_VIDEO_ENCODER_PICTURE_TYPE_IDR);
486:             } else {
487:                 AMF_ASSIGN_PROPERTY_INT64(res, surface, AMF_VIDEO_ENCODER_FORCE_PICTURE_TYPE, AMF_VIDEO_ENCODER_PICTURE_TYPE_I);
488:             }
489:             break;
490:         case AV_PICTURE_TYPE_P:
491:             AMF_ASSIGN_PROPERTY_INT64(res, surface, AMF_VIDEO_ENCODER_FORCE_PICTURE_TYPE, AMF_VIDEO_ENCODER_PICTURE_TYPE_P);
492:             break;
493:         case AV_PICTURE_TYPE_B:
494:             AMF_ASSIGN_PROPERTY_INT64(res, surface, AMF_VIDEO_ENCODER_FORCE_PICTURE_TYPE, AMF_VIDEO_ENCODER_PICTURE_TYPE_B);
495:             break;
496:         }
497:         break;
498:     case AV_CODEC_ID_HEVC:
499:         AMF_ASSIGN_PROPERTY_BOOL(res, surface, AMF_VIDEO_ENCODER_HEVC_STATISTICS_FEEDBACK, 1);
500:         AMF_ASSIGN_PROPERTY_INT64(res, surface, AMF_VIDEO_ENCODER_HEVC_INSERT_AUD, !!ctx->aud);
501:         switch (frame->pict_type) {
502:         case AV_PICTURE_TYPE_I:
503:             if (ctx->forced_idr) {
504:                 AMF_ASSIGN_PROPERTY_INT64(res, surface, AMF_VIDEO_ENCODER_HEVC_INSERT_HEADER, 1);
505:                 AMF_ASSIGN_PROPERTY_INT64(res, surface, AMF_VIDEO_ENCODER_HEVC_FORCE_PICTURE_TYPE, AMF_VIDEO_ENCODER_HEVC_PICTURE_TYPE_IDR);
506:             } else {
507:                 AMF_ASSIGN_PROPERTY_INT64(res, surface, AMF_VIDEO_ENCODER_HEVC_FORCE_PICTURE_TYPE, AMF_VIDEO_ENCODER_HEVC_PICTURE_TYPE_I);
508:             }
509:             break;
510:         case AV_PICTURE_TYPE_P:
511:             AMF_ASSIGN_PROPERTY_INT64(res, surface, AMF_VIDEO_ENCODER_HEVC_FORCE_PICTURE_TYPE, AMF_VIDEO_ENCODER_HEVC_PICTURE_TYPE_P);
512:             break;
```

#### `amfenc.h` lines 99-106
```c
99:     int                 max_b_frames;
100:     int                 qvbr_quality_level;
101:     int                 hw_high_motion_quality_boost;
102:     int                 forced_idr;
103: 
104:     // HEVC - specific options
105: 
106:     int                 gops_per_idr;
```

Grep result (2026-11-10): `grep -c "i_quant_factor\|i_quant_offset"` returns 0 for amfenc.c, amfenc.h, amfenc_h264.c and amfenc_hevc.c.

## Additional ranges cited in GF06_amf_vt_intra.md

#### `amfenc_h264.c` lines 312-330
```c
312:     if (ctx->rate_control_mode == AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_CONSTANT_QP) {
313:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_PREENCODE_ENABLE, AMF_VIDEO_ENCODER_PREENCODE_DISABLED);
314:         if (ctx->preencode != -1) {
315:             if (ctx->preencode) {
316:                 av_log(ctx, AV_LOG_WARNING, "Preencode is not supported by cqp Rate Control Method, automatically disabled\n");
317:             }
318:         }
319:     }
320:     else {
321:         if (ctx->preencode != -1) {
322:             AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_PREENCODE_ENABLE, ctx->preencode);
323:         }
324:     }
325: 
326:     if (ctx->rate_control_mode == AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_QUALITY_VBR) {
327:         if (ctx->qvbr_quality_level != -1) {
328:             AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_QVBR_QUALITY_LEVEL, ctx->qvbr_quality_level);
329:         }
330:     }
```

#### `amfenc_h264.c` lines 539-547
```c
539:     if (ctx->rate_control_mode == AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_CONSTANT_QP) {
540:         AMF_ASSIGN_PROPERTY_BOOL(res, ctx->encoder, AMF_VIDEO_ENCODER_ENABLE_VBAQ, 0);
541:         if (ctx->enable_vbaq)
542:             av_log(ctx, AV_LOG_WARNING, "VBAQ is not supported by cqp Rate Control Method, automatically disabled\n");
543:     } else {
544:         if (ctx->enable_vbaq != -1) {
545:             AMF_ASSIGN_PROPERTY_BOOL(res, ctx->encoder, AMF_VIDEO_ENCODER_ENABLE_VBAQ, !!ctx->enable_vbaq);
546:         }
547:     }
```

#### `amfenc_hevc.c` lines 345-362
```c
345:     if (ctx->rate_control_mode == AMF_VIDEO_ENCODER_HEVC_RATE_CONTROL_METHOD_CONSTANT_QP) {
346:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_PREENCODE_ENABLE, 0);
347:         if (ctx->preencode != -1) {
348:             if (ctx->preencode) {
349:                 av_log(ctx, AV_LOG_WARNING, "Preencode is not supported by cqp Rate Control Method, automatically disabled\n");
350:             }
351:         }
352:     }
353:     else {
354:         if (ctx->preencode != -1) {
355:             AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_PREENCODE_ENABLE, ctx->preencode);
356:         }
357:     }
358: 
359:     if (ctx->rate_control_mode == AMF_VIDEO_ENCODER_HEVC_RATE_CONTROL_METHOD_QUALITY_VBR) {
360:         if (ctx->qvbr_quality_level != -1) {
361:             AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_QVBR_QUALITY_LEVEL, ctx->qvbr_quality_level);
362:         }
```

#### `amfenc_hevc.c` lines 382-389
```c
382:     if (ctx->rate_control_mode == AMF_VIDEO_ENCODER_HEVC_RATE_CONTROL_METHOD_CONSTANT_QP) {
383:         AMF_ASSIGN_PROPERTY_BOOL(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_ENABLE_VBAQ, false);
384:         if (ctx->enable_vbaq)
385:             av_log(ctx, AV_LOG_WARNING, "VBAQ is not supported by cqp Rate Control Method, automatically disabled\n");
386:     } else {
387:         if (ctx->enable_vbaq != -1) {
388:             AMF_ASSIGN_PROPERTY_BOOL(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_ENABLE_VBAQ, !!ctx->enable_vbaq);
389:         }
```

#### `amfenc_h264.c` lines 222-226
```c
222: 
223:     // init static parameters
224:     if (ctx->usage != -1) {
225:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_USAGE, ctx->usage);
226:     }
```

#### `amfenc_hevc.c` lines 193-197
```c
193: 
194:     // init static parameters
195:     if (ctx->usage != -1) {
196:         AMF_ASSIGN_PROPERTY_INT64(res, ctx->encoder, AMF_VIDEO_ENCODER_HEVC_USAGE, ctx->usage);
197:     }
```

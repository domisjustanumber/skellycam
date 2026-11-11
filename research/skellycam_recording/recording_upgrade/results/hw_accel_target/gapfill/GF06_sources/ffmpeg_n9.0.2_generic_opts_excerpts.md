# FFmpeg n9.0.2: generic option handling and the NVENC/QSV contrast (verbatim, with line numbers)

Source: https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/<path>, fetched 2026-11-10 (commit 946fcce07b6dcd0331c8cc609192aeff5e1924f8).

#### `options_table.h` lines 96-96
```c
96: {"g", "set the group of picture (GOP) size", OFFSET(gop_size), AV_OPT_TYPE_INT, {.i64 = 12 }, INT_MIN, INT_MAX, V|E},
```

#### `options_table.h` lines 106-109
```c
106: {"qmin", "minimum video quantizer scale (VBR)", OFFSET(qmin), AV_OPT_TYPE_INT, {.i64 = 2 }, -1, 69, V|E},
107: {"qmax", "maximum video quantizer scale (VBR)", OFFSET(qmax), AV_OPT_TYPE_INT, {.i64 = 31 }, -1, 1024, V|E},
108: {"qdiff", "maximum difference between the quantizer scales (VBR)", OFFSET(max_qdiff), AV_OPT_TYPE_INT, {.i64 = 3 }, INT_MIN, INT_MAX, V|E},
109: {"bf", "set maximum number of B-frames between non-B-frames", OFFSET(max_b_frames), AV_OPT_TYPE_INT, {.i64 = DEFAULT }, -1, INT_MAX, V|E},
```

#### `options_table.h` lines 151-152
```c
151: {"i_qfactor", "QP factor between P- and I-frames", OFFSET(i_quant_factor), AV_OPT_TYPE_FLOAT, {.dbl = -0.8 }, -FLT_MAX, FLT_MAX, V|E},
152: {"i_qoffset", "QP offset between P- and I-frames", OFFSET(i_quant_offset), AV_OPT_TYPE_FLOAT, {.dbl = 0.0 }, -FLT_MAX, FLT_MAX, V|E},
```

#### `options_table.h` lines 209-209
```c
209: {"global_quality", NULL, OFFSET(global_quality), AV_OPT_TYPE_INT, {.i64 = DEFAULT }, INT_MIN, INT_MAX, V|A|E},
```

#### `avcodec.c` lines 226-228
```c
226:     ret = av_opt_set_dict2(avctx, options, AV_OPT_SEARCH_CHILDREN);
227:     if (ret < 0)
228:         goto free_and_end;
```

#### `opt.c` lines 2004-2019
```c
2004:     if (search_flags & AV_OPT_SEARCH_CHILDREN) {
2005:         if (search_flags & AV_OPT_SEARCH_FAKE_OBJ) {
2006:             void *iter = NULL;
2007:             const AVClass *child;
2008:             while (child = av_opt_child_class_iterate(c, &iter))
2009:                 if (o = av_opt_find2(&child, name, unit, opt_flags, search_flags, NULL))
2010:                     return o;
2011:         } else {
2012:             void *child = NULL;
2013:             while (child = av_opt_child_next(obj, child))
2014:                 if (o = av_opt_find2(child, name, unit, opt_flags, search_flags, target_obj))
2015:                     return o;
2016:         }
2017:     }
2018: 
2019:     while (o = av_opt_next(obj, o)) {
```

#### `nvenc.c` lines 833-837
```c
833:         if (avctx->b_quant_factor != 0.0)
834:             rc->constQP.qpInterB = av_clip(ctx->cqp * fabs(avctx->b_quant_factor) + avctx->b_quant_offset + 0.5, 0, qmax);
835:         if (avctx->i_quant_factor != 0.0)
836:             rc->constQP.qpIntra = av_clip(ctx->cqp * fabs(avctx->i_quant_factor) + avctx->i_quant_offset + 0.5, 0, qmax);
837:     }
```

#### `nvenc.c` lines 1761-1767
```c
1761:     if (avctx->gop_size > 0) {
1762:         // only overwrite preset if a GOP size was selected as input
1763:         ctx->encode_config.gopLength = avctx->gop_size;
1764:     } else if (avctx->gop_size == 0) {
1765:         ctx->encode_config.frameIntervalP = 0;
1766:         ctx->encode_config.gopLength = 1;
1767:     }
```

#### `qsvenc.c` lines 923-930
```c
923:         quant = avctx->global_quality / FF_QP2LAMBDA;
924:         if (avctx->codec_id == AV_CODEC_ID_AV1) {
925:             q->param.mfx.QPI = av_clip_uintp2(quant * fabs(avctx->i_quant_factor) + avctx->i_quant_offset, 8);
926:             q->param.mfx.QPP = av_clip_uintp2(quant, 8);
927:             q->param.mfx.QPB = av_clip_uintp2(quant * fabs(avctx->b_quant_factor) + avctx->b_quant_offset, 8);
928:         } else {
929:             q->param.mfx.QPI = av_clip(quant * fabs(avctx->i_quant_factor) + avctx->i_quant_offset, 0, 51);
930:             q->param.mfx.QPP = av_clip(quant, 0, 51);
```

libavutil/avutil.h:226 (n9.0.2): `#define FF_QP2LAMBDA 118 ///< factor to convert from H.263 QP to lambda`

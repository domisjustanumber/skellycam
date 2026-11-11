# Apple VideoToolbox: property text (verbatim)

## A. Apple developer documentation JSON endpoint (primary, Apple-hosted)

URL pattern: https://developer.apple.com/tutorials/data/documentation/videotoolbox/<symbol>.json, fetched 2026-11-10. Text below is the JSON's abstract and Discussion paragraphs, flattened by `scratchpad/step3/apple_text.py` (inline code shown in backticks, references in [brackets]); words are not edited.
```text
===== kvtcompressionpropertykey_allowframereordering.json kVTCompressionPropertyKey_AllowFrameReordering
platforms: [('iOS', '8.0', False), ('iPadOS', '8.0', False), ('Mac Catalyst', '13.1', False), ('macOS', '10.8', False), ('tvOS', '10.2', False), ('visionOS', '1.0', False)]
abstract: A Boolean value that indicates whether frame reordering is enabled.
decl: let kVTCompressionPropertyKey_AllowFrameReordering: CFString ['swift']
## Discussion
In order to encode B frames, a video encoder must reorder frames, which means that the order in which the frames are emitted and stored (the decode order) is different from the order in which they were presented to the video encoder (the display order).  The default value is `true`.  Set this value to `false` to prevent frame reordering.
===== kvtcompressionpropertykey_allowtemporalcompression.json kVTCompressionPropertyKey_AllowTemporalCompression
platforms: [('iOS', '8.0', False), ('iPadOS', '8.0', False), ('Mac Catalyst', '13.1', False), ('macOS', '10.8', False), ('tvOS', '10.2', False), ('visionOS', '1.0', False)]
abstract: A Boolean value indicating whether temporal compression is enabled.
decl: let kVTCompressionPropertyKey_AllowTemporalCompression: CFString ['swift']
## Discussion
The default value is `true`.  Set this `value` to false to require key-frame-only compression.
===== kvtcompressionpropertykey_constantbitrate.json kVTCompressionPropertyKey_ConstantBitRate
platforms: [('iOS', '16.0', False), ('iPadOS', '16.0', False), ('Mac Catalyst', '16.0', False), ('macOS', '13.0', False), ('tvOS', '16.0', False), ('visionOS', '1.0', False)]
abstract: Requires that the encoder use a Constant Bit Rate algorithm.
decl: let kVTCompressionPropertyKey_ConstantBitRate: CFString ['swift']
===== kvtcompressionpropertykey_maxallowedframeqp.json kVTCompressionPropertyKey_MaxAllowedFrameQP
platforms: [('iOS', '15.0', False), ('iPadOS', '15.0', False), ('Mac Catalyst', '15.0', False), ('macOS', '12.0', False), ('tvOS', '15.0', False), ('visionOS', '1.0', False)]
abstract: The maximum allowed encoded frame QP (Quantization Parameter).
decl: let kVTCompressionPropertyKey_MaxAllowedFrameQP: CFString ['swift']
===== kvtcompressionpropertykey_maxkeyframeinterval.json kVTCompressionPropertyKey_MaxKeyFrameInterval
platforms: [('iOS', '8.0', False), ('iPadOS', '8.0', False), ('Mac Catalyst', '13.1', False), ('macOS', '10.8', False), ('tvOS', '10.2', False), ('visionOS', '1.0', False)]
abstract: The maximum interval between key frames, also known as the key frame rate.
decl: let kVTCompressionPropertyKey_MaxKeyFrameInterval: CFString ['swift']
## Discussion
Key frames, also known as sync frames, reset inter-frame dependencies; decoding a key frame is sufficient to prepare a decoder for correctly decoding the difference frames that follow. Video encoders are allowed to generate key frames more frequently if doing so results in more efficient compression. The default key frame interval is 0, which indicates that the video encoder should choose where to place all key frames. A key frame interval of 1 indicates that every frame must be a keyframe, 2 indicates that at least every other frame must be a keyframe, and so on.
This key can be set in conjunction with [kVTCompressionPropertyKey_MaxKeyFrameIntervalDuration], which requires a keyframe every X frames or every Y seconds, whichever comes first.
===== kvtcompressionpropertykey_maxkeyframeintervalduration.json kVTCompressionPropertyKey_MaxKeyFrameIntervalDuration
platforms: [('iOS', '8.0', False), ('iPadOS', '8.0', False), ('Mac Catalyst', '13.1', False), ('macOS', '10.8', False), ('tvOS', '10.2', False), ('visionOS', '1.0', False)]
abstract: The maximum duration from one key frame to the next in seconds.
decl: let kVTCompressionPropertyKey_MaxKeyFrameIntervalDuration: CFString ['swift']
## Discussion
The default value is `0`, which means no limit.  This property is particularly useful when the frame rate is variable. See [kVTCompressionPropertyKey_MaxKeyFrameIntervalDuration] for more discussion of key frames.
This key can be set in conjunction with [kVTCompressionPropertyKey_MaxKeyFrameIntervalDuration], which requires a keyframe every `X` frames or every `Y` seconds, whichever comes first.
===== kvtcompressionpropertykey_minallowedframeqp.json kVTCompressionPropertyKey_MinAllowedFrameQP
platforms: [('iOS', '16.0', False), ('iPadOS', '16.0', False), ('Mac Catalyst', '16.0', False), ('macOS', '13.0', False), ('tvOS', '16.0', False), ('visionOS', '1.0', False)]
abstract: The minimum allowed encoded frame QP (Quantization Parameter).
decl: let kVTCompressionPropertyKey_MinAllowedFrameQP: CFString ['swift']
===== kvtcompressionpropertykey_quality.json kVTCompressionPropertyKey_Quality
platforms: [('iOS', '8.0', False), ('iPadOS', '8.0', False), ('Mac Catalyst', '13.1', False), ('macOS', '10.8', False), ('tvOS', '10.2', False), ('visionOS', '1.0', False)]
abstract: The desired compression quality.
decl: let kVTCompressionPropertyKey_Quality: CFString ['swift']
## Discussion
Some encoders, such as JPEG, describe the compression level of each image with a quality value.  This value should be specified as a number in the range of 0.0 to 1.0, where low = 0.25, normal = 0.50, high = 0.75, and 1.0 implies lossless compression for encoders that support it.
===== kvtcompressionpropertykey_supportsbaseframeqp.json kVTCompressionPropertyKey_SupportsBaseFrameQP
platforms: [('iOS', '15.0', False), ('iPadOS', '15.0', False), ('Mac Catalyst', '15.0', False), ('macOS', '12.0', False), ('tvOS', '15.0', False), ('visionOS', '1.0', False)]
abstract: A value that indicates whether the encoder supports base frame QP requests.
decl: let kVTCompressionPropertyKey_SupportsBaseFrameQP: CFString ['swift']
===== kvtencodeframeoptionkey_baseframeqp.json kVTEncodeFrameOptionKey_BaseFrameQP
platforms: [('iOS', '15.0', False), ('iPadOS', '15.0', False), ('Mac Catalyst', '15.0', False), ('macOS', '12.0', False), ('tvOS', '15.0', False), ('visionOS', '1.0', False)]
abstract: 
decl: let kVTEncodeFrameOptionKey_BaseFrameQP: CFString ['swift']
===== kvtencodeframeoptionkey_forcekeyframe.json kVTEncodeFrameOptionKey_ForceKeyFrame
platforms: [('iOS', '8.0', False), ('iPadOS', '8.0', False), ('Mac Catalyst', '13.1', False), ('macOS', '10.8', False), ('tvOS', '10.2', False), ('visionOS', '1.0', False)]
abstract: Boolean value indicating whether the current frame is forced to be a key frame.
decl: let kVTEncodeFrameOptionKey_ForceKeyFrame: CFString ['swift']
## Discussion
This value is set in the `frameProperties` dictionary passed to [VTCompressionSessionEncodeFrame(_:imageBuffer:presentationTimeStamp:duration:frameProperties:sourceFrameRefcon:infoFlagsOut:)]; it determines whether the current frame is forced to be a keyframe or not. Note that it may not be possible for the encoder to accommodate all requests.
===== kvtvideoencoderspecification_requirehardwareacceleratedvideoencoder.json kVTVideoEncoderSpecification_RequireHardwareAcceleratedVideoEncoder
platforms: [('iOS', '17.4', False), ('iPadOS', '17.4', False), ('Mac Catalyst', '17.4', False), ('macOS', '10.9', False), ('tvOS', '17.4', False), ('visionOS', '1.1', False)]
abstract: A Boolean value indicating whether hardware-accelerated encoding is required.
decl: let kVTVideoEncoderSpecification_RequireHardwareAcceleratedVideoEncoder: CFString ['swift']
## Discussion
This key is set in the `encoderSpecification` passed in to [VTCompressionSessionCreate(allocator:width:height:codecType:encoderSpecification:imageBufferAttributes:compressedDataAllocator:outputCallback:refcon:compressionSessionOut:)].  Set it to [kCFBooleanTrue] to require hardware-accelerated encoding.  If hardware acceleration is not possible, the [VTCompressionSessionCreate(allocator:width:height:codecType:encoderSpecification:imageBufferAttributes:compressedDataAllocator:outputCallback:refcon:compressionSessionOut:)] call fails. Setting this key automatically implies that [kVTVideoEncoderSpecification_EnableHardwareAcceleratedVideoEncoder] is enabled; there is no need to set both.
This key is useful for clients that have their own software encoding implementation or those that may need to configure software and hardware encode sessions differently. Hardware acceleration may be unavailable for a number of reasons:
- The machine does not have hardware acceleration capabilities.
- The requested encoding format or encoding configuration is not supported.
- The hardware encoding resources on the machine are busy.
```

## B. VTCompressionProperties.h from the macOS 15.5 SDK, via a third-party mirror (NOT Apple-hosted)

URL: https://raw.githubusercontent.com/alexey-lysiuk/macos-sdk/896cd40df984b847d486723edce50e247385617e/MacOSX15.5.sdk/System/Library/Frameworks/VideoToolbox.framework/Versions/A/Headers/VTCompressionProperties.h, fetched 2026-11-10, sha256 e7cf58626155843b0cf2ec8094d88bdd7c760a9e994eb06dc2c29a1edb66ca00. Label: SDK header text via mirror. Where it overlaps with section A the wording agrees (MaxKeyFrameInterval, AllowFrameReordering, Quality, AllowTemporalCompression). Header-only text (BaseFrameQP, Min/MaxAllowedFrameQP discussion) has no Apple-hosted verbatim copy in this folder.

#### `VTCompressionProperties_15.5.h` lines 124-142
```text
124: 		Key frames, also known as sync frames, reset inter-frame
125: 		dependencies; decoding a key frame is sufficient to prepare a
126: 		decoder for correctly decoding the difference frames that
127: 		follow. 
128: 		Video encoders are allowed to generate key frames more frequently if
129: 		this would result in more efficient compression. 
130: 		The default key frame interval is 0, which indicates that the
131: 		video encoder should choose where to place all key frames. A key
132: 		frame interval of 1 indicates that every frame must be a key
133: 		frame, 2 indicates that at least every other frame must be a key
134: 		frame, etc.
135: 		See also kVTCompressionPropertyKey_AllowTemporalCompression.
136: 		
137: 		This key can be set in conjunction with 
138: 		kVTCompressionPropertyKey_MaxKeyFrameIntervalDuration,
139: 		and both limits will be enforced - requiring a keyframe every X
140: 		frames or every Y seconds, whichever comes first.
141: */
142: VT_EXPORT const CFStringRef kVTCompressionPropertyKey_MaxKeyFrameInterval API_AVAILABLE(macos(10.8), ios(8.0), tvos(10.2), visionos(1.0)) API_UNAVAILABLE(watchos); // Read/write, CFNumber<int>, Optional
```

#### `VTCompressionProperties_15.5.h` lines 162-182
```text
162: /*!
163: 	@constant	kVTCompressionPropertyKey_AllowTemporalCompression
164: 	@abstract
165: 		Enables temporal compression.
166: 	@discussion
167: 		True by default.  Set this to false to require key-frame-only compression.
168: */
169: VT_EXPORT const CFStringRef kVTCompressionPropertyKey_AllowTemporalCompression API_AVAILABLE(macos(10.8), ios(8.0), tvos(10.2), visionos(1.0)) API_UNAVAILABLE(watchos); // Read/Write, CFBoolean, Optional, defaults to true
170: 
171: /*!
172: 	@constant	kVTCompressionPropertyKey_AllowFrameReordering
173: 	@abstract
174: 		Enables frame reordering. 
175: 	@discussion
176: 		In order to encode B frames, a video encoder must reorder frames,
177: 		which means that the order in which they will be emitted and
178: 		stored (the decode order) is different from the order in which
179: 		they were presented to the video encoder (the display order). 
180: 		True by default.  Set this to false to prevent frame reordering.
181: */
182: VT_EXPORT const CFStringRef kVTCompressionPropertyKey_AllowFrameReordering API_AVAILABLE(macos(10.8), ios(8.0), tvos(10.2), visionos(1.0)) API_UNAVAILABLE(watchos); // Read/Write, CFBoolean, Optional, defaults to true
```

#### `VTCompressionProperties_15.5.h` lines 248-260
```text
248: 
249: /*!
250: 	@constant	kVTCompressionPropertyKey_Quality
251: 	@abstract
252: 		The desired compression quality.
253: 	@discussion
254: 		Some encoders, such as JPEG, describe the compression level of each
255: 		image with a quality value.  This value should be specified as a
256: 		number in the range of 0.0 to 1.0, where low = 0.25, normal = 0.50,
257: 		high = 0.75, and 1.0 implies lossless compression for encoders that
258: 		support it.
259: */
260: VT_EXPORT const CFStringRef kVTCompressionPropertyKey_Quality API_AVAILABLE(macos(10.8), ios(8.0), tvos(10.2), visionos(1.0)) API_UNAVAILABLE(watchos); // Read/write, CFNumber<Float>, Optional
```

#### `VTCompressionProperties_15.5.h` lines 784-793
```text
784: 
785: /*!
786: 	@constant  kVTCompressionPropertyKey_SupportsBaseFrameQP
787: 	@abstract
788: 		This property can be queried to determine if the encoder supports base frame QP requests.
789: 	@discussion
790: 		If this property returns kCFBooleanTrue, it indicates that the encoder supports base frame QP requests through kVTEncodeFrameOptionKey_BaseFrameQP. If it returns false or kVTPropertyNotSupportedErr, base frame QP requests will cause errors on VTCompressionSessionEncodeFrame calls, or will be ignored.
791: 
792: */
793: VT_EXPORT const CFStringRef kVTCompressionPropertyKey_SupportsBaseFrameQP API_AVAILABLE(macos(12.0), ios(15.0), tvos(15.0), visionos(1.0)) API_UNAVAILABLE(watchos); // Read only, CFBoolean, Optional, false by default
```

#### `VTCompressionProperties_15.5.h` lines 809-838
```text
809: 
810: /*!
811: 	@constant  kVTEncodeFrameOptionKey_BaseFrameQP
812: 	@abstract
813: 		CFNumberRef requesting the current frame to use the provided base frame QP.
814: 	@discussion
815: 		This value is set in the frameProperties CFDictionary passed to VTCompressionSessionEncodeFrame to force
816: 		the QP value for the current frame. This is an optional parameter. Use it only when you have a specific requirement
817: 		for the video quality and you are familiar with frame QP and are prepared to assume full responsibility for rate control.
818: 		Otherwise it is strongly encouraged to rely on the encoder’s rate control for adjusting frame QP.
819:  
820: 		Setting BaseFrameQP turns off standard rate control and will cause the following properties to be ignored::
821: 			kVTCompressionPropertyKey_DataRateLimits
822: 			kVTCompressionPropertyKey_AverageBitRate
823: 			kVTCompressionPropertyKey_BaseLayerBitRateFraction
824: 			kVTCompressionPropertyKey_Quality
825: 			kVTCompressionPropertyKey_MaxAllowedFrameQP
826: 			kVTCompressionPropertyKey_MinAllowedFrameQP
827:  
828: 		If kVTEncodeFrameOptionKey_BaseFrameQP is used, it must be set for all frames in a session. The QP value specified is
829: 		frame-level but macro-block level QP may be modulated inside a frame. There will be no rate-control related frame dropping
830: 		if kVTEncodeFrameOptionKey_BaseFrameQP is used.
831: 
832: 		kVTEncodeFrameOptionKey_BaseFrameQP is only supported if the encoder returns kCFBooleanTrue when the
833: 		kVTCompressionPropertyKey_SupportsBaseFrameQP is queried. If this FrameOptionKey is set for encoder which
834: 		does not support it, it will be ignored.
835: 
836: 		Note that it may not be possible for the encoder to accommodate all requests.
837: */
838: VT_EXPORT const CFStringRef kVTEncodeFrameOptionKey_BaseFrameQP API_AVAILABLE(macos(12.0), ios(15.0), tvos(15.0), visionos(1.0)) API_UNAVAILABLE(watchos); // CFNumberRef, Optional
```

#### `VTCompressionProperties_15.5.h` lines 1135-1158
```text
1135: 
1136: /*!
1137: 	@constant	kVTCompressionPropertyKey_MaxAllowedFrameQP
1138: 	@abstract
1139: 		Specifies the maximum allowed encoded frame QP (Quantization Parameter).
1140: 	@discussion
1141: 		This is an optional parameter. Use it only when you have a specific requirement for the video quality and you are
1142: 		familiar with frame QP. To satisfy this requirement, the encoder may drop frames to maintain bitrate and QP goals.
1143: 		This is not supported in all encoders or in all encoder operating modes. kVTPropertyNotSupportedErr will be
1144: 		returned when this option is not supported.
1145: */
1146: VT_EXPORT const CFStringRef kVTCompressionPropertyKey_MaxAllowedFrameQP API_AVAILABLE(macos(12.0), ios(15.0), tvos(15.0), visionos(1.0)) API_UNAVAILABLE(watchos); // Read/write, CFNumberRef, Optional
1147: 
1148: /*!
1149: 	@constant	kVTCompressionPropertyKey_MinAllowedFrameQP
1150: 	@abstract
1151: 		Specifies the minimum allowed encoded frame QP (Quantization Parameter).
1152: 	@discussion
1153: 		This is an optional parameter. Use it only when you have a specific requirement for the video quality and you are
1154: 		familiar with frame QP. 
1155: 		This is not supported in all encoders or in all encoder operating modes. kVTPropertyNotSupportedErr will be
1156: 		returned when this option is not supported.
1157: */
1158: VT_EXPORT const CFStringRef kVTCompressionPropertyKey_MinAllowedFrameQP API_AVAILABLE(macos(13.0), ios(16.0), tvos(16.0), visionos(1.0)) API_UNAVAILABLE(watchos); // Read/write, CFNumberRef, Optional
```

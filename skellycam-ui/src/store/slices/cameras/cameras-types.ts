// cameras-types.ts
import { z } from 'zod';

// ==================== Constants ====================
export const PIXEL_FORMATS = ['RGB', 'BGR', 'GRAY'] as const;
export const EXPOSURE_MODES = ['MANUAL', 'AUTO', 'RECOMMEND'] as const;
export const CONNECTION_STATUS = ['disconnected', 'connecting', 'connected', 'error'] as const;


export const ROTATION_DEGREE_LABELS: Record<RotationValue, string> = {
    [-1]: '0°',
    [0]: '90°',
    [1]: '180°',
    [2]: '270°',
};

export const ROTATION_OPTIONS = [-1, 0, 1, 2] as const;
/** Capture/stream pixel formats exposed in the UI (MJPEG-only for now). */
export const CAPTURE_FOURCC_OPTIONS = ['MJPG'] as const;
/** Video writer codec choices — independent of capture. */
export const WRITER_FOURCC_OPTIONS = ['MJPG', 'X264', 'YUYV', 'H264'] as const;

/** @deprecated Prefer CAPTURE_FOURCC_OPTIONS or WRITER_FOURCC_OPTIONS. */
export const FOURCC_OPTIONS = CAPTURE_FOURCC_OPTIONS;

/** Default shared frame-rate preset (`30fps (default)` in the Cameras bar when intersecting selections support it). */
export const DEFAULT_UI_FRAMERATE = 30;

/** Treat advertised FPS labels as compatible (mirror server ``fps_compatibility.FPS_VALUE_TOLERANCE``). */
export const FPS_VALUE_TOLERANCE = 0.51;

export type PixelFormat = typeof PIXEL_FORMATS[number];
export type ExposureMode = typeof EXPOSURE_MODES[number];
export type ConnectionStatus = typeof CONNECTION_STATUS[number];
export type RotationValue = typeof ROTATION_OPTIONS[number];
export type CaptureFourccOption = typeof CAPTURE_FOURCC_OPTIONS[number];
export type WriterFourccOption = typeof WRITER_FOURCC_OPTIONS[number];
export type FourccOption = CaptureFourccOption;

// Helper to get rotation label for UI
export const ROTATION_LABELS: Record<RotationValue, string> = {
    [-1]: 'No Rotation',
    [0]: '90°',
    [1]: '180°',
    [2]: '270°',
};

// ==================== Camera Configuration ====================
export const CameraConfigSchema = z.object({
    // Identity
    camera_id: z.string(),
    camera_index: z.number(),
    camera_name: z.string(),
    use_this_camera: z.boolean(),

    // Video settings
    resolution: z.object({
        width: z.number().int(),
        height: z.number().int()
    }),
    framerate: z.number().min(-1).max(1000), // -1 for auto

    // Image settings
    color_channels: z.number().int().min(1).max(4),
    pixel_format: z.enum(PIXEL_FORMATS),
    rotation: z.union([z.literal(-1), z.literal(0), z.literal(1), z.literal(2)]),

    // Exposure settings
    exposure_mode: z.enum(EXPOSURE_MODES),
    exposure: z.number(),
    auto_focus_enabled: z.boolean(),
    focus: z.number(),

    // Codec settings
    capture_fourcc: z.enum(CAPTURE_FOURCC_OPTIONS),
    writer_fourcc: z.enum(WRITER_FOURCC_OPTIONS),
});

export type CameraConfig = z.infer<typeof CameraConfigSchema>;

// ==================== Camera State ====================
export interface Camera {
    id: string;                    // Primary key (same as camera_id in config) - must be unique
    index: number;                 // openpnp-capture device index — must be unique in the group
    name: string;                  // Human-readable name, e.g. "Logitech C920" - not necessarily unique
    actualConfig: CameraConfig;     // Configuration extracted from camera stream
    desiredConfig: CameraConfig;    // User's desired configuration
    hasConfigMismatch: boolean;     // Whether actual differs from desired
    connectionStatus: 'available' | 'connected' | 'error' | 'unavailable';  // unavailable = detected but stream probe failed (often in use elsewhere)
    selected: boolean;              // UI selection state
    /** False when detection could not open a capture stream (e.g. exclusive use by another app). */
    streamAvailable: boolean;
    /** Backend hint when ``streamAvailable`` is false. */
    streamUnavailableReason?: string | null;
    matchesListedVirtualName?: boolean;

    // Device info (from detection)
    deviceInfo: {
        virtual?: boolean;
        /** Stable ID from openpnp ``Cap_getDeviceUniqueID`` (when present). */
        uniqueId?: string | null;
        matchesListedVirtualName?: boolean;
        supportsFocusManual?: boolean;
        focusAutoSupported?: boolean;
        focusMin?: number | null;
        focusMax?: number | null;
        focusDefault?: number | null;
        availableFormats?: Array<{
            format_id: number;
            width: number;
            height: number;
            fps: number;
            fourcc_str: string;
            bpp: number;
        }>;
    };

    // Performance metrics (optional, updated from websocket)
    metrics?: {
        fps: number;
        droppedFrames: number;
        lastFrameTime: number;
    };
}

// ==================== Store State ====================
export interface CamerasState {
    cameras: Camera[];
    isPaused: boolean;
    /** Deprecated combined flag — derived from detecting vs applying connection */
    isLoading: boolean;
    isDetectingCameras: boolean;
    isApplyingCameraConnection: boolean;
    suppressListedVirtualCameras: boolean;
    /** Renderer hint that OS media devices may have changed (USB webcam plug/unplug) */
    hardwareCameraEnumerationChanged: boolean;
    error: string | null;
}

// ==================== API Types ====================
export interface DetectCamerasRequest {
    /** When omitted, follows the “Ignore virtual webcams” setting (suppress listed virtual devices on the server). */
    filterVirtual?: boolean;
    probeStreams?: boolean;
    /** When true (default mirrors “Ignore virtual webcams”), backend skips format/resolution probing for listed virtual cameras. */
    skipListedVirtualResolutionInterrogation?: boolean;
}

export interface DetectCamerasResponse {
    cameras: Array<{
        camera_id: string;
        index: number;
        name: string;
        unique_id?: string | null;
        stream_available?: boolean;
        stream_unavailable_reason?: string | null;
        matches_listed_virtual_name?: boolean;
        supports_focus_manual?: boolean;
        focus_auto_supported?: boolean;
        focus_min?: number | null;
        focus_max?: number | null;
        focus_default?: number | null;
        available_formats?: Array<{
            format_id: number;
            width: number;
            height: number;
            fps: number;
            fourcc_str: string;
            bpp: number;
        }>;
    }>;
}

export interface CamerasConnectOrUpdateRequest {
    camera_configs: Record<string, CameraConfig>;
}

export interface ConnectCamerasResponse {
    camera_configs: Record<string, CameraConfig>;
}

// ==================== Helper Functions ====================
export function createDefaultCameraConfig(
    id: string,
    index: number,
    name: string,
): CameraConfig {
    return {
        camera_id: id,
        camera_index: index,
        camera_name: name,
        use_this_camera: true,
        resolution: { width: 1280, height: 720 },
        framerate: DEFAULT_UI_FRAMERATE,
        color_channels: 3,
        pixel_format: 'RGB',
        rotation: -1,
        exposure_mode: 'RECOMMEND',
        exposure: -7,
        auto_focus_enabled: false,
        focus: -1,
        capture_fourcc: 'MJPG',
        writer_fourcc: 'X264',
    };
}

export function areConfigsEqual(
    config1: CameraConfig,
    config2: CameraConfig
): boolean {
    return (
        config1.resolution.width === config2.resolution.width &&
        config1.resolution.height === config2.resolution.height &&
        config1.framerate === config2.framerate &&
        config1.exposure_mode === config2.exposure_mode &&
        config1.exposure === config2.exposure &&
        config1.rotation === config2.rotation &&
        config1.pixel_format === config2.pixel_format &&
        config1.capture_fourcc === config2.capture_fourcc &&
        config1.writer_fourcc === config2.writer_fourcc &&
        config1.auto_focus_enabled === config2.auto_focus_enabled &&
        config1.focus === config2.focus
    );
}

export function extractConfigSettings(
    config: CameraConfig
): Partial<CameraConfig> {
    // Extract copyable settings (exclude identity fields)
    return {
        resolution: { ...config.resolution },
        framerate: config.framerate,
        color_channels: config.color_channels,
        pixel_format: config.pixel_format,
        rotation: config.rotation,
        exposure_mode: config.exposure_mode,
        exposure: config.exposure,
        auto_focus_enabled: config.auto_focus_enabled,
        focus: config.focus,
        capture_fourcc: config.capture_fourcc,
        writer_fourcc: config.writer_fourcc,
    };
}

/** Known virtual webcam name prefixes (case-sensitive ``startsWith``); whole-word “virtual” also matches (regex below). */
export const LISTED_VIRTUAL_CAMERA_NAME_PREFIXES: readonly string[] = [
    'OBS-Camera',
    'Spout',
    'NDI Webcam',
    'Camera (NVIDIA Broadcast)',
] as const;

const LISTED_VIRTUAL_NAME_WORD_RE = /\bvirtual\b/i;

/** Backend flag, device-info flag, case-sensitive listed prefix, or whole-word “virtual” (case-insensitive). */
export function cameraMatchesListedVirtualPattern(camera: Camera): boolean {
    if (
        camera.matchesListedVirtualName
        || camera.deviceInfo.matchesListedVirtualName
    ) {
        return true;
    }
    const name = (camera.name ?? '').trim();
    if (LISTED_VIRTUAL_NAME_WORD_RE.test(name)) {
        return true;
    }
    return LISTED_VIRTUAL_CAMERA_NAME_PREFIXES.some((p) => name.startsWith(p));
}

export function fpsValuesEquivalent(a: number, b: number): boolean {
    return Math.abs(a - b) < FPS_VALUE_TOLERANCE;
}

/**
 * Positive FPS from the Cameras bar when > 0, otherwise this camera’s desired framerate (when > 0).
 * ``null`` = no numeric target (“Auto / mixed” UI).
 */
export function effectiveResolutionTargetFramerate(
    groupFramerateChoice: number,
    desiredFramerate: number,
): number | null {
    if (typeof groupFramerateChoice === 'number' && groupFramerateChoice > 0) {
        return groupFramerateChoice;
    }
    if (typeof desiredFramerate === 'number' && desiredFramerate > 0) {
        return desiredFramerate;
    }
    return null;
}

/** True when at least one enumerated mode reports a native FPS matching ``targetFps``. */
export function formatsIncludeTargetFramerate(
    formats: Camera['deviceInfo']['availableFormats'],
    targetFps: number,
): boolean {
    if (!formats?.length) return false;
    if (targetFps <= 0) {
        return false;
    }
    return formats.some((f) => fpsValuesEquivalent(f.fps, targetFps));
}

/**
 * True when ``availableFormats`` includes no mode at the Cameras-bar target FPS (see
 * {@link selectBarAppliedTargetFramerate}). Every tree row re-evaluates when selection or FPS changes.
 */
export function cameraMissingFormatForTargetFps(
    camera: Pick<Camera, 'deviceInfo'>,
    barAppliedTargetFramerate: number | null,
): boolean {
    if (barAppliedTargetFramerate === null) {
        return false;
    }
    return !formatsIncludeTargetFramerate(camera.deviceInfo.availableFormats, barAppliedTargetFramerate);
}

/** Map device/driver fourcc labels to stored capture_fourcc while capture is MJPEG-only. */
export function normalizeCaptureFourcc(_deviceFourcc: string): CaptureFourccOption {
    return 'MJPG';
}

const _FOURCC_ALNUM = /[^A-Z0-9]/gi;

/**
 * Codec tie-break among modes with the same resolution + fps:
 * YUV / uncompressed (better) → H.264 → MJPEG (worse).
 * Lower numeric rank = preferred.
 */
export function captureFourccFamilyRank(fourccRaw: string): number {
    const compact = fourccRaw.replace(/\s+/g, '').toUpperCase();
    const alnum = compact.replace(_FOURCC_ALNUM, '');
    const canon = normalizeCaptureFourcc(fourccRaw);

    if (/\bMJPE?G\b/i.test(compact) || alnum.includes('MJPEG') || alnum.includes('JFIF')) {
        return 2;
    }
    if (
        alnum.includes('H264')
        || alnum.includes('X264')
        || /\b(?:AVC1|HVC1|DVHE|DAVC|M264)\b/i.test(compact)
        || canon === 'H264'
        || canon === 'X264'
    ) {
        return 1;
    }
    if (
        canon === 'YUYV'
        || /\b(?:YUY2|YUYV|UYVY|NV12|NV21|IYUV|I420|YV12|YU12|P010|P016|NV16|Y41P|P210|P216)\b/i.test(
            compact,
        )
        || /\b(?:BGR\d?|RGB\d?|GRAY|GREY|Y800|RAW)\b/i.test(compact)
    ) {
        return 0;
    }
    if (canon === 'MJPG') {
        return 2;
    }
    return 3;
}

type DeviceFormatEntry = NonNullable<
    Camera['deviceInfo']['availableFormats']
>[number];

/** True if format ``b`` is preferred over ``a`` (higher resolution or better codec rank). */
export function prefersDeviceFormatBOverA(a: DeviceFormatEntry, b: DeviceFormatEntry): boolean {
    const pa = a.width * a.height;
    const pb = b.width * b.height;
    if (pb !== pa) return pb > pa;
    if (b.width !== a.width) return b.width > a.width;
    const ra = captureFourccFamilyRank(a.fourcc_str);
    const rb = captureFourccFamilyRank(b.fourcc_str);
    if (rb !== ra) return rb < ra;
    return b.format_id >= a.format_id;
}

export function compareDeviceFormatsResolutionPreference(
    a: DeviceFormatEntry,
    b: DeviceFormatEntry,
): number {
    if (prefersDeviceFormatBOverA(a, b)) return 1;
    if (prefersDeviceFormatBOverA(b, a)) return -1;
    return 0;
}

/** Unique advertised FPS buckets (within {@link FPS_VALUE_TOLERANCE}), sorted ascending. */
export function uniqRepresentativeFpsFromFormats(
    formats: Camera['deviceInfo']['availableFormats'],
): number[] {
    if (!formats?.length) return [];
    const reps: number[] = [];
    for (const f of formats) {
        if (!reps.some((existing) => fpsValuesEquivalent(existing, f.fps))) {
            reps.push(f.fps);
        }
    }
    return reps.sort((a, b) => a - b);
}

/**
 * Best format whose native FPS exactly matches ``targetFps`` (>0): prefers higher resolution then
 * codec ranking. Auto / unspecified (``targetFps``≤0): highest-resolution heuristic.
 */
export function pickBestFormatAtTargetFps(
    formats: Camera['deviceInfo']['availableFormats'],
    targetFps: number,
): DeviceFormatEntry | null {
    if (!formats?.length) return null;

    let pool = [...formats];
    if (targetFps > 0) {
        const feasible = formats.filter((f) => fpsValuesEquivalent(f.fps, targetFps));
        if (!feasible.length) {
            return null;
        }
        pool = feasible;
    }

    return pool.reduce((best, cur) =>
        (prefersDeviceFormatBOverA(best, cur) ? cur : best),
    );
}

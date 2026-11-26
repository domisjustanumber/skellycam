// The parser of the camera message (specs/preview-4b.md 5.2; layout: table 3.2 of specs/preview.md). No import:
// the Node unit tests load this file directly.

export const CAMERA_FRAME_VERSION = 1;
export const CAMERA_FRAME_HEADER_SIZE = 48;

export interface CameraMessage {
    flags: number;
    frameNumber: bigint;
    arrivalNs: bigint;
    rotationCwDeg: 0 | 90 | 180 | 270;
    cameraId: string;
    jpeg: Uint8Array | null;   // a view of the bytes after the header; null when flags & 0x0F
}

/** Read one camera message. Throws an Error that names the reason of a refused message. */
export function parseCameraMessage(data: ArrayBuffer): CameraMessage {
    if (data.byteLength < CAMERA_FRAME_HEADER_SIZE) {
        throw new Error(`camera message: ${data.byteLength} bytes, shorter than the header of ${CAMERA_FRAME_HEADER_SIZE}`);
    }
    const view = new DataView(data);
    const version = view.getUint8(0);
    if (version !== CAMERA_FRAME_VERSION) {
        throw new Error(`camera message: version ${version}, not ${CAMERA_FRAME_VERSION}`);
    }
    const jpegLen = view.getUint32(28, true);
    if (data.byteLength !== CAMERA_FRAME_HEADER_SIZE + jpegLen) {
        throw new Error('camera message: the length is not 48 + jpeg_len');
    }
    const rotation = view.getUint32(24, true);
    if (rotation !== 0 && rotation !== 90 && rotation !== 180 && rotation !== 270) {
        throw new Error('camera message: rotation_cw_deg is not 0, 90, 180 or 270');
    }
    const idBytes = new Uint8Array(data, 32, 16);
    const end = idBytes.indexOf(0);
    const cameraId = String.fromCharCode(...idBytes.subarray(0, end === -1 ? 16 : end));
    if (cameraId === '') throw new Error('camera message: the camera id is empty');
    const flags = view.getUint32(4, true);
    return {
        flags,
        frameNumber: view.getBigInt64(8, true),
        arrivalNs: view.getBigInt64(16, true),
        rotationCwDeg: rotation,
        cameraId,
        jpeg: (flags & 0x0f) !== 0 ? null : new Uint8Array(data, CAMERA_FRAME_HEADER_SIZE, jpegLen),
    };
}

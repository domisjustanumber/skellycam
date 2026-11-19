// The flat-block JPEG encoder of specs/player.md section 12.2.1, and the barcode image of the fixtures.
// Each 8 x 8 block holds one flat value, so the encoder needs no DCT: DC only, then EOB.

export type Sampling = '444' | '422' | '420' | 'gray';

export interface JpegOptions {
    noDht?: boolean;          // leave out the DHT segment (the data still uses the Annex K tables)
    exifOrientation?: number; // write an APP1 EXIF segment with this orientation tag
    trailingBytes?: number;   // bytes after the EOI
}

// ITU-T T.81 Annex K.3: BITS (counts of codes of length 1 to 16) and HUFFVAL.
const DC_LUM_BITS = [0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0];
const DC_CHR_BITS = [0, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0];
const DC_VALS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
const AC_LUM_BITS = [0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7d];
const AC_LUM_VALS = [
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07,
    0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xa1, 0x08, 0x23, 0x42, 0xb1, 0xc1, 0x15, 0x52, 0xd1, 0xf0,
    0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0a, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2a, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3a, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
    0x4a, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5a, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
    0x6a, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7a, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
    0x8a, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0xa2, 0xa3, 0xa4, 0xa5, 0xa6, 0xa7,
    0xa8, 0xa9, 0xaa, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6, 0xb7, 0xb8, 0xb9, 0xba, 0xc2, 0xc3, 0xc4, 0xc5,
    0xc6, 0xc7, 0xc8, 0xc9, 0xca, 0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda, 0xe1, 0xe2,
    0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea, 0xf1, 0xf2, 0xf3, 0xf4, 0xf5, 0xf6, 0xf7, 0xf8,
    0xf9, 0xfa,
];
const AC_CHR_BITS = [0, 2, 1, 2, 4, 4, 3, 4, 7, 5, 4, 4, 0, 1, 2, 0x77];
const AC_CHR_VALS = [
    0x00, 0x01, 0x02, 0x03, 0x11, 0x04, 0x05, 0x21, 0x31, 0x06, 0x12, 0x41, 0x51, 0x07, 0x61, 0x71,
    0x13, 0x22, 0x32, 0x81, 0x08, 0x14, 0x42, 0x91, 0xa1, 0xb1, 0xc1, 0x09, 0x23, 0x33, 0x52, 0xf0,
    0x15, 0x62, 0x72, 0xd1, 0x0a, 0x16, 0x24, 0x34, 0xe1, 0x25, 0xf1, 0x17, 0x18, 0x19, 0x1a, 0x26,
    0x27, 0x28, 0x29, 0x2a, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3a, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48,
    0x49, 0x4a, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5a, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68,
    0x69, 0x6a, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7a, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87,
    0x88, 0x89, 0x8a, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0xa2, 0xa3, 0xa4, 0xa5,
    0xa6, 0xa7, 0xa8, 0xa9, 0xaa, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6, 0xb7, 0xb8, 0xb9, 0xba, 0xc2, 0xc3,
    0xc4, 0xc5, 0xc6, 0xc7, 0xc8, 0xc9, 0xca, 0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda,
    0xe2, 0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea, 0xf2, 0xf3, 0xf4, 0xf5, 0xf6, 0xf7, 0xf8,
    0xf9, 0xfa,
];

export const ANNEX_K = {
    dcLum: {bits: DC_LUM_BITS, vals: DC_VALS},
    acLum: {bits: AC_LUM_BITS, vals: AC_LUM_VALS},
    dcChr: {bits: DC_CHR_BITS, vals: DC_VALS},
    acChr: {bits: AC_CHR_BITS, vals: AC_CHR_VALS},
};

type Code = {code: number; len: number};

// T.81 Annex C: the code of each value from BITS and HUFFVAL.
function huffCodes(bits: number[], vals: number[]): Map<number, Code> {
    const codes = new Map<number, Code>();
    let code = 0;
    let k = 0;
    for (let len = 1; len <= 16; len++) {
        for (let i = 0; i < bits[len - 1]; i++) codes.set(vals[k++], {code: code++, len});
        code <<= 1;
    }
    return codes;
}

const DC_LUM = huffCodes(DC_LUM_BITS, DC_VALS);
const DC_CHR = huffCodes(DC_CHR_BITS, DC_VALS);
const EOB_LUM = huffCodes(AC_LUM_BITS, AC_LUM_VALS).get(0)!;
const EOB_CHR = huffCodes(AC_CHR_BITS, AC_CHR_VALS).get(0)!;

class BitWriter {
    bytes: number[] = [];
    private acc = 0;
    private n = 0;

    write(value: number, len: number): void {
        for (let i = len - 1; i >= 0; i--) {
            this.acc = (this.acc << 1) | ((value >> i) & 1);
            if (++this.n === 8) this.flushByte();
        }
    }

    private flushByte(): void {
        this.bytes.push(this.acc);
        if (this.acc === 0xff) this.bytes.push(0x00);
        this.acc = 0;
        this.n = 0;
    }

    finish(): number[] {
        while (this.n !== 0) this.write(1, 1);
        return this.bytes;
    }
}

function segment(marker: number, body: number[]): number[] {
    const len = body.length + 2;
    return [0xff, marker, len >> 8, len & 0xff, ...body];
}

export function dhtSegment(): number[] {
    const body: number[] = [];
    const add = (tcth: number, t: {bits: number[]; vals: number[]}) => body.push(tcth, ...t.bits, ...t.vals);
    add(0x00, ANNEX_K.dcLum);
    add(0x10, ANNEX_K.acLum);
    add(0x01, ANNEX_K.dcChr);
    add(0x11, ANNEX_K.acChr);
    return segment(0xc4, body);
}

function exifSegment(orientation: number): number[] {
    // "Exif\0\0", then a big-endian TIFF header with one IFD entry: 0x0112 SHORT 1 <orientation>.
    const tiff = [0x4d, 0x4d, 0x00, 0x2a, 0, 0, 0, 8, 0, 1, 0x01, 0x12, 0, 3, 0, 0, 0, 1, 0, orientation, 0, 0, 0, 0, 0, 0];
    return segment(0xe1, [0x45, 0x78, 0x69, 0x66, 0, 0, ...tiff]);
}

export const SAMPLING_FACTORS: Record<Sampling, [number, number][]> = {
    '444': [[1, 1], [1, 1], [1, 1]],
    '422': [[2, 1], [1, 1], [1, 1]],
    '420': [[2, 2], [1, 1], [1, 1]],
    gray: [[1, 1]],
};

/** The YCbCr value (0 to 255) of component c at image pixel (x, y). */
export type ImageFn = (x: number, y: number) => [number, number, number];

export function encodeFlatJpeg(width: number, height: number, sampling: Sampling, image: ImageFn, options: JpegOptions = {}): Uint8Array {
    const factors = SAMPLING_FACTORS[sampling];
    const nc = factors.length;
    const hmax = Math.max(...factors.map(f => f[0]));
    const vmax = Math.max(...factors.map(f => f[1]));
    const out: number[] = [0xff, 0xd8];
    if (options.exifOrientation !== undefined) out.push(...exifSegment(options.exifOrientation));
    out.push(...segment(0xdb, [0x00, ...new Array(64).fill(16), 0x01, ...new Array(64).fill(16)]));
    const sof = [8, height >> 8, height & 0xff, width >> 8, width & 0xff, nc];
    factors.forEach(([h, v], c) => sof.push(c + 1, (h << 4) | v, c === 0 ? 0 : 1));
    out.push(...segment(0xc0, sof));
    if (!options.noDht) out.push(...dhtSegment());
    const sos = [nc];
    factors.forEach((_, c) => sos.push(c + 1, c === 0 ? 0x00 : 0x11));
    sos.push(0, 63, 0);
    out.push(...segment(0xda, sos));

    const bw = new BitWriter();
    const pred = new Array(nc).fill(0);
    const block = (c: number, bx: number, by: number) => {
        const [h, v] = factors[c];
        // the centre of the block in image pixels, clamped into the image (the padding repeats the edge)
        const x = Math.min(width - 1, Math.floor(((bx * 8 + 4) * hmax) / h));
        const y = Math.min(height - 1, Math.floor(((by * 8 + 4) * vmax) / v));
        const value = image(x, y)[c];
        const dc = Math.round(((value - 128) * 8) / 16);
        const diff = dc - pred[c];
        pred[c] = dc;
        const cat = diff === 0 ? 0 : Math.floor(Math.log2(Math.abs(diff))) + 1;
        const dcCode = (c === 0 ? DC_LUM : DC_CHR).get(cat)!;
        bw.write(dcCode.code, dcCode.len);
        if (cat > 0) bw.write(diff > 0 ? diff : diff + (1 << cat) - 1, cat);
        const eob = c === 0 ? EOB_LUM : EOB_CHR;
        bw.write(eob.code, eob.len);
    };
    if (nc === 1) {
        for (let by = 0; by < Math.ceil(height / 8); by++)
            for (let bx = 0; bx < Math.ceil(width / 8); bx++) block(0, bx, by);
    } else {
        const mcuCols = Math.ceil(width / (8 * hmax));
        const mcuRows = Math.ceil(height / (8 * vmax));
        for (let my = 0; my < mcuRows; my++)
            for (let mx = 0; mx < mcuCols; mx++)
                factors.forEach(([h, v], c) => {
                    for (let iy = 0; iy < v; iy++) for (let ix = 0; ix < h; ix++) block(c, mx * h + ix, my * v + iy);
                });
    }
    out.push(...bw.finish(), 0xff, 0xd9);
    if (options.trailingBytes) out.push(...new Array(options.trailingBytes).fill(0x5a));
    return Uint8Array.from(out);
}

/** The ring of M6: insert the Annex K DHT segment immediately before the first SOS. */
export function insertDht(jpeg: Uint8Array): Uint8Array {
    const sos = findMarker(jpeg, 0xda);
    if (sos < 0) throw new Error('no SOS');
    const dht = Uint8Array.from(dhtSegment());
    const out = new Uint8Array(jpeg.length + dht.length);
    out.set(jpeg.subarray(0, sos));
    out.set(dht, sos);
    out.set(jpeg.subarray(sos), sos + dht.length);
    return out;
}

/** The offset of the first marker 0xFF <marker> in the segment chain before the scan, or -1. */
export function findMarker(jpeg: Uint8Array, marker: number): number {
    let i = 2;
    while (i + 4 <= jpeg.length && jpeg[i] === 0xff) {
        if (jpeg[i + 1] === marker) return i;
        if (jpeg[i + 1] === 0xda) return -1;
        i += 2 + ((jpeg[i + 2] << 8) | jpeg[i + 3]);
    }
    return -1;
}

export interface SofInfo {
    width: number;
    height: number;
    components: {id: number; h: number; v: number}[];
}

export function readSof(jpeg: Uint8Array): SofInfo {
    const i = findMarker(jpeg, 0xc0);
    if (i < 0) throw new Error('no SOF0');
    const nc = jpeg[i + 9];
    const components = [];
    for (let c = 0; c < nc; c++) {
        const b = i + 10 + c * 3;
        components.push({id: jpeg[b], h: jpeg[b + 1] >> 4, v: jpeg[b + 1] & 15});
    }
    return {height: (jpeg[i + 5] << 8) | jpeg[i + 6], width: (jpeg[i + 7] << 8) | jpeg[i + 8], components};
}

// ---- The barcode image ----

export const IMAGE_WIDTH = 256;
export const IMAGE_HEIGHT = 128;
export const CELL = 16;                 // a barcode cell is 16 x 16 pixels: whole MCUs at 4:2:0
export const BARCODE_Y = 32;            // the barcode row: y from 32 to 47, below the top overlay
export const CAMERA_BITS = 4;
export const POSITION_BITS = 12;
export const ONE: [number, number, number] = [235, 128, 128];
export const ZERO: [number, number, number] = [20, 128, 128];

// The four quadrants show the rotation: top left, top right, bottom left, bottom right.
export const QUADRANTS: [number, number, number][] = [
    [81, 90, 240],   // red
    [145, 54, 34],   // green
    [41, 240, 110],  // blue
    [210, 16, 146],  // yellow
];
export const GRAY_QUADRANTS: [number, number, number][] = [[60, 128, 128], [110, 128, 128], [160, 128, 128], [210, 128, 128]];

/** The points (stored image pixels) where a test reads the quadrant colours, away from the barcode and the overlay. */
export const QUADRANT_POINTS: [number, number][] = [[32, 56], [192, 56], [32, 100], [192, 100]];

export function barcodeBits(camera: number, position: number): number[] {
    const bits: number[] = [];
    for (let i = CAMERA_BITS - 1; i >= 0; i--) bits.push((camera >> i) & 1);
    for (let i = POSITION_BITS - 1; i >= 0; i--) bits.push((position >> i) & 1);
    return bits;
}

export function barcodeImage(camera: number, position: number, gray = false): ImageFn {
    const bits = barcodeBits(camera, position);
    const quads = gray ? GRAY_QUADRANTS : QUADRANTS;
    return (x, y) => {
        if (y >= BARCODE_Y && y < BARCODE_Y + CELL) return bits[Math.floor(x / CELL)] ? ONE : ZERO;
        return quads[(y < IMAGE_HEIGHT / 2 ? 0 : 2) + (x < IMAGE_WIDTH / 2 ? 0 : 1)];
    };
}

export function barcodeJpeg(camera: number, position: number, sampling: Sampling = '422', options: JpegOptions = {}): Uint8Array {
    return encodeFlatJpeg(IMAGE_WIDTH, IMAGE_HEIGHT, sampling, barcodeImage(camera, position, sampling === 'gray'), options);
}

/** The black placeholder of M2: the size and the sampling factors of the SOF of the camera's first real frame. */
export function placeholderFor(firstReal: Uint8Array): Uint8Array {
    const sof = readSof(firstReal);
    const key = sof.components.map(c => `${c.h}${c.v}`).join(',');
    const sampling = (Object.keys(SAMPLING_FACTORS) as Sampling[])
        .find(s => SAMPLING_FACTORS[s].map(([h, v]) => `${h}${v}`).join(',') === key);
    if (!sampling) throw new Error(`no fixture sampling for ${key}`);
    return encodeFlatJpeg(sof.width, sof.height, sampling, () => [0, 128, 128]);
}

/** JFIF YCbCr to RGB, as a decoder computes it for a flat block. */
export function ycbcrToRgb([y, cb, cr]: [number, number, number]): [number, number, number] {
    const clamp = (v: number) => Math.max(0, Math.min(255, Math.round(v)));
    return [clamp(y + 1.402 * (cr - 128)), clamp(y - 0.344136 * (cb - 128) - 0.714136 * (cr - 128)), clamp(y + 1.772 * (cb - 128))];
}

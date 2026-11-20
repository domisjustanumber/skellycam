// Read the barcode and the quadrant colours of a fixture image from canvas pixels. The tile rotates the
// stored image clockwise, then fits it into the canvas ("contain"), centred (specs/player.md 8.2).
import {BARCODE_Y, CAMERA_BITS, CELL, IMAGE_HEIGHT, IMAGE_WIDTH, POSITION_BITS, QUADRANT_POINTS} from './jpeg.ts';

export type Rgb = [number, number, number];

/** The canvas pixel of the stored image point (x, y) for a canvas of w x h and a rotation. The point is
 * in the coordinates of the 256 x 128 design; `size` is the stored size, when the image is larger. */
export function canvasPoint(w: number, h: number, rotation: number, x: number, y: number, size: [number, number] = [IMAGE_WIDTH, IMAGE_HEIGHT]): [number, number] {
    const [iw, ih] = size;
    x = (x * iw) / IMAGE_WIDTH;
    y = (y * ih) / IMAGE_HEIGHT;
    const [rw, rh] = rotation % 180 === 0 ? [iw, ih] : [ih, iw];
    const scale = Math.min(w / rw, h / rh);
    const ox = (w - rw * scale) / 2;
    const oy = (h - rh * scale) / 2;
    const [rx, ry] = rotation === 90 ? [ih - y, x] : rotation === 180 ? [iw - x, ih - y] : rotation === 270 ? [y, iw - x] : [x, y];
    return [Math.floor(ox + rx * scale), Math.floor(oy + ry * scale)];
}

export interface TileReading {
    camera: number;
    position: number;
    quadrants: Rgb[];
    black: boolean;
}

export function readTile(pixel: (x: number, y: number) => Rgb, w: number, h: number, rotation: number, size?: [number, number]): TileReading {
    const at = (x: number, y: number) => pixel(...canvasPoint(w, h, rotation, x, y, size));
    const luma = ([r, g, b]: Rgb) => 0.299 * r + 0.587 * g + 0.114 * b;
    const cells = Array.from({length: CAMERA_BITS + POSITION_BITS}, (_, i) => at(i * CELL + CELL / 2, BARCODE_Y + CELL / 2));
    const bits: number[] = cells.map(c => (luma(c) > 128 ? 1 : 0));
    const value = (from: number, n: number) => bits.slice(from, from + n).reduce((a, b) => a * 2 + b, 0);
    const quadrants = QUADRANT_POINTS.map(([x, y]) => at(x, y));
    const black = [...cells, ...quadrants].every(c => Math.max(...c) < 24);
    return {camera: value(0, CAMERA_BITS), position: value(CAMERA_BITS, POSITION_BITS), quadrants, black};
}

export function near(a: Rgb, b: Rgb, tolerance = 8): boolean {
    return a.every((v, i) => Math.abs(v - b[i]) <= tolerance);
}

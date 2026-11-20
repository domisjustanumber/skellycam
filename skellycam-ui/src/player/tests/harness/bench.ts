// The page side of the benchmarks T-PLAY-65 to T-PLAY-70 (specs/player.md sections 11.3 and 12). The
// JPEGs come from the JPEG encoder of Chromium: a smooth noise pattern with the barcode of the fixtures,
// about 190 kB at 1080p [agent 33].
import {canvasPoint, readTile} from '../fixtures/barcode.ts';
import type {Rgb} from '../fixtures/barcode.ts';
import {barcodeBits, BARCODE_Y, CELL, IMAGE_HEIGHT, IMAGE_WIDTH} from '../fixtures/jpeg.ts';
import type {TakePlayer} from '../../index.ts';

const toBase64 = (b: Uint8Array) => {
    let s = '';
    for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
    return btoa(s);
};

const percentile = (values: number[], p: number) => {
    const s = [...values].sort((a, b) => a - b);
    return s.length ? s[Math.min(s.length - 1, Math.floor((p / 100) * s.length))] : NaN;
};

export interface BenchContext {
    player(): TakePlayer;
    canvases(): HTMLCanvasElement[];
}

const REF_BITS = 12;
const REF_CELL = 8;   // CSS pixels of one cell of the reference strip

export function makeBench(ctx: BenchContext) {
    let imageSize: [number, number] = [1920, 1080];
    let ref: HTMLCanvasElement | null = null;   // the reference strip: k* as 12 black or white cells
    // A getImageData of a tile canvas itself changes the player: after 10 s of such reads at N = 8, play
    // fell from 57 to 20 display refreshes/s and from 100 % to 0 % correct tiles, also after the reads
    // stopped (2026-11-19, Windows test machine). So the reader copies the barcode row of the tile into a
    // scratch canvas and reads the copy (no change of the play rate in the same test), and the play
    // benchmarks use the observer outside the page. Only `position` of the reading is valid.
    const scratch = document.createElement('canvas');
    const sg = scratch.getContext('2d', {willReadFrequently: true})!;
    const read = (i: number) => {
        const c = ctx.canvases()[i];
        const {width: w, height: h} = c;
        if (scratch.width !== w) scratch.width = w;
        if (scratch.height !== h) scratch.height = h;
        const y = canvasPoint(w, h, 0, 0, BARCODE_Y + CELL / 2, imageSize)[1];
        sg.drawImage(c, 0, y, w, 1, 0, y, w, 1);
        const d = sg.getImageData(0, 0, w, h).data;
        return readTile((x, y) => {
            const p = (Math.max(0, Math.min(h - 1, y)) * w + Math.max(0, Math.min(w - 1, x))) * 4;
            return [d[p], d[p + 1], d[p + 2]] as Rgb;
        }, w, h, 0, imageSize);
    };

    async function encode(canvas: OffscreenCanvas, camera: number, position: number, amplitude: number, seed: number): Promise<Uint8Array> {
        const {width, height} = canvas;
        const g = canvas.getContext('2d')!;
        const img = g.createImageData(width, height);
        let s = seed;
        // smooth noise: a random value for each 8 x 8 cell, so the JPEG size follows the amplitude
        const cells = new Float32Array(Math.ceil(width / 8) * Math.ceil(height / 8));
        for (let i = 0; i < cells.length; i++) cells[i] = ((s = (s * 1103515245 + 12345) % 2 ** 31) / 2 ** 31 - 0.5) * amplitude;
        const cols = Math.ceil(width / 8);
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const n = cells[(y >> 3) * cols + (x >> 3)] + (((x * 7 + y * 13) % 17) - 8) * (amplitude / 64);
                const i = (y * width + x) * 4;
                img.data[i] = 128 + n;
                img.data[i + 1] = 120 + n;
                img.data[i + 2] = 110 + n;
                img.data[i + 3] = 255;
            }
        }
        g.putImageData(img, 0, 0);
        const sx = width / IMAGE_WIDTH;
        const sy = height / IMAGE_HEIGHT;
        barcodeBits(camera, position).forEach((bit, i) => {
            g.fillStyle = bit ? '#ebebeb' : '#141414';
            g.fillRect(Math.floor(i * CELL * sx), Math.floor(BARCODE_Y * sy), Math.ceil(CELL * sx), Math.ceil(CELL * sy));
        });
        const blob = await canvas.convertToBlob({type: 'image/jpeg', quality: 0.9});
        return new Uint8Array(await blob.arrayBuffer());
    }

    return {
        /** `count` JPEGs of one camera, as base64, about `target` bytes each. */
        async jpegs(camera: number, count: number, width: number, height: number, target = 190_000): Promise<{base64: string[]; meanBytes: number}> {
            imageSize = [width, height];
            const canvas = new OffscreenCanvas(width, height);
            let amplitude = 24;
            for (let i = 0; i < 8; i++) {
                const size = (await encode(canvas, camera, 0, amplitude, 1)).length;
                if (Math.abs(size - target) < target * 0.1) break;
                amplitude *= Math.sqrt(target / size);
            }
            const out: string[] = [];
            let total = 0;
            for (let p = 0; p < count; p++) {
                const j = await encode(canvas, camera, p, amplitude, p + 1);
                total += j.length;
                out.push(toBase64(j));
            }
            return {base64: out, meanBytes: total / count};
        },

        setImageSize(width: number, height: number) {
            imageSize = [width, height];
        },

        /** Lay the tiles out in `cols` columns with the reference strip under them. Gives the window points
         * (CSS pixels) of the barcode cells of each tile and of the strip cells, for the observer. */
        layout(cols: number) {
            const box = document.getElementById('tiles')!;
            box.style.cssText = `display:flex;flex-wrap:wrap;width:${cols * 520}px`;
            ref?.remove();
            ref = document.createElement('canvas');
            ref.width = REF_BITS * REF_CELL;
            ref.height = REF_CELL;
            ref.style.cssText = `display:block;margin:4px;width:${REF_BITS * REF_CELL}px;height:${REF_CELL}px`;
            document.body.append(ref);
            const r = (e: Element) => {
                const b = e.getBoundingClientRect();
                return {x: b.left, y: b.top, w: b.width, h: b.height};
            };
            const tiles = ctx.canvases().map(c => {
                const b = r(c);
                return Array.from({length: 16}, (_, i) => {
                    const [x, y] = canvasPoint(c.width, c.height, 0, i * CELL + CELL / 2, BARCODE_Y + CELL / 2, imageSize);
                    return [b.x + (x * b.w) / c.width, b.y + (y * b.h) / c.height];
                });
            });
            const rb = r(ref);
            const refPts = Array.from({length: REF_BITS}, (_, i) => [rb.x + i * REF_CELL + REF_CELL / 2, rb.y + REF_CELL / 2]);
            return {tiles, ref: refPts, innerWidth};
        },

        /** T-PLAY-65: readers x fps range reads of `size` bytes for `seconds`; a tick is dropped when
         * the read of the tick before is still in flight. */
        async transport(url: string, fileSize: number, readers: number, fps: number, size: number, seconds: number) {
            let ticks = 0;
            let dropped = 0;
            let failed = 0;
            const busy = new Array(readers).fill(false);
            const end = performance.now() + seconds * 1000;
            await new Promise<void>(resolve => {
                const timer = setInterval(() => {
                    if (performance.now() >= end) {
                        clearInterval(timer);
                        resolve();
                        return;
                    }
                    for (let r = 0; r < readers; r++) {
                        ticks++;
                        if (busy[r]) {
                            dropped++;
                            continue;
                        }
                        busy[r] = true;
                        const start = Math.floor(Math.random() * (fileSize - size));
                        fetch(url, {cache: 'no-store', headers: {Range: `bytes=${start}-${start + size - 1}`}})
                            .then(async res => {
                                if (res.status !== 206 || (await res.arrayBuffer()).byteLength !== size) failed++;
                            })
                            .catch(() => void failed++)
                            .finally(() => (busy[r] = false));
                    }
                }, 1000 / fps);
            });
            return {ticks, dropped, failed, droppedPercent: (100 * dropped) / ticks};
        },

        /** T-PLAY-69: IPC round trips while something else runs. */
        async ipc(seconds: number, invoke: () => Promise<unknown>) {
            const rtts: number[] = [];
            const end = performance.now() + seconds * 1000;
            while (performance.now() < end) {
                const t0 = performance.now();
                await invoke();
                rtts.push(performance.now() - t0);
                await new Promise(r => setTimeout(r, 50));
            }
            return {count: rtts.length, p50: percentile(rtts, 50), p95: percentile(rtts, 95), max: Math.max(...rtts)};
        },

        /** T-PLAY-66, T-PLAY-70: at each display refresh, draw k* into the reference strip. The observer
         * outside the page compares the strip with each tile in the same captured frame; the page reads no
         * tile. Call it after play(): its frame callback then runs after the clock tick of the player. */
        async watch(seconds: number, warmupSeconds = 1) {
            const g = ref!.getContext('2d')!;
            let refreshes = 0;
            const start = performance.now();
            await new Promise<void>(resolve => {
                const step = () => {
                    const now = performance.now();
                    if (now - start > seconds * 1000) return resolve();
                    const k = ctx.player().state.frame;
                    for (let i = 0; i < REF_BITS; i++) {
                        g.fillStyle = (k >> (REF_BITS - 1 - i)) & 1 ? '#fff' : '#000';
                        g.fillRect(i * REF_CELL, 0, REF_CELL, REF_CELL);
                    }
                    if (now - start > warmupSeconds * 1000) refreshes++;
                    requestAnimationFrame(step);
                };
                requestAnimationFrame(step);
            });
            const end = performance.now();
            return {refreshes, refreshesPerSecond: refreshes / ((end - start) / 1000 - warmupSeconds),
                from: performance.timeOrigin + start + warmupSeconds * 1000, to: performance.timeOrigin + end};
        },

        /** T-PLAY-67: seeks; the time from seekFrame to the draw of every tile. It polls with a task loop, not
         * with requestAnimationFrame, which gave a floor of one refresh (about 17 ms) to each time. */
        async seeks(count: number, frameCount: number, cycle: number) {
            const n = ctx.canvases().length;
            const times: number[] = [];
            const channel = new MessageChannel();
            const nextTask = () => new Promise<void>(resolve => {
                channel.port1.onmessage = () => resolve();
                channel.port2.postMessage(0);
            });
            for (let s = 0; s < count; s++) {
                const k = (s * 7919) % frameCount;
                const t0 = performance.now();
                ctx.player().seekFrame(k);
                const pending = new Set(Array.from({length: n}, (_, i) => i));
                while (performance.now() - t0 <= 2000) {
                    for (const i of pending) if (read(i).position === k % cycle) pending.delete(i);
                    if (!pending.size) break;
                    await nextTask();
                }
                times.push(performance.now() - t0);
            }
            return {p50: percentile(times, 50), p95: percentile(times, 95), max: Math.max(...times)};
        },

        /** T-PLAY-68: a drag at `fps` frames per second, one input each 16 ms. */
        async scrub(seconds: number, fps: number, frameCount: number, cycle: number) {
            const n = ctx.canvases().length;
            const shown: Set<number>[] = Array.from({length: n}, () => new Set<number>());
            const lags: number[] = [];
            const start = performance.now();
            let target = 0;
            let refreshes = 0;
            const input = setInterval(() => {
                target = Math.floor(((performance.now() - start) / 1000) * fps) % frameCount;
                ctx.player().seekFrame(target);
            }, 16);
            await new Promise<void>(resolve => {
                const step = () => {
                    if (performance.now() - start > seconds * 1000) return resolve();
                    refreshes++;
                    for (let i = 0; i < n; i++) {
                        const p = read(i).position;
                        shown[i].add(Math.floor((performance.now() - start) / 1000) * 100000 + p);
                        if (i === 0) lags.push((target % cycle) - p);
                    }
                    requestAnimationFrame(step);
                };
                requestAnimationFrame(step);
            });
            clearInterval(input);
            return {shownPerSecond: shown.map(s => s.size / seconds), refreshesPerSecond: refreshes / seconds, lagMedian: percentile(lags.filter(l => l >= 0), 50)};
        },
    };
}

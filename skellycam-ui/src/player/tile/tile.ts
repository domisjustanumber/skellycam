// The shared tile: decode a JPEG with ImageDecoder and draw it on a canvas, with its overlay
// (specs/player.md section 8). The player and the live preview use it [Y3, L6]. It imports nothing
// of the take reader.
import {formatFrame, formatTime} from './format.ts';

export interface DecodedImage {
    displayWidth: number;
    displayHeight: number;
    close(): void;
}

export type JpegDecoder = (jpeg: Uint8Array) => Promise<DecodedImage>;

export type CameraStateName = 'starting' | 'waiting' | 'failed' | 'checking' | 'too_slow' | 'ready' | 'recording' | 'dead';

export type TileMark =
    | {kind: 'not_readable'; reason: string}
    | {kind: 'read_error'}
    | {kind: 'damaged'; frame: number}
    | {kind: 'camera_lost'; frame: number}
    | {kind: 'no_frame'}
    | {kind: 'flagged'}
    | {kind: 'unfinished'};

export interface TileLabel {
    frame: number;
    frameDigits: number;
    camera: string;
    timeNs: number | null;
    nominalFps: number;
}

export interface TileUpdate {
    jpeg: Uint8Array | null;
    rotationCwDeg: 0 | 90 | 180 | 270;
    label: TileLabel | null;
    rateText: string | null;
    cameraState: CameraStateName | null;
    mark: TileMark | null;
    image?: DecodedImage;
    blank?: boolean;
}

/** The texts of the overlay; `{reason}` and `{frame}` are replaced. `time_title` is the canvas title. */
export type TileTexts = Record<TileMark['kind'] | CameraStateName | 'time_title', string>;

export interface TileOptions {
    showLabel: boolean;
    timeFormat: 'seconds' | 'timecode';
    texts: TileTexts;
}

export interface TileOverlay {
    frame: string | null;
    camera: string | null;
    time: string | null;
    rate: string | null;
    state: string | null;
    mark: string | null;
}

const TEXTS: TileTexts = {
    not_readable: 'camera file not readable: {reason}', read_error: 'read error', damaged: 'damaged at frame {frame}',
    camera_lost: 'camera lost at frame {frame}', no_frame: 'no frame', flagged: 'flagged frame', unfinished: 'unfinished',
    starting: 'starting', waiting: 'waiting', failed: 'failed', checking: 'checking', too_slow: 'too_slow', ready: 'ready',
    recording: 'recording', dead: 'dead', time_title: 'timestamp from recording',
};

const FONT_PX = 12;
const PAD = 4;

/** ImageDecoder, with the EXIF orientation undone: the tile shows the stored pixels (8.1). */
export async function decodeJpeg(jpeg: Uint8Array): Promise<DecodedImage> {
    const decoder = new ImageDecoder({data: jpeg as Uint8Array<ArrayBuffer>, type: 'image/jpeg'});
    try {
        const {image} = await decoder.decode();
        const {rotation, flip} = image as VideoFrame & {rotation: number; flip: boolean};
        if (!rotation && !flip) return image;
        try {
            return new VideoFrame(image, {rotation: flip ? rotation : (360 - rotation) % 360, flip} as VideoFrameInit);
        } finally {
            image.close();
        }
    } finally {
        decoder.close();
    }
}

type Pending = {u: TileUpdate; seq: number; resolve: (r: 'drawn' | 'superseded') => void};

export class Tile {
    overlay: TileOverlay = {frame: null, camera: null, time: null, rate: null, state: null, mark: null};
    #canvas: HTMLCanvasElement;
    #decode: JpegDecoder;
    #options: TileOptions;
    #image: DecodedImage | null = null;
    #rotation = 0;
    #last: Pick<TileUpdate, 'label' | 'rateText' | 'cameraState' | 'mark'> = {label: null, rateText: null, cameraState: null, mark: null};
    #seq = 0;
    #decoding = false;
    #pending: Pending | null = null;
    #observer: ResizeObserver | null = null;
    #closed = false;

    constructor(canvas: HTMLCanvasElement, options: Partial<TileOptions> = {}, seams: {decode?: JpegDecoder} = {}) {
        this.#canvas = canvas;
        this.#decode = seams.decode ?? decodeJpeg;
        this.#options = {showLabel: true, timeFormat: 'timecode', ...options, texts: {...TEXTS, ...options.texts}};
        if (typeof ResizeObserver !== 'undefined') {
            this.#observer = new ResizeObserver(() => this.#draw());
            this.#observer.observe(canvas);
        }
        this.#draw();
    }

    /** Newest wins: an update supersedes an update whose decode has not ended (8.3). */
    update(u: TileUpdate): Promise<'drawn' | 'superseded'> {
        if (this.#closed) {
            u.image?.close();
            return Promise.resolve('superseded');
        }
        const seq = ++this.#seq;
        this.#dropPending();
        if (u.jpeg === null || u.image || u.blank) {
            if (u.blank || u.image) this.#setImage(u.image ?? null, u.rotationCwDeg);
            this.#apply(u);
            return Promise.resolve('drawn');
        }
        return new Promise(resolve => {
            this.#pending = {u, seq, resolve};
            this.#next();
        });
    }

    setOptions(o: Partial<TileOptions>): void {
        this.#options = {...this.#options, ...o, texts: {...this.#options.texts, ...o.texts}};
        this.#draw();
    }

    close(): void {
        this.#closed = true;
        this.#observer?.disconnect();
        this.#dropPending();
        this.#setImage(null, 0);
    }

    #dropPending(): void {
        this.#pending?.resolve('superseded');
        this.#pending = null;
    }

    #next(): void {
        const p = this.#pending;
        if (this.#decoding || !p) return;
        this.#pending = null;
        this.#decoding = true;
        const done = (image: DecodedImage | null) => {
            this.#decoding = false;
            if (this.#closed || p.seq !== this.#seq) {
                image?.close();
                p.resolve('superseded');
            } else {
                // a JPEG that does not decode keeps the last image
                if (image) this.#setImage(image, p.u.rotationCwDeg);
                this.#apply(p.u);
                p.resolve('drawn');
            }
            this.#next();
        };
        this.#decode(p.u.jpeg!).then(done, () => done(null));
    }

    #setImage(image: DecodedImage | null, rotation: number): void {
        if (this.#image !== image) this.#image?.close();
        this.#image = image;
        this.#rotation = rotation;
    }

    #apply(u: TileUpdate): void {
        this.#last = {label: u.label, rateText: u.rateText, cameraState: u.cameraState, mark: u.mark};
        this.#draw();
    }

    #draw(): void {
        if (this.#closed) return;
        const c = this.#canvas;
        const dpr = (globalThis as {devicePixelRatio?: number}).devicePixelRatio ?? 1;
        if (c.clientWidth > 0 && c.clientHeight > 0) {
            const w = Math.round(c.clientWidth * dpr);
            const h = Math.round(c.clientHeight * dpr);
            if (c.width !== w) c.width = w;
            if (c.height !== h) c.height = h;
        }
        const ctx = c.getContext('2d');
        if (!ctx) return;
        const {width: w, height: h} = c;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, w, h);
        const img = this.#image;
        if (img) {
            // rotate clockwise, then contain (8.2)
            const [iw, ih] = [img.displayWidth, img.displayHeight];
            const turned = this.#rotation % 180 !== 0;
            const scale = Math.min(w / (turned ? ih : iw), h / (turned ? iw : ih));
            ctx.translate(w / 2, h / 2);
            ctx.rotate((this.#rotation * Math.PI) / 180);
            ctx.drawImage(img as unknown as CanvasImageSource, (-iw * scale) / 2, (-ih * scale) / 2, iw * scale, ih * scale);
            ctx.setTransform(1, 0, 0, 1, 0, 0);
        }
        this.#drawOverlay(ctx, w, h, dpr);
    }

    #drawOverlay(ctx: CanvasRenderingContext2D, w: number, h: number, dpr: number): void {
        const {label, rateText, cameraState, mark} = this.#last;
        const {showLabel, timeFormat, texts} = this.#options;
        const showing = showLabel && label !== null;
        const markText = mark && texts[mark.kind]
            .replace('{reason}', 'reason' in mark ? mark.reason : '')
            .replace('{frame}', 'frame' in mark ? String(mark.frame) : '');
        this.overlay = {
            frame: showing ? formatFrame(label.frame, label.frameDigits) : null,
            camera: showing ? label.camera : null,
            time: showing ? formatTime(label.timeNs, timeFormat, label.nominalFps) : null,
            rate: rateText,
            state: cameraState && texts[cameraState],
            mark: markText,
        };
        this.#canvas.title = this.overlay.time !== null ? texts.time_title : '';

        const px = FONT_PX * dpr;
        const pad = PAD * dpr;
        const line = px + 2 * pad;
        ctx.font = `${px}px monospace`;
        ctx.textBaseline = 'middle';
        const box = (text: string | null, x: number, y: number, align: 'left' | 'right' | 'center', colour = '#fff') => {
            if (!text) return;
            const tw = ctx.measureText(text).width + 2 * pad;
            const left = align === 'left' ? x : align === 'right' ? x - tw : x - tw / 2;
            ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
            ctx.fillRect(left, y, tw, line);
            ctx.fillStyle = colour;
            ctx.fillText(text, left + pad, y + line / 2);
        };
        const o = this.overlay;
        box(o.state, 0, 0, 'left');
        box(o.frame, w, 0, 'right', '#00ff88');
        // the rate text is under the camera part, so the camera part moves up one line when it shows
        box(o.camera, 0, h - line * (o.rate ? 2 : 1), 'left');
        box(o.rate, 0, h - line, 'left');
        box(o.time, w, h - line, 'right');
        box(o.mark, w / 2, h / 2 - line / 2, 'center', '#ffcc00');
    }
}

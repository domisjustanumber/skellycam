// The flow control of the preview for each camera (specs/preview-4b.md 5.3, 5.4): the newest pending camera message,
// one tile update in flight, one ready message for each draw. Only type imports: the Node unit tests load this file.
import type {CameraStateName, Tile, TileMark, TileUpdate} from '../../../player/index.ts';
import {parseCameraMessage} from './camera-message.ts';
import type {CameraMessage} from './camera-message.ts';

type TileLike = Pick<Tile, 'update'>;

export interface OverlayValues {
    label: string | null;
    cameraState: CameraStateName | null;
    rateText: string | null;
}

interface CameraEntry extends OverlayValues {
    pending: CameraMessage | null;
    busy: boolean;
    overlayChanged: boolean;
    lastFrame: number | null;   // the frame number of the last frame given to the tile; null before the first
    lastMark: TileMark | null;
    lastRotation: 0 | 90 | 180 | 270;
}

const FLAGGED: TileMark = {kind: 'flagged'};

export class PreviewTiles {
    readonly tiles = new Map<string, TileLike>();
    readonly drawnCount = new Map<string, number>();   // updates that resolved 'drawn' with a JPEG
    private readonly cameras = new Map<string, CameraEntry>();
    private readonly loggedReasons = new Set<string>();   // one console.error for each reason and connection
    private paused = false;
    private first = 0;   // the camera that gets its update first turns at each refresh [Q893]
    private readonly sendReady: (cameraId: string) => void;
    private readonly onDrawn: (cameraId: string, atMs: number) => void;
    private readonly now: () => number;

    constructor(sendReady: (cameraId: string) => void,
                onDrawn: (cameraId: string, atMs: number) => void = () => {},
                now: () => number = () => performance.now()) {
        this.sendReady = sendReady;
        this.onDrawn = onDrawn;
        this.now = now;
    }

    private entry(cameraId: string): CameraEntry {
        let e = this.cameras.get(cameraId);
        if (!e) {
            e = {pending: null, busy: false, overlayChanged: false, label: null, cameraState: null, rateText: null,
                lastFrame: null, lastMark: null, lastRotation: 0};
            this.cameras.set(cameraId, e);
        }
        return e;
    }

    setTile(cameraId: string, tile: TileLike | null): void {
        if (tile) {
            this.tiles.set(cameraId, tile);
            return;
        }
        this.tiles.delete(cameraId);
        this.cameras.delete(cameraId);   // rule 9: the pending message and the state of the camera go
    }

    /** One binary websocket message (rule 1). A refused message is dropped and gets no ready message (5.2). */
    receive(data: ArrayBuffer): void {
        let message: CameraMessage;
        try {
            message = parseCameraMessage(data);
        } catch (error) {
            const reason = error instanceof Error ? error.message : String(error);
            if (!this.loggedReasons.has(reason)) {
                this.loggedReasons.add(reason);
                console.error(`Preview: a camera message is refused: ${reason}`);
            }
            return;
        }
        this.entry(message.cameraId).pending = message;
    }

    setOverlay(cameraId: string, values: Partial<OverlayValues>): void {
        const e = this.entry(cameraId);
        for (const key of ['label', 'cameraState', 'rateText'] as const) {
            if (key in values && values[key] !== e[key]) {
                (e as OverlayValues)[key] = values[key] as never;
                e.overlayChanged = true;
            }
        }
    }

    setPaused(paused: boolean): void {
        this.paused = paused;
    }

    /** Rule 10: the connection closed. The tiles and their images stay. */
    clearPending(): void {
        for (const e of this.cameras.values()) e.pending = null;
        this.loggedReasons.clear();
    }

    /** One display refresh (rules 2 to 7). */
    tick(): void {
        if (this.paused) return;
        const order = [...this.tiles];
        this.first = order.length ? (this.first + 1) % order.length : 0;
        for (const [cameraId, tile] of [...order.slice(this.first), ...order.slice(0, this.first)]) {
            const e = this.entry(cameraId);
            if (e.busy) continue;
            const message = e.pending;
            if (!message && !e.overlayChanged) continue;
            e.pending = null;
            e.overlayChanged = false;
            if (message) {
                e.lastFrame = Number(message.frameNumber);
                e.lastMark = message.jpeg === null ? FLAGGED : null;
                e.lastRotation = message.rotationCwDeg;
            }
            const update: TileUpdate = {
                jpeg: message ? message.jpeg : null,
                rotationCwDeg: e.lastRotation,
                label: {frame: e.lastFrame, frameDigits: 6, camera: e.label ?? '', timeNs: null, nominalFps: 0},
                rateText: e.rateText,
                cameraState: e.cameraState,
                mark: e.lastMark,
            };
            e.busy = true;
            void tile.update(update).then(result => {
                e.busy = false;
                if (!message) return;   // an overlay update: no ready message, no draw count (rule 5)
                if (result === 'drawn' && message.jpeg !== null) {
                    this.drawnCount.set(cameraId, (this.drawnCount.get(cameraId) ?? 0) + 1);
                    this.onDrawn(cameraId, this.now());
                }
                this.sendReady(cameraId);
            }, error => {
                e.busy = false;   // a failed update must not hold the camera; the safety net of the server sends again
                console.error(`Preview: a tile update of camera ${cameraId} failed:`, error);
            });
        }
    }
}

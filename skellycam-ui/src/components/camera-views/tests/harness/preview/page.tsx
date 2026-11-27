// The harness page `preview` of the step 4b component tests and benchmarks (specs/preview-4b.md 7.2). It
// mounts the real ServerContextProvider and CameraViewsGrid with the store of the app, seeds the camera list
// with fake detected cameras, and points the provider at ui_server.py (127.0.0.1, never 53117). Only this page
// puts the PreviewTiles of the provider on `window.__previewTiles`. The page reads no canvas back: it gives
// the outside observer the place of each tile from getBoundingClientRect() and canvasPoint (layout). The
// tests call `window.preview`.
import {useEffect, useState} from 'react';
import ReactDOM from 'react-dom/client';
import {Provider} from 'react-redux';
import '@/index.css';
import i18n from '@/i18n/i18n';
import {store} from '@/store';
import {ServerContextProvider, useServer} from '@/services/server/ServerContextProvider';
import {serverUrls} from '@/services/server/server-helpers/server-urls';
import {CameraViewsGrid} from '@/components/camera-views/CameraViewsGrid';
import {RecordingGuardProvider} from '@/components/RecordingGuardProvider';
import FramerateViewerPanel from '@/components/framerate-viewer/FrameRateViewer';
import {detectCameras} from '@/store/slices/cameras/cameras-thunks';
import {createDefaultCameraConfig} from '@/store/slices/cameras/cameras-types';
import type {Camera} from '@/store/slices/cameras/cameras-types';
import type {TileOverlay} from '@/player/index.ts';
import type {PreviewTiles} from '@/services/server/preview/preview-tiles';
import {canvasPoint} from '../../../../../player/tests/fixtures/barcode.ts';
import {BARCODE_Y, CELL} from '../../../../../player/tests/fixtures/jpeg.ts';

export interface SeedCamera {
    id: string;
    index: number;   // the camera list number
    name: string;
}

export type ViewerMode = 'full' | 'collapsed' | null;

export interface StartOptions {
    port: number;
    cameras: SeedCamera[];
    viewer?: ViewerMode;
    gridHeight?: number;
}

type Server = ReturnType<typeof useServer>;
// 4b names (specs/preview-4b.md 5.3, 5.5): the provider gives these two; today's provider does not
type Server4b = Server & {getPreviewTiles?: () => PreviewTiles; gridCameraIds?: string[]};

declare global {
    interface Window {
        preview: typeof preview;
        __previewTiles?: PreviewTiles;
        harnessIpc: {invoke(channel: string, ...args: unknown[]): Promise<unknown>; send(channel: string, ...args: unknown[]): void; productError(): Promise<string | null>};
    }
}

const HOST = '127.0.0.1';
const GRID_WIDTH = 1380;

let server: Server4b | null = null;
let setViewerMode: (mode: ViewerMode) => void = () => {};
let root: ReactDOM.Root | null = null;
const stateLog: {state: string; at: number}[] = [];
const notes: string[] = [];

function seedCamera({id, index, name}: SeedCamera): Camera {
    const config = createDefaultCameraConfig(id, index, name);
    return {
        id, index, name, actualConfig: config, desiredConfig: {...config}, hasConfigMismatch: false,
        connectionStatus: 'available', selected: true, deviceInfo: {usbLink: 'USB 3'},
    };
}

/** Gives the tests the provider value, the connection states with their times and the PreviewTiles. */
function Bridge() {
    const value = useServer() as Server4b;
    server = value;
    useEffect(() => {
        stateLog.push({state: String(value.connectionState), at: Date.now()});
    }, [value.connectionState]);
    useEffect(() => {
        if (typeof value.getPreviewTiles === 'function') window.__previewTiles = value.getPreviewTiles();
        else if (!notes.includes('no getPreviewTiles')) notes.push('no getPreviewTiles');
    }, [value]);
    return null;
}

function Root({options}: {options: StartOptions}) {
    const [viewer, setViewer] = useState<ViewerMode>(options.viewer ?? null);
    setViewerMode = setViewer;
    const gridHeight = options.gridHeight ?? (viewer ? 600 : 980);
    return (
        <Provider store={store}>
            <ServerContextProvider>
                <RecordingGuardProvider>
                    <Bridge/>
                    <div id="grid" style={{width: GRID_WIDTH, height: gridHeight, position: 'relative', overflow: 'hidden'}}>
                        <CameraViewsGrid manualColumns={null} resetKey={0}/>
                    </div>
                    {viewer && (
                        <div id="viewer" style={{width: GRID_WIDTH, height: 380}}>
                            <FramerateViewerPanel isCollapsed={viewer === 'collapsed'}/>
                        </div>
                    )}
                </RecordingGuardProvider>
            </ServerContextProvider>
        </Provider>
    );
}

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

function tileCanvas(id: string): HTMLCanvasElement | null {
    return document.querySelector<HTMLCanvasElement>(`#grid canvas[data-camera-id="${CSS.escape(id)}"]`);
}

const text = (e: Element | null | undefined) => (e?.textContent ?? '').replace(/\s+/g, ' ').trim();

const preview = {
    productError: async () => (await window.harnessIpc.productError()) ?? null,

    /** Seed the camera list, mount, set the server host and port, then connect. */
    async start(options: StartOptions): Promise<void> {
        if (options.port === 53117) throw new Error('never the port of the product server');
        serverUrls.setHost(HOST);
        serverUrls.setPort(options.port);
        await i18n.changeLanguage('en');
        store.dispatch(detectCameras.fulfilled(options.cameras.map(seedCamera), 'preview-harness-seed', undefined));
        root ??= ReactDOM.createRoot(document.getElementById('root')!);
        root.render(<Root options={options}/>);
        for (let i = 0; i < 200 && !server; i++) await sleep(10);
        if (!server) throw new Error('the provider did not mount');
        server.updateServerConnection(HOST, options.port);
        server.connect();
    },

    connect: () => server?.connect(),
    notes: () => notes.slice(),
    connectionState: () => (server ? String(server.connectionState) : null),
    stateLog: () => stateLog.slice(),
    connectedCameraIds: () => server?.connectedCameraIds ?? null,
    gridCameraIds: () => server?.gridCameraIds ?? null,
    visibility: () => document.visibilityState,

    /** The camera ids of the tiles of `window.__previewTiles`, or null when it is not set. */
    tileIds: () => (window.__previewTiles ? [...window.__previewTiles.tiles.keys()] : null),

    /** The kept overlay of the tile of a camera (`Tile.overlay`), or null. Product state, not a pixel read. */
    overlay: (id: string): TileOverlay | null =>
        (window.__previewTiles?.tiles.get(id) as {overlay?: TileOverlay} | undefined)?.overlay ?? null,

    /** The draw count of the product (a claim of the product about itself, 6.1). */
    drawnCount: (): Record<string, number> | null => (window.__previewTiles ? Object.fromEntries(window.__previewTiles.drawnCount) : null),

    /** The tile canvases of the grid in DOM order, with their places. */
    cells: () => [...document.querySelectorAll<HTMLCanvasElement>('#grid canvas[data-camera-id]')].map(c => {
        const b = c.getBoundingClientRect();
        return {id: c.dataset.cameraId!, top: Math.round(b.top), left: Math.round(b.left), width: c.width, height: c.height};
    }),

    emptyState: () => document.querySelector('#grid .camera-grid-empty-state-container') !== null,

    /** The window points of the 16 barcode cells of each tile (rotation 0), for the observer. A camera with no
     * tile canvas (or a canvas with no size yet) is in `missing` and has no points. */
    layout(ids: string[], imageSize: [number, number]) {
        const missing: string[] = [];
        const tiles = ids.map(id => {
            const c = tileCanvas(id);
            if (!c || !c.width || !c.height) {
                missing.push(id);
                return [];
            }
            const b = c.getBoundingClientRect();
            return Array.from({length: 16}, (_, i) => {
                const [x, y] = canvasPoint(c.width, c.height, 0, i * CELL + CELL / 2, BARCODE_Y + CELL / 2, imageSize);
                return [b.left + (x * b.width) / c.width, b.top + (y * b.height) / c.height];
            });
        });
        return {tiles, missing, innerWidth};
    },

    setViewer: (mode: ViewerMode) => setViewerMode(mode),

    /** The DOM and SVG of the frame rate viewer (specs/preview-4b.md 5.8). No tile. */
    viewer() {
        const box = document.getElementById('viewer');
        const full = box?.querySelector('.framerate-viewer');
        const collapsed = box?.querySelector('.framerate-collapsed-summary');
        const table = full?.querySelector('table');
        const headers = table ? [...table.querySelectorAll('thead th')].map(th => text(th)) : [];
        const rows = table ? [...table.querySelectorAll('tbody tr')]
            .map(tr => [...tr.querySelectorAll('td')].map(td => text(td.querySelector('.stats-cell-primary') ?? td)))
            .filter(cells => cells.length > 1) : [];
        const svgTexts = full ? [...full.querySelectorAll('svg text')].map(t => text(t)).filter(Boolean) : [];
        // an HTML legend: the text of the full view outside the table and the SVG
        const rest = full?.cloneNode(true) as Element | undefined;
        rest?.querySelectorAll('table, svg').forEach(e => e.remove());
        const legendText = rest ? text(rest) : '';
        const painted = (v: string) => !!v && v !== 'none' && v !== 'rgba(0, 0, 0, 0)';
        const series = full ? [...full.querySelectorAll('svg [data-series]')].map(e => {
            const style = getComputedStyle(e);
            // a bar (rect) shows its fill; a line shows its stroke
            const order = e.tagName.toLowerCase() === 'rect' ? [style.fill, style.stroke] : [style.stroke, style.fill];
            return {camera: e.getAttribute('data-camera-id'), series: e.getAttribute('data-series'),
                colour: order.find(painted) ?? '', dash: style.strokeDasharray};
        }) : [];
        return {full: !!full, collapsed: collapsed ? text(collapsed) : null, headers, rows, svgTexts, legendText, series};
    },
};

export type PreviewApi = typeof preview;
window.preview = preview;

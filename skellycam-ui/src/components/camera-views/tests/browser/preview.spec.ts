// Component tests of the step 4b preview with fake rings: T-PRV-43, T-PRV-47, T-PRV-48 (specs/preview-4b.md 7.4).
// ui_server.py in a subprocess; the harness page `preview` with the real ServerContextProvider, CameraViewsGrid,
// PreviewTiles and Tile. The images are checked only with the outside observer; the overlay is the kept
// `Tile.overlay` (product state). The thresholds are loose, so that a slow runner passes.
import {expect} from '@playwright/test';
import {captureOnce, observe, readings} from '../../../../player/tests/harness/observer.ts';
import {
    connectionNumbers, counts, describe, geometry, otherErrors, overlayFrame, requirePreviewTiles, sameReading, SIZE_640,
    sleep, test, toCaptures, waitDrawn, waitLayoutSettled, watch, written,
} from './preview-kit.ts';
import type {Capture} from './preview-kit.ts';

interface Cam {
    id: string;
    number: number;   // the camera number of the barcode
    list: number;     // the camera list number in the store
    name: string;
}

const serverCameras = (cams: Cam[]) => cams.map(c => ({id: c.id, number: c.number, index: 90 + c.number, name: `ring ${c.id}`}));
const seed = (cams: Cam[]) => cams.map(c => ({id: c.id, index: c.list, name: c.name}));
const label = (c: Cam) => `Camera ${c.list} · ${c.name}`;

test('T-PRV-43 three cameras at 30 fps: each tile shows its own camera', async ({preview}) => {
    const cams: Cam[] = [
        {id: 'c1', number: 1, list: 5, name: 'Alpha cam'},
        {id: 'c2', number: 2, list: 2, name: 'Beta cam'},
        {id: 'c3', number: 3, list: 7, name: 'Gamma cam'},
    ];
    const ids = cams.map(c => c.id);
    const server = await preview.server({cameras: serverCameras(cams), fps: 30});
    const win = await preview.open(server, seed(cams));
    const connected = Date.now();
    await requirePreviewTiles(win.page);
    await waitDrawn(win.page, ids);
    await sleep(Math.max(0, connected + 1000 - Date.now()));

    // the last 4 s of a 5 s run
    const before = await written(server);
    const from = Date.now();
    const captures = await watch(win, ids, 4000);
    const to = Date.now();
    const after = await written(server);

    expect(captures.length, 'the observer got captures').toBeGreaterThan(20);
    for (const c of cams) {
        const wrong = captures.filter(k => {
            const r = k.tiles[c.id];
            return typeof r === 'string' || r.camera !== c.number;
        });
        expect(wrong.map(k => describe(k.tiles[c.id])).slice(0, 5), `tile ${c.id}: each capture reads camera ${c.number}`).toEqual([]);
        let changes = 0;
        for (let i = 1; i < captures.length; i++) if (!sameReading(captures[i].tiles[c.id], captures[i - 1].tiles[c.id])) changes++;
        expect(changes / (captures.length - 1), `tile ${c.id}: the frame number changes in at least 50 % of consecutive captures`).toBeGreaterThanOrEqual(0.5);
    }

    const n = await counts(server, from, to);
    const [only] = connectionNumbers(n);
    for (const c of cams) {
        const frames = after[c.id] - before[c.id];
        const ready = n.connections[only]?.cameras[c.id]?.ready.length ?? 0;
        expect(ready, `camera ${c.id}: ready messages for at least 80 % of the ${frames} frames`).toBeGreaterThanOrEqual(0.8 * frames);
    }

    for (const c of cams) {
        const o = await win.page.evaluate(id => window.preview.overlay(id), c.id);
        expect(o?.camera, `the camera list label of ${c.id}`).toBe(label(c));
        expect(o?.state, `the state of ${c.id}`).toBe('ready');
        const rate = /^(\d+(?:\.\d)?) fps$/.exec(o?.rate ?? '');
        expect(rate, `a rate text of ${c.id}: ${o?.rate}`).not.toBeNull();
        expect(Math.abs(Number(rate![1]) - 30), `the rate text of ${c.id}: 30.0 ± 0.5 fps`).toBeLessThanOrEqual(0.5);
    }
});

test('T-PRV-47 reconnect, then give up', async ({preview}) => {
    const cams: Cam[] = [
        {id: 'r1', number: 1, list: 3, name: 'Left cam'},
        {id: 'r2', number: 2, list: 1, name: 'Right cam'},
    ];
    const ids = cams.map(c => c.id);
    const server = await preview.server({cameras: serverCameras(cams), fps: 30});
    const win = await preview.open(server, seed(cams));
    await requirePreviewTiles(win.page);
    await waitDrawn(win.page, ids);
    await waitLayoutSettled(win.page, ids);   // the tiles still move after the first draw (open work)

    await observe(win.app, await geometry(win.page, ids, SIZE_640), win.windowId);
    await sleep(1000);
    const closed = Date.now();
    await server.command({cmd: 'close_connections'});
    await expect.poll(async () => {
        const log = await win.page.evaluate(() => window.preview.stateLog());
        const r = log.findIndex(e => e.at >= closed && e.state === 'RECONNECTING');
        const back = r >= 0 && log.slice(r + 1).some(e => e.state === 'CONNECTED');
        // Q867: a still window gives no capture; force one while RECONNECTING (spec 7.2)
        if (r >= 0 && !back) await captureOnce(win.app, win.windowId);
        return back;
    }, {message: 'the UI goes RECONNECTING, then CONNECTED again', timeout: 15_000, intervals: [100]}).toBe(true);
    const log = await win.page.evaluate(() => window.preview.stateLog());
    const r = log.findIndex(e => e.at >= closed && e.state === 'RECONNECTING');
    const reconnecting = log[r].at;
    const back = log.slice(r + 1).find(e => e.state === 'CONNECTED')!.at;
    await sleep(Math.max(0, back + 3000 - Date.now()));
    const captures = toCaptures(await readings(win.app, win.windowId), ids);

    // a draw that was in flight at the close can still land in the first 100 ms
    const during = captures.filter(k => k.at >= reconnecting + 100 && k.at <= back);
    const afterBack = captures.filter(k => k.at > back && k.at <= back + 3000);
    expect(during.length, 'captures while RECONNECTING').toBeGreaterThan(0);
    for (const id of ids) {
        const first = during[0].tiles[id];
        expect(first, `tile ${id} while RECONNECTING: not "none"`).not.toBe('none');
        expect(during.filter(k => !sameReading(k.tiles[id], first)).map(k => describe(k.tiles[id])),
            `tile ${id}: the reading does not change while RECONNECTING (${describe(first)})`).toEqual([]);
        expect(afterBack.some(k => !sameReading(k.tiles[id], first)), `tile ${id}: the reading changes within 3 s of the reconnect`).toBe(true);
    }

    // the server stops (a clean stop: its port is free for the next test); the UI gives up
    const stopped = Date.now();
    await server.stop();
    await expect.poll(() => win.page.evaluate(() => window.preview.connectionState()),
        {message: 'the UI gives up (FAILED; DISCONNECTED is also a give-up of WebSocketConnection)', timeout: 60_000})
        .toMatch(/^(FAILED|DISCONNECTED)$/);
    await expect.poll(() => win.page.evaluate(() => window.preview.emptyState()), {message: 'the grid shows its empty state'}).toBe(true);
    expect(otherErrors(win.consoleErrors, stopped).map(e => e.text), 'no console error other than the failed connect').toEqual([]);
});

test('T-PRV-48 cameras come, go and restart; the order of the camera list', async ({preview}) => {
    const A: Cam = {id: 'aa', number: 1, list: 7, name: 'Cam A'};
    const B: Cam = {id: 'bb', number: 2, list: 3, name: 'Cam B'};
    const C: Cam = {id: 'cc', number: 3, list: 5, name: 'Cam C'};
    const D: Cam = {id: 'dd', number: 4, list: 1, name: 'Cam D'};
    const server = await preview.server({cameras: serverCameras([A, B, C]), fps: 30});
    // D is in the camera list of the store from the start; it gets a tile when it comes into app_state
    const win = await preview.open(server, seed([A, B, C, D]));
    const page = win.page;
    await requirePreviewTiles(page);
    await waitDrawn(page, [A.id, B.id, C.id]);
    const order = async () => {
        const cells = await page.evaluate(() => window.preview.cells());
        const visual = [...cells].sort((p, q) => p.top - q.top || p.left - q.left).map(c => c.id);
        return {dom: cells.map(c => c.id), visual};
    };
    expect(await order(), 'the grid cells in the order of the list numbers').toEqual({dom: [B.id, C.id, A.id], visual: [B.id, C.id, A.id]});

    // D comes
    const added = Date.now();
    await server.command({cmd: 'add', camera: D.id, number: D.number, index: 94, name: 'ring dd'});
    let seen: Capture | null = null;
    while (!seen && Date.now() - added < 2000) {
        const ids = (await page.evaluate(() => window.preview.cells())).map(c => c.id);
        if (!ids.includes(D.id)) {
            await sleep(50);
            continue;
        }
        const g = await page.evaluate(([i, size]) => window.preview.layout(i, size), [ids, SIZE_640] as const);
        if (g.missing.length) {
            await sleep(50);
            continue;
        }
        await observe(win.app, g, win.windowId);
        await sleep(250);
        const caps = toCaptures(await readings(win.app, win.windowId), ids);
        seen = caps.find(k => {
            const r = k.tiles[D.id];
            return typeof r !== 'string' && r.camera === D.number;
        }) ?? null;
    }
    expect(seen?.at ?? Infinity, 'the observer reads the tile of D within 2 s').toBeLessThanOrEqual(added + 2000);
    await expect.poll(order, {message: 'D first, in the DOM and on the screen'}).toEqual({dom: [D.id, B.id, C.id, A.id], visual: [D.id, B.id, C.id, A.id]});

    // B goes
    await server.command({cmd: 'remove', camera: B.id});
    await expect.poll(order, {message: 'B leaves the grid', timeout: 5000}).toEqual({dom: [D.id, C.id, A.id], visual: [D.id, C.id, A.id]});
    expect(await page.evaluate(id => window.preview.tileIds()?.includes(id), B.id), 'B has no tile in PreviewTiles').toBe(false);

    // A restarts with a new ring from frame 0
    const frames = async () => Object.fromEntries(await Promise.all([A, C, D].map(async c =>
        [c.id, overlayFrame((await page.evaluate(id => window.preview.overlay(id), c.id))?.frame)] as const)));
    await sleep(2000);
    const before = await frames();
    expect(before[A.id], 'A drew more frames than the restart threshold').toBeGreaterThan(60);
    await server.command({cmd: 'restart', camera: A.id});
    await expect.poll(async () => (await frames())[A.id], {message: 'the kept overlay frame of A starts again at a low number', timeout: 3000})
        .toBeLessThan(Math.min(45, before[A.id]!));
    const others = await watch(win, [C.id, D.id], 1000);
    for (const c of [C, D]) {
        const now = (await frames())[c.id];
        expect(now, `camera ${c.id} continues (overlay frame)`).toBeGreaterThan(before[c.id]!);
        expect(new Set(others.map(k => describe(k.tiles[c.id]))).size, `camera ${c.id} continues (observer)`).toBeGreaterThan(1);
    }
    const a = await watch(win, [A.id], 500);
    expect(a.every(k => typeof k.tiles[A.id] !== 'string' && (k.tiles[A.id] as {camera: number}).camera === A.number),
        'the tile of A shows its camera after the restart').toBe(true);
});

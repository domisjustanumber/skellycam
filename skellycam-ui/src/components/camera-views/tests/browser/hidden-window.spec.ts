// Component test T-PRV-49 of the step 4b preview (specs/preview-4b.md 7.4, 7.5): a hidden window gets only the
// safety net. Two windows of the page `preview`, each with its own connection. The app has no switch against
// backgrounding (PLAYER_HARNESS_PRODUCT_THROTTLING=1), and window 2 has the default `backgroundThrottling`, the
// product setting. Windows only.
import {expect} from '@playwright/test';
import {observe, readings} from '../../../../player/tests/harness/observer.ts';
import {
    connectionNumbers, counts, describe, geometry, requirePreviewTiles, sameReading, SIZE_640, sleep, test, toCaptures,
    waitDrawn, watch, written,
} from './preview-kit.ts';

const HIDDEN_MS = 5000;
const SETTLE_MS = 1000;   // the first second after the hide is not counted: frames in flight, the last ready messages

test.skip(process.platform !== 'win32',
    'T-PRV-49 runs on Windows only: no one has verified that a hidden window under xvfb-run (Linux) or on the macOS '
    + 'runner is hidden and stops requestAnimationFrame [NV] (specs/preview-4b.md 7.5)');

test('T-PRV-49 a hidden window gets only the safety net', async ({preview}) => {
    const cams = [{id: 'h1', number: 1, index: 2, name: 'Desk cam'}, {id: 'h2', number: 2, index: 1, name: 'Door cam'}];
    const ids = cams.map(c => c.id);
    const seed = cams.map(({id, index, name}) => ({id, index, name}));
    const server = await preview.server({cameras: cams.map(c => ({id: c.id, number: c.number, index: 90 + c.number, name: c.name})), fps: 30});
    const env = {PLAYER_HARNESS_PRODUCT_THROTTLING: '1'};
    const win1 = await preview.open(server, seed, {env});
    await requirePreviewTiles(win1.page);
    await waitDrawn(win1.page, ids);
    await expect.poll(async () => connectionNumbers(await counts(server)).length, {message: 'the connection of window 1'}).toBe(1);
    const win2 = await preview.openSecond(win1, server, seed, {productThrottling: true});
    await requirePreviewTiles(win2.page);
    await waitDrawn(win2.page, ids);
    const [conn1, conn2] = connectionNumbers(await counts(server));
    expect(conn2, 'window 2 has its own connection').toBeDefined();

    const geo2 = await geometry(win2.page, ids, SIZE_640);
    const before = await watch(win2, ids, 500);
    expect(before.length, 'the observer reads window 2 before the hide').toBeGreaterThan(0);
    const last = before[before.length - 1];
    const writtenAtHide = await written(server);
    const hidden = Date.now();
    await win1.app.evaluate(({BrowserWindow}, id) => BrowserWindow.fromId(id)!.hide(), win2.windowId);
    const visibility: string[] = [];
    while (Date.now() - hidden < HIDDEN_MS) {
        visibility.push(await win2.page.evaluate(() => document.visibilityState));
        await sleep(500);
    }
    const shown = Date.now();
    const writtenAtShow = await written(server);
    await observe(win1.app, geo2, win2.windowId);
    await win1.app.evaluate(({BrowserWindow}, id) => BrowserWindow.fromId(id)!.showInactive(), win2.windowId);
    await sleep(1500);
    const after = toCaptures(await readings(win1.app, win2.windowId), ids);

    expect(visibility.slice(1).every(v => v === 'hidden'), `document.visibilityState in window 2 while hidden: ${visibility.join(', ')}`).toBe(true);
    const n = await counts(server, hidden + SETTLE_MS, shown);
    const seconds = (shown - hidden - SETTLE_MS) / 1000;
    const n1 = await counts(server, hidden, shown);   // window 1: the whole hidden time, against the frames written
    for (const id of ids) {
        const perSecond = (n.connections[conn2]?.cameras[id]?.sent.length ?? 0) / seconds;
        expect(perSecond, `window 2, camera ${id}: camera messages each second while hidden (the safety net)`).toBeGreaterThanOrEqual(0.5);
        expect(perSecond, `window 2, camera ${id}: camera messages each second while hidden (the safety net)`).toBeLessThanOrEqual(1.6);
        const ready1 = n1.connections[conn1]?.cameras[id]?.ready.length ?? 0;
        const frames = writtenAtShow[id] - writtenAtHide[id];
        expect(ready1, `window 1, camera ${id}: at least 80 % of the ${frames} frames written while window 2 is hidden`).toBeGreaterThanOrEqual(0.8 * frames);
    }
    for (const id of ids) {
        const fresh = after.find(k => k.at <= shown + 1000 && typeof k.tiles[id] !== 'string' && !sameReading(k.tiles[id], last.tiles[id]));
        expect(fresh, `window 2, camera ${id}: the observer reads a new frame within 1 s of the show (before the hide: ${describe(last.tiles[id])})`).toBeDefined();
    }
});

// Component test T-PRV-44 of the step 4b preview (specs/preview-4b.md 7.4): the states of the cameras with no
// filter on `alive`. ui_server.py in the mode "capture": the real CameraGroupManager and CameraGroup with the fake
// sources of skellycam/tests/capture/ (THREAD workers, the real clock). The states are the real group states, not
// scripted. Camera A fails its first open and holds in its second open (`starting`, after a retry); camera B
// fails its open (`failed`); camera C is `ready`, then stalls (`dead`).
import {expect} from '@playwright/test';
import type {Page} from '@playwright/test';
import {describe, requirePreviewTiles, sleep, test, watch} from './preview-kit.ts';
import type {UiServer} from './preview-kit.ts';

const MODE = [640, 360, 30, 1, 'MJPG'];
const SHOW_WITHIN_MS = 1500;

interface States {
    states: Record<string, string | null>;
    alive: Record<string, boolean>;
    at: number;
    applies: ({status: number; text: string} | null)[];   // the answer of each apply; null while it runs
}

const states = (server: UiServer) => server.command<States>({cmd: 'states'});

async function waitStates(server: UiServer, want: Record<string, string>, timeoutMs: number): Promise<States> {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
        const s = await states(server);
        if (Object.entries(want).every(([id, state]) => s.states[id] === state)) return s;
        if (Date.now() > deadline) throw new Error(`the server states ${JSON.stringify(s.states)} are not ${JSON.stringify(want)}`);
        await sleep(100);
    }
}

/** The time when the server first gives `state` for the camera, and the time when the kept overlay of its tile
 * first shows it. */
async function stateTimes(server: UiServer, page: Page, id: string, state: string, timeoutMs = 30_000) {
    let atServer: number | null = null;
    let atTile: number | null = null;
    let last: States | null = null;
    const deadline = Date.now() + timeoutMs;
    while ((atServer === null || atTile === null) && Date.now() < deadline) {
        const s = last = await states(server);
        if (atServer === null && s.states[id] === state) atServer = s.at;
        const o = await page.evaluate(i => window.preview.overlay(i), id);
        if (atTile === null && o?.state === state) atTile = Date.now();
        await sleep(50);
    }
    expect(atServer, `the server gives ${state} for ${id} (last states ${JSON.stringify(last?.states)}, applies ${JSON.stringify(last?.applies)})`).not.toBeNull();
    expect(atTile, `the tile of ${id} shows ${state}`).not.toBeNull();
    expect(atTile! - atServer!, `the tile of ${id} shows ${state} within ${SHOW_WITHIN_MS} ms of its change in app_state`)
        .toBeLessThanOrEqual(SHOW_WITHIN_MS);
}

test('T-PRV-44 the states of the cameras, with no filter on alive', async ({preview}) => {
    const server = await preview.server({mode: 'capture', cameras: [
        {name: 'Cam A', script: {modes: [MODE], fail_opens: [1], hold_opens: [2]}},
        {name: 'Cam B', script: {modes: [MODE], fail_opens: [1]}},
        {name: 'Cam C', script: {modes: [MODE]}},
    ]});
    const [A, B, C] = server.cameras;
    const list: Record<string, number> = {[A.id]: 4, [B.id]: 6, [C.id]: 2};
    const label = (c: {id: string; name: string}) => `Camera ${list[c.id]} · ${c.name}`;
    const win = await preview.open(server, server.cameras.map(c => ({id: c.id, index: list[c.id], name: c.name})));
    const page = win.page;
    await requirePreviewTiles(page);

    await server.command({cmd: 'apply'});
    await waitStates(server, {[A.id]: 'failed', [B.id]: 'failed', [C.id]: 'ready'}, 60_000);
    // the states can be final before the first apply answers; a second apply while it runs is refused (409)
    await expect.poll(async () => (await states(server)).applies[0]?.status ?? null,
        {message: 'the first apply has its answer', timeout: 60_000}).not.toBeNull();
    // A opens again; its second open holds in `starting`
    await server.command({cmd: 'apply', retry: [A.id]});
    await stateTimes(server, page, A.id, 'starting');
    const held = await states(server);
    expect(held.states[A.id], 'A still holds in starting').toBe('starting');
    // Since ADR-NYT6 the group is alive while one selected camera lives (spec 4.5): the value is recorded, not checked.
    // T-PRV-44 says "three tiles, with no filter on alive" (Q830 of ADR-NA1N).
    test.info().annotations.push({type: 'group alive while A is starting', description: JSON.stringify(held.alive)});

    const ids = [A.id, B.id, C.id];
    await expect.poll(async () => (await page.evaluate(() => window.preview.tileIds()))?.slice().sort(),
        {message: 'three tiles, with no filter on alive'}).toEqual([...ids].sort());
    await expect.poll(async () => (await page.evaluate(() => window.preview.cells())).map(c => c.id).sort(),
        {message: 'three grid cells'}).toEqual([...ids].sort());
    const overlays = await page.evaluate(i => i.map(id => window.preview.overlay(id)), ids);
    expect(overlays.map(o => o?.state), 'the states of A, B and C').toEqual(['starting', 'failed', 'ready']);
    for (const [k, c] of [[0, A], [1, B]] as const) {
        expect(overlays[k]?.camera, `the label of ${c.name}`).toBe(label(c));
        expect(overlays[k]?.frame, `no frame part for ${c.name} [Q1]`).toBeNull();
    }
    expect(overlays[2]?.camera, 'the label of Cam C').toBe(label(C));
    let caps = await watch(win, ids, 1000);
    expect(caps.length, 'the observer got captures').toBeGreaterThan(5);
    for (const k of caps) {
        expect(k.tiles[A.id], 'A is black').toBe('none');
        expect(k.tiles[B.id], 'B is black').toBe('none');
        expect(describe(k.tiles[C.id]), 'C shows its camera').toMatch(new RegExp(`^camera ${C.number} frame`));
    }

    // the release of A
    await server.command({cmd: 'release', camera: A.id});
    await stateTimes(server, page, A.id, 'ready');
    await expect.poll(async () => {
        const k = await watch(win, [A.id], 400);
        return k.some(x => describe(x.tiles[A.id]).startsWith(`camera ${A.number} frame`));
    }, {message: 'the observer reads the camera of A', timeout: 5000}).toBe(true);

    // C stalls for more than 2 s: dead
    await server.command({cmd: 'stall', camera: C.id});
    await stateTimes(server, page, C.id, 'dead', 15_000);
    caps = await watch(win, [C.id], 1000);
    expect(caps.length).toBeGreaterThan(5);
    expect(caps[0].tiles[C.id], 'the last image of C stays').not.toBe('none');
    expect(new Set(caps.map(k => describe(k.tiles[C.id]))).size, 'the reading of C stops changing').toBe(1);
});

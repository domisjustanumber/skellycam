// Component tests of the host view CanvasTakePlayer with today's PlaybackControls: T-PLAY-51 to
// T-PLAY-53 (specs/player.md sections 3 and 10). The test Electron app opens the host page.
import {expect} from '@playwright/test';
import type {Page} from '@playwright/test';
import {mkdirSync, writeFileSync} from 'node:fs';
import path from 'node:path';
import {defaultTake} from '../../../player/tests/fixtures/take.ts';
import {harnessTest} from '../../../player/tests/browser/harness.ts';
import type {Harness} from '../../../player/tests/browser/harness.ts';

const test = harnessTest('host');

// The labels of today's controls (en locale) and their keys.
const PLAY = 'Play (Space)';
const PAUSE = 'Pause (Space)';
const NEXT = 'Next frame (→ / Shift+→ for 10)';
const PREVIOUS = 'Previous frame (← / Shift+← for 10)';
const START = 'Jump to start (Home)';
const END = 'Jump to end (End)';
const LOOP_OFF = 'Loop playback (L)';
const LOOP_ON = 'Loop is on (L to toggle)';
const SPEED = 'Playback speed (does not affect recording fps)';
const SETTINGS = 'Playback settings';
const SYNC = 'Sync info';

async function mount(h: Harness, cameras: number, props: Record<string, unknown> = {}) {
    await h.requireProduct();
    const built = h.build(defaultTake(`host_${cameras}`, cameras, 120));
    await h.page.evaluate(([f, p]) => window.host.mount(f as string, p as never), [built.dir, props] as const);
    await expect(h.page.getByText(/Frame \d+ \/ 120/)).toBeVisible();
    return built;
}

async function frame(page: Page): Promise<number> {
    const text = await page.getByText(/Frame \d+ \/ \d+/).textContent();
    return Number(/Frame (\d+)/.exec(text ?? '')![1]);
}

const playing = async (page: Page) => (await page.getByTitle(PAUSE).count()) > 0;

test('T-PLAY-51 the host view with today\'s controls: buttons, keys, speeds, the seek drag', async ({harness: h}) => {
    await mount(h, 4);
    const page = h.page;
    await page.getByTitle(NEXT).click();
    expect(await frame(page)).toBe(1);
    await page.getByTitle(PREVIOUS).click();
    expect(await frame(page)).toBe(0);
    await page.getByTitle(END).click();
    expect(await frame(page)).toBe(119);
    await page.getByTitle(START).click();
    expect(await frame(page)).toBe(0);
    await page.getByTitle(PLAY).click();
    expect(await playing(page)).toBe(true);
    await page.getByTitle(PAUSE).click();
    expect(await playing(page)).toBe(false);
    await page.getByTitle(LOOP_OFF).click();
    await expect(page.getByTitle(LOOP_ON)).toBeVisible();
    await page.keyboard.press('l');
    await expect(page.getByTitle(LOOP_OFF)).toBeVisible();
    // keys of F9 to F12 (the focus is on the page body)
    await page.locator('body').click({position: {x: 5, y: 5}});
    await page.keyboard.press('Home');
    await page.keyboard.press('ArrowRight');
    expect(await frame(page)).toBe(1);
    await page.keyboard.press('Shift+ArrowRight');
    expect(await frame(page)).toBe(11);
    await page.keyboard.press('ArrowLeft');
    expect(await frame(page)).toBe(10);
    await page.keyboard.press('Shift+ArrowLeft');
    expect(await frame(page)).toBe(0);
    await page.keyboard.press('End');
    expect(await frame(page)).toBe(119);
    await page.keyboard.press('Home');
    await page.keyboard.press('Space');
    expect(await playing(page)).toBe(true);
    await page.keyboard.press('Space');
    expect(await playing(page)).toBe(false);
    // keys do nothing while an <input> has the focus: the seek bar, and a text input
    const seek = page.locator('input[type="range"]');
    await seek.focus();
    await page.keyboard.press('Space');
    expect(await playing(page)).toBe(false);
    await page.evaluate(() => {
        const input = document.createElement('input');
        input.type = 'text';
        input.id = 'text-input';
        document.body.append(input);
    });
    await page.locator('#text-input').focus();
    const before = await frame(page);
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('Space');
    expect(await frame(page)).toBe(before);
    expect(await playing(page)).toBe(false);
    // each speed of F13
    for (const rate of ['0.1', '0.25', '0.5', '1', '1.5', '2', '4', '8']) {
        await page.getByTitle(SPEED).click();
        await page.getByRole('button', {name: `${rate}×`, exact: true}).click();
        await expect(page.getByTitle(SPEED)).toContainText(`${rate}×`);
    }
    await page.getByTitle(SPEED).click();
    await page.getByRole('button', {name: '1×', exact: true}).click();
    // the settings popup (F17) opens
    await page.getByTitle(SETTINGS).click();
    // the sync warning of F16 is not shown [L4]
    await expect(page.getByTitle(SYNC)).toHaveCount(0);
    // a seek drag while playing shows images, and the release resumes play
    await page.getByTitle(START).click();
    await page.getByTitle(PLAY).click();
    await seek.dispatchEvent('mousedown');
    await seek.fill('60');
    expect(await frame(page)).toBe(60);
    expect(await playing(page)).toBe(false);
    await seek.dispatchEvent('mouseup');
    await expect.poll(() => playing(page)).toBe(true);
});

/** Auto tiling of today (SyncedVideoPlayer): the column count with the largest tile area. */
function autoColumns(n: number, w: number, h: number): number {
    if (n <= 1) return 1;
    let best = 1;
    let bestArea = 0;
    for (let cols = 1; cols <= n; cols++) {
        const rows = Math.ceil(n / cols);
        const cw = (w - 2 * (cols - 1)) / cols;
        const ch = (h - 2 * (rows - 1)) / rows;
        if (cw < 80 || ch < 60) continue;
        if (n * cw * ch > bestArea) {
            bestArea = n * cw * ch;
            best = cols;
        }
    }
    return best;
}

async function columns(page: Page): Promise<number> {
    const xs = await page.locator('canvas[data-camera-label]').evaluateAll(cs => cs.map(c => Math.round(c.getBoundingClientRect().left)));
    return new Set(xs).size;
}

test('T-PLAY-52 the host grid: auto tiling, manual columns, reset, a swap', async ({harness: h}) => {
    for (const n of [1, 4, 9]) {
        await mount(h, n);
        const box = await h.page.locator('[data-testid="take-grid"]').boundingBox();
        expect(box).not.toBeNull();
        await expect(h.page.locator('canvas[data-camera-label]')).toHaveCount(n);
        expect(await columns(h.page), `auto tiling of ${n}`).toBe(autoColumns(n, box!.width, box!.height));
        await h.page.evaluate(() => window.host.unmount());
    }
    const built = await mount(h, 4, {manualColumns: 2});
    expect(await columns(h.page)).toBe(2);
    const labels = () => h.page.locator('canvas[data-camera-label]').evaluateAll(cs => cs
        .map(c => ({label: c.getAttribute('data-camera-label'), x: c.getBoundingClientRect().left, y: c.getBoundingClientRect().top}))
        .sort((a, b) => a.y - b.y || a.x - b.x).map(c => c.label));
    const order = await labels();
    const tile1 = h.page.locator(`canvas[data-camera-label="${built.plan.cameras[1].label}"]`);
    const tile3 = h.page.locator(`canvas[data-camera-label="${built.plan.cameras[3].label}"]`);
    await tile1.dragTo(tile3);
    // the grid moves the tiles with a 200 ms CSS transition
    await expect.poll(async () => {
        const swapped = await labels();
        return [swapped[1], swapped[3]];
    }).toEqual([order[3], order[1]]);
    await h.page.evaluate(([f]) => window.host.mount(f as string, {manualColumns: 2, resetKey: 1}), [built.dir] as const);
    await expect.poll(labels).toEqual(order);
});

test('T-PLAY-53 initialFrame, frame events, loading, the empty state and the route', async ({harness: h}) => {
    await mount(h, 4, {initialFrame: 50});
    expect(await frame(h.page)).toBe(50);
    const frames = await h.page.evaluate(() => window.host.frames());
    expect(frames[0]?.frame ?? 50).toBe(50);
    await h.page.getByTitle(PLAY).click();
    const t0 = Date.now();
    await h.page.waitForTimeout(2000);
    await h.page.getByTitle(PAUSE).click();
    const during = (await h.page.evaluate(() => window.host.frames())).filter(f => f.frame !== 50);
    const seconds = (Date.now() - t0) / 1000;
    expect(during.length).toBeGreaterThan(0);
    expect(during.length / seconds, 'frame events at most 5 per second').toBeLessThanOrEqual(5.5);
    await h.page.evaluate(() => window.host.unmount());
    // the loading message counts the cameras whose first image is drawn
    const built = h.build(defaultTake('host_loading', 4, 30));
    await h.page.evaluate(f => window.host.mount(f), built.dir);
    // F18 as today: the message counts the drawn cameras and goes away when each one has drawn its image
    await expect(h.page.locator('canvas[data-camera-label][title="timestamp from recording"]')).toHaveCount(4);
    await expect(h.page.getByText(/^\d+ \/ 4$/)).toHaveCount(0);
    await h.page.evaluate(() => window.host.unmount());
    // an empty camera list: a take folder with no camera
    const empty = path.join(h.recordings, 'empty_take');
    mkdirSync(path.join(empty, 'synchronized_videos'), {recursive: true});
    await h.page.evaluate(f => window.host.mount(f), empty);
    await expect(h.page.getByText(/no videos loaded/i)).toBeVisible();
    await h.page.evaluate(() => window.host.unmount());
    // the route [L1]: a folder of today's format opens in today's player, a take in the new one
    const old = path.join(h.recordings, 'old_format');
    mkdirSync(path.join(old, 'synchronized_videos'), {recursive: true});
    writeFileSync(path.join(old, 'synchronized_videos', 'camera_0.mp4'), new Uint8Array(64));
    expect(await h.page.evaluate(f => window.host.route(f), old)).toBe('video');
    expect(await h.page.evaluate(f => window.host.route(f), built.dir)).toBe('canvas');
});

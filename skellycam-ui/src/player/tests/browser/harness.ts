// The Playwright side of the test Electron app: launch, temporary folders, close. Each test gets a new
// recordings folder, and the app is closed after the test.
import {_electron, test as base} from '@playwright/test';
import type {ElectronApplication, Page} from '@playwright/test';
import {mkdtempSync, rmSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {writeTake} from '../fixtures/take.ts';
import type {BuiltTake, TakePlan} from '../fixtures/take.ts';
import {planOf} from '../fixtures/takes.ts';
import type {TileUpdate} from '../../index.ts';

const UI = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
export const HARNESS_MAIN = path.join(UI, 'dist-player-harness', 'main', 'main.js');

export interface Harness {
    app: ElectronApplication;
    page: Page;
    root: string;              // the temporary folder of the test
    recordings: string;        // the test recordingsFolder
    userData: string;          // the Electron userData folder of the harness
    build(plan: TakePlan | string): BuiltTake;
    relaunch(): Promise<void>;
    /** Fail with the product error when the product is missing. */
    requireProduct(): Promise<void>;
}

/** The Electron userData folder of a harness, beside its recordings folder (player.md 12.1). */
export const userDataOf = (recordings: string) => path.join(path.dirname(recordings), 'harness-user-data');

export async function launch(recordings: string, pageName: 'harness' | 'host' | 'preview',
                             extraEnv: Record<string, string> = {}): Promise<{app: ElectronApplication; page: Page}> {
    const env: Record<string, string> = {};
    for (const [k, v] of Object.entries(process.env)) if (v !== undefined && k !== 'ELECTRON_RUN_AS_NODE') env[k] = v;
    Object.assign(env, {PLAYER_HARNESS_RECORDINGS: recordings, PLAYER_HARNESS_USER_DATA: userDataOf(recordings), PLAYER_HARNESS_PAGE: pageName}, extraEnv);
    const app = await _electron.launch({args: [HARNESS_MAIN, '--no-sandbox'], env});
    const page = await app.firstWindow();
    await page.waitForFunction(name => name in window, pageName);
    const inner = await page.evaluate(() => [innerWidth, innerHeight]);
    console.log(`harness ${pageName} window at start: requestAnimationFrame ${await rafRate(page)}/s, inner size ${inner.join(' x ')}`);
    return {app, page};
}

/** The display refreshes per second of the page over 0.5 s (at most 2 s): a slow window makes clicks time out. */
export const rafRate = (page: Page) => page.evaluate(() => new Promise<number>(resolve => {
    let n = 0;
    const t0 = performance.now();
    const rate = () => resolve(Math.round(n / ((performance.now() - t0) / 1000)));
    const step = () => (performance.now() - t0 < 500 ? (n++, requestAnimationFrame(step)) : rate());
    setTimeout(rate, 2000);
    requestAnimationFrame(step);
})).catch(() => -1);

export function harnessTest(pageName: 'harness' | 'host') {
    return base.extend<{harness: Harness}>({
        harness: async ({}, use) => {
            const root = mkdtempSync(path.join(os.tmpdir(), 'skellycam-player-e2e-'));
            const recordings = path.join(root, 'skellycam_data', 'recordings');
            let {app, page} = await launch(recordings, pageName);
            const h: Harness = {
                get app() {
                    return app;
                },
                get page() {
                    return page;
                },
                root, recordings, userData: userDataOf(recordings),
                build: plan => writeTake(recordings, typeof plan === 'string' ? planOf(plan) : plan),
                relaunch: async () => {
                    await app.close();
                    ({app, page} = await launch(recordings, pageName));
                },
                requireProduct: async () => {
                    const error = await page.evaluate(() => window.harnessIpc.productError());
                    if (error) throw new Error(error);
                },
            };
            try {
                await use(h);
            } finally {
                console.log(`harness ${pageName} window at the end: requestAnimationFrame ${await rafRate(page)}/s`);
                await app.close();
                rmSync(root, {recursive: true, force: true});
            }
        },
    });
}

export const toBase64 = (b: Uint8Array) => Buffer.from(b).toString('base64');

/** A TileUpdate for the wire: the JPEG as base64. */
export function wire(u: Partial<TileUpdate> & {jpeg: Uint8Array | null}) {
    return {rotationCwDeg: 0 as const, label: null, rateText: null, cameraState: null, mark: null, ...u, jpeg: u.jpeg ? toBase64(u.jpeg) : null};
}

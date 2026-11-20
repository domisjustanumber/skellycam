// T-PLAY-81: the route of a folder that the take handler refuses (ADR-5FBS). Node, with a bridge double.
import assert from 'node:assert/strict';
import test from 'node:test';

type Bridge = {open(p: string): Promise<unknown>; close(t: string): Promise<void>};
const setBridge = (b: Bridge) => ((globalThis as {skellycamTake?: Bridge}).skellycamTake = b);

test('T-PLAY-81 a refused folder routes to not_allowed, an old folder to video', async () => {
    const {routeTake, chooseTakePlayer} = await import('../take-route.ts');
    setBridge({open: () => Promise.reject(new Error("Error invoking remote method 'skellycam-take:open': Error: folder not allowed")), close: async () => {}});
    assert.equal(await routeTake('/outside/take'), 'not_allowed');
    assert.equal(await chooseTakePlayer('/outside/take'), 'video', 'the L1 route of today stays');
    let closed = '';
    setBridge({
        open: async () => ({token: 'a'.repeat(32), folderName: 'old', entries: [{path: 'synchronized_videos/camera_0.mp4', size: 64}]}),
        close: async t => void (closed = t),
    });
    assert.equal(await routeTake('/recordings/old'), 'video');
    assert.equal(closed, 'a'.repeat(32), 'the route closes the files');
});

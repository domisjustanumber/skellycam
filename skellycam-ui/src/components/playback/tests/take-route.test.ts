// T-PLAY-81: the route of a folder that the take handler refuses (ADR-5FBS). Node, with a bridge double.
// T-PLAY-92: the picked folder path of the recording browser (specs/player.md 5.10).
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

test('T-PLAY-92 a picked folder path: trailing separators go, a root stays a root, white space stays; its name', async () => {
    const {folderNameOf, trimFolder} = await import('../take-route.ts');
    assert.equal(trimFolder('D:\\'), 'D:\\', 'a drive root stays absolute');
    assert.equal(trimFolder('/'), '/');
    assert.equal(trimFolder('C:\\takes\\t1\\\\'), 'C:\\takes\\t1');
    // white space is part of a folder name: a trim would ask for another folder
    assert.equal(trimFolder('C:\\takes\\t1\u00a0'), 'C:\\takes\\t1\u00a0', 'not the sibling C:\\takes\\t1');
    assert.equal(trimFolder('C:\\\u00a0'), 'C:\\\u00a0', 'not the root C:\\');
    assert.equal(trimFolder('/srv/ '), '/srv/ ', 'not /srv');
    assert.equal(trimFolder('/srv/takes/t1/'), '/srv/takes/t1');
    assert.equal(folderNameOf('C:\\takes\\t1\\'), 't1');
    assert.equal(folderNameOf('/srv/takes/t1'), 't1');
    assert.equal(folderNameOf('D:\\'), 'D:\\', 'a root shows as itself');
    assert.equal(folderNameOf('/'), '/');
});

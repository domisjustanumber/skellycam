// A tile update that rejects does not hold the camera (specs/preview-4b.md 5.3 rule 2; ADR-8WX9). Not a spec ID: a
// guard of the code lane.
import assert from 'node:assert/strict';
import test from 'node:test';
import {fakes, flush, message, previewTiles, recordConsoleErrors} from './helpers.ts';

test('a rejected tile update clears busy: the next tick gives the tile the next message', async () => {
    const {PreviewTiles} = await previewTiles();
    const f = fakes();
    const frames: (number | null | undefined)[] = [];
    let reject = true;
    const tile = {
        update(u: {label: {frame: number | null} | null}) {
            frames.push(u.label?.frame);
            return reject ? Promise.reject(new Error('decode failed')) : Promise.resolve('drawn' as const);
        },
    };
    const tiles = new PreviewTiles(f.sendReady, f.onDrawn, f.now);
    tiles.setTile('a1b2', tile as never);
    const errors = await recordConsoleErrors(async () => {
        tiles.receive(message({camera: 'a1b2', frame: 1}));
        tiles.tick();
        await flush();
    });
    assert.equal(errors.length, 1, 'one console.error for the failed update');
    assert.deepEqual(f.ready, [], 'no ready message for a failed update');
    reject = false;
    tiles.receive(message({camera: 'a1b2', frame: 2}));
    tiles.tick();
    await flush();
    assert.deepEqual(frames, [1, 2], 'the camera is not busy after the rejection');
    assert.deepEqual(f.ready, ['a1b2']);
});

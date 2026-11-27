// The order of the tile updates turns at each refresh, so that no camera is always last [Q893]
// (specs/preview-4b.md 5.3 rule 6).
import assert from 'node:assert/strict';
import test from 'node:test';
import {fakes, flush, message, previewTiles} from './helpers.ts';

test('the first camera of the tile updates turns at each tick [Q893]', async () => {
    const {PreviewTiles} = await previewTiles();
    const f = fakes();
    const tiles = new PreviewTiles(f.sendReady, f.onDrawn, f.now);
    const calls: string[] = [];
    for (const id of ['A', 'B', 'C']) {
        tiles.setTile(id, {update: () => (calls.push(id), Promise.resolve('drawn' as const))});
    }
    const firsts: string[] = [];
    for (let frame = 1; frame <= 3; frame++) {
        for (const id of ['A', 'B', 'C']) tiles.receive(message({camera: id, frame}));
        calls.length = 0;
        tiles.tick();
        await flush();
        assert.equal(calls.length, 3, 'each camera gets its update');
        firsts.push(calls[0]);
    }
    assert.deepEqual([...firsts].sort(), ['A', 'B', 'C'], `each camera is first once in three ticks: ${firsts.join(', ')}`);
});

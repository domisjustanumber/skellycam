// Unit tests of the findings of the 6a code review: T-PLAY-74 to T-PLAY-76 (ADR-5FBS).
import assert from 'node:assert/strict';
import test from 'node:test';
import {defaultTake, writeTake} from '../fixtures/take.ts';
import {nodeTakeFiles} from '../fixtures/node-take-files.ts';
import {FakeLoop, FakeTile, openFixture, player, settle, spyFiles, tempRoot, testDecoder} from './helpers.ts';

test('T-PLAY-74 a JPEG that does not decode marks its frame only, and play goes on', async t => {
    const {openTake} = await player();
    const built = writeTake(tempRoot(t), defaultTake('undecodable'));
    const files = spyFiles(await nodeTakeFiles(built.dir));
    const decoder = testDecoder(built);
    const decode = (jpeg: Uint8Array) => (built.identify(jpeg)?.row === 30 ? Promise.reject(new Error('no decode')) : decoder.decode(jpeg));
    const p = await openTake(files, {frameLoop: new FakeLoop().frameLoop, decode});
    t.after(() => p.close());
    const tile = new FakeTile();
    p.attachTile(0, tile as never);
    const shown = () => ({row: built.identify(tile.image)?.row, mark: tile.mark});
    const seek = async (k: number) => {
        p.seekFrame(k);
        await settle(files);
    };
    await seek(29);
    assert.deepEqual(shown(), {row: 29, mark: null});
    await seek(30);
    assert.deepEqual(shown(), {row: 29, mark: {kind: 'damaged', frame: 30}}, 'the last image, with the mark of frame 30');
    await seek(31);
    assert.deepEqual(shown(), {row: 31, mark: null}, 'the next frame shows, with no mark');
    await seek(30);
    assert.deepEqual(shown(), {row: 31, mark: {kind: 'damaged', frame: 30}});
    assert.notEqual(p.state.cameras[0].state, 'invalid');
});

test('T-PLAY-75 a failed open closes the files', async t => {
    const {openTake} = await player();
    const built = writeTake(tempRoot(t), defaultTake('open_fails'));
    const files = spyFiles(await nodeTakeFiles(built.dir));
    files.failPath = built.cameras[0].csv;
    let closed = false;
    files.close = async () => void (closed = true);
    await assert.rejects(openTake(files, {frameLoop: new FakeLoop().frameLoop, decode: testDecoder(built).decode}));
    assert.equal(closed, true);
});

test('T-PLAY-76 a pair whose take_uuid does not read is in no take', async t => {
    const o = await openFixture(t, 'header_uuid_dashes');
    const c1 = o.built.cameras[1].mkv;
    assert.deepEqual(o.player.state.cameras.map(c => c.name), o.built.cameras.map(c => c.mkv).filter(n => n !== c1), 'SFF-889: other_files');
    assert.equal(o.player.state.take.state, 'incomplete', 'SFF-869: it does not count as a camera file');
    assert.ok(o.player.state.take.warnings.includes('incomplete_take'));
});

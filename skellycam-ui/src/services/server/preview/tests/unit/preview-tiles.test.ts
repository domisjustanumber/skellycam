// T-PRV-34 to T-PRV-39: the flow control of PreviewTiles (specs/preview-4b.md 5.3, 5.4, 7.4). A manual `tick`, fake
// tiles whose promises the test resolves, a fake `sendReady`, `onDrawn` and `now`. No timer, no browser.
import assert from 'node:assert/strict';
import test from 'node:test';
import {FakeTile, fakes, flush, message, previewTiles} from './helpers.ts';

const A = 'a1b2';
const B = 'c3d4';
const C = 'e5f6';

async function setUp(...cameras: string[]) {
    const {PreviewTiles} = await previewTiles();
    const f = fakes();
    const tiles = new PreviewTiles(f.sendReady, f.onDrawn, f.now);
    const fake: Record<string, FakeTile> = {};
    for (const id of cameras) {
        fake[id] = new FakeTile();
        tiles.setTile(id, fake[id]);
    }
    return {tiles, f, fake};
}

test('T-PRV-34 newest pending; one ready message for each draw', async () => {
    const {tiles, f, fake} = await setUp(A);
    for (const frame of [1, 2, 3]) tiles.receive(message({camera: A, frame}));
    f.clock.ms = 4321;
    tiles.tick();
    await flush();
    assert.deepEqual(fake[A].frames(), [3], 'one update, with frame 3');
    assert.ok(fake[A].last!.jpeg, 'the update has the JPEG');
    assert.deepEqual(f.ready, [], 'no ready message before the resolve');
    await fake[A].resolve('drawn');
    assert.deepEqual(f.ready, [A]);
    assert.equal(tiles.drawnCount.get(A), 1);
    assert.deepEqual(f.drawn, [[A, 4321]]);
    assert.equal(fake[A].last!.label?.frameDigits, 6);
    assert.equal(fake[A].last!.label?.timeNs, null);
    assert.equal(fake[A].last!.label?.nominalFps, 0);
});

test('T-PRV-35 one update in flight; a slow camera does not hold back another camera', async () => {
    const {tiles, f, fake} = await setUp(A, B);
    tiles.receive(message({camera: A, frame: 3}));
    tiles.receive(message({camera: B, frame: 3}));
    tiles.tick();
    await flush();
    for (const frame of [4, 5]) {
        tiles.receive(message({camera: A, frame}));
        tiles.receive(message({camera: B, frame}));
    }
    for (let i = 0; i < 3; i++) tiles.tick();
    await flush();
    assert.deepEqual(fake[A].frames(), [3], 'no second update for A while A is busy');
    await fake[A].resolve('drawn');
    assert.deepEqual(f.ready, [A]);
    tiles.tick();
    await flush();
    assert.deepEqual(fake[A].frames(), [3, 5], 'the next tick draws frame 5 of A');
    assert.deepEqual(fake[B].frames(), [3], 'B gets no second update');
    assert.ok(!f.ready.includes(B), 'B gets no ready message');
});

test('T-PRV-36 a flagged message', async () => {
    const {tiles, f, fake} = await setUp(A);
    tiles.receive(message({camera: A, frame: 10}));
    tiles.tick();
    await fake[A].resolve('drawn');
    const drawnBefore = f.drawn.length;
    assert.equal(tiles.drawnCount.get(A), 1);

    tiles.receive(message({camera: A, frame: 11, flags: 0x04, rotation: 90}));
    tiles.tick();
    await flush();
    const flagged = fake[A].last!;
    assert.equal(flagged.jpeg, null);
    assert.deepEqual(flagged.mark, {kind: 'flagged'});
    assert.equal(flagged.label?.frame, 11, 'the label frame of the flagged message');
    assert.equal(flagged.rotationCwDeg, 90);
    await fake[A].resolve('drawn');
    assert.deepEqual(f.ready, [A, A], 'one ready message after the flagged update');
    assert.equal(tiles.drawnCount.get(A), 1, 'drawnCount does not change for a flagged message');
    assert.equal(f.drawn.length, drawnBefore, 'onDrawn is not called for a flagged message');

    tiles.receive(message({camera: A, frame: 12}));
    tiles.tick();
    await flush();
    assert.ok(fake[A].last!.jpeg, 'the next update has the JPEG');
    assert.equal(fake[A].last!.mark, null);
});

test('T-PRV-37 an overlay update with no frame; the label before the first frame [Q1]', async () => {
    const {tiles, f, fake} = await setUp(A);
    tiles.setOverlay(A, {label: 'Camera 2 · USB Camera', cameraState: 'starting', rateText: '29.9 fps'});
    tiles.tick();
    await flush();
    assert.equal(fake[A].updates.length, 1, 'one overlay update');
    const first = fake[A].last!;
    assert.equal(first.jpeg, null);
    assert.equal(first.label?.frame, null, 'no frame part before the first frame');
    assert.equal(first.label?.camera, 'Camera 2 · USB Camera');
    assert.equal(first.cameraState, 'starting');
    assert.equal(first.rateText, '29.9 fps');
    await fake[A].resolve('drawn');
    assert.deepEqual(f.ready, [], 'no ready message for an overlay update');
    assert.deepEqual(f.drawn, [], 'no onDrawn for an overlay update');

    tiles.receive(message({camera: A, frame: 20}));
    tiles.tick();
    await flush();
    assert.equal(fake[A].updates.length, 2, 'the frame update is in flight');
    tiles.setOverlay(A, {cameraState: 'too_slow'});
    for (let i = 0; i < 3; i++) tiles.tick();
    await flush();
    assert.equal(fake[A].updates.length, 2, 'no update while the frame update is in flight');
    await fake[A].resolve('drawn');
    tiles.tick();
    await flush();
    assert.equal(fake[A].updates.length, 3, 'one overlay update after the resolve');
    const overlay = fake[A].last!;
    assert.equal(overlay.jpeg, null);
    assert.equal(overlay.cameraState, 'too_slow');
    assert.equal(overlay.label?.frame, 20, 'the frame number of the drawn frame');
    assert.equal(overlay.label?.camera, 'Camera 2 · USB Camera');
});

test('T-PRV-38 a hidden page and the UI pause', async () => {
    const {tiles, f, fake} = await setUp(A);
    for (let frame = 1; frame <= 100; frame++) tiles.receive(message({camera: A, frame}));
    await flush();
    assert.equal(fake[A].updates.length, 0, 'no update with no tick (a hidden page)');
    tiles.setPaused(true);
    for (let i = 0; i < 10; i++) tiles.tick();
    await flush();
    assert.equal(fake[A].updates.length, 0, 'no update while paused');
    assert.deepEqual(f.ready, []);
    tiles.setPaused(false);
    tiles.tick();
    await flush();
    assert.deepEqual(fake[A].frames(), [100], 'one update, with the newest message');
    assert.deepEqual(f.ready, [], 'no ready message before the resolve');
});

test('T-PRV-39 no tile yet; tile removed; connection closed', async () => {
    const {tiles, f, fake} = await setUp(A);
    const tileC = new FakeTile();
    tiles.receive(message({camera: C, frame: 1}));
    tiles.receive(message({camera: C, frame: 2}));
    tiles.tick();
    await flush();
    assert.deepEqual(f.ready, [], 'no ready message for C before its tile');
    tiles.setTile(C, tileC);
    tiles.tick();
    await flush();
    assert.deepEqual(tileC.frames(), [2], 'the newest message of C');
    await tileC.resolve('drawn');
    assert.deepEqual(f.ready, [C]);

    tiles.setTile(C, null);
    tiles.receive(message({camera: C, frame: 3}));
    tiles.tick();
    await flush();
    assert.equal(tileC.updates.length, 1, 'no update for C after its removal');

    tiles.receive(message({camera: A, frame: 7}));
    tiles.clearPending();
    tiles.tick();
    await flush();
    assert.equal(fake[A].updates.length, 0, 'no update for A after clearPending');
    assert.equal(tiles.tiles.get(A), fake[A], 'the tile of A stays');
});

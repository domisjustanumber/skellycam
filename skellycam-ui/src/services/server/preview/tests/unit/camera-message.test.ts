// T-PRV-32 and T-PRV-33: the parser of the camera message (specs/preview-4b.md 5.2, 7.4).
import assert from 'node:assert/strict';
import test from 'node:test';
import {bufferOf, cameraMessage, FakeTile, fakes, fixtureCases, flush, hexBytes, previewTiles, recordConsoleErrors} from './helpers.ts';

test('T-PRV-32 the parser reads the shared fixture', async () => {
    const {parseCameraMessage, CAMERA_FRAME_VERSION, CAMERA_FRAME_HEADER_SIZE} = await cameraMessage();
    assert.equal(CAMERA_FRAME_VERSION, 1);
    assert.equal(CAMERA_FRAME_HEADER_SIZE, 48);
    const cases = fixtureCases();
    assert.equal(cases.length, 6);
    for (const c of cases) {
        const m = parseCameraMessage(bufferOf(hexBytes(c.message_hex)));
        assert.equal(m.flags, c.input.flags, c.name);
        assert.equal(typeof m.frameNumber, 'bigint', c.name);
        assert.equal(typeof m.arrivalNs, 'bigint', c.name);
        assert.equal(m.frameNumber, BigInt(c.input.frame_number), c.name);
        assert.equal(m.arrivalNs, BigInt(c.input.arrival_ns), c.name);
        assert.equal(m.rotationCwDeg, c.input.rotation_cw_deg, c.name);
        assert.equal(m.cameraId, c.input.camera_id, c.name);
        assert.ok(!m.cameraId.includes('\0'), `${c.name}: the camera id has a NUL`);
        if ((c.input.flags & 0x0f) !== 0) assert.equal(m.jpeg, null, `${c.name}: a flagged message has no JPEG`);
        else assert.deepEqual(m.jpeg && [...m.jpeg], [...hexBytes(c.input.jpeg_hex)], c.name);
    }
    const large = cases.find(c => c.name === 'large-values')!;
    const m = parseCameraMessage(bufferOf(hexBytes(large.message_hex)));
    assert.equal(m.frameNumber, 2n ** 53n + 1n, 'above 2^53');
    assert.equal(m.arrivalNs, 2n ** 63n - 1n);
});

/** The changed cases of T-PRV-33, each from the spec example of the fixture. */
function badMessages(): [string, Uint8Array][] {
    const good = hexBytes(fixtureCases().find(c => c.name === 'spec-example')!.message_hex);
    const edit = (f: (b: Uint8Array) => Uint8Array) => f(good.slice());
    const view = (b: Uint8Array) => new DataView(b.buffer, b.byteOffset, b.byteLength);
    return [
        ['version 0', edit(b => (b[0] = 0, b))],
        ['version 2', edit(b => (b[0] = 2, b))],
        ['47 bytes', good.slice(0, 47)],
        ['one byte too long', Uint8Array.from([...good, 0])],
        ['one byte too short', good.slice(0, good.length - 1)],
        ['rotation 45', edit(b => (view(b).setUint32(24, 45, true), b))],
        ['empty camera id', edit(b => (b.fill(0, 32, 48), b))],
    ];
}

test('T-PRV-33 the parser refuses a bad message; PreviewTiles logs each reason once and sends nothing', async () => {
    const {parseCameraMessage} = await cameraMessage();
    const {PreviewTiles} = await previewTiles();
    for (const [name, bytes] of badMessages()) {
        assert.throws(() => parseCameraMessage(bufferOf(bytes)), Error, name);
    }
    for (const version of [0, 2]) {
        const [, bytes] = badMessages().find(([name]) => name === `version ${version}`)!;
        assert.throws(() => parseCameraMessage(bufferOf(bytes)), (e: Error) => new RegExp(`\\b${version}\\b`).test(e.message) && /\b1\b/.test(e.message),
            `the version text names both values (${version} and 1)`);
    }

    const f = fakes();
    const tile = new FakeTile('drawn');
    const tiles = new PreviewTiles(f.sendReady, f.onDrawn, f.now);
    tiles.setTile('a1b2', tile);
    const errors = await recordConsoleErrors(async errors => {
        for (const [name, bytes] of badMessages()) {
            tiles.receive(bufferOf(bytes));
            const afterFirst = errors.length;
            tiles.receive(bufferOf(bytes));
            assert.equal(errors.length, afterFirst, `${name}: a second console.error for the same reason`);
            tiles.tick();
            await flush();
        }
    });
    assert.ok(errors.length >= 4 && errors.length <= 7, `${errors.length} console.error calls for 7 bad messages of 4 kinds`);
    assert.equal(tile.updates.length, 0, 'a refused message reached the tile');
    assert.deepEqual(f.ready, [], 'a refused message got a ready message');
});

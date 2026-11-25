// T-PLAY-37: the overlay text of tile/format.ts (specs/player.md section 8.4).
import assert from 'node:assert/strict';
import test from 'node:test';
import {product} from './helpers.ts';

type Format = typeof import('../../tile/format.ts');

test('T-PLAY-37 the overlay text: frame digits, seconds, timecode, no time', async () => {
    const {formatFrame, formatTime} = await product<Format>('tile/format.ts');
    assert.equal(formatFrame(7, 1), 'F7');
    assert.equal(formatFrame(7, 3), 'F007');
    assert.equal(formatFrame(42, 5), 'F00042');
    assert.equal(formatTime(33_400_000, 'seconds', 30), '0.033s');
    assert.equal(formatTime(3_725_500_000_000, 'seconds', 30), '3725.500s');
    assert.equal(formatTime(33_400_000, 'timecode', 30), '00:00:00:01');
    assert.equal(formatTime(3_725_500_000_000, 'timecode', 30), '01:02:05:15');
    assert.equal(formatTime(3_725_500_000_000, 'timecode', 29.97), '01:02:05:14');
    assert.equal(formatTime(null, 'seconds', 30), null, 'no time part for null');
    assert.equal(formatTime(null, 'timecode', 30), null);
});

test('T-PLAY-37 a label with frame null has no frame part; the camera part stays [Q1 of ADR-VYS7]', async () => {
    const {Tile} = await product<typeof import('../../index.ts')>('index.ts');
    const {fakeCanvas} = await import('./helpers.ts');
    const tile = new Tile(fakeCanvas().canvas);
    const label = {frame: null as unknown as number, frameDigits: 6, camera: 'Camera 2 · USB Camera', timeNs: null, nominalFps: 0};
    assert.equal(await tile.update({jpeg: null, rotationCwDeg: 0, label, rateText: null, cameraState: 'starting', mark: null}), 'drawn');
    assert.equal(tile.overlay.frame, null, 'no frame part');
    assert.equal(tile.overlay.camera, 'Camera 2 · USB Camera');
    assert.equal(tile.overlay.state, 'starting');
    tile.close();
});

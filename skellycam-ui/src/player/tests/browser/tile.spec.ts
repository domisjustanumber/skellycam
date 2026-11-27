// Component tests of the tile in a bare page (no host code, no reader): T-PLAY-40 to T-PLAY-45
// (specs/player.md section 8). Real ImageDecoder and canvas in Electron 45.3.4.
import {expect} from '@playwright/test';
import {barcodeBits, barcodeJpeg, BARCODE_Y, CELL, insertDht, ONE, QUADRANTS, ycbcrToRgb, ZERO} from '../fixtures/jpeg.ts';
import type {JpegOptions} from '../fixtures/jpeg.ts';
import {near} from '../fixtures/barcode.ts';
import type {Rgb} from '../fixtures/barcode.ts';
import {planOf} from '../fixtures/takes.ts';
import {harnessTest, wire} from './harness.ts';
import type {Harness} from './harness.ts';

const test = harnessTest('harness');

const label = {frame: 7, frameDigits: 3, camera: 'a1b2c3', timeNs: 33_400_000, nominalFps: 30};

async function assertImage(h: Harness, id: string, camera: number, position: number) {
    const r = await h.page.evaluate(i => window.harness.readTile(i), id);
    expect(r.camera, 'barcode camera').toBe(camera);
    expect(r.position, 'barcode position').toBe(position);
    r.quadrants.forEach((q: Rgb, i: number) => expect(near(q, ycbcrToRgb(QUADRANTS[i])), `quadrant ${i}: ${q}`).toBe(true));
}

async function assertBlockColours(h: Harness, id: string, camera: number, position: number) {
    const bits = barcodeBits(camera, position);
    for (const [i, bit] of bits.entries()) {
        const px = await h.page.evaluate(([tid, x, y]) => window.harness.imagePixel(tid as string, x as number, y as number), [id, i * CELL + CELL / 2, BARCODE_Y + CELL / 2]);
        expect(near(px, ycbcrToRgb(bit ? ONE : ZERO)), `cell ${i}: ${px}`).toBe(true);
    }
}

test('T-PLAY-40 a bare page with only Tile: one barcode JPEG', async ({harness: h}) => {
    await h.page.evaluate(() => window.harness.makeTile('a'));
    const result = await h.page.evaluate(u => window.harness.updateTile('a', u), wire({jpeg: barcodeJpeg(1, 77)}));
    expect(result).toBe('drawn');
    await assertImage(h, 'a', 1, 77);
    await assertBlockColours(h, 'a', 1, 77);
});

test('T-PLAY-41 rotations: the quadrants at the upright corners', async ({harness: h}) => {
    await h.requireProduct();
    const built = h.build(planOf('rotations'));
    await h.page.evaluate(folder => window.harness.openPlayer(folder), built.dir);
    for (const [i, cam] of built.plan.cameras.entries()) {
        // the quadrants of the same reading as the barcode: a second read could come between a resize of the canvas,
        // which clears it, and the redraw of the tile
        let r = await h.page.evaluate(n => window.harness.readPlayerTile(n), i);
        await expect.poll(async () => (r = await h.page.evaluate(n => window.harness.readPlayerTile(n), i))).toMatchObject({camera: cam.index, position: 0});
        r.quadrants.forEach((q: Rgb, j: number) => expect(near(q, ycbcrToRgb(QUADRANTS[j])), `rotation ${cam.rotation} quadrant ${j}: ${q}`).toBe(true));
    }
    await h.page.evaluate(() => window.harness.closePlayer());
});

test('T-PLAY-42 jpeg_forms: no DHT, an inserted DHT, no APP0, bytes after the EOI', async ({harness: h}) => {
    const forms: [string, JpegOptions & {insertDht?: boolean}][] = [
        ['no DHT', {noDht: true}], ['inserted DHT', {noDht: true, insertDht: true}], ['no APP0', {}], ['bytes after the EOI', {trailingBytes: 1024}],
    ];
    for (const [i, [name, options]] of forms.entries()) {
        const id = `form${i}`;
        await h.page.evaluate(n => window.harness.makeTile(n), id);
        const plain = barcodeJpeg(i, 3, '422', options);
        const jpeg = options.insertDht ? insertDht(plain) : plain;
        const result = await h.page.evaluate(([n, u]) => window.harness.updateTile(n as string, u as never), [id, wire({jpeg})] as const);
        expect(result, name).toBe('drawn');
        await assertImage(h, id, i, 3);
        await assertBlockColours(h, id, i, 3);
    }
});

test('T-PLAY-43 EXIF orientation 6 with rotation 0: drawn as stored', async ({harness: h}) => {
    await h.page.evaluate(() => window.harness.makeTile('exif'));
    await h.page.evaluate(u => window.harness.updateTile('exif', u), wire({jpeg: barcodeJpeg(2, 9, '422', {exifOrientation: 6})}));
    await assertImage(h, 'exif', 2, 9);
});

test('T-PLAY-44 the label on and off, seconds and timecode, the canvas title', async ({harness: h}) => {
    await h.page.evaluate(() => window.harness.makeTile('l'));
    await h.page.evaluate(u => window.harness.updateTile('l', u), wire({jpeg: barcodeJpeg(0, 1), label}));
    const overlay = () => h.page.evaluate(() => window.harness.overlay('l'));
    await expect.poll(overlay).toMatchObject({overlay: {frame: 'F007', camera: 'a1b2c3', time: '00:00:00:01'}, title: 'timestamp from recording'});
    await h.page.evaluate(() => window.harness.setTileOptions('l', {timeFormat: 'seconds'}));
    await expect.poll(overlay).toMatchObject({overlay: {time: '0.033s'}});
    await h.page.evaluate(() => window.harness.setTileOptions('l', {showLabel: false}));
    await expect.poll(overlay).toMatchObject({overlay: {frame: null, camera: null, time: null}});
    expect((await overlay()).title).not.toBe('timestamp from recording');
    await h.page.evaluate(() => window.harness.setTileOptions('l', {showLabel: true}));
    await h.page.evaluate(u => window.harness.updateTile('l', u), wire({jpeg: null, label: {...label, timeNs: null}}));
    await expect.poll(overlay).toMatchObject({overlay: {frame: 'F007', time: null}});
    expect((await overlay()).title).not.toBe('timestamp from recording');
    // specs/preview-4b.md 7.6 [Q1]: the label on and `frame` null (an overlay before the first frame): the kept
    // overlay has no frame text and has the camera text
    await h.page.evaluate(u => window.harness.updateTile('l', u), wire({jpeg: null, label: {...label, frame: null as unknown as number, timeNs: null}}));
    await expect.poll(overlay, {message: 'frame null: no frame text, the camera text stays'}).toMatchObject({overlay: {frame: null, camera: 'a1b2c3', time: null}});
});

test('T-PLAY-45 Tile alone: no new image, the eight states, a rate text, flagged, newest wins', async ({harness: h}) => {
    await h.page.evaluate(() => window.harness.makeTile('p'));
    await h.page.evaluate(u => window.harness.updateTile('p', u), wire({jpeg: barcodeJpeg(3, 40)}));
    await assertImage(h, 'p', 3, 40);
    const states = ['starting', 'waiting', 'failed', 'checking', 'too_slow', 'ready', 'recording', 'dead'] as const;
    for (const cameraState of states) {
        const r = await h.page.evaluate(u => window.harness.updateTile('p', u), wire({jpeg: null, cameraState, rateText: '29.97 fps'}));
        expect(r).toBe('drawn');
        const o = await h.page.evaluate(() => window.harness.overlay('p'));
        expect(o.overlay).toMatchObject({state: cameraState, rate: '29.97 fps'});
        await assertImage(h, 'p', 3, 40);
    }
    await h.page.evaluate(u => window.harness.updateTile('p', u), wire({jpeg: null, mark: {kind: 'flagged'}}));
    expect((await h.page.evaluate(() => window.harness.overlay('p'))).overlay.mark).toBe('flagged frame');
    await assertImage(h, 'p', 3, 40);
    await h.page.evaluate(u => window.harness.updateTile('p', u), wire({jpeg: null}));
    expect((await h.page.evaluate(() => window.harness.overlay('p'))).overlay.mark).toBe(null);
    const both = await h.page.evaluate(([a, b]) => window.harness.updateTwice('p', a as never, b as never), [wire({jpeg: barcodeJpeg(3, 41)}), wire({jpeg: barcodeJpeg(3, 42)})] as const);
    expect(both).toEqual(['superseded', 'drawn']);
    await assertImage(h, 'p', 3, 42);
});

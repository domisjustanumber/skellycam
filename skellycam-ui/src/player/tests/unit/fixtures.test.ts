// T-PLAY-01 and the self-tests of the fixture builder. These tests use no product module: they pass now.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import {fileURLToPath} from 'node:url';
import {crc32} from 'node:zlib';
import {ANNEX_K, barcodeImage, IMAGE_HEIGHT, IMAGE_WIDTH, QUADRANTS, readSof, ycbcrToRgb} from '../fixtures/jpeg.ts';
import {near, readTile} from '../fixtures/barcode.ts';
import {HEADER_VARIANTS, PLANS, VERSION_VARIANTS, buildTake} from '../fixtures/takes.ts';
import type {BuiltTake} from '../fixtures/take.ts';
import {tempRoot} from './helpers.ts';

// ---- An independent small parser: EBML walk and CSV read ----

function vint(b: Uint8Array, at: number): {value: number; len: number; unknown: boolean} {
    let len = 1;
    while (len <= 8 && !(b[at] & (0x80 >> (len - 1)))) len++;
    let value = b[at] & (0xff >> len);
    let allOnes = value === 0xff >> len;
    for (let i = 1; i < len; i++) {
        value = value * 256 + b[at + i];
        if (b[at + i] !== 0xff) allOnes = false;
    }
    return {value, len, unknown: allOnes};
}

function elementId(b: Uint8Array, at: number): {id: number; len: number} {
    const v = vint(b, at);
    let id = 0;
    for (let i = 0; i < v.len; i++) id = id * 256 + b[at + i];
    return {id, len: v.len};
}

const LEVEL1 = new Set([0x1f43b675, 0x1c53bb6b, 0x1549a966, 0x1654ae6b, 0x114d9b74, 0x1254c367, 0x1941a469, 0x1043a770]);

export interface WalkedBlock {
    payloadOffset: number;
    payloadSize: number;
    track: number;
    flags: number;
}

export function walkMkv(b: Uint8Array) {
    const head = elementId(b, 0);
    assert.equal(head.id, 0x1a45dfa3, 'EBML magic');
    const headSize = vint(b, head.len);
    let at = head.len + headSize.len + headSize.value;
    const seg = elementId(b, at);
    assert.equal(seg.id, 0x18538067, 'one Segment');
    const segSize = vint(b, at + seg.len);
    const segStart = at + seg.len + segSize.len;
    const segEnd = segSize.unknown ? b.length : segStart + segSize.value;
    const blocks: WalkedBlock[] = [];
    const codecs: string[] = [];
    let crcClusters = 0;
    at = segStart;
    while (at < segEnd) {
        const e = elementId(b, at);
        const s = vint(b, at + e.len);
        const dataStart = at + e.len + s.len;
        let dataEnd = s.unknown ? segEnd : dataStart + s.value;
        if (e.id === 0x1654ae6b) {
            const text = Buffer.from(b.subarray(dataStart, dataEnd)).toString('latin1');
            for (const m of text.matchAll(/V_[A-Z]+/g)) codecs.push(m[0]);
        }
        if (e.id === 0x1f43b675) {
            let c = dataStart;
            let first = true;
            while (c < dataEnd) {
                const ce = elementId(b, c);
                if (s.unknown && LEVEL1.has(ce.id)) {
                    dataEnd = c;
                    break;
                }
                const cs = vint(b, c + ce.len);
                const cd = c + ce.len + cs.len;
                if (ce.id === 0xbf) {
                    assert.ok(first, 'the CRC-32 is the first child');
                    const stored = b[cd] | (b[cd + 1] << 8) | (b[cd + 2] << 16) | (b[cd + 3] << 24);
                    assert.equal(stored >>> 0, crc32(b.subarray(cd + 4, dataEnd)) >>> 0, 'Cluster CRC-32');
                    crcClusters++;
                }
                if (ce.id === 0xa3) {
                    const tn = vint(b, cd);
                    const payloadOffset = cd + tn.len + 3;
                    blocks.push({payloadOffset, payloadSize: cd + cs.value - payloadOffset, track: tn.value, flags: b[cd + tn.len + 2]});
                }
                first = false;
                c = cd + cs.value;
            }
        }
        at = dataEnd;
    }
    return {blocks, codecs, segmentUnknown: segSize.unknown, crcClusters};
}

export function readCsv(text: string) {
    const lines = text.split('\n');
    const torn = lines.pop()!;
    const header: Record<string, string> = {};
    let i = 0;
    for (; lines[i].startsWith('# '); i++) {
        const [k, ...v] = lines[i].slice(2).split('=');
        header[k] = v.join('=');
    }
    const columns = lines[i++].split(',');
    const rows: {fields: Record<string, string>; line: string}[] = [];
    for (; i < lines.length && !lines[i].startsWith('# '); i++) {
        const parts = lines[i].split(',');
        rows.push({fields: Object.fromEntries(columns.map((c, j) => [c, parts[j]])), line: lines[i]});
    }
    return {header, columns, rows, footer: lines.slice(i), torn};
}

function checkTake(built: BuiltTake) {
    for (const cam of built.cameras) {
        if (cam.plan.noMkv || cam.plan.noCsv || cam.plan.mkv.noMagic || built.plan.deleteAfter?.includes(cam.csv)) continue;
        const mkv = new Uint8Array(readFileSync(path.join(built.dir, cam.mkv)));
        const csv = readCsv(readFileSync(path.join(built.dir, cam.csv), 'utf8'));
        const cut = cam.plan.mkv.cutInBlock;
        const walked = walkMkv(cut === undefined ? mkv : mkv.subarray(0, cam.blockPayloadEnds[cut - 1]));
        assert.deepEqual(walked.codecs, ['V_MJPEG'], 'one V_MJPEG track');
        const withBlock = csv.rows.filter(r => r.fields.byte_offset !== '');
        const extra = (cam.plan.mkv.extraBlockAtEnd ? 1 : 0) + cam.plan.rows.filter(r => r.extraBlockAfter).length;
        if (cam.plan.mkv.cutInBlock === undefined) assert.equal(walked.blocks.length, withBlock.length + extra, `${cam.mkv}: one block per row with byte fields`);
        let b = 0;
        csv.rows.forEach((r, k) => {
            const plan = cam.plan.rows[k];
            const body = r.line.slice(0, r.line.lastIndexOf(','));
            const crc = (crc32(Buffer.from(body)) >>> 0).toString(16).padStart(8, '0');
            if (!plan.badCrc) assert.equal(r.fields.crc32, crc, `${cam.csv} row ${k} CRC`);
            if (r.fields.byte_offset === '' || r.fields.byte_offset === undefined) return;
            if (b >= walked.blocks.length) return;   // a cut file
            const blk = walked.blocks[b++];
            if (!plan.offsetDelta) assert.equal(Number(r.fields.byte_offset), blk.payloadOffset, `${cam.csv} row ${k} offset`);
            if (!plan.fields?.byte_size && !cam.plan.columns) assert.equal(Number(r.fields.byte_size), blk.payloadSize, `${cam.csv} row ${k} size`);
            const jpeg = mkv.subarray(blk.payloadOffset, blk.payloadOffset + blk.payloadSize);
            assert.deepEqual([jpeg[0], jpeg[1]], [0xff, 0xd8], 'SOI');
            if (!plan.jpeg?.trailingBytes) assert.deepEqual([jpeg[jpeg.length - 2], jpeg[jpeg.length - 1]], [0xff, 0xd9], 'EOI');
            if (plan.extraBlockAfter) b++;
        });
    }
}

test('T-PLAY-01 the builder writes normal and missing from the format rules', t => {
    const root = tempRoot(t);
    for (const name of ['normal', 'missing']) {
        const built = buildTake(name, root);
        checkTake(built);
        for (const cam of built.cameras) {
            const csv = readCsv(readFileSync(path.join(built.dir, cam.csv), 'utf8'));
            const missingRows = csv.rows.filter(r => Number(r.fields.flags) & 16).length;
            const end = csv.footer.find(l => l.startsWith('# end '))!;
            assert.match(end, new RegExp(` missing=${missingRows} encode_skips=`), '`missing=` counts the missing rows, before the last key');
            const first = cam.payloads[cam.plan.rows.findIndex(r => r.kind === 'real')]!;
            const ph = readSof(cam.placeholder);
            const fr = readSof(first);
            assert.deepEqual(ph, fr, 'the placeholder has the size and the sampling factors of the first real frame');
            cam.plan.rows.forEach((r, k) => {
                if (r.kind === 'missing') assert.equal(cam.payloads[k], cam.placeholder, `row ${k} points at the placeholder`);
            });
        }
        if (name === 'missing') {
            const c1 = readCsv(readFileSync(path.join(built.dir, built.cameras[1].csv), 'utf8'));
            assert.equal(c1.rows.filter(r => Number(r.fields.flags) & 16).length, 22);
            assert.equal(c1.rows[0].fields.arrival_ns, '', 'row 0 has no time');
            assert.notEqual(c1.rows[10].fields.arrival_ns, '', 'row 10 keeps its time');
        }
    }
});

test('fixture self-test: every take of section 12.2 builds and parses back', t => {
    const root = tempRoot(t);
    const names = [...Object.keys(PLANS), ...Object.keys(HEADER_VARIANTS), ...Object.keys(VERSION_VARIANTS)];
    for (const name of names) {
        const built = buildTake(name, root);
        if (name.startsWith('header_') || name === 'pairs') continue;   // columns or names that the walk does not model
        checkTake(built);
    }
});

test('fixture self-test: live and short files have the FFmpeg live form', t => {
    const root = tempRoot(t);
    const short = buildTake('dead_short', root);
    const c3 = short.cameras[3];
    const w = walkMkv(new Uint8Array(readFileSync(path.join(short.dir, c3.mkv))));
    assert.equal(w.segmentUnknown, true, 'unknown-size Segment');
    assert.equal(w.blocks.length, 80);
    assert.equal(w.crcClusters, 80, 'a CRC-32 child in each Cluster');
    const csv = readCsv(readFileSync(path.join(short.dir, c3.csv), 'utf8'));
    assert.equal(csv.rows.length, 120);
    assert.equal(csv.rows.filter(r => r.fields.byte_offset === '').length, 40);
    assert.ok(csv.footer[0].startsWith('# repair ') && csv.footer[1].startsWith('# end '));

    const unf = buildTake('unfinished', root);
    const c1 = unf.cameras[1];
    const w1 = walkMkv(new Uint8Array(readFileSync(path.join(unf.dir, c1.mkv))).subarray(0, c1.blocks[96]!.offset + c1.blocks[96]!.size));
    assert.equal(w1.blocks.length, 97, 'camera 1 of unfinished: 97 complete blocks');
    assert.ok(c1.mkvSize > c1.blocks[96]!.offset + c1.blocks[96]!.size, 'then part of block 97');
    const c3u = readCsv(readFileSync(path.join(unf.dir, unf.cameras[3].csv), 'utf8'));
    assert.equal(c3u.rows.length, 110);
    assert.equal(c3u.torn, '110,1110,3676', 'a torn last line');
    const wide = buildTake('block_wide', root);
    checkTake(wide);
});

test('fixture self-test: the barcode reader reads a rotated, fitted image', () => {
    // Render the design of the image (not the JPEG) into a virtual canvas with the inverse of the
    // clockwise rotation and the "contain" fit, then read it back.
    for (const rotation of [0, 90, 180, 270]) {
        for (const [w, h] of [[640, 320], [512, 256], [300, 500]]) {
            const image = barcodeImage(5, 1234);
            const [rw, rh] = rotation % 180 === 0 ? [IMAGE_WIDTH, IMAGE_HEIGHT] : [IMAGE_HEIGHT, IMAGE_WIDTH];
            const scale = Math.min(w / rw, h / rh);
            const ox = (w - rw * scale) / 2;
            const oy = (h - rh * scale) / 2;
            const pixel = (cx: number, cy: number): [number, number, number] => {
                const rx = (cx + 0.5 - ox) / scale;
                const ry = (cy + 0.5 - oy) / scale;
                if (rx < 0 || ry < 0 || rx >= rw || ry >= rh) return [0, 0, 0];
                const [x, y] = rotation === 90 ? [ry, IMAGE_HEIGHT - rx] : rotation === 180 ? [IMAGE_WIDTH - rx, IMAGE_HEIGHT - ry] : rotation === 270 ? [IMAGE_WIDTH - ry, rx] : [rx, ry];
                return ycbcrToRgb(image(Math.floor(x), Math.floor(y)));
            };
            const r = readTile(pixel, w, h, rotation);
            assert.equal(r.camera, 5, `rotation ${rotation} ${w}x${h}`);
            assert.equal(r.position, 1234);
            r.quadrants.forEach((q, i) => assert.ok(near(q, ycbcrToRgb(QUADRANTS[i]), 0), `quadrant ${i}`));
        }
    }
});

test('fixture self-test: the Annex K tables have 12 and 162 values', () => {
    for (const tbl of Object.values(ANNEX_K)) assert.equal(tbl.bits.reduce((a, b) => a + b, 0), tbl.vals.length);
    assert.equal(ANNEX_K.acLum.vals.length, 162);
    assert.equal(ANNEX_K.acChr.vals.length, 162);
});

// Optional: PyAV of the repository environment reads a built fixture. Skipped when uv or PyAV is absent.
test('fixture self-test (optional): PyAV reads the blocks of a finished and a short file', t => {
    const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../../..');
    const probe = spawnSync('uv', ['run', '--no-sync', 'python', '-c', 'import av'], {cwd: repo, encoding: 'utf8'});
    if (probe.error || probe.status !== 0) {
        t.skip('uv or PyAV is not available');
        return;
    }
    const root = tempRoot(t);
    const normal = buildTake('normal', root);
    const short = buildTake('dead_short', root);
    const script = [
        'import av, sys',
        'for p in sys.argv[1:]:',
        '    c = av.open(p)',
        '    n = sum(1 for pk in c.demux(video=0) if pk.size)',
        '    c.seek(0)',
        '    f = next(c.decode(video=0))',
        '    print(n, f.width, f.height)',
    ].join('\n');
    const files = [path.join(normal.dir, normal.cameras[0].mkv), path.join(short.dir, short.cameras[3].mkv)];
    const r = spawnSync('uv', ['run', '--no-sync', 'python', '-c', script, ...files], {cwd: repo, encoding: 'utf8'});
    assert.equal(r.status, 0, r.stderr);
    assert.deepEqual(r.stdout.trim().split(/\r?\n/), ['120 256 128', '80 256 128']);
});

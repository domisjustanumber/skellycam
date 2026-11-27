// Unit tests of the camera label of the player (specs/player.md 8.4 and 5.8; ADR-70J6, ADR-WP77):
// T-PLAY-83 and T-PLAY-84.
import assert from 'node:assert/strict';
import test from 'node:test';
import type {TestContext} from 'node:test';
import {defaultTake, manifestText} from '../fixtures/take.ts';
import type {TakePlan} from '../fixtures/take.ts';
import {nodeTakeFiles} from '../fixtures/node-take-files.ts';
import {writeTake} from '../fixtures/take.ts';
import {FakeLoop, FakeTile, player, settle, tempRoot, testDecoder} from './helpers.ts';

const MiB = 1024 * 1024;

type Config = {os_index?: unknown; os_name?: unknown} | null;   // null: no member for the camera

/** The capture info of the take: one member for each camera with a config, keyed by `camera_key`. */
function infoText(plan: TakePlan, configs: Config[], over: Record<string, unknown> = {}): string {
    const camera_configs: Record<string, unknown> = {};
    plan.cameras.forEach((c, i) => {
        const cfg = configs[i];
        if (cfg === null) return;
        camera_configs[c.key] = {
            camera_label: c.label, user_name: null, key_origin: 'provisional',
            device: {model: null, os_name: cfg.os_name, vendor_id: null, product_id: null, serial: null, port_path: null,
                     os_device_id: null, backend: 'media_foundation', os_index: cfg.os_index},
        };
    });
    return JSON.stringify({skellyfileformat: 'capture_info', format_version: '2.0', format_prerelease: 1, writer: 'fixture 1.0.0',
        take_uuid: plan.takeUuid, camera_configs, audio: null, ...over}, null, 2) + '\n';
}

const USABLE: Config[] = [{os_index: 0, os_name: 'USB Camera'}, {os_index: 1, os_name: 'Cam One'},
    {os_index: 2, os_name: 'Cam Two'}, {os_index: 3, os_name: 'Cam Three'}];

interface Opened {
    labels: string[];
    tileCameras: (string | undefined)[];
    warnings: string[];
    order: string[];
    frameCount: number;
    errors: number;
    wholeReads: {path: string; maxBytes: number}[];
}

/** Open a take with a spy on the whole reads; `fail` makes the read of one path fail. */
async function open(t: TestContext, plan: TakePlan, fail?: string): Promise<Opened> {
    const {openTake} = await player();
    const built = writeTake(tempRoot(t), plan);
    const inner = await nodeTakeFiles(built.dir);
    const wholeReads: {path: string; maxBytes: number}[] = [];
    const files = {
        ...inner,
        readRange: inner.readRange,
        readWhole: (p: string, maxBytes: number) => {
            wholeReads.push({path: p, maxBytes});
            return p === fail ? Promise.reject(new Error(`test read fault: ${p}`)) : inner.readWhole(p, maxBytes);
        },
        close: inner.close,
    };
    const loop = new FakeLoop();
    const p = await openTake(files, {frameLoop: loop.frameLoop, decode: testDecoder(built).decode});
    t.after(() => p.close());
    let errors = 0;
    p.on('error', () => void errors++);
    const tiles = p.state.cameras.map(() => new FakeTile());
    tiles.forEach((tile, i) => p.attachTile(i, tile as never));
    await settle();
    const s = p.state;
    return {
        labels: s.cameras.map(c => c.label), tileCameras: tiles.map(tile => tile.label?.camera), warnings: s.take.warnings,
        order: s.cameras.map(c => c.name), frameCount: s.frameCount, errors, wholeReads,
    };
}

function withInfo(name: string, info: string | ((plan: TakePlan) => string)): TakePlan {
    const plan = defaultTake(name);
    plan.extraFiles = [{path: `${plan.rec}_info.json`, content: typeof info === 'string' ? info : info(plan)}];
    return plan;
}

// one take name, so that the file names and thus the camera order compare
test('T-PLAY-83 the label from the capture info, camera by camera', async t => {
    const bare = await open(t, defaultTake('label'));
    const plan = defaultTake('label');
    const own = plan.cameras.map(c => c.label);
    plan.extraFiles = [{path: `${plan.rec}_info.json`, content: infoText(plan, [
        {os_index: 0, os_name: 'USB Camera'}, {os_index: 1, os_name: null}, null, {os_index: '3', os_name: 'Cam Three'}])}];
    const mixed = await open(t, plan);
    assert.deepEqual(mixed.labels, ['Camera 0 · USB Camera', own[1], own[2], own[3]], 'the label of each camera');
    assert.deepEqual(mixed.tileCameras, mixed.labels, 'the tile label is the label of the state');
    assert.deepEqual(mixed.order, bare.order, 'the camera order does not change');
    assert.deepEqual(mixed.warnings, bare.warnings, 'no warning from the label');
    assert.equal(mixed.frameCount, bare.frameCount);
    assert.equal(mixed.errors, 0, 'no error event');

    const same = withInfo('label', p => infoText(p, [USABLE[0], USABLE[1], {os_index: 7, os_name: 'Same Cam'}, {os_index: 7, os_name: 'Same Cam'}]));
    const dup = await open(t, same);
    assert.deepEqual(dup.labels.slice(2), ['Camera 7 · Same Cam', 'Camera 7 · Same Cam'], 'equal labels, as they are');
    assert.ok(!dup.warnings.includes('duplicate_label'), 'duplicate_label comes only from the sidecars');
    assert.deepEqual(dup.order, bare.order);

    const odd = withInfo('label', p => infoText(p, [USABLE[0], {os_index: 1, os_name: '  '}, {os_index: -1, os_name: 'Cam Two'}, USABLE[3]]));
    const oddOwn = odd.cameras.map(c => c.label);
    const o = await open(t, odd);
    assert.deepEqual(o.labels, ['Camera 0 · USB Camera', oddOwn[1], oddOwn[2], 'Camera 3 · Cam Three'], 'a blank name and a negative index fall back');
});

test('T-PLAY-84 the file-level fallbacks of the label', async t => {
    const bare = await open(t, defaultTake('fall_bare'));
    const usable = withInfo('fall_usable', p => infoText(p, USABLE));
    const own = usable.cameras.map(c => c.label);
    const u = await open(t, usable);
    assert.deepEqual(u.labels, ['Camera 0 · USB Camera', 'Camera 1 · Cam One', 'Camera 2 · Cam Two', 'Camera 3 · Cam Three']);
    const infoReads = u.wholeReads.filter(r => r.path === `${usable.rec}_info.json`);
    assert.equal(infoReads.length, 1, 'the capture info is read once');
    assert.equal(infoReads[0].maxBytes, 16 * MiB, 'with the limit 16 MiB');

    const cases: [string, TakePlan, string?][] = [];
    const missing = defaultTake('fall_missing');
    cases.push(['missing', missing]);
    cases.push(['not JSON', withInfo('fall_not_json', '{"skellyfileformat": "capture_info", ')]);
    cases.push(['another take_uuid', withInfo('fall_uuid', p => infoText(p, USABLE, {take_uuid: 'ffffffffffffffffffffffffffffffff'}))]);
    cases.push(['another skellyfileformat', withInfo('fall_kind', p => infoText(p, USABLE, {skellyfileformat: 'processing_info'}))]);
    cases.push(['camera_configs not an object', withInfo('fall_configs', p => infoText(p, USABLE, {camera_configs: [1, 2]}))]);
    const faulty = withInfo('fall_fault', p => infoText(p, USABLE));
    cases.push(['a read that fails', faulty, `${faulty.rec}_info.json`]);
    const slash = withInfo('fall_slash', p => infoText(p, USABLE));
    // the name points at a usable capture info in the media folder: only a root file of the take is read
    const m = JSON.parse(manifestText(slash));
    m.recording_name = `synchronized_videos/${slash.rec}`;
    slash.extraFiles!.push({path: 'recording_manifest.json', content: JSON.stringify(m, null, 2) + '\n'},
        {path: `synchronized_videos/${slash.rec}_info.json`, content: infoText(slash, USABLE)});
    cases.push(['a recording_name with /', slash]);
    const noManifest = withInfo('fall_no_manifest', p => infoText(p, USABLE));
    noManifest.manifest = 'missing';
    cases.push(['no manifest', noManifest]);

    for (const [name, plan, fail] of cases) {
        const o = await open(t, plan, fail);
        assert.deepEqual(o.labels, own, `${name}: camera_label on each camera`);
        assert.equal(o.errors, 0, `${name}: no error event`);
        assert.equal(o.frameCount, bare.frameCount, `${name}: the take opens`);
        const expected = plan.manifest === 'missing' ? [...bare.warnings, 'manifest_missing'].sort() : bare.warnings;
        assert.deepEqual(o.warnings, [...new Set(expected)].sort(), `${name}: no warning from the label`);
        if (name === 'a recording_name with /' || name === 'no manifest') {
            assert.ok(!o.wholeReads.some(r => r.path.endsWith('_info.json')), `${name}: no read of a capture info`);
        }
    }
});

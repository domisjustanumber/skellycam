// T-TIM-24 (the TypeScript part) and the Node part of T-TIM-26: the summary function and the buffers of
// tile/timings.ts (specs/capture-timings.md 5.2, 6.1, 7; ADR-W3VD items 1, 2, 4 and 11).
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {product} from './helpers.ts';

type TimingsModule = typeof import('../../tile/timings.ts');

const timings = () => product<TimingsModule>('tile/timings.ts');
const ROOT = new URL('../../../../../', import.meta.url); // the repository root

test('T-TIM-24 one shape: buildSummary gives the JSON of the shared fixture of the Python test', async () => {
    const {buildSummary} = await timings();
    const fixture = JSON.parse(readFileSync(new URL('skellycam/tests/capture_timings/summary_fixture.json', ROOT), 'utf8'));
    assert.equal(JSON.stringify(buildSummary(fixture.input)), JSON.stringify(fixture.expected), 'the same JSON, in the same key order');
});

test('T-TIM-24 the copy of the step table equals STEPS and DELAYS of capture_timings.py', async () => {
    const {STEPS, DELAYS} = await timings();
    const source = readFileSync(new URL('skellycam/core/capture_timings.py', ROOT), 'utf8');
    const steps = Object.fromEntries([...source.matchAll(/^ {4}"(\w+)": \("(\w+)", "(\w+)", "(\w+)"\),$/gm)].map(m => [m[1], [m[2], m[3], m[4]]]));
    const delays = Object.fromEntries([...(source.match(/^DELAYS = \{(.*)\}$/m)?.[1] ?? '').matchAll(/"(\w+)": "(\w+)"/g)].map(m => [m[1], m[2]]));
    assert.equal(Object.keys(steps).length, 24, 'the Python table as this test reads it');
    assert.equal(Object.keys(delays).length, 3, 'the Python delays as this test reads it');
    assert.deepEqual(Object.keys(STEPS), Object.keys(steps), 'the ids, in the order of table 3.1');
    assert.deepEqual(STEPS, steps);
    assert.deepEqual(DELAYS, delays);
});

test('T-TIM-26 (Node part) a handle: the window of a takeSummaries(), the newest 512 samples, seq', async () => {
    const {TileTimings} = await timings();
    let ms = 50;
    const tileTimings = new TileTimings(() => ms);
    const handle = tileTimings.handle('cam1', null);
    assert.equal(tileTimings.handle('cam1', 'g2'), handle, 'one handle for each camera id');
    for (let i = 1; i <= 600; i++) handle.add('ui_draw', i / 1000);
    handle.add('receive_to_draw', 12.3456);
    ms = 1050.5;
    const [first, ...more] = tileTimings.takeSummaries();
    assert.deepEqual(more, []);
    assert.equal(first.camera_group_id, 'g2', 'the second call set the group id');
    assert.equal(first.seq, 0);
    assert.equal(first.window_end_ns, 1_050_500_000);
    assert.equal(first.window_s, 1.001);
    assert.deepEqual(first.steps.ui_draw, {kind: 'work', cadence: 'frame', where: 'ui_tile', n: 600, p50_ms: 0.344, p95_ms: 0.575, max_ms: 0.6});
    assert.deepEqual(first.steps.ui_jpeg_decode, {kind: 'work', cadence: 'frame', where: 'ui_tile', n: 0, p50_ms: null, p95_ms: null, max_ms: null});
    assert.deepEqual(first.delays.receive_to_draw, {where: 'ui_tile', n: 1, p50_ms: 12.346, p95_ms: 12.346, max_ms: 12.346});
    handle.add('ui_draw', 2);
    const [second] = tileTimings.takeSummaries();
    assert.equal(second.seq, 1);
    assert.equal(second.window_s, 0);
    assert.deepEqual(second.steps.ui_draw, {kind: 'work', cadence: 'frame', where: 'ui_tile', n: 1, p50_ms: 2, p95_ms: 2, max_ms: 2});
});

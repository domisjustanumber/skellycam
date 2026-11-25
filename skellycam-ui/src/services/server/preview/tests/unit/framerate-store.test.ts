// T-PRV-41 and T-PRV-53: the frame rate store keeps each camera and each count apart; the Displayed series comes from
// the drawn frames [Q3] (specs/preview-4b.md 5.8, 7.4). The store API of the tests is in ADR-70WD.
import assert from 'node:assert/strict';
import test from 'node:test';
import {FakeTile, fakes, flush, framerateStore, message, previewTiles} from './helpers.ts';

function rate(fps: number) {
    const ms = 1000 / fps;
    return {
        mean_frame_duration_ms: ms, mean_frames_per_second: fps, frame_duration_max: ms, frame_duration_min: ms,
        frame_duration_mean: ms, frame_duration_stddev: 0, frame_duration_median: ms, frame_duration_coefficient_of_variation: 0,
        calculation_window_size: 8, framerate_source: 'Captured',
    };
}

function update(cameras: Record<string, [number | null, number, number, number]>) {
    const out: Record<string, unknown> = {};
    for (const [id, [fps, notShown, ringSkipped, oversize]] of Object.entries(cameras)) {
        out[id] = {delivered_framerate: fps === null ? null : rate(fps), not_shown_count: notShown, ring_skipped_count: ringSkipped, oversize_count: oversize};
    }
    return {message_type: 'framerate_update', camera_group_id: 'g1', cameras: out};
}

function appStateWithReplaced(replaced: Record<string, number>) {
    const cameras: Record<string, unknown> = {};
    for (const [id, n] of Object.entries(replaced)) cameras[id] = {alive: true, status: {state: 'ready', replaced_count: n}};
    return {message_type: 'app_state', server_pid: 1, state: {camera_groups: {g1: {id: 'g1', alive: true, recording_in_progress: false, configs: {}, cameras}}}};
}

test('T-PRV-41 the frame rate store keeps each camera and each count apart', async () => {
    const {FramerateStore} = await framerateStore();
    const store = new FramerateStore();
    for (const name of ['recordFramerateUpdate', 'recordAppState', 'recordDrawn', 'getCamera', 'cameraIds', 'clear'] as const) {
        assert.equal(typeof (store as unknown as Record<string, unknown>)[name], 'function', `FramerateStore.${name}`);
    }
    store.recordFramerateUpdate(update({a1b2: [29.0, 3, 5, 2], c3d4: [15.0, 11, 0, 7]}) as never);
    store.recordFramerateUpdate(update({a1b2: [30.0, 4, 5, 2], c3d4: [14.0, 12, 1, 7]}) as never);
    store.recordAppState(appStateWithReplaced({a1b2: 13, c3d4: 17}) as never);

    const a = store.getCamera('a1b2')!;
    const c = store.getCamera('c3d4')!;
    assert.deepEqual(store.cameraIds().sort(), ['a1b2', 'c3d4']);
    assert.equal(a.captured.current?.mean_frames_per_second, 30.0);
    assert.equal(c.captured.current?.mean_frames_per_second, 14.0);
    assert.deepEqual([a.notShown, a.ringSkipped, a.oversize, a.replaced], [4, 5, 2, 13]);
    assert.deepEqual([c.notShown, c.ringSkipped, c.oversize, c.replaced], [12, 1, 7, 17]);
    // the exact values: no value is a sum of two counts (Not shown 4 and Ring skipped 5 are never shown as 9) [A7]
    assert.equal(a.displayed.current, null, 'no Displayed value before a drawn frame');

    const capturedBefore = JSON.stringify(store.getCamera('a1b2')!.captured);
    for (let i = 0; i < 5; i++) store.recordDrawn('a1b2', 1000 + i * 20);
    assert.equal(JSON.stringify(store.getCamera('a1b2')!.captured), capturedBefore, 'recordDrawn does not change Captured');
    assert.ok(store.getCamera('a1b2')!.displayed.current, 'a Displayed value after drawn frames');
    assert.equal(store.getCamera('c3d4')!.displayed.current, null, 'the drawn frames of a1b2 are not the frames of c3d4');

    store.clear();
    assert.deepEqual(store.cameraIds(), []);
    assert.equal(store.getCamera('a1b2'), null);
});

test('T-PRV-53 the Displayed series comes from the drawn frames [Q3]', async () => {
    const {FramerateStore} = await framerateStore();
    const {PreviewTiles} = await previewTiles();
    const store = new FramerateStore();
    const f = fakes();
    const tiles = new PreviewTiles(f.sendReady, (id, at) => store.recordDrawn(id, at), f.now);
    tiles.setTile('a1b2', new FakeTile('drawn'));
    let frame = 0;
    const draw = async (stepMs: number) => {
        f.clock.ms += stepMs;
        tiles.receive(message({camera: 'a1b2', frame: frame++}));
        tiles.tick();
        await flush();
    };

    for (let i = 0; i < 31; i++) await draw(i === 0 ? 0 : 100 / 3);
    const first = store.getCamera('a1b2')!;
    assert.ok(Math.abs(first.displayed.current!.mean_frames_per_second - 30.0) <= 0.1, `Displayed ${first.displayed.current?.mean_frames_per_second}`);
    assert.equal(first.displayed.aggregate?.calculation_window_size, 30, '30 times between 31 drawn frames');

    f.clock.ms += 2000; // a gap of 2 s with no tick
    for (let i = 0; i < 31; i++) await draw(i === 0 ? 0 : 50 / 3);
    const last = store.getCamera('a1b2')!;
    assert.ok(Math.abs(last.displayed.current!.mean_frames_per_second - 60.0) <= 0.1, `Displayed ${last.displayed.current?.mean_frames_per_second}`);
    assert.equal(last.displayed.aggregate?.calculation_window_size, 60, 'the gap of 2 s adds no value');
    assert.ok(last.displayed.aggregate!.frame_duration_max < 1000, 'no time longer than 1 s');

    f.clock.ms += 50 / 3;
    tiles.receive(message({camera: 'a1b2', frame: frame++, flags: 0x04}));
    tiles.tick();
    await flush();
    tiles.setOverlay('a1b2', {cameraState: 'ready'});
    f.clock.ms += 50 / 3;
    tiles.tick();
    await flush();
    assert.equal(store.getCamera('a1b2')!.displayed.aggregate?.calculation_window_size, 60, 'the flagged message and the overlay update add no value');
    assert.equal(store.getCamera('a1b2')!.captured.current, null, 'Captured stays empty');
    assert.equal(store.getCamera('a1b2')!.captured.aggregate, null);
});

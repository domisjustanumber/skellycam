// T-PRV-40: the values from app_state and framerate_update: states, lists, label, order [Q5, Q7]
// (specs/preview-4b.md 5.4, 5.5, 7.4). Plain objects; no store, no React. The label functions are `cameraLabel` and
// `labelText` of camera-labels.ts: camera-requests.md 1.8 renamed the two label functions of the 4b spec [ADR-70WD].
import assert from 'node:assert/strict';
import test from 'node:test';
import {cameraLabel, labelText} from '../../../../../store/slices/cameras/camera-labels.ts';
import {serverMessages} from './helpers.ts';

const STATES = ['starting', 'waiting', 'failed', 'checking', 'too_slow', 'ready', 'recording', 'dead'] as const;
const STREAMING = new Set(['checking', 'too_slow', 'ready', 'recording']);

type Status = {state?: unknown; replaced_count?: number} | undefined;

function appState(groups: Record<string, {alive: boolean; cameras: Record<string, Status>; configs?: Record<string, {camera_index: number; camera_name: string}>}>) {
    const camera_groups: Record<string, unknown> = {};
    for (const [id, g] of Object.entries(groups)) {
        const cameras: Record<string, unknown> = {};
        for (const [cid, status] of Object.entries(g.cameras)) cameras[cid] = status === undefined ? {alive: true} : {alive: true, status};
        const configs: Record<string, unknown> = {};
        for (const cid of Object.keys(g.cameras)) {
            const c = g.configs?.[cid] ?? {camera_index: 0, camera_name: `config name of ${cid}`};
            configs[cid] = {camera_id: cid, ...c};
        }
        camera_groups[id] = {id, alive: g.alive, recording_in_progress: false, cameras, configs};
    }
    return {message_type: 'app_state', server_pid: 1, state: {camera_groups}};
}

const LIST = [
    {id: 'c1', index: 9, name: 'Logitech C920'},
    {id: 'c2', index: 2, name: 'Kiyo Pro'},
    {id: 'c3', index: 6, name: 'c922 Pro Stream Webcam'},
];

test('T-PRV-40 the camera state of each camera, and connectedCameraIds for each state [Q7, Q10]', async () => {
    const {appStateValues} = await serverMessages();
    for (const state of STATES) {
        const values = appStateValues(appState({g1: {alive: false, cameras: {c3: {state}}}}) as never, LIST);
        assert.equal(values.overlays.c3.cameraState, state);
        assert.deepEqual(values.gridCameraIds, ['c3'], `${state}: the camera has a tile`);
        assert.deepEqual(values.connectedCameraIds, STREAMING.has(state) ? ['c3'] : [], `${state}: connectedCameraIds`);
    }
    for (const status of [{state: null}, {state: 'unknown'}, undefined] as Status[]) {
        const values = appStateValues(appState({g1: {alive: true, cameras: {c3: status}}}) as never, LIST);
        assert.equal(values.overlays.c3.cameraState, null, `${JSON.stringify(status)}: no state`);
        assert.deepEqual(values.gridCameraIds, ['c3']);
        assert.deepEqual(values.connectedCameraIds, []);
    }
});

test('T-PRV-40 the grid lists each camera with no filter on alive, in the order of the camera list [Q5, Q7]', async () => {
    const {appStateValues} = await serverMessages();
    const message = appState({
        g1: {
            alive: false,
            cameras: {c1: {state: 'failed'}, c2: {state: 'starting'}, c3: {state: 'ready'}, c4: {state: 'ready'}},
            configs: {
                c1: {camera_index: 1, camera_name: 'stale name'}, c2: {camera_index: 1, camera_name: 'stale name'},
                c3: {camera_index: 1, camera_name: 'stale name'}, c4: {camera_index: 4, camera_name: 'USB Camera'},
            },
        },
    });
    const values = appStateValues(message as never, LIST);
    assert.deepEqual(values.gridCameraIds, ['c2', 'c4', 'c3', 'c1'], 'list numbers 2, 4, 6, 9');
    assert.equal(values.overlays.c3.label, 'Camera 6 · c922 Pro Stream Webcam');
    assert.equal(values.overlays.c4.label, 'Camera 4 · USB Camera', 'not in the list: the config');
    assert.equal(values.overlays.c1.label, cameraLabel(LIST[0]));
    for (const [id, o] of Object.entries(values.overlays)) {
        for (const other of ['c1', 'c2', 'c3', 'c4']) assert.ok(!o.label.includes(other), `the label of ${id} holds the camera id ${other}`);
    }
    const notAlive = appStateValues(appState({g1: {alive: false, cameras: {c1: {state: 'failed'}, c2: {state: 'starting'}, c3: {state: 'ready'}}}}) as never, LIST);
    assert.deepEqual(notAlive.connectedCameraIds, ['c3'], 'the group that is not alive: only c3 streams');
    assert.deepEqual(notAlive.gridCameraIds, ['c2', 'c3', 'c1'], 'three tiles, although the group is not alive');
});

test('T-PRV-40 one label form everywhere [Q13]', () => {
    assert.equal(cameraLabel(LIST[2]), 'Camera 6 · c922 Pro Stream Webcam');
    assert.equal(labelText('camera c3 is failed', LIST), 'Camera 6 · c922 Pro Stream Webcam is failed');
});

test('T-PRV-40 the rate text from framerate_update [A3]', async () => {
    const {rateTexts, isFramerateUpdate} = await serverMessages();
    const update = {
        message_type: 'framerate_update', camera_group_id: 'g1',
        cameras: {
            c1: {delivered_framerate: null, not_shown_count: 0, ring_skipped_count: 0, oversize_count: 0},
            c3: {delivered_framerate: {mean_frames_per_second: 29.97}, not_shown_count: 0, ring_skipped_count: 0, oversize_count: 0},
        },
    };
    assert.equal(isFramerateUpdate(update), true);
    // the old key is built at run time, so that the search of T-PRV-30 does not find it here
    const oldShape = {message_type: 'framerate_update', camera_group_id: 'g1', [['backend', 'framerate'].join('_')]: {}};
    assert.equal(isFramerateUpdate(oldShape), false, 'the old shape');
    assert.equal(isFramerateUpdate({message_type: 'app_state'}), false);
    assert.deepEqual(rateTexts(update as never), {c1: null, c3: '30.0 fps'});
});

// Run: node --experimental-strip-types --test src/store/slices/error-detail.test.ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { errorDetail } from './error-detail.ts';

test('T4: a string detail is the text', () => {
    assert.equal(errorDetail({ detail: 'camera c3c6 is recording' }, 'Conflict'), 'camera c3c6 is recording');
});

test('T4: a 422 list detail gives each msg, not "[object Object]"', () => {
    const body = { detail: [
        { loc: ['body', 'camera_configs', 'a', 'framerate'], msg: 'Input should be 30 or 60', type: 'literal_error' },
        { loc: ['body'], msg: 'cameras a and b at 30 fps', type: 'value_error' },
    ] };
    assert.equal(errorDetail(body, 'Unprocessable Entity'), 'Input should be 30 or 60; cameras a and b at 30 fps');
});

test('T4: an object detail with no msg is shown as JSON', () => {
    assert.equal(errorDetail({ detail: { code: 'no-mode' } }, 'Unprocessable Entity'), '{"code":"no-mode"}');
    assert.equal(errorDetail({ detail: [{ code: 'x' }] }, 'Unprocessable Entity'), '{"code":"x"}');
});

test('T4: no JSON body (a 500 "Internal Server Error" page) or no detail gives the status text', () => {
    assert.equal(errorDetail(null, 'Internal Server Error'), 'Internal Server Error');
    assert.equal(errorDetail({}, 'Bad Request'), 'Bad Request');
    assert.equal(errorDetail({ detail: '' }, 'Bad Request'), 'Bad Request');
});

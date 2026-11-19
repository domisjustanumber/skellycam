// T-PLAY-39: the shared TakeFiles check suite on the Node implementation [L8]. The Node implementation
// is a fixture (specs/player.md section 12.2), so this test can pass before the product code exists.
import assert from 'node:assert/strict';
import test from 'node:test';
import {nodeTakeFiles, writeSuiteFolder} from '../fixtures/node-take-files.ts';
import {runTakeFilesChecks} from '../fixtures/take-files-checks.ts';
import {tempRoot} from './helpers.ts';

test('T-PLAY-39 the shared TakeFiles check suite on the Node implementation', async t => {
    const files = await nodeTakeFiles(await writeSuiteFolder(tempRoot(t)));
    const results = await runTakeFilesChecks(files);
    await files.close();
    assert.deepEqual(results.filter(r => !r.ok), []);
    assert.equal(results.length, 10);
});

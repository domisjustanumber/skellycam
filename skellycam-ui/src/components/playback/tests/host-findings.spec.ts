// T-PLAY-80: the loading message of the host view with a camera that has no image to show (ADR-5FBS).
import {expect} from '@playwright/test';
import {planOf} from '../../../player/tests/fixtures/takes.ts';
import {harnessTest} from '../../../player/tests/browser/harness.ts';

const test = harnessTest('host');

test('T-PLAY-80 the loading message goes away with a refused camera', async ({harness: h}) => {
    await h.requireProduct();
    const built = h.build(planOf('counts_refused'));
    await h.page.evaluate(f => window.host.mount(f), built.dir);
    await expect(h.page.getByText(/Frame \d+ \/ 120/)).toBeVisible();
    await expect(h.page.locator('canvas[data-camera-label]')).toHaveCount(4);
    await expect(h.page.getByText(/^\d+ \/ 4$/)).toHaveCount(0);
});

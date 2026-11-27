// The component and electron tests of the player (specs/player.md section 12.1) and the component tests of the
// step 4b preview (specs/preview-4b.md 7.4). Run them with `npm run test:player:browser`, which builds the
// harness first.
import {defineConfig} from '@playwright/test';

export default defineConfig({
    testDir: './src',
    testMatch: ['player/tests/browser/**/*.spec.ts', 'components/playback/tests/**/*.spec.ts', 'components/camera-views/tests/browser/**/*.spec.ts'],
    timeout: 60_000,
    expect: {timeout: 10_000},
    fullyParallel: false,
    workers: 1,
    retries: 0,
    forbidOnly: !!process.env.CI,
    reporter: [['list']],
    outputDir: 'test-results/player',
});

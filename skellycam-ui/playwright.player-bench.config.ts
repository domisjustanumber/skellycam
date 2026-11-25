// The benchmarks of the player, T-PLAY-65 to T-PLAY-70 (specs/player.md section 12.1), and of the step 4b
// preview, T-PRV-51 and T-PRV-52 (specs/preview-4b.md section 6). They run by hand
// on the Windows test machine, not in CI: `npx vite build -c vite.player-harness.config.ts`, then
// `npx playwright test -c playwright.player-bench.config.ts`. Results go to PLAYER_BENCH_OUT.
import {defineConfig} from '@playwright/test';

export default defineConfig({
    testDir: './src',
    testMatch: ['player/tests/bench/**/*.bench.ts', 'components/camera-views/tests/bench/**/*.bench.ts'],
    timeout: 30 * 60_000,
    workers: 1,
    retries: 0,
    reporter: [['list']],
    outputDir: 'test-results/player-bench',
});

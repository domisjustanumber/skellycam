// The benchmarks of the player, T-PLAY-65 to T-PLAY-70 (specs/player.md section 12.1). They run by hand
// on the Windows test machine, not in CI: `npx vite build -c vite.player-harness.config.ts`, then
// `npx playwright test -c playwright.player-bench.config.ts`. Results go to PLAYER_BENCH_OUT.
import {defineConfig} from '@playwright/test';

export default defineConfig({
    testDir: './src/player/tests/bench',
    testMatch: ['**/*.bench.ts'],
    timeout: 30 * 60_000,
    workers: 1,
    retries: 0,
    reporter: [['list']],
    outputDir: 'test-results/player-bench',
});

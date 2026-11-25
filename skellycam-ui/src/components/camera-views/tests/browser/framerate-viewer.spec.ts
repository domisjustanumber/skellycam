// Component test T-PRV-50 of the step 4b preview (specs/preview-4b.md 7.4, 5.8): the frame rate viewer, full and
// collapsed. The test reads the DOM and the SVG of the viewer, not a tile. Fake rings: camera A gets 3 oversize
// frames, 1 ring skip and `replaced_count` 7 in app_state.
import {expect} from '@playwright/test';
import {requirePreviewTiles, sleep, test, waitDrawn} from './preview-kit.ts';
import type {PreviewWindow} from './preview-kit.ts';

const OLD_NAMES = /\b(Server|Display|Delivered)\b/;

const viewer = (win: PreviewWindow) => win.page.evaluate(() => window.preview.viewer());
type Viewer = Awaited<ReturnType<typeof viewer>>;

/** The cell of a row in the column that has the header text `name`. */
function cell(v: Viewer, row: string[], name: string): string | undefined {
    const column = v.headers.findIndex(h => h === name);
    expect(column, `a column "${name}" in the statistics table (headers: ${v.headers.join(' | ')})`).toBeGreaterThanOrEqual(0);
    return row[column];
}

function row(v: Viewer, label: string, series: 'Captured' | 'Displayed'): string[] {
    const found = v.rows.filter(r => r[0].includes(label) && r[0].includes(series));
    expect(found.length, `one row "${label}" "${series}" in the statistics table (rows: ${v.rows.map(r => r[0]).join(' | ')})`).toBe(1);
    return found[0];
}

test('T-PRV-50 the frame rate viewer: Captured and Displayed for each camera, and the counts', async ({preview}) => {
    const A = {id: 'fa', number: 1, index: 3, name: 'Alpha cam'};
    const B = {id: 'fb', number: 2, index: 8, name: 'Beta cam'};
    const cams = [A, B];
    const label = (c: typeof A) => `Camera ${c.index} · ${c.name}`;
    const server = await preview.server({cameras: cams.map(c => ({id: c.id, number: c.number, index: 90 + c.number, name: c.name})), fps: 30});
    const win = await preview.open(server, cams.map(({id, index, name}) => ({id, index, name})), {viewer: 'full'});
    await requirePreviewTiles(win.page);
    await waitDrawn(win.page, cams.map(c => c.id));
    await server.command({cmd: 'oversize', camera: A.id, count: 3});
    await server.command({cmd: 'ring_skip', camera: A.id, count: 1});
    await server.command({cmd: 'set_replaced', camera: A.id, count: 7});
    await sleep(3000);   // framerate_update at 4 Hz, app_state at most each second

    // the full view
    let v = await viewer(win);
    expect(v.full, 'the full view of the frame rate viewer').toBe(true);
    const svg = v.svgTexts.join(' | ');
    for (const c of cams) {
        for (const series of ['Captured', 'Displayed'] as const) {
            expect(svg.includes(label(c)) && svg.includes(series),
                `the series "${series}" of ${label(c)} in the timeline and the histogram (SVG texts: ${svg})`).toBe(true);
            row(v, label(c), series);
        }
    }
    const names = [...v.headers, ...v.rows.map(r => r[0]), ...v.svgTexts];
    expect(names.filter(t => OLD_NAMES.test(t)), 'no series or column named Server, Display or Delivered').toEqual([]);
    const colour = (id: string) => new Set(v.series.filter(s => s.camera === id).map(s => s.colour));
    expect(colour(A.id).size, 'a colour for the series of A (svg [data-camera-id][data-series])').toBeGreaterThan(0);
    expect(colour(B.id).size, 'a colour for the series of B').toBeGreaterThan(0);
    expect([...colour(A.id)].some(c => colour(B.id).has(c)), 'the two cameras have two different colours').toBe(false);
    const capturedA = row(v, label(A), 'Captured');
    expect(cell(v, capturedA, 'Oversize'), 'Oversize of A').toBe('3');
    expect(cell(v, capturedA, 'Ring skipped'), 'Ring skipped of A').toBe('1');
    expect(cell(v, capturedA, 'Replaced'), 'Replaced of A').toBe('7');

    // the collapsed view
    await win.page.evaluate(() => window.preview.setViewer('collapsed'));
    await sleep(1000);
    v = await viewer(win);
    expect(v.collapsed, 'the collapsed view').not.toBeNull();
    for (const c of cams) {
        const m = new RegExp(`${label(c).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}: Captured (\\d+(?:\\.\\d+)?) fps, Displayed (\\d+(?:\\.\\d+)?) fps`).exec(v.collapsed ?? '');
        expect(m, `"${label(c)}: Captured <x> fps, Displayed <y> fps" in the collapsed view: ${v.collapsed}`).not.toBeNull();
        expect(Math.abs(Number(m![1]) - 30), `Captured of ${label(c)}: 30.0 ± 1 fps`).toBeLessThanOrEqual(1);
        expect(Number(m![2]), `Displayed of ${label(c)}: more than 0`).toBeGreaterThan(0);
    }

    // "Not shown" is the last not_shown_count of the server for this connection: the writers stop, so it stays
    for (const c of cams) await server.command({cmd: 'stop_writer', camera: c.id});
    await sleep(1500);
    await win.page.evaluate(() => window.preview.setViewer('full'));
    await sleep(1000);
    v = await viewer(win);
    const notShown = await server.command<{connections: Record<string, Record<string, number>>}>({cmd: 'not_shown'});
    const conn = String(Math.max(...Object.keys(notShown.connections).map(Number)));   // the one connection of this window
    for (const c of cams) {
        expect(cell(v, row(v, label(c), 'Captured'), 'Not shown'), `Not shown of ${label(c)}`).toBe(String(notShown.connections[conn]?.[c.id]));
    }
});

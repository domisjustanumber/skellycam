// The host view of the canvas player for new takes (specs/player.md section 10). It holds the grid of
// F1 to F3, the keys of F9 to F12 and F20, and today's PlaybackControls; the player module holds the
// engine and the tiles.
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import ReactGridLayout, { noCompactor } from 'react-grid-layout';
import type { Layout, LayoutItem } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import { useTranslation } from 'react-i18next';
import { PlaybackControls } from './PlaybackControls';
import type { PlaybackSettings } from './SyncedVideoPlayer';
import { electronTakeFiles, openTake, Tile } from '@/player/index.ts';
import type { PlayerState, TakePlayer, TileUpdate } from '@/player/index.ts';

interface CanvasTakePlayerProps {
    folderPath: string;
    /** null = auto tiling, number = manual column count */
    manualColumns: number | null;
    /** Increment to reset the layout */
    resetKey: number;
    initialFrame?: number;
    onFrameChange?: (frame: number) => void;
}

const GRID_COLS = 12;
const GRID_MARGIN: [number, number] = [2, 2];

/** F1: the column count with the largest tile area, with a smallest tile of 80 × 60 pixels. */
function computeTiling(n: number, w: number, h: number) {
    if (n <= 1) return { cols: 1, rows: 1 };
    let bestCols = 1;
    let bestArea = 0;
    for (let cols = 1; cols <= n; cols++) {
        const rows = Math.ceil(n / cols);
        const cellW = (w - GRID_MARGIN[0] * (cols - 1)) / cols;
        const cellH = (h - GRID_MARGIN[1] * (rows - 1)) / rows;
        if (cellW < 80 || cellH < 60) continue;
        if (n * cellW * cellH > bestArea) {
            bestArea = n * cellW * cellH;
            bestCols = cols;
        }
    }
    return { cols: bestCols, rows: Math.ceil(n / bestCols) };
}

export const CanvasTakePlayer: React.FC<CanvasTakePlayerProps> = ({ folderPath, manualColumns, resetKey, initialFrame, onFrameChange }) => {
    const { t } = useTranslation();
    const [player, setPlayer] = useState<TakePlayer | null>(null);
    const [state, setState] = useState<PlayerState | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [drawn, setDrawn] = useState<Set<number>>(new Set());
    const [settings, setSettings] = useState<PlaybackSettings>({ showOverlays: true, timestampFormat: 'timecode' });
    const onFrameChangeRef = useRef(onFrameChange);
    onFrameChangeRef.current = onFrameChange;
    const initialFrameRef = useRef(initialFrame);
    const canvases = useRef(new Map<number, HTMLCanvasElement>());
    const dragRef = useRef<{ wasPlaying: boolean } | null>(null);

    // open the take; close it when the host leaves it
    useEffect(() => {
        let gone = false;
        let opened: TakePlayer | null = null;
        setPlayer(null);
        setState(null);
        setError(null);
        setDrawn(new Set());
        (async () => {
            const files = await electronTakeFiles(folderPath);
            opened = await openTake(files, { initialFrame: initialFrameRef.current });
            if (gone) return void opened.close();
            opened.on('state', e => setState(e.state));
            opened.on('frame', e => onFrameChangeRef.current?.(e.state.frame));
            setState(opened.state);
            setPlayer(opened);
        })().catch(e => !gone && setError(String(e)));
        return () => {
            gone = true;
            void opened?.close();
        };
    }, [folderPath]);

    const cameras = state?.cameras ?? [];
    const cameraKey = cameras.map(c => c.name).join(',');

    // one Tile for each camera; the loading count of F18 counts the first drawn image of each tile
    useEffect(() => {
        if (!player) return;
        const tiles = [...canvases.current].map(([i, canvas]) => {
            const tile = new Tile(canvas);
            const update = tile.update.bind(tile);
            tile.update = async (u: TileUpdate) => {
                const r = await update(u);
                if (r === 'drawn' && u.jpeg) setDrawn(d => (d.has(i) ? d : new Set(d).add(i)));
                return r;
            };
            return { tile, detach: player.attachTile(i, tile) };
        });
        return () => tiles.forEach(({ tile, detach }) => {
            detach();
            tile.close();
        });
    }, [player, cameraKey]);

    useEffect(() => {
        player?.setTileOptions({ showLabel: settings.showOverlays, timeFormat: settings.timestampFormat });
    }, [player, settings]);

    // ---- grid (F1 to F3) ----
    const gridContainerRef = useRef<HTMLDivElement>(null);
    // 0 until measured: the grid mounts at its real size, so its tiles do not animate from a default size
    const [gridWidth, setGridWidth] = useState(0);
    const [gridHeight, setGridHeight] = useState(0);
    // measured before the paint, so the first grid already has the right columns
    useLayoutEffect(() => {
        const el = gridContainerRef.current;
        if (!el) return;
        const measure = () => {
            const rect = el.getBoundingClientRect();
            setGridWidth(rect.width);
            setGridHeight(rect.height);
        };
        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(el);
        return () => observer.disconnect();
    }, [cameras.length > 0]);

    const n = cameras.length;
    const tiling = useMemo(() => {
        if (manualColumns === null) return computeTiling(n, gridWidth, gridHeight);
        const cols = Math.max(1, Math.min(manualColumns, n || 1));
        return { cols, rows: Math.ceil((n || 1) / cols) };
    }, [n, gridWidth, gridHeight, manualColumns]);

    // the auto layout; a drag or a resize changes it until the cameras, the columns or the reset key change
    const autoLayout = useMemo((): LayoutItem[] => {
        const colSpan = Math.floor(GRID_COLS / tiling.cols);
        return cameras.map((c, i) => ({ i: c.name, x: (i % tiling.cols) * colSpan, y: Math.floor(i / tiling.cols), w: colSpan, h: 1, minW: 1, minH: 1 }));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [cameraKey, tiling.cols, resetKey]);
    const [moved, setMoved] = useState<{ base: LayoutItem[]; layout: LayoutItem[] } | null>(null);
    const gridLayout = moved?.base === autoLayout ? moved.layout : autoLayout;
    const setGridLayout = useCallback((layout: LayoutItem[]) => setMoved({ base: autoLayout, layout }), [autoLayout]);

    const beforeDrag = useRef<LayoutItem[]>(gridLayout);
    const handleDragStart = useCallback(() => {
        beforeDrag.current = gridLayout;
    }, [gridLayout]);
    // F2: a drop onto another tile swaps the two; else the tile moves
    const handleDragStop = useCallback((_l: Layout, _old: LayoutItem | null, item: LayoutItem | null) => {
        if (!item) return;
        const pre = beforeDrag.current;
        const dragged = pre.find(l => l.i === item.i);
        if (!dragged) return;
        const target = pre.find(l => l.i !== item.i && item.x < l.x + l.w && item.x + item.w > l.x && item.y < l.y + l.h && item.y + item.h > l.y);
        setGridLayout(pre.map(l => {
            if (target && l.i === item.i) return { ...l, x: target.x, y: target.y };
            if (target && l.i === target.i) return { ...l, x: dragged.x, y: dragged.y };
            if (!target && l.i === item.i) return { ...l, x: Math.max(0, Math.min(item.x, GRID_COLS - item.w)), y: Math.max(0, Math.min(item.y, tiling.rows - item.h)) };
            return l;
        }));
    }, [tiling.rows, setGridLayout]);
    const handleResizeStop = useCallback((l: Layout) => setGridLayout([...l]), [setGridLayout]);
    const rowHeight = Math.max(30, (gridHeight - (tiling.rows - 1) * GRID_MARGIN[1]) / tiling.rows);

    // ---- commands (F9 to F14) ----
    const playPause = useCallback(() => {
        if (!player) return;
        if (player.state.playing) player.pause();
        else player.play();
    }, [player]);
    const frameStep = useCallback((delta: number) => player?.step(delta), [player]);
    const seekToStart = useCallback(() => player?.seekFrame(0), [player]);
    const seekToEnd = useCallback(() => {
        player?.pause();
        player?.seekFrame(player.state.frameCount - 1);
    }, [player]);
    const toggleLoop = useCallback(() => player?.setLoop(!player.state.loop), [player]);
    const seekDrag = useCallback((frame: number) => {
        if (!player) return;
        if (!dragRef.current) {
            dragRef.current = { wasPlaying: player.state.playing };
            player.pause();
        }
        player.seekFrame(frame);
    }, [player]);
    const seekCommit = useCallback((frame: number) => {
        if (!player) return;
        player.seekFrame(frame);
        if (dragRef.current?.wasPlaying) player.play();
        dragRef.current = null;
    }, [player]);

    // ---- keys (F9 to F12, F20) ----
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
            switch (e.key) {
                case ' ': if (e.shiftKey) break; e.preventDefault(); playPause(); break;
                case 'ArrowLeft': e.preventDefault(); frameStep(e.shiftKey ? -10 : -1); break;
                case 'ArrowRight': e.preventDefault(); frameStep(e.shiftKey ? 10 : 1); break;
                case 'Home': e.preventDefault(); seekToStart(); break;
                case 'End': e.preventDefault(); seekToEnd(); break;
                case 'l': case 'L': e.preventDefault(); toggleLoop(); break;
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [playPause, frameStep, seekToStart, seekToEnd, toggleLoop]);

    if (error) return <div className="flex items-center justify-center h-full"><p className="text sm text-gray">{error}</p></div>;
    if (!state) return null;
    if (n === 0) {
        return (
            <div className="flex items-center justify-center h-full">
                <p className="text sm text-gray">{t('noVideosLoaded')}</p>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full w-full gap-1">
            <div ref={gridContainerRef} data-testid="take-grid" className="flex-1 pos-rel overflow-hidden" style={{ backgroundColor: '#0a0a0a', minHeight: 0 }}>
                {gridWidth > 0 && <ReactGridLayout
                    width={gridWidth}
                    layout={gridLayout}
                    gridConfig={{ cols: GRID_COLS, rowHeight, margin: GRID_MARGIN, containerPadding: [0, 0] as [number, number] }}
                    dragConfig={{ enabled: true }}
                    resizeConfig={{ enabled: true }}
                    compactor={noCompactor}
                    onDragStart={handleDragStart}
                    onDragStop={handleDragStop}
                    onResizeStop={handleResizeStop}
                >
                    {cameras.map((c, i) => (
                        <div key={c.name} style={{ position: 'relative', overflow: 'hidden', backgroundColor: '#000', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.15)' }}>
                            <canvas
                                data-camera-label={c.label}
                                ref={el => {
                                    if (el) canvases.current.set(i, el);
                                    else canvases.current.delete(i);
                                }}
                                style={{ width: '100%', height: '100%', display: 'block' }}
                            />
                        </div>
                    ))}
                </ReactGridLayout>}
            </div>

            {drawn.size < n && (
                <div className="text-center p-1" style={{ backgroundColor: 'var(--color-warning)', color: '#fff' }}>
                    <p className="text sm" title={t('loadingVideos', { ready: drawn.size, total: n })}>{drawn.size} / {n}</p>
                </div>
            )}

            <PlaybackControls
                isPlaying={state.playing}
                currentTime={state.time / 1e9}
                duration={state.lastTime / 1e9}
                playbackRate={state.speed}
                currentFrame={state.frame}
                totalFrames={state.frameCount}
                fps={state.nominalFps || 30}
                recordingFps={state.nominalFps}
                settings={settings}
                onSettingsChange={setSettings}
                onPlayPause={playPause}
                onSeekDrag={seekDrag}
                onSeekCommit={seekCommit}
                onFrameStep={frameStep}
                onPlaybackRateChange={rate => player?.setSpeed(rate)}
                onSeekToStart={seekToStart}
                onSeekToEnd={seekToEnd}
                isLooping={state.loop}
                onToggleLoop={toggleLoop}
                hideSyncInfo
            />
        </div>
    );
};

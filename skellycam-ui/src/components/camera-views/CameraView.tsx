import React, { useEffect, useRef, useMemo, memo } from 'react';
import { useServer } from '@/services/server/ServerContextProvider';
import { useAppSelector } from '@/store/hooks';
import { selectIsPaused } from '@/store/slices/cameras/cameras-selectors';
import { Tile } from '@/player/index.ts';

interface CameraViewProps {
    cameraId: string;
    scale?: number;
    maxWidth?: boolean;
}

/**
 * CameraView component - the shared tile of the player for one camera (specs/preview-4b.md 5.4): the tile draws
 * the image and its overlay (label, rate text, state, mark) on the main thread. Wrapped in memo to prevent
 * re-renders when props haven't changed.
 */
export const CameraView: React.FC<CameraViewProps> = memo(({ cameraId, scale, maxWidth }) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const { setTile } = useServer();
    const isPaused = useAppSelector(selectIsPaused);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const tile = new Tile(canvas);
        setTile(cameraId, tile);
        return () => {
            setTile(cameraId, null);
            tile.close();
        };
    }, [cameraId, setTile]);

    const canvasStyle = useMemo((): React.CSSProperties => {
        if (maxWidth) {
            return { width: '100%', height: '100%', objectFit: 'contain' };
        }
        if (scale !== undefined && scale !== 1.0) {
            return { width: `${scale * 100}%`, height: `${scale * 100}%`, objectFit: 'contain' };
        }
        return { width: '100%', height: '100%', objectFit: 'contain' };
    }, [scale, maxWidth]);

    return (
        <div
            style={{
                width: '100%',
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: '#000',
                position: 'relative',
                overflow: 'hidden'
            }}
        >
            <canvas
                ref={canvasRef}
                data-camera-id={cameraId}
                style={canvasStyle}
            />
            {isPaused && (
                <div
                    style={{
                        position: 'absolute',
                        inset: 0,
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: 'rgba(0, 0, 0, 0.45)',
                        gap: 8,
                        pointerEvents: 'none',
                    }}
                >
                    <span
                        className="icon pause-icon"
                        style={{ width: 40, height: 40, opacity: 0.9 }}
                    />
                    <span
                        style={{
                            color: '#fff',
                            fontSize: '13px',
                            fontFamily: 'monospace',
                            letterSpacing: '0.08em',
                            opacity: 0.9,
                        }}
                    >
                        PAUSED
                    </span>
                </div>
            )}
        </div>
    );
}, (prevProps, nextProps) => {
    return prevProps.cameraId === nextProps.cameraId &&
        prevProps.scale === nextProps.scale &&
        prevProps.maxWidth === nextProps.maxWidth;
});

CameraView.displayName = 'CameraView';

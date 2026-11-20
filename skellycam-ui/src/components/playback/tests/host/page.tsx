// The host-view page of the test Electron app: it mounts `CanvasTakePlayer` (specs/player.md section
// 10) with today's controls, and gives the route of L1. The tests call `window.host`.
import ReactDOM from 'react-dom/client';
import '@/index.css';
import '@/i18n/i18n';

interface MountProps {
    initialFrame?: number;
    manualColumns?: number | null;
    resetKey?: number;
}

declare global {
    interface Window {
        host: typeof host;
    }
}

const frames: {frame: number; at: number}[] = [];
let root: ReactDOM.Root | null = null;

const host = {
    productError: () => (window as unknown as {harnessIpc: {productError(): Promise<string | null>}}).harnessIpc.productError(),

    async mount(folderPath: string, props: MountProps = {}): Promise<void> {
        const {CanvasTakePlayer} = await import('../../CanvasTakePlayer');
        root ??= ReactDOM.createRoot(document.getElementById('root')!);
        root.render(
            <CanvasTakePlayer
                folderPath={folderPath}
                manualColumns={props.manualColumns ?? null}
                resetKey={props.resetKey ?? 0}
                initialFrame={props.initialFrame}
                onFrameChange={(frame: number) => void frames.push({frame, at: performance.now()})}
            />,
        );
    },

    frames: () => frames.slice(),

    async route(folderPath: string): Promise<'canvas' | 'video'> {
        const {chooseTakePlayer} = await import('../../take-route');
        return chooseTakePlayer(folderPath);
    },

    unmount(): void {
        root?.unmount();
        root = null;
    },
};

window.host = host;

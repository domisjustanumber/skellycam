// The overlay text of the tile (specs/player.md section 8.4).

export function formatFrame(frame: number, frameDigits: number): string {
    return 'F' + String(frame).padStart(frameDigits, '0');
}

export function formatTime(timeNs: number | null, format: 'seconds' | 'timecode', nominalFps: number): string | null {
    if (timeNs === null) return null;
    if (format === 'seconds') return `${(timeNs / 1e9).toFixed(3)}s`;
    const sign = timeNs < 0 ? '-' : '';
    const ns = Math.abs(timeNs);
    const whole = Math.floor(ns / 1e9);
    const ff = Math.floor(((ns - whole * 1e9) / 1e9) * nominalFps);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${sign}${pad(Math.floor(whole / 3600))}:${pad(Math.floor((whole % 3600) / 60))}:${pad(whole % 60)}:${pad(ff)}`;
}

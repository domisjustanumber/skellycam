// No imports: the node unit test loads this file directly.

/**
 * The size floor of windows-capture.md 22.2 (Q887 to Q889): a size below 640 wide or 360 high is never offered. The
 * server has the same two numbers in `modes.size_at_floor`.
 */
export function sizeAtFloor(width: number, height: number): boolean {
    return width >= 640 && height >= 360;
}

/** 22.2 (Q888): below 1280x720, hand and face tracking are limited by the resolution; the UI shows a note. */
export function trackingLimited(width: number, height: number): boolean {
    return width < 1280 || height < 720;
}

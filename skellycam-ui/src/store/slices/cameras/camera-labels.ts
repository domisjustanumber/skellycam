// No imports: the node unit test loads this file directly.

interface LabelledCamera { id: string; index: number; name: string }

/** The camera label of rows, tiles and error texts: "Camera <n> · <name>" (Q13 of ADR-VYS7). */
export function cameraLabel(camera: LabelledCamera): string {
    return `Camera ${camera.index} · ${camera.name}`;
}

/** Replace each known camera id of a server text by its label, and drop the word "camera(s)" just before it (camera-requests.md 1.8). */
export function labelText(text: string, cameras: LabelledCamera[]): string {
    if (cameras.length === 0) return text;
    const ids = cameras.map(cam => cam.id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
    return text.replace(new RegExp(`\\b(?:[Cc]ameras? )?(${ids})\\b`, 'g'), (_match, id: string) =>
        cameraLabel(cameras.find(cam => cam.id === id)!));
}

/** The USB link chip of a camera row as i18n keys (camera-requests.md 3.5); null while the detection has no usb_link. */
export function linkChip(deviceInfo: { virtual?: boolean; usbLink?: string }): { text: string; tooltip: string } | null {
    if (deviceInfo.virtual) return { text: 'usbLinkVirtual', tooltip: 'usbLinkVirtualTooltip' };
    if (deviceInfo.usbLink === undefined) return null;
    const speed = { 'USB 1': 'usbLink1', 'USB 2': 'usbLink2', 'USB 3': 'usbLink3' }[deviceInfo.usbLink] ?? 'usbLinkUnknown';
    return { text: speed, tooltip: `${speed}Tooltip` };
}

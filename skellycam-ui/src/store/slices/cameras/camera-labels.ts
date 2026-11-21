// No imports: the node unit test loads this file directly.

interface LabelledCamera { id: string; index: number; name: string }

/** The camera label of rows, tiles and error texts: "Camera <n> · <name>" (Q13 of ADR-VYS7). */
export function cameraLabel(camera: LabelledCamera): string {
    return `Camera ${camera.index} · ${camera.name}`;
}

/**
 * Replace each known camera id that "camera", "cameras" or "Camera" leads, or that is in a list such a word starts
 * ("cameras a, b and c", "recording cameras: a, b"), by its label; drop the word, but keep "cameras:" (1.8).
 * An id with no such word stays: ids are short hex texts that also occur in numbers, GUIDs and codes.
 */
export function labelText(text: string, cameras: LabelledCamera[]): string {
    if (cameras.length === 0) return text;
    const id = `(?:${cameras.map(cam => cam.id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})(?!\\w)`;
    const named = new RegExp(`\\b([Cc]ameras?)(:?) (${id}(?:(?:, and |, | and )${id})*)`, 'g');
    const oneId = new RegExp(`(?<!\\w)${id}`, 'g');
    return text.replace(named, (_match, word: string, colon: string, list: string) => {
        const labels = list.replace(oneId, found => cameraLabel(cameras.find(cam => cam.id === found)!));
        return colon ? `${word}: ${labels}` : labels;
    });
}

/** The USB link chip of a camera row as i18n keys (camera-requests.md 3.5); null for a detection with no usb_link. */
export function linkChip(deviceInfo: { virtual?: boolean; usbLink?: string }): { text: string; tooltip: string } | null {
    if (deviceInfo.virtual) return { text: 'usbLinkVirtual', tooltip: 'usbLinkVirtualTooltip' };
    if (deviceInfo.usbLink === undefined) return null;
    const speed = { 'USB 1': 'usbLink1', 'USB 2': 'usbLink2', 'USB 3': 'usbLink3' }[deviceInfo.usbLink] ?? 'usbLinkUnknown';
    return { text: speed, tooltip: `${speed}Tooltip` };
}

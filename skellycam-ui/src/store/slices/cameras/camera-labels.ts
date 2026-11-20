// No imports: the node unit test loads this file directly.

/** Replace each "camera <id>" of a server text by the camera list label, e.g. "Camera 5 (USB Camera)". */
export function withCameraLabels(text: string, cameras: { id: string; index: number; name: string }[]): string {
    return text.replace(/\bcamera (\w+)/g, (match, id: string) => {
        const camera = cameras.find(cam => cam.id === id);
        return camera ? `Camera ${camera.index} (${camera.name})` : match;
    });
}

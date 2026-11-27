// The route of L1 (specs/player.md section 10): a take folder of the new format opens in the canvas
// player, each other folder in the player of today. It runs before any backend video call.
import {electronTakeFiles, isTakeFolder} from '../../player/index.ts';

/** 'not_allowed': the take handler refuses the folder (L7); the user can pick it in the folder dialog. */
export async function routeTake(folderPath: string): Promise<'canvas' | 'video' | 'not_allowed'> {
    let files;
    try {
        files = await electronTakeFiles(folderPath);
    } catch (e) {
        return String(e).includes('folder not allowed') ? 'not_allowed' : 'video';
    }
    try {
        return (await isTakeFolder(files)) ? 'canvas' : 'video';
    } finally {
        await files.close();
    }
}

/** A picked folder path with no trailing separator; a root (`D:\`, `/`) stays a root, so it stays absolute. White
 * space stays: it is part of a folder name. */
export const trimFolder = (folder: string) => folder.replace(/([^:\\/])[\\/]+$/, '$1');

/** The last part of a folder path (player.md 5.10); a root shows as itself. */
export function folderNameOf(folder: string): string {
    const trimmed = trimFolder(folder);
    return trimmed.slice(Math.max(trimmed.lastIndexOf('/'), trimmed.lastIndexOf('\\')) + 1) || trimmed;
}

export async function chooseTakePlayer(folderPath: string): Promise<'canvas' | 'video'> {
    return (await routeTake(folderPath)) === 'canvas' ? 'canvas' : 'video';
}

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

export async function chooseTakePlayer(folderPath: string): Promise<'canvas' | 'video'> {
    return (await routeTake(folderPath)) === 'canvas' ? 'canvas' : 'video';
}

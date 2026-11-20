// The route of L1 (specs/player.md section 10): a take folder of the new format opens in the canvas
// player, each other folder in the player of today. It runs before any backend video call.
import {electronTakeFiles, isTakeFolder} from '@/player/index.ts';

export async function chooseTakePlayer(folderPath: string): Promise<'canvas' | 'video'> {
    let files;
    try {
        files = await electronTakeFiles(folderPath);
    } catch {
        // a folder that the handler does not open stays with the player of today
        return 'video';
    }
    try {
        return (await isTakeFolder(files)) ? 'canvas' : 'video';
    } finally {
        await files.close();
    }
}

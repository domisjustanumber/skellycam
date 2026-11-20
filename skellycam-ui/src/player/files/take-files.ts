// The page-side interface for the bytes of the opened take (specs/player.md section 5.1). Every file
// read of the player goes through it [Y2, L8].
export interface TakeFiles {
    readonly folderName: string;
    readonly entries: {path: string; size: number}[];
    readRange(path: string, start: number, end: number, signal?: AbortSignal): Promise<Uint8Array>;
    readWhole(path: string, maxBytes: number): Promise<Uint8Array>;
    close(): Promise<void>;
}

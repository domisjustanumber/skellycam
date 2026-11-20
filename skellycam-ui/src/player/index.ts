// The public page entry of the player module (specs/player.md section 4.1).
export {openTake} from './clock/clock.ts';
export type {FrameLoop, OpenTakeOptions, PlayerEvent, PlayerState, TakePlayer} from './clock/clock.ts';
export {electronTakeFiles} from './files/electron-take-files.ts';
export type {TakeFiles} from './files/take-files.ts';
export {isTakeFolder} from './reader/take.ts';
export type {CameraState, TakeState} from './reader/take.ts';
export {Tile} from './tile/tile.ts';
export type {CameraStateName, DecodedImage, JpegDecoder, TileLabel, TileMark, TileOptions, TileOverlay, TileTexts, TileUpdate} from './tile/tile.ts';

// electron/main/index.ts
import { app, BrowserWindow, systemPreferences } from 'electron';
import { setupIPC } from './ipc';
import { WindowManager } from './services/window-manager';
import { PythonServer } from './services/python-server';
import { UpdateHandler } from './services/update-handler';
import { LifecycleLogger } from './services/logger';
import { buildApplicationMenu } from './services/menu-builder';
import { installTakeHandler, registerTakeScheme } from '../../src/player/main/take-scheme.ts';
import { setTakeHandler } from './api';
import { SAVING_NOTICE_DELAY_MS, noticeWhileWaiting } from './services/server-messages.ts';
import { showSavingNotice } from './services/server-dialogs';
import path from 'node:path';
// import os from 'node:os'; // Uncomment if needed for platform-specific checks

// Export environment configuration
export const APP_ENVIRONMENT = {
    IS_DEV: process.env.NODE_ENV === 'development',
    VITE_DEV_SERVER_URL: process.env.VITE_DEV_SERVER_URL,
};


// Platform config
// if (os.release().startsWith('6.1')) app.disableHardwareAcceleration();
if (process.platform === 'win32') app.setAppUserModelId(app.getName());

// A quit waits for the exit of the server with no bound (Q925); after 10 s it shows the "saving" box (recorder.md 9.2)
let quitWait: Promise<void> | null = null;
function waitForServerExit(): Promise<void> {
    quitWait ??= noticeWhileWaiting(PythonServer.shutdown(), SAVING_NOTICE_DELAY_MS, showSavingNotice)
        .finally(() => { quitWait = null; });
    return quitWait;
}

// The scheme of the take handler must be registered before `app` is ready (specs/player.md 4.3)
registerTakeScheme();

// Prevent multiple instances
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
    app.quit();
} else {
    app.on('second-instance', () => {
        // Someone tried to run a second instance, focus our window instead
        const windows = BrowserWindow.getAllWindows();
        if (windows.length > 0) {
            const window = windows[0];
            if (window.isMinimized()) window.restore();
            window.focus();
        }
    });

    // App lifecycle
    app.whenReady().then(async () => {
        LifecycleLogger.logProcessInfo();
        console.log('App is ready');

        // Request camera and microphone permissions on macOS up front.
        // AVFoundation triggers the camera dialog itself, but CoreAudio silently
        // returns zeros for mic without an explicit request — so we ask for both here.
        if (process.platform === 'darwin') {
            await systemPreferences.askForMediaAccess('camera');
            await systemPreferences.askForMediaAccess('microphone');
        }

        // The take handler of the player: the recordings folder of the backend; dialog picks last for this run only, and
        // the folders of the player dialog are remembered in recent-take-folders.json (player.md 5.10)
        setTakeHandler(await installTakeHandler({
            recordingsFolder: path.join(app.getPath('home'), 'skellycam_data', 'recordings'),
        }));

        // Setup IPC
        setupIPC();

        // Build the native application menu with shortcuts
        buildApplicationMenu();

        // Create window
        const mainWindow = WindowManager.createMainWindow();

        // Initialize auto-updater (only in production)
        if (!APP_ENVIRONMENT.IS_DEV) {
            UpdateHandler.initialize(mainWindow);
        }

    });

    app.on('window-all-closed', async () => {
        console.log('All windows closed, shutting down...');
        try {
            await waitForServerExit();
            app.quit();
        } catch (error) {
            console.error('Leaving backend running to protect video saves:', error);
        }
    });

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            WindowManager.createMainWindow();
        }
    });

    app.on('before-quit', async (event) => {
        event.preventDefault();
        console.log('App is quitting, cleaning up...');
        UpdateHandler.shutdown();
        try {
            await waitForServerExit();
            app.exit(0);
        } catch (error) {
            console.error('Quit deferred to protect video saves:', error);
        }
    });
}

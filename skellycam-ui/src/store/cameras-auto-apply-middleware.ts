/**
 * When cameras are already connected, changing resolution/exposure/etc. only updated Redux.
 * Settings reach the backend via POST /skellycam/camera/group/apply (``camerasConnectOrUpdate``).
 * Without a second "Apply" click, the preview never reflected manual exposure or RECOMMEND.
 *
 * This listener debounces and dispatches apply whenever the user edits desired config while
 * at least one selected camera is in the ``connected`` state.
 */
import { createListenerMiddleware, isAnyOf } from '@reduxjs/toolkit';

import {
    cameraDesiredConfigUpdated,
    configCopiedToAll,
    camerasGroupFramerateSet,
} from './slices/cameras/cameras-slice';
import { camerasConnectOrUpdate } from './slices/cameras/cameras-thunks';

const APPLY_DEBOUNCE_MS = 450;

let debounceTimer: ReturnType<typeof setTimeout> | null = null;

function hasConnectedSelectedCamera(state: unknown): boolean {
    const s = state as {
        cameras?: {
            cameras?: Array<{ selected?: boolean; connectionStatus?: string }>;
        };
    };
    return Boolean(
        s.cameras?.cameras?.some(
            (c) => c.selected && c.connectionStatus === 'connected',
        ),
    );
}

export const camerasAutoApplyListener = createListenerMiddleware();

camerasAutoApplyListener.startListening({
    matcher: isAnyOf(
        cameraDesiredConfigUpdated,
        configCopiedToAll,
        camerasGroupFramerateSet,
    ),
    effect: (_action, listenerApi) => {
        if (!hasConnectedSelectedCamera(listenerApi.getState())) {
            return;
        }
        if (debounceTimer !== null) {
            clearTimeout(debounceTimer);
        }
        debounceTimer = setTimeout(() => {
            debounceTimer = null;
            void listenerApi.dispatch(camerasConnectOrUpdate());
        }, APPLY_DEBOUNCE_MS);
    },
});

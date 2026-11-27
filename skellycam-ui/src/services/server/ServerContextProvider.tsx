// ServerContextProvider.tsx
import React, { createContext, ReactNode, useContext, useEffect, useRef, useState, useCallback, useMemo } from 'react';

import { ConnectionState, WebSocketConnection } from "@/services/server/server-helpers/websocket-connection";
import { serverUrls } from "@/services";
import {FramerateStore} from "@/services/server/server-helpers/framerate-store";
import {LogStore, LogRecord} from "@/services/server/server-helpers/log-store";
import { PreviewTiles } from "@/services/server/preview/preview-tiles";
import type { OverlayValues } from "@/services/server/preview/preview-tiles";
import { appStateValues, isCaptureTimings, isFramerateUpdate, rateTexts } from "@/services/server/preview/server-messages";
import type { AppStateLike, CameraOverlay } from "@/services/server/preview/server-messages";
import { TileTimings } from '@/player/index.ts';
import type { Tile } from '@/player/index.ts';
import { store } from "@/store/store";
import { serverStateReceived, wsConnectionChanged, serverDisconnected } from "@/store/slices/connection/connection-slice";
import type { AppStateMessage } from "@/store/slices/connection/connection-types";

type TileLike = Pick<Tile, 'update'>;

interface ServerContextValue {
    isConnected: boolean;
    connectionState: ConnectionState;
    connect: () => void;
    disconnect: () => void;
    send: (data: string | object) => void;
    getFramerateStore: () => FramerateStore;
    getLogStore: () => LogStore;
    getPreviewTiles: () => PreviewTiles;
    /** The decode and draw timing of the tiles (capture-timings.md 7): give each tile a handle. */
    getTileTimings: () => TileTimings;
    /** Give the tile of a camera to the preview, or remove it with null (specs/preview-4b.md 5.4). */
    setTile: (cameraId: string, tile: TileLike | null) => void;
    /** The cameras that stream: `checking`, `too_slow`, `ready` or `recording` (5.5) [Q7, Q10]. */
    connectedCameraIds: string[];
    /** One tile for each camera of `app_state`, in the order of the camera list (5.5) [Q5, Q7]. */
    gridCameraIds: string[];
    /** The camera list label of each camera of the grid (5.4). */
    cameraLabels: Record<string, string>;
    updateServerConnection: (host: string, port: number) => void;
    setStreamPaused: (paused: boolean) => void;
}

const ServerContext = createContext<ServerContextValue | null>(null);

function sameIds(a: string[], b: string[]): boolean {
    return a.length === b.length && a.every((id, i) => id === b[i]);
}

// Type guard to check if a message is a log record
function isLogRecord(data: any): data is LogRecord {
    return (
        data &&
        typeof data === 'object' &&
        data.message_type === 'log_record' &&
        typeof data.levelname === 'string' &&
        typeof data.message === 'string'
    );
}

// Type guard for the server's authoritative APP_STATE snapshot
function isAppState(data: any): data is AppStateMessage {
    return (
        data &&
        typeof data === 'object' &&
        data.message_type === 'app_state' &&
        typeof data.server_pid === 'number' &&
        data.state &&
        typeof data.state === 'object'
    );
}

export const ServerContextProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [isConnected, setIsConnected] = useState<boolean>(false);
    const [connectionState, setConnectionState] = useState<ConnectionState>(ConnectionState.DISCONNECTED);
    const [connectedCameraIds, setConnectedCameraIds] = useState<string[]>([]);
    const [gridCameraIds, setGridCameraIds] = useState<string[]>([]);
    const [cameraLabels, setCameraLabels] = useState<Record<string, string>>({});

    const wsConnectionRef = useRef<WebSocketConnection | null>(null);
    const framerateStoreRef = useRef<FramerateStore>(new FramerateStore());
    const logStoreRef = useRef<LogStore>(new LogStore());
    const tileTimingsRef = useRef<TileTimings>(new TileTimings());
    // 5.3 rule 4: one ready message for each draw; onDrawn feeds Displayed (5.8)
    const previewTilesRef = useRef<PreviewTiles>(new PreviewTiles(
        cameraId => void wsConnectionRef.current?.send({message_type: 'camera_ready', camera_id: cameraId}),
        (cameraId, atMs) => framerateStoreRef.current.recordDrawn(cameraId, atMs),
    ));
    // the last overlay values of each camera: a tile that mounts again gets them (5.3 rule 9 drops them)
    const overlaysRef = useRef<Record<string, Partial<OverlayValues>>>({});
    const lastAppStateRef = useRef<AppStateLike | null>(null);
    const frameLoopRef = useRef<number | null>(null);

    useEffect(() => {
        wsConnectionRef.current = new WebSocketConnection({
            url: serverUrls.getWebSocketUrl(),
            reconnectDelay: 1000,
            maxReconnectAttempts: 5,
            heartbeatInterval: 30000
        });
        return () => {
            wsConnectionRef.current?.disconnect();
        };
    }, []);

    useEffect(() => {
        const ws = wsConnectionRef.current;
        if (!ws) return;
        const tiles = previewTilesRef.current;

        const setOverlay = (cameraId: string, values: Partial<OverlayValues>): void => {
            overlaysRef.current[cameraId] = {...overlaysRef.current[cameraId], ...values};
            tiles.setOverlay(cameraId, values);
        };

        // 5.5: the overlay values and the two lists from app_state and the camera list of the store
        const applyAppState = (): void => {
            const message = lastAppStateRef.current;
            if (!message) return;
            const values = appStateValues(message, store.getState().cameras.cameras);
            const labels: Record<string, string> = {};
            for (const [id, overlay] of Object.entries(values.overlays) as [string, CameraOverlay][]) {
                setOverlay(id, {label: overlay.label, cameraState: overlay.cameraState});
                if (overlay.label !== null) labels[id] = overlay.label;
            }
            setGridCameraIds(prev => (sameIds(prev, values.gridCameraIds) ? prev : values.gridCameraIds));
            setConnectedCameraIds(prev => (sameIds(prev, values.connectedCameraIds) ? prev : values.connectedCameraIds));
            setCameraLabels(prev => (JSON.stringify(prev) === JSON.stringify(labels) ? prev : labels));
        };

        // a new camera list (a detection) changes the labels and the order with no new app_state
        let cameraList = store.getState().cameras.cameras;
        const unsubscribe = store.subscribe(() => {
            const next = store.getState().cameras.cameras;
            if (next !== cameraList) {
                cameraList = next;
                applyAppState();
            }
        });

        const handleStateChange = (newState: ConnectionState): void => {
            const connected = newState === ConnectionState.CONNECTED;
            setIsConnected(connected);
            setConnectionState(newState);
            store.dispatch(wsConnectionChanged(connected));
            if (!connected) tiles.clearPending();   // 5.3 rule 10: each close
            if (newState === ConnectionState.DISCONNECTED || newState === ConnectionState.FAILED) {
                lastAppStateRef.current = null;
                overlaysRef.current = {};
                framerateStoreRef.current.clear();
                setConnectedCameraIds([]);
                setGridCameraIds([]);
                setCameraLabels({});
                // Clear all server-derived Redux state so the UI self-heals on
                // reconnect rather than showing the previous server's stale state.
                store.dispatch(serverDisconnected());
            }
        };

        // 5.3 rule 6: the display drives the draws
        const frameLoop = (): void => {
            tiles.tick();
            frameLoopRef.current = requestAnimationFrame(frameLoop);
        };
        frameLoopRef.current = requestAnimationFrame(frameLoop);

        const handleMessage = (event: MessageEvent): void => {
            if (event.data instanceof ArrayBuffer) {
                tiles.receive(event.data);
                return;
            }
            if (typeof event.data !== 'string' || event.data === 'pong') return;
            try {
                const jsonData = JSON.parse(event.data);
                if (isLogRecord(jsonData)) {
                    logStoreRef.current.add(jsonData);
                } else if (isFramerateUpdate(jsonData)) {
                    for (const [id, rateText] of Object.entries(rateTexts(jsonData))) setOverlay(id, {rateText});
                    framerateStoreRef.current.recordFramerateUpdate(jsonData as never);
                } else if (isAppState(jsonData)) {
                    store.dispatch(serverStateReceived(jsonData));
                    lastAppStateRef.current = jsonData as AppStateLike;
                    framerateStoreRef.current.recordAppState(jsonData as AppStateLike);
                    applyAppState();
                } else if (isCaptureTimings(jsonData)) {
                    tileTimingsRef.current.on = jsonData.log_capture_times;   // capture-timings.md 7: the switch
                }
                // other message types are ignored, so that the DevTools console keeps no reference to them
            } catch (error) {
                console.error('Error parsing JSON message:', error);
            }
        };

        ws.on('state-change', handleStateChange);
        ws.on('message', handleMessage);

        // Connection is driven by ServerConnectionStatus via the connect() callback.
        // No auto-connect here — the component's autoConnectWs loop handles it.

        return () => {
            unsubscribe();
            ws.off('state-change', handleStateChange);
            ws.off('message', handleMessage);
            ws.disconnect();
            if (frameLoopRef.current !== null) {
                cancelAnimationFrame(frameLoopRef.current);
                frameLoopRef.current = null;
            }
        };
    }, []);

    const connect = useCallback((): void => {
        wsConnectionRef.current?.connect();
    }, []);

    const disconnect = useCallback((): void => {
        wsConnectionRef.current?.disconnect();
    }, []);

    const send = useCallback((data: string | object): void => {
        wsConnectionRef.current?.send(data);
    }, []);

    const getFramerateStore = useCallback((): FramerateStore => framerateStoreRef.current, []);
    const getLogStore = useCallback((): LogStore => logStoreRef.current, []);
    const getPreviewTiles = useCallback((): PreviewTiles => previewTilesRef.current, []);
    const getTileTimings = useCallback((): TileTimings => tileTimingsRef.current, []);

    const setTile = useCallback((cameraId: string, tile: TileLike | null): void => {
        previewTilesRef.current.setTile(cameraId, tile);
        const overlay = overlaysRef.current[cameraId];
        if (tile && overlay) previewTilesRef.current.setOverlay(cameraId, overlay);
    }, []);

    const setStreamPaused = useCallback((paused: boolean): void => {
        previewTilesRef.current.setPaused(paused);   // 5.3 rule 7: the only pause of the display
    }, []);

    const updateServerConnection = useCallback((host: string, port: number): void => {
        // Update the singleton so HTTP endpoints also update
        serverUrls.setHost(host);
        serverUrls.setPort(port);

        // Update the WebSocket URL and reconnect
        const ws = wsConnectionRef.current;
        if (ws) {
            ws.disconnect();
            ws.updateUrl(serverUrls.getWebSocketUrl());
            // The auto-reconnect loop in ServerConnectionStatus will re-trigger connect()
        }
    }, []);

    const contextValue = useMemo(() => ({
        isConnected,
        connectionState,
        connect,
        disconnect,
        send,
        getFramerateStore,
        getLogStore,
        getPreviewTiles,
        getTileTimings,
        setTile,
        connectedCameraIds,
        gridCameraIds,
        cameraLabels,
        updateServerConnection,
        setStreamPaused,
    }), [isConnected, connectionState, connectedCameraIds, gridCameraIds, cameraLabels, connect, disconnect, send,
        getFramerateStore, getLogStore, getPreviewTiles, getTileTimings, setTile, updateServerConnection, setStreamPaused]);

    return (
        <ServerContext.Provider value={contextValue}>
            {children}
        </ServerContext.Provider>
    );
};

export const useServer = (): ServerContextValue => {
    const context = useContext(ServerContext);
    if (!context) throw new Error('useServer must be used within ServerContextProvider');
    return context;
};

import React, { useEffect, useCallback, useState } from 'react';
import { useAppDispatch, useAppSelector, selectCameras, selectConnectedCameras, selectIsLoading, detectCameras } from '@/store';
import { camerasConnectOrUpdate, pauseUnpauseCameras, closeCameras } from '@/store/slices/cameras/cameras-thunks';
import { savedSettingsCleared } from '@/store/slices/cameras/cameras-slice';
import { selectIsPaused } from '@/store/slices/cameras/cameras-selectors';
import { CameraTreeItem } from './CameraTreeItem';
import { NoCamerasPlaceholder } from './NoCamerasPlaceholder';
import { useServer } from '@/services/server/ServerContextProvider';
import { useTranslation } from 'react-i18next';
import ButtonSm from '@/components/ui-components/ButtonSm';
import IconButton from "@/components/ui-components/IconButton";
import { useRecordingGuard } from '@/components/RecordingGuardProvider';
import { pendingCameraChanges } from '@/store/slices/cameras/camera-updates';
import { withCameraLabels } from '@/store/slices/cameras/camera-labels';


export const CameraConfigSidebarPanel: React.FC = () => {
    const [isStoppingCameras, setIsStoppingCameras] = useState(false);
    const [isUpdating, setIsUpdating] = useState(false);
    const [updateError, setUpdateError] = useState<string | null>(null);
    const dispatch = useAppDispatch();
    const { isConnected } = useServer();
    const { t } = useTranslation();
    const { requestGuardedAction } = useRecordingGuard();
    const cameras = useAppSelector(selectCameras);
    const connectedCameras = useAppSelector(selectConnectedCameras);
    const isLoading = useAppSelector(selectIsLoading);
    const isPaused = useAppSelector(selectIsPaused);
    const isRecording = useAppSelector((state) => state.recording.isRecording);

    useEffect(() => {
        if (isConnected && cameras.length === 0) {
            dispatch(detectCameras({ filterVirtual: true }));
        }
    }, [isConnected, cameras.length, dispatch]);

    useEffect(() => {
        if (isStoppingCameras && connectedCameras.length === 0) {
            setIsStoppingCameras(false);
        }
    }, [isStoppingCameras, connectedCameras.length]);

    const handleUpdate = useCallback(() => {
        requestGuardedAction('Stop Recording & Update Camera Config', () => dispatch(camerasConnectOrUpdate()));
    }, [dispatch, requestGuardedAction]);

    const changes = pendingCameraChanges(cameras);
    const hasChanges = Object.values(changes).some(ids => ids.length > 0);

    // Send only the differences (specs/windows-capture.md 8.3): the server keeps each camera that a request does
    // not name, so open unchanged cameras are not closed or reopened. One request removes, restarts and adds;
    // a too_slow camera needs a second one (removed, then added again).
    const handleUpdateCameras = useCallback(() => {
        requestGuardedAction('Stop Recording & Update Cameras', async () => {
            const config = (id: string, use: boolean) =>
                [id, { ...cameras.find(cam => cam.id === id)!.desiredConfig, use_this_camera: use }] as const;
            setUpdateError(null);
            setIsUpdating(true);
            try {
                const response = await dispatch(camerasConnectOrUpdate(Object.fromEntries([
                    ...[...changes.close, ...changes.tooSlow].map(id => config(id, false)),
                    ...[...changes.retry, ...changes.add].map(id => config(id, true)),
                ]))).unwrap();
                if (changes.tooSlow.length > 0) {
                    await dispatch(camerasConnectOrUpdate(Object.fromEntries(changes.tooSlow.map(id => config(id, true))))).unwrap();
                }
                // The server adds to a running group only a camera that was in it before; it leaves out a new one
                // (camera_group.py apply). Then the only way is the full sequence: close all, connect the selected.
                if (changes.add.some(id => !(id in response.camera_configs))) {
                    await dispatch(closeCameras()).unwrap();
                    await dispatch(camerasConnectOrUpdate()).unwrap();
                }
            } catch (error) {
                setUpdateError(withCameraLabels((error as { message?: string })?.message ?? String(error), cameras));
            } finally {
                setIsUpdating(false);
            }
        });
    }, [cameras, changes, dispatch, requestGuardedAction]);

    const handleDetect = useCallback(() => {
        requestGuardedAction('Stop Recording & Detect Cameras', () => dispatch(detectCameras({ filterVirtual: true })));
    }, [dispatch, requestGuardedAction]);

    const handleStop = useCallback(() => {
        requestGuardedAction('Stop Recording & Close Cameras', () => {
            setIsStoppingCameras(true);
            dispatch(closeCameras());
        });
    }, [dispatch, requestGuardedAction]);

    return (
        <div className="camera-config-sidebar-panel flex flex-col flex-1 bg-middark br-2 p-1 min-h-0">
            {/* Header */}
            <div className="camera-group-header flex flex-row flex-wrap items-center gap-1 p-1 pos-rel z-2">
                {/* Row 1 — actions */}
              
               
                    
                     
                                                <p className="flex flex-row text md text-gray">{cameras.length} Cameras</p>
                            {connectedCameras.length > 0 && (
                                <span
                                    className="text md"
                                    style={{ color: 'var(--color-success, #4ade80)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                                >
                                    {/* <span className="icon icon-size-20 streaming-icon" /> */}
                                    {connectedCameras.length} Streaming
                                </span>
                            )}
                    <div className="flex-1" />
                    {/* Buttons: Detect + Connect OR Pause/Stop (when connected) */}
                    <div data-onboarding="connect-cameras" className="button-group flex items-center gap-1 pos-rel">
                           
                           
                        
                     
                     <IconButton
                        icon="scan-icon"
                        onClick={handleDetect}
                        tooltip={true}
                        tooltipText={isRecording ? t('stopRecordingFirst') : "Detect new cameras"}
                        tooltipPosition="pos-bottom"
                        disabled={isRecording}
                    />
                        {connectedCameras.length === 0 ? (
                            <ButtonSm
                              text={isLoading ? 'Connecting...' : 'Connect Cameras'}
                              iconClass={isLoading ? 'loader-icon' : 'stream-icon'}
                              onClick={handleUpdate}
                              textColor = "text-black"
                              className={isLoading ? 'disabled primary' : 'primary'}
                              
                            tooltip={true}
                            tooltipText="Connect to Cameras"
                            tooltipPosition="pos-bottom-right"

                            />
                        ) : (
                            <>
                                {hasChanges && (
                                    <ButtonSm
                                        text={isUpdating ? 'Updating...' : 'Update Cameras'}
                                        iconClass={isUpdating ? 'loader-icon' : 'stream-icon'}
                                        onClick={handleUpdateCameras}
                                        textColor="text-black"
                                        className={isUpdating ? 'disabled primary' : 'primary'}
                                        disabled={isUpdating}
                                        tooltip={true}
                                        tooltipText="Open, close or retry only the changed cameras"
                                        tooltipPosition="pos-bottom-right"
                                    />
                                )}
                                <IconButton
                                    icon={isPaused ? 'play-icon' : 'pause-icon'}
                                    onClick={() => requestGuardedAction('Stop Recording & Pause Cameras', () => dispatch(pauseUnpauseCameras()))}
                                    tooltip={true}
                                    tooltipText={isRecording ? t('stopRecordingFirst') : isPaused ? t('resumeStreaming') : t('pauseStreaming')}
                                    tooltipPosition="pos-bottom-right"
                                    disabled={isRecording}
                                />
                                <IconButton
                                    icon={isStoppingCameras ? 'loader-icon' : 'stopstreaming-icon'}
                                    onClick={handleStop}
                                    tooltip={true}
                                    tooltipText={isRecording ? t('stopRecordingFirst') : t('closeAllCameras')}
                                    tooltipPosition="pos-bottom-right"
                                    disabled={isRecording || isStoppingCameras}
                                />
                            </>
                        )}
                    </div>

            </div>
            {updateError && (
                <p className="text sm text-error p-1" style={{ whiteSpace: 'normal' }}>{updateError}</p>
            )}

            {/* Camera list */}
            <div className="camera-list-container flex flex-col overflow-y z-1 pos-rel">
                {cameras.length === 0 ? (
                    <NoCamerasPlaceholder />
                ) : (
                    cameras
                        .slice()
                        .sort((a, b) => a.index - b.index)
                        .map(camera => (
                            <CameraTreeItem key={camera.id} camera={camera} />
                        ))
                )}
            </div>
        </div>
    );
};

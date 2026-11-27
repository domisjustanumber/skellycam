import React, { useEffect, useCallback, useId, useState } from 'react';
import { useAppDispatch, useAppSelector, selectCameras, selectConnectedCameras, selectIsLoading, detectCameras } from '@/store';
import { camerasConnectOrUpdate, closeCameras, searchExposure } from '@/store/slices/cameras/cameras-thunks';
import { savedSettingsCleared, displayPauseToggled, cameraErrorCleared, frameRateChosen } from '@/store/slices/cameras/cameras-slice';
import { selectError, selectIsPaused } from '@/store/slices/cameras/cameras-selectors';
import { CameraTreeItem } from './CameraTreeItem';
import { NoCamerasPlaceholder } from './NoCamerasPlaceholder';
import { useServer } from '@/services/server/ServerContextProvider';
import { useTranslation } from 'react-i18next';
import ButtonSm from '@/components/ui-components/ButtonSm';
import IconButton from "@/components/ui-components/IconButton";
import { useRecordingGuard } from '@/components/RecordingGuardProvider';
import { pendingCameraChanges, updateRequestConfigs } from '@/store/slices/cameras/camera-updates';
import { labelText } from '@/store/slices/cameras/camera-labels';
import { searchBlocked } from '@/store/slices/cameras/exposure-row';
import { chosenRate, groupRate, rateChoice, rateRequestConfigs } from '@/store/slices/cameras/rate-choice';
import { useStore } from 'react-redux';
import type { RootState } from '@/store/types';
import SegmentedControl from '@/components/ui-components/SegmentedControl';


export const CameraConfigSidebarPanel: React.FC = () => {
    const [isStoppingCameras, setIsStoppingCameras] = useState(false);
    const [isUpdating, setIsUpdating] = useState(false);
    const [isSearching, setIsSearching] = useState(false);
    // The error of each apply (Update Cameras, Connect, the menu, the settings) and of Detect: the store keeps it
    const cameraError = useAppSelector(selectError);
    const dispatch = useAppDispatch();
    const { isConnected, connectedCameraIds } = useServer();
    const { t } = useTranslation();
    const { requestGuardedAction } = useRecordingGuard();
    const cameras = useAppSelector(selectCameras);
    const connectedCameras = useAppSelector(selectConnectedCameras);
    const isLoading = useAppSelector(selectIsLoading);
    const isPaused = useAppSelector(selectIsPaused);
    const isRecording = useAppSelector((state) => state.recording.isRecording);
    const groups = useAppSelector((state) => state.connection.cameraGroups);
    const groupConfigs = Object.assign({}, ...groups.map(group => group.configs));
    // The group buttons show while the server has a camera group, also when each camera of it failed
    const hasGroup = cameras.some(cam => cam.inGroup) || Object.keys(groupConfigs).length > 0;
    // An error line is about the selection it was sent with: a new selection clears it
    const selectionKey = cameras.map(cam => `${cam.id}:${cam.selected}`).join();
    useEffect(() => { dispatch(cameraErrorCleared()); }, [selectionKey, dispatch]);

    useEffect(() => {
        if (isConnected && cameras.length === 0) {
            dispatch(detectCameras({ filterVirtual: true }));
        }
    }, [isConnected, cameras.length, dispatch]);

    useEffect(() => {
        if (isStoppingCameras && !hasGroup) {
            setIsStoppingCameras(false);
        }
    }, [isStoppingCameras, hasGroup]);

    // Connect shows only with no group: it may close all and connect the selected (the empty group of an untick-all)
    const handleUpdate = useCallback(() => {
        requestGuardedAction('Stop Recording & Update Camera Config', () => dispatch(camerasConnectOrUpdate({ kind: 'connect' })));
    }, [dispatch, requestGuardedAction]);

    const changes = pendingCameraChanges(cameras, Object.keys(groupConfigs), groupConfigs);
    const hasChanges = Object.values(changes).some(ids => ids.length > 0);

    // Send only the differences (specs/windows-capture.md 8.3): the server keeps each camera that a request does
    // not name, so open unchanged cameras are not closed or reopened. The thunk runs the close-all fall back.
    // Disabled during a recording (ADR-F2KY), so no recording guard.
    const handleUpdateCameras = async () => {
        setIsUpdating(true);
        try {
            const configs = updateRequestConfigs(cameras, changes, groupConfigs);
            await dispatch(camerasConnectOrUpdate({ configs, kind: 'update-cameras', retry: changes.retry })).unwrap();
        } catch {
            // the store keeps the error; the error line shows it
        } finally {
            setIsUpdating(false);
        }
    };

    // The button "Auto-set exposure (all cameras)" (camera-requests.md 1.2 (c), 1.8): each selected camera that
    // streams searches; disabled during a recording and with no streaming camera.
    const searchDisabledText = isRecording ? t('stopRecordingFirst') : connectedCameras.length === 0 ? t('connectCamerasFirst')
        : searchBlocked(groups) ? t('settingExposure') : undefined;  // 1.5: a camera starts, waits or searches
    const handleSearchExposure = async () => {
        setIsSearching(true);
        try {
            await dispatch(searchExposure()).unwrap();
        } catch {
            // the store keeps the error; the error line shows it
        } finally {
            setIsSearching(false);
        }
    };

    // The one frame rate of the group (camera-requests.md 2.1, 2.5, 2.7, 2.8)
    const rateNote = useAppSelector((state) => state.cameras.rateNote);
    const rateChecking = useAppSelector((state) => state.cameras.rateChecking);
    const rateReasonId = useId();
    const store = useStore<RootState>();
    const rate = chosenRate(cameras);
    const { can60, reasons } = rateChoice(cameras);
    const rateDisabledText = isRecording ? t('stopRecordingFirst') : searchBlocked(groups) ? t('settingExposure') : undefined;
    const rateReason = rateDisabledText ?? (can60 ? undefined : reasons.join(' '));
    const handleRate = async (value: string) => {
        const picked = Number(value);
        if (picked === rate || rateDisabledText || (picked === 60 && !can60)) return;
        const send = connectedCameras.length > 0;  // no camera streams: the next connect sends the choice (2.4)
        dispatch(frameRateChosen({ rate: picked, check: send && picked === 60 }));
        if (!send) return;
        try {
            await dispatch(camerasConnectOrUpdate({ configs: rateRequestConfigs(groupConfigs, picked), kind: 'rate' })).unwrap();
        } catch {
            // the server keeps its rate (read now: a fall back can have come meanwhile); the error line shows why
            const live = Object.assign({}, ...store.getState().connection.cameraGroups.map(group => group.configs));
            dispatch(frameRateChosen({ rate: groupRate(live, rate), check: false }));
        }
    };

    const handleDetect = useCallback(() => {
        requestGuardedAction('Stop Recording & Detect Cameras', () => dispatch(detectCameras({ filterVirtual: true })));
    }, [dispatch, requestGuardedAction]);

    const handleStop = useCallback(() => {
        dispatch(cameraErrorCleared());
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
              
               
                    
                     
                                                <p className="flex flex-row text md text-gray">{t('cameraListCount', { count: cameras.length })}</p>
                            {connectedCameraIds.length > 0 && (  // preview-4b.md 5.6: the cameras that stream [Q10]
                                <span
                                    className="text md"
                                    style={{ color: 'var(--color-success, #4ade80)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                                >
                                    {/* <span className="icon icon-size-20 streaming-icon" /> */}
                                    {t('streamingCount', { count: connectedCameraIds.length })}
                                </span>
                            )}
                    <div className="flex-1" />
                    <span title={rateReason}>
                        <SegmentedControl
                            options={[
                                { label: '30 fps', value: '30', disabled: !!rateDisabledText },
                                { label: '60 fps', value: '60', disabled: !!rateDisabledText || !can60 },
                            ]}
                            value={String(rate)}
                            onChange={handleRate}
                            size="sm"
                            describedBy={rateReason ? rateReasonId : undefined}
                        />
                    </span>
                    {/* Buttons: Detect + Connect OR Pause/Stop (when connected) */}
                    <div data-onboarding="connect-cameras" className="button-group flex items-center gap-1 pos-rel">
                           
                           
                        
                     
                     <IconButton
                        icon="scan-icon"
                        onClick={handleDetect}
                        tooltip={true}
                        tooltipText={isRecording ? t('stopRecordingFirst') : t('detectNewCameras')}
                        tooltipPosition="pos-bottom"
                        disabled={isRecording}
                    />
                        {!hasGroup ? (
                            <ButtonSm
                              text={isLoading ? t('connectingCameras') : t('connectCamerasButton')}
                              iconClass={isLoading ? 'loader-icon' : 'stream-icon'}
                              onClick={handleUpdate}
                              textColor = "text-black"
                              className={isLoading ? 'disabled primary' : 'primary'}
                              
                            tooltip={true}
                            tooltipText={t('connectToCamerasTooltip')}
                            tooltipPosition="pos-bottom-right"

                            />
                        ) : (
                            <>
                                {hasChanges && (
                                    <ButtonSm
                                        text={isUpdating ? t('updatingCameras') : t('updateCameras')}
                                        iconClass={isUpdating ? 'loader-icon' : 'stream-icon'}
                                        onClick={handleUpdateCameras}
                                        textColor="text-black"
                                        className={isUpdating ? 'disabled primary' : 'primary'}
                                        disabled={isUpdating || isRecording}
                                        tooltip={true}
                                        tooltipText={isRecording ? t('stopRecordingFirst') : t('updateCamerasTooltip')}
                                        tooltipPosition="pos-bottom-right"
                                    />
                                )}
                                <ButtonSm
                                    text={isSearching ? t('settingExposure') : t('autoSetExposureAll')}
                                    iconClass={isSearching ? 'loader-icon' : undefined}
                                    onClick={handleSearchExposure}
                                    className={isSearching ? 'disabled' : ''}
                                    disabled={isSearching || searchDisabledText !== undefined}
                                    tooltip={searchDisabledText !== undefined}
                                    tooltipText={searchDisabledText}
                                    tooltipPosition="pos-bottom-right"
                                />
                                <IconButton
                                    icon={isPaused ? 'play-icon' : 'pause-icon'}
                                    onClick={() => dispatch(displayPauseToggled())}
                                    tooltip={true}
                                    tooltipText={isPaused ? t('resumeStreaming') : t('pauseStreaming')}
                                    tooltipPosition="pos-bottom-right"
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
            {(rateChecking || rateNote) && (
                <p className="text sm text-gray p-1" style={{ whiteSpace: 'normal' }}>
                    {rateChecking ? t('checkingSixtyFps') : rateNote}
                </p>
            )}
            {rateReason && (
                <p id={rateReasonId} className="text sm text-gray p-1" style={{ whiteSpace: 'normal' }}>{rateReason}</p>
            )}
            {cameraError && (
                <p role="alert" className="text sm text-error p-1" style={{ whiteSpace: 'normal' }}>{labelText(cameraError, cameras)}</p>
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

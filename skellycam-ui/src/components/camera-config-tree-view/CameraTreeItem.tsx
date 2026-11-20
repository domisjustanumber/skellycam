import React, { useRef, useState } from "react";
import ReactDOM from "react-dom";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { CameraGridSettingsModal } from "@/components/camera-views/CameraGridSettingsModal";
import DesignerCheckbox from "@/components/ui-components/Checkbox";
import { ROTATION_DEGREE_LABELS, RotationValue, useAppDispatch, useAppSelector } from "@/store";
import { cameraSelectionToggled } from "@/store/slices/cameras/cameras-slice";
import { openCameraSettings, closeCameraSettings } from "@/store/slices/ui/ui-slice";
import { Camera } from "@/store/slices/cameras/cameras-types";
import { selectCameras, selectIsLoading } from "@/store/slices/cameras/cameras-selectors";
import { camerasConnectOrUpdate } from "@/store/slices/cameras/cameras-thunks";
import ButtonSm from "@/components/ui-components/ButtonSm";
import { withCameraLabels } from "@/store/slices/cameras/camera-labels";
import { useServer } from "@/services/server";

interface CameraTreeItemProps {
    camera: Camera;
}

const getConfigSummary = (config: any): string[] => {
    const summary: string[] = [];
    if (!config) return summary;
    if (config.resolution?.width && config.resolution?.height) {
        summary.push(`${config.resolution.width}×${config.resolution.height}`);
    }
    if (config.exposure !== undefined && config.exposure_mode === 'MANUAL') {
        summary.push(`E:${config.exposure}`);
    }
    if (config.rotation) summary.push(ROTATION_DEGREE_LABELS[config.rotation as RotationValue]);
    if (config.capture_fourcc) summary.push(config.capture_fourcc);
    return summary.filter(Boolean);
};

export const CameraTreeItem: React.FC<CameraTreeItemProps> = ({ camera }) => {
    const dispatch = useAppDispatch();
    const { t } = useTranslation();
    const { connectedCameraIds } = useServer();
    const [modalPos, setModalPos] = useState<{ top: number; left: number }>({ top: 80, left: 40 });
    const settingsBtnRef = useRef<HTMLButtonElement>(null);
    
    const openCameraSettingsId = useAppSelector(state => state.ui.openCameraSettingsId);
    const settingsOpen = openCameraSettingsId === camera.id;
    const cameras = useAppSelector(selectCameras);
    const isLoading = useAppSelector(selectIsLoading);

    const isStreaming = connectedCameraIds.includes(camera.id);

    const handleToggleSelection = (e: React.ChangeEvent<HTMLInputElement>): void => {
        e.stopPropagation();
        dispatch(cameraSelectionToggled(camera.id));
    };

    // "Apply again" (specs/windows-capture.md 8.3): a request that names only this camera restarts it if it is
    // failed or dead; the server keeps the other cameras as they are. too_slow with the same config is "no
    // effect", so a too_slow camera is first unselected, then selected again, which starts it again.
    const handleRetry = async (): Promise<void> => {
        const config = { ...camera.desiredConfig, use_this_camera: true };
        if (camera.failure === 'too_slow') {
            await dispatch(camerasConnectOrUpdate({ [camera.id]: { ...config, use_this_camera: false } }));
        }
        await dispatch(camerasConnectOrUpdate({ [camera.id]: config }));
    };

    const handleOpenSettings = (e: React.MouseEvent): void => {
        e.stopPropagation();
        if (settingsOpen) {
            // Close if already open
            dispatch(closeCameraSettings());
        } else {
            // Close any other open modal and open this one
            dispatch(openCameraSettings(camera.id));
            if (settingsBtnRef.current) {
                const rect = settingsBtnRef.current.getBoundingClientRect();
                setModalPos({ top: rect.bottom + 8, left: rect.right + 8 });
            }
        }
    };

    const handleModalClose = () => {
        dispatch(closeCameraSettings());
    };

    const configSummary = getConfigSummary(camera.desiredConfig);

    return (
        <div className="camera-item-row br-1 flex flex-col gap-1 m-1"
            style={camera.deviceInfo.virtual ? { opacity: 0.5 } : undefined}
        >
            {/* Row 1 — selection, name, settings */}
            <div className="camera-row-group flex flex-row gap-0 items-center">
                {/* Left group — checkbox */}
                <div className="flex flex-row checkbox-group">
                    <DesignerCheckbox
                        label=""
                        checked={camera.selected}
                        onChange={handleToggleSelection}
                        disabled={camera.deviceInfo.virtual}
                        inputClassName={isStreaming ? "streaming" : ""}
                    />
                </div>

                {/* Right group — camera info and settings */}
                <div
                    className={clsx("camera-settings-button button sm br-1 flex flex-col gap-1 flex-1 cursor-pointer p-1", settingsOpen && "selected-camera-settings")}
                    onClick={handleOpenSettings}
                    onMouseDown={e => e.stopPropagation()}
                    title={t('cameraSettings')}
                >
                    {/* Camera info row */}
                    <div className="flex flex-row items-center gap-1">
                        <p className="text sm text-white text-nowrap" style={{ minWidth: 72 }}>Camera {camera.index}</p>
                        <p className="text sm text-gray text-nowrap" style={{ flex: '0 1 auto', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {camera.name}
                        </p>

                        <div className="flex-1" />

                        <button
                            ref={settingsBtnRef}
                            className={clsx("pos-abs top-50 right-0 button icon-button", settingsOpen && "activated")}
                            onClick={e => {
                                e.stopPropagation();
                                handleOpenSettings(e);
                            }}
                            onMouseDown={e => e.stopPropagation()}
                            title={t('cameraSettings')}
                        >
                            <span className={clsx("icon icon-size-20", settingsOpen ? "close-icon" : "settings-icon")} />
                        </button>
                    </div>

                    {/* Config chips */}
                    {configSummary.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                            {configSummary.map(item => (
                                <span key={item} className="camera-config-chip">{item}</span>
                            ))}
                        </div>
                    )}

                    {camera.deviceInfo.virtual && (
                        <p className="text sm text-gray">Virtual cameras are not supported yet.</p>
                    )}

                    {camera.connectionStatus === 'error' && (
                        <p className="text sm text-warning" style={{ whiteSpace: 'normal', paddingRight: 24 }}>
                            Failed: {camera.failure ? withCameraLabels(camera.failure, cameras) : 'unknown reason'}
                        </p>
                    )}

                    {camera.connectionStatus === 'error' && camera.selected && (
                        <div onClick={e => e.stopPropagation()} onMouseDown={e => e.stopPropagation()}>
                            <ButtonSm text="Retry" onClick={handleRetry} disabled={isLoading} tooltip={true}
                                tooltipText="Start this camera again; the other cameras keep streaming" />
                        </div>
                    )}
                </div>
            </div>

            {settingsOpen && ReactDOM.createPortal(
                <CameraGridSettingsModal
                    camera={camera}
                    initialPos={modalPos}
                    onClose={handleModalClose}
                />,
                document.body
            )}
        </div>
    );
};

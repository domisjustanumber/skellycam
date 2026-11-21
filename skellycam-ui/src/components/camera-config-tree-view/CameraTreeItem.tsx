import React, { useId, useRef, useState } from "react";
import ReactDOM from "react-dom";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { CameraGridSettingsModal } from "@/components/camera-views/CameraGridSettingsModal";
import DesignerCheckbox from "@/components/ui-components/Checkbox";
import { ROTATION_DEGREE_LABELS, RotationValue, useAppDispatch, useAppSelector } from "@/store";
import { cameraSelectionToggled } from "@/store/slices/cameras/cameras-slice";
import { openCameraSettings, closeCameraSettings } from "@/store/slices/ui/ui-slice";
import { Camera } from "@/store/slices/cameras/cameras-types";
import { selectCameras } from "@/store/slices/cameras/cameras-selectors";
import { cameraLabel, labelText, linkChip } from "@/store/slices/cameras/camera-labels";
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
    const rowId = useId();

    const openCameraSettingsId = useAppSelector(state => state.ui.openCameraSettingsId);
    const settingsOpen = openCameraSettingsId === camera.id;
    const cameras = useAppSelector(selectCameras);
    const isRecording = useAppSelector(state => state.recording.isRecording);

    const isStreaming = connectedCameraIds.includes(camera.id);
    const isVirtual = Boolean(camera.deviceInfo.virtual);
    const chip = linkChip(camera.deviceInfo);
    const failed = camera.connectionStatus === 'error';
    const showRetryHint = failed && camera.selected && !isRecording;  // Update Cameras is disabled during a recording

    const handleToggleSelection = (e: React.ChangeEvent<HTMLInputElement>): void => {
        e.stopPropagation();
        dispatch(cameraSelectionToggled(camera.id));
    };

    const handleOpenSettings = (e: React.MouseEvent): void => {
        e.stopPropagation();
        if (isVirtual) return;  // a virtual camera cannot be used, so its settings do not open (G9 of ADR-JK79)
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
        <div className="camera-item-row br-1 flex flex-col gap-1 m-1">
            {/* Row 1 — selection, name, settings */}
            <div className="camera-row-group flex flex-row gap-0 items-center">
                {/* Left group — checkbox (a disabled checkbox greys itself) */}
                <div className="flex flex-row checkbox-group">
                    <DesignerCheckbox
                        label=""
                        checked={camera.selected}
                        onChange={handleToggleSelection}
                        disabled={isVirtual}
                        inputClassName={isStreaming ? "streaming" : ""}
                        inputProps={{
                            "aria-label": t('useThisCamera', { label: cameraLabel(camera) }),
                            "aria-describedby": failed ? `${rowId}-failure${showRetryHint ? ` ${rowId}-hint` : ''}` : undefined,
                        }}
                    />
                </div>

                {/* Right group — camera info and settings; greyed for a virtual camera */}
                <div
                    className={clsx("camera-settings-button button sm br-1 flex flex-col gap-1 flex-1 p-1", !isVirtual && "cursor-pointer", settingsOpen && "selected-camera-settings")}
                    style={isVirtual ? { opacity: 0.5 } : undefined}
                    onClick={handleOpenSettings}
                    onMouseDown={e => e.stopPropagation()}
                    title={isVirtual ? undefined : t('cameraSettings')}
                >
                    {/* Camera info row: the label "Camera <n> · <name>" */}
                    <div className="flex flex-row items-center gap-1">
                        <p className="text sm text-white text-nowrap" style={{ minWidth: 72 }}>Camera {camera.index}</p>
                        <p className="text sm text-gray text-nowrap" style={{ flex: '0 1 auto', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            · {camera.name}
                        </p>
                        {chip && (
                            <span className="camera-config-chip text-nowrap" title={t(chip.tooltip)}>{t(chip.text)}</span>
                        )}

                        <div className="flex-1" />

                        {!isVirtual && (
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
                        )}
                    </div>

                    {/* Config chips */}
                    {configSummary.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                            {configSummary.map(item => (
                                <span key={item} className="camera-config-chip">{item}</span>
                            ))}
                        </div>
                    )}

                    {/* A slow camera is not a failure: it keeps streaming (Q10 of ADR-VYS7, G3 of ADR-JK79) */}
                    {camera.state === 'too_slow' && (
                        <p className="text sm text-warning" style={{ whiteSpace: 'normal', paddingRight: 24 }}>{t('cameraIsSlow')}</p>
                    )}

                    {failed && (
                        <p id={`${rowId}-failure`} role="alert" className="text sm text-warning" style={{ whiteSpace: 'normal', paddingRight: 24 }}>
                            {t('cameraFailed', { reason: camera.failure ? labelText(camera.failure, cameras) : t('unknownReason') })}
                        </p>
                    )}

                    {showRetryHint && (
                        <p id={`${rowId}-hint`} className="text sm text-gray">{t('clickUpdateCamerasToRetry')}</p>
                    )}
                </div>
            </div>

            {settingsOpen && !isVirtual && ReactDOM.createPortal(
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

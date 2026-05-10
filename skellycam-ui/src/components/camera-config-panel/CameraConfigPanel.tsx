import React from "react";
import {
    Box,
    Collapse,
    IconButton,
    Tooltip,
    useTheme,
} from "@mui/material";
import MediationIcon from "@mui/icons-material/Mediation";
import { CameraConfigResolution, ResolutionRow } from "./CameraConfigResolution";
import { CameraConfigExposure } from "./CameraConfigExposure";
import { CameraConfigRotation } from "./CameraConfigRotation";
import { CameraConfigFocus } from './CameraConfigFocus';
import {
    Camera,
    CameraConfig,
    ExposureMode,
    RotationValue,
    cameraMissingFormatForTargetFps,
    deriveFramerateFieldsFromResolutionPick,
    effectiveResolutionTargetFramerate,
    normalizeCaptureFourcc,
} from "@/store/slices/cameras/cameras-types";
import { useAppDispatch, useAppSelector } from "@/store";
import {
    configCopiedToAll,
    selectCamerasDisplayedInUi,
    selectBarAppliedTargetFramerate,
    selectGroupDisplayedFramerate,
    selectHasCameraSelection,
} from '@/store/slices/cameras';
import { useTranslation } from 'react-i18next';

interface CameraConfigPanelProps {
    camera: Camera;
    config: CameraConfig;
    onConfigChange: (newConfig: CameraConfig) => void;
    isExpanded: boolean;
    /** When true, controls are non-interactive (e.g. device not usable / in use elsewhere). */
    disabled?: boolean;
}

export const CameraConfigPanel: React.FC<CameraConfigPanelProps> = ({
    camera,
    config,
    onConfigChange,
    isExpanded,
    disabled = false,
}) => {
    const theme = useTheme();
    const dispatch = useAppDispatch();
    const { t } = useTranslation();
    const allCameras = useAppSelector(selectCamerasDisplayedInUi);
    const groupFpsChoice = useAppSelector(selectGroupDisplayedFramerate);
    const barAppliedTargetFps = useAppSelector(selectBarAppliedTargetFramerate);
    const hasCameraSelection = useAppSelector(selectHasCameraSelection);
    const otherCamerasCount = allCameras.length - 1;
    const fpsTargetUnsupported =
        hasCameraSelection
        && cameraMissingFormatForTargetFps(camera, barAppliedTargetFps);

    const handleChange = <K extends keyof CameraConfig>(
        key: K,
        value: CameraConfig[K]
    ): void => {
        onConfigChange({
            ...config,
            [key]: value,
        });
    };

    const logicalTarget =
        effectiveResolutionTargetFramerate(
            hasCameraSelection ? groupFpsChoice : -1,
            config.framerate,
        );

    const handlePickResolutionRow = (row: ResolutionRow): void => {
        const fp = deriveFramerateFieldsFromResolutionPick(row.fps, logicalTarget);
        onConfigChange({
            ...config,
            resolution: { width: row.width, height: row.height },
            capture_fourcc: normalizeCaptureFourcc(row.fourcc_str),
            framerate: fp.framerate,
            stream_framerate: fp.stream_framerate,
        });
    };

    const handleCopyToAllCameras = (): void => {
        dispatch(configCopiedToAll(config.camera_id));
    };

    const handleRotationChange = (value: RotationValue): void => {
        handleChange("rotation", value);
    };

    const handleExposureModeChange = (mode: ExposureMode): void => {
        handleChange("exposure_mode", mode);
    };

    const handleExposureValueChange = (value: number): void => {
        handleChange("exposure", value);
    };

    return (
        <Collapse in={isExpanded} timeout="auto" unmountOnExit>
            <Box
                sx={{
                    px: 1.5,
                    py: 1,
                    ml: 5,
                    mr: 1,
                    mb: 0.5,
                    borderRadius: 1,
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.paper,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 1,
                    ...(disabled
                        ? { opacity: 0.65, pointerEvents: 'none' as const }
                        : fpsTargetUnsupported
                            ? {
                                opacity: 0.52,
                                pointerEvents: 'none' as const,
                            }
                            : {}),
                }}
            >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
                    <CameraConfigResolution
                        resolution={config.resolution}
                        desiredFramerate={hasCameraSelection ? config.framerate : -1}
                        desiredStreamFramerate={hasCameraSelection ? (config.stream_framerate ?? null) : null}
                        groupFramerateChoice={groupFpsChoice}
                        capture_fourcc={config.capture_fourcc}
                        formats={camera.deviceInfo.availableFormats}
                        disabled={disabled}
                        onPick={(row) => handlePickResolutionRow(row)}
                    />

                    <CameraConfigRotation
                        rotation={config.rotation}
                        onChange={handleRotationChange}
                    />

                    <Box sx={{ flex: 1 }} />

                    <Tooltip
                        title={
                            otherCamerasCount > 0
                                ? `Copy settings to ${otherCamerasCount} other camera${
                                    otherCamerasCount > 1 ? 's' : ''
                                }`
                                : 'No other cameras to copy to'
                        }
                    >
                        <span>
                            <IconButton
                                size="small"
                                onClick={handleCopyToAllCameras}
                                disabled={disabled || otherCamerasCount === 0}
                                aria-label={t('copySettingsToAll')}
                                sx={{
                                    color: theme.palette.primary.contrastText,
                                    border: `1px solid ${theme.palette.divider}`,
                                    '&:hover': {
                                        backgroundColor: theme.palette.primary.dark,
                                        color: theme.palette.primary.contrastText,
                                        borderColor: theme.palette.primary.dark,
                                    },
                                    '&:disabled': {
                                        color: theme.palette.action.disabled,
                                    },
                                }}
                            >
                                <MediationIcon fontSize="small" />
                            </IconButton>
                        </span>
                    </Tooltip>
                </Box>

                <CameraConfigExposure
                    exposureMode={config.exposure_mode}
                    exposure={config.exposure}
                    onExposureModeChange={handleExposureModeChange}
                    onExposureValueChange={handleExposureValueChange}
                />

                <CameraConfigFocus
                    disabled={disabled}
                    autoFocusEnabled={config.auto_focus_enabled}
                    focusValue={config.focus}
                    camera={camera}
                    onChange={(upd) =>
                        onConfigChange({ ...config, ...upd })
                    }
                />
            </Box>
        </Collapse>
    );
};

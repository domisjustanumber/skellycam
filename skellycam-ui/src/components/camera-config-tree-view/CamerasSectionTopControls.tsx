import React from 'react';
import {
    Alert,
    Box,
    Button,
    Checkbox,
    FormControl,
    FormControlLabel,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    Typography,
    useTheme,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import {
    suppressListedVirtualCamerasSet,
    dismissHardwareCameraEnumerationHint,
    camerasGroupFramerateSet,
} from '@/store/slices/cameras/cameras-slice';
import { detectCameras } from '@/store/slices/cameras/cameras-thunks';
import {
    DEFAULT_UI_FRAMERATE,
    fpsValuesEquivalent,
} from '@/store/slices/cameras/cameras-types';
import {
    selectIntersectingFpsOptions,
    selectGroupDisplayedFramerate,
    selectHardwareEnumerationChanged,
    selectCameraCount,
    selectSelectedCameras,
} from '@/store/slices/cameras/cameras-selectors';
import { useAppDispatch, useAppSelector } from '@/store';

/** FPS bar sentinel when nothing is selected (-1 mirrors ``selectGroupDisplayedFramerate`` “mixed/auto”). */
const BAR_FPS_AUTO = -1;

export const CamerasSectionTopControls: React.FC = () => {
    const theme = useTheme();
    const { t } = useTranslation();
    const dispatch = useAppDispatch();
    const fpsChoices = useAppSelector(selectIntersectingFpsOptions);
    const cameraCount = useAppSelector(selectCameraCount);
    const hasCameraSelection = useAppSelector(selectSelectedCameras).length > 0;
    const suppressVirtual = useAppSelector((state) => state.cameras.suppressListedVirtualCameras);
    const deviceChangeHint = useAppSelector(selectHardwareEnumerationChanged);
    const groupFpsDisplay = useAppSelector(selectGroupDisplayedFramerate);

    const handleFpsPick = (v: number): void => {
        dispatch(camerasGroupFramerateSet(v));
    };

    /** With ≥1 usable selected camera — intersect lists only valid fps for that selection. */
    const hasIntersectingRates = fpsChoices.length > 0;

    /** Nothing selected → bar stays on Auto without blocking camera checkbox selection elsewhere. */
    const fpsBarAutoMode = !hasCameraSelection;

    /** Representative value when selection exists — always an element of `fpsChoices`. */
    const representativeMatchingGroup = fpsChoices.find((fps) =>
        fpsValuesEquivalent(fps, groupFpsDisplay),
    );
    const representativeWhenMixed =
        fpsChoices.find((fps) => fpsValuesEquivalent(fps, DEFAULT_UI_FRAMERATE))
        ?? fpsChoices[0];

    const intersectSelectValue =
        hasIntersectingRates
            ? (representativeMatchingGroup ?? representativeWhenMixed)!
            : ('' as const);

    const fpsSelectDisabled =
        cameraCount === 0 || (hasCameraSelection && !hasIntersectingRates);

    const fpsSelectValue: number | '' = fpsBarAutoMode ? BAR_FPS_AUTO : intersectSelectValue;

    const formatFpsLabel = (fps: number): string =>
        `${fps.toFixed(Math.abs(fps - Math.round(fps)) < 0.01 ? 0 : 2)} fps`;

    function formatIntersectFpsLabel(fps: number): string {
        return fpsValuesEquivalent(fps, DEFAULT_UI_FRAMERATE)
            ? `${fps.toFixed(Math.abs(fps - Math.round(fps)) < 0.01 ? 0 : 2)}fps (default)`
            : formatFpsLabel(fps);
    }

    const displayFpsDropdownValue = (value: number | ''): string => {
        if (value === BAR_FPS_AUTO) {
            return t('auto');
        }
        if (value === '') {
            return '';
        }
        return formatIntersectFpsLabel(value);
    };

    return (
        <Box
            sx={{
                px: 2,
                py: 1.25,
                bgcolor: theme.palette.background.default,
                borderBottom: `1px solid ${theme.palette.divider}`,
            }}
        >
            {deviceChangeHint && (
                <Alert
                    severity="info"
                    sx={{ mb: 1.25 }}
                    action={
                        <Button
                            color="inherit"
                            size="small"
                            onClick={() => dispatch(dismissHardwareCameraEnumerationHint())}
                        >
                            Dismiss
                        </Button>
                    }
                >
                    USB or built-in webcam devices may have changed — click refresh in the toolbar to rescan.
                </Alert>
            )}

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
                <Typography variant="body2" sx={{ minWidth: 140, fontWeight: 600 }}>
                    Cameras
                </Typography>

                <FormControl size="small" sx={{ minWidth: 168 }}>
                    <InputLabel>{t('framerateLabel', 'Frame rate')}</InputLabel>
                    <Select<number | ''>
                        label={t('framerateLabel', 'Frame rate')}
                        displayEmpty={fpsBarAutoMode ? false : !hasIntersectingRates}
                        value={fpsSelectValue}
                        disabled={fpsSelectDisabled}
                        onChange={(e) => handleFpsPick(Number(e.target.value))}
                        renderValue={(value) => displayFpsDropdownValue(value as number | '')}
                    >
                        {fpsBarAutoMode ? (
                            <MenuItem value={BAR_FPS_AUTO}>{t('auto')}</MenuItem>
                        ) : !hasIntersectingRates ? (
                            <MenuItem value="" disabled>
                                —
                            </MenuItem>
                        ) : (
                            fpsChoices.map((fps) => (
                                <MenuItem key={`fps_${fps}`} value={fps}>
                                    {formatIntersectFpsLabel(fps)}
                                </MenuItem>
                            ))
                        )}
                    </Select>
                </FormControl>

                <FormControlLabel
                    control={
                        <Checkbox
                            checked={suppressVirtual}
                            size="small"
                            onChange={(e) => {
                                const ignoreVirtual = e.target.checked;
                                dispatch(suppressListedVirtualCamerasSet(ignoreVirtual));
                                if (!ignoreVirtual) {
                                    void dispatch(detectCameras());
                                }
                            }}
                        />
                    }
                    label="Ignore virtual webcams"
                    sx={{ alignItems: 'center', ml: { sm: 'auto !important' } }}
                />
            </Stack>
        </Box>
    );
};

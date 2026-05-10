import React from 'react';
import { Box, Checkbox, FormControlLabel, Slider, Tooltip, Typography, useTheme } from '@mui/material';
import { Camera } from '@/store/slices/cameras/cameras-types';

interface CameraConfigFocusProps {
    disabled?: boolean;
    autoFocusEnabled: boolean;
    focusValue: number;
    camera: Camera;
    onChange: (updates: { auto_focus_enabled?: boolean; focus?: number }) => void;
}

export const CameraConfigFocus: React.FC<CameraConfigFocusProps> = ({
    disabled,
    autoFocusEnabled,
    focusValue,
    camera,
    onChange,
}) => {
    const theme = useTheme();
    const supported = !!(camera.deviceInfo.supportsFocusManual && camera.deviceInfo.focusMax != null
        && camera.deviceInfo.focusMin != null);

    const min = camera.deviceInfo.focusMin ?? 0;
    const max = camera.deviceInfo.focusMax ?? 100;

    let sliderVal = focusValue >= 0 ? focusValue : (camera.deviceInfo.focusDefault ?? min);
    if (sliderVal < min || sliderVal > max) {
        sliderVal = Math.min(max, Math.max(min, sliderVal));
    }

    const focusControlsDisabled = disabled || autoFocusEnabled;

    return (
        <Box
            sx={{
                pt: 0.75,
                borderTop: `1px solid ${theme.palette.divider}`,
                opacity: supported ? 1 : 0.55,
                pointerEvents: supported ? 'auto' : 'none',
            }}
        >
            <Typography variant="caption" sx={{ display: 'block', mb: 0.75, color: theme.palette.text.secondary }}>
                Focus
            </Typography>
            <Tooltip
                title={
                    supported
                        ? 'Autofocus is turned off whenever a camera is opened; enable it here if you need continuous AF.'
                        : 'This camera does not expose manual focus controls through the capture driver.'
                }
            >
                <span>
                    <FormControlLabel
                        control={
                            <Checkbox
                                size="small"
                                checked={autoFocusEnabled}
                                disabled={!supported || disabled || !camera.deviceInfo.focusAutoSupported}
                                onChange={(e) => onChange({ auto_focus_enabled: e.target.checked })}
                            />
                        }
                        label="Autofocus"
                    />
                </span>
            </Tooltip>

            {!supported ? null : (
                <Box sx={{ px: 0.75, pb: 0.75 }}>
                    <Typography variant="caption" color="text.secondary">
                        Manual focus
                    </Typography>
                    <Slider
                        disabled={focusControlsDisabled}
                        size="small"
                        min={min}
                        max={max}
                        value={sliderVal}
                        valueLabelDisplay="auto"
                        onChange={(_, v) => typeof v === 'number' && onChange({ focus: v })}
                    />
                </Box>
            )}
        </Box>
    );
};

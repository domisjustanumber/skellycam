import React from 'react';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import { Box, FormControl, InputLabel, Tooltip, useTheme } from '@mui/material';
import {ROTATION_DEGREE_LABELS, ROTATION_OPTIONS, RotationValue} from '@/store/slices/cameras/cameras-types';
import { useTranslation } from 'react-i18next';

interface CameraConfigRotationProps {
    rotation?: RotationValue;
    onChange: (rotation: RotationValue) => void;
}

export const CameraConfigRotation: React.FC<CameraConfigRotationProps> = ({
    rotation = -1,
    onChange,
}) => {
    const theme = useTheme();
    const { t } = useTranslation();

    const handleChange = (
        event: React.MouseEvent<HTMLElement>,
        newRotation: RotationValue | null,
    ): void => {
        if (newRotation !== null) {
            onChange(newRotation);
        }
    };

    return (
        <Box sx={{ minWidth: 220 }}>
            <FormControl variant="standard" sx={{ width: '100%' }}>
                <InputLabel
                    sx={{
                        position: 'static',
                        transform: 'none',
                        mb: 0.25,
                        color: theme.palette.text.primary,
                        fontSize: '0.75rem',
                        lineHeight: 1.4,
                        fontWeight: theme.typography.fontWeightRegular,
                    }}
                >
                    Rotation
                </InputLabel>
                <Tooltip title={t('selectCameraRotation')}>
                    <ToggleButtonGroup
                        color={theme.palette.primary.main as any}
                        value={rotation}
                        size="small"
                        exclusive
                        onChange={handleChange}
                        aria-label={t('cameraRotation')}
                        sx={{
                            mt: 0.5,
                            '& .MuiToggleButton-root.Mui-selected': {
                                backgroundColor: theme.palette.primary.dark,
                                color: theme.palette.primary.contrastText,
                                border: `1px solid ${theme.palette.text.secondary}`,
                                '&:hover': {
                                    backgroundColor: theme.palette.primary.light,
                                },
                            },
                        }}
                    >
                        {ROTATION_OPTIONS.map((option: RotationValue) => (
                            <ToggleButton key={option} value={option}>
                                {ROTATION_DEGREE_LABELS[option]}
                            </ToggleButton>
                        ))}
                    </ToggleButtonGroup>
                </Tooltip>
            </FormControl>
        </Box>
    );
};

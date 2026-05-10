import React, { useEffect, useMemo, useRef } from "react";
import { Box, FormControl, InputLabel, MenuItem, Select, useTheme } from "@mui/material";
import {
    CameraConfig,
    Camera,
    compareDeviceFormatsResolutionPreference,
    effectiveResolutionTargetFramerate,
    fpsValuesEquivalent,
    normalizeCaptureFourcc,
    pickBestFormatAtTargetFps,
} from "@/store/slices/cameras/cameras-types";

export interface ResolutionRow {
    key: string;
    width: number;
    height: number;
    fps: number;
    fourcc_str: string;
    format_id: number;
}

function rowComparable(r: ResolutionRow): {
    format_id: number;
    width: number;
    height: number;
    fps: number;
    fourcc_str: string;
    bpp: number;
} {
    return {
        format_id: r.format_id,
        width: r.width,
        height: r.height,
        fps: r.fps,
        fourcc_str: r.fourcc_str,
        bpp: 24,
    };
}

function rowFromDeviceFormat(
    f: NonNullable<Camera["deviceInfo"]["availableFormats"]>[number],
): ResolutionRow {
    const fourcc_str = f.fourcc_str.trim();
    return {
        key: `${f.format_id}_${f.width}x${f.height}@${f.fps}_${fourcc_str}`,
        width: f.width,
        height: f.height,
        fps: f.fps,
        fourcc_str,
        format_id: f.format_id,
    };
}

function buildResolutionRows(formats: NonNullable<Camera["deviceInfo"]["availableFormats"]>): ResolutionRow[] {
    const out: ResolutionRow[] = [];
    const seen = new Set<string>();
    for (const f of formats) {
        const key = `${f.format_id}_${f.width}x${f.height}@${f.fps}_${f.fourcc_str}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({
            key,
            width: f.width,
            height: f.height,
            fps: f.fps,
            fourcc_str: f.fourcc_str.trim(),
            format_id: f.format_id,
        });
    }
    out.sort((a, b) => compareDeviceFormatsResolutionPreference(rowComparable(a), rowComparable(b)));
    return out;
}

interface CameraConfigResolutionProps {
    resolution: CameraConfig["resolution"];
    /** Shared FPS when all selected cameras agree (often from top-bar); negative or omitted means “unset / mixed”. */
    groupFramerateChoice: number;
    /** This camera’s desired FPS (fallback when group shows mixed or −1). */
    desiredFramerate: number;
    capture_fourcc: string;
    formats: Camera["deviceInfo"]["availableFormats"] | undefined;
    disabled?: boolean;
    onPick: (row: ResolutionRow) => void;
}

export const CameraConfigResolution: React.FC<CameraConfigResolutionProps> = ({
    resolution,
    groupFramerateChoice,
    desiredFramerate,
    capture_fourcc,
    formats,
    disabled,
    onPick,
}) => {
    const theme = useTheme();

    const rows = useMemo(
        () => (formats?.length ? buildResolutionRows(formats) : []),
        [formats],
    );

    const targetFps = useMemo(
        () => effectiveResolutionTargetFramerate(groupFramerateChoice, desiredFramerate),
        [groupFramerateChoice, desiredFramerate],
    );

    const selectableRows = useMemo(() => {
        if (targetFps === null) {
            return rows;
        }
        return rows.filter((r) => fpsValuesEquivalent(r.fps, targetFps));
    }, [rows, targetFps]);

    const idealRow = useMemo(() => {
        if (!formats?.length || targetFps === null || selectableRows.length === 0) {
            return null;
        }
        const best = pickBestFormatAtTargetFps(formats, targetFps);
        return best ? rowFromDeviceFormat(best) : null;
    }, [formats, targetFps, selectableRows.length]);

    const onPickRef = useRef(onPick);
    onPickRef.current = onPick;

    const prevTargetFpsSeen = useRef<number | undefined>(undefined);

    useEffect(() => {
        if (disabled || targetFps === null || idealRow === null || !formats?.length) {
            return;
        }

        const matchesIdeal =
            resolution.width === idealRow.width
            && resolution.height === idealRow.height
            && normalizeCaptureFourcc(capture_fourcc) === normalizeCaptureFourcc(idealRow.fourcc_str)
            && fpsValuesEquivalent(idealRow.fps, targetFps);

        if (matchesIdeal) {
            prevTargetFpsSeen.current = targetFps;
            return;
        }

        const prev = prevTargetFpsSeen.current;
        const bindingFirstNumericTarget = prev === undefined;
        const targetFpsMoved =
            prev !== undefined && !fpsValuesEquivalent(prev, targetFps);

        if (bindingFirstNumericTarget || targetFpsMoved) {
            prevTargetFpsSeen.current = targetFps;
            onPickRef.current(idealRow);
            return;
        }

        prevTargetFpsSeen.current = targetFps;
    }, [
        disabled,
        idealRow,
        idealRow?.key,
        targetFps,
        formats?.length,
        resolution.width,
        resolution.height,
        capture_fourcc,
    ]);

    const currentRowValid = rows.find(
        (r) =>
            r.width === resolution.width
            && r.height === resolution.height
            && normalizeCaptureFourcc(r.fourcc_str) === normalizeCaptureFourcc(capture_fourcc)
            && (targetFps === null || fpsValuesEquivalent(r.fps, targetFps)),
    );

    const noEnumeratedModes = rows.length === 0;
    const noSupportedFormatAtTarget =
        targetFps !== null && rows.length > 0 && selectableRows.length === 0;

    const showPlaceholder = noEnumeratedModes || noSupportedFormatAtTarget;
    /** Parent stream lock disables the FormControl outline + label cascade; unsupported-FPS mute is handled on the Select only so the notch label stays aligned like other selects. */
    const formLocked = Boolean(disabled);
    const selectDisabled = formLocked || showPlaceholder;
    const placeholderFieldText = noEnumeratedModes
        ? 'No enumerated modes reported'
        : 'No supported format';

    const selectValueKey =
        showPlaceholder
            ? ''
            : (targetFps !== null
                    ? (idealRow?.key ?? currentRowValid?.key ?? selectableRows[0]?.key ?? '')
                    : (currentRowValid?.key ?? idealRow?.key ?? selectableRows[0]?.key ?? ''));

    const handleSelect = (event: { target: { value: string } }): void => {
        const row = rows.find((x) => x.key === event.target.value);
        if (!row) {
            return;
        }
        onPick(row);
    };

    return (
        <Box sx={{ minWidth: 230 }}>
            <FormControl fullWidth size="small" disabled={formLocked}>
                <InputLabel sx={{ color: theme.palette.text.primary }}>Resolution</InputLabel>
                <Select<string>
                    disabled={selectDisabled}
                    displayEmpty={showPlaceholder}
                    value={showPlaceholder ? '' : selectValueKey}
                    label="Resolution"
                    onChange={handleSelect}
                    renderValue={(selected) => {
                        if (showPlaceholder) {
                            return placeholderFieldText;
                        }
                        const row = rows.find((x) => x.key === selected);
                        if (!row) {
                            return '';
                        }
                        return `${row.width} × ${row.height} (${row.fourcc_str.trim()}) @ ${row.fps} fps`;
                    }}
                    sx={{ color: theme.palette.text.primary }}
                >
                    {showPlaceholder ? (
                        <MenuItem disabled value="">
                            {placeholderFieldText}
                        </MenuItem>
                    ) : (
                        rows.map((row) => {
                            const fpsMatch =
                                targetFps === null || fpsValuesEquivalent(row.fps, targetFps);
                            const label = `${row.width} × ${row.height} (${row.fourcc_str.trim()}) @ ${row.fps} fps`;
                            return (
                                <MenuItem
                                    key={row.key}
                                    value={row.key}
                                    disabled={!fpsMatch}
                                    sx={!fpsMatch ? { opacity: 0.45 } : {}}
                                >
                                    {label}
                                </MenuItem>
                            );
                        })
                    )}
                </Select>
            </FormControl>
        </Box>
    );
};

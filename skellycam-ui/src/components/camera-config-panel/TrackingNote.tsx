import React from "react";
import { useTranslation } from 'react-i18next';
import { trackingLimited } from "@/store/slices/cameras/resolution-floor";

/**
 * windows-capture.md 22.2 (Q888): below 1280x720, a note under a resolution control tells the user that hand and face
 * tracking will be limited. It does not block the choice. The control points at it with `aria-describedby={id}`.
 */
export const TrackingNote: React.FC<{ id: string; width: number; height: number }> = ({ id, width, height }) => {
    const { t } = useTranslation();
    if (!trackingLimited(width, height)) return null;
    return (
        <p id={id} className="text sm text-gray p-1" style={{ whiteSpace: 'normal' }}>{t('trackingLimitedByResolution')}</p>
    );
};

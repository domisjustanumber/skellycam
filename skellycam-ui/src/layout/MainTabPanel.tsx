import React, { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import SegmentedControl from '@/components/ui-components/SegmentedControl';
import { BaseContentRouter } from '@/layout/BaseContentRouter';
import { useServer } from '@/services/server/ServerContextProvider';
import { useAppSelector } from '@/store';
import { selectIsPaused } from '@/store/slices/cameras/cameras-selectors';

export const MainTabPanel: React.FC = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const { t } = useTranslation();
    const { setStreamPaused } = useServer();
    const isPaused = useAppSelector(selectIsPaused);  // Q495: the pause of the user freezes the display only

    const activeTab = location.pathname.startsWith('/playback')
        ? 'playback'
        : 'cameras';

    useEffect(() => {
        setStreamPaused(activeTab === 'playback' || isPaused);
    }, [activeTab, isPaused, setStreamPaused]);

    return (
        <div className="main-container gap-1 overflow-hidden flex flex-row flex-1 pos-rel">
            <SegmentedControl
                options={[
                    { label: t('cameras'), value: 'cameras' },
                    { label: t('videoPlayback'), value: 'playback' },
                ]}
                value={activeTab}
                onChange={(v) => navigate('/' + v)}
                size="md"
            />
            <div className="mode-container flex-5 br-2 bg-darkgray border-mid-black border-1 overflow-hidden flex flex-col flex-1 gap-1 p-1">
                <BaseContentRouter />
            </div>
        </div>
    );
};

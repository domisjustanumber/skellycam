// src/components/framerate-viewer/FrameRateViewer.tsx
// The frame rate viewer (specs/preview-4b.md 5.8): two series for each camera, "Captured" and "Displayed", with
// one colour for each camera in the order of the camera list; the Captured line is solid, the Displayed line dashed.
import {useEffect, useRef, useState} from "react"
import clsx from "clsx"
import FramerateTimeseriesView from "./FramerateTimeseriesView"
import FramerateHistogramView from "./FramerateHistogramView"
import FramerateStatisticsView from "./FramerateStatisticsView"
import { useTranslation } from "react-i18next"
import { useServer } from "@/services/server/ServerContextProvider"
import { DISPLAYED_DASH, SERIES, SERIES_KEY, useViewerCameras } from "./viewer-cameras"
import type { ViewerCamera } from "./viewer-cameras"

const COLLAPSED_POLL_MS = 500;
const fpsText = (fps: number | null | undefined) => (fps != null ? fps.toFixed(1) : "--")

const FramerateCollapsedView = () => {
    const { t } = useTranslation()
    const { getFramerateStore } = useServer()
    const cameras = useViewerCameras()
    const refs = useRef<Record<string, HTMLSpanElement | null>>({})

    useEffect(() => {
        const tick = () => {
            for (const camera of cameras) {
                const values = getFramerateStore().getCamera(camera.id)
                const captured = refs.current[`${camera.id}-captured`]
                const displayed = refs.current[`${camera.id}-displayed`]
                if (captured) captured.textContent = fpsText(values?.captured.current?.mean_frames_per_second)
                if (displayed) displayed.textContent = fpsText(values?.displayed.current?.mean_frames_per_second)
            }
        }
        tick()
        const id = setInterval(tick, COLLAPSED_POLL_MS)
        return () => clearInterval(id)
    }, [getFramerateStore, cameras])

    return (
        <div className="framerate-collapsed-summary flex items-center h-full gap-2">
            <p className="text bg text-gray">{t("cameraPerformanceMetrics")}</p>
            {cameras.map(camera => (
                <p key={camera.id} className="text sm text-gray" style={{color: camera.colour}}>
                    {camera.label}: {t("capturedFramerate")} <span ref={el => { refs.current[`${camera.id}-captured`] = el }}>--</span> fps,{" "}
                    {t("displayedFramerate")} <span ref={el => { refs.current[`${camera.id}-displayed`] = el }}>--</span> fps
                </p>
            ))}
        </div>
    )
}

/** The legend of the timeline and the histogram: one colour for each camera, and the line of each series. */
const FramerateLegend = ({cameras}: {cameras: ViewerCamera[]}) => {
    const { t } = useTranslation()
    const line = (colour: string, dash: string | undefined) => (
        <svg width="18" height="6" aria-hidden="true">
            <line x1="0" y1="3" x2="18" y2="3" stroke={colour} strokeWidth="2" strokeDasharray={dash}/>
        </svg>
    )
    return (
        <div className="framerate-legend flex flex-row gap-2 text sm text-gray">
            {cameras.map(camera => (
                <span key={camera.id} className="flex items-center gap-1">
                    {line(camera.colour, undefined)}{camera.label}: {t("capturedFramerate")}
                    {line(camera.colour, DISPLAYED_DASH)}{t("displayedFramerate")}
                </span>
            ))}
        </div>
    )
}

export const FramerateViewerPanel = ({ isCollapsed = false }: { isCollapsed?: boolean }) => {
    const { t } = useTranslation()
    const cameras = useViewerCameras()
    const [showStats, setShowStats] = useState(true)
    const [showTimeseries, setShowTimeseries] = useState(true)
    const [showHistogram, setShowHistogram] = useState(true)

    if (isCollapsed) return <FramerateCollapsedView />

    return (
        <div className="framerate-viewer br-1">
            {/* Header */}
            <div className="framerate-viewer-header">
                <p className="text bg text-gray">{t('cameraPerformanceMetrics')}</p>
                <div className="flex gap-1">
                    <button
                        className={clsx("button sm br-1", showStats && "activated")}
                        onClick={() => setShowStats(v => !v)}
                        title={t("statisticsView")}
                    >
                        <p className="text sm">Stats</p>
                    </button>
                    <button
                        className={clsx("button sm br-1", showTimeseries && "activated")}
                        onClick={() => setShowTimeseries(v => !v)}
                        title={t("timelineView")}
                    >
                        <p className="text sm">Timeline</p>
                    </button>
                    <button
                        className={clsx("button sm br-1", showHistogram && "activated")}
                        onClick={() => setShowHistogram(v => !v)}
                        title={t("distributionView")}
                    >
                        <p className="text sm">Distribution</p>
                    </button>
                </div>
            </div>

            {/* Stats table */}
            {showStats && (
                <div className="framerate-stats-wrapper br-1 border-1 border-black p-1">
                    <FramerateStatisticsView cameras={cameras} />
                </div>
            )}

            {(showTimeseries || showHistogram) && <FramerateLegend cameras={cameras}/>}

            {/* Chart area: the timeline, and one histogram panel for each series */}
            <div className={clsx("framerate-charts-area", showTimeseries && showHistogram ? "row" : "column")}>
                {showTimeseries && (
                    <div className="framerate-chart-panel border-1 border-black br-1">
                        <FramerateTimeseriesView cameras={cameras} title={t("framerateTimeline")}/>
                    </div>
                )}
                {showHistogram && SERIES.map(series => (
                    <div key={series} className="framerate-chart-panel border-1 border-black br-1">
                        <FramerateHistogramView cameras={cameras} series={series}
                                                title={`${t("framerateDistribution")}: ${t(SERIES_KEY[series])}`}/>
                    </div>
                ))}
            </div>
        </div>
    )
}

export default FramerateViewerPanel

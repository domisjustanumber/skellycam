// src/components/framerate-viewer/FramerateStatisticsView.tsx
import React, {useEffect, useRef} from "react";
import {DetailedFramerate} from "@/services/server/server-helpers/framerate-store";
import {SERIES, SERIES_KEY} from "./viewer-cameras";
import type {Series, ViewerCamera} from "./viewer-cameras";
import {useTranslation} from "react-i18next";
import {useServer} from "@/services/server/ServerContextProvider";

const STATS_POLL_INTERVAL_MS = 500;

type FramerateStatisticsViewProps = {
    cameras: ViewerCamera[];   // the cameras of the grid, in the order of the camera list
};

const formatNumber = (num: number | null, precision = 3): string => {
    return num !== null ? num.toFixed(precision) : "N/A";
};

const METRIC_KEYS = ["recent", "mean", "median", "stdDev", "max", "min"] as const;
type MetricKey = typeof METRIC_KEYS[number];
// the four counts of 5.8, in the Captured row; never added [A7]
const COUNT_KEYS = ["notShown", "ringSkipped", "oversize", "replaced"] as const;

// CSS class suffix per metric key (stdDev → stddev for valid class names)
const metricClass = (metric: MetricKey) => metric === "stdDev" ? "stddev" : metric;

function computeCellValues(
    currentData: DetailedFramerate | null,
    aggregateData: DetailedFramerate | null,
): Record<MetricKey, {primary: string; secondary: string}> & {samples: string} {
    const safeFps = (durationMs: number | null | undefined): number | null =>
        durationMs !== null && durationMs !== undefined && durationMs > 0 ? 1000 / durationMs : null;

    return {
        recent: {
            primary: formatNumber(currentData?.mean_frames_per_second ?? null) + " fps",
            secondary: formatNumber(currentData?.mean_frame_duration_ms ?? null) + " ms",
        },
        mean: {
            primary: formatNumber(safeFps(aggregateData?.frame_duration_mean)) + " fps",
            secondary: formatNumber(aggregateData?.frame_duration_mean ?? null) + " ms",
        },
        median: {
            primary: formatNumber(safeFps(aggregateData?.frame_duration_median)) + " fps",
            secondary: formatNumber(aggregateData?.frame_duration_median ?? null) + " ms",
        },
        stdDev: {
            primary: formatNumber(aggregateData?.frame_duration_stddev ?? null) + " ms",
            secondary: formatNumber(aggregateData ? aggregateData.frame_duration_coefficient_of_variation * 100 : null) + " CV%",
        },
        max: {
            primary: formatNumber(safeFps(aggregateData?.frame_duration_min)) + " fps",
            secondary: formatNumber(aggregateData?.frame_duration_min ?? null) + " ms",
        },
        min: {
            primary: formatNumber(safeFps(aggregateData?.frame_duration_max)) + " fps",
            secondary: formatNumber(aggregateData?.frame_duration_max ?? null) + " ms",
        },
        samples: String(aggregateData?.calculation_window_size || 0),
    };
}

export default function FramerateStatisticsView({cameras}: FramerateStatisticsViewProps) {
    const {t} = useTranslation();
    const {getFramerateStore} = useServer();

    const spanRefs = useRef<Record<string, HTMLSpanElement | null>>({});
    const setSpanRef = (key: string) => (el: HTMLSpanElement | null) => {
        spanRefs.current[key] = el;
    };

    useEffect(() => {
        const tick = () => {
            const store = getFramerateStore();
            for (const camera of cameras) {
                const values = store.getCamera(camera.id);
                for (const series of SERIES) {
                    const key = `${camera.id}-${series}`;
                    const vals = computeCellValues(values?.[series].current ?? null, values?.[series].aggregate ?? null);
                    for (const metric of METRIC_KEYS) {
                        const pEl = spanRefs.current[`${key}-${metric}-primary`];
                        if (pEl) pEl.textContent = vals[metric].primary;
                        const sEl = spanRefs.current[`${key}-${metric}-secondary`];
                        if (sEl) sEl.textContent = vals[metric].secondary;
                    }
                    const samplesEl = spanRefs.current[`${key}-samples`];
                    if (samplesEl) samplesEl.textContent = `${vals.samples} ${t("samples")}`;
                }
                for (const count of COUNT_KEYS) {
                    const el = spanRefs.current[`${camera.id}-${count}`];
                    if (el) el.textContent = values ? String(values[count]) : "--";
                }
            }
        };
        tick();
        const id = setInterval(tick, STATS_POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [getFramerateStore, cameras, t]);

    const tooltips = {
        recent: {short: t("statsCurrentShort"), long: t("statsCurrentLong")},
        mean: {short: t("statsMeanShort"), long: t("statsMeanLong")},
        median: {short: t("statsMedianShort"), long: t("statsMedianLong")},
        stdDev: {short: t("statsStdDevShort"), long: t("statsStdDevLong")},
        max: {short: t("statsMaxShort"), long: t("statsMaxLong")},
        min: {short: t("statsMinShort"), long: t("statsMinLong")},
    };

    const renderTooltip = (text: string, position: string = "pos-bottom") => (
        <div className={`tooltip-container elevated-sharp ${position} p-01 br-2 bg-dark stats-tooltip`}>
            <div className="tooltip-inner br-1 pl-2 pr-2 pt-1 pb-1 border-1 border-mid-black border-solid">
                <span className="text-xs">{text}</span>
            </div>
        </div>
    );

    const renderMetricCell = (key: string, metric: MetricKey) => (
        <td key={metric} className={`stats-td stats-col-${metricClass(metric)}`}>
            <div className={`stats-cell-primary stats-cell-${metricClass(metric)}-text`}>
                <span ref={setSpanRef(`${key}-${metric}-primary`)}>--</span>
            </div>
            <div className={`stats-cell-secondary stats-cell-${metricClass(metric)}-text`}>
                <span ref={setSpanRef(`${key}-${metric}-secondary`)}>--</span>
            </div>
        </td>
    );

    const renderRow = (camera: ViewerCamera, series: Series) => {
        const key = `${camera.id}-${series}`;
        return (
            <tr key={key}>
                <td className={`stats-td stats-source-cell stats-source-${series}`} style={{color: camera.colour}}>
                    {camera.label} {t(SERIES_KEY[series])}
                    <div className="stats-source-samples">
                        <span ref={setSpanRef(`${key}-samples`)}>--</span>
                    </div>
                    {renderTooltip(t(`${SERIES_KEY[series]}Tooltip`), "pos-bottom-left")}
                </td>
                {METRIC_KEYS.map((metric) => renderMetricCell(key, metric))}
                {COUNT_KEYS.map((count) => (
                    <td key={count} className="stats-td">
                        <div className="stats-cell-primary">
                            {series === "captured" ? <span ref={setSpanRef(`${camera.id}-${count}`)}>--</span> : null}
                        </div>
                    </td>
                ))}
            </tr>
        );
    };

    const columns = 1 + METRIC_KEYS.length + COUNT_KEYS.length;
    return (
        <div className="stats-table-wrapper">
            <table className="stats-table">
                <thead>
                    <tr>
                        <th className="stats-th stats-th-source">
                            {t("source")}
                            {renderTooltip(t("framerateSourceTooltip"), "pos-bottom-left")}
                        </th>
                        {METRIC_KEYS.map((metric) => (
                            <th key={metric}
                                className={`stats-th stats-col-${metricClass(metric)}`}>
                                {t(metric === "stdDev" ? "stdDevCv" : metric === "recent" ? "Recent" : metric)}
                                {renderTooltip(`${tooltips[metric].short} ${tooltips[metric].long}`, (metric === "recent") ? "pos-bottom-left" : (metric === "stdDev" || metric === "max" || metric === "min") ? "pos-bottom-right" : "pos-bottom")}
                            </th>
                        ))}
                        {COUNT_KEYS.map((count) => (
                            <th key={count} className="stats-th">
                                {t(`${count}Count`)}
                                {renderTooltip(t(`${count}CountTooltip`), "pos-bottom-right")}
                            </th>
                        ))}
                    </tr>
                    <tr className="stats-divider"><td colSpan={columns} /></tr>
                </thead>
                <tbody>
                    {cameras.map((camera) => (
                        <React.Fragment key={camera.id}>
                            {SERIES.map((series) => renderRow(camera, series))}
                            <tr className="stats-divider"><td colSpan={columns} /></tr>
                        </React.Fragment>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

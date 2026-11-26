// src/components/framerate-viewer/FramerateTimeseriesView.tsx
// The timeline of the frame rate viewer (specs/preview-4b.md 5.8): for each camera, a solid Captured line and a
// dashed Displayed line in the colour of the camera.
import {useCallback, useRef} from "react"
import * as d3 from "d3"
import {applyAxisStyles, DISABLED_TEXT_COLOR} from "@/components/framerate-viewer/d3ChartUtils"
import BaseD3ChartView, {ChartScaffolding, ChartLifecycle} from "@/components/framerate-viewer/BaseD3ChartView"
import {useTranslation} from "react-i18next"
import {useServer} from "@/services/server/ServerContextProvider"
import {DISPLAYED_DASH, SERIES} from "./viewer-cameras"
import type {Series, ViewerCamera} from "./viewer-cameras"

type FramerateTimeseriesProps = {
    cameras: ViewerCamera[]
    title?: string
}

type FpsSample = { timestamp: number; value: number }
type Line = { key: string; cameraId: string; series: Series; colour: string; data: FpsSample[] }

/** How many seconds of data the rolling window shows. */
const WINDOW_SECONDS = 60

/** Fixed relative-time tick positions (seconds ago). These never change,
 *  so D3's axis join always matches existing tick elements — zero DOM churn. */
const RELATIVE_TICK_SECONDS = [0, -15, -30, -45, -60]

type ChartState = {
    xScale: d3.ScaleLinear<number, number>
    yScale: d3.ScaleLinear<number, number>
}

const AXIS_LABEL_COLOR = "var(--color-text-muted)"

export default function FramerateTimeseriesView({cameras, title = "Framerate Over Time"}: FramerateTimeseriesProps) {
    const {t} = useTranslation()
    const stateRef = useRef<ChartState | null>(null)
    const camerasRef = useRef(cameras)
    camerasRef.current = cameras
    const {getFramerateStore} = useServer()

    // initChart — creates persistent SVG elements that live for the chart's lifetime
    const initChart = useCallback(
        ({svg, chartArea, xAxisG, yAxisG, width, height}: ChartScaffolding): ChartLifecycle => {
            // X-axis uses relative seconds (0 = now, -60 = oldest).
            const xScale = d3.scaleLinear().domain([-WINDOW_SECONDS, 0]).range([0, width])
            const yScale = d3.scaleLinear().range([height, 0])

            xAxisG.call(d3.axisBottom(xScale).tickValues(RELATIVE_TICK_SECONDS).tickSize(-height)
                .tickFormat((d) => ((d as number) === 0 ? "now" : `${d as number}s`)))
            yAxisG.call(d3.axisLeft(yScale).ticks(Math.max(2, Math.min(5, Math.floor(height / 30)))).tickSize(-width))
            applyAxisStyles(chartArea)

            svg.append("text")
                .attr("class", "x-axis-label")
                .attr("x", width / 2)
                .attr("y", height + 32)
                .attr("text-anchor", "middle")
                .style("font-family", "monospace")
                .style("font-size", "10px")
                .style("fill", AXIS_LABEL_COLOR)
                .text("Time")

            svg.append("text")
                .attr("class", "y-axis-label")
                .attr("transform", "rotate(-90)")
                .attr("x", -height / 2)
                .attr("y", -28)
                .attr("text-anchor", "middle")
                .style("font-family", "monospace")
                .style("font-size", "10px")
                .style("fill", AXIS_LABEL_COLOR)
                .text("FPS")

            chartArea.append("text")
                .attr("class", "empty-text")
                .attr("x", width / 2)
                .attr("y", height / 2)
                .attr("text-anchor", "middle")
                .attr("dominant-baseline", "central")
                .style("font-family", "monospace")
                .style("font-size", "12px")
                .style("fill", DISABLED_TEXT_COLOR)
                .style("display", "none")

            stateRef.current = {xScale, yScale}
            return {cleanup: () => { stateRef.current = null }}
        },
        []
    )

    // updateChart — one path for each camera and series, joined by key
    const updateChart = useCallback(
        ({svg, chartArea, yAxisG, width, height}: ChartScaffolding) => {
            const state = stateRef.current
            if (!state) return
            const store = getFramerateStore()
            const lines: Line[] = camerasRef.current.flatMap(camera => SERIES.map(series => ({
                key: `${camera.id}|${series}`, cameraId: camera.id, series, colour: camera.colour,
                data: store.recentDurations(camera.id, series)
                    .filter(s => s.value > 0)
                    .map(s => ({timestamp: s.timestamp, value: 1000 / s.value})),
            })))

            let windowEnd = -Infinity
            for (const line of lines) for (const d of line.data) if (d.timestamp > windowEnd) windowEnd = d.timestamp
            const windowStart = windowEnd - WINDOW_SECONDS * 1000
            for (const line of lines) line.data = line.data.filter(d => d.timestamp >= windowStart)

            let yMin = Infinity
            let yMax = -Infinity
            for (const line of lines) {
                for (const d of line.data) {
                    if (d.value < yMin) yMin = d.value
                    if (d.value > yMax) yMax = d.value
                }
            }
            const empty = yMax === -Infinity
            svg.select<SVGTextElement>(".empty-text").style("display", empty ? "" : "none").text(t("waitingForData"))
            if (!empty) {
                const yPadding = Math.max(1, (yMax - yMin) * 0.3)
                state.yScale.domain([Math.max(0, yMin - yPadding), yMax + yPadding])
                yAxisG.call(d3.axisLeft(state.yScale).ticks(Math.max(2, Math.min(5, Math.floor(height / 30)))).tickSize(-width))
                applyAxisStyles(svg)
            }

            const lineGen = d3
                .line<FpsSample>()
                .x((d) => state.xScale((d.timestamp - windowEnd) / 1000))
                .y((d) => state.yScale(d.value))
                .curve(d3.curveLinear)

            chartArea.selectAll<SVGPathElement, Line>("path.series")
                .data(lines, d => d.key)
                .join("path")
                .attr("class", "series")
                .attr("data-camera-id", d => d.cameraId)
                .attr("data-series", d => d.series)
                .attr("fill", "none")
                .attr("stroke", d => d.colour)
                .attr("stroke-width", 1.5)
                .attr("stroke-dasharray", d => (d.series === "displayed" ? DISPLAYED_DASH : null))
                .attr("d", d => (d.data.length > 0 ? lineGen(d.data) : null))
        },
        [getFramerateStore, t]
    )

    return <BaseD3ChartView title={title} initChart={initChart} updateChart={updateChart}
                            margin={{top: 20, right: 10, bottom: 42, left: 40}}/>
}

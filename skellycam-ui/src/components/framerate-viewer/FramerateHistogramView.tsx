// src/components/framerate-viewer/FramerateHistogramView.tsx
// One histogram panel of the frame rate viewer: the bars of one series, one colour for each camera (5.8).
import {useCallback, useRef} from "react"
import * as d3 from "d3"
import {applyAxisStyles, DISABLED_TEXT_COLOR} from "./d3ChartUtils"
import BaseD3ChartView, {ChartScaffolding, ChartLifecycle} from "@/components/framerate-viewer/BaseD3ChartView"
import {useTranslation} from "react-i18next"
import {useServer} from "@/services/server/ServerContextProvider"
import type {Series, ViewerCamera} from "./viewer-cameras"

type FramerateHistogramProps = {
    cameras: ViewerCamera[]
    series: Series   // one panel for each series (specs/preview-4b.md 5.8)
    title?: string
}

type HistogramBin = {x0: number; x1: number; count: number; density: number}

/**
 * Build histogram bins with a domain tight to the actual data range.
 */
function buildHistogram(fpsValues: number[]): {
    bins: HistogramBin[]
    maxDensity: number
} | null {
    if (fpsValues.length === 0) return null

    const min = Math.floor(d3.min(fpsValues)!)
    const max = Math.ceil(d3.max(fpsValues)!)

    const range = max - min
    const binWidth = range > 40 ? Math.ceil(range / 30) : 1
    const thresholds: number[] = []
    for (let v = min; v <= max; v += binWidth) {
        thresholds.push(v)
    }

    const generator = d3
        .bin<number, number>()
        .domain([min, max + binWidth])
        .thresholds(thresholds)

    const rawBins = generator(fpsValues)
    const total = fpsValues.length
    let maxDensity = 0

    const bins = rawBins.map((b) => {
        const density = b.length / total
        if (density > maxDensity) maxDensity = density
        return {
            x0: b.x0 as number,
            x1: b.x1 as number,
            count: b.length,
            density,
        }
    })

    return {bins, maxDensity}
}

type CameraBins = {cameraId: string; colour: string; bins: HistogramBin[]}

type ChartState = {
    xScale: d3.ScaleLinear<number, number>
    yScale: d3.ScaleLinear<number, number>
}

const PAPER_COLOR = "var(--color-text-muted)"

export default function FramerateHistogramView({cameras, series, title = "Framerate Distribution"}: FramerateHistogramProps) {
    const {t} = useTranslation()
    const stateRef = useRef<ChartState | null>(null)
    const camerasRef = useRef(cameras)
    camerasRef.current = cameras
    const {getFramerateStore} = useServer()

    const initChart = useCallback(
        ({svg, chartArea, width, height}: ChartScaffolding): ChartLifecycle => {
            const xScale = d3.scaleLinear().range([0, width])
            const yScale = d3.scaleLinear().range([height, 0])

            svg.append("text")
                .attr("class", "x-axis-label")
                .attr("x", width / 2)
                .attr("y", height + 32)
                .attr("text-anchor", "middle")
                .style("font-family", "monospace")
                .style("font-size", "10px")
                .style("fill", "var(--color-text-muted)")
                .text("FPS")

            svg.append("text")
                .attr("class", "y-axis-label")
                .attr("transform", "rotate(-90)")
                .attr("x", -height / 2)
                .attr("y", -28)
                .attr("text-anchor", "middle")
                .style("font-family", "monospace")
                .style("font-size", "10px")
                .style("fill", "var(--color-text-muted)")
                .text("Density")

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

    // updateChart — one group of bars for each camera, joined by camera id
    const updateChart = useCallback(
        ({svg, chartArea, xAxisG, yAxisG, width, height}: ChartScaffolding) => {
            const state = stateRef.current
            if (!state) return
            const store = getFramerateStore()
            const groups: CameraBins[] = []
            let minX = Infinity
            let maxX = -Infinity
            let maxDensity = 0
            for (const camera of camerasRef.current) {
                const fps = store.recentDurations(camera.id, series).filter(s => s.value > 0).map(s => 1000 / s.value)
                const hist = buildHistogram(fps)
                groups.push({cameraId: camera.id, colour: camera.colour, bins: hist?.bins ?? []})
                if (hist && hist.bins.length > 0) {
                    minX = Math.min(minX, hist.bins[0].x0)
                    maxX = Math.max(maxX, hist.bins[hist.bins.length - 1].x1)
                    maxDensity = Math.max(maxDensity, hist.maxDensity)
                }
            }
            const empty = minX === Infinity
            chartArea.select<SVGTextElement>(".empty-text").style("display", empty ? "" : "none").text(t("waitingForData"))
            if (empty) {
                minX = 0
                maxX = 60
            }
            if (maxDensity === 0) maxDensity = 1
            const xPad = Math.max(1, (maxX - minX) * 0.05)
            state.xScale.domain([minX - xPad, maxX + xPad])
            state.yScale.domain([0, maxDensity * 1.15])

            // The domain shifts as the bins change: remove the old ticks before the redraw.
            xAxisG.selectAll("*").remove()
            xAxisG.call(d3.axisBottom(state.xScale).ticks(Math.max(2, Math.min(8, Math.floor(width / 50)))).tickSize(-height))
            yAxisG.selectAll("*").remove()
            yAxisG.call(d3.axisLeft(state.yScale).ticks(Math.max(2, Math.min(5, Math.floor(height / 30)))).tickSize(-width))
            applyAxisStyles(svg)

            const inset = groups.length > 1 ? 1 : 0
            chartArea.selectAll<SVGGElement, CameraBins>("g.camera-bars")
                .data(groups, d => d.cameraId)
                .join("g")
                .attr("class", "camera-bars")
                .each(function (group, index) {
                    d3.select(this).selectAll<SVGRectElement, HistogramBin>("rect")
                        .data(group.bins, d => `${d.x0}-${d.x1}`)
                        .join("rect")
                        .attr("data-camera-id", group.cameraId)
                        .attr("data-series", series)
                        .attr("fill", group.colour)
                        .attr("stroke", PAPER_COLOR)
                        .attr("stroke-width", 0.5)
                        .attr("opacity", 0.7)
                        .attr("x", d => state.xScale(d.x0) + index * inset)
                        .attr("width", d => Math.max(1, state.xScale(d.x1) - state.xScale(d.x0) - inset))
                        .attr("y", d => {
                            const y = state.yScale(d.density)
                            return isNaN(y) ? height : Math.min(height, Math.max(0, y))
                        })
                        .attr("height", d => {
                            const y = state.yScale(d.density)
                            return isNaN(y) ? 0 : Math.max(0, height - Math.min(height, Math.max(0, y)))
                        })
                })
        },
        [getFramerateStore, series, t]
    )

    return <BaseD3ChartView title={title} initChart={initChart} updateChart={updateChart}
                            margin={{top: 20, right: 10, bottom: 42, left: 40}} />
}

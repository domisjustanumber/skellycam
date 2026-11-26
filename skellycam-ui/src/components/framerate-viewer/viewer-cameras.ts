// The series and the cameras of the frame rate viewer (specs/preview-4b.md 5.8).
import {useMemo} from "react"
import * as d3 from "d3"
import {useServer} from "@/services/server/ServerContextProvider"

export type Series = "captured" | "displayed"
export const SERIES: readonly Series[] = ["captured", "displayed"]
export const SERIES_KEY: Record<Series, string> = {captured: "capturedFramerate", displayed: "displayedFramerate"}
export const DISPLAYED_DASH = "4 3"   // the Captured line is solid; the Displayed line is dashed

export interface ViewerCamera {
    id: string
    label: string
    colour: string
}

/** The cameras of the grid, in the order of the camera list, each with its label and one colour [Q3]. */
export function useViewerCameras(): ViewerCamera[] {
    const {gridCameraIds, cameraLabels} = useServer()
    return useMemo(() => gridCameraIds.map((id, i) => ({
        id, label: cameraLabels[id] ?? id, colour: d3.schemeTableau10[i % d3.schemeTableau10.length],
    })), [gridCameraIds, cameraLabels])
}

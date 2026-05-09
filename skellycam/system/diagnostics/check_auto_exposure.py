"""Interactive exposure sweep using openpnp-capture (UI via OpenCV windows)."""

from __future__ import annotations

import platform
from typing import Union

import cv2
import numpy as np

from skellycam.core.camera.openpnp_capture import OpenPnPCamera, OpenPnPCaptureAPIError, OpenPnPProperty

MIN_EXPOSURE = -9
MAX_EXPOSURE = -5
DEFAULT_EXPOSURE = -6

EXPOSURE_SETTINGS: list[Union[int, str]] = [DEFAULT_EXPOSURE, "AUTO"]
EXPOSURE_SETTINGS.extend(list(range(MIN_EXPOSURE, MAX_EXPOSURE + 1)))


def run_frame_loop(
    camera: OpenPnPCamera,
    exposure_setting: int | str,
    auto_manual_label: str,
    frames: int = 10,
) -> dict[str, float]:
    brightness_values: list[float] = []
    r = np.random.randint(0, 99999)
    buf = np.zeros((camera.format.height, camera.format.width, 3), dtype=np.uint8)
    actual_exp = camera.get_settings().exposure
    for fr in range(frames):
        if not camera.capture_frame_into(buf):
            print("Failed to capture frame, breaking frame loop")
            break
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        color = (255, 0, 255)
        thickness = 2
        position = (10, 30)
        position2 = (10, 60)

        annotated_image = buf.copy()
        cv2.rectangle(annotated_image, (0, 0), (300, 80), (255, 255, 255), -1)
        cv2.putText(
            annotated_image,
            f"(Fr#{fr}) {auto_manual_label}, Set: {exposure_setting}, Actual: {actual_exp}",
            position,
            font,
            font_scale,
            color,
            thickness,
        )
        cv2.putText(
            annotated_image,
            f"np.mean(image)={np.mean(buf):.2f}",
            position2,
            font,
            font_scale,
            color,
            thickness,
        )

        cv2.imshow(f"{r} Brightness Calibration (q to quit)", annotated_image)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        brightness_values.append(float(np.mean(buf)))
    cv2.destroyAllWindows()
    arr = np.asarray(brightness_values)
    return {"mean": float(np.mean(arr)), "median": float(np.median(arr)), "std": float(np.std(arr))}


def main() -> None:
    devices = OpenPnPCamera.list_devices()
    if not devices:
        print("No cameras found.")
        return
    dev = devices[0]
    fmt = dev.formats[0] if dev.formats else None
    if fmt is None:
        print("No formats for camera 0.")
        return

    camera = OpenPnPCamera(0, fmt.format_id, format_info=fmt, device_formats=dev.formats)
    camera.open()
    print(f"Platform: {platform.system()} — openpnp library {OpenPnPCamera.library_version()}")
    print(f"Exposure on init: {camera.get_settings().exposure}")

    try:
        if camera.supports_property(OpenPnPProperty.EXPOSURE):
            camera.set_exposure(DEFAULT_EXPOSURE)
    except OpenPnPCaptureAPIError as e:
        print(f"Could not set initial exposure: {e}")

    results: list[list] = []
    for exposure_setting in EXPOSURE_SETTINGS:
        if exposure_setting == "AUTO":
            camera.set_auto_exposure(True)
            label = "AUTO exposure"
        else:
            camera.set_auto_exposure(False)
            try:
                camera.set_exposure(int(exposure_setting))
            except OpenPnPCaptureAPIError as e:
                print(f"Skip exposure {exposure_setting}: {e}")
                continue
            label = "MANUAL exposure"

        for _ in range(30):
            buf = np.zeros((camera.format.height, camera.format.width, 3), dtype=np.uint8)
            camera.capture_frame_into(buf)

        exposure_actual = camera.get_settings().exposure
        print(f"Exposure after set to {exposure_setting}: {exposure_actual}")
        brightness_data = run_frame_loop(
            camera=camera,
            exposure_setting=exposure_setting,
            auto_manual_label=label,
        )
        results.append([label, exposure_setting, brightness_data["mean"], brightness_data["median"], brightness_data["std"]])

    headers = ["Mode", "Exposure", "Mean Brightness", "Median", "Std Dev"]
    header_format = "{:<25} {:<15} {:<20} {:<20} {:<20}"
    row_format = "{:<25} {:<15} {:<20.1f} {:<20.1f} {:<20.1f}"
    print(header_format.format(*headers))
    print("-" * 90)
    for row in results:
        print(row_format.format(row[0], str(row[1]), row[2], row[3], row[4]))

    camera.close()


if __name__ == "__main__":
    main()

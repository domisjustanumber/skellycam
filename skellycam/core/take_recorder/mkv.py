"""The PyAV calls of the camera file (specs/recorder.md, section 6.3)."""
import os
from fractions import Fraction

import av

TIME_BASE = Fraction(1, 1000)


class _WholeWrites:
    """The file object that PyAV gets. FFmpeg ignores a write count that is not negative, so a short
    write would leave a hole and wrong offsets: `write` writes every byte or raises."""

    def __init__(self, raw, on_write):
        self._raw, self._on_write = raw, on_write

    def write(self, data) -> int:
        view = memoryview(data)
        while view:
            written = self._raw.write(view)
            if not written:
                raise OSError("the camera file accepted no bytes")
            self._on_write()  # progress (D1): the OS took bytes
            view = view[written:]
        return len(data)

    def __getattr__(self, name):
        return getattr(self._raw, name)


class MkvFile:
    """One Matroska file with one `V_MJPEG` track, written through a file object that it owns."""

    def __init__(self, path, *, num, den, width, height, on_write=lambda: None):
        self.num, self.den = num, den
        # A file object, not a path: the writer needs the descriptor for os.fsync and for tell() [agent 6].
        self.raw = open(path, "xb", buffering=0)
        try:
            # cluster_size_limit=1: one block in each cluster, also for small JPEGs, so that block k is
            # in the file when block k + 1 is muxed [review B1].
            self.container = av.open(_WholeWrites(self.raw, on_write), mode="w", format="matroska",
                                     options={"flush_packets": "1", "cluster_size_limit": "1"})
            self.stream = self.container.add_mux_stream("mjpeg", rate=Fraction(num, den), width=width, height=height)
            self.container.start_encoding()  # the header is in the file before the first block [review S5]
        except BaseException:
            self.raw.close()
            raise

    def mux(self, payload: bytes, k: int) -> None:
        packet = av.Packet(payload)
        packet.stream = self.stream
        packet.time_base = TIME_BASE
        packet.pts = packet.dts = (2 * k * self.den * 1000 + self.num) // (2 * self.num)
        self.container.mux(packet)

    def tell(self) -> int:
        return self.raw.tell()

    def fsync(self) -> None:
        os.fsync(self.raw.fileno())

    def close_container(self) -> None:
        self.container.close()

    def close(self) -> None:
        """Close the container and the file object after an error. The container close can raise
        (PyAVCallbackError after ENOSPC); the file object is closed in each case."""
        try:
            self.container.close()
        except Exception:  # the error that ended the writer is already recorded
            pass
        finally:
            self.raw.close()

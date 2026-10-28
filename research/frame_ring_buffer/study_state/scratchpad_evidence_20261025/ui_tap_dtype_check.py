"""Confirms wire-format sizes/offsets of the SkellyCam frontend payload dtypes match skellycam-ui binary-protocol.ts."""
import sys, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, r"C:\Users\Dom\GitHub\freemocap\skellycam")
from skellycam.core.types.frontend_payload_bytearray import FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE as H, FRONTEND_FRAME_HEADER_DTYPE as F
print("payload header/footer itemsize", H.itemsize, {k: H.fields[k][1] for k in H.names})
print("frame header itemsize", F.itemsize, {k: F.fields[k][1] for k in F.names})

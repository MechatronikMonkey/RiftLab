"""RiftLab - analysis and visualisation of RiftRec sessions.

RiftLab knows RiftRec only through the SQLite session contract
(RiftRec/riftrec/storage/schema.sql) - it imports no RiftRec code. Milestone 4
delivers the demo viewer (EW-31/36): heart rate and HRV over the match timeline
with marked game events.
"""

__version__ = "0.1.0"

# Highest RiftRec schema version this reader understands.
SUPPORTED_SCHEMA_VERSION = 1

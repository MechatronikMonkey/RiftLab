"""RiftLab - analysis and visualisation of RiftRec sessions.

RiftLab knows RiftRec only through the SQLite session contract
(RiftRec/riftrec/storage/schema.sql) - it imports no RiftRec code. Milestone 4
delivers the demo viewer (EW-31/36): heart rate and HRV over the match timeline
with marked game events.
"""

__version__ = "0.1.0"

# Highest RiftRec schema version this reader understands.
#
# 3 (EW-86): RiftRec added `device_info` plus the raw channels `hr_raw` and
#            `game_raw`, and a `contact` column on `hr_sample`. All additive -
#            the tables this reader uses (session, hr_sample, rr_interval,
#            game_event) are unchanged, so v2 and v3 files are read fully and
#            the "display may be incomplete" warning would be misleading.
#            Raise this again only after checking that the tables read here
#            still carry what the reader expects.
SUPPORTED_SCHEMA_VERSION = 3

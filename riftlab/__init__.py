"""RiftLab - Auswertung/Visualisierung von RiftRec-Sessions.

RiftLab kennt RiftRec ausschliesslich ueber den SQLite-Session-Vertrag
(RiftRec/riftrec/storage/schema.sql) - es importiert keinen RiftRec-Code.
Milestone 4 liefert den Demo-Viewer (EW-31/36): HR- und HRV-Verlauf ueber die
Match-Timeline mit markierten Game-Events.
"""

__version__ = "0.1.0"

# Hoechste RiftRec-Schemaversion, die dieser Reader versteht.
SUPPORTED_SCHEMA_VERSION = 1

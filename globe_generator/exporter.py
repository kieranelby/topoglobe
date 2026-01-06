"""3MF export functionality for FreeCAD documents."""

import logging
import os
import sys
from pathlib import Path

# Add FreeCAD to path
freecad_paths = [
    "/snap/freecad/current/usr/lib",
    "/usr/lib/freecad-python3/lib",
    "/usr/lib/freecad/lib",
    "/usr/lib/freecad-daily-python3/lib",
    os.path.expanduser("~/.local/lib/freecad/lib"),
]

for path in freecad_paths:
    if os.path.exists(path) and path not in sys.path:
        sys.path.append(path)

try:
    import FreeCAD as App
    import Mesh
    import MeshPart
    import Part
except ImportError:
    raise ImportError(
        "FreeCAD not found. Install with: sudo apt install freecad python3-freecad"
    )

from .config import SegmentDefinition

logger = logging.getLogger(__name__)


class Exporter:
    """Export FreeCAD documents to 3MF files."""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_segment(
        self,
        doc: App.Document,
        segment: SegmentDefinition
    ) -> Path:
        """
        Export FreeCAD document to 3MF file.

        Args:
            doc: FreeCAD document with geometry
            segment: Segment definition for naming

        Returns:
            Path to exported 3MF file
        """
        output_path = self.output_dir / f"{segment.segment_id}.3mf"

        logger.info(f"Exporting to {output_path}")

        # Get all Part objects from document
        objects = [obj for obj in doc.Objects if hasattr(obj, 'Shape')]

        if not objects:
            logger.warning("No objects to export")
            return output_path

        # Merge all shapes into a single compound
        shapes = [obj.Shape for obj in objects]
        compound = Part.makeCompound(shapes)

        # Mesh the compound
        # LinearDeflection controls mesh resolution (smaller = finer mesh)
        # 0.1 is a good balance between quality and file size
        mesh = MeshPart.meshFromShape(
            Shape=compound,
            LinearDeflection=0.1,
            AngularDeflection=0.523599,  # 30 degrees in radians
            Relative=False
        )

        # Export to 3MF
        mesh.write(str(output_path), "3MF")

        logger.info(f"Exported {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")

        return output_path

"""FreeCAD geometry generation for globe segments."""

import sys
import os
import math
import logging
from typing import Optional

# Add FreeCAD to path if not already available
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
    import Part
except ImportError:
    raise ImportError(
        "FreeCAD not found. Install with: sudo apt install freecad python3-freecad"
    )

import polars as pl
from .config import GlobeConfig, SegmentDefinition


logger = logging.getLogger(__name__)


def make_sphere_patch(r: float, t: float, lat1: float, lat2: float, lon1: float, lon2: float):
    """
    Create a spherical shell patch as a revolved solid.

    Conventions:
      - Latitude 0° at equator, +90° at +Z pole, -90° at -Z pole
      - Latitude band is [lat1, lat2]
      - Longitude is rotation about +Z, 0° along +X, increasing toward +Y

    Args:
        r: Inner radius (mm)
        t: Thickness (mm)
        lat1: Start latitude (degrees)
        lat2: End latitude (degrees)
        lon1: Start longitude (degrees)
        lon2: End longitude (degrees)

    Returns:
        FreeCAD Part solid representing the spherical shell patch
    """
    # Ensure lat1 < lat2
    lat_lo = min(lat1, lat2)
    lat_hi = max(lat1, lat2)

    # Convert latitude (from equator) to polar angle from +Z:
    #   lat = 90° - polar
    # => polar = 90° - lat
    theta_lo = math.radians(90.0 - lat_hi)  # "top" (closer to +Z)
    theta_hi = math.radians(90.0 - lat_lo)  # "bottom" (closer to equator)

    # Radii
    r_outer = float(r) + float(t)
    r_inner = float(r)

    # Convenience function
    def v(x, y, z):
        return App.Vector(x, y, z)

    # Points on outer circle (plane XZ, Y=0)
    mid_theta = 0.5 * (theta_lo + theta_hi)

    po1 = v(r_outer * math.sin(theta_lo), 0.0, r_outer * math.cos(theta_lo))
    po2 = v(r_outer * math.sin(theta_hi), 0.0, r_outer * math.cos(theta_hi))
    pom = v(r_outer * math.sin(mid_theta), 0.0, r_outer * math.cos(mid_theta))

    # Points on inner circle
    pi1 = v(r_inner * math.sin(theta_lo), 0.0, r_inner * math.cos(theta_lo))
    pi2 = v(r_inner * math.sin(theta_hi), 0.0, r_inner * math.cos(theta_hi))
    pim = v(r_inner * math.sin(mid_theta), 0.0, r_inner * math.cos(mid_theta))

    # Arcs (outer from po1 -> po2, inner from pi2 -> pi1 to orient properly)
    outer_arc = Part.Arc(po1, pom, po2).toShape()
    inner_arc = Part.Arc(pi2, pim, pi1).toShape()

    # Radial edges at the two latitudes
    edge1 = Part.LineSegment(po1, pi1).toShape()
    edge2 = Part.LineSegment(pi2, po2).toShape()

    # Wire & face of the 2D profile
    wire = Part.Wire([outer_arc, edge2, inner_arc, edge1])
    face = Part.Face(wire)

    # Revolve around Z to get longitude span
    lon_span = float(lon2 - lon1)
    solid = face.revolve(App.Vector(0, 0, 0), App.Vector(0, 0, 1), lon_span)

    # Rotate so that it starts at lon1
    rot = App.Rotation(App.Vector(0, 0, 1), lon1)
    solid.Placement = App.Placement(App.Vector(0, 0, 0), rot)

    return solid


class GeometryBuilder:
    """Build FreeCAD geometry for globe segments."""

    def __init__(self, config: GlobeConfig):
        self.config = config

    def create_segment_geometry(
        self,
        cells_df: pl.DataFrame,
        segment: SegmentDefinition
    ) -> App.Document:
        """
        Create FreeCAD document with segment geometry.

        Args:
            cells_df: DataFrame with cell data (already filtered for segment)
            segment: Segment definition

        Returns:
            FreeCAD Document with water, land, and snow objects
        """
        logger.info(f"Creating geometry for {segment.segment_id} ({len(cells_df)} cells)")

        # Create new document
        doc_name = f"Globe_{segment.segment_id}"
        doc = App.newDocument(doc_name)

        # Create hollow core for this segment
        core = make_sphere_patch(
            self.config.hollow_radius_mm,
            self.config.core_radius_mm - self.config.hollow_radius_mm,
            segment.lat_min,
            segment.lat_max,
            segment.lon_min,
            segment.lon_max
        )

        # Start with core in water compound
        water_shapes = [core]
        land_shapes = []
        snow_shapes = []

        # Process each cell
        for row in cells_df.iter_rows(named=True):
            water_height_mm = float(row["water_height_mm"])
            lat1 = float(row["lat_a_deg"])
            lat2 = float(row["lat_b_deg"])
            lon1 = float(row["lng_a_deg"])
            lon2 = float(row["lng_b_deg"])

            # Skip cells outside segment bounds
            if lat2 <= segment.lat_min or lat1 >= segment.lat_max:
                continue
            if lon2 <= segment.lon_min or lon1 >= segment.lon_max:
                continue

            if water_height_mm > 0:
                # Create water patch
                wsp = make_sphere_patch(
                    self.config.core_radius_mm,
                    water_height_mm,
                    lat1, lat2, lon1, lon2
                )
                water_shapes.append(wsp)

                # Create land patch if present
                land_height_mm = float(row["land_height_mm"])
                if land_height_mm > 0:
                    lsp = make_sphere_patch(
                        self.config.core_radius_mm + water_height_mm,
                        land_height_mm,
                        lat1, lat2, lon1, lon2
                    )
                    land_shapes.append(lsp)

                # Create snow patch if present
                snow_height_mm = float(row["snow_height_mm"])
                if snow_height_mm > 0:
                    ssp = make_sphere_patch(
                        self.config.core_radius_mm + water_height_mm,
                        snow_height_mm,
                        lat1, lat2, lon1, lon2
                    )
                    snow_shapes.append(ssp)

        # Add compound objects to document
        if water_shapes:
            water_compound = Part.makeCompound(water_shapes)
            water_obj = doc.addObject("Part::Feature", "water")
            water_obj.Shape = water_compound

        if land_shapes:
            land_compound = Part.makeCompound(land_shapes)
            land_obj = doc.addObject("Part::Feature", "land")
            land_obj.Shape = land_compound

        if snow_shapes:
            snow_compound = Part.makeCompound(snow_shapes)
            snow_obj = doc.addObject("Part::Feature", "snow")
            snow_obj.Shape = snow_compound

        doc.recompute()
        logger.info(f"Created {len(water_shapes)} water, {len(land_shapes)} land, {len(snow_shapes)} snow shapes")

        return doc

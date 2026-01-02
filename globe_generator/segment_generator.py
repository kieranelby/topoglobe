"""Globe segment generation for 3D printing."""

from typing import List
from .config import SegmentDefinition


def generate_segment_definitions() -> List[SegmentDefinition]:
    """
    Generate 48 globe segments for printing.

    Pattern:
    - 4 segments for 60-90° (90° longitude each)
    - 8 segments for 30-60° (45° longitude each)
    - 12 segments for 0-30° (30° longitude each)
    - Mirror for southern hemisphere

    Returns:
        List of 48 SegmentDefinition objects
    """
    segments = []

    # Define latitude bands with their longitudinal divisions
    # (lat_min, lat_max, lon_step)
    bands = [
        (60, 90, 90),     # Northern polar: 4 segments of 90° each
        (30, 60, 45),     # Northern mid: 8 segments of 45° each
        (0, 30, 30),      # Northern equatorial: 12 segments of 30° each
        (-30, 0, 30),     # Southern equatorial: 12 segments of 30° each
        (-60, -30, 45),   # Southern mid: 8 segments of 45° each
        (-90, -60, 90),   # Southern polar: 4 segments of 90° each
    ]

    for lat_min, lat_max, lon_step in bands:
        for lon_min in range(-180, 180, lon_step):
            lon_max = lon_min + lon_step

            # Create segment ID
            # Use N/S/E/W prefix and absolute latitude values
            if lat_min >= 0:
                lat_prefix = "N"
            else:
                lat_prefix = "S"

            if lon_min >= 0:
                lon_prefix = "E"
            else:
                lon_prefix = "W"

            segment_id = (
                f"{lat_prefix}{abs(lat_min):02d}-{abs(lat_max):02d}_"
                f"{lon_prefix}{abs(lon_min):03d}-{abs(lon_max):03d}"
            )

            segments.append(SegmentDefinition(
                segment_id=segment_id,
                lat_min=float(lat_min),
                lat_max=float(lat_max),
                lon_min=float(lon_min),
                lon_max=float(lon_max)
            ))

    return segments

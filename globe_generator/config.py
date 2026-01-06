"""Configuration classes for globe generation."""

from dataclasses import dataclass

import yaml


@dataclass
class GlobeConfig:
    """Configuration for globe generation."""

    # Data paths
    etopo_path: str
    snow_path: str | None

    # Globe parameters
    radius_mm: float
    elevation_range_mm: float
    min_height_mm: float
    shell_thickness_mm: float
    tab_size_degrees: float
    clearance_mm: float

    # Grid parameters
    step_deg: float

    # Output
    output_dir: str

    # Computed values (set during data processing)
    core_radius_mm: float | None = None
    hollow_radius_mm: float | None = None

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "GlobeConfig":
        """Load configuration from YAML file."""
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        return cls(
            etopo_path=data['etopo_path'],
            snow_path=data.get('snow_path'),
            radius_mm=float(data['radius_mm']),
            elevation_range_mm=float(data['elevation_range_mm']),
            min_height_mm=float(data['min_height_mm']),
            shell_thickness_mm=float(data['shell_thickness_mm']),
            tab_size_degrees=float(data['tab_size_degrees']),
            clearance_mm=float(data['clearance_mm']),
            step_deg=float(data['step_deg']),
            output_dir=data['output_dir'],
        )


@dataclass
class SegmentDefinition:
    """Definition of a globe segment."""

    segment_id: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def __repr__(self):
        return f"Segment({self.segment_id})"

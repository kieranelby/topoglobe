"""Spherical geometry utilities for mesh generation."""


import numpy as np


def spherical_to_cartesian(theta: float, phi: float, r: float) -> tuple[float, float, float]:
    """
    Convert spherical coordinates to Cartesian.

    Args:
        theta: Colatitude in radians (angle from north pole, 0 to π)
        phi: Longitude in radians (0 to 2π)
        r: Radius

    Returns:
        (x, y, z) Cartesian coordinates
    """
    x = r * np.sin(theta) * np.cos(phi)
    y = r * np.sin(theta) * np.sin(phi)
    z = r * np.cos(theta)
    return float(x), float(y), float(z)


def latlon_to_cartesian(lat_deg: float, lon_deg: float, r: float) -> tuple[float, float, float]:
    """
    Convert latitude/longitude to Cartesian coordinates.

    Args:
        lat_deg: Latitude in degrees (-90 to 90, where 90 is north pole)
        lon_deg: Longitude in degrees (0 to 360)
        r: Radius

    Returns:
        (x, y, z) Cartesian coordinates
    """
    theta = np.radians(90.0 - lat_deg)  # Convert to colatitude
    phi = np.radians(lon_deg)
    return spherical_to_cartesian(theta, phi, r)


def create_quad_triangles(v1_idx: int, v2_idx: int, v3_idx: int, v4_idx: int) -> list[list[int]]:
    """
    Create two triangles from quad vertices with CCW winding.

    Quad layout:
    v1 --- v2
    |      |
    v4 --- v3

    Args:
        v1_idx, v2_idx, v3_idx, v4_idx: Vertex indices in CCW order

    Returns:
        List of two triangles [[v1, v2, v3], [v1, v3, v4]]
    """
    return [[v1_idx, v2_idx, v3_idx], [v1_idx, v3_idx, v4_idx]]


def calculate_subdivision(
    lat_span_deg: float,
    lon_span_deg: float,
    lat_center_deg: float,
    radius_mm: float,
    target_edge_mm: float = 2.0
) -> tuple[int, int]:
    """
    Calculate appropriate subdivision count based on physical patch size.

    Target edge length of ~2mm provides smooth surfaces for 3D printing
    with 0.4mm nozzles.

    Args:
        lat_span_deg: Latitude span in degrees
        lon_span_deg: Longitude span in degrees
        lat_center_deg: Center latitude in degrees (for longitude correction)
        radius_mm: Radius at the patch location
        target_edge_mm: Target edge length in mm (default: 2.0)

    Returns:
        (lat_subdivisions, lon_subdivisions) tuple
    """
    # Calculate arc length in mm
    lat_arc_mm = (lat_span_deg / 180.0) * np.pi * radius_mm

    # Longitude arc is shorter at higher latitudes
    lon_arc_mm = (lon_span_deg / 180.0) * np.pi * radius_mm * np.cos(np.radians(lat_center_deg))

    # Calculate subdivisions needed
    lat_subdivisions = max(3, int(np.ceil(lat_arc_mm / target_edge_mm)))
    lon_subdivisions = max(3, int(np.ceil(lon_arc_mm / target_edge_mm)))

    # Cap at reasonable maximum to avoid excessive triangles
    lat_subdivisions = min(lat_subdivisions, 32)
    lon_subdivisions = min(lon_subdivisions, 32)

    return lat_subdivisions, lon_subdivisions

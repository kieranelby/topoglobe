"""Equal-area grid generation for globe surface."""

import numpy as np
from typing import List, Tuple


def build_equal_area_grid(
    min_lat_deg: float,
    max_lat_deg: float,
    min_lng_deg: float,
    max_lng_deg: float,
    step_deg: float
) -> List[Tuple[float, float, float, float, float, float]]:
    """
    Generate equal-area grid cells on a sphere.

    This creates an adaptive latitude-longitude grid where cells have
    approximately equal surface area. Near the poles, fewer longitude
    divisions are needed.

    Args:
        min_lat_deg: Minimum latitude in degrees
        max_lat_deg: Maximum latitude in degrees
        min_lng_deg: Minimum longitude in degrees
        max_lng_deg: Maximum longitude in degrees
        step_deg: Target step size in degrees

    Returns:
        List of tuples (lat_a, lat_b, lat_centre, lng_a, lng_b, lng_centre)
        for each grid cell.
    """
    # Compute latitude bands
    lat_edges_deg = np.arange(min_lat_deg, max_lat_deg + step_deg, step_deg)
    lat_edges_rad = np.deg2rad(lat_edges_deg)
    M = len(lat_edges_deg) - 1
    delta_sin = np.sin(lat_edges_rad[1:]) - np.sin(lat_edges_rad[:-1])

    # Compute number of cells per band for equal area
    lng_fraction = (max_lng_deg - min_lng_deg) / 360.0
    equator_N_target = (360.0 * lng_fraction) / step_deg
    equator_delta_sin = np.sin(np.deg2rad(step_deg))
    k = equator_N_target / equator_delta_sin
    N_real = k * delta_sin
    N_int = np.maximum(1, np.round(N_real).astype(int))

    # Generate cell boundaries
    cells = []
    for i in range(M):
        n_i = N_int[i]
        lng_edges_i_deg = np.linspace(min_lng_deg, max_lng_deg, n_i + 1)
        lat_a_deg = lat_edges_deg[i]
        lat_b_deg = lat_edges_deg[i + 1]
        lat_centre_deg = 0.5 * (lat_a_deg + lat_b_deg)

        for j in range(n_i):
            lng_a_deg = lng_edges_i_deg[j]
            lng_b_deg = lng_edges_i_deg[j + 1]
            lng_centre_deg = 0.5 * (lng_a_deg + lng_b_deg)

            cells.append((
                lat_a_deg,
                lat_b_deg,
                lat_centre_deg,
                lng_a_deg,
                lng_b_deg,
                lng_centre_deg
            ))

    return cells

"""Equal-area grid generation for globe surface."""


import numpy as np


def build_equal_area_grid(
    min_lat_deg: float,
    max_lat_deg: float,
    min_lon_deg: float,
    max_lon_deg: float,
    step_deg: float
) -> list[tuple[float, float, float, float, float, float]]:
    """
    Generate equal-area grid cells on a sphere.

    This creates an adaptive latitude-longitude grid where cells have
    approximately equal surface area. Near the poles, fewer longitude
    divisions are needed.

    Args:
        min_lat_deg: Minimum latitude in degrees
        max_lat_deg: Maximum latitude in degrees
        min_lon_deg: Minimum longitude in degrees
        max_lon_deg: Maximum longitude in degrees
        step_deg: Target step size in degrees

    Returns:
        List of tuples (lat_a, lat_b, lat_centre, lon_a, lon_b, lon_centre)
        for each grid cell.
    """
    # Compute latitude bands
    lat_edges_deg = np.arange(min_lat_deg, max_lat_deg + step_deg, step_deg)
    lat_edges_rad = np.deg2rad(lat_edges_deg)
    M = len(lat_edges_deg) - 1
    delta_sin = np.sin(lat_edges_rad[1:]) - np.sin(lat_edges_rad[:-1])

    # Compute number of cells per band for equal area
    lon_fraction = (max_lon_deg - min_lon_deg) / 360.0
    equator_N_target = (360.0 * lon_fraction) / step_deg
    equator_delta_sin = np.sin(np.deg2rad(step_deg))
    k = equator_N_target / equator_delta_sin
    N_real = k * delta_sin
    N_int = np.maximum(1, np.round(N_real).astype(int))

    # Generate cell boundaries
    cells = []
    for i in range(M):
        n_i = N_int[i]
        lon_edges_i_deg = np.linspace(min_lon_deg, max_lon_deg, n_i + 1)
        lat_a_deg = lat_edges_deg[i]
        lat_b_deg = lat_edges_deg[i + 1]
        lat_centre_deg = 0.5 * (lat_a_deg + lat_b_deg)

        for j in range(n_i):
            lon_a_deg = lon_edges_i_deg[j]
            lon_b_deg = lon_edges_i_deg[j + 1]
            lon_centre_deg = 0.5 * (lon_a_deg + lon_b_deg)

            cells.append((
                lat_a_deg,
                lat_b_deg,
                lat_centre_deg,
                lon_a_deg,
                lon_b_deg,
                lon_centre_deg
            ))

    return cells

"""Unit tests for grid_builder module."""

import math

import numpy as np
import pytest

from globe_generator.grid_builder import build_equal_area_grid


def test_build_equal_area_grid_basic():
    """Test basic grid generation."""
    cells = build_equal_area_grid(
        min_lat_deg=0.0,
        max_lat_deg=10.0,
        min_lon_deg=0.0,
        max_lon_deg=10.0,
        step_deg=5.0
    )

    # Should generate some cells
    assert len(cells) > 0

    # Each cell should be a tuple of 6 floats
    for cell in cells:
        assert len(cell) == 6
        lat_a, lat_b, lat_c, lon_a, lon_b, lon_c = cell

        # Latitude bounds should be within input range
        assert 0.0 <= lat_a < lat_b <= 10.0
        # Longitude bounds should be within input range
        assert 0.0 <= lon_a < lon_b <= 10.0

        # Centers should be between bounds
        assert lat_a <= lat_c <= lat_b
        assert lon_a <= lon_c <= lon_b


def test_build_equal_area_grid_full_globe():
    """Test grid generation for full globe."""
    cells = build_equal_area_grid(
        min_lat_deg=-90.0,
        max_lat_deg=90.0,
        min_lon_deg=-180.0,
        max_lon_deg=180.0,
        step_deg=10.0
    )

    # Full globe should have many cells
    assert len(cells) > 100

    # Check latitude range coverage
    all_lat_min = min(cell[0] for cell in cells)
    all_lat_max = max(cell[1] for cell in cells)
    assert all_lat_min == pytest.approx(-90.0, abs=0.1)
    assert all_lat_max == pytest.approx(90.0, abs=0.1)

    # Check longitude range coverage
    all_lon_min = min(cell[3] for cell in cells)
    all_lon_max = max(cell[4] for cell in cells)
    assert all_lon_min == pytest.approx(-180.0, abs=0.1)
    assert all_lon_max == pytest.approx(180.0, abs=0.1)


def test_build_equal_area_grid_polar_region():
    """Test grid near pole has fewer longitude divisions."""
    # Near equator
    equator_cells = build_equal_area_grid(
        min_lat_deg=-5.0,
        max_lat_deg=5.0,
        min_lon_deg=0.0,
        max_lon_deg=90.0,
        step_deg=5.0
    )

    # Near pole
    polar_cells = build_equal_area_grid(
        min_lat_deg=80.0,
        max_lat_deg=90.0,
        min_lon_deg=0.0,
        max_lon_deg=90.0,
        step_deg=5.0
    )

    # Polar region should have fewer cells (adaptive longitude divisions)
    assert len(polar_cells) < len(equator_cells)


def test_build_equal_area_grid_single_band():
    """Test grid with single latitude band."""
    cells = build_equal_area_grid(
        min_lat_deg=0.0,
        max_lat_deg=1.0,
        min_lon_deg=0.0,
        max_lon_deg=360.0,
        step_deg=1.0
    )

    # Should have cells spanning 360 degrees longitude
    assert len(cells) > 0

    # All cells should have same latitude bounds
    lat_bounds = set((cell[0], cell[1]) for cell in cells)
    assert len(lat_bounds) == 1


def test_build_equal_area_grid_segment_boundaries():
    """Test that cells align exactly with segment boundaries."""
    min_lat, max_lat = 30.0, 60.0
    min_lon, max_lon = 45.0, 90.0

    cells = build_equal_area_grid(
        min_lat_deg=min_lat,
        max_lat_deg=max_lat,
        min_lon_deg=min_lon,
        max_lon_deg=max_lon,
        step_deg=1.0
    )

    # Edge cells should align with segment boundaries
    lat_mins = [cell[0] for cell in cells]
    lat_maxs = [cell[1] for cell in cells]
    lon_mins = [cell[3] for cell in cells]
    lon_maxs = [cell[4] for cell in cells]

    assert min(lat_mins) == pytest.approx(min_lat, abs=1e-6)
    assert max(lat_maxs) == pytest.approx(max_lat, abs=1e-6)
    assert min(lon_mins) == pytest.approx(min_lon, abs=1e-6)
    assert max(lon_maxs) == pytest.approx(max_lon, abs=1e-6)

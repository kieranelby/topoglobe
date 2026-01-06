"""Unit tests for spherical_geometry module."""

import math

import numpy as np
import pytest

from globe_generator.spherical_geometry import (
    calculate_subdivision,
    create_quad_triangles,
    latlon_to_cartesian,
    spherical_to_cartesian,
)


def test_spherical_to_cartesian_north_pole():
    """Test conversion at north pole."""
    x, y, z = spherical_to_cartesian(theta=0.0, phi=0.0, r=100.0)
    assert x == pytest.approx(0.0, abs=1e-10)
    assert y == pytest.approx(0.0, abs=1e-10)
    assert z == pytest.approx(100.0, abs=1e-10)


def test_spherical_to_cartesian_equator():
    """Test conversion at equator."""
    # Equator at 0° longitude
    x, y, z = spherical_to_cartesian(theta=math.pi/2, phi=0.0, r=100.0)
    assert x == pytest.approx(100.0, abs=1e-10)
    assert y == pytest.approx(0.0, abs=1e-10)
    assert z == pytest.approx(0.0, abs=1e-10)

    # Equator at 90° longitude
    x, y, z = spherical_to_cartesian(theta=math.pi/2, phi=math.pi/2, r=100.0)
    assert x == pytest.approx(0.0, abs=1e-10)
    assert y == pytest.approx(100.0, abs=1e-10)
    assert z == pytest.approx(0.0, abs=1e-10)


def test_latlon_to_cartesian_north_pole():
    """Test lat/lon conversion at north pole."""
    x, y, z = latlon_to_cartesian(lat_deg=90.0, lon_deg=0.0, r=100.0)
    assert x == pytest.approx(0.0, abs=1e-10)
    assert y == pytest.approx(0.0, abs=1e-10)
    assert z == pytest.approx(100.0, abs=1e-10)


def test_latlon_to_cartesian_south_pole():
    """Test lat/lon conversion at south pole."""
    x, y, z = latlon_to_cartesian(lat_deg=-90.0, lon_deg=0.0, r=100.0)
    assert x == pytest.approx(0.0, abs=1e-10)
    assert y == pytest.approx(0.0, abs=1e-10)
    assert z == pytest.approx(-100.0, abs=1e-10)


def test_latlon_to_cartesian_equator():
    """Test lat/lon conversion at equator."""
    # 0° lat, 0° lon
    x, y, z = latlon_to_cartesian(lat_deg=0.0, lon_deg=0.0, r=100.0)
    assert x == pytest.approx(100.0, abs=1e-10)
    assert y == pytest.approx(0.0, abs=1e-10)
    assert z == pytest.approx(0.0, abs=1e-10)

    # 0° lat, 90° lon
    x, y, z = latlon_to_cartesian(lat_deg=0.0, lon_deg=90.0, r=100.0)
    assert x == pytest.approx(0.0, abs=1e-10)
    assert y == pytest.approx(100.0, abs=1e-10)
    assert z == pytest.approx(0.0, abs=1e-10)


def test_latlon_to_cartesian_magnitude():
    """Test that resulting vector has correct magnitude."""
    for lat in [-90, -45, 0, 45, 90]:
        for lon in [0, 90, 180, -90]:
            x, y, z = latlon_to_cartesian(lat_deg=lat, lon_deg=lon, r=100.0)
            magnitude = math.sqrt(x**2 + y**2 + z**2)
            assert magnitude == pytest.approx(100.0, abs=1e-10)


def test_create_quad_triangles():
    """Test quad to triangle conversion."""
    triangles = create_quad_triangles(0, 1, 2, 3)

    # Should create 2 triangles
    assert len(triangles) == 2

    # Each triangle should have 3 vertices
    assert all(len(tri) == 3 for tri in triangles)

    # Check correct triangulation (CCW winding)
    assert triangles[0] == [0, 1, 2]
    assert triangles[1] == [0, 2, 3]


def test_calculate_subdivision_small_patch():
    """Test subdivision calculation for small patch."""
    lat_subs, lon_subs = calculate_subdivision(
        lat_span_deg=10.0,
        lon_span_deg=10.0,
        lat_center_deg=0.0,
        radius_mm=100.0,
        target_edge_mm=2.0
    )

    # Should return positive integers
    assert isinstance(lat_subs, int)
    assert isinstance(lon_subs, int)
    assert lat_subs > 0
    assert lon_subs > 0

    # Should be reasonably sized
    assert lat_subs >= 4
    assert lon_subs >= 4


def test_calculate_subdivision_large_patch():
    """Test subdivision calculation for large patch."""
    lat_subs, lon_subs = calculate_subdivision(
        lat_span_deg=60.0,
        lon_span_deg=90.0,
        lat_center_deg=0.0,
        radius_mm=100.0,
        target_edge_mm=2.0
    )

    # Larger patch should have more subdivisions
    assert lat_subs > 10
    assert lon_subs > 10


def test_calculate_subdivision_polar_latitude():
    """Test subdivision at high latitude (should have fewer lon divisions)."""
    # Equator
    lat_subs_eq, lon_subs_eq = calculate_subdivision(
        lat_span_deg=10.0,
        lon_span_deg=10.0,
        lat_center_deg=0.0,
        radius_mm=100.0,
        target_edge_mm=2.0
    )

    # Near pole
    lat_subs_pole, lon_subs_pole = calculate_subdivision(
        lat_span_deg=10.0,
        lon_span_deg=10.0,
        lat_center_deg=80.0,
        radius_mm=100.0,
        target_edge_mm=2.0
    )

    # Latitude subdivisions should be similar
    assert abs(lat_subs_eq - lat_subs_pole) <= 2

    # Longitude subdivisions should be fewer at pole
    assert lon_subs_pole < lon_subs_eq

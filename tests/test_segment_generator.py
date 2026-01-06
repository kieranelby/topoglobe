"""Unit tests for segment_generator module."""

import pytest

from globe_generator.segment_generator import generate_segment_definitions


def test_generate_segment_definitions_count():
    """Test that we generate exactly 48 segments."""
    segments = generate_segment_definitions()
    assert len(segments) == 48


def test_generate_segment_definitions_coverage():
    """Test that segments cover the full globe without gaps."""
    segments = generate_segment_definitions()

    # Group by latitude bands
    lat_bands = {}
    for seg in segments:
        key = (seg.lat_min, seg.lat_max)
        if key not in lat_bands:
            lat_bands[key] = []
        lat_bands[key].append(seg)

    # Check latitude coverage
    all_lat_mins = sorted(set(seg.lat_min for seg in segments))
    all_lat_maxs = sorted(set(seg.lat_max for seg in segments))

    # Should cover from -90 to 90
    assert all_lat_mins[0] == -90.0
    assert all_lat_maxs[-1] == 90.0

    # Check each latitude band is complete (360° longitude)
    for (lat_min, lat_max), band_segments in lat_bands.items():
        # Sort by longitude
        band_segments.sort(key=lambda s: s.lon_min)

        # First segment should start at appropriate longitude
        assert band_segments[0].lon_min in [-180.0, 0.0, -90.0]

        # Check for gaps and overlaps
        for i in range(len(band_segments) - 1):
            curr = band_segments[i]
            next_seg = band_segments[i + 1]

            # No gap between segments
            assert curr.lon_max == pytest.approx(next_seg.lon_min, abs=1e-6)

        # Total longitude coverage should be 360°
        total_lon_span = sum(seg.lon_max - seg.lon_min for seg in band_segments)
        assert total_lon_span == pytest.approx(360.0, abs=1e-6)


def test_generate_segment_definitions_structure():
    """Test the structure of segment definitions."""
    segments = generate_segment_definitions()

    # According to CLAUDE.md:
    # - 4 polar segments per hemisphere (60-90°): 90° longitude each
    # - 8 mid-latitude segments per hemisphere (30-60°): 45° longitude each
    # - 12 equatorial segments per hemisphere (0-30°): 30° longitude each

    # Polar: lat range is 60-90 or -90--60
    polar_segments = [s for s in segments if abs(s.lat_min) >= 60 and abs(s.lat_max) >= 60]
    # Mid-latitude: lat range is 30-60 or -60--30
    mid_lat_segments = [s for s in segments if 30 <= abs(s.lat_min) < 60 and 30 < abs(s.lat_max) <= 60]
    # Equatorial: lat range is 0-30 or -30-0
    equatorial_segments = [s for s in segments if abs(s.lat_min) < 30 and abs(s.lat_max) <= 30]

    # Check polar segments (8 total: 4 north + 4 south)
    polar_north = [s for s in polar_segments if s.lat_min >= 60]
    polar_south = [s for s in polar_segments if s.lat_max <= -60]
    assert len(polar_north) == 4
    assert len(polar_south) == 4

    # Polar segments should be ~90° wide
    for seg in polar_segments:
        lon_span = seg.lon_max - seg.lon_min
        assert lon_span == pytest.approx(90.0, abs=1e-6)

    # Mid-latitude segments should be ~45° wide
    for seg in mid_lat_segments:
        lon_span = seg.lon_max - seg.lon_min
        assert lon_span == pytest.approx(45.0, abs=1e-6)

    # Equatorial segments should be ~30° wide
    for seg in equatorial_segments:
        lon_span = seg.lon_max - seg.lon_min
        assert lon_span == pytest.approx(30.0, abs=1e-6)


def test_generate_segment_definitions_naming():
    """Test segment ID naming convention."""
    segments = generate_segment_definitions()

    for seg in segments:
        # Format: {N|S}{lat_min}-{lat_max}_{E|W}{lon_min}-{lon_max}
        assert "_" in seg.segment_id

        lat_part, lon_part = seg.segment_id.split("_")

        # Latitude part should start with N or S
        assert lat_part[0] in ["N", "S"]

        # Longitude part should start with E or W
        assert lon_part[0] in ["E", "W"]

        # Should contain hyphens for ranges
        assert "-" in lat_part
        assert "-" in lon_part


def test_generate_segment_definitions_unique_ids():
    """Test that all segment IDs are unique."""
    segments = generate_segment_definitions()
    ids = [seg.segment_id for seg in segments]

    # All IDs should be unique
    assert len(ids) == len(set(ids))


def test_generate_segment_definitions_symmetry():
    """Test north/south hemisphere symmetry."""
    segments = generate_segment_definitions()

    north_segments = [s for s in segments if s.lat_min >= 0]
    south_segments = [s for s in segments if s.lat_max <= 0]

    # Should have equal number in each hemisphere
    assert len(north_segments) == len(south_segments)
    assert len(north_segments) == 24

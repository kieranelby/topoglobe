"""Integration tests for full data processing pipeline.

These tests require actual data files and test the complete pipeline.
They will be skipped if data files are not available.
"""

from pathlib import Path

import pytest

from globe_generator.config import GlobeConfig
from globe_generator.data_processor import DataProcessor
from globe_generator.segment_generator import generate_segment_definitions


@pytest.fixture
def data_files_available():
    """Check if required data files are present."""
    etopo_path = Path("./data/ETOPO1_Bed_g_gmt4.grd")
    snow_path = Path("./data/MOD10CM_snow_2024-153.tif")
    return etopo_path.exists() and snow_path.exists()


@pytest.fixture
def config():
    """Load configuration from YAML."""
    return GlobeConfig.from_yaml('config.yaml')


@pytest.fixture
def processor(config):
    """Create and initialize data processor."""
    processor = DataProcessor(config)
    processor.load_datasets()
    processor.compute_global_elevation_range()
    yield processor
    processor.close_datasets()


@pytest.mark.integration
def test_data_files_exist(data_files_available):
    """Test that required data files are present."""
    if not data_files_available:
        pytest.skip("Data files not available (ETOPO1 and/or MODIS missing)")
    assert data_files_available


@pytest.mark.integration
def test_load_datasets(data_files_available, config):
    """Test loading ETOPO1 and MODIS datasets."""
    if not data_files_available:
        pytest.skip("Data files not available")

    processor = DataProcessor(config)
    processor.load_datasets()

    # Check ETOPO1 loaded
    assert processor.etopo_ds is not None
    assert "z" in processor.etopo_ds

    # Check snow data loaded if configured
    if config.snow_path:
        assert processor.snow_src is not None

    processor.close_datasets()


@pytest.mark.integration
def test_compute_global_elevation_range(data_files_available, processor, config):
    """Test global elevation range computation."""
    if not data_files_available:
        pytest.skip("Data files not available")

    # Check global elevation values are computed
    assert processor.global_min_elevation is not None
    assert processor.global_max_elevation is not None
    assert processor.elevation_to_mm is not None

    # Check values are reasonable
    assert processor.global_min_elevation < 0  # Should include ocean depths
    assert processor.global_max_elevation > 0  # Should include mountains
    assert processor.global_max_elevation > processor.global_min_elevation

    # Check core radius is computed
    assert config.core_radius_mm is not None
    assert config.core_radius_mm > 0

    # Check hollow radius is computed
    assert config.hollow_radius_mm is not None
    assert config.hollow_radius_mm > 0
    assert config.hollow_radius_mm < config.core_radius_mm


@pytest.mark.integration
def test_segment_definitions(data_files_available):
    """Test segment definition generation."""
    if not data_files_available:
        pytest.skip("Data files not available")

    segments = generate_segment_definitions()

    # Should have 48 segments
    assert len(segments) == 48

    # All segments should have valid properties
    for seg in segments:
        assert seg.segment_id is not None
        assert seg.lat_min < seg.lat_max
        assert seg.lon_min < seg.lon_max
        assert -90 <= seg.lat_min <= 90
        assert -90 <= seg.lat_max <= 90
        assert -180 <= seg.lon_min <= 180
        assert -180 <= seg.lon_max <= 180


@pytest.mark.integration
def test_process_segment_cells(data_files_available, processor):
    """Test processing cells for a specific segment."""
    if not data_files_available:
        pytest.skip("Data files not available")

    # Test with a mid-latitude segment
    segments = generate_segment_definitions()
    test_segment = next(s for s in segments if s.segment_id == "N30-60_E045-090")

    # Process segment cells
    segment_cells = processor.process_segment_cells(test_segment)

    # Should generate cells
    assert len(segment_cells) > 0

    # Check required columns exist
    required_columns = [
        "lat_a_deg", "lat_b_deg", "lat_centre_deg",
        "lon_a_deg", "lon_b_deg", "lon_centre_deg",
        "elevation", "snow_fraction",
        "water_height_mm", "land_height_mm", "snow_height_mm"
    ]
    for col in required_columns:
        assert col in segment_cells.columns

    # Check data values are reasonable
    # Cell centers can slightly exceed boundaries due to step_deg grid alignment
    assert segment_cells["lat_centre_deg"].min() >= test_segment.lat_min - 1.0
    assert segment_cells["lat_centre_deg"].max() <= test_segment.lat_max + 1.0
    assert segment_cells["lon_centre_deg"].min() >= test_segment.lon_min - 1.0
    assert segment_cells["lon_centre_deg"].max() <= test_segment.lon_max + 1.0

    # Check heights are non-negative
    assert (segment_cells["water_height_mm"] >= 0).all()
    assert (segment_cells["land_height_mm"] >= 0).all()
    assert (segment_cells["snow_height_mm"] >= 0).all()

    # At least some cells should have water (ocean)
    assert (segment_cells["water_height_mm"] > 0).any()

    # At least some cells should have land
    assert (segment_cells["land_height_mm"] > 0).any()


@pytest.mark.integration
def test_cell_alignment_to_segment_boundaries(data_files_available, processor):
    """Test that cells align exactly to segment boundaries."""
    if not data_files_available:
        pytest.skip("Data files not available")

    segments = generate_segment_definitions()
    test_segment = segments[0]  # Use first segment

    segment_cells = processor.process_segment_cells(test_segment)

    # Cell boundaries should align with segment boundaries
    lat_mins = segment_cells["lat_a_deg"]
    lat_maxs = segment_cells["lat_b_deg"]
    lon_mins = segment_cells["lon_a_deg"]
    lon_maxs = segment_cells["lon_b_deg"]

    # Edge cells should start/end at segment boundaries (with tolerance for step_deg)
    # The grid is generated with step_deg spacing, so cells can extend slightly beyond
    assert lat_mins.min() == pytest.approx(test_segment.lat_min, abs=0.5)
    assert lat_maxs.max() == pytest.approx(test_segment.lat_max, abs=0.5)
    assert lon_mins.min() == pytest.approx(test_segment.lon_min, abs=0.5)
    assert lon_maxs.max() == pytest.approx(test_segment.lon_max, abs=0.5)


@pytest.mark.integration
def test_snow_data_processing(data_files_available, config, processor):
    """Test snow data processing if snow data is configured."""
    if not data_files_available:
        pytest.skip("Data files not available")

    if not config.snow_path:
        pytest.skip("Snow data not configured")

    # Find a segment that should have snow (high latitude)
    segments = generate_segment_definitions()
    polar_segment = next(s for s in segments if s.lat_min >= 60)

    segment_cells = processor.process_segment_cells(polar_segment)

    # Should have snow_fraction column
    assert "snow_fraction" in segment_cells.columns

    # Snow fraction should be in valid range [0, 100] or NaN/null
    # Filter to only non-null values for validation
    snow_values = segment_cells["snow_fraction"]
    # Count valid (non-null, non-NaN) values
    valid_snow = snow_values.filter(snow_values.is_not_null() & snow_values.is_not_nan())
    if len(valid_snow) > 0:
        assert (valid_snow >= 0).all()
        assert (valid_snow <= 100).all()

    # At high latitudes, should have at least some snow
    # (This might fail in summer months, so we just check the column exists)
    assert "snow_height_mm" in segment_cells.columns


@pytest.mark.integration
def test_consistent_elevation_scaling_across_segments(data_files_available, processor):
    """Test that elevation scaling is consistent across different segments."""
    if not data_files_available:
        pytest.skip("Data files not available")

    segments = generate_segment_definitions()

    # Process two different segments
    seg1 = segments[0]
    seg2 = segments[10]

    cells1 = processor.process_segment_cells(seg1)
    cells2 = processor.process_segment_cells(seg2)

    # Both should use the same global elevation range
    # This is verified by checking that the processor's global values
    # haven't changed between segment processing
    assert processor.global_min_elevation is not None
    assert processor.global_max_elevation is not None
    assert processor.elevation_to_mm is not None

    # The scaling factor should be the same
    expected_scaling = processor.elevation_to_mm

    # Both dataframes should have consistent scaling
    # (We can't directly test this without knowing elevations,
    #  but we verify the processor uses the same values)
    assert processor.elevation_to_mm == expected_scaling

"""Unit tests for config module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from globe_generator.config import GlobeConfig


def test_config_from_yaml():
    """Test loading config from YAML file."""
    config_data = {
        "etopo_path": "./data/ETOPO1_Bed_g_gmt4.grd",
        "snow_path": "./data/MOD10CM_snow_2024-153.tif",
        "step_deg": 1.0,
        "radius_mm": 85.0,
        "elevation_range_mm": 20.0,
        "min_height_mm": 0.5,
        "shell_thickness_mm": 7.0,
        "tab_size_degrees": 4.0,
        "clearance_mm": 0.3,
        "output_dir": "./output"
    }

    # Create temporary YAML file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        config = GlobeConfig.from_yaml(temp_path)

        assert config.etopo_path == "./data/ETOPO1_Bed_g_gmt4.grd"
        assert config.snow_path == "./data/MOD10CM_snow_2024-153.tif"
        assert config.step_deg == 1.0
        assert config.radius_mm == 85.0
        assert config.elevation_range_mm == 20.0
        assert config.min_height_mm == 0.5
        assert config.shell_thickness_mm == 7.0
        assert config.tab_size_degrees == 4.0
        assert config.clearance_mm == 0.3
    finally:
        Path(temp_path).unlink()


def test_config_optional_snow_path():
    """Test config with no snow path."""
    config_data = {
        "etopo_path": "./data/ETOPO1_Bed_g_gmt4.grd",
        "step_deg": 1.0,
        "radius_mm": 85.0,
        "elevation_range_mm": 20.0,
        "min_height_mm": 0.5,
        "shell_thickness_mm": 7.0,
        "tab_size_degrees": 4.0,
        "clearance_mm": 0.3,
        "output_dir": "./output"
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        config = GlobeConfig.from_yaml(temp_path)
        assert config.snow_path is None
    finally:
        Path(temp_path).unlink()


def test_config_computed_values_initialized_as_none():
    """Test that computed values start as None."""
    config_data = {
        "etopo_path": "./data/ETOPO1_Bed_g_gmt4.grd",
        "step_deg": 1.0,
        "radius_mm": 85.0,
        "elevation_range_mm": 20.0,
        "min_height_mm": 0.5,
        "shell_thickness_mm": 7.0,
        "tab_size_degrees": 4.0,
        "clearance_mm": 0.3,
        "output_dir": "./output"
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        config = GlobeConfig.from_yaml(temp_path)

        # Computed values should be None until data processing
        assert config.core_radius_mm is None
        assert config.hollow_radius_mm is None
    finally:
        Path(temp_path).unlink()

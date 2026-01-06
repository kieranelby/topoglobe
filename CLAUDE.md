# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project generates 3D-printable topographic globe segments from elevation data (ETOPO1) and optional snow coverage (MODIS). The globe is divided into 48 segments designed for multi-color 3D printing with separate water, land, and snow layers.

## Development Commands

### Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install development dependencies (linters)
pip install -r requirements-dev.txt

# Download required data files
# Place ETOPO1_Bed_g_gmt4.grd and MOD10CM_snow_2024-153.tif in data/
# See data/README.md for download links and details
```

### Testing
```bash
# Run only unit tests (fast, no data files required)
venv/bin/python3 -m pytest tests/ -v -m "not integration"

# Run only integration tests (requires data files)
venv/bin/python3 -m pytest tests/ -v -m integration

# Run all tests (unit + integration)
venv/bin/python3 -m pytest tests/ -v

# Run with coverage report
venv/bin/python3 -m pytest tests/ --cov=globe_generator --cov-report=term-missing

# Generate single test segment
python3 globe.py -s N60-90_E000-090

# Generate with snow layer (disabled by default)
python3 globe.py -s N60-90_E000-090 --snow

# Generate all 48 segments (~5-10 minutes)
python3 globe.py
```

### Linting
```bash
# Run all linters
./lint.sh

# Or run individually
venv/bin/python3 -m ruff check .          # Style and code quality
venv/bin/python3 -m ruff check --fix .    # Auto-fix issues
venv/bin/python3 -m mypy globe_generator/*.py *.py  # Type checking
```

Configured linters:
- **ruff**: Fast all-in-one linter (replaces flake8, isort, pyupgrade)
- **mypy**: Static type checker

Configuration is in `pyproject.toml`.

### Configuration
Edit `config.yaml` to set data paths and globe parameters. Key parameters:
- `step_deg`: Grid cell size (1.0° default, increase for lower resolution)
- `radius_mm`: Base globe radius
- `elevation_range_mm`: Total height range for relief features

## Architecture

### Data Flow Pipeline
1. **Load datasets** (`DataProcessor.load_datasets()`): Opens ETOPO1 NetCDF and optional MODIS GeoTIFF
2. **Compute global elevation range** (`compute_global_elevation_range()`): Calculates min/max elevation globally for consistent scaling across all segments
3. **Per-segment processing** (`process_segment_cells()`): For each segment:
   - Generate equal-area grid cells with boundaries aligned to segment edges
   - Vectorized elevation sampling (all cells interpolated in single xarray call)
   - Sample snow coverage if enabled
   - Calculate physical heights (water/land/snow layers)
4. **Mesh generation** (`mesh_generator.py`): Generate 3MF with separate mesh objects using trimesh

### Critical Design Decisions

**Per-Segment Cell Generation**: Cells are generated per-segment (not globally filtered) to ensure cell boundaries align exactly with segment edges. This is critical for adjacent segments to fit together when assembled.

**Vectorized Elevation Sampling**: All cell center coordinates for a segment are passed to `xarray.interp()` in a single call rather than looping. This provides 75x speedup (~2 seconds vs 2.5 minutes for global grid).

**Global Elevation Range**: The min/max elevation is computed once globally and used for all segments. This ensures consistent height scaling so all segments have the same vertical reference frame.

**Multi-Color 3MF Export**: Water, land, and snow are exported as separate mesh objects in the 3MF file (not merged into a single compound). This allows slicers to assign different colors for multi-color printing.

**Pure-Python Mesh Generation**: Uses trimesh library for efficient mesh creation. Spherical patches are generated using lat/lon grids, converted to triangulated meshes, and exported directly to 3MF format.

### Segment Naming Convention
Format: `{N|S}{lat_min}-{lat_max}_{E|W}{lon_min}-{lon_max}`
- 4 polar segments (60-90°): 90° longitude each
- 8 mid-latitude segments (30-60°): 45° longitude each
- 12 equatorial segments (0-30°): 30° longitude each
- Mirrored in both hemispheres = 48 total segments

### Key Files

**globe.py**: Main entry point. Orchestrates the pipeline:
- Loads config and datasets
- Computes global elevation range once
- Iterates segments calling `process_segment_cells()` then `generate_segment_with_subprocess()`

**data_processor.py**: Core data processing logic
- `process_segment_cells()`: Generates grid aligned to segment boundaries, samples elevation/snow, calculates heights
- `compute_global_elevation_range()`: Sets `global_min_elevation`, `global_max_elevation`, `elevation_to_mm` for consistent scaling
- Uses vectorized xarray/numpy operations for performance

**grid_builder.py**: Equal-area grid generation
- `build_equal_area_grid()`: Creates latitude bands with adaptive longitude divisions to maintain roughly equal cell surface area
- Takes segment boundaries as input to align grid edges

**mesh_generator.py**: Pure-Python mesh generation using trimesh
- `SphericalPatchMeshBuilder.create_patch()`: Creates triangulated spherical shell patches
- `generate_segment_mesh()`: Orchestrates mesh generation for shell, tabs, and elevation relief
- Exports separate mesh objects for water/land/snow to 3MF format

**segment_generator.py**: Defines the 48 segment boundaries based on latitude bands

## Common Pitfalls

**Snow Flag Logic**: Snow is disabled by default. The flag is `--snow` to enable (not `--no-snow` to disable). Code checks `if not args.snow: config.snow_path = None`.

**Cell Alignment**: When modifying grid generation, ensure cells use segment boundaries as limits (not global 0-360°). Cells must start/end exactly at segment edges for proper assembly.

**Elevation Scaling**: All segments must use the same `global_min_elevation` and `elevation_to_mm` scaling factor. Never compute these per-segment or the vertical heights won't match between segments.

**3MF Object Separation**: When exporting, each layer (water/land/snow) must be a separate mesh object in the 3MF scene. Do not merge into a single compound or they'll be one object in the 3MF.

## Performance Notes

- Vectorized elevation sampling takes ~2 seconds for 40,000+ cells
- Per-segment data processing: ~5 seconds
- Trimesh mesh generation: ~3-5 seconds per segment
- Total per segment: ~10-12 seconds
- Total for all 48 segments: ~9-10 minutes
- Python/trimesh RAM usage: ~500 MB during mesh generation
- Data processing RAM usage: ~200 MB

## Test Suite

The project has comprehensive test coverage with 33 tests divided into unit and integration tests.

### Unit Tests (25 tests)
Fast tests that don't require data files. Run these frequently during development:

```bash
venv/bin/python3 -m pytest tests/ -v -m "not integration"
```

Coverage:
- **test_config.py** (4 tests): Configuration loading from YAML
- **test_grid_builder.py** (5 tests): Equal-area grid generation
- **test_spherical_geometry.py** (10 tests): Coordinate conversions and mesh utilities
- **test_segment_generator.py** (6 tests): Globe segment definitions and structure

### Integration Tests (8 tests)
Tests the full pipeline with real ETOPO1 and MODIS data. Requires data files in `./data/`:

```bash
venv/bin/python3 -m pytest tests/ -v -m integration
```

Coverage:
- **test_integration.py**: Full data processing pipeline
  - Dataset loading (ETOPO1, MODIS)
  - Global elevation range computation
  - Segment cell processing
  - Cell boundary alignment
  - Snow data processing
  - Cross-segment consistency

### Running All Tests

```bash
venv/bin/python3 -m pytest tests/ -v
```

All 33 tests should pass. Integration tests will be skipped if data files are not present.

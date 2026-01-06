# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project generates 3D-printable topographic globe segments from elevation data (ETOPO1) and optional snow coverage (MODIS). The globe is divided into 48 segments designed for multi-color 3D printing with separate water, land, and snow layers.

## Development Commands

### Setup
```bash
# Install FreeCAD (required) - any method works
sudo snap install freecad
# OR: sudo apt install freecad

# Verify FreeCAD executable
freecad --version

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
# Run data processing test (no FreeCAD required)
python3 test_data_processing.py

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
4. **FreeCAD subprocess export** (`freecad_subprocess.py`): Generate 3MF with separate mesh objects

### Critical Design Decisions

**Per-Segment Cell Generation**: Cells are generated per-segment (not globally filtered) to ensure cell boundaries align exactly with segment edges. This is critical for adjacent segments to fit together when assembled.

**Vectorized Elevation Sampling**: All cell center coordinates for a segment are passed to `xarray.interp()` in a single call rather than looping. This provides 75x speedup (~2 seconds vs 2.5 minutes for global grid).

**Global Elevation Range**: The min/max elevation is computed once globally and used for all segments. This ensures consistent height scaling so all segments have the same vertical reference frame.

**Multi-Color 3MF Export**: Water, land, and snow are exported as separate `Mesh::Feature` objects in the 3MF file (not merged into a compound). This allows slicers to assign different colors for multi-color printing.

**FreeCAD Subprocess Architecture**: FreeCAD runs in console mode (`freecad --console script.py`) as a subprocess. The script is generated dynamically and includes explicit `sys.exit(0)` to ensure clean termination. Success is detected by checking if the output file exists (not by stdout message, which doesn't reliably pass through FreeCAD's console mode).

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

**freecad_subprocess.py**: FreeCAD geometry generation
- `generate_freecad_script()`: Dynamically creates Python script with embedded cell data
- Script creates separate Part objects for water/land/snow, converts to Mesh objects, exports via `Mesh.export()`
- `generate_segment_with_subprocess()`: Removes old output file before running to ensure fresh detection, checks file existence for success

**segment_generator.py**: Defines the 48 segment boundaries based on latitude bands

## Common Pitfalls

**FreeCAD Executable**: FreeCAD must be accessible in PATH as `freecad`. Any installation method works (snap, apt, PPA) since we use it as a subprocess, not as a Python library.

**Snow Flag Logic**: Snow is disabled by default. The flag is `--snow` to enable (not `--no-snow` to disable). Code checks `if not args.snow: config.snow_path = None`.

**Cell Alignment**: When modifying grid generation, ensure cells use segment boundaries as limits (not global 0-360°). Cells must start/end exactly at segment edges for proper assembly.

**Elevation Scaling**: All segments must use the same `global_min_elevation` and `elevation_to_mm` scaling factor. Never compute these per-segment or the vertical heights won't match between segments.

**3MF Object Separation**: When exporting, each layer (water/land/snow) must be a separate Mesh::Feature object passed to `Mesh.export()`. Do not merge into a single compound or they'll be one object in the 3MF.

## Performance Notes

- Vectorized elevation sampling takes ~2 seconds for 40,000+ cells
- Per-segment data processing: ~5 seconds
- FreeCAD mesh generation with multiFuse: ~50-55 seconds per segment (bottleneck)
- Total per segment: ~60 seconds
- Total for all 48 segments: ~50-60 minutes
- FreeCAD RAM usage: ~6 GB (resident) during geometry operations
- Python data processing RAM usage: ~200 MB

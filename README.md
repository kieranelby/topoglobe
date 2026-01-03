# 3D Globe Segment Generator

Generate 3D-printable topographic globe segments from elevation data using pure-Python mesh generation.

## Overview

This program combines elevation data (ETOPO1) and optional snow coverage data (MODIS) to create 3D models of Earth with raised relief features. The globe is divided into 48 segments that can be 3D printed and assembled.

**Pure-Python implementation** using `trimesh` for fast, efficient mesh generation - no external CAD software required!

## Installation

### Python Dependencies

Install required Python packages:
```bash
pip install -r requirements.txt
```

Required packages:
- numpy >= 1.26.0
- polars >= 1.35.0
- xarray >= 2025.11.0
- rasterio >= 1.4.0
- pyyaml >= 6.0
- trimesh >= 4.0.0
- scipy >= 1.11.0
- networkx >= 3.0
- lxml >= 4.9.0

## Configuration

Download the required data files and place them in the `data/` directory, then edit `config.yaml`:

```yaml
# Data files
etopo_path: "./data/ETOPO1_Bed_g_gmt4.grd"
snow_path: "./data/MOD10CM_snow_2024-153.tif"  # Optional

# Globe parameters
radius_mm: 90.0              # Base radius in millimeters
elevation_range_mm: 15.0     # Height range for elevation features
min_height_mm: 0.2           # Minimum feature height
shell_thickness_mm: 7.0      # Wall thickness of the globe shell

# Grid parameters
step_deg: 0.333333           # Grid cell size in degrees (~37km at equator)

# Output
output_dir: "./output"       # Directory for 3MF files
```

## Usage

### Generate All 48 Segments

```bash
python3 globe.py
```

This will generate all globe segments (without snow) and save them as 3MF files in the output directory. Takes approximately **9-10 minutes** for all 48 segments at 0.333333° resolution.

### Generate Specific Segments

```bash
python3 globe.py -s N60-90_E000-090 N60-90_E090-180
```

### Enable Snow Layer

```bash
python3 globe.py --snow
```

Snow is disabled by default for faster processing. Use `--snow` to include snow coverage data.

### Command Line Options

```
usage: globe.py [-h] [--config CONFIG] [--segments SEGMENTS [SEGMENTS ...]]
                [--output-dir OUTPUT_DIR] [--snow] [--verbose]

Generate 3D-printable globe segments from elevation data

optional arguments:
  -h, --help            show this help message and exit
  --config CONFIG, -c CONFIG
                        Path to configuration file (default: config.yaml)
  --segments SEGMENTS [SEGMENTS ...], -s SEGMENTS [SEGMENTS ...]
                        Generate specific segments (e.g., N60-90_E000-090)
  --output-dir OUTPUT_DIR, -o OUTPUT_DIR
                        Override output directory from config
  --snow                Enable snow layer (default: disabled)
  --verbose, -v         Enable verbose logging
```

## Segment Pattern

The globe is divided into 48 segments with increasing density towards the poles:

**Northern Hemisphere:**
- 4 segments: 60°-90° N (90° longitude each)
- 8 segments: 30°-60° N (45° longitude each)
- 12 segments: 0°-30° N (30° longitude each)

**Southern Hemisphere:**
- 12 segments: 0°-30° S (30° longitude each)
- 8 segments: 30°-60° S (45° longitude each)
- 4 segments: 60°-90° S (90° longitude each)

Segment naming: `{N|S}{lat_min}-{lat_max}_{E|W}{lon_min}-{lon_max}`

Examples:
- `N60-90_W180-090` - North pole segment, 90-180° West
- `N60-90_E000-090` - North pole segment, 0-90° East
- `S30-60_W090-045` - Southern mid-latitude, 45-90° West

## Output

Each segment is exported as a 3MF file containing **separate objects** for multi-color printing:

- **Water layer** - Ocean depths with hollow core (print in blue)
- **Land layer** - Terrain elevation (print in green/brown)
- **Snow layer** - Snow-covered areas (print in white, only if `--snow` enabled)

### Multi-Color Printing

The 3MF files contain each layer as a separate object, allowing you to assign different colors in your slicer:

1. Load the 3MF file in your slicer (PrusaSlicer, Cura, Bambu Studio, etc.)
2. You'll see 2-3 separate objects (water, land, and optionally snow)
3. Assign different colors/materials to each object
4. Slice and print!

### Segment Alignment

Cell boundaries are precisely aligned with segment edges, ensuring adjacent segments fit together perfectly when assembled.

## Data Sources

### ETOPO1 Global Relief Model
- Download from: https://www.ncei.noaa.gov/products/etopo-global-relief-model
- Format: NetCDF (GMT .grd format)
- Resolution: 1 arc-minute

### MODIS Snow Cover (Optional)
- Download from: https://nsidc.org/data/mod10cm
- Format: GeoTIFF
- Use converted GeoTIFF in EPSG:4326 projection

## Architecture

```
globe_generator/
├── config.py              # Configuration dataclasses
├── grid_builder.py        # Equal-area grid generation
├── data_processor.py      # Elevation and snow data processing
├── segment_generator.py   # 48-segment definition
├── mesh_generator.py      # Pure-Python mesh generation using trimesh
├── spherical_geometry.py  # Spherical coordinate and geometry utilities
└── freecad_subprocess.py.backup  # Legacy FreeCAD implementation (archived)
```

**Key Features:**
- **Pure-Python mesh generation**: Direct triangulation using `trimesh` - no external CAD software needed
- **Per-segment cell generation**: Cells are generated with boundaries aligned to segment edges for perfect assembly
- **Vectorized data processing**: 75x faster elevation sampling using NumPy/xarray vectorization
- **Multi-color 3MF export**: Separate objects for water, land, and snow layers
- **Adaptive subdivision**: Shell patches use ~1° per subdivision for smooth surfaces, small cell patches use efficient 4x4 grids

## Performance

**Processing Time (at 0.333333° resolution):**
- Per segment: ~10-12 seconds (pure-Python mesh generation)
- All 48 segments: ~9-10 minutes total
- Data processing: elevation sampling ~2 seconds, cell processing ~5 seconds per segment
- Mesh generation: ~3-5 seconds per segment

**Grid Resolution:**
- Cell size: 0.333333° (~37km at equator, ~20 arc-minutes)
- Typical segment: 8,000-9,000 cells
- High detail capture of elevation features

**Comparison to Previous FreeCAD Implementation:**
- **5-6x faster** per segment at same resolution (10s vs 60s)
- **Much higher detail** possible due to efficient mesh generation
- Previous implementation at this resolution would take hours

**Memory Usage:**
- Python process uses ~500 MB RAM during mesh generation
- Data processing uses minimal memory (~200 MB)
- Total peak usage: < 1 GB (vs 6 GB with FreeCAD)

### 3MF File Size

Each segment 3MF file is typically **10-15 MB** at 0.333333° resolution, depending on terrain complexity.

**Total output size:** ~650 MB for all 48 segments

**Adjusting Grid Resolution:**

Edit `config.yaml` to adjust detail level:
- `step_deg: 0.333333` - High detail, ~37km cells (current)
- `step_deg: 0.5` - Medium detail, ~55km cells, faster generation
- `step_deg: 1.0` - Lower detail, ~110km cells, fastest generation

**Adjusting Shell Smoothness:**

Shell patches automatically use ~1° angular subdivision for professional-quality smooth surfaces. To adjust, edit `globe_generator/mesh_generator.py` line 196-197.

## License

This project is provided as-is for personal and educational use.

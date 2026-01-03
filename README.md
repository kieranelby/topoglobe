# 3D Globe Segment Generator

Generate 3D-printable topographic globe segments from elevation data.

## Overview

This program combines elevation data (ETOPO1) and optional snow coverage data (MODIS) to create 3D models of Earth with raised relief features. The globe is divided into 48 segments that can be 3D printed and assembled.

## Installation

### Prerequisites

**FreeCAD (Required)**

FreeCAD is used as a subprocess to generate 3D geometry. Any installation method works:

**Option 1: Install via Snap (Easiest)**
```bash
sudo snap install freecad
```

**Option 2: Install via APT**
```bash
sudo apt update
sudo apt install freecad
```

**Option 3: Install FreeCAD PPA (Latest stable version)**
```bash
sudo add-apt-repository ppa:freecad-maintainers/freecad-stable
sudo apt update
sudo apt install freecad
```

After installation, verify FreeCAD is accessible:
```bash
freecad --version
```

**Python Dependencies**

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
shell_thickness_mm: 10.0     # Wall thickness of the globe shell

# Grid parameters
step_deg: 1.0                # Grid cell size in degrees

# Output
output_dir: "./output"       # Directory for 3MF files
```

## Usage

### Generate All 48 Segments

```bash
python3 globe.py
```

This will generate all globe segments (without snow) and save them as 3MF files in the output directory. Takes approximately 5-10 minutes for all 48 segments.

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

Segment naming: `{N|S}{lat_min}-{lat_max}_E{lon_min}-{lon_max}`

Examples:
- `N60-90_E000-090` - North pole segment, 0-90° East
- `S30-60_E045-090` - Southern mid-latitude, 45-90° East

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
├── freecad_subprocess.py  # FreeCAD geometry and 3MF export
└── (legacy files for reference)
```

**Key Features:**
- **Per-segment cell generation**: Cells are generated with boundaries aligned to segment edges for perfect assembly
- **Vectorized data processing**: 75x faster elevation sampling using NumPy/xarray vectorization
- **Multi-color 3MF export**: Separate objects for water, land, and snow layers
- **Subprocess architecture**: FreeCAD runs in console mode for reliable batch processing

## Troubleshooting

### "FreeCAD not found" Error

If you get this error, the FreeCAD executable is not in your PATH:

1. Check if FreeCAD is installed:
   ```bash
   which freecad
   freecad --version
   ```

2. If not installed, install via snap (easiest):
   ```bash
   sudo snap install freecad
   ```

3. Or install via APT:
   ```bash
   sudo apt install freecad
   ```

### Performance

**Processing Time:**
- Per segment: ~60 seconds (FreeCAD mesh generation with multiFuse is the bottleneck)
- All 48 segments: ~50-60 minutes total
- Data processing is fast: elevation sampling ~2 seconds, cell processing ~5 seconds
- FreeCAD geometry and mesh generation: ~50-55 seconds per segment

**Memory Usage:**
- FreeCAD process uses ~6 GB RAM (resident) during mesh generation
- Python data processing uses minimal memory (~200 MB)
- Ensure you have adequate RAM available for FreeCAD's geometry kernel

### 3MF File Size

Each segment 3MF file is typically 400-500 KB. Adjust mesh resolution in `globe_generator/freecad_subprocess.py`:
- `LinearDeflection=0.1` - Balance of quality and size (default)
- `LinearDeflection=0.05` - Higher quality, larger files (~1-2 MB)
- `LinearDeflection=0.2` - Lower quality, smaller files (~200-300 KB)

## License

This project is provided as-is for personal and educational use.

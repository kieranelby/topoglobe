# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See `README.md` for project overview, installation, configuration, usage, segment naming, architecture, performance, testing, and assembly instructions.

## Development Commands

### Testing
```bash
# Run only unit tests (fast, no data files required)
venv/bin/python3 -m pytest tests/ -v -m "not integration"

# Run all tests (unit + integration, integration skipped if no data files)
venv/bin/python3 -m pytest tests/ -v

# Generate single test segment
python3 globe.py -s N60-90_E000-090

# Generate all 48 segments (~6-7 minutes)
python3 globe.py

# Generate Bambu Studio-ready 3MF files (~4 minutes)
python3 bambu_3mf.py
```

### Linting
```bash
./lint.sh
# Or individually:
venv/bin/python3 -m ruff check .
venv/bin/python3 -m mypy globe_generator/*.py *.py
```

Configured in `pyproject.toml`: **ruff** (style/quality) and **mypy** (type checking).

## Critical Design Decisions

**Per-Segment Cell Generation**: Cells are generated per-segment (not globally filtered) to ensure cell boundaries align exactly with segment edges. This is critical for adjacent segments to fit together when assembled.

**Vectorized Elevation Sampling**: All cell center coordinates for a segment are passed to `xarray.interp()` in a single call rather than looping. This provides 75x speedup.

**Global Elevation Range**: The min/max elevation is computed once globally and used for all segments. This ensures consistent height scaling so all segments have the same vertical reference frame.

**3MF Object Separation**: Water, land, and snow are exported as separate mesh objects in the 3MF file (not merged into a single compound). This allows slicers to assign different colours.

**Bambu Studio Plate Assignment**: Plate assignment is purely spatial — BambuStudio uses `intersect_instance()` to check which plate's bounding box each object physically intersects. Objects must be offset by `plate_size * 1.2` (307.2mm for 256mm plates) to land on different plates.

## Common Pitfalls

**Snow Flag Logic**: Snow is disabled by default. The flag is `--snow` to enable (not `--no-snow` to disable). Code checks `if not args.snow: config.snow_path = None`.

**Cell Alignment**: When modifying grid generation, ensure cells use segment boundaries as limits (not global 0-360°). Cells must start/end exactly at segment edges for proper assembly.

**Elevation Scaling**: All segments must use the same `global_min_elevation` and `elevation_to_mm` scaling factor. Never compute these per-segment or the vertical heights won't match between segments.

**3MF Object Separation**: When exporting, each layer (water/land/snow) must be a separate mesh object in the 3MF scene. Do not merge into a single compound or they'll be one object in the 3MF.

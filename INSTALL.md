# Installation and Testing Guide

## Step-by-Step Setup

### 1. Install pip (Python package manager)
```bash
sudo apt update
sudo apt install python3-pip
```

### 2. Install Python dependencies
```bash
cd /home/kierane/globe
pip3 install -r requirements.txt
```

Or install them individually:
```bash
pip3 install numpy polars xarray rasterio pyyaml
```

### 3. Install FreeCAD with Python bindings

**Remove snap version (if installed):**
```bash
sudo snap remove freecad
```

**Install from APT:**
```bash
sudo apt update
sudo apt install freecad python3-freecad
```

**Verify FreeCAD Python module:**
```bash
python3 -c "import FreeCAD; print('FreeCAD version:', FreeCAD.Version())"
```

### 4. Test data processing (without FreeCAD)
```bash
cd /home/kierane/globe
python3 test_data_processing.py
```

This will test:
- Loading ETOPO1 elevation data
- Processing grid cells
- Generating segment definitions
- Filtering cells for one segment

### 5. Test full segment generation (with FreeCAD)
```bash
# Generate just one segment for testing
python3 globe.py -s N60-90_E000-090 -v
```

This should create `output/N60-90_E000-090.3mf`

### 6. Generate all 48 segments
```bash
python3 globe.py
```

This will take 10-50 minutes depending on your system.

## Troubleshooting

### "ModuleNotFoundError: No module named 'numpy'"
Install Python dependencies: `pip3 install -r requirements.txt`

### "FreeCAD not found"
Install FreeCAD with Python bindings: `sudo apt install freecad python3-freecad`

### "No such file or directory: ETOPO1_Bed_g_gmt4.grd"
Update the paths in `config.yaml` to point to your data files

### Permission errors with pip
Use: `pip3 install --user -r requirements.txt`

## Verification Commands

```bash
# Check Python version (should be 3.8+)
python3 --version

# Check pip
pip3 --version

# Check if dependencies are installed
python3 -c "import numpy, polars, xarray, rasterio, yaml; print('✓ All packages installed')"

# Check FreeCAD
python3 -c "import FreeCAD; print('✓ FreeCAD version:', FreeCAD.Version())"

# List all segments that will be generated
python3 -c "from globe_generator.segment_generator import generate_segment_definitions; segs = generate_segment_definitions(); [print(s.segment_id) for s in segs]"
```

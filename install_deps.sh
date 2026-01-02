#!/bin/bash
# Installation script for globe generator dependencies

set -e  # Exit on error

echo "=== Globe Generator Dependency Installation ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script needs sudo access."
    echo "You'll be prompted for your password."
    echo ""
fi

# Update package lists
echo "Step 1: Updating package lists..."
sudo apt update

# Install pip3
echo ""
echo "Step 2: Installing pip3..."
sudo apt install -y python3-pip

# Install FreeCAD with Python bindings
echo ""
echo "Step 3: Installing FreeCAD with Python bindings..."

# Remove snap version if it exists
if snap list 2>/dev/null | grep -q freecad; then
    echo "  Removing snap version of FreeCAD..."
    sudo snap remove freecad
fi

# Install from apt
sudo apt install -y freecad python3-freecad

# Verify FreeCAD installation
echo ""
echo "Step 4: Verifying FreeCAD installation..."
if python3 -c "import FreeCAD" 2>/dev/null; then
    python3 -c "import FreeCAD; print('✓ FreeCAD installed:', FreeCAD.Version())"
else
    echo "⚠ FreeCAD Python module not found. Trying alternative installation..."
    # Try with PPA
    sudo add-apt-repository -y ppa:freecad-maintainers/freecad-stable
    sudo apt update
    sudo apt install -y freecad python3-freecad
fi

# Install Python dependencies
echo ""
echo "Step 5: Installing Python dependencies..."
cd /home/kierane/globe
pip3 install --user -r requirements.txt

# Verify installations
echo ""
echo "Step 6: Verifying all dependencies..."
python3 -c "import numpy; print('✓ numpy installed')"
python3 -c "import polars; print('✓ polars installed')"
python3 -c "import xarray; print('✓ xarray installed')"
python3 -c "import rasterio; print('✓ rasterio installed')"
python3 -c "import yaml; print('✓ pyyaml installed')"
python3 -c "import FreeCAD; print('✓ FreeCAD installed')"

echo ""
echo "=== Installation Complete! ==="
echo ""
echo "You can now test the program:"
echo "  python3 test_data_processing.py    # Test data processing"
echo "  python3 globe.py -s N60-90_E000-090 -v   # Generate one segment"
echo "  python3 globe.py                    # Generate all 48 segments"

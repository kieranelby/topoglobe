"""FreeCAD subprocess wrapper for using snap-installed FreeCAD."""

import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Optional

import polars as pl
from .config import GlobeConfig, SegmentDefinition


logger = logging.getLogger(__name__)


def generate_freecad_script(
    cells_df: pl.DataFrame,
    segment: SegmentDefinition,
    config: GlobeConfig,
    output_path: Path
) -> str:
    """
    Generate a FreeCAD Python script that creates the geometry.

    This script will be executed by FreeCAD in console mode.
    """
    # Convert DataFrame to Python list for embedding in script
    # Replace NaN values with 0.0 to avoid "name 'nan' is not defined" errors
    import math
    cells_data = []
    for row in cells_df.iter_rows(named=True):
        cells_data.append({
            'water_height_mm': float(row['water_height_mm']) if not math.isnan(row['water_height_mm']) else 0.0,
            'land_height_mm': float(row['land_height_mm']) if not math.isnan(row['land_height_mm']) else 0.0,
            'snow_height_mm': float(row['snow_height_mm']) if not math.isnan(row['snow_height_mm']) else 0.0,
            'lat_a_deg': float(row['lat_a_deg']),
            'lat_b_deg': float(row['lat_b_deg']),
            'lng_a_deg': float(row['lng_a_deg']),
            'lng_b_deg': float(row['lng_b_deg']),
        })

    script = f'''
import FreeCAD as App
import Part
import Mesh
import MeshPart
import math

# Configuration
hollow_radius_mm = {config.hollow_radius_mm}
core_radius_mm = {config.core_radius_mm}
segment_lat_min = {segment.lat_min}
segment_lat_max = {segment.lat_max}
segment_lon_min = {segment.lon_min}
segment_lon_max = {segment.lon_max}
output_path = "{output_path}"

# Cell data
cells = {cells_data!r}

def make_sphere_patch(r, t, lat1, lat2, lon1, lon2):
    """Create a spherical shell patch."""
    lat_lo = min(lat1, lat2)
    lat_hi = max(lat1, lat2)

    theta_lo = math.radians(90.0 - lat_hi)
    theta_hi = math.radians(90.0 - lat_lo)

    r_outer = float(r) + float(t)
    r_inner = float(r)

    def v(x, y, z):
        return App.Vector(x, y, z)

    mid_theta = 0.5 * (theta_lo + theta_hi)

    po1 = v(r_outer * math.sin(theta_lo), 0.0, r_outer * math.cos(theta_lo))
    po2 = v(r_outer * math.sin(theta_hi), 0.0, r_outer * math.cos(theta_hi))
    pom = v(r_outer * math.sin(mid_theta), 0.0, r_outer * math.cos(mid_theta))

    pi1 = v(r_inner * math.sin(theta_lo), 0.0, r_inner * math.cos(theta_lo))
    pi2 = v(r_inner * math.sin(theta_hi), 0.0, r_inner * math.cos(theta_hi))
    pim = v(r_inner * math.sin(mid_theta), 0.0, r_inner * math.cos(mid_theta))

    outer_arc = Part.Arc(po1, pom, po2).toShape()
    inner_arc = Part.Arc(pi2, pim, pi1).toShape()

    edge1 = Part.LineSegment(po1, pi1).toShape()
    edge2 = Part.LineSegment(pi2, po2).toShape()

    wire = Part.Wire([outer_arc, edge2, inner_arc, edge1])
    face = Part.Face(wire)

    lon_span = float(lon2 - lon1)
    solid = face.revolve(App.Vector(0, 0, 0), App.Vector(0, 0, 1), lon_span)

    rot = App.Rotation(App.Vector(0, 0, 1), lon1)
    solid.Placement = App.Placement(App.Vector(0, 0, 0), rot)

    return solid

# Create document
doc = App.newDocument("GlobeSegment")

# Create hollow core
core = make_sphere_patch(
    hollow_radius_mm,
    core_radius_mm - hollow_radius_mm,
    segment_lat_min,
    segment_lat_max,
    segment_lon_min,
    segment_lon_max
)

water_shapes = [core]
land_shapes = []
snow_shapes = []

# Process cells
for cell in cells:
    water_height_mm = cell['water_height_mm']
    lat1 = cell['lat_a_deg']
    lat2 = cell['lat_b_deg']
    lon1 = cell['lng_a_deg']
    lon2 = cell['lng_b_deg']

    if lat2 <= segment_lat_min or lat1 >= segment_lat_max:
        continue
    if lon2 <= segment_lon_min or lon1 >= segment_lon_max:
        continue

    if water_height_mm > 0:
        wsp = make_sphere_patch(core_radius_mm, water_height_mm, lat1, lat2, lon1, lon2)
        water_shapes.append(wsp)

        land_height_mm = cell['land_height_mm']
        if land_height_mm > 0:
            lsp = make_sphere_patch(core_radius_mm + water_height_mm, land_height_mm, lat1, lat2, lon1, lon2)
            land_shapes.append(lsp)

        snow_height_mm = cell['snow_height_mm']
        if snow_height_mm > 0:
            ssp = make_sphere_patch(core_radius_mm + water_height_mm, snow_height_mm, lat1, lat2, lon1, lon2)
            snow_shapes.append(ssp)

# Fuse shapes into single solids (avoids non-manifold edges)
if water_shapes:
    if len(water_shapes) == 1:
        water_solid = water_shapes[0]
    else:
        water_solid = water_shapes[0].multiFuse(water_shapes[1:])
    water_obj = doc.addObject("Part::Feature", "water")
    water_obj.Shape = water_solid

if land_shapes:
    if len(land_shapes) == 1:
        land_solid = land_shapes[0]
    else:
        land_solid = land_shapes[0].multiFuse(land_shapes[1:])
    land_obj = doc.addObject("Part::Feature", "land")
    land_obj.Shape = land_solid

if snow_shapes:
    if len(snow_shapes) == 1:
        snow_solid = snow_shapes[0]
    else:
        snow_solid = snow_shapes[0].multiFuse(snow_shapes[1:])
    snow_obj = doc.addObject("Part::Feature", "snow")
    snow_obj.Shape = snow_solid

doc.recompute()

# Rotate segment to position as if at north pole (lat=90°)
lat_center = (segment_lat_min + segment_lat_max) / 2.0
lon_center = (segment_lon_min + segment_lon_max) / 2.0

# Calculate the 3D direction vector for the segment center
lat_rad = math.radians(lat_center)
lon_rad = math.radians(lon_center)
from_vec = App.Vector(
    math.cos(lat_rad) * math.cos(lon_rad),
    math.cos(lat_rad) * math.sin(lon_rad),
    math.sin(lat_rad)
)
to_vec = App.Vector(0, 0, 1)  # North pole direction

# Single rotation to align segment center with north pole
rotation = App.Rotation(from_vec, to_vec)

# Apply rotation to all objects
for obj in doc.Objects:
    if hasattr(obj, 'Shape') and obj.Name in ['water', 'land', 'snow']:
        if obj.Shape.Volume > 0:
            obj.Placement = App.Placement(App.Vector(0, 0, 0), rotation)

doc.recompute()

# Convert each Part object to a Mesh for multi-color 3MF export
mesh_objects_list = []

for obj in doc.Objects:
    if hasattr(obj, 'Shape') and obj.Name in ['water', 'land', 'snow']:
        if obj.Shape.Volume > 0:
            # Create mesh from Part shape
            mesh = MeshPart.meshFromShape(
                Shape=obj.Shape,
                LinearDeflection=0.1,
                AngularDeflection=0.523599,
                Relative=False
            )
            # Create a Mesh::Feature to hold the mesh
            mesh_obj = doc.addObject("Mesh::Feature", obj.Name)
            mesh_obj.Mesh = mesh
            mesh_obj.Label = obj.Name
            mesh_objects_list.append(mesh_obj)

if mesh_objects_list:
    doc.recompute()
    # Export using Mesh module - this should preserve separate objects in 3MF
    import Mesh as MeshModule
    MeshModule.export(mesh_objects_list, output_path)
    print(f"EXPORT_SUCCESS: {{output_path}}")
else:
    print("ERROR: No shapes to export")

App.closeDocument(doc.Name)

# Explicitly exit FreeCAD
import sys
sys.exit(0)
'''
    return script


def generate_segment_with_subprocess(
    cells_df: pl.DataFrame,
    segment: SegmentDefinition,
    config: GlobeConfig,
    output_path: Path
) -> bool:
    """
    Generate a segment using FreeCAD in console mode.

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Generating {segment.segment_id} using FreeCAD subprocess...")

    # Generate FreeCAD script
    script = generate_freecad_script(cells_df, segment, config, output_path)

    # Write script to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        script_path = f.name
        f.write(script)

    try:
        # Remove any existing output file to ensure we detect fresh output
        if output_path.exists():
            output_path.unlink()

        # Run FreeCAD in console mode
        cmd = ['freecad', '--console', script_path]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        # Check for success by verifying the output file was created
        if output_path.exists() and output_path.stat().st_size > 0:
            logger.info(f"Successfully exported {output_path}")
            return True
        else:
            logger.error(f"FreeCAD execution failed - output file not created or empty")
            if result.stderr:
                logger.error(f"Error: {result.stderr}")
            if result.stdout:
                logger.debug(f"Output: {result.stdout}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"FreeCAD execution timed out")
        # Even if it timed out, check if file was written
        if output_path.exists() and output_path.stat().st_size > 0:
            logger.warning(f"Timeout occurred but file was created successfully: {output_path}")
            return True
        return False
    except FileNotFoundError:
        logger.error("FreeCAD executable not found. Is it installed?")
        return False
    except Exception as e:
        logger.error(f"Error running FreeCAD: {e}")
        return False
    finally:
        # Clean up temporary script
        Path(script_path).unlink(missing_ok=True)

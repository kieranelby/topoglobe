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
shell_thickness_mm = {config.shell_thickness_mm}
tab_size_degrees = {config.tab_size_degrees}
clearance_mm = {config.clearance_mm}
segment_lat_min = {segment.lat_min}
segment_lat_max = {segment.lat_max}
segment_lon_min = {segment.lon_min}
segment_lon_max = {segment.lon_max}
output_path = "{output_path}"

# Calculate clearance in degrees
clearance_degrees = (clearance_mm / hollow_radius_mm) * (180.0 / math.pi)
cutout_size_degrees = tab_size_degrees + 2.0 * clearance_degrees

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

# Calculate dual cutout regions on western edge (lowest longitude)
# Position cutouts at 1/3 and 2/3 of segment height
# Longitude span is adjusted for latitude to match tab dimensions
segment_lat_range = segment_lat_max - segment_lat_min

# Lower cutout (at 1/3 height)
cutout_lower_lat_center = segment_lat_min + (segment_lat_range / 3.0)
cutout_lower_lat_min = cutout_lower_lat_center - (cutout_size_degrees / 2.0)
cutout_lower_lat_max = cutout_lower_lat_center + (cutout_size_degrees / 2.0)

# Adjust longitude span to match latitude-adjusted tabs
cutout_lower_lon_span = cutout_size_degrees / max(0.1, math.cos(math.radians(cutout_lower_lat_center)))
cutout_lower_lon_min = segment_lon_min
cutout_lower_lon_max = segment_lon_min + cutout_lower_lon_span

# Upper cutout (at 2/3 height)
cutout_upper_lat_center = segment_lat_min + (2.0 * segment_lat_range / 3.0)
cutout_upper_lat_min = cutout_upper_lat_center - (cutout_size_degrees / 2.0)
cutout_upper_lat_max = cutout_upper_lat_center + (cutout_size_degrees / 2.0)

# Adjust longitude span for this cutout's latitude
cutout_upper_lon_span = cutout_size_degrees / max(0.1, math.cos(math.radians(cutout_upper_lat_center)))
cutout_upper_lon_min = segment_lon_min
cutout_upper_lon_max = segment_lon_min + cutout_upper_lon_span

# Create full-thickness shell patches with cutouts for tabs
# South patch (below lower cutout)
shell_south = make_sphere_patch(
    hollow_radius_mm,
    shell_thickness_mm,
    segment_lat_min,
    cutout_lower_lat_min,
    segment_lon_min,
    segment_lon_max
)

# Center patch (between two cutouts)
shell_center = make_sphere_patch(
    hollow_radius_mm,
    shell_thickness_mm,
    cutout_lower_lat_max,
    cutout_upper_lat_min,
    segment_lon_min,
    segment_lon_max
)

# North patch (above upper cutout)
shell_north = make_sphere_patch(
    hollow_radius_mm,
    shell_thickness_mm,
    cutout_upper_lat_max,
    segment_lat_max,
    segment_lon_min,
    segment_lon_max
)

# East-lower patch (right of lower cutout)
shell_east_lower = make_sphere_patch(
    hollow_radius_mm,
    shell_thickness_mm,
    cutout_lower_lat_min,
    cutout_lower_lat_max,
    cutout_lower_lon_max,
    segment_lon_max
)

# East-upper patch (right of upper cutout)
shell_east_upper = make_sphere_patch(
    hollow_radius_mm,
    shell_thickness_mm,
    cutout_upper_lat_min,
    cutout_upper_lat_max,
    cutout_upper_lon_max,
    segment_lon_max
)

water_shapes = [shell_south, shell_center, shell_north, shell_east_lower, shell_east_upper]
land_shapes = []
snow_shapes = []

# Create dual tabs on eastern edge (highest longitude)
# Tabs start at hollow_radius_mm and extend full shell thickness
# Longitude span is adjusted for latitude to maintain physical aspect ratio

# Lower tab (at 1/3 height)
tab_lower_lat_center = segment_lat_min + (segment_lat_range / 3.0)
tab_lower_lat_min = tab_lower_lat_center - (tab_size_degrees / 2.0)
tab_lower_lat_max = tab_lower_lat_center + (tab_size_degrees / 2.0)

# Adjust longitude span to compensate for latitude convergence
# At high latitudes, longitude degrees are physically shorter, so extend further
tab_lower_lon_span = tab_size_degrees / max(0.1, math.cos(math.radians(tab_lower_lat_center)))
tab_lower_lon_min = segment_lon_max
tab_lower_lon_max = segment_lon_max + tab_lower_lon_span

tab_lower = make_sphere_patch(
    hollow_radius_mm,
    shell_thickness_mm,
    tab_lower_lat_min,
    tab_lower_lat_max,
    tab_lower_lon_min,
    tab_lower_lon_max
)
water_shapes.append(tab_lower)

# Upper tab (at 2/3 height)
tab_upper_lat_center = segment_lat_min + (2.0 * segment_lat_range / 3.0)
tab_upper_lat_min = tab_upper_lat_center - (tab_size_degrees / 2.0)
tab_upper_lat_max = tab_upper_lat_center + (tab_size_degrees / 2.0)

# Adjust longitude span for this tab's latitude
tab_upper_lon_span = tab_size_degrees / max(0.1, math.cos(math.radians(tab_upper_lat_center)))
tab_upper_lon_min = segment_lon_max
tab_upper_lon_max = segment_lon_max + tab_upper_lon_span

tab_upper = make_sphere_patch(
    hollow_radius_mm,
    shell_thickness_mm,
    tab_upper_lat_min,
    tab_upper_lat_max,
    tab_upper_lon_min,
    tab_upper_lon_max
)
water_shapes.append(tab_upper)

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

# Print shape counts for debugging
import sys
sys.stderr.write(f"Shape counts - Water: {{len(water_shapes)}}, Land: {{len(land_shapes)}}, Snow: {{len(snow_shapes)}}\\n")
sys.stderr.flush()

# Fuse shapes into single solids (avoids non-manifold edges)
# Note: Even single shapes are fused with a copy of themselves to ensure
# consistent behavior with rotation. Single unfused shapes retain individual
# Placements which interfere with the global rotation applied later.
if water_shapes:
    if len(water_shapes) == 1:
        water_solid = water_shapes[0].multiFuse([water_shapes[0].copy()])
    else:
        water_solid = water_shapes[0].multiFuse(water_shapes[1:])
    water_obj = doc.addObject("Part::Feature", "water")
    water_obj.Shape = water_solid

if land_shapes:
    if len(land_shapes) == 1:
        land_solid = land_shapes[0].multiFuse([land_shapes[0].copy()])
    else:
        land_solid = land_shapes[0].multiFuse(land_shapes[1:])
    land_obj = doc.addObject("Part::Feature", "land")
    land_obj.Shape = land_solid

if snow_shapes:
    if len(snow_shapes) == 1:
        snow_solid = snow_shapes[0].multiFuse([snow_shapes[0].copy()])
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
            if result.stderr:
                logger.debug(f"FreeCAD stderr: {result.stderr}")
            if result.stdout:
                logger.debug(f"FreeCAD stdout: {result.stdout}")
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

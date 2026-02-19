#!/usr/bin/env python3
"""Convert trimesh-generated segment 3MF files into Bambu Studio-compatible 3MF.

Reads individual segment 3MF files from output/ and produces hemisphere 3MF files
in 3mf/ with proper multi-color extruder assignments, plate layouts, and all
metadata files that Bambu Studio expects.

Usage:
    python3 bambu_3mf.py                        # Process all segments
    python3 bambu_3mf.py --hemisphere north      # Only northern hemisphere
    python3 bambu_3mf.py --input-dir output --output-dir 3mf
"""

import argparse
import json
import logging
import math
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

logger = logging.getLogger(__name__)

# Bambu Studio version to declare in metadata
BAMBU_VERSION = "02.04.00.70"

# Build plate size (mm) for Bambu X1C/P1S
PLATE_WIDTH = 256.0
PLATE_DEPTH = 256.0
PLATE_SPACING = 10.0  # mm gap between objects on plate

# Bambu Studio plate layout: stride = size * (1 + LOGICAL_PART_PLATE_GAP)
# where LOGICAL_PART_PLATE_GAP = 1/5 (from BambuStudio PartPlate.cpp)
PLATE_STRIDE_X = PLATE_WIDTH * 1.2
PLATE_STRIDE_Y = PLATE_DEPTH * 1.2

# Snap-fit clip settings
CLIP_STL_PATH = Path("snapfits/connector1-slim-model_files/clip-slim-00-clearance-r2.stl")
CLIP_SCALE = 0.75
CLIPS_PER_PLATE = 24


@dataclass
class SegmentMeshes:
    """Meshes extracted from a single segment 3MF file."""

    segment_id: str
    water: trimesh.Trimesh | None = None
    land: trimesh.Trimesh | None = None
    snow: trimesh.Trimesh | None = None


@dataclass
class PlateSegment:
    """A segment positioned on a build plate."""

    segment: SegmentMeshes
    # Object file index (1-based, for object_N.model)
    object_file_idx: int
    # Top-level assembly object ID in main model
    assembly_object_id: int
    # Sub-object IDs inside the object file (water, land, snow)
    part_ids: list[tuple[int, str, str]] = field(default_factory=list)
    # Position on build plate (translation in mm)
    plate_x: float = 0.0
    plate_y: float = 0.0
    plate_z: float = 0.0


def load_segment_meshes(input_dir: Path, segment_id: str) -> SegmentMeshes | None:
    """Load meshes from a trimesh-generated segment 3MF file."""
    path = input_dir / f"{segment_id}.3mf"
    if not path.exists():
        logger.warning(f"Missing segment file: {path}")
        return None

    scene = trimesh.load(str(path))
    result = SegmentMeshes(segment_id=segment_id)

    if isinstance(scene, trimesh.Scene):
        for name, geom in scene.geometry.items():
            if name.endswith("_water"):
                result.water = geom
            elif name.endswith("_land"):
                result.land = geom
            elif name.endswith("_snow"):
                result.snow = geom
    elif isinstance(scene, trimesh.Trimesh):
        result.water = scene

    return result


def get_hemisphere_segments(hemisphere: str) -> list[str]:
    """Get ordered segment IDs for a hemisphere, grouped by plate.

    Plate grouping (6 segments each):
      Plate 1: equatorial east (0-30 lat, E000-E180)
      Plate 2: equatorial west (0-30 lat, W180-W000)
      Plate 3: 6 of 8 mid-latitude segments (30-60 lat, W090 through E180)
      Plate 4: 2 remaining mid-lat (W180 to W090) + 4 polar (60-90 lat)
    """
    if hemisphere == "north":
        equatorial_east = [
            "N00-30_E000-030", "N00-30_E030-060", "N00-30_E060-090",
            "N00-30_E090-120", "N00-30_E120-150", "N00-30_E150-180",
        ]
        equatorial_west = [
            "N00-30_W030-000", "N00-30_W060-030", "N00-30_W090-060",
            "N00-30_W120-090", "N00-30_W150-120", "N00-30_W180-150",
        ]
        mid_lat_plate3 = [
            "N30-60_E000-045", "N30-60_E045-090", "N30-60_E090-135",
            "N30-60_E135-180", "N30-60_W045-000", "N30-60_W090-045",
        ]
        mid_lat_plate4 = [
            "N30-60_W135-090", "N30-60_W180-135",
        ]
        polar = [
            "N60-90_E000-090", "N60-90_E090-180",
            "N60-90_W090-000", "N60-90_W180-090",
        ]
    else:
        equatorial_east = [
            "S30-00_E000-030", "S30-00_E030-060", "S30-00_E060-090",
            "S30-00_E090-120", "S30-00_E120-150", "S30-00_E150-180",
        ]
        equatorial_west = [
            "S30-00_W030-000", "S30-00_W060-030", "S30-00_W090-060",
            "S30-00_W120-090", "S30-00_W150-120", "S30-00_W180-150",
        ]
        mid_lat_plate3 = [
            "S60-30_E000-045", "S60-30_E045-090", "S60-30_E090-135",
            "S60-30_E135-180", "S60-30_W045-000", "S60-30_W090-045",
        ]
        mid_lat_plate4 = [
            "S60-30_W135-090", "S60-30_W180-135",
        ]
        polar = [
            "S90-60_E000-090", "S90-60_E090-180",
            "S90-60_W090-000", "S90-60_W180-090",
        ]

    return equatorial_east + equatorial_west + mid_lat_plate3 + mid_lat_plate4 + polar


def compute_plate_layout(segments: list[SegmentMeshes]) -> list[tuple[float, float, float]]:
    """Compute positions for segments on a build plate.

    Arranges segments in a 2x3 grid centered on the plate.
    Returns list of (x, y, z_offset) positions.
    """
    # Get bounding boxes of all segment meshes
    bboxes = []
    for seg in segments:
        all_meshes = []
        if seg.water is not None:
            all_meshes.append(seg.water)
        if seg.land is not None:
            all_meshes.append(seg.land)
        if seg.snow is not None:
            all_meshes.append(seg.snow)
        if all_meshes:
            combined = trimesh.util.concatenate(all_meshes)
            bboxes.append(combined.bounds)  # [[min_x,min_y,min_z],[max_x,max_y,max_z]]
        else:
            bboxes.append(np.array([[0, 0, 0], [10, 10, 10]]))

    # Compute sizes
    sizes = [(b[1] - b[0]) for b in bboxes]

    n = len(segments)
    if n <= 3:
        cols, rows = n, 1
    elif n <= 6:
        cols, rows = 3, 2
    else:
        # Wider-than-tall grid for larger counts (e.g. 6x4 for 24 clips)
        cols = round(math.sqrt(n * 1.5))
        rows = math.ceil(n / cols)

    # Calculate column widths and row heights
    col_widths = []
    row_heights = []
    for c in range(cols):
        max_w = 0.0
        for r in range(rows):
            idx = r * cols + c
            if idx < n:
                max_w = max(max_w, sizes[idx][0])
        col_widths.append(max_w)

    for r in range(rows):
        max_h = 0.0
        for c in range(cols):
            idx = r * cols + c
            if idx < n:
                max_h = max(max_h, sizes[idx][1])
        row_heights.append(max_h)

    total_w = sum(col_widths) + PLATE_SPACING * (cols - 1)
    total_h = sum(row_heights) + PLATE_SPACING * (rows - 1)

    # Center the grid on the plate
    start_x = (PLATE_WIDTH - total_w) / 2.0
    start_y = (PLATE_DEPTH - total_h) / 2.0

    positions = []
    for i in range(n):
        r = i // cols
        c = i % cols

        # Cumulative position
        x_offset = start_x + sum(col_widths[:c]) + PLATE_SPACING * c
        y_offset = start_y + sum(row_heights[:r]) + PLATE_SPACING * r

        # Center within cell
        cell_cx = x_offset + col_widths[c] / 2.0
        cell_cy = y_offset + row_heights[r] / 2.0

        # Place segment center at cell center
        seg_cx = (bboxes[i][0][0] + bboxes[i][1][0]) / 2.0
        seg_cy = (bboxes[i][0][1] + bboxes[i][1][1]) / 2.0

        px = cell_cx - seg_cx
        py = cell_cy - seg_cy
        # Z offset: lift so bottom is at z=0
        pz = -bboxes[i][0][2]

        positions.append((px, py, pz))

    return positions


def make_uuid() -> str:
    return str(uuid.uuid4())


def build_object_model_xml(segment: SegmentMeshes, part_id_start: int) -> tuple[str, list[tuple[int, str, str]]]:
    """Build XML for a 3D/Objects/object_N.model file.

    Returns:
        Tuple of (xml_string, list of (part_id, part_uuid, part_type))
        where part_type is 'water', 'land', or 'snow'.
    """
    parts: list[tuple[int, str, str]] = []
    current_id = part_id_start

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append(
        '<model unit="millimeter" xml:lang="en-US"'
        ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
        ' xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"'
        ' xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
        ' requiredextensions="p">'
    )
    lines.append(' <metadata name="BambuStudio:3mfVersion">1</metadata>')
    lines.append(' <resources>')

    for mesh, mesh_type in [
        (segment.water, "water"),
        (segment.land, "land"),
        (segment.snow, "snow"),
    ]:
        if mesh is None or len(mesh.vertices) == 0:
            continue
        part_uuid = make_uuid()
        lines.append(f'  <object id="{current_id}" p:UUID="{part_uuid}" type="model">')
        lines.append('   <mesh>')
        lines.append('    <vertices>')
        for v in mesh.vertices:
            lines.append(f'     <vertex x="{v[0]:.6g}" y="{v[1]:.6g}" z="{v[2]:.6g}"/>')
        lines.append('    </vertices>')
        lines.append('    <triangles>')
        for f in mesh.faces:
            lines.append(f'     <triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>')
        lines.append('    </triangles>')
        lines.append('   </mesh>')
        lines.append('  </object>')

        parts.append((current_id, part_uuid, mesh_type))
        current_id += 1

    lines.append(' </resources>')
    lines.append(' <build/>')
    lines.append('</model>')

    return '\n'.join(lines), parts


def build_main_model_xml(
    plates: list[list[PlateSegment]],
) -> str:
    """Build the main 3D/3dmodel.model XML."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append(
        '<model unit="millimeter" xml:lang="en-US"'
        ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
        ' xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"'
        ' xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
        ' requiredextensions="p">'
    )

    # Metadata
    lines.append(f' <metadata name="Application">BambuStudio-{BAMBU_VERSION}</metadata>')
    lines.append(' <metadata name="BambuStudio:3mfVersion">1</metadata>')
    lines.append(' <metadata name="Copyright"></metadata>')
    lines.append(' <metadata name="CreationDate">2026-02-19</metadata>')
    lines.append(' <metadata name="Description"></metadata>')
    lines.append(' <metadata name="Designer"></metadata>')
    lines.append(' <metadata name="DesignerCover"></metadata>')
    lines.append(' <metadata name="DesignerUserId"></metadata>')
    lines.append(' <metadata name="License"></metadata>')
    lines.append(' <metadata name="ModificationDate">2026-02-19</metadata>')
    lines.append(' <metadata name="Origin"></metadata>')
    lines.append(' <metadata name="Title"></metadata>')

    # Resources
    lines.append(' <resources>')

    for plate in plates:
        for ps in plate:
            obj_uuid = make_uuid()
            lines.append(f'  <object id="{ps.assembly_object_id}" p:UUID="{obj_uuid}" type="model">')
            lines.append('   <components>')
            for part_id, part_uuid, _ in ps.part_ids:
                lines.append(
                    f'    <component p:path="/3D/Objects/object_{ps.object_file_idx}.model"'
                    f' objectid="{part_id}" p:UUID="{part_uuid}"'
                    f' transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
                )
            lines.append('   </components>')
            lines.append('  </object>')

    lines.append(' </resources>')

    # Build
    build_uuid = make_uuid()
    lines.append(f' <build p:UUID="{build_uuid}">')

    for plate in plates:
        for ps in plate:
            item_uuid = make_uuid()
            tx = ps.plate_x
            ty = ps.plate_y
            tz = ps.plate_z
            lines.append(
                f'  <item objectid="{ps.assembly_object_id}" p:UUID="{item_uuid}"'
                f' transform="1 0 0 0 1 0 0 0 1 {tx:.6g} {ty:.6g} {tz:.6g}"'
                f' printable="1"/>'
            )

    lines.append(' </build>')
    lines.append('</model>')

    return '\n'.join(lines)


def build_model_settings_config(
    plates: list[list[PlateSegment]],
) -> str:
    """Build Metadata/model_settings.config XML."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<config>')

    # Object entries with part extruder assignments
    for plate in plates:
        for ps in plate:
            seg = ps.segment
            # Count total faces across all parts
            total_faces = 0
            for mesh, _ in [(seg.water, "water"), (seg.land, "land"), (seg.snow, "snow")]:
                if mesh is not None:
                    total_faces += len(mesh.faces)

            lines.append(f'  <object id="{ps.assembly_object_id}">')
            lines.append(f'    <metadata key="name" value="{seg.segment_id}"/>')
            lines.append('    <metadata key="extruder" value="1"/>')
            lines.append(f'    <metadata face_count="{total_faces}"/>')

            for part_id, _part_uuid, part_type in ps.part_ids:
                # Extruder: 1=water, 2=land, 3=snow
                if part_type == "water":
                    extruder = "1"
                elif part_type == "land":
                    extruder = "2"
                else:
                    extruder = "3"

                mesh = getattr(seg, part_type)
                face_count = len(mesh.faces) if mesh is not None else 0

                lines.append(f'    <part id="{part_id}" subtype="normal_part">')
                lines.append(f'      <metadata key="name" value="{seg.segment_id}_{part_type}"/>')
                lines.append('      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>')
                lines.append(f'      <metadata key="source_file" value="{seg.segment_id}.3mf"/>')
                lines.append('      <metadata key="source_object_id" value="0"/>')
                lines.append('      <metadata key="source_volume_id" value="0"/>')
                lines.append('      <metadata key="source_offset_x" value="0"/>')
                lines.append('      <metadata key="source_offset_y" value="0"/>')
                lines.append('      <metadata key="source_offset_z" value="0"/>')
                lines.append(f'      <metadata key="extruder" value="{extruder}"/>')
                lines.append(
                    f'      <mesh_stat face_count="{face_count}"'
                    f' edges_fixed="0" degenerate_facets="0" facets_removed="0"'
                    f' facets_reversed="0" backwards_edges="0"/>'
                )
                lines.append('    </part>')

            lines.append('  </object>')

    # Plate definitions
    for plate_idx, plate in enumerate(plates, 1):
        lines.append('  <plate>')
        lines.append(f'    <metadata key="plater_id" value="{plate_idx}"/>')
        lines.append('    <metadata key="plater_name" value=""/>')
        lines.append('    <metadata key="locked" value="false"/>')
        lines.append('    <metadata key="filament_map_mode" value="Auto For Flush"/>')
        lines.append('    <metadata key="filament_maps" value="1 1"/>')
        lines.append('    <metadata key="filament_volume_maps" value="0 0"/>')

        for ps in plate:
            lines.append('    <model_instance>')
            lines.append(f'      <metadata key="object_id" value="{ps.assembly_object_id}"/>')
            lines.append('      <metadata key="instance_id" value="0"/>')
            lines.append('      <metadata key="identify_id" value="0"/>')
            lines.append('    </model_instance>')

        lines.append('  </plate>')

    # Assemble section
    lines.append('  <assemble>')
    for plate in plates:
        for ps in plate:
            lines.append(
                f'   <assemble_item object_id="{ps.assembly_object_id}"'
                f' instance_id="0"'
                f' transform="1 0 0 0 1 0 0 0 1 0 0 {ps.plate_z:.6g}"'
                f' offset="0 0 0" />'
            )
    lines.append('  </assemble>')

    lines.append('</config>')
    return '\n'.join(lines)


def build_content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        '</Types>'
    )


def build_root_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        ' <Relationship Target="/3D/3dmodel.model" Id="rel-1"'
        ' Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        '</Relationships>'
    )


def build_model_rels(object_file_indices: list[int]) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">')
    for i, idx in enumerate(object_file_indices, 1):
        lines.append(
            f' <Relationship Target="/3D/Objects/object_{idx}.model" Id="rel-{i}"'
            f' Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        )
    lines.append('</Relationships>')
    return '\n'.join(lines)


def build_slice_info_config() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<config>\n'
        '  <header>\n'
        f'    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
        f'    <header_item key="X-BBL-Client-Version" value="{BAMBU_VERSION}"/>\n'
        '  </header>\n'
        '</config>'
    )


def build_cut_information_xml(object_file_indices: list[int]) -> str:
    lines = ['<?xml version="1.0" encoding="utf-8"?>']
    lines.append('<objects>')
    for idx in object_file_indices:
        lines.append(f' <object id="{idx}">')
        lines.append('  <cut_id id="0" check_sum="1" connectors_cnt="0"/>')
        lines.append(' </object>')
    lines.append('</objects>')
    return '\n'.join(lines)


def build_filament_sequence_json(num_plates: int) -> str:
    data: dict[str, dict[str, list[str]]] = {}
    for i in range(1, num_plates + 1):
        data[f"plate_{i}"] = {"sequence": []}
    return json.dumps(data)


def load_template_settings(template_3mf: Path) -> dict[str, str]:
    """Extract slicer settings from a template 3MF file.

    Reads project_settings.config and slice_info.config from the template,
    which contain filament colours, support settings, print profile, etc.

    Args:
        template_3mf: Path to template 3MF (e.g. 3mf/settings.3mf)

    Returns:
        Dict mapping archive entry names to their content strings.
    """
    settings: dict[str, str] = {}
    if not template_3mf.exists():
        logger.warning(f"Template 3MF not found: {template_3mf}")
        return settings
    try:
        with zipfile.ZipFile(template_3mf, 'r') as zf:
            for name in [
                "Metadata/project_settings.config",
                "Metadata/slice_info.config",
            ]:
                if name in zf.namelist():
                    settings[name] = zf.read(name).decode("utf-8")
    except zipfile.BadZipFile:
        logger.warning(f"Invalid ZIP file: {template_3mf}")
    return settings


def generate_bambu_3mf(
    hemisphere: str,
    input_dir: Path,
    output_dir: Path,
    template_3mf: Path | None = None,
) -> Path:
    """Generate a Bambu Studio-compatible 3MF for one hemisphere.

    Args:
        hemisphere: 'north' or 'south'
        input_dir: Directory containing trimesh-generated segment 3MF files
        output_dir: Directory for output Bambu 3MF files
        template_3mf: Path to template 3MF for slicer settings (default: 3mf/settings.3mf)

    Returns:
        Path to the generated 3MF file
    """
    segment_ids = get_hemisphere_segments(hemisphere)

    # Load all segment meshes
    logger.info(f"Loading {len(segment_ids)} segments for {hemisphere} hemisphere...")
    segments: list[SegmentMeshes] = []
    for sid in segment_ids:
        seg = load_segment_meshes(input_dir, sid)
        if seg is None:
            logger.error(f"Could not load segment {sid}, skipping")
            continue
        segments.append(seg)

    if not segments:
        raise RuntimeError(f"No segments loaded for {hemisphere} hemisphere")

    # Group into 4 plates of 6
    plates_segments: list[list[SegmentMeshes]] = []
    for i in range(0, len(segments), 6):
        plates_segments.append(segments[i:i + 6])

    # Assign IDs and compute positions
    # All IDs (part + assembly) share a single global namespace to avoid
    # collisions that confuse Bambu Studio. Pattern matches reference:
    # parts allocated first, then assembly ID, e.g. parts 1,2 -> assembly 3.
    next_object_file_idx = 1
    next_id = 1  # Single counter for both part and assembly IDs

    plates: list[list[PlateSegment]] = []

    # Check if clip plate should be added
    has_clips = CLIP_STL_PATH.exists()

    # Bambu Studio plate layout: compute_colum_count(n) = round(sqrt(n))
    num_plates = len(plates_segments)
    plate_cols = round(math.sqrt(num_plates)) if num_plates > 0 else 1

    for plate_idx, plate_segments in enumerate(plates_segments):
        # Compute within-plate layout positions (centered on 256x256 area)
        positions = compute_plate_layout(plate_segments)

        # Plate offset: Bambu Studio uses a grid layout with stride = size * 1.2
        col = plate_idx % plate_cols
        row = plate_idx // plate_cols
        plate_offset_x = col * PLATE_STRIDE_X
        plate_offset_y = -row * PLATE_STRIDE_Y

        plate: list[PlateSegment] = []
        for seg, (px, py, pz) in zip(plate_segments, positions):
            # Build object model XML and get part IDs first
            _, parts = build_object_model_xml(seg, next_id)
            next_id += len(parts)

            # Assembly object ID comes after part IDs
            assembly_id = next_id
            next_id += 1

            ps = PlateSegment(
                segment=seg,
                object_file_idx=next_object_file_idx,
                assembly_object_id=assembly_id,
                plate_x=px + plate_offset_x,
                plate_y=py + plate_offset_y,
                plate_z=pz,
            )
            ps.part_ids = parts

            next_object_file_idx += 1
            plate.append(ps)

        plates.append(plate)

    # Add clip plate (5th plate with snap-fit connector clips)
    if has_clips:
        logger.info(f"Adding {CLIPS_PER_PLATE} snap-fit clips at {CLIP_SCALE:.0%} scale...")
        clip_mesh = trimesh.load(str(CLIP_STL_PATH))
        if isinstance(clip_mesh, trimesh.Scene):
            clip_mesh = trimesh.util.concatenate(list(clip_mesh.geometry.values()))
        clip_mesh.apply_scale(CLIP_SCALE)

        clip_segments = []
        for i in range(CLIPS_PER_PLATE):
            seg = SegmentMeshes(segment_id=f"clip_{i + 1:02d}")
            seg.water = clip_mesh.copy()
            clip_segments.append(seg)

        positions = compute_plate_layout(clip_segments)

        # Position clip plate to the right of the segment grid (top row)
        # so Bambu shows: S S C / S S  instead of  S S / S S / C
        plate_offset_x = plate_cols * PLATE_STRIDE_X
        plate_offset_y = 0.0

        clip_plate: list[PlateSegment] = []
        for seg, (px, py, pz) in zip(clip_segments, positions):
            _, parts = build_object_model_xml(seg, next_id)
            next_id += len(parts)
            assembly_id = next_id
            next_id += 1

            ps = PlateSegment(
                segment=seg,
                object_file_idx=next_object_file_idx,
                assembly_object_id=assembly_id,
                plate_x=px + plate_offset_x,
                plate_y=py + plate_offset_y,
                plate_z=pz,
            )
            ps.part_ids = parts
            next_object_file_idx += 1
            clip_plate.append(ps)

        plates.append(clip_plate)

    # Build all XML content
    logger.info("Generating 3MF structure...")

    # Collect all object file indices
    all_object_file_indices = []
    for plate in plates:
        for ps in plate:
            all_object_file_indices.append(ps.object_file_idx)

    content_types = build_content_types_xml()
    root_rels = build_root_rels()
    main_model = build_main_model_xml(plates)
    model_rels = build_model_rels(all_object_file_indices)
    model_settings = build_model_settings_config(plates)
    cut_info = build_cut_information_xml(all_object_file_indices)
    filament_seq = build_filament_sequence_json(len(plates))

    # Load slicer settings (filament colours, support, print profile) from template
    if template_3mf is None:
        template_3mf = output_dir / "settings.3mf"
    template_settings = load_template_settings(template_3mf)
    if template_settings:
        logger.info(f"Using slicer settings from {template_3mf}")
    else:
        logger.warning(f"No template found at {template_3mf}, output will lack slicer settings")

    # Write ZIP
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"topoglobe_18_2_{hemisphere}.3mf"

    logger.info(f"Writing {output_path}...")

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("3D/3dmodel.model", main_model)
        zf.writestr("3D/_rels/3dmodel.model.rels", model_rels)

        # Write individual object model files
        for plate in plates:
            for ps in plate:
                # Regenerate the XML for each object file
                # (we generated it before just for part IDs, now write for real)
                obj_xml, _ = build_object_model_xml(ps.segment, ps.part_ids[0][0])
                zf.writestr(f"3D/Objects/object_{ps.object_file_idx}.model", obj_xml)

        # Metadata files
        zf.writestr("Metadata/model_settings.config", model_settings)
        zf.writestr("Metadata/cut_information.xml", cut_info)
        zf.writestr("Metadata/filament_sequence.json", filament_seq)

        # Slicer settings from template (or fallback to generated)
        if "Metadata/slice_info.config" in template_settings:
            zf.writestr("Metadata/slice_info.config", template_settings["Metadata/slice_info.config"])
        else:
            zf.writestr("Metadata/slice_info.config", build_slice_info_config())
        if "Metadata/project_settings.config" in template_settings:
            zf.writestr("Metadata/project_settings.config", template_settings["Metadata/project_settings.config"])

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"Generated {output_path} ({file_size_mb:.1f} MB)")

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Bambu Studio-compatible 3MF files from segment 3MFs"
    )
    parser.add_argument(
        "--hemisphere",
        choices=["north", "south"],
        default=None,
        help="Only process one hemisphere (default: both)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("output"),
        help="Directory containing trimesh-generated segment 3MF files (default: output)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("3mf"),
        help="Directory for output Bambu 3MF files (default: 3mf)",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        help="Template 3MF with slicer settings (default: 3mf/settings.3mf)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    hemispheres = [args.hemisphere] if args.hemisphere else ["north", "south"]

    for hemisphere in hemispheres:
        generate_bambu_3mf(
            hemisphere=hemisphere,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            template_3mf=args.template,
        )


if __name__ == "__main__":
    main()

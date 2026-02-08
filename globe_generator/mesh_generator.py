"""Pure-Python mesh generation using trimesh."""

import logging
import math
from pathlib import Path

import numpy as np
import polars as pl
import trimesh

from .config import GlobeConfig, SegmentDefinition
from .spherical_geometry import calculate_subdivision, create_quad_triangles, latlon_to_cartesian

logger = logging.getLogger(__name__)


class SphericalPatchMeshBuilder:
    """Build triangulated spherical shell patches."""

    def __init__(self, config: GlobeConfig):
        self.config = config

    def create_flat_bottom_patch(
        self,
        r_outer: float,
        flat_z: float,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        rotation_matrix: np.ndarray,
        lat_subdivisions: int | None = None,
        lon_subdivisions: int | None = None
    ) -> trimesh.Trimesh:
        """
        Generate spherical patch with flat inner surface for support-free printing.

        Creates a patch with a curved outer surface and a flat inner surface.
        The flat surface is horizontal (constant Z) in rotated space, which becomes
        the print bed orientation.

        Args:
            r_outer: Outer radius in mm
            flat_z: Z coordinate of flat bottom plane in rotated space
            lat_min: Minimum latitude in degrees
            lat_max: Maximum latitude in degrees
            lon_min: Minimum longitude in degrees
            lon_max: Maximum longitude in degrees
            rotation_matrix: 4x4 transformation matrix for segment orientation
            lat_subdivisions: Number of latitude divisions (auto-calculated if None)
            lon_subdivisions: Number of longitude divisions (auto-calculated if None)

        Returns:
            Trimesh object representing the patch with flat bottom
        """
        # Calculate adaptive subdivision if not provided
        if lat_subdivisions is None or lon_subdivisions is None:
            lat_center = (lat_min + lat_max) / 2.0
            lat_span = lat_max - lat_min
            lon_span = lon_max - lon_min
            lat_subdivisions, lon_subdivisions = calculate_subdivision(
                lat_span, lon_span, lat_center, r_outer
            )

        # Generate grid of (lat, lon) sample points
        lats = np.linspace(lat_min, lat_max, lat_subdivisions)
        lons = np.linspace(lon_min, lon_max, lon_subdivisions)

        # Extract 3x3 rotation and compute inverse
        rot_3x3 = rotation_matrix[:3, :3]
        rot_inv_3x3 = rot_3x3.T  # Orthogonal matrix: inverse = transpose

        # Convert to 3D vertices
        vertices_outer = []
        vertices_inner = []

        for lat in lats:
            for lon in lons:
                # Outer vertex on sphere
                x_outer, y_outer, z_outer = latlon_to_cartesian(lat, lon, r_outer)
                vertices_outer.append([x_outer, y_outer, z_outer])

                # Inner vertex: project to flat plane in rotated space
                # 1. Apply rotation to outer vertex
                outer_pt = np.array([x_outer, y_outer, z_outer])
                rotated_pt = rot_3x3 @ outer_pt

                # 2. Project to flat plane (set Z = flat_z)
                rotated_pt[2] = flat_z

                # 3. Transform back to original space
                inner_pt = rot_inv_3x3 @ rotated_pt
                vertices_inner.append(inner_pt.tolist())

        # Combine vertices: outer layer first, then inner layer
        num_outer = len(vertices_outer)
        vertices = vertices_outer + vertices_inner

        # Generate triangle faces
        faces = []

        def get_vertex_index(lat_idx: int, lon_idx: int, is_outer: bool) -> int:
            """Get vertex index for a given lat/lon grid position."""
            base_idx = lat_idx * lon_subdivisions + lon_idx
            if not is_outer:
                base_idx += num_outer
            return base_idx

        # Outer surface triangles (CCW winding when viewed from outside)
        for i in range(lat_subdivisions - 1):
            for j in range(lon_subdivisions - 1):
                v1 = get_vertex_index(i, j, True)
                v2 = get_vertex_index(i, j + 1, True)
                v3 = get_vertex_index(i + 1, j + 1, True)
                v4 = get_vertex_index(i + 1, j, True)
                faces.extend(create_quad_triangles(v1, v2, v3, v4))

        # Inner surface triangles (CW winding when viewed from outside = CCW from inside)
        for i in range(lat_subdivisions - 1):
            for j in range(lon_subdivisions - 1):
                v1 = get_vertex_index(i, j, False)
                v2 = get_vertex_index(i, j + 1, False)
                v3 = get_vertex_index(i + 1, j + 1, False)
                v4 = get_vertex_index(i + 1, j, False)
                # Reverse winding for inner surface
                faces.extend(create_quad_triangles(v1, v4, v3, v2))

        # Side edge 1: lat_min edge (connect inner and outer)
        i = 0
        for j in range(lon_subdivisions - 1):
            vo1 = get_vertex_index(i, j, True)
            vo2 = get_vertex_index(i, j + 1, True)
            vi1 = get_vertex_index(i, j, False)
            vi2 = get_vertex_index(i, j + 1, False)
            faces.extend(create_quad_triangles(vi1, vi2, vo2, vo1))

        # Side edge 2: lat_max edge
        i = lat_subdivisions - 1
        for j in range(lon_subdivisions - 1):
            vo1 = get_vertex_index(i, j, True)
            vo2 = get_vertex_index(i, j + 1, True)
            vi1 = get_vertex_index(i, j, False)
            vi2 = get_vertex_index(i, j + 1, False)
            faces.extend(create_quad_triangles(vo1, vo2, vi2, vi1))

        # Side edge 3: lon_min edge
        j = 0
        for i in range(lat_subdivisions - 1):
            vo1 = get_vertex_index(i, j, True)
            vo2 = get_vertex_index(i + 1, j, True)
            vi1 = get_vertex_index(i, j, False)
            vi2 = get_vertex_index(i + 1, j, False)
            faces.extend(create_quad_triangles(vo1, vo2, vi2, vi1))

        # Side edge 4: lon_max edge
        j = lon_subdivisions - 1
        for i in range(lat_subdivisions - 1):
            vo1 = get_vertex_index(i, j, True)
            vo2 = get_vertex_index(i + 1, j, True)
            vi1 = get_vertex_index(i, j, False)
            vi2 = get_vertex_index(i + 1, j, False)
            faces.extend(create_quad_triangles(vi1, vi2, vo2, vo1))

        return trimesh.Trimesh(vertices=np.array(vertices), faces=np.array(faces))

    def create_patch(
        self,
        r_inner: float,
        r_outer: float,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        lat_subdivisions: int | None = None,
        lon_subdivisions: int | None = None
    ) -> trimesh.Trimesh:
        """
        Generate triangulated spherical shell patch.

        Creates a patch with two surfaces (inner and outer) connected by side faces.
        Uses lat-lon grid subdivision for controlled mesh density.

        Args:
            r_inner: Inner radius in mm
            r_outer: Outer radius in mm (r_inner + thickness)
            lat_min: Minimum latitude in degrees
            lat_max: Maximum latitude in degrees
            lon_min: Minimum longitude in degrees
            lon_max: Maximum longitude in degrees
            lat_subdivisions: Number of latitude divisions (auto-calculated if None)
            lon_subdivisions: Number of longitude divisions (auto-calculated if None)

        Returns:
            Trimesh object representing the patch
        """
        # Calculate adaptive subdivision if not provided
        if lat_subdivisions is None or lon_subdivisions is None:
            lat_center = (lat_min + lat_max) / 2.0
            lat_span = lat_max - lat_min
            lon_span = lon_max - lon_min
            thickness = r_outer - r_inner
            # Use the middle radius for subdivision calculation
            r_mid = r_inner + thickness / 2.0
            lat_subdivisions, lon_subdivisions = calculate_subdivision(
                lat_span, lon_span, lat_center, r_mid
            )

        # Generate grid of (lat, lon) sample points
        lats = np.linspace(lat_min, lat_max, lat_subdivisions)
        lons = np.linspace(lon_min, lon_max, lon_subdivisions)

        # Convert to 3D vertices
        vertices = []
        vertices_outer = []
        vertices_inner = []

        for lat in lats:
            for lon in lons:
                x_outer, y_outer, z_outer = latlon_to_cartesian(lat, lon, r_outer)
                x_inner, y_inner, z_inner = latlon_to_cartesian(lat, lon, r_inner)
                vertices_outer.append([x_outer, y_outer, z_outer])
                vertices_inner.append([x_inner, y_inner, z_inner])

        # Combine vertices: outer layer first, then inner layer
        num_outer = len(vertices_outer)
        vertices = vertices_outer + vertices_inner

        # Generate triangle faces
        faces = []

        def get_vertex_index(lat_idx: int, lon_idx: int, is_outer: bool) -> int:
            """Get vertex index for a given lat/lon grid position."""
            base_idx = lat_idx * lon_subdivisions + lon_idx
            if not is_outer:
                base_idx += num_outer
            return base_idx

        # Outer surface triangles (CCW winding when viewed from outside)
        for i in range(lat_subdivisions - 1):
            for j in range(lon_subdivisions - 1):
                v1 = get_vertex_index(i, j, True)
                v2 = get_vertex_index(i, j + 1, True)
                v3 = get_vertex_index(i + 1, j + 1, True)
                v4 = get_vertex_index(i + 1, j, True)
                faces.extend(create_quad_triangles(v1, v2, v3, v4))

        # Inner surface triangles (CW winding when viewed from outside = CCW from inside)
        for i in range(lat_subdivisions - 1):
            for j in range(lon_subdivisions - 1):
                v1 = get_vertex_index(i, j, False)
                v2 = get_vertex_index(i, j + 1, False)
                v3 = get_vertex_index(i + 1, j + 1, False)
                v4 = get_vertex_index(i + 1, j, False)
                # Reverse winding for inner surface
                faces.extend(create_quad_triangles(v1, v4, v3, v2))

        # Side edge 1: lat_min edge (connect inner and outer)
        i = 0
        for j in range(lon_subdivisions - 1):
            vo1 = get_vertex_index(i, j, True)
            vo2 = get_vertex_index(i, j + 1, True)
            vi1 = get_vertex_index(i, j, False)
            vi2 = get_vertex_index(i, j + 1, False)
            faces.extend(create_quad_triangles(vi1, vi2, vo2, vo1))

        # Side edge 2: lat_max edge
        i = lat_subdivisions - 1
        for j in range(lon_subdivisions - 1):
            vo1 = get_vertex_index(i, j, True)
            vo2 = get_vertex_index(i, j + 1, True)
            vi1 = get_vertex_index(i, j, False)
            vi2 = get_vertex_index(i, j + 1, False)
            faces.extend(create_quad_triangles(vo1, vo2, vi2, vi1))

        # Side edge 3: lon_min edge
        j = 0
        for i in range(lat_subdivisions - 1):
            vo1 = get_vertex_index(i, j, True)
            vo2 = get_vertex_index(i + 1, j, True)
            vi1 = get_vertex_index(i, j, False)
            vi2 = get_vertex_index(i + 1, j, False)
            faces.extend(create_quad_triangles(vo1, vo2, vi2, vi1))

        # Side edge 4: lon_max edge
        j = lon_subdivisions - 1
        for i in range(lat_subdivisions - 1):
            vo1 = get_vertex_index(i, j, True)
            vo2 = get_vertex_index(i + 1, j, True)
            vi1 = get_vertex_index(i, j, False)
            vi2 = get_vertex_index(i + 1, j, False)
            faces.extend(create_quad_triangles(vi1, vi2, vo2, vo1))

        return trimesh.Trimesh(vertices=np.array(vertices), faces=np.array(faces))

    def create_shell_patches(
        self,
        segment: SegmentDefinition,
        rotation_matrix: np.ndarray,
        flat_z: float
    ) -> list[trimesh.Trimesh]:
        """
        Create 5 shell patches with cutouts for tabs and flat inner surfaces.

        Creates a shell divided into 5 patches to accommodate dual tabs on the
        eastern edge and corresponding cutouts on the western edge. Inner surfaces
        are flat for support-free 3D printing.

        Args:
            segment: Segment definition with lat/lon boundaries
            rotation_matrix: 4x4 transformation matrix for segment orientation
            flat_z: Z coordinate of flat bottom plane in rotated space

        Returns:
            List of 5 mesh patches (south, center, north, east-lower, east-upper)
        """
        tab_size_degrees = self.config.tab_size_degrees
        r_outer = self.config.core_radius_mm

        # Calculate dual cutout regions on western edge
        # Cutouts are same angular size as tabs (clearance applied to tab thickness instead)
        segment_lat_range = segment.lat_max - segment.lat_min

        # Lower cutout (at 1/3 height)
        cutout_lower_lat_center = segment.lat_min + (segment_lat_range / 3.0)
        cutout_lower_lat_min = cutout_lower_lat_center - (tab_size_degrees / 2.0)
        cutout_lower_lat_max = cutout_lower_lat_center + (tab_size_degrees / 2.0)

        # Adjust longitude span to match latitude-adjusted tabs
        cutout_lower_lon_span = tab_size_degrees / max(0.1, math.cos(math.radians(cutout_lower_lat_center)))
        cutout_lower_lon_max = segment.lon_min + cutout_lower_lon_span

        # Upper cutout (at 2/3 height)
        cutout_upper_lat_center = segment.lat_min + (2.0 * segment_lat_range / 3.0)
        cutout_upper_lat_min = cutout_upper_lat_center - (tab_size_degrees / 2.0)
        cutout_upper_lat_max = cutout_upper_lat_center + (tab_size_degrees / 2.0)

        # Adjust longitude span for this cutout's latitude
        cutout_upper_lon_span = tab_size_degrees / max(0.1, math.cos(math.radians(cutout_upper_lat_center)))
        cutout_upper_lon_max = segment.lon_min + cutout_upper_lon_span

        # Helper function to calculate subdivisions for shell patches
        # Target: ~1 degree per subdivision for smooth visible surfaces
        def calc_shell_subdivisions(lat_span: float, lon_span: float) -> tuple:
            lat_subs = max(8, int(round(lat_span)))
            lon_subs = max(8, int(round(lon_span)))
            return lat_subs, lon_subs

        # Create 5 shell patches with subdivision based on angular extent
        patches = []
        segment_lon_span = segment.lon_max - segment.lon_min

        # South patch (below lower cutout)
        lat_span_south = cutout_lower_lat_min - segment.lat_min
        lat_subs_south, lon_subs_south = calc_shell_subdivisions(lat_span_south, segment_lon_span)
        shell_south = self.create_flat_bottom_patch(
            r_outer,
            flat_z,
            segment.lat_min,
            cutout_lower_lat_min,
            segment.lon_min,
            segment.lon_max,
            rotation_matrix,
            lat_subdivisions=lat_subs_south,
            lon_subdivisions=lon_subs_south
        )
        patches.append(shell_south)

        # Center patch (between two cutouts)
        lat_span_center = cutout_upper_lat_min - cutout_lower_lat_max
        lat_subs_center, lon_subs_center = calc_shell_subdivisions(lat_span_center, segment_lon_span)
        shell_center = self.create_flat_bottom_patch(
            r_outer,
            flat_z,
            cutout_lower_lat_max,
            cutout_upper_lat_min,
            segment.lon_min,
            segment.lon_max,
            rotation_matrix,
            lat_subdivisions=lat_subs_center,
            lon_subdivisions=lon_subs_center
        )
        patches.append(shell_center)

        # North patch (above upper cutout)
        lat_span_north = segment.lat_max - cutout_upper_lat_max
        lat_subs_north, lon_subs_north = calc_shell_subdivisions(lat_span_north, segment_lon_span)
        shell_north = self.create_flat_bottom_patch(
            r_outer,
            flat_z,
            cutout_upper_lat_max,
            segment.lat_max,
            segment.lon_min,
            segment.lon_max,
            rotation_matrix,
            lat_subdivisions=lat_subs_north,
            lon_subdivisions=lon_subs_north
        )
        patches.append(shell_north)

        # East-lower patch (right of lower cutout)
        lat_span_east_lower = cutout_lower_lat_max - cutout_lower_lat_min
        lon_span_east_lower = segment.lon_max - cutout_lower_lon_max
        lat_subs_east_lower, lon_subs_east_lower = calc_shell_subdivisions(lat_span_east_lower, lon_span_east_lower)
        shell_east_lower = self.create_flat_bottom_patch(
            r_outer,
            flat_z,
            cutout_lower_lat_min,
            cutout_lower_lat_max,
            cutout_lower_lon_max,
            segment.lon_max,
            rotation_matrix,
            lat_subdivisions=lat_subs_east_lower,
            lon_subdivisions=lon_subs_east_lower
        )
        patches.append(shell_east_lower)

        # East-upper patch (right of upper cutout)
        lat_span_east_upper = cutout_upper_lat_max - cutout_upper_lat_min
        lon_span_east_upper = segment.lon_max - cutout_upper_lon_max
        lat_subs_east_upper, lon_subs_east_upper = calc_shell_subdivisions(lat_span_east_upper, lon_span_east_upper)
        shell_east_upper = self.create_flat_bottom_patch(
            r_outer,
            flat_z,
            cutout_upper_lat_min,
            cutout_upper_lat_max,
            cutout_upper_lon_max,
            segment.lon_max,
            rotation_matrix,
            lat_subdivisions=lat_subs_east_upper,
            lon_subdivisions=lon_subs_east_upper
        )
        patches.append(shell_east_upper)

        return patches

    def create_tab_patches(
        self,
        segment: SegmentDefinition,
        rotation_matrix: np.ndarray,
        flat_z: float
    ) -> list[trimesh.Trimesh]:
        """
        Create 2 tab patches on eastern edge with flat inner surfaces.

        Tabs are thinner than shell by clearance amount to provide radial clearance.
        Inner surfaces are flat for support-free 3D printing.

        Args:
            segment: Segment definition with lat/lon boundaries
            rotation_matrix: 4x4 transformation matrix for segment orientation
            flat_z: Z coordinate of flat bottom plane in rotated space

        Returns:
            List of 2 mesh patches (lower tab, upper tab)
        """
        shell_thickness_mm = self.config.shell_thickness_mm
        tab_size_degrees = self.config.tab_size_degrees
        clearance_mm = self.config.clearance_mm

        # Tabs are thinner than shell to provide clearance in depth
        tab_thickness_mm = shell_thickness_mm - clearance_mm
        r_outer_tab = self.config.hollow_radius_mm + tab_thickness_mm

        segment_lat_range = segment.lat_max - segment.lat_min

        # Helper function for tab subdivisions (same as shell)
        def calc_tab_subdivisions(lat_span: float, lon_span: float) -> tuple:
            lat_subs = max(8, int(round(lat_span)))
            lon_subs = max(8, int(round(lon_span)))
            return lat_subs, lon_subs

        patches = []

        # Lower tab (at 1/3 height)
        tab_lower_lat_center = segment.lat_min + (segment_lat_range / 3.0)
        tab_lower_lat_min = tab_lower_lat_center - (tab_size_degrees / 2.0)
        tab_lower_lat_max = tab_lower_lat_center + (tab_size_degrees / 2.0)

        # Adjust longitude span to compensate for latitude convergence
        tab_lower_lon_span = tab_size_degrees / max(0.1, math.cos(math.radians(tab_lower_lat_center)))
        tab_lower_lon_min = segment.lon_max
        tab_lower_lon_max = segment.lon_max + tab_lower_lon_span

        lat_span_lower = tab_lower_lat_max - tab_lower_lat_min
        lat_subs_lower, lon_subs_lower = calc_tab_subdivisions(lat_span_lower, tab_lower_lon_span)

        tab_lower = self.create_flat_bottom_patch(
            r_outer_tab,
            flat_z,
            tab_lower_lat_min,
            tab_lower_lat_max,
            tab_lower_lon_min,
            tab_lower_lon_max,
            rotation_matrix,
            lat_subdivisions=lat_subs_lower,
            lon_subdivisions=lon_subs_lower
        )
        patches.append(tab_lower)

        # Upper tab (at 2/3 height)
        tab_upper_lat_center = segment.lat_min + (2.0 * segment_lat_range / 3.0)
        tab_upper_lat_min = tab_upper_lat_center - (tab_size_degrees / 2.0)
        tab_upper_lat_max = tab_upper_lat_center + (tab_size_degrees / 2.0)

        # Adjust longitude span for this tab's latitude
        tab_upper_lon_span = tab_size_degrees / max(0.1, math.cos(math.radians(tab_upper_lat_center)))
        tab_upper_lon_min = segment.lon_max
        tab_upper_lon_max = segment.lon_max + tab_upper_lon_span

        lat_span_upper = tab_upper_lat_max - tab_upper_lat_min
        lat_subs_upper, lon_subs_upper = calc_tab_subdivisions(lat_span_upper, tab_upper_lon_span)

        tab_upper = self.create_flat_bottom_patch(
            r_outer_tab,
            flat_z,
            tab_upper_lat_min,
            tab_upper_lat_max,
            tab_upper_lon_min,
            tab_upper_lon_max,
            rotation_matrix,
            lat_subdivisions=lat_subs_upper,
            lon_subdivisions=lon_subs_upper
        )
        patches.append(tab_upper)

        return patches

    def create_elevation_patch(
        self,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        r_base: float,
        height_mm: float
    ) -> trimesh.Trimesh | None:
        """
        Create single elevation relief patch.

        Args:
            lat_min, lat_max, lon_min, lon_max: Cell boundaries in degrees
            r_base: Base radius where this layer starts
            height_mm: Height of this layer

        Returns:
            Trimesh patch or None if height is zero
        """
        if height_mm <= 0:
            return None

        return self.create_patch(
            r_base,
            r_base + height_mm,
            lat_min,
            lat_max,
            lon_min,
            lon_max,
            lat_subdivisions=4,
            lon_subdivisions=4
        )


def calculate_rotation_to_north_pole(segment: SegmentDefinition) -> np.ndarray:
    """
    Calculate 4x4 transformation matrix to rotate segment to north pole orientation.

    Rotates the segment so that its center point aligns with the north pole (0, 0, 1).
    This allows printing the segment flat with the pole at the top.

    Args:
        segment: Segment definition with lat/lon boundaries

    Returns:
        4x4 transformation matrix
    """
    lat_center = (segment.lat_min + segment.lat_max) / 2.0
    lon_center = (segment.lon_min + segment.lon_max) / 2.0

    # Calculate the 3D direction vector for the segment center
    lat_rad = math.radians(lat_center)
    lon_rad = math.radians(lon_center)

    from_vec = np.array([
        math.cos(lat_rad) * math.cos(lon_rad),
        math.cos(lat_rad) * math.sin(lon_rad),
        math.sin(lat_rad)
    ])
    to_vec = np.array([0, 0, 1])  # North pole direction

    # Calculate rotation axis (cross product)
    axis = np.cross(from_vec, to_vec)
    axis_len = np.linalg.norm(axis)

    if axis_len < 1e-6:
        # Already aligned or opposite direction
        if np.dot(from_vec, to_vec) > 0:
            return np.eye(4)  # Already aligned
        # 180 degree rotation needed - use arbitrary perpendicular axis
        axis = np.array([1, 0, 0])
        angle = np.pi
    else:
        axis = axis / axis_len
        angle = np.arccos(np.clip(np.dot(from_vec, to_vec), -1.0, 1.0))

    # Create rotation matrix using trimesh utilities
    return trimesh.transformations.rotation_matrix(angle, axis, point=[0, 0, 0])


def export_segment_3mf(
    water_mesh: trimesh.Trimesh | None,
    land_mesh: trimesh.Trimesh | None,
    snow_mesh: trimesh.Trimesh | None,
    segment_id: str,
    output_path: Path
) -> None:
    """
    Export three separate mesh objects to 3MF with color metadata.

    Args:
        water_mesh: Water layer mesh (blue)
        land_mesh: Land layer mesh (brown)
        snow_mesh: Snow layer mesh (white)
        segment_id: Segment identifier to include in object names
        output_path: Output file path
    """
    scene = trimesh.Scene()

    if water_mesh is not None and len(water_mesh.vertices) > 0:
        scene.add_geometry(
            water_mesh,
            node_name=f'{segment_id}_water',
            geom_name=f'{segment_id}_water',
            metadata={'color': [0, 119, 190, 255]}  # Blue
        )

    if land_mesh is not None and len(land_mesh.vertices) > 0:
        scene.add_geometry(
            land_mesh,
            node_name=f'{segment_id}_land',
            geom_name=f'{segment_id}_land',
            metadata={'color': [139, 90, 43, 255]}  # Brown
        )

    if snow_mesh is not None and len(snow_mesh.vertices) > 0:
        scene.add_geometry(
            snow_mesh,
            node_name=f'{segment_id}_snow',
            geom_name=f'{segment_id}_snow',
            metadata={'color': [255, 255, 255, 255]}  # White
        )

    # Export to 3MF (trimesh handles ZIP structure automatically)
    scene.export(str(output_path), file_type='3mf')


def generate_segment_mesh(
    cells_df: pl.DataFrame,
    segment: SegmentDefinition,
    config: GlobeConfig,
    output_path: Path
) -> bool:
    """
    Generate segment mesh and export to 3MF.

    Creates a complete segment mesh including hollow shell, tabs, and elevation relief
    for water, land, and snow layers. Exports as multi-object 3MF for multi-color printing.

    Args:
        cells_df: DataFrame with cell data (water/land/snow heights)
        segment: Segment definition
        config: Globe configuration
        output_path: Output 3MF file path

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Generating {segment.segment_id} mesh...")

    try:
        builder = SphericalPatchMeshBuilder(config)

        # Pre-calculate rotation matrix for flat bottom computation
        rotation_matrix = calculate_rotation_to_north_pole(segment)

        # Calculate flat_z: after rotation, segment center is at Z = r_outer
        # For shell_thickness at center, flat plane is at r_outer - shell_thickness
        # This maintains minimum wall thickness at the thinnest point (center)
        flat_z = config.core_radius_mm - config.shell_thickness_mm

        # Build shell and tabs with flat inner surfaces
        shell_patches = builder.create_shell_patches(segment, rotation_matrix, flat_z)
        tab_patches = builder.create_tab_patches(segment, rotation_matrix, flat_z)

        water_patches = shell_patches + tab_patches
        land_patches = []
        snow_patches = []

        core_radius_mm = config.core_radius_mm

        # Build elevation relief patches for each grid cell
        for row in cells_df.iter_rows(named=True):
            water_height_mm = float(row['water_height_mm']) if not math.isnan(row['water_height_mm']) else 0.0
            land_height_mm = float(row['land_height_mm']) if not math.isnan(row['land_height_mm']) else 0.0
            snow_height_mm = float(row['snow_height_mm']) if not math.isnan(row['snow_height_mm']) else 0.0

            lat1 = float(row['lat_a_deg'])
            lat2 = float(row['lat_b_deg'])
            lon1 = float(row['lon_a_deg'])
            lon2 = float(row['lon_b_deg'])

            # Check if cell overlaps segment (preserve exact logic from lines 245-248)
            if lat2 <= segment.lat_min or lat1 >= segment.lat_max:
                continue
            if lon2 <= segment.lon_min or lon1 >= segment.lon_max:
                continue

            # Water patches
            if water_height_mm > 0:
                wsp = builder.create_elevation_patch(
                    lat1, lat2, lon1, lon2,
                    core_radius_mm, water_height_mm
                )
                if wsp is not None:
                    water_patches.append(wsp)

                # Land patches (on top of water)
                if land_height_mm > 0:
                    lsp = builder.create_elevation_patch(
                        lat1, lat2, lon1, lon2,
                        core_radius_mm + water_height_mm, land_height_mm
                    )
                    if lsp is not None:
                        land_patches.append(lsp)

                # Snow patches (on top of water, replaces land)
                if snow_height_mm > 0:
                    ssp = builder.create_elevation_patch(
                        lat1, lat2, lon1, lon2,
                        core_radius_mm + water_height_mm, snow_height_mm
                    )
                    if ssp is not None:
                        snow_patches.append(ssp)

        logger.info(f"  Shape counts - Water: {len(water_patches)}, Land: {len(land_patches)}, Snow: {len(snow_patches)}")

        # Merge patches by layer
        water_mesh = None
        land_mesh = None
        snow_mesh = None

        if water_patches:
            water_mesh = trimesh.util.concatenate(water_patches)
            water_mesh.merge_vertices(digits_vertex=4)  # Merge vertices within 0.1mm

        if land_patches:
            land_mesh = trimesh.util.concatenate(land_patches)
            land_mesh.merge_vertices(digits_vertex=4)

        if snow_patches:
            snow_mesh = trimesh.util.concatenate(snow_patches)
            snow_mesh.merge_vertices(digits_vertex=4)

        # Rotate to north pole orientation
        rotation_matrix = calculate_rotation_to_north_pole(segment)
        if water_mesh is not None:
            water_mesh.apply_transform(rotation_matrix)
        if land_mesh is not None:
            land_mesh.apply_transform(rotation_matrix)
        if snow_mesh is not None:
            snow_mesh.apply_transform(rotation_matrix)

        # Export to 3MF
        export_segment_3mf(water_mesh, land_mesh, snow_mesh, segment.segment_id, output_path)

        # Verify output file was created
        if output_path.exists() and output_path.stat().st_size > 0:
            return True
        logger.error(f"Output file not created or empty: {output_path}")
        return False

    except Exception as e:
        logger.error(f"Error generating mesh: {e}", exc_info=True)
        return False

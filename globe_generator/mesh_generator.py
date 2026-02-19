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

# Path to snap-fit pocket STL (relative to project root)
POCKET_STL_PATH = Path(__file__).parent.parent / "snapfits" / "connector1-slim-model_files" / "pocket-0-dof-slim-r1.stl"


def load_half_pocket() -> trimesh.Trimesh:
    """
    Load the snap-fit pocket and return only the Z >= 0 half.

    Returns:
        Trimesh of the half-pocket
    """
    pocket_geom = trimesh.load(str(POCKET_STL_PATH))
    if not isinstance(pocket_geom, trimesh.Trimesh):
        raise ValueError("Pocket STL did not load as a Trimesh")
    pocket: trimesh.Trimesh = pocket_geom

    # Slice to keep only Z >= 0 (one half of the symmetric pocket)
    # Normal [0,0,1] keeps the side where Z >= 0, cap=True closes the cut
    half_pocket = pocket.slice_plane([0, 0, 0], [0, 0, 1], cap=True)
    # try to make it very small so we don't collide with cells
    half_pocket.apply_scale(0.75)
    return half_pocket


def create_pocket_transform(
    lat: float,
    lon: float,
    radius: float,
    direction: str
) -> np.ndarray:
    """
    Create transformation matrix to position pocket at edge midpoint.

    The pocket is oriented so:
    - Its Z axis (length, 16mm) runs east-west, pointing toward adjacent segment
    - Its X axis (width, 13.2mm) runs north-south along the edge
    - Its Y axis (depth, 5.2mm) points radially inward

    Args:
        lat: Latitude of pocket center in degrees
        lon: Longitude of pocket center in degrees
        radius: Radius at which to place the pocket (outer surface)
        direction: 'east' or 'west' - which edge

    Returns:
        4x4 transformation matrix
    """
    # Convert to radians
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    # Position on sphere
    pos = np.array([
        radius * math.cos(lat_rad) * math.cos(lon_rad),
        radius * math.cos(lat_rad) * math.sin(lon_rad),
        radius * math.sin(lat_rad)
    ])

    # Radial direction (outward from center)
    radial = pos / np.linalg.norm(pos)

    # North tangent direction (along meridian, pointing north)
    # Derivative of position with respect to latitude
    north = np.array([
        -math.sin(lat_rad) * math.cos(lon_rad),
        -math.sin(lat_rad) * math.sin(lon_rad),
        math.cos(lat_rad)
    ])
    north = north / np.linalg.norm(north)

    # East tangent direction (along parallel, pointing east)
    east = np.cross(radial, north)
    east = east / np.linalg.norm(east)

    # Pocket orientation:
    # - Pocket Z (length) -> east direction (toward adjacent segment)
    # - Pocket X (width) -> north direction (along the edge)
    # - Pocket Y (depth) -> inward (-radial)

    if direction == 'east':
        pocket_z = east      # Length points east toward adjacent segment
        pocket_x = north     # Width runs along edge (north-south)
        pocket_y = -radial   # Depth points inward
    else:  # west
        pocket_z = -east     # Length points west toward adjacent segment
        pocket_x = north     # Width runs along edge
        pocket_y = -radial   # Depth points inward

    # Build rotation matrix (columns are the new axes)
    rotation = np.eye(4)
    rotation[:3, 0] = pocket_x
    rotation[:3, 1] = pocket_y
    rotation[:3, 2] = pocket_z

    # Translation to position
    translation = np.eye(4)
    translation[:3, 3] = pos

    # Combined transform: first rotate, then translate
    return translation @ rotation


class SphericalPatchMeshBuilder:
    """Build triangulated spherical shell patches."""

    def __init__(self, config: GlobeConfig):
        self.config = config

    def create_flat_bottom_patch(
        self,
        r_inner: float,
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
        Generate spherical patch with radial side walls and flat interior.

        Creates a patch with:
        - Curved outer surface (on sphere at r_outer)
        - Radial side walls (edge inner vertices on sphere at r_inner)
        - Flat interior bottom (interior inner vertices on horizontal plane)

        Args:
            r_inner: Inner radius in mm (for edge vertices)
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
            Trimesh object representing the patch
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

        # Calculate the 4 corners of the flat base quadrilateral
        # Project segment corners at r_inner to the flat plane
        def get_flat_corner(lat: float, lon: float) -> np.ndarray:
            x, y, z = latlon_to_cartesian(lat, lon, r_inner)
            pt = np.array([x, y, z])
            rotated = rot_3x3 @ pt
            rotated[2] = flat_z
            return rot_inv_3x3 @ rotated

        # Corners: SW, SE, NE, NW (in lat/lon order)
        corner_sw = get_flat_corner(lat_min, lon_min)  # i=0, j=0
        corner_se = get_flat_corner(lat_min, lon_max)  # i=0, j=max
        corner_ne = get_flat_corner(lat_max, lon_max)  # i=max, j=max
        corner_nw = get_flat_corner(lat_max, lon_min)  # i=max, j=0

        # Convert to 3D vertices
        vertices_outer = []
        vertices_inner = []

        for i, lat in enumerate(lats):
            # Normalized latitude coordinate [0, 1]
            u = i / (lat_subdivisions - 1) if lat_subdivisions > 1 else 0.0

            for j, lon in enumerate(lons):
                # Normalized longitude coordinate [0, 1]
                v = j / (lon_subdivisions - 1) if lon_subdivisions > 1 else 0.0

                # Outer vertex on sphere
                x_outer, y_outer, z_outer = latlon_to_cartesian(lat, lon, r_outer)
                vertices_outer.append([x_outer, y_outer, z_outer])

                # Inner vertex: bilinear interpolation on flat quadrilateral
                inner_pt = ((1-u) * (1-v) * corner_sw +
                            (1-u) * v * corner_se +
                            u * v * corner_ne +
                            u * (1-v) * corner_nw)
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

    def create_shell_patch(
        self,
        segment: SegmentDefinition,
        rotation_matrix: np.ndarray,
        flat_z: float
    ) -> trimesh.Trimesh:
        """
        Create a single shell patch with radial side walls and flat interior.

        Creates a shell covering the entire segment with:
        - Curved outer surface
        - Radial side walls (for proper fit with adjacent segments)
        - Flat interior bottom for support-free printing

        Args:
            segment: Segment definition with lat/lon boundaries
            rotation_matrix: 4x4 transformation matrix for segment orientation
            flat_z: Z coordinate of flat bottom plane in rotated space

        Returns:
            Single mesh patch for the shell
        """
        r_inner = self.config.hollow_radius_mm
        r_outer = self.config.core_radius_mm

        # Calculate subdivisions based on angular extent
        # Target: ~1 degree per subdivision for smooth visible surfaces
        lat_span = segment.lat_max - segment.lat_min
        lon_span = segment.lon_max - segment.lon_min
        lat_subs = max(8, int(round(lat_span)))
        lon_subs = max(8, int(round(lon_span)))

        return self.create_flat_bottom_patch(
            r_inner,
            r_outer,
            flat_z,
            segment.lat_min,
            segment.lat_max,
            segment.lon_min,
            segment.lon_max,
            rotation_matrix,
            lat_subdivisions=lat_subs,
            lon_subdivisions=lon_subs
        )

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


def calculate_edge_min_z(
    segment: SegmentDefinition,
    r_inner: float,
    rotation_matrix: np.ndarray,
    num_samples: int = 50
) -> float:
    """
    Calculate the minimum Z coordinate of inner edge vertices after rotation.

    This determines where the flat bottom plane should be placed so that
    it sits at or below all edge vertices.

    Args:
        segment: Segment definition with lat/lon boundaries
        r_inner: Inner radius for edge vertices
        rotation_matrix: 4x4 transformation matrix
        num_samples: Number of sample points per edge

    Returns:
        Minimum Z coordinate of edge vertices in rotated space
    """
    rot_3x3 = rotation_matrix[:3, :3]
    min_z = float('inf')

    # Sample points along all four edges
    lats_edge = np.linspace(segment.lat_min, segment.lat_max, num_samples)
    lons_edge = np.linspace(segment.lon_min, segment.lon_max, num_samples)

    # South edge (lat_min)
    for lon in lons_edge:
        x, y, z = latlon_to_cartesian(segment.lat_min, lon, r_inner)
        rotated = rot_3x3 @ np.array([x, y, z])
        min_z = min(min_z, rotated[2])

    # North edge (lat_max)
    for lon in lons_edge:
        x, y, z = latlon_to_cartesian(segment.lat_max, lon, r_inner)
        rotated = rot_3x3 @ np.array([x, y, z])
        min_z = min(min_z, rotated[2])

    # West edge (lon_min)
    for lat in lats_edge:
        x, y, z = latlon_to_cartesian(lat, segment.lon_min, r_inner)
        rotated = rot_3x3 @ np.array([x, y, z])
        min_z = min(min_z, rotated[2])

    # East edge (lon_max)
    for lat in lats_edge:
        x, y, z = latlon_to_cartesian(lat, segment.lon_max, r_inner)
        rotated = rot_3x3 @ np.array([x, y, z])
        min_z = min(min_z, rotated[2])

    return min_z


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

    Creates a complete segment mesh including shell and elevation relief
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

        # Calculate flat_z: must be at or below the lowest edge vertex after rotation
        # This ensures the flat interior doesn't float above the radial edges
        r_inner = config.hollow_radius_mm
        flat_z = calculate_edge_min_z(segment, r_inner, rotation_matrix)

        # Build shell with flat inner surface
        shell_patch = builder.create_shell_patch(segment, rotation_matrix, flat_z)

        water_patches = [shell_patch]
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

            # Check if cell fully within segment
            if lat1 < segment.lat_min or lat2 > segment.lat_max:
                continue
            if lon1 < segment.lon_min or lon2 > segment.lon_max:
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

        # Repair shell_patch for polar segments (may have degenerate faces at pole)
        if not shell_patch.is_volume:
            # Remove degenerate (zero-area) faces
            areas = shell_patch.area_faces
            valid_faces = areas > 1e-10
            if not np.all(valid_faces):
                shell_patch.update_faces(valid_faces)
                shell_patch.remove_unreferenced_vertices()
            # Fill any holes and fix normals
            shell_patch.fill_holes()
            trimesh.repair.fix_normals(shell_patch)

        # Add snap-fit pockets to shell before combining with elevation patches
        if POCKET_STL_PATH.exists():
            try:
                half_pocket = load_half_pocket()
                # Position pocket centered N-S on the edge
                pocket_lat = (segment.lat_min + segment.lat_max) / 2.0
                # Position pocket lower on wall (smaller radius = closer to base after rotation)
                pocket_radius = r_inner + 1.0

                # East edge pocket
                east_transform = create_pocket_transform(
                    pocket_lat, segment.lon_max, pocket_radius, 'east'
                )
                east_pocket = half_pocket.copy()
                east_pocket.apply_transform(east_transform)

                # West edge pocket
                west_transform = create_pocket_transform(
                    pocket_lat, segment.lon_min, pocket_radius, 'west'
                )
                west_pocket = half_pocket.copy()
                west_pocket.apply_transform(west_transform)

                # Boolean subtract pockets from shell patch (which is a valid volume)
                shell_patch = shell_patch.difference(east_pocket)
                shell_patch = shell_patch.difference(west_pocket)
                water_patches[0] = shell_patch
                logger.info("  Added snap-fit pockets on east and west edges")
            except Exception as e:
                logger.warning(f"  Failed to add snap-fit pockets: {e}")

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

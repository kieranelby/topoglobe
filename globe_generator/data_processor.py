"""Data processing for elevation and snow data."""

import numpy as np
import polars as pl
import xarray as xr
import rasterio
from typing import Optional
import logging

from .config import GlobeConfig, SegmentDefinition
from .grid_builder import build_equal_area_grid


logger = logging.getLogger(__name__)


class DataProcessor:
    """Process elevation and snow data for globe generation."""

    def __init__(self, config: GlobeConfig):
        self.config = config
        self.etopo_ds = None
        self.snow_src = None
        self.global_min_elevation = None
        self.global_max_elevation = None
        self.elevation_to_mm = None

    def load_datasets(self):
        """Load ETOPO1 and MODIS data files."""
        logger.info(f"Loading ETOPO1 data from {self.config.etopo_path}")
        self.etopo_ds = xr.open_dataset(self.config.etopo_path)

        if self.config.snow_path:
            logger.info(f"Loading snow data from {self.config.snow_path}")
            self.snow_src = rasterio.open(self.config.snow_path)

    def compute_global_elevation_range(self):
        """Compute global elevation range for consistent height scaling across segments."""
        logger.info("Computing global elevation range...")
        self.global_min_elevation = float(self.etopo_ds["z"].min().values)
        self.global_max_elevation = float(self.etopo_ds["z"].max().values)
        elevation_range = self.global_max_elevation - self.global_min_elevation
        self.elevation_to_mm = self.config.elevation_range_mm / elevation_range

        # Store core radius for geometry generation
        self.config.core_radius_mm = self.config.radius_mm + self.global_min_elevation * self.elevation_to_mm
        logger.info(f"Global elevation range: {self.global_min_elevation:.1f}m to {self.global_max_elevation:.1f}m")
        logger.info(f"Core radius: {self.config.core_radius_mm:.3f} mm")

    def close_datasets(self):
        """Close open datasets."""
        if self.etopo_ds is not None:
            self.etopo_ds.close()
        if self.snow_src is not None:
            self.snow_src.close()

    def process_all_cells(self) -> pl.DataFrame:
        """
        Generate equal-area grid and process elevation/snow data for entire globe.

        Returns:
            DataFrame with columns: lat_a_deg, lat_b_deg, lat_centre_deg,
            lng_a_deg, lng_b_deg, lng_centre_deg, elevation, snow_fraction,
            water_height_mm, land_height_mm, snow_height_mm
        """
        # Generate equal-area grid for full globe
        logger.info("Generating equal-area grid cells...")
        cells = build_equal_area_grid(
            min_lat_deg=-90.0,
            max_lat_deg=90.0,
            min_lng_deg=-180.0,
            max_lng_deg=180.0,
            step_deg=self.config.step_deg
        )

        # Sample elevation at cell centers (vectorized for speed)
        logger.info("Sampling elevation data...")

        # Convert cells to arrays for vectorized operations
        cells_array = np.array(cells)
        lat_centres = cells_array[:, 2]  # lat_centre column
        lng_centres = cells_array[:, 5]  # lng_centre column

        # Vectorized interpolation - much faster than looping
        elevations = self.etopo_ds["z"].interp(
            x=xr.DataArray(lng_centres, dims="points"),
            y=xr.DataArray(lat_centres, dims="points"),
            kwargs={"fill_value": np.nan},
        ).values

        # Build DataFrame directly from array
        cells_df = pl.DataFrame({
            "lat_a_deg": cells_array[:, 0],
            "lat_b_deg": cells_array[:, 1],
            "lat_centre_deg": cells_array[:, 2],
            "lng_a_deg": cells_array[:, 3],
            "lng_b_deg": cells_array[:, 4],
            "lng_centre_deg": cells_array[:, 5],
            "elevation": elevations,
        })

        # Add snow data if available
        if self.snow_src:
            logger.info("Sampling snow coverage data...")
            cells_df = self._add_snow_data(cells_df)
        else:
            cells_df = cells_df.with_columns(pl.lit(0.0).alias("snow_fraction"))

        # Calculate heights
        logger.info("Calculating physical heights...")
        cells_df = self._calculate_heights(cells_df)

        logger.info(f"Processed {len(cells_df)} cells")
        return cells_df

    def _add_snow_data(self, cells_df: pl.DataFrame) -> pl.DataFrame:
        """Add snow coverage data to cells DataFrame."""
        latc = cells_df["lat_centre_deg"].to_numpy()
        lngc = cells_df["lng_centre_deg"].to_numpy()

        coords = list(zip(lngc, latc))
        samples = np.array(
            [val[0] for val in self.snow_src.sample(coords)],
            dtype="float32"
        )

        snow = samples.copy()
        nodata = self.snow_src.nodata
        if nodata is not None:
            snow[snow == nodata] = np.nan
        snow[snow > 100] = np.nan

        return cells_df.with_columns(pl.Series("snow_fraction", snow))

    def _calculate_heights(self, cells_df: pl.DataFrame) -> pl.DataFrame:
        """Calculate water, land, and snow heights in millimeters."""
        # Calculate elevation scaling
        max_elevation = cells_df["elevation"].max()
        min_elevation = cells_df["elevation"].min()
        elevation_range = max_elevation - min_elevation
        elevation_to_mm = self.config.elevation_range_mm / elevation_range

        # Store core radius for geometry generation
        self.config.core_radius_mm = self.config.radius_mm + min_elevation * elevation_to_mm
        logger.info(f"Core radius: {self.config.core_radius_mm:.3f} mm")

        # Water height (ocean depth)
        cells_df = cells_df.with_columns([
            (
                (
                    -min_elevation +
                    pl.col("elevation").clip(upper_bound=0)
                ) * elevation_to_mm
            ).alias("water_height_mm")
        ])

        # Snow height (only for cells with ≥90% snow coverage on land)
        cells_df = cells_df.with_columns([
            pl.when(
                (pl.col("snow_fraction").fill_nan(0.0).fill_null(0.0) < 90.0) |
                (pl.col("elevation") < 0)
            )
            .then(0.0)
            .otherwise(
                (pl.col("elevation") * elevation_to_mm).clip(lower_bound=self.config.min_height_mm)
            )
            .alias("snow_height_mm")
        ])

        # Land height (bare land, not snow or water)
        cells_df = cells_df.with_columns([
            pl.when(
                (pl.col("snow_fraction").fill_nan(0.0).fill_null(0.0) >= 90.0) |
                (pl.col("elevation") < 0)
            )
            .then(0.0)
            .otherwise(
                (pl.col("elevation") * elevation_to_mm).clip(lower_bound=self.config.min_height_mm)
            )
            .alias("land_height_mm")
        ])

        return cells_df

    def _calculate_heights_for_segment(self, cells_df: pl.DataFrame) -> pl.DataFrame:
        """
        Calculate water, land, and snow heights using pre-computed global elevation range.

        This ensures consistent scaling across all segments.
        """
        # Water height (ocean depth)
        cells_df = cells_df.with_columns([
            (
                (
                    -self.global_min_elevation +
                    pl.col("elevation").clip(upper_bound=0)
                ) * self.elevation_to_mm
            ).alias("water_height_mm")
        ])

        # Snow height (only for cells with ≥90% snow coverage on land)
        cells_df = cells_df.with_columns([
            pl.when(
                (pl.col("snow_fraction").fill_nan(0.0).fill_null(0.0) < 90.0) |
                (pl.col("elevation") < 0)
            )
            .then(0.0)
            .otherwise(
                (pl.col("elevation") * self.elevation_to_mm).clip(lower_bound=self.config.min_height_mm)
            )
            .alias("snow_height_mm")
        ])

        # Land height (bare land, not snow or water)
        cells_df = cells_df.with_columns([
            pl.when(
                (pl.col("snow_fraction").fill_nan(0.0).fill_null(0.0) >= 90.0) |
                (pl.col("elevation") < 0)
            )
            .then(0.0)
            .otherwise(
                (pl.col("elevation") * self.elevation_to_mm).clip(lower_bound=self.config.min_height_mm)
            )
            .alias("land_height_mm")
        ])

        return cells_df

    def process_segment_cells(self, segment: SegmentDefinition) -> pl.DataFrame:
        """
        Generate and process cells for a specific segment.

        This ensures cell boundaries align exactly with segment boundaries,
        which is critical for proper assembly when gluing segments together.

        Args:
            segment: Segment definition with lat/lon boundaries

        Returns:
            DataFrame with processed cells aligned to segment boundaries
        """
        # Generate cells aligned to segment boundaries
        cells = build_equal_area_grid(
            min_lat_deg=segment.lat_min,
            max_lat_deg=segment.lat_max,
            min_lng_deg=segment.lon_min,
            max_lng_deg=segment.lon_max,
            step_deg=self.config.step_deg
        )

        if len(cells) == 0:
            return pl.DataFrame()

        # Convert cells to arrays for vectorized operations
        cells_array = np.array(cells)
        lat_centres = cells_array[:, 2]
        lng_centres = cells_array[:, 5]

        # Vectorized interpolation
        elevations = self.etopo_ds["z"].interp(
            x=xr.DataArray(lng_centres, dims="points"),
            y=xr.DataArray(lat_centres, dims="points"),
            kwargs={"fill_value": np.nan},
        ).values

        # Build DataFrame
        cells_df = pl.DataFrame({
            "lat_a_deg": cells_array[:, 0],
            "lat_b_deg": cells_array[:, 1],
            "lat_centre_deg": cells_array[:, 2],
            "lng_a_deg": cells_array[:, 3],
            "lng_b_deg": cells_array[:, 4],
            "lng_centre_deg": cells_array[:, 5],
            "elevation": elevations,
        })

        # Add snow data if available
        if self.snow_src:
            cells_df = self._add_snow_data(cells_df)
        else:
            cells_df = cells_df.with_columns(pl.lit(0.0).alias("snow_fraction"))

        # Calculate heights using global min/max elevation
        # (computed once during initialization)
        cells_df = self._calculate_heights_for_segment(cells_df)

        return cells_df

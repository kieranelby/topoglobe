#!/usr/bin/env python3
"""
Generate 3D-printable globe segments using FreeCAD.

Usage:
    python3 globe.py                    # Generate all 48 segments (no snow)
    python3 globe.py -s N60-90_E000-090 # Generate specific segment
    python3 globe.py --snow             # Enable snow layer
"""

import sys
import logging
import argparse
from pathlib import Path

from globe_generator.config import GlobeConfig
from globe_generator.data_processor import DataProcessor
from globe_generator.segment_generator import generate_segment_definitions
from globe_generator.mesh_generator import generate_segment_mesh


def setup_logging(verbose: bool):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=level,
        datefmt='%H:%M:%S'
    )


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate 3D-printable globe segments"
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)"
    )
    parser.add_argument(
        "--segments", "-s",
        nargs="+",
        help="Generate specific segments (e.g., N60-90_E000-090)"
    )
    parser.add_argument(
        "--output-dir", "-o",
        help="Override output directory from config"
    )
    parser.add_argument(
        "--snow",
        action="store_true",
        help="Enable snow layer (default: disabled)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=== Globe Segment Generator ===")

    # Load configuration
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)

    logger.info(f"Loading configuration from {config_path}")
    config = GlobeConfig.from_yaml(str(config_path))

    # Override config with CLI arguments
    if args.output_dir:
        config.output_dir = args.output_dir
    if not args.snow:
        config.snow_path = None

    # Create output directory
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load and process data
    processor = DataProcessor(config)

    try:
        logger.info("Loading elevation and snow data...")
        processor.load_datasets()

        logger.info("Computing global elevation range...")
        processor.compute_global_elevation_range()

        # Determine which segments to generate
        all_segments = generate_segment_definitions()
        logger.info(f"Total segments defined: {len(all_segments)}")

        if args.segments:
            # Filter to requested segments
            requested = set(args.segments)
            segments = [s for s in all_segments if s.segment_id in requested]
            if not segments:
                logger.error(f"No matching segments found for: {args.segments}")
                sys.exit(1)
            logger.info(f"Generating {len(segments)} requested segments")
        else:
            segments = all_segments
            logger.info(f"Generating all {len(segments)} segments")

        # Generate each segment
        success_count = 0
        fail_count = 0

        for i, segment in enumerate(segments, 1):
            logger.info(f"\n[{i}/{len(segments)}] Processing {segment.segment_id}")

            try:
                # Generate cells aligned to segment boundaries
                segment_cells = processor.process_segment_cells(segment)
                logger.info(f"  {len(segment_cells)} cells in segment")

                if len(segment_cells) == 0:
                    logger.warning(f"  Skipping - no cells in segment")
                    continue

                # Output path
                output_path = output_dir / f"{segment.segment_id}.3mf"

                # Generate using pure-Python mesh generation
                success = generate_segment_mesh(
                    segment_cells,
                    segment,
                    config,
                    output_path
                )

                if success:
                    file_size = output_path.stat().st_size / 1024
                    logger.info(f"  ✓ Exported ({file_size:.1f} KB)")
                    success_count += 1
                else:
                    logger.error(f"  ✗ Failed to export")
                    fail_count += 1

            except Exception as e:
                logger.error(f"  ✗ Failed: {e}", exc_info=args.verbose)
                fail_count += 1
                continue

        logger.info("\n=== Generation Complete ===")
        logger.info(f"Successful: {success_count}")
        logger.info(f"Failed: {fail_count}")
        logger.info(f"Output directory: {output_dir.absolute()}")

    finally:
        # Clean up
        processor.close_datasets()


if __name__ == "__main__":
    main()

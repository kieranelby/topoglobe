#!/usr/bin/env python3
"""Test data processing without FreeCAD dependency."""


import logging

from globe_generator.config import GlobeConfig
from globe_generator.data_processor import DataProcessor
from globe_generator.segment_generator import generate_segment_definitions

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def main():
    """Test data processing for one segment."""

    # Load config
    config = GlobeConfig.from_yaml('config.yaml')

    # Create processor
    processor = DataProcessor(config)

    try:
        print("\n=== Testing Data Processing ===\n")

        # Load datasets
        print("1. Loading elevation data...")
        processor.load_datasets()
        print("   ✓ ETOPO1 loaded successfully")
        if config.snow_path:
            print("   ✓ Snow data loaded successfully")

        # Compute global elevation range
        print("\n2. Computing global elevation range...")
        processor.compute_global_elevation_range()
        print(f"   ✓ Core radius: {config.core_radius_mm:.3f} mm")

        # Generate segment definitions
        print("\n3. Generating segment definitions...")
        segments = generate_segment_definitions()
        print(f"   ✓ Generated {len(segments)} segments")

        # Test generating cells for one segment
        test_segment = segments[9]
        print(f"\n4. Testing segment: {test_segment.segment_id}")
        print(f"   Latitude: {test_segment.lat_min}° to {test_segment.lat_max}°")
        print(f"   Longitude: {test_segment.lon_min}° to {test_segment.lon_max}°")

        print("\n5. Generating cells aligned to segment boundaries...")
        segment_cells = processor.process_segment_cells(test_segment)
        print(f"   ✓ Generated {len(segment_cells)} cells")

        # Show sample data
        print("\n6. Sample cell data:")
        print(segment_cells.head(5))

        # Show statistics
        print("\n7. Segment statistics:")
        print(f"   Water cells: {(segment_cells['water_height_mm'] > 0).sum()}")
        print(f"   Land cells: {(segment_cells['land_height_mm'] > 0).sum()}")
        print(f"   Snow cells: {(segment_cells['snow_height_mm'] > 0).sum()}")

        print("\n✓ Data processing test PASSED!")

    finally:
        processor.close_datasets()


if __name__ == "__main__":
    main()

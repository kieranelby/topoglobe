# Data Directory

This directory contains the geospatial data files used to generate the globe segments.

## Required Files

### ETOPO1 Global Relief Model (Required)
- **Filename**: `ETOPO1_Bed_g_gmt4.grd`
- **Size**: ~891 MB
- **Format**: NetCDF (GMT .grd format)
- **Resolution**: 1 arc-minute
- **Download**: https://www.ncei.noaa.gov/products/etopo-global-relief-model
- **Description**: Global elevation data including ocean bathymetry and land topography

### MODIS Snow Cover (Optional)
- **Filename**: `MOD10CM_snow_2024-153.tif` (or similar)
- **Size**: ~25 MB
- **Format**: GeoTIFF in EPSG:4326 projection
- **Download**: https://nsidc.org/data/mod10cm
- **Description**: Monthly snow cover percentage data
- **Note**: Only needed if generating globe segments with snow layer (`--snow` flag)

## File Locations

After downloading, the data files should be placed in this directory:
```
data/
├── ETOPO1_Bed_g_gmt4.grd
└── MOD10CM_snow_2024-153.tif
```

Then update `config.yaml` to point to these files:
```yaml
etopo_path: "./data/ETOPO1_Bed_g_gmt4.grd"
snow_path: "./data/MOD10CM_snow_2024-153.tif"
```

## Note

These files are not included in the repository due to their large size. You must download them separately from the sources listed above.

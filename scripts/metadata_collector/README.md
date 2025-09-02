# PDF Split Rotate - Metadata Collector & Report Generator

A comprehensive metadata analysis and reporting system for the PDF Split Rotate processing system. This toolkit scans processed output files, extracts detailed metadata into a structured Parquet file, and generates interactive HTML reports with visualizations.

## Features

### Metadata Collection (`collect_metadata.py`)
- **Comprehensive Metadata Extraction**: Analyzes output filenames, file system properties, and cross-references with source files
- **Multi-threaded Processing**: Configurable parallel processing with progress bars
- **Parquet Output**: Efficient columnar storage format perfect for data analysis
- **Source File Cross-referencing**: Matches output files with their original source files
- **Highly Configurable**: All paths and processing options configurable via environment variables
- **Robust Filename Parsing**: Handles the complex naming convention used by the processing system

### Report Generation (`generate_report.py`)
- **Interactive HTML Reports**: Beautiful, responsive reports with Plotly visualizations
- **Comprehensive Analytics**: Customer analysis, file size distributions, processing statistics
- **Summary Tables**: Detailed breakdowns by customer, group, and processing metrics
- **Configurable Visualizations**: Customizable color schemes and display options
- **Bootstrap Styling**: Professional, mobile-friendly report layout

### Complete Pipeline (`run_analysis.py`)
- **One-Click Analysis**: Runs both metadata collection and report generation
- **Error Handling**: Comprehensive error handling and logging
- **Performance Reporting**: Execution time tracking and statistics

## Installation

1. Navigate to the metadata collector directory:
```bash
cd scripts/metadata_collector
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy and configure the environment file:
```bash
cp .env.template .env
# Edit .env with your specific paths and settings
```

## Configuration

The scripts are configured via environment variables (`.env` file):

### Core Collection Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `METADATA_OUTPUT_FOLDER` | `./output` | Folder containing processed output files |
| `METADATA_INPUT_FOLDER` | `./input` | Folder containing original source files |
| `METADATA_OUTPUT_FILE` | `./metadata_analysis.parquet` | Output file for metadata |
| `METADATA_MAX_WORKERS` | `8` | Number of worker threads for processing |
| `METADATA_CACHE_WORKERS` | `16` | Number of worker threads for I/O operations |
| `ENABLE_SOURCE_LOOKUP` | `true` | Enable source file cross-referencing |

### Report Generation Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `REPORT_INPUT_FILE` | `./metadata_analysis.parquet` | Input Parquet file for reports |
| `REPORT_OUTPUT_FILE` | `./metadata_report.html` | Output HTML report file |
| `REPORT_TITLE` | `PDF Split Rotate - Processing Report` | Report title |
| `INCLUDE_DETAILED_TABLES` | `true` | Include detailed summary tables |
| `MAX_CUSTOMERS_DISPLAY` | `20` | Max customers to show in charts |
| `COLOR_SCHEME` | `plotly` | Chart color scheme |

## Usage

### Quick Start - Complete Analysis
```bash
# Run both metadata collection and report generation
python run_analysis.py
```

### Individual Scripts

#### Metadata Collection Only
```bash
python collect_metadata.py
```

#### Report Generation Only (requires existing Parquet file)
```bash
python generate_report.py
```

### Advanced Usage Examples

```bash
# High-performance configuration for large remote datasets
METADATA_CACHE_WORKERS=32 METADATA_MAX_WORKERS=16 python collect_metadata.py

# Memory-conscious for very large datasets
METADATA_CHUNK_SIZE=500 CACHE_BATCH_SIZE=100 python collect_metadata.py

# Fast mode without source lookup
ENABLE_SOURCE_LOOKUP=false python collect_metadata.py

# Custom report configuration
REPORT_TITLE="Monthly Processing Report" MAX_CUSTOMERS_DISPLAY=50 python generate_report.py
```

## Report Features

The generated HTML report includes:

### 📊 Summary Statistics Dashboard
- Total files processed and data volume
- Customer and group counts
- Parsing success rates
- Processing timeline information

### 📈 Overview Charts
- **Top Customers by File Count**: Horizontal bar chart of most active customers
- **File Size Distribution**: Histogram showing file size patterns
- **Group Utilization**: Distribution of files across processing groups
- **Processing Timeline**: Daily processing volumes (if applicable)

### 🔍 Detailed Analytics
- **Customer vs Group Heatmap**: Matrix showing customer-group relationships
- **File Size by Customer**: Box plots comparing file sizes across customers
- **Multi-page Analysis**: Breakdown of single vs multi-page source files
- **Source Matching Statistics**: Success rate of source file identification
- **Parsing Success Analysis**: Filename parsing performance by customer

### 📋 Summary Tables
- **Customer Summary**: File counts, sizes, and statistics per customer
- **Group Summary**: Utilization and distribution across groups
- **Error Analysis**: Common parsing errors and their frequency

## Output Schema

The generated Parquet file contains the following columns:

### Primary Identification
- `output_filename`: Name of the output PDF file (PRIMARY KEY)
- `output_path`: Full path to the output file

### Parsed Filename Components
- `customer_clean`: Cleaned customer name from filename
- `group_number`: Group number (for file organization)
- `subfolder_path`: Original subfolder structure
- `source_basename`: Original source filename (without extension)
- `page_number`: Page number (for multi-page sources, NULL for single-page)

### File System Metadata
- `output_size_bytes`: Size of output file in bytes
- `output_created`: Output file creation timestamp
- `output_modified`: Output file modification timestamp

### Source File Information (if `ENABLE_SOURCE_LOOKUP=true`)
- `source_file_exists`: Whether the source file was found
- `source_file_path`: Path to the source file (if found)
- `source_size_bytes`: Size of source file in bytes
- `source_extension`: Source file extension (.pdf, .tif, etc.)
- `source_modified`: Source file modification timestamp

### Analysis Metadata
- `analysis_timestamp`: When this analysis was performed
- `parsing_success`: Whether filename parsing was successful
- `parsing_errors`: Any errors encountered during parsing

## Performance Optimizations

### For Large Remote Folders
- **Parallel cache building**: Uses separate thread pool for I/O operations
- **Batch processing**: Manages memory with configurable chunk sizes
- **Progress tracking**: Real-time feedback during long operations
- **Directory scanning**: Parallel processing of customer folders

### Memory Management
- **Configurable batching**: Process files in chunks to manage memory
- **Efficient caching**: In-memory source file cache with parallel building
- **Streaming processing**: Avoid loading entire datasets at once

## Data Analysis Examples

Once you have the Parquet file, you can analyze it with pandas:

```python
import pandas as pd
import plotly.express as px

# Load the metadata
df = pd.read_parquet('metadata_analysis.parquet')

# Basic statistics
print(f"Total files: {len(df)}")
print(f"Total size: {df['output_size_bytes'].sum() / 1024**3:.2f} GB")
print(f"Customers: {df['customer_clean'].nunique()}")

# Files per customer
customer_stats = df.groupby('customer_clean').agg({
    'output_filename': 'count',
    'output_size_bytes': 'sum'
}).rename(columns={'output_filename': 'file_count'})

# Create custom visualizations
fig = px.treemap(df, path=['customer_clean', 'group_number'], 
                 title="File Distribution by Customer and Group")
fig.show()
```

## Troubleshooting

### Common Issues

1. **No files found**: Check that `METADATA_OUTPUT_FOLDER` points to the correct output directory
2. **Source lookup slow**: Disable with `ENABLE_SOURCE_LOOKUP=false` or reduce `METADATA_CACHE_WORKERS`
3. **Memory issues**: Reduce `METADATA_MAX_WORKERS` and `METADATA_CHUNK_SIZE` for large datasets
4. **Report generation fails**: Ensure Plotly is installed and Parquet file exists
5. **Charts not displaying**: Check that Plotly JavaScript is loading (internet connection required)

### Logging

Both scripts provide comprehensive logging:
- Progress information during processing
- Statistics about parsing success rate
- Source file match rate (if enabled)
- Final summary with execution time
- Error details for troubleshooting

### Dependencies

Make sure all required packages are installed:
```bash
pip install pandas pyarrow tqdm python-dotenv plotly
```

## Integration

This toolkit is designed to work with the main PDF Split Rotate processing system and can be run:
- **Periodically**: To analyze processing results over time
- **On-demand**: For specific analysis needs
- **Automated**: As part of a larger data pipeline
- **Scheduled**: For regular reporting and monitoring

The Parquet output format and HTML reports make it easy to integrate with:
- Data analysis tools (Jupyter notebooks, R, etc.)
- Business intelligence platforms
- Automated reporting systems
- Quality assurance workflows

## Example Workflow

1. **Process documents** with the main PDF Split Rotate system
2. **Run analysis**: `python run_analysis.py`
3. **Review report**: Open `metadata_report.html` in your browser
4. **Deep analysis**: Load `metadata_analysis.parquet` in your preferred analysis tool
5. **Share results**: Distribute the HTML report to stakeholders

#!/usr/bin/env python3
"""
PDF Split Rotate - Mapping Analyzer

Standalone script that scans the WATCH_FOLDER and creates a lookup table
mapping source files to their predicted output filenames (with 'pagex' placeholder).

Uses the same naming logic as the main processing script but without opening files.
Outputs results to CSV, Parquet, and JSON formats in the logs subfolder.
"""

import os
import time
from pathlib import Path
from datetime import datetime
import pandas as pd
import logging
from dotenv import load_dotenv

# Import the same clean_name function used by main script
try:
    from pdf_files_rename import clean_name
except ImportError as e:
    print(f"Error: Could not import clean_name function: {e}")
    print("Make sure pdf_files_rename.py is in the same directory.")
    exit(1)


def setup_logging():
    """Setup logging for the analyzer"""
    # Create logs directory if it doesn't exist
    logs_dir = Path('./logs')
    logs_dir.mkdir(exist_ok=True)
    
    # Setup logging
    log_file = logs_dir / f'mapping_analyzer_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()  # Also log to console
        ]
    )
    return str(log_file)


def load_configuration():
    """Load configuration from .env file, same as main script"""
    try:
        load_dotenv(override=True)
        
        config = {
            'WATCH_FOLDER': os.path.abspath(os.getenv('WATCH_FOLDER', './input')),
            'OUTPUT_FOLDER': os.path.abspath(os.getenv('OUTPUT_FOLDER', './output')),
            'FILENAME_SEPARATOR': os.getenv('FILENAME_SEPARATOR', '__EKR__'),
            'MAX_FILES_PER_GROUP': int(os.getenv('MAX_FILES_PER_GROUP', '10000')),
        }
        
        # Load supported file extensions
        process_extensions_str = os.getenv('PROCESS_EXTENSIONS', '.pdf,.tif,.tiff,.png,.jpg,.jpeg')
        config['PROCESS_EXTENSIONS'] = tuple(ext.strip().lower() for ext in process_extensions_str.split(',') if ext.strip())
        
        # Separate PDF and image extensions
        config['PDF_EXTENSIONS'] = ('.pdf',)
        config['IMAGE_EXTENSIONS'] = tuple(ext for ext in config['PROCESS_EXTENSIONS'] if ext not in config['PDF_EXTENSIONS'])
        
        logging.info(f"Configuration loaded successfully")
        logging.info(f"Watch folder: {config['WATCH_FOLDER']}")
        logging.info(f"Output folder: {config['OUTPUT_FOLDER']}")
        logging.info(f"Supported extensions: {', '.join(config['PROCESS_EXTENSIONS'])}")
        
        return config
        
    except Exception as e:
        logging.error(f"Error loading configuration: {e}")
        raise


def is_supported_file(file_path: str, extensions: tuple) -> bool:
    """Check if file has a supported extension"""
    return file_path.lower().endswith(extensions)


def get_file_type(file_path: str, pdf_ext: tuple, img_ext: tuple) -> str:
    """Determine file type: PDF or Image"""
    if file_path.lower().endswith(pdf_ext):
        return 'PDF'
    elif file_path.lower().endswith(img_ext):
        return 'Image'
    else:
        return 'Unknown'


def analyze_source_file(file_path: str, config: dict) -> dict:
    """
    Analyze a source file and predict its output naming pattern.
    Returns a dictionary with all the analysis data.
    """
    try:
        # Basic file info
        file_stat = os.stat(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # Get relative path from WATCH_FOLDER to file's parent (same logic as main script)
        rel_dir = os.path.relpath(os.path.dirname(file_path), config['WATCH_FOLDER'])
        rel_parts = os.path.normpath(rel_dir).split(os.sep)
        
        # Customer is always the first part, or use filename if directly in input
        if rel_parts and rel_parts[0] != '.' and rel_parts[0] != '':
            customer_folder = rel_parts[0]
            # All subfolders under customer (may be empty)
            subfolders = rel_parts[1:] if len(rel_parts) > 1 else []
        else:
            # Files directly in input folder - use filename as customer
            customer_folder = base_name
            subfolders = []
        
        # Clean names using the same logic as main script
        customer_clean = clean_name(customer_folder, config['OUTPUT_FOLDER'], kind="dir")
        subfolder_clean = '_'.join(''.join(c for c in part if c.isalnum()) for part in subfolders) if subfolders else ''
        base_clean = ''.join(c for c in base_name if c.isalnum())
        
        # Predict target directory
        target_dir = os.path.join(config['OUTPUT_FOLDER'], customer_clean)
        
        # Predict group (using groupx placeholder since we don't know the actual assignment)
        group_clean = 'groupx'  # Placeholder for actual group number
        customer_group = f"{customer_clean}_{group_clean}{config['FILENAME_SEPARATOR']}"
        
        # Build predicted filename with pagex placeholder
        if subfolder_clean:
            name_parts = [subfolder_clean, f"{base_clean}pagex.pdf"]
        else:
            name_parts = [f"{base_clean}pagex.pdf"]
        
        predicted_filename = customer_group + '_'.join(name_parts)
        predicted_output_path = os.path.join(target_dir, 'groupx', predicted_filename)
        
        # Determine file type
        file_type = get_file_type(file_path, config['PDF_EXTENSIONS'], config['IMAGE_EXTENSIONS'])
        
        return {
            'source_path': file_path,
            'source_filename': os.path.basename(file_path),
            'file_type': file_type,
            'source_size_mb': round(file_stat.st_size / (1024*1024), 2),
            'customer_original': customer_folder,
            'customer_cleaned': customer_clean,
            'base_name_cleaned': base_clean,
            'predicted_output_filename': predicted_filename,
            'processing_status': 'analyzed',
            'error_description': '',
        }
        
    except Exception as e:
        # Return partial data with error info
        error_msg = f"Error analyzing {file_path}: {str(e)}"
        logging.error(error_msg)
        
        return {
            'source_path': file_path,
            'source_filename': os.path.basename(file_path) if file_path else 'unknown',
            'file_type': 'unknown',
            'source_size_mb': None,
            'customer_original': 'unknown',
            'customer_cleaned': 'unknown',
            'base_name_cleaned': 'unknown',
            'predicted_output_filename': 'unknown',
            'processing_status': 'error',
            'error_description': error_msg,
        }


def scan_watch_folder(config: dict, output_dir: Path) -> list:
    """
    Scan the WATCH_FOLDER recursively for supported files.
    Writes incremental results and progress logs.
    Returns a list of analysis dictionaries.
    """
    results = []
    total_files = 0
    supported_files = 0
    error_files = 0
    
    # Setup incremental CSV file for real-time preview
    csv_file = output_dir / "mapping_analysis_incremental.csv"
    progress_file = output_dir / "scan_progress.txt"
    csv_written_header = False
    
    try:
        logging.info(f"Starting scan of {config['WATCH_FOLDER']}")
        logging.info(f"Incremental results will be written to: {csv_file}")
        logging.info(f"Progress tracking file: {progress_file}")
        
        # Write initial progress file
        with open(progress_file, 'w') as f:
            f.write(f"Scan started at: {datetime.now().isoformat()}\n")
            f.write(f"Target folder: {config['WATCH_FOLDER']}\n")
            f.write(f"Supported extensions: {', '.join(config['PROCESS_EXTENSIONS'])}\n")
            f.write("=" * 50 + "\n")
        
        for root, dirs, files in os.walk(config['WATCH_FOLDER']):
            logging.info(f"Scanning directory: {root} ({len(files)} files)")
            
            for filename in files:
                total_files += 1
                file_path = os.path.join(root, filename)
                
                # Log progress every 100 files
                if total_files % 100 == 0:
                    progress_msg = f"Progress: {total_files} files scanned, {supported_files} supported, {error_files} errors"
                    logging.info(progress_msg)
                    
                    # Update progress file
                    with open(progress_file, 'a') as f:
                        f.write(f"{datetime.now().strftime('%H:%M:%S')} - {progress_msg}\n")
                
                # Check if file is supported
                if is_supported_file(file_path, config['PROCESS_EXTENSIONS']):
                    supported_files += 1
                    
                    # Analyze the file
                    analysis = analyze_source_file(file_path, config)
                    results.append(analysis)
                    
                    if analysis['processing_status'] == 'error':
                        error_files += 1
                    
                    # Write immediately to incremental CSV for preview
                    df_single = pd.DataFrame([analysis])
                    if not csv_written_header:
                        df_single.to_csv(csv_file, mode='w', index=False, encoding='utf-8')
                        csv_written_header = True
                        logging.info(f"Created incremental CSV file: {csv_file}")
                    else:
                        df_single.to_csv(csv_file, mode='a', header=False, index=False, encoding='utf-8')
                    
                    # Log every 10th supported file for detailed progress
                    if supported_files % 10 == 0:
                        detail_msg = f"Processed {supported_files} supported files. Latest: {analysis['source_filename']} -> {analysis['predicted_output_filename']}"
                        logging.info(detail_msg)
                        
                        # Update progress file with latest file info
                        with open(progress_file, 'a') as f:
                            f.write(f"{datetime.now().strftime('%H:%M:%S')} - {detail_msg}\n")
                    
                    # Save checkpoint every 1000 supported files
                    if supported_files % 1000 == 0:
                        checkpoint_file = output_dir / f"checkpoint_{supported_files}_files.csv"
                        df_checkpoint = pd.DataFrame(results)
                        df_checkpoint.to_csv(checkpoint_file, index=False, encoding='utf-8')
                        logging.info(f"Checkpoint saved: {checkpoint_file} ({len(results)} records)")
        
        final_msg = f"Scan completed: {total_files} total files, {supported_files} supported files, {error_files} errors"
        logging.info(final_msg)
        
        # Final update to progress file
        with open(progress_file, 'a') as f:
            f.write("=" * 50 + "\n")
            f.write(f"{datetime.now().strftime('%H:%M:%S')} - {final_msg}\n")
            f.write(f"Scan completed at: {datetime.now().isoformat()}\n")
        
    except Exception as e:
        logging.error(f"Error during folder scan: {e}")
        # Save whatever we have so far
        if results:
            emergency_file = output_dir / "emergency_backup.csv"
            df_emergency = pd.DataFrame(results)
            df_emergency.to_csv(emergency_file, index=False, encoding='utf-8')
            logging.info(f"Emergency backup saved: {emergency_file}")
        raise
    
    return results


def save_results(results: list, config: dict, output_dir: Path) -> dict:
    """
    Save results to CSV, Parquet, and JSON formats.
    Returns dictionary with output file paths.
    """
    try:
        # Generate timestamp for filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create DataFrame
        df = pd.DataFrame(results)
        
        if df.empty:
            logging.warning("No data to save - DataFrame is empty")
            return {}
        
        # Define output files
        output_files = {
            'csv': output_dir / f'mapping_analysis_{timestamp}.csv',
            'parquet': output_dir / f'mapping_analysis_{timestamp}.parquet',
            'json': output_dir / f'mapping_analysis_{timestamp}.json'
        }
        
        # Save CSV
        df.to_csv(output_files['csv'], index=False, encoding='utf-8')
        logging.info(f"Saved CSV: {output_files['csv']}")
        
        # Save Parquet
        df.to_parquet(output_files['parquet'], index=False)
        logging.info(f"Saved Parquet: {output_files['parquet']}")
        
        # Save JSON
        df.to_json(output_files['json'], orient='records', indent=2, date_format='iso')
        logging.info(f"Saved JSON: {output_files['json']}")
        
        # Log summary statistics
        logging.info(f"Results summary:")
        logging.info(f"  Total records: {len(df)}")
        logging.info(f"  Successful analyses: {len(df[df['processing_status'] == 'analyzed'])}")
        logging.info(f"  Errors: {len(df[df['processing_status'] == 'error'])}")
        logging.info(f"  File types: {df['file_type'].value_counts().to_dict()}")
        
        return {k: str(v) for k, v in output_files.items()}
        
    except Exception as e:
        logging.error(f"Error saving results: {e}")
        raise


def main():
    """Main function"""
    start_time = time.time()
    
    # Setup logging
    log_file = setup_logging()
    logging.info("PDF Split Rotate - Mapping Analyzer started")
    logging.info(f"Log file: {log_file}")
    
    try:
        # Load configuration
        config = load_configuration()
        
        # Verify watch folder exists
        if not os.path.exists(config['WATCH_FOLDER']):
            raise FileNotFoundError(f"Watch folder does not exist: {config['WATCH_FOLDER']}")
        
        # Create output directory early so we can write incremental results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path('./logs/mapping') / timestamp
        output_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f"Output directory created: {output_dir}")
        
        # Scan watch folder with incremental logging
        results = scan_watch_folder(config, output_dir)
        
        if not results:
            logging.warning("No supported files found in watch folder")
            return
        
        # Save final results (the output_dir is already created)
        output_files = save_results(results, config, output_dir)
        
        # Final summary
        elapsed_time = time.time() - start_time
        logging.info(f"Analysis completed in {elapsed_time:.2f} seconds")
        logging.info(f"Output files created:")
        for format_type, file_path in output_files.items():
            logging.info(f"  {format_type.upper()}: {file_path}")
        
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        raise
    
    finally:
        logging.info("PDF Split Rotate - Mapping Analyzer finished")


if __name__ == "__main__":
    main()

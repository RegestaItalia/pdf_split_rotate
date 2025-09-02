#!/usr/bin/env python3
"""
PDF Split Rotate - Metadata Collector

Analyzes existing output files and collects comprehensive metadata into a Parquet file.
This script scans the output folder structure and extracts metadata from filenames,
file system properties, and cross-references with source files.

Features:
- Configurable paths and processing options
- Multi-threaded processing with progress bar
- Parquet output format via pandas
- Comprehensive filename parsing
- Source file cross-referencing
"""

import os
import re
import time
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv

# Load environment variables
# load_dotenv(override=True)

# Configuration
OUTPUT_FOLDER = os.path.abspath(os.getenv('METADATA_OUTPUT_FOLDER', 'W:/01_unzipped/merged'))
INPUT_FOLDER = os.path.abspath(os.getenv('METADATA_INPUT_FOLDER', 'W:/03_processati'))
METADATA_OUTPUT_FILE = os.getenv('METADATA_OUTPUT_FILE', './metadata_analysis.parquet')
MAX_WORKERS = int(os.getenv('METADATA_MAX_WORKERS', '8'))
CACHE_WORKERS = int(os.getenv('METADATA_CACHE_WORKERS', '16'))  # More workers for I/O heavy caching
FILENAME_SEPARATOR = os.getenv('FILENAME_SEPARATOR', '__EKR__')
CHUNK_SIZE = int(os.getenv('METADATA_CHUNK_SIZE', '1000'))
ENABLE_SOURCE_LOOKUP = os.getenv('ENABLE_SOURCE_LOOKUP', 'true').lower() == 'true'
CACHE_BATCH_SIZE = int(os.getenv('CACHE_BATCH_SIZE', '500'))  # Batch size for parallel file operations

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class FileMetadata:
    """Data structure for file metadata"""
    # Primary key
    output_filename: str
    output_path: str
    
    # Parsed from filename
    customer_clean: str
    group_number: int
    subfolder_path: str
    source_basename: str
    page_number: Optional[int]
    
    # File system metadata
    output_size_bytes: int
    output_created: datetime
    output_modified: datetime
    
    # Source file information (if available)
    source_file_exists: bool
    source_file_path: Optional[str]
    source_size_bytes: Optional[int]
    source_extension: Optional[str]
    source_modified: Optional[datetime]
    
    # Analysis metadata
    analysis_timestamp: datetime
    parsing_success: bool
    parsing_errors: str

class FilenameParser:
    """Parser for output filenames following the naming convention"""
    
    def __init__(self, separator: str = '__EKR__'):
        self.separator = separator
        # Pattern: {customer_clean}_{group_clean}{SEPARATOR}{content}
        self.pattern = re.compile(
            rf'^(.+?)_(group\d+){re.escape(separator)}(.*)$'
        )
        self.page_pattern = re.compile(r'page-(\d+)\.pdf$')
    
    def parse(self, filename: str) -> Dict[str, Any]:
        """Parse filename and extract components"""
        result = {
            'customer_clean': '',
            'group_number': 0,
            'subfolder_path': '',
            'source_basename': '',
            'page_number': None,
            'parsing_success': False,
            'parsing_errors': ''
        }
        
        try:
            # Main pattern match
            match = self.pattern.match(filename)
            if not match:
                result['parsing_errors'] = 'Filename does not match expected pattern'
                return result
            
            customer_clean, group_part, content = match.groups()
            result['customer_clean'] = customer_clean
            
            # Extract group number
            group_match = re.match(r'group(\d+)', group_part)
            if group_match:
                result['group_number'] = int(group_match.group(1))
            
            # Parse content part
            # Remove .pdf extension
            if content.endswith('.pdf'):
                content = content[:-4]
            
            # Check for page number
            page_match = self.page_pattern.search(filename)
            if page_match:
                result['page_number'] = int(page_match.group(1))
                # Remove page part from content
                content = re.sub(r'page-\d+$', '', content)
            
            # Split content into subfolder and basename
            parts = content.split('_')
            if len(parts) >= 2:
                # Last part is likely the basename, rest are subfolders
                result['source_basename'] = parts[-1]
                result['subfolder_path'] = '_'.join(parts[:-1])
            elif len(parts) == 1:
                result['source_basename'] = parts[0]
                result['subfolder_path'] = ''
            
            result['parsing_success'] = True
            
        except Exception as e:
            result['parsing_errors'] = str(e)
            logger.warning(f"Error parsing filename {filename}: {e}")
        
        return result

class SourceFileFinder:
    """Finds corresponding source files based on parsed metadata"""
    
    def __init__(self, input_folder: str, cache_workers: int = 16):
        self.input_folder = Path(input_folder)
        self.cache_workers = cache_workers
        self.source_extensions = ['.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg']
        # Build a cache of source files for faster lookup
        self._build_source_cache_parallel()
    
    def _get_file_info(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Get file information for a single file (for parallel processing)"""
        try:
            if file_path.is_file() and file_path.suffix.lower() in self.source_extensions:
                basename = file_path.stem.lower()
                relative_path = file_path.relative_to(self.input_folder)
                return {
                    'basename': basename,
                    'path': file_path,
                    'relative_path': relative_path,
                    'extension': file_path.suffix.lower()
                }
        except Exception as e:
            logger.debug(f"Error processing file {file_path}: {e}")
        return None
    
    def _build_source_cache_parallel(self):
        """Build a cache of source files using parallel processing"""
        self.source_cache = {}
        logger.info("Building source file cache with parallel processing...")
        
        if not self.input_folder.exists():
            logger.warning(f"Input folder does not exist: {self.input_folder}")
            return
        
        # First, collect all potential file paths
        logger.info("Scanning directory structure...")
        all_files = []
        for file_path in self.input_folder.rglob('*'):
            if file_path.suffix.lower() in self.source_extensions:
                all_files.append(file_path)
        
        logger.info(f"Found {len(all_files)} potential source files, processing in parallel...")
        
        # Process files in parallel batches
        processed_count = 0
        with ThreadPoolExecutor(max_workers=self.cache_workers) as executor:
            # Process in batches to manage memory
            for i in range(0, len(all_files), CACHE_BATCH_SIZE):
                batch = all_files[i:i + CACHE_BATCH_SIZE]
                
                # Submit batch for parallel processing
                future_to_file = {
                    executor.submit(self._get_file_info, file_path): file_path 
                    for file_path in batch
                }
                
                # Process results
                for future in as_completed(future_to_file):
                    file_info = future.result()
                    if file_info:
                        basename = file_info['basename']
                        if basename not in self.source_cache:
                            self.source_cache[basename] = []
                        self.source_cache[basename].append({
                            'path': file_info['path'],
                            'relative_path': file_info['relative_path'],
                            'extension': file_info['extension']
                        })
                    processed_count += 1
                
                # Progress update for large datasets
                if len(all_files) > 10000:
                    logger.info(f"Processed {processed_count}/{len(all_files)} files...")
        
        logger.info(f"Built source cache with {len(self.source_cache)} unique basenames from {processed_count} files")
    
    def _build_source_cache(self):
        """Build a cache of source files for faster lookup"""
        self.source_cache = {}
        logger.info("Building source file cache...")
        
        if not self.input_folder.exists():
            logger.warning(f"Input folder does not exist: {self.input_folder}")
            return
        
        for file_path in self.input_folder.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in self.source_extensions:
                # Store by basename without extension for easier matching
                basename = file_path.stem.lower()
                relative_path = file_path.relative_to(self.input_folder)
                
                if basename not in self.source_cache:
                    self.source_cache[basename] = []
                self.source_cache[basename].append({
                    'path': file_path,
                    'relative_path': relative_path,
                    'extension': file_path.suffix.lower()
                })
        
        logger.info(f"Built source cache with {len(self.source_cache)} unique basenames")
    
    def find_source_file(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Find the corresponding source file"""
        result = {
            'source_file_exists': False,
            'source_file_path': None,
            'source_size_bytes': None,
            'source_extension': None,
            'source_modified': None
        }
        
        if not self.source_cache:
            return result
        
        # Try to match by source basename
        basename_clean = parsed_data['source_basename'].lower()
        
        if basename_clean in self.source_cache:
            candidates = self.source_cache[basename_clean]
            
            # If multiple candidates, try to match by subfolder structure
            best_match = None
            if len(candidates) == 1:
                best_match = candidates[0]
            else:
                # Try to find best match based on subfolder structure
                subfolder_parts = parsed_data['subfolder_path'].split('_') if parsed_data['subfolder_path'] else []
                for candidate in candidates:
                    rel_path_parts = candidate['relative_path'].parts[:-1]  # Exclude filename
                    if self._path_similarity(subfolder_parts, rel_path_parts) > 0.5:
                        best_match = candidate
                        break
                
                # If no good match, take the first one
                if best_match is None:
                    best_match = candidates[0]
            
            if best_match and best_match['path'].exists():
                try:
                    stat = best_match['path'].stat()
                    result.update({
                        'source_file_exists': True,
                        'source_file_path': str(best_match['path']),
                        'source_size_bytes': stat.st_size,
                        'source_extension': best_match['extension'],
                        'source_modified': datetime.fromtimestamp(stat.st_mtime)
                    })
                except Exception as e:
                    logger.warning(f"Error accessing source file {best_match['path']}: {e}")
        
        return result
    
    def _path_similarity(self, parts1: List[str], parts2: List[str]) -> float:
        """Calculate similarity between two path component lists"""
        if not parts1 and not parts2:
            return 1.0
        if not parts1 or not parts2:
            return 0.0
        
        # Simple similarity based on common elements
        set1 = set(p.lower() for p in parts1)
        set2 = set(p.lower() for p in parts2)
        if not set1 and not set2:
            return 1.0
        return len(set1.intersection(set2)) / len(set1.union(set2))

class MetadataCollector:
    """Main class for collecting metadata from output files"""
    
    def __init__(self, output_folder: str, input_folder: str, enable_source_lookup: bool = True, cache_workers: int = 16):
        self.output_folder = Path(output_folder)
        self.input_folder = Path(input_folder)
        self.enable_source_lookup = enable_source_lookup
        self.cache_workers = cache_workers
        self.parser = FilenameParser()
        self.source_finder = SourceFileFinder(input_folder, cache_workers) if enable_source_lookup else None
        
    def _get_pdf_files_batch(self, directory: Path) -> List[Path]:
        """Get PDF files from a directory (for parallel processing)"""
        pdf_files = []
        try:
            for item in directory.iterdir():
                if item.is_file() and item.suffix.lower() == '.pdf':
                    pdf_files.append(item)
                elif item.is_dir():
                    # Recursively get files from subdirectories
                    pdf_files.extend(self._get_pdf_files_batch(item))
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot access directory {directory}: {e}")
        return pdf_files
    
    def collect_all_files(self) -> List[Path]:
        """Collect all PDF files from the output folder using parallel processing"""
        logger.info(f"Scanning output folder: {self.output_folder}")
        
        if not self.output_folder.exists():
            logger.error(f"Output folder does not exist: {self.output_folder}")
            return []
        
        # Get top-level directories (typically customer folders)
        top_dirs = [d for d in self.output_folder.iterdir() if d.is_dir()]
        
        if not top_dirs:
            # No subdirectories, scan directly
            logger.info("No subdirectories found, scanning output folder directly...")
            pdf_files = []
            for file_path in self.output_folder.rglob('*.pdf'):
                if file_path.is_file():
                    pdf_files.append(file_path)
            logger.info(f"Found {len(pdf_files)} PDF files")
            return pdf_files
        
        logger.info(f"Found {len(top_dirs)} top-level directories, scanning in parallel...")
        
        pdf_files = []
        with ThreadPoolExecutor(max_workers=self.cache_workers) as executor:
            # Submit directory scanning tasks
            future_to_dir = {
                executor.submit(self._get_pdf_files_batch, directory): directory 
                for directory in top_dirs
            }
            
            # Collect results with progress
            for future in tqdm(as_completed(future_to_dir), total=len(top_dirs), desc="Scanning directories"):
                try:
                    dir_files = future.result()
                    pdf_files.extend(dir_files)
                except Exception as e:
                    directory = future_to_dir[future]
                    logger.error(f"Error scanning directory {directory}: {e}")
        
        logger.info(f"Found {len(pdf_files)} PDF files")
        return pdf_files
    
    def process_file(self, file_path: Path) -> FileMetadata:
        """Process a single file and extract metadata"""
        analysis_time = datetime.now()
        
        try:
            # Get file system metadata
            stat = file_path.stat()
            
            # Parse filename
            parsed_data = self.parser.parse(file_path.name)
            
            # Find source file if enabled
            source_data = {}
            if self.enable_source_lookup and self.source_finder:
                source_data = self.source_finder.find_source_file(parsed_data)
            else:
                source_data = {
                    'source_file_exists': False,
                    'source_file_path': None,
                    'source_size_bytes': None,
                    'source_extension': None,
                    'source_modified': None
                }
            
            # Create metadata object
            metadata = FileMetadata(
                output_filename=file_path.name,
                output_path=str(file_path),
                customer_clean=parsed_data['customer_clean'],
                group_number=parsed_data['group_number'],
                subfolder_path=parsed_data['subfolder_path'],
                source_basename=parsed_data['source_basename'],
                page_number=parsed_data['page_number'],
                output_size_bytes=stat.st_size,
                output_created=datetime.fromtimestamp(stat.st_ctime),
                output_modified=datetime.fromtimestamp(stat.st_mtime),
                source_file_exists=source_data['source_file_exists'],
                source_file_path=source_data['source_file_path'],
                source_size_bytes=source_data['source_size_bytes'],
                source_extension=source_data['source_extension'],
                source_modified=source_data['source_modified'],
                analysis_timestamp=analysis_time,
                parsing_success=parsed_data['parsing_success'],
                parsing_errors=parsed_data['parsing_errors']
            )
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            # Return a minimal metadata object with error info
            return FileMetadata(
                output_filename=file_path.name,
                output_path=str(file_path),
                customer_clean='',
                group_number=0,
                subfolder_path='',
                source_basename='',
                page_number=None,
                output_size_bytes=0,
                output_created=analysis_time,
                output_modified=analysis_time,
                source_file_exists=False,
                source_file_path=None,
                source_size_bytes=None,
                source_extension=None,
                source_modified=None,
                analysis_timestamp=analysis_time,
                parsing_success=False,
                parsing_errors=str(e)
            )
    
    def collect_metadata(self, max_workers: int = 8) -> pd.DataFrame:
        """Collect metadata from all files using multi-threading"""
        files = self.collect_all_files()
        
        if not files:
            logger.warning("No files found to process")
            return pd.DataFrame()
        
        logger.info(f"Processing {len(files)} files with {max_workers} workers")
        
        metadata_list = []
        
        # Process files in batches to manage memory for very large datasets
        total_batches = (len(files) + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * CHUNK_SIZE
            end_idx = min(start_idx + CHUNK_SIZE, len(files))
            batch_files = files[start_idx:end_idx]
            
            if total_batches > 1:
                logger.info(f"Processing batch {batch_idx + 1}/{total_batches} ({len(batch_files)} files)")
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks for this batch
                future_to_file = {
                    executor.submit(self.process_file, file_path): file_path 
                    for file_path in batch_files
                }
                
                # Process results with progress bar
                batch_desc = f"Batch {batch_idx + 1}/{total_batches}" if total_batches > 1 else "Processing files"
                for future in tqdm(as_completed(future_to_file), total=len(batch_files), desc=batch_desc):
                    try:
                        metadata = future.result()
                        metadata_list.append(asdict(metadata))
                    except Exception as e:
                        file_path = future_to_file[future]
                        logger.error(f"Failed to process {file_path}: {e}")
        
        # Convert to DataFrame
        df = pd.DataFrame(metadata_list)
        
        logger.info(f"Collected metadata for {len(df)} files")
        logger.info(f"Parsing success rate: {df['parsing_success'].mean()*100:.1f}%")
        
        if self.enable_source_lookup:
            source_found_rate = df['source_file_exists'].mean() * 100
            logger.info(f"Source files found: {source_found_rate:.1f}%")
        
        return df
    
    def save_metadata(self, df: pd.DataFrame, output_file: str):
        """Save metadata DataFrame to Parquet file"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Saving metadata to: {output_path}")
        df.to_parquet(output_path, index=False)
        logger.info(f"Metadata saved successfully ({len(df)} records)")
        
        # Log some basic statistics
        logger.info("=== Metadata Statistics ===")
        logger.info(f"Total files: {len(df)}")
        logger.info(f"Unique customers: {df['customer_clean'].nunique()}")
        logger.info(f"Unique groups: {df['group_number'].nunique()}")
        logger.info(f"Total size (MB): {df['output_size_bytes'].sum() / 1024 / 1024:.1f}")
        
        if 'page_number' in df.columns:
            pages_with_numbers = df['page_number'].notna().sum()
            logger.info(f"Multi-page sources: {pages_with_numbers} pages")

def main():
    """Main execution function"""
    start_time = time.time()
    
    logger.info("=== PDF Split Rotate - Metadata Collector ===")
    logger.info(f"Output folder: {OUTPUT_FOLDER}")
    logger.info(f"Input folder: {INPUT_FOLDER}")
    logger.info(f"Max workers: {MAX_WORKERS}")
    logger.info(f"Source lookup: {ENABLE_SOURCE_LOOKUP}")
    logger.info(f"Output file: {METADATA_OUTPUT_FILE}")
    
    # Create collector
    collector = MetadataCollector(
        output_folder=OUTPUT_FOLDER,
        input_folder=INPUT_FOLDER,
        enable_source_lookup=ENABLE_SOURCE_LOOKUP,
        cache_workers=CACHE_WORKERS
    )
    
    # Collect metadata
    df = collector.collect_metadata(max_workers=MAX_WORKERS)
    
    if df.empty:
        logger.warning("No metadata collected")
        return
    
    # Save results
    collector.save_metadata(df, METADATA_OUTPUT_FILE)
    
    execution_time = time.time() - start_time
    logger.info(f"Execution completed in {execution_time:.2f} seconds")

if __name__ == "__main__":
    main()

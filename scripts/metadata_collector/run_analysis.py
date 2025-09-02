#!/usr/bin/env python3
"""
PDF Split Rotate - Complete Analysis Pipeline

Runs both metadata collection and report generation in sequence.
This is a convenience script to perform the complete analysis workflow.
"""

import os
import sys
import time
import logging
from pathlib import Path

# Add current directory to path to import our modules
sys.path.append(str(Path(__file__).parent))

try:
    from collect_metadata import main as collect_main
    from generate_report import main as report_main
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure both collect_metadata.py and generate_report.py are in the same directory")
    sys.exit(1)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Run complete analysis pipeline"""
    start_time = time.time()
    
    logger.info("=== PDF Split Rotate - Complete Analysis Pipeline ===")
    
    # Step 1: Collect metadata
    logger.info("Step 1: Collecting metadata...")
    try:
        if not collect_main():
            logger.error("Metadata collection failed")
            return False
    except Exception as e:
        logger.error(f"Error during metadata collection: {e}")
        return False
    
    # Step 2: Generate report
    logger.info("Step 2: Generating report...")
    try:
        if not report_main():
            logger.error("Report generation failed")
            return False
    except Exception as e:
        logger.error(f"Error during report generation: {e}")
        return False
    
    # Success
    total_time = time.time() - start_time
    logger.info(f"Complete analysis pipeline finished successfully in {total_time:.2f} seconds")
    
    # Show output files
    metadata_file = os.getenv('METADATA_OUTPUT_FILE', './metadata_analysis.parquet')
    report_file = os.getenv('REPORT_OUTPUT_FILE', './metadata_report.html')
    
    logger.info("=== Analysis Complete ===")
    logger.info(f"Metadata file: {os.path.abspath(metadata_file)}")
    logger.info(f"Report file: {os.path.abspath(report_file)}")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

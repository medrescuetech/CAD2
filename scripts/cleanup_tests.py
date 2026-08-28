#!/usr/bin/env python3
"""
Test Artifact Cleanup Script

This script cleans up old test artifacts including:
- Old test log files
- Screenshots
- Temporary files
"""
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_cleanup')

# Configuration
KEEP_LAST_N_LOGS = 10  # Number of most recent log files to keep
KEEP_LAST_N_SCREENSHOTS = 20  # Number of most recent screenshots to keep
DAYS_TO_KEEP_REPORTS = 7  # Keep reports newer than this many days

# Directories
BASE_DIR = Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / 'logs'
SCREENSHOTS_DIR = LOGS_DIR / 'screenshots'
REPORTS_DIR = BASE_DIR / 'reports'

def cleanup_old_files(directory: Path, pattern: str, keep_last_n: int):
    """Remove old files matching pattern, keeping the most recent n files."""
    if not directory.exists():
        logger.info(f"Directory does not exist: {directory}")
        return
        
    try:
        # Get all matching files sorted by modification time (newest first)
        files = sorted(
            directory.glob(pattern),
            key=os.path.getmtime,
            reverse=True
        )
        
        # Keep the most recent n files
        for file in files[keep_last_n:]:
            try:
                if file.is_file():
                    file.unlink()
                    logger.debug(f"Removed old file: {file}")
                elif file.is_dir():
                    shutil.rmtree(file)
                    logger.debug(f"Removed old directory: {file}")
            except Exception as e:
                logger.error(f"Error removing {file}: {str(e)}")
                
    except Exception as e:
        logger.error(f"Error cleaning up {directory}/{pattern}: {str(e)}")

def cleanup_old_reports():
    """Remove report files older than configured days."""
    if not REPORTS_DIR.exists():
        return
        
    cutoff_date = datetime.now() - timedelta(days=DAYS_TO_KEEP_REPORTS)
    
    for report_file in REPORTS_DIR.glob('**/*'):
        if not report_file.is_file():
            continue
            
        try:
            mtime = datetime.fromtimestamp(report_file.stat().st_mtime)
            if mtime < cutoff_date:
                report_file.unlink()
                logger.debug(f"Removed old report: {report_file}")
        except Exception as e:
            logger.error(f"Error removing report {report_file}: {str(e)}")

def cleanup_screenshots():
    """Clean up old screenshot files."""
    if not SCREENSHOTS_DIR.exists():
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        return
        
    cleanup_old_files(SCREENSHOTS_DIR, '*.png', KEEP_LAST_N_SCREENSHOTS)

def main():
    """Main cleanup function."""
    logger.info("Starting test artifact cleanup...")
    
    # Create necessary directories if they don't exist
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Clean up old logs
    logger.info("Cleaning up old log files...")
    cleanup_old_files(LOGS_DIR / 'tests', 'test_*.log', KEEP_LAST_N_LOGS)
    
    # Clean up old screenshots
    logger.info("Cleaning up old screenshots...")
    cleanup_screenshots()
    
    # Clean up old reports
    logger.info("Cleaning up old reports...")
    cleanup_old_reports()
    
    logger.info("Cleanup completed successfully")

if __name__ == "__main__":
    main()

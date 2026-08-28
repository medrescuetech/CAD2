"""
File Utility functions for the CAD system.
Contains utility functions for file and directory operations.
"""

import os
import shutil
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def ensure_directory_exists(directory_path):
    """
    Ensure that a directory exists, creating it if it doesn't.
    
    Args:
        directory_path: Path to the directory to check/create
        
    Returns:
        bool: True if the directory exists or was created successfully
    """
    try:
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)
            logger.info(f"Created directory: {directory_path}")
        return True
    except Exception as e:
        logger.error(f"Error creating directory {directory_path}: {str(e)}")
        return False

def safe_filename(filename):
    """
    Make a filename safe for all operating systems
    
    Args:
        filename: The filename to make safe
        
    Returns:
        str: Safe filename
    """
    # Replace unsafe characters with underscores
    unsafe_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
    return filename

def get_file_size(file_path):
    """
    Get the size of a file in a human-readable format.
    
    Args:
        file_path: Path to the file
        
    Returns:
        str: Human-readable file size (e.g., "1.2 MB")
    """
    try:
        size_bytes = os.path.getsize(file_path)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
    except Exception as e:
        logger.error(f"Error getting file size for {file_path}: {str(e)}")
        return "Unknown"

def copy_file(src, dest):
    """
    Copy a file from source to destination with error handling.
    
    Args:
        src: Source file path
        dest: Destination file path
        
    Returns:
        bool: True if copy was successful
    """
    try:
        shutil.copy2(src, dest)
        return True
    except Exception as e:
        logger.error(f"Error copying file from {src} to {dest}: {str(e)}")
        return False

def get_file_extension(filename):
    """
    Get the extension of a file.
    
    Args:
        filename: The filename
        
    Returns:
        str: The file extension without the dot
    """
    return os.path.splitext(filename)[1][1:].lower()

def get_timestamp_filename(base_name, extension):
    """
    Generate a filename with the current timestamp.
    
    Args:
        base_name: Base name for the file
        extension: File extension (without the dot)
        
    Returns:
        str: Filename with timestamp
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base_name}_{timestamp}.{extension}"

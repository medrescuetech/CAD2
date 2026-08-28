"""
Terminal Logger Module

This module provides functionality to capture all terminal outputs (stdout and stderr)
and redirect them to log files in addition to the console.
"""
import os
import sys
import logging
import datetime


class TerminalOutputLogger:
    """
    Logger class that captures stdout and stderr and redirects them to log files
    while also maintaining the original output to the console.
    """
    def __init__(self, log_dir='new_log'):
        """Initialize the terminal output logger."""
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        # Create log files with timestamp and process ID
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        pid = os.getpid()
        
        # Create log files
        self.stdout_log_path = f"{log_dir}/stdout_{timestamp}_{pid}.log"
        self.stderr_log_path = f"{log_dir}/stderr_{timestamp}_{pid}.log"
        self.combined_log_path = f"{log_dir}/terminal_{timestamp}_{pid}.log"
        
        # Open log files
        self.stdout_log = open(self.stdout_log_path, 'a', encoding='utf-8')
        self.stderr_log = open(self.stderr_log_path, 'a', encoding='utf-8')
        self.combined_log = open(self.combined_log_path, 'a', encoding='utf-8')
        
        # Store original stdout and stderr
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
        # Set up logger for terminal output
        self.logger = logging.getLogger('terminal')
        handler = logging.FileHandler(f"{log_dir}/terminal_output.log")
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
        
        # Log initialization
        self.logger.info(f"Terminal logger initialized. PID: {pid}")
        self.logger.info(f"Stdout log: {self.stdout_log_path}")
        self.logger.info(f"Stderr log: {self.stderr_log_path}")
        self.logger.info(f"Combined log: {self.combined_log_path}")

    def start(self):
        """Start capturing stdout and stderr."""
        # Replace stdout and stderr with our custom file-like objects
        sys.stdout = self.StdoutLogger(self.stdout_log, self.combined_log, self.original_stdout)
        sys.stderr = self.StderrLogger(self.stderr_log, self.combined_log, self.original_stderr)
        self.logger.info("Started capturing stdout and stderr")

    def stop(self):
        """Stop capturing stdout and stderr and close log files."""
        # Restore original stdout and stderr
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        
        # Close log files
        self.stdout_log.close()
        self.stderr_log.close()
        self.combined_log.close()
        
        self.logger.info("Stopped capturing stdout and stderr")
    
    class StdoutLogger:
        """Custom file-like object that captures stdout."""
        def __init__(self, log_file, combined_log, original_stdout):
            self.log_file = log_file
            self.combined_log = combined_log
            self.original_stdout = original_stdout
        
        def write(self, message):
            # Write to original stdout
            self.original_stdout.write(message)
            
            # Write to log files
            self.log_file.write(message)
            self.combined_log.write(f"[STDOUT] {message}")
            
            # Flush to ensure immediate writing
            self.log_file.flush()
            self.combined_log.flush()
        
        def flush(self):
            # Flush all outputs
            self.original_stdout.flush()
            self.log_file.flush()
            self.combined_log.flush()
    
    class StderrLogger:
        """Custom file-like object that captures stderr."""
        def __init__(self, log_file, combined_log, original_stderr):
            self.log_file = log_file
            self.combined_log = combined_log
            self.original_stderr = original_stderr
        
        def write(self, message):
            # Write to original stderr
            self.original_stderr.write(message)
            
            # Write to log files
            self.log_file.write(message)
            self.combined_log.write(f"[STDERR] {message}")
            
            # Flush to ensure immediate writing
            self.log_file.flush()
            self.combined_log.flush()
        
        def flush(self):
            # Flush all outputs
            self.original_stderr.flush()
            self.log_file.flush()
            self.combined_log.flush()


def init_terminal_logging():
    """Initialize terminal output logging."""
    terminal_logger = TerminalOutputLogger()
    terminal_logger.start()
    return terminal_logger

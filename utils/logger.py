"""Log file management for Playlist Administrator"""

import os
import time
from datetime import datetime
from pathlib import Path
import threading

class LogFileManager:
    """Manages log file writing with rotation and cleanup"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.log_file = None
        self.log_path = None
        self.enabled = False
        self._write_lock = threading.Lock()
    
    def enable(self, base_path, max_files=10):
        """Enable log file writing"""
        log_dir = os.path.join(base_path, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Create timestamped log file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_path = os.path.join(log_dir, f'session_{timestamp}.log')
        self.log_file = open(self.log_path, 'w', encoding='utf-8', buffering=1)
        self.enabled = True
        
        # Write header
        self._write_raw(f"=== Playlist Administrator Log ===\n")
        self._write_raw(f"Session started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self._write_raw(f"=" * 50 + "\n\n")
        
        # Cleanup old log files
        self._cleanup_old_logs(log_dir, max_files)
        
        return self.log_path
    
    def disable(self):
        """Disable log file writing"""
        if self.log_file:
            self._write_raw(f"\n=== Session ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            self.log_file.close()
            self.log_file = None
        self.enabled = False
    
    def _write_raw(self, text):
        """Write raw text to log file"""
        if self.enabled and self.log_file:
            with self._write_lock:
                try:
                    self.log_file.write(text)
                    self.log_file.flush()
                except Exception:
                    pass  # Silently fail if file write fails
    
    def log(self, message, level='INFO'):
        """Write a log message with timestamp"""
        if not self.enabled:
            return
        
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        log_line = f"[{timestamp}] [{level}] {message}\n"
        self._write_raw(log_line)
    
    def _cleanup_old_logs(self, log_dir, max_files):
        """Remove old log files, keeping only the most recent ones"""
        try:
            log_files = sorted(
                [f for f in os.listdir(log_dir) if f.startswith('session_') and f.endswith('.log')],
                key=lambda f: os.path.getmtime(os.path.join(log_dir, f)),
                reverse=True
            )
            for old_file in log_files[max_files:]:
                try:
                    os.remove(os.path.join(log_dir, old_file))
                except Exception:
                    pass
        except Exception:
            pass

# Global instance
LOG_MANAGER = LogFileManager()

def enable_file_logging(base_path, max_files=10):
    """Enable file logging"""
    return LOG_MANAGER.enable(base_path, max_files)

def disable_file_logging():
    """Disable file logging"""
    LOG_MANAGER.disable()

def log_to_file(message, level='INFO'):
    """Write message to log file if enabled"""
    LOG_MANAGER.log(message, level)

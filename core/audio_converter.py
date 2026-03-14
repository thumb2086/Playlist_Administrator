"""
Audio Converter Utility
Handles conversion between different audio formats (MP3, FLAC, etc.)
"""

import os
import subprocess
import tempfile
from pathlib import Path

def convert_audio_file(input_path, output_path, target_format, log_func=None):
    """
    Convert audio file to target format using ffmpeg
    
    Args:
        input_path: Path to input audio file
        output_path: Path for output audio file
        target_format: Target format ('mp3' or 'flac')
        log_func: Optional logging function
    
    Returns:
        bool: True if conversion successful, False otherwise
    """
    try:
        # Check if input file exists
        if not os.path.exists(input_path):
            if log_func:
                log_func(f"  ❌ Input file not found: {input_path}")
            return False
        
        # Get input file extension
        input_ext = Path(input_path).suffix.lower()
        output_ext = Path(output_path).suffix.lower()
        
        # If already in target format, just copy
        if input_ext == f".{target_format}":
            import shutil
            shutil.copy2(input_path, output_path)
            if log_func:
                log_func(f"  📋 Copied (already {target_format.upper()}): {os.path.basename(input_path)}")
            return True
        
        # Prepare ffmpeg command
        if target_format == 'mp3':
            # High quality MP3 conversion
            cmd = [
                'ffmpeg', '-y',  # Overwrite output files
                '-i', input_path,
                '-codec:a', 'libmp3lame',
                '-qscale:a', '0',  # Highest quality VBR
                '-ar', '44100',    # Sample rate
                output_path
            ]
        elif target_format == 'flac':
            # Lossless FLAC conversion
            cmd = [
                'ffmpeg', '-y',
                '-i', input_path,
                '-codec:a', 'flac',
                '-compression_level', '8',  # Good compression
                output_path
            ]
        else:
            if log_func:
                log_func(f"  ❌ Unsupported target format: {target_format}")
            return False
        
        # Run conversion
        if log_func:
            log_func(f"  🔄 Converting to {target_format.upper()}: {os.path.basename(input_path)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=300  # 5 minute timeout per file
        )
        
        if result.returncode == 0:
            if log_func:
                log_func(f"  ✅ Converted: {os.path.basename(input_path)} → {os.path.basename(output_path)}")
            return True
        else:
            if log_func:
                log_func(f"  ❌ Conversion failed: {os.path.basename(input_path)}")
                log_func(f"     Error: {result.stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        if log_func:
            log_func(f"  ⏱️ Conversion timeout: {os.path.basename(input_path)}")
        return False
    except Exception as e:
        if log_func:
            log_func(f"  ❌ Conversion error: {os.path.basename(input_path)} - {str(e)}")
        return False

def convert_audio_if_needed(input_path, target_format, log_func=None):
    """
    Convert audio file if it's not already in target format
    
    Args:
        input_path: Path to input audio file
        target_format: Target format ('mp3', 'flac', or 'original')
        log_func: Optional logging function
    
    Returns:
        str: Path to the file in target format (original or converted)
        bool: True if conversion was performed, False if original was used
    """
    if target_format == 'original':
        return input_path, False
    
    input_ext = Path(input_path).suffix.lower()
    target_ext = f".{target_format}"
    
    # If already in target format, return original
    if input_ext == target_ext:
        return input_path, False
    
    # Create temporary output path
    temp_dir = tempfile.gettempdir()
    base_name = Path(input_path).stem
    output_path = os.path.join(temp_dir, f"{base_name}{target_ext}")
    
    # Perform conversion
    success = convert_audio_file(input_path, output_path, target_format, log_func)
    
    if success:
        return output_path, True
    else:
        # If conversion fails, return original
        if log_func:
            log_func(f"  ⚠️ Using original file due to conversion failure: {os.path.basename(input_path)}")
        return input_path, False

def check_ffmpeg_available():
    """Check if ffmpeg is available in the system"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def get_audio_format(file_path):
    """Get the audio format of a file"""
    ext = Path(file_path).suffix.lower()
    format_map = {
        '.mp3': 'mp3',
        '.flac': 'flac',
        '.m4a': 'm4a',
        '.wav': 'wav',
        '.webm': 'webm'
    }
    return format_map.get(ext, 'unknown')

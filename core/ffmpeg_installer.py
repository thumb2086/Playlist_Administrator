#!/usr/bin/env python3
"""
FFmpeg 自動安裝模組

提供自動下載和安裝 FFmpeg 的功能
"""

import os
import sys
import requests
import zipfile
import shutil
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlparse
import json

# FFmpeg 下載 URL (Windows 64-bit)
FFMPEG_DOWNLOAD_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
FFMPEG_FILENAME = "ffmpeg-master-latest-win64-gpl.zip"
FFMPEG_EXE_NAME = "ffmpeg.exe"

def check_ffmpeg_installed():
    """檢查 FFmpeg 是否已安裝"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def check_local_ffmpeg(ffmpeg_path):
    """檢查本地 FFmpeg 是否存在且可執行"""
    if not ffmpeg_path:
        return False
    
    # 處理相對路徑
    if not os.path.isabs(ffmpeg_path):
        # 如果是相對路徑，相對於程式目錄
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ffmpeg_path = os.path.join(app_dir, ffmpeg_path)
    
    if not os.path.exists(ffmpeg_path):
        return False
    
    try:
        result = subprocess.run([ffmpeg_path, '-version'], 
                              capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False

def download_ffmpeg(progress_callback=None):
    """下載 FFmpeg"""
    try:
        print("正在下載 FFmpeg...")
        
        # 創建臨時目錄
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, FFMPEG_FILENAME)
            
            # 下載檔案
            response = requests.get(FFMPEG_DOWNLOAD_URL, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            progress = (downloaded / total_size) * 100
                            progress_callback(progress)
            
            print("正在解壓縮 FFmpeg...")
            
            # 解壓縮
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # 找到 ffmpeg.exe
            ffmpeg_dir = None
            for root, dirs, files in os.walk(temp_dir):
                if FFMPEG_EXE_NAME in files:
                    ffmpeg_dir = root
                    break
            
            if not ffmpeg_dir:
                raise Exception("在壓縮檔中找不到 ffmpeg.exe")
            
            # 創建 bin 目錄
            app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            bin_dir = os.path.join(app_dir, 'bin')
            os.makedirs(bin_dir, exist_ok=True)
            
            # 複製 ffmpeg.exe 到 bin 目錄
            src_path = os.path.join(ffmpeg_dir, FFMPEG_EXE_NAME)
            dst_path = os.path.join(bin_dir, FFMPEG_EXE_NAME)
            
            shutil.copy2(src_path, dst_path)
            
            # 同時複製其他必要的檔案
            for file in os.listdir(ffmpeg_dir):
                if file.endswith('.exe') or file.endswith('.dll'):
                    src_file = os.path.join(ffmpeg_dir, file)
                    dst_file = os.path.join(bin_dir, file)
                    shutil.copy2(src_file, dst_file)
            
            print(f"FFmpeg 已安裝到: {dst_path}")
            return True
            
    except Exception as e:
        print(f"安裝 FFmpeg 失敗: {e}")
        return False

def auto_install_ffmpeg(config, log_func=None):
    """自動安裝 FFmpeg"""
    if log_func:
        log_func("🔧 檢查 FFmpeg 安裝狀態...")
    
    # 檢查系統是否已安裝 FFmpeg
    if check_ffmpeg_installed():
        if log_func:
            log_func("✅ 系統已安裝 FFmpeg")
        return True
    
    # 檢查設定中的 FFmpeg 路徑
    ffmpeg_path = config.get('ffmpeg_path', 'bin/ffmpeg.exe')
    if check_local_ffmpeg(ffmpeg_path):
        if log_func:
            log_func(f"✅ 本地 FFmpeg 可用: {ffmpeg_path}")
        return True
    
    # 自動安裝
    if log_func:
        log_func("📥 正在自動安裝 FFmpeg...")
    
    def progress_callback(percent):
        if log_func:
            log_func(f"📥 下載進度: {percent:.1f}%")
    
    success = download_ffmpeg(progress_callback)
    
    if success:
        # 更新設定
        config['ffmpeg_path'] = 'bin/ffmpeg.exe'
        from utils.config import save_config
        save_config(config)
        
        if log_func:
            log_func("✅ FFmpeg 安裝完成！")
            log_func("📁 安裝位置: bin/ffmpeg.exe")
        
        return True
    else:
        if log_func:
            log_func("❌ FFmpeg 安裝失敗")
        return False

def get_ffmpeg_path(config):
    """取得 FFmpeg 路徑"""
    ffmpeg_path = config.get('ffmpeg_path', 'bin/ffmpeg.exe')
    
    # 如果是相對路徑，轉換為絕對路徑
    if not os.path.isabs(ffmpeg_path):
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ffmpeg_path = os.path.join(app_dir, ffmpeg_path)
    
    return ffmpeg_path

def ensure_ffmpeg_available(config, log_func=None):
    """確保 FFmpeg 可用（如果不可用則自動安裝）"""
    ffmpeg_path = get_ffmpeg_path(config)
    
    if check_local_ffmpeg(ffmpeg_path):
        return True
    
    if log_func:
        log_func("⚠️ FFmpeg 不可用，正在自動安裝...")
    
    return auto_install_ffmpeg(config, log_func)

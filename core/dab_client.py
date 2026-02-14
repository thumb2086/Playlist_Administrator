"""
DAB Music API Client
Handles authentication, search, and download functionality for DAB Music Player API
"""

import requests
import json
import time
import os
import ssl
import urllib3
from typing import Optional, Dict, List, Any
from urllib.parse import urljoin

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class DABMusicClient:
    """Client for DAB Music Player API"""
    
    def __init__(self, base_url: str = "https://dab.yeet.su/api/"):
        self.base_url = base_url
        self.session = requests.Session()
        # Configure SSL verification bypass
        self.session.verify = False
        # Update headers for better compatibility
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
        })
        self.authenticated = False
        self.user_info = None
        self.last_request_time = 0
        self.min_request_interval = 2.0  # 最小請求間隔 2 秒
        
    def login(self, email: str, password: str) -> bool:
        """Authenticate with DAB Music API"""
        try:
            current_time = time.time()
            if current_time - self.last_request_time < self.min_request_interval:
                time.sleep(self.min_request_interval - (current_time - self.last_request_time))
            self.last_request_time = time.time()
            
            response = self.session.post(
                urljoin(self.base_url, "auth/login"),
                json={"email": email, "password": password},
                timeout=30
            )
            
            if response.status_code == 200:
                self.authenticated = True
                # Store user info from response
                data = response.json()
                self.user_info = data.get('user', {})
                return True
            else:
                resp_text = response.text[:200] + "..." if len(response.text) > 200 else response.text
                print(f"Login failed: {response.status_code} - {resp_text}")
                return False
                
        except Exception as e:
            print(f"Login error: {str(e)}")
            return False
    
    def logout(self) -> bool:
        """Logout from DAB Music API"""
        try:
            response = self.session.post(
                urljoin(self.base_url, "auth/logout"),
                timeout=30
            )
            self.authenticated = False
            self.user_info = None
            return response.status_code == 200
        except Exception as e:
            print(f"Logout error: {str(e)}")
            return False
    
    def search_tracks(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search for tracks"""
        try:
            # 添加延遲避免 Rate Limiting
            current_time = time.time()
            if current_time - self.last_request_time < self.min_request_interval:
                time.sleep(self.min_request_interval - (current_time - self.last_request_time))
            self.last_request_time = time.time()
            
            params = {
                "q": query,
                "type": "track",
                "limit": min(limit, 50)  # API limit is 50
            }
            
            response = self.session.get(
                urljoin(self.base_url, "search"),
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('tracks', [])
            else:
                resp_text = response.text[:200] + "..." if len(response.text) > 200 else response.text
                print(f"Search failed: {response.status_code} - {resp_text}")
                return []
                
        except Exception as e:
            print(f"Search error: {str(e)}")
            return []
    
    def get_album_info(self, album_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed album information"""
        try:
            params = {"albumId": album_id}
            response = self.session.get(
                urljoin(self.base_url, "album"),
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                resp_text = response.text[:200] + "..." if len(response.text) > 200 else response.text
                print(f"Get album info failed: {response.status_code} - {resp_text}")
                return None
                
        except Exception as e:
            print(f"Get album info error: {str(e)}")
            return None
    
    def get_download_info(self, album_id: str, quality: str = "27") -> Optional[Dict[str, Any]]:
        """Get download information for an album
        Quality codes: 27 (lossless FLAC), 18 (320kbps), 6 (128kbps)
        """
        try:
            params = {
                "albumId": album_id,
                "quality": quality
            }
            response = self.session.get(
                urljoin(self.base_url, "download"),
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                resp_text = response.text[:200] + "..." if len(response.text) > 200 else response.text
                print(f"Get download info failed: {response.status_code} - {resp_text}")
                return None
                
        except Exception as e:
            print(f"Get download info error: {str(e)}")
            return None
    
    def get_stream_url(self, track_id: str, quality: str = "27") -> Optional[str]:
        """Get streaming URL for a track"""
        try:
            # 添加延遲避免 Rate Limiting
            current_time = time.time()
            if current_time - self.last_request_time < self.min_request_interval:
                time.sleep(self.min_request_interval - (current_time - self.last_request_time))
            self.last_request_time = time.time()
            
            params = {
                "trackId": track_id,
                "quality": quality
            }
            response = self.session.get(
                urljoin(self.base_url, "stream"),
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('url')
            else:
                resp_text = response.text[:200] + "..." if len(response.text) > 200 else response.text
                print(f"Get stream URL failed: {response.status_code} - {resp_text}")
                return None
                
        except Exception as e:
            print(f"Get stream URL error: {str(e)}")
            return None
    
    def get_lyrics(self, artist: str, title: str) -> Optional[str]:
        """Get lyrics for a song"""
        try:
            params = {
                "artist": artist,
                "title": title
            }
            response = self.session.get(
                urljoin(self.base_url, "lyrics"),
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('lyrics')
            else:
                # Truncate large error pages (e.g. Cloudflare 504)
                resp_text = response.text[:200] + "..." if len(response.text) > 200 else response.text
                print(f"Get lyrics failed: {response.status_code} - {resp_text}")
                return None
                
        except Exception as e:
            print(f"Get lyrics error: {str(e)}")
            return None
    
    def download_track(self, track_info: Dict[str, Any], output_path: str, 
                      quality: str = "27", progress_callback=None) -> bool:
        """Download a single track to file"""
        try:
            track_id = track_info.get('id')
            if not track_id:
                print("No track ID found")
                return False
            
            # Get stream URL
            stream_url = self.get_stream_url(track_id, quality)
            if not stream_url:
                print("Failed to get stream URL")
                return False
            
            # Download the file
            response = self.session.get(stream_url, stream=True, timeout=60)
            if response.status_code != 200:
                print(f"Download failed: {response.status_code}")
                return False
            
            # Get file size for progress tracking
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            # Write to file with progress tracking
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback and total_size > 0:
                            progress = (downloaded / total_size) * 100
                            progress_callback(progress)
            
            return True
            
        except Exception as e:
            print(f"Download track error: {str(e)}")
            return False
    
    def get_best_quality_match(self, track_name: str, artist_name: str = None) -> Optional[Dict[str, Any]]:
        """Search for the best quality match for a track"""
        import re
        
        # Clean track name - remove common suffixes and extra info
        clean_track_name = track_name
        
        # First, extract quoted content if present (this is usually the actual song title)
        quoted_content = re.search(r'\'([^\']+)\'', clean_track_name)
        if quoted_content:
            # If we found quoted content, use that as the song title
            clean_track_name = quoted_content.group(1)
        else:
            # If no quotes, handle "Artist - Title" format first
            if ' - ' in clean_track_name:
                parts = clean_track_name.split(' - ', 1)
                if len(parts) == 2:
                    # We have artist and title, but we'll use the title part for search
                    # The artist will be added separately in the query
                    clean_track_name = parts[1].strip()
            
            # Remove common video/suffix patterns
            suffixes_to_remove = [
                r'\s*Official\s+.*?\s*Video',
                r'\s*Performance\s+Video',
                r'\s*Music\s+Video',
                r'\s*MV',
                r'\s*Official\s+MV',
                r'\s*\[.*?\]',  # Remove brackets content
                r'\s*\(.*?\)',  # Remove parentheses content
                r'\s*【.*?】',  # Remove Chinese brackets
            ]
            
            for suffix in suffixes_to_remove:
                clean_track_name = re.sub(suffix, '', clean_track_name, flags=re.IGNORECASE)
        
        # Clean up extra spaces
        clean_track_name = re.sub(r'\s+', ' ', clean_track_name).strip()
        
        # Remove artist name if it's at the beginning (only if we didn't extract from quotes)
        # Skip this step since we already handled "Artist - Title" format above
        # if not quoted_content and artist_name:
        #     if clean_track_name.startswith(artist_name):
        #         clean_track_name = clean_track_name.replace(artist_name, '', 1).strip(' -')
        #     # Handle duplicate artist names
        #     if clean_track_name.startswith(artist_name):
        #         clean_track_name = clean_track_name.replace(artist_name, '', 1).strip(' -')
        
        # Construct search query
        if artist_name:
            query = f"{artist_name} {clean_track_name}"
        else:
            query = clean_track_name
        
        # Search for tracks
        tracks = self.search_tracks(query, limit=10)
        if not tracks:
            return None
        
        # Try to find exact match first
        for track in tracks:
            title = track.get('title', '').lower()
            artist = track.get('artist', '').lower()
            clean_name_lower = clean_track_name.lower()
            
            # Check for exact title match
            if clean_name_lower == title or title == clean_name_lower:
                if artist_name:
                    artist_lower = artist_name.lower()
                    # More flexible artist matching - check for partial matches
                    if (artist_lower == artist or 
                        artist_lower in artist or 
                        artist in artist_lower or
                        # Handle case where artist name contains spaces vs no spaces
                        artist_lower.replace(' ', '') == artist.replace(' ', '') or
                        artist_lower.replace(' ', '') in artist.replace(' ', '') or
                        artist.replace(' ', '') in artist_lower.replace(' ', '')):
                        return track
                else:
                    return track
        
        # Try partial match with higher similarity requirement
        for track in tracks:
            title = track.get('title', '').lower()
            artist = track.get('artist', '').lower()
            clean_name_lower = clean_track_name.lower()
            
            # Check if title contains significant portion of search query
            if len(clean_name_lower) > 3 and (clean_name_lower in title or title in clean_name_lower):
                if artist_name:
                    artist_lower = artist_name.lower()
                    if len(artist_lower) > 2 and (artist_lower in artist or artist in artist_lower):
                        return track
                else:
                    return track
        
        # If still no good match, return None to trigger fallback
        return None

"""
DAB Music API Client
Handles authentication, search, and download functionality for DAB Music Player API
"""

import requests
import json
import time
import os
from typing import Optional, Dict, List, Any
from urllib.parse import urljoin

class DABMusicClient:
    """Client for DAB Music Player API"""
    
    def __init__(self, base_url: str = "https://dab.yeet.su/api/"):
        self.base_url = base_url
        self.session = requests.Session()
        self.authenticated = False
        self.user_info = None
        
    def login(self, email: str, password: str) -> bool:
        """Authenticate with DAB Music API"""
        try:
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
                print(f"Login failed: {response.status_code} - {response.text}")
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
                print(f"Search failed: {response.status_code} - {response.text}")
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
                print(f"Get album info failed: {response.status_code} - {response.text}")
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
                print(f"Get download info failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Get download info error: {str(e)}")
            return None
    
    def get_stream_url(self, track_id: str, quality: str = "27") -> Optional[str]:
        """Get streaming URL for a track"""
        try:
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
                print(f"Get stream URL failed: {response.status_code} - {response.text}")
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
                print(f"Get lyrics failed: {response.status_code} - {response.text}")
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
        # Construct search query
        if artist_name:
            query = f"{artist_name} {track_name}"
        else:
            query = track_name
        
        # Search for tracks
        tracks = self.search_tracks(query, limit=10)
        if not tracks:
            return None
        
        # Try to find exact match first
        for track in tracks:
            title = track.get('title', '').lower()
            name_lower = track_name.lower()
            
            # Check for exact title match
            if name_lower in title or title in name_lower:
                if artist_name:
                    artist = track.get('artist', '').lower()
                    artist_lower = artist_name.lower()
                    if artist_lower in artist or artist in artist_lower:
                        return track
                else:
                    return track
        
        # If no exact match, return first result
        return tracks[0] if tracks else None

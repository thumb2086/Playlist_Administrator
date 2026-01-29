"""
DAB Music Downloader
Handles downloading lossless FLAC files with metadata from DAB Music API
"""

import os
import re
import time
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TRCK
from utils.helpers import sanitize_filename
from core.dab_client import DABMusicClient

class DABDownloader:
    """Downloader for DAB Music API with lossless FLAC support"""
    
    def __init__(self, email: str, password: str):
        self.client = DABMusicClient()
        self.authenticated = self.client.login(email, password)
        if not self.authenticated:
            raise Exception("Failed to authenticate with DAB Music API")
    
    def download_song(self, song_name: str, library_path: str, log_func, 
                     file_list=None, stats=None, progress_callback=None, 
                     current_dl=0, artist_name: str = None) -> str:
        """Download song in lossless FLAC format with metadata"""
        
        try:
            log_func(f"  🔍 [DAB Search] {song_name}")
            
            # Search for the track
            track_info = self.client.get_best_quality_match(song_name, artist_name)
            if not track_info:
                log_func(f"  ❌ [DAB Not Found] {song_name}")
                return None
            
            # Extract track information
            track_title = track_info.get('title', song_name)
            track_artist = track_info.get('artist', artist_name or 'Unknown Artist')
            track_album = track_info.get('album', 'Unknown Album')
            track_id = track_info.get('id')
            
            log_func(f"  🎵 [DAB Found] {track_artist} - {track_title}")
            
            # Sanitize filename
            safe_title = sanitize_filename(f"{track_artist} - {track_title}")
            
            # Separate lossless files into a subfolder
            lossless_dir = os.path.join(library_path, "Lossless")
            os.makedirs(lossless_dir, exist_ok=True)
            output_path = os.path.join(lossless_dir, f"{safe_title}.flac")
            
            # Check if file already exists
            if os.path.exists(output_path):
                log_func(f"  ✅ [Already Exists] {safe_title}.flac")
                return output_path
            
            # Create directory if it doesn't exist
            os.makedirs(library_path, exist_ok=True)
            
            # Progress callback wrapper
            def progress_wrapper(progress):
                if progress_callback:
                    progress_callback(current_dl, progress)
            
            # Download the track
            log_func(f"  ⬇️ [DAB Downloading] {safe_title}.flac (Lossless)")
            success = self.client.download_track(
                track_info, 
                output_path, 
                quality="27",  # Lossless FLAC
                progress_callback=progress_wrapper
            )
            
            if not success:
                log_func(f"  ❌ [DAB Download Failed] {safe_title}.flac")
                return None
            
            # Add metadata to the file
            self._add_metadata(output_path, track_info, log_func)
            
            # Download lyrics if available
            lyrics_path = output_path.replace('.flac', '.lrc')
            self._download_lyrics(track_artist, track_title, lyrics_path, log_func)
            
            log_func(f"  ✅ [DAB Complete] {safe_title}.flac")
            return output_path
            
        except Exception as e:
            log_func(f"  ❌ [DAB Error] {song_name}: {str(e)}")
            return None
    
    def _add_metadata(self, file_path: str, track_info: dict, log_func):
        """Add metadata to FLAC file"""
        try:
            # Extract metadata from track info
            title = track_info.get('title', '')
            artist = track_info.get('artist', '')
            album = track_info.get('album', '')
            track_number = track_info.get('trackNumber', '')
            year = track_info.get('year', '')
            duration = track_info.get('duration', '')
            genre = track_info.get('genre', '')
            
            # Load FLAC file
            audio = FLAC(file_path)
            
            # Add metadata
            if title:
                audio['TITLE'] = title
            if artist:
                audio['ARTIST'] = artist
            if album:
                audio['ALBUM'] = album
            if track_number:
                audio['TRACKNUMBER'] = str(track_number)
            if year:
                audio['DATE'] = str(year)
            if duration:
                audio['LENGTH'] = str(duration)
            if genre:
                audio['GENRE'] = genre
            
            # Add DAB Music specific tags
            audio['SOURCE'] = 'DAB Music'
            audio['QUALITY'] = 'Lossless FLAC'
            
            # Save metadata
            audio.save()
            log_func(f"  🏷️ [Metadata Added] {title}")
            
        except Exception as e:
            log_func(f"  ⚠️ [Metadata Error] {str(e)}")
    
    def _download_lyrics(self, artist: str, title: str, lyrics_path: str, log_func):
        """Download lyrics for the track"""
        try:
            lyrics = self.client.get_lyrics(artist, title)
            if lyrics:
                with open(lyrics_path, 'w', encoding='utf-8') as f:
                    f.write(lyrics)
                log_func(f"  📝 [Lyrics Downloaded] {title}")
            else:
                log_func(f"  ℹ️ [No Lyrics Found] {title}")
        except Exception as e:
            log_func(f"  ⚠️ [Lyrics Error] {str(e)}")
    
    def search_and_preview(self, song_name: str, artist_name: str = None, limit: int = 5) -> list:
        """Search for tracks and return preview information"""
        try:
            if artist_name:
                query = f"{artist_name} {song_name}"
            else:
                query = song_name
            
            tracks = self.client.search_tracks(query, limit=limit)
            
            results = []
            for track in tracks:
                results.append({
                    'id': track.get('id', ''),
                    'title': track.get('title', ''),
                    'artist': track.get('artist', ''),
                    'album': track.get('album', ''),
                    'duration': track.get('duration', ''),
                    'year': track.get('year', ''),
                    'quality': 'Lossless FLAC'
                })
            
            return results
            
        except Exception as e:
            print(f"Search error: {str(e)}")
            return []
    
    def get_album_info(self, album_id: str) -> dict:
        """Get detailed album information"""
        return self.client.get_album_info(album_id)
    
    def logout(self):
        """Logout from DAB Music API"""
        self.client.logout()
        self.authenticated = False

def create_dab_downloader(email: str, password: str) -> DABDownloader:
    """Factory function to create DAB downloader with authentication"""
    try:
        return DABDownloader(email, password)
    except Exception as e:
        raise Exception(f"Failed to create DAB downloader: {str(e)}")

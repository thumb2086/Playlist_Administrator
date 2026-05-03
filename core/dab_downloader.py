"""
DAB Music Downloader
Handles downloading lossless FLAC files with metadata from DAB Music API
"""

import os
import re
import time
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TRCK, APIC
from utils.helpers import sanitize_filename, download_image
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
                     current_dl=0, artist_name: str = None, config=None) -> str:
        """Download song in lossless FLAC format with metadata"""
        
        try:
            log_func(f"  🔍 [DAB Search] {song_name}")
            
            # Extract artist name from song_name if in "Artist - Title" format and not provided
            if not artist_name and ' - ' in song_name:
                parts = song_name.split(' - ', 1)
                if len(parts) == 2:
                    artist_name = parts[0].strip()
            
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
            
            # Use the playlist song_name for the filename base to match MP3 naming
            safe_title = sanitize_filename(song_name)
            
            # Separate lossless files into a subfolder
            lossless_dir = os.path.join(library_path, "Lossless")
            os.makedirs(lossless_dir, exist_ok=True)
            output_path = os.path.join(lossless_dir, f"{safe_title}.flac")
            
            # Check if file already exists in the entire library, not just Lossless folder
            existing_flac = None
            if file_list:
                from core.library import find_song_prefer_flac
                existing_flac = find_song_prefer_flac(song_name, file_list)
            
            if existing_flac and existing_flac.lower().endswith('.flac'):
                log_func(f"  ✅ [Already Exists] {os.path.basename(existing_flac)}")
                return existing_flac
            
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
            from utils.config import get_lyrics_file_path
            lyrics_path = get_lyrics_file_path(config or {'library_path': library_path}, output_path)
            os.makedirs(os.path.dirname(lyrics_path), exist_ok=True)
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
            
            # Add album art if available
            image_url = track_info.get('image', '')
            if image_url:
                artwork_data = download_image(image_url)
                if artwork_data:
                    picture = Picture()
                    picture.data = artwork_data
                    picture.type = 3 # Front cover
                    picture.mime = 'image/jpeg'
                    audio.add_picture(picture)
            
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

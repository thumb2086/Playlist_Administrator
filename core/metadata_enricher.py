"""
Metadata Enricher for existing audio files
Handles scanning and adding missing metadata to existing songs
"""

import os
import glob
import time
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TRCK, TCON
from mutagen.mp4 import MP4
from mutagen.easyid3 import EasyID3
from mutagen import File as MutagenFile
from utils.helpers import sanitize_filename
from core.dab_client import DABMusicClient

class MetadataEnricher:
    """Enriches metadata for existing audio files"""
    
    def __init__(self, config=None):
        self.config = config
        self.dab_client = None
        
        # Initialize DAB client if credentials are available
        if config and config.get('use_dab_music', False):
            dab_email = config.get('dab_email', '')
            dab_password = config.get('dab_password', '')
            if dab_email and dab_password:
                try:
                    self.dab_client = DABMusicClient()
                    if self.dab_client.login(dab_email, dab_password):
                        print("DAB Music client initialized for metadata enrichment")
                    else:
                        self.dab_client = None
                except Exception as e:
                    print(f"Failed to initialize DAB client: {e}")
                    self.dab_client = None
    
    def scan_files_missing_metadata(self, library_path, log_func):
        """Scan library for files missing essential metadata"""
        log_func("🔍 Scanning for files missing metadata...")
        
        # Search for all audio files
        search_pattern = os.path.join(library_path, "**", "*")
        all_files = glob.glob(search_pattern, recursive=True)
        audio_files = [f for f in all_files if os.path.isfile(f) and 
                      f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]
        
        files_missing_metadata = []
        
        for file_path in audio_files:
            try:
                missing_fields = self._check_metadata_completeness(file_path)
                if missing_fields:
                    files_missing_metadata.append({
                        'path': file_path,
                        'missing_fields': missing_fields,
                        'filename': os.path.basename(file_path)
                    })
            except Exception as e:
                log_func(f"  ⚠️ Error checking {os.path.basename(file_path)}: {str(e)}")
        
        log_func(f"  📊 Found {len(files_missing_metadata)} files missing metadata")
        return files_missing_metadata
    
    def _check_metadata_completeness(self, file_path):
        """Check what metadata fields are missing from a file"""
        missing_fields = []
        
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext == '.flac':
                audio = FLAC(file_path)
                required_fields = ['TITLE', 'ARTIST']
                for field in required_fields:
                    if field not in audio or not audio[field]:
                        missing_fields.append(field)
                        
            elif file_ext in ['.mp3', '.mp2', '.mp1']:
                try:
                    audio = EasyID3(file_path)
                    required_fields = ['title', 'artist']
                    for field in required_fields:
                        if field not in audio or not audio[field]:
                            missing_fields.append(field)
                except:
                    # Fallback to ID3 if EasyID3 fails
                    audio = ID3(file_path)
                    if not audio.get('TIT2'):
                        missing_fields.append('title')
                    if not audio.get('TPE1'):
                        missing_fields.append('artist')
                        
            elif file_ext in ['.m4a', '.mp4']:
                audio = MP4(file_path)
                required_fields = ['\xa9nam', '\xa9ART']  # title, artist
                for field in required_fields:
                    if field not in audio or not audio[field]:
                        missing_fields.append(field)
        
        except Exception:
            # If we can't read the file, consider all fields missing
            missing_fields = ['title', 'artist']
        
        return missing_fields
    
    def enrich_file_metadata(self, file_path, song_name, log_func, artist_hint=None):
        """Enrich metadata for a single file"""
        
        try:
            log_func(f"  🎵 Processing: {os.path.basename(file_path)}")
            
            # Try DAB Music first if available
            if self.dab_client:
                success = self._enrich_with_dab_music(file_path, song_name, log_func, artist_hint)
                if success:
                    return True
            
            # Fallback to filename-based metadata
            success = self._enrich_from_filename(file_path, song_name, log_func)
            return success
            
        except Exception as e:
            log_func(f"  ❌ Error enriching {os.path.basename(file_path)}: {str(e)}")
            return False
    
    def _enrich_with_dab_music(self, file_path, song_name, log_func, artist_hint=None):
        """Try to enrich metadata using DAB Music API"""
        try:
            # Extract artist name if not provided
            search_artist = artist_hint
            search_title = song_name
            if not search_artist and ' - ' in song_name:
                parts = song_name.split(' - ', 1)
                if len(parts) == 2:
                    search_artist = parts[0].strip()
                    search_title = parts[1].strip()

            # Search for the track
            track_info = self.dab_client.get_best_quality_match(search_title, search_artist)
            if not track_info:
                return False
            
            # Extract metadata
            title = track_info.get('title', '')
            artist = track_info.get('artist', '')
            album = track_info.get('album', '')
            year = track_info.get('year', '')
            genre = track_info.get('genre', '')
            
            if not title or not artist:
                return False
            
            # Apply metadata to file
            success = self._apply_metadata_to_file(file_path, {
                'title': title,
                'artist': artist,
                'album': album,
                'year': year,
                'genre': genre,
                'source': 'DAB Music'
            }, log_func)
            
            if success:
                log_func(f"  ✅ [DAB Enriched] {title} - {artist}")
            
            return success
            
        except Exception as e:
            log_func(f"  ⚠️ DAB enrichment failed: {str(e)}")
            return False
    
    def _enrich_from_filename(self, file_path, song_name, log_func):
        """Enrich metadata by parsing filename"""
        try:
            # Try to extract artist and title from filename
            title = song_name
            artist = ''
            
            if ' - ' in song_name:
                parts = song_name.split(' - ', 1)
                if len(parts) == 2:
                    artist = parts[0].strip()
                    title = parts[1].strip()
            
            # Apply basic metadata
            success = self._apply_metadata_to_file(file_path, {
                'title': title,
                'artist': artist,
                'album': 'Unknown Album',
                'year': '',
                'genre': '',
                'source': 'Filename Parser'
            }, log_func)
            
            if success:
                log_func(f"  ✅ [Filename Enriched] {title}")
            
            return success
            
        except Exception as e:
            log_func(f"  ⚠️ Filename enrichment failed: {str(e)}")
            return False
    
    def _apply_metadata_to_file(self, file_path, metadata, log_func):
        """Apply metadata to the audio file"""
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext == '.flac':
                audio = FLAC(file_path)
                if metadata.get('title'):
                    audio['TITLE'] = metadata['title']
                if metadata.get('artist'):
                    audio['ARTIST'] = metadata['artist']
                if metadata.get('album'):
                    audio['ALBUM'] = metadata['album']
                if metadata.get('year'):
                    audio['DATE'] = metadata['year']
                if metadata.get('genre'):
                    audio['GENRE'] = metadata['genre']
                if metadata.get('source'):
                    audio['SOURCE'] = metadata['source']
                audio.save()
                
            elif file_ext in ['.mp3', '.mp2', '.mp1']:
                try:
                    audio = EasyID3(file_path)
                except:
                    audio = ID3(file_path)
                
                if isinstance(audio, EasyID3):
                    if metadata.get('title'):
                        audio['title'] = metadata['title']
                    if metadata.get('artist'):
                        audio['artist'] = metadata['artist']
                    if metadata.get('album'):
                        audio['album'] = metadata['album']
                    if metadata.get('year'):
                        audio['date'] = metadata['year']
                    if metadata.get('genre'):
                        audio['genre'] = metadata['genre']
                else:
                    if metadata.get('title'):
                        audio.add(TIT2(encoding=3, text=metadata['title']))
                    if metadata.get('artist'):
                        audio.add(TPE1(encoding=3, text=metadata['artist']))
                    if metadata.get('album'):
                        audio.add(TALB(encoding=3, text=metadata['album']))
                    if metadata.get('year'):
                        audio.add(TDRC(encoding=3, text=metadata['year']))
                    if metadata.get('genre'):
                        audio.add(TCON(encoding=3, text=metadata['genre']))
                
                audio.save()
                
            elif file_ext in ['.m4a', '.mp4']:
                audio = MP4(file_path)
                if metadata.get('title'):
                    audio['\xa9nam'] = metadata['title']
                if metadata.get('artist'):
                    audio['\xa9ART'] = metadata['artist']
                if metadata.get('album'):
                    audio['\xa9alb'] = metadata['album']
                if metadata.get('year'):
                    audio['\xa9day'] = metadata['year']
                if metadata.get('genre'):
                    audio['\xa9gen'] = metadata['genre']
                audio.save()
            
            return True
            
        except Exception as e:
            log_func(f"  ⚠️ Metadata application error: {str(e)}")
            return False
    
    def enrich_library_metadata(self, library_path, log_func, progress_callback=None):
        """Enrich metadata for all files in library"""
        # Scan for files missing metadata
        files_to_enrich = self.scan_files_missing_metadata(library_path, log_func)
        
        if not files_to_enrich:
            log_func("✅ All files have complete metadata")
            return 0
        
        total_files = len(files_to_enrich)
        log_func(f"🎵 Starting metadata enrichment for {total_files} files...")
        
        successful_enrichments = 0
        
        for i, file_info in enumerate(files_to_enrich):
            try:
                # Check for pause/stop if needed
                if progress_callback:
                    progress_callback(i, total_files)
                
                # Extract path and song name
                file_path = file_info['path']
                song_name = os.path.splitext(file_info['filename'])[0]
                
                # Show progress every 5 files or for small batches every file
                progress_interval = 5 if total_files > 20 else 1
                if (i + 1) % progress_interval == 0 or (i + 1) == total_files:
                    success_rate = (successful_enrichments / (i + 1) * 100) if (i + 1) > 0 else 0
                    log_func(f"🎵 Metadata 補充進度: {i + 1}/{total_files} (成功: {successful_enrichments}, 成功率: {success_rate:.1f}%)")
                
                success = self.enrich_file_metadata(file_path, song_name, log_func, None)
                if success:
                    successful_enrichments += 1
                
                # Small delay to avoid overwhelming APIs
                time.sleep(0.5)
                
            except Exception as e:
                log_func(f"  ❌ Error processing {file_info['filename']}: {str(e)}")
        
        log_func(f"🎉 Metadata enrichment complete: {successful_enrichments}/{total_files} files enriched")
        
        if progress_callback:
            progress_callback(total_files, total_files)
        
        return successful_enrichments
    
    def cleanup(self):
        """Clean up resources"""
        if self.dab_client:
            try:
                self.dab_client.logout()
            except:
                pass

def create_metadata_enricher(config=None):
    """Factory function to create metadata enricher"""
    return MetadataEnricher(config)

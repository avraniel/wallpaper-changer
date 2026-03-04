#!/usr/bin/env python3
"""
AI-Powered Wallpaper Changer - Complete Version
With Duplicate Detection, Secure Key Storage, and All Features
"""

import os
import sys
import time
import json
import random
import ctypes
import winreg
import requests
import threading
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
from PIL import Image, ImageTk, ImageDraw, ImageFile
import io
import pystray
import subprocess
import tempfile
import shutil
import hashlib
import numpy as np
from typing import List, Tuple

# Increase PIL image size limit for large wallpapers
Image.MAX_IMAGE_PIXELS = None  # Disable decompression bomb check
ImageFile.LOAD_TRUNCATED_IMAGES = True  # Handle truncated images

# Try to import imagehash, install if not present
try:
    import imagehash
except ImportError:
    print("Installing imagehash module...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "imagehash"])
    import imagehash

# Try to import keyboard, install if not present
try:
    import keyboard
except ImportError:
    print("Installing keyboard module...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "keyboard"])
    import keyboard

# Try to import keyring for secure API key storage
try:
    import keyring
    from keyring.backends import Windows
    # Set the Windows backend explicitly
    keyring.set_keyring(Windows.WinVaultKeyring())
    HAS_KEYRING = True
    print("✅ Keyring loaded with Windows Credential Manager")
except ImportError:
    HAS_KEYRING = False
    print("ℹ️ Keyring not installed - API keys will be stored in config file")
except Exception as e:
    HAS_KEYRING = False
    print(f"ℹ️ Keyring error: {e} - using config file instead")

# ============================================================================
# CONFIGURATION
# ============================================================================

if getattr(sys, 'frozen', False):
    # Running as compiled EXE
    APP_DATA = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'WallpaperChanger')
    BASE_DIR = sys._MEIPASS
else:
    # Running as script
    APP_DATA = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.makedirs(APP_DATA, exist_ok=True)

CONFIG_FILE = os.path.join(APP_DATA, "wallpaper_changer_config.json")
DATABASE_FILE = os.path.join(APP_DATA, "wallhaven_favorites.db")
DUPLICATE_DB_FILE = os.path.join(APP_DATA, "duplicate_hashes.db")
LAST_WALLPAPER_FILE = os.path.join(APP_DATA, "last_wallpaper.dat")
KEYWORDS_FILE = os.path.join(APP_DATA, "keywords.json")

PICTURES_FOLDER = os.path.join(os.path.expanduser("~"), "Pictures")
WALLHAVEN_FOLDER = os.path.join(PICTURES_FOLDER, "Wallhaven")
FAVORITES_FOLDER = os.path.join(WALLHAVEN_FOLDER, "Favorites")

os.makedirs(PICTURES_FOLDER, exist_ok=True)

# NSFW Warning Message
NSFW_WARNING = """⚠️ NSFW CONTENT WARNING ⚠️

You have enabled NSFW (Not Safe For Work) content. 
This may contain adult material including nudity, violence, or explicit content.

By proceeding, you confirm that you are:
• 18 years of age or older
• Legally allowed to view adult content in your location
• Using this in a private environment

Do you want to enable NSFW content?"""

DEFAULT_CONFIG = {
    "api_key": "",
    "download_folder": WALLHAVEN_FOLDER,
    "favorites_folder": FAVORITES_FOLDER,
    "interval_value": 30,
    "interval_unit": "minutes",
    "categories": {
        "general": 1,
        "anime": 1,
        "people": 1
    },
    "purity": {
        "sfw": 1,
        "sketchy": 0,
        "nsfw": 0
    },
    "nsfw_acknowledged": False,
    "resolutions": ["1920x1080"],
    "resolution_presets": {
        "4k": False,
        "2k": False,
        "1080p": True,
        "ultrawide": False
    },
    "min_resolution": "1920x1080",
    "aspect_ratios": [],
    "wallpaper_style": "fill",
    "notifications": True,
    "theme": "light",
    "accent_color": "#3b82f6",
    "remember_last_wallpaper": True,
    "random_order": True,
    "keywords": [],
    "downloads_per_keyword": 10,
    "last_keyword_download": {},
    "quota_enabled": True,
    "quota_size": 1000,
    "shortcuts": {
        "next": "ctrl+alt+right",
        "previous": "ctrl+alt+left",
        "delete": "ctrl+alt+del",
        "pause": "alt+p"
    },
    "copy_to_favorites": True,
    "change_on_startup": True,
    "auto_start_enabled": True,
    "api_key_use_keyring": False,
    # Duplicate detector settings
    "duplicate_detection_enabled": True,
    "duplicate_hash_size": 8,
    "duplicate_auto_cleanup": False,
    "duplicate_keep_newest": True,
    "duplicate_similarity_threshold": 0.9
}

# ============================================================================
# COLOR SCHEMES
# ============================================================================

COLOR_SCHEMES = {
    "light": {
        "name": "Light Mode",
        "bg": "#f8fafd",
        "fg": "#1e293b",
        "accent": "#3b82f6",
        "accent_light": "#60a5fa",
        "accent_dark": "#2563eb",
        "card_bg": "#ffffff",
        "card_shadow": "#e2e8f0",
        "success": "#10b981",
        "warning": "#f59e0b",
        "error": "#ef4444",
        "info": "#3b82f6",
        "button_bg": "#3b82f6",
        "button_fg": "#ffffff",
        "button_hover": "#60a5fa",
        "entry_bg": "#ffffff",
        "entry_fg": "#1e293b",
        "trough_color": "#e2e8f0",
    },
    "dark": {
        "name": "Dark Mode",
        "bg": "#0f172a",
        "fg": "#f1f5f9",
        "accent": "#3b82f6",
        "accent_light": "#60a5fa",
        "accent_dark": "#2563eb",
        "card_bg": "#1e293b",
        "card_shadow": "#0f172a",
        "success": "#10b981",
        "warning": "#f59e0b",
        "error": "#ef4444",
        "info": "#3b82f6",
        "button_bg": "#3b82f6",
        "button_fg": "#ffffff",
        "button_hover": "#60a5fa",
        "entry_bg": "#334155",
        "entry_fg": "#f1f5f9",
        "trough_color": "#1e293b",
    }
}

# ============================================================================
# SECURE CONFIG MANAGER with Keyring Support
# ============================================================================

class SecureConfig:
    """Handle secure storage of API keys using Windows Credential Manager"""
    
    SERVICE_NAME = "WallpaperChanger"  # Name in Windows Credential Manager
    
    @staticmethod
    def get_api_key(config):
        """Get API key from secure storage if available"""
        # First check if we have a key in keyring
        if HAS_KEYRING:
            try:
                # Try to get from Windows Credential Manager
                api_key = keyring.get_password(SecureConfig.SERVICE_NAME, "wallhaven_api_key")
                if api_key:
                    return api_key
            except Exception as e:
                print(f"Error reading from keyring: {e}")
        
        # Fall back to config file
        return config.get("api_key", "")
    
    @staticmethod
    def set_api_key(config, api_key, use_keyring=False):
        """Set API key in secure storage if requested"""
        success = False
        
        if HAS_KEYRING and use_keyring:
            try:
                # Store in Windows Credential Manager
                keyring.set_password(SecureConfig.SERVICE_NAME, "wallhaven_api_key", api_key)
                # Clear from config file for security
                config["api_key"] = ""
                config["api_key_use_keyring"] = True
                success = True
                print("✅ API key stored securely in Windows Credential Manager")
            except Exception as e:
                print(f"❌ Failed to store in keyring: {e}")
                # Fall back to config file
                config["api_key"] = api_key
                config["api_key_use_keyring"] = False
                success = False
        else:
            # Store in config file (less secure)
            config["api_key"] = api_key
            config["api_key_use_keyring"] = False
            success = True
            if HAS_KEYRING and not use_keyring:
                print("ℹ️ API key stored in config file (consider using keyring for better security)")
        
        return success
    
    @staticmethod
    def delete_api_key(config):
        """Remove API key from secure storage"""
        if HAS_KEYRING:
            try:
                # Delete from Windows Credential Manager
                keyring.delete_password(SecureConfig.SERVICE_NAME, "wallhaven_api_key")
                print("✅ API key removed from Windows Credential Manager")
            except:
                pass
        
        # Clear from config
        config["api_key"] = ""
        config["api_key_use_keyring"] = False
        return True
    
    @staticmethod
    def verify_keyring():
        """Verify keyring is working and show where keys are stored"""
        if not HAS_KEYRING:
            return False, "Keyring not installed"
        
        try:
            # Test keyring by setting and getting a test value
            test_key = "test_connection"
            keyring.set_password(SecureConfig.SERVICE_NAME, test_key, "working")
            result = keyring.get_password(SecureConfig.SERVICE_NAME, test_key)
            keyring.delete_password(SecureConfig.SERVICE_NAME, test_key)
            
            if result == "working":
                # Determine which backend is being used
                if sys.platform == 'win32':
                    storage = "Windows Credential Manager"
                else:
                    storage = "Keyring"
                return True, f"Keyring working (using {storage})"
            else:
                return False, "Keyring test failed"
        except Exception as e:
            return False, f"Keyring error: {e}"

# ============================================================================
# WALLPAPER VALIDATOR
# ============================================================================

class WallpaperValidator:
    """Validate image files before setting as wallpaper"""
    
    @staticmethod
    def is_valid_image(file_path: str) -> bool:
        """Check if file exists and is a valid image"""
        if not os.path.exists(file_path):
            return False
        
        try:
            with Image.open(file_path) as img:
                img.verify()  # Verify it's a valid image
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_image_info(file_path: str) -> dict:
        """Get image dimensions and format"""
        try:
            with Image.open(file_path) as img:
                return {
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode,
                    "size": os.path.getsize(file_path)
                }
        except Exception:
            return None

# ============================================================================
# DUPLICATE DETECTOR
# ============================================================================

class DuplicateDetector:
    """Detect duplicate images using perceptual hashing"""
    
    def __init__(self, db_path: str, enabled: bool = True, hash_size: int = 8):
        self.db_path = db_path
        self.enabled = enabled
        self.hash_size = hash_size
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self._create_tables()
    
    def _create_tables(self):
        with self.lock:
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS image_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE,
                phash TEXT,
                file_size INTEGER,
                width INTEGER,
                height INTEGER,
                created_at TEXT
            )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_phash ON image_hashes(phash)")
            self.conn.commit()
    
    def get_image_hash(self, image_path: str) -> str:
        """Generate perceptual hash for an image"""
        if not self.enabled:
            return None
        
        try:
            # Temporarily increase the limit for this operation
            original_limit = Image.MAX_IMAGE_PIXELS
            Image.MAX_IMAGE_PIXELS = None
            
            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                # Resize very large images before hashing for performance
                if img.width > 2000 or img.height > 2000:
                    img.thumbnail((2000, 2000))
                result = str(imagehash.phash(img, hash_size=self.hash_size))
            
            # Restore original limit
            Image.MAX_IMAGE_PIXELS = original_limit
            return result
        except Exception as e:
            print(f"Error generating hash: {e}")
            return None
    
    def index_image(self, image_path: str) -> bool:
        """Index an image by storing its hash"""
        if not self.enabled or not os.path.exists(image_path):
            return False
        
        cursor = self.conn.execute("SELECT path FROM image_hashes WHERE path = ?", (image_path,))
        if cursor.fetchone():
            return True
        
        try:
            phash = self.get_image_hash(image_path)
            if not phash:
                return False
            
            with Image.open(image_path) as img:
                width, height = img.width, img.height
            
            file_size = os.path.getsize(image_path)
            
            with self.lock:
                self.conn.execute(
                    "INSERT INTO image_hashes (path, phash, file_size, width, height, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (image_path, phash, file_size, width, height, datetime.now().isoformat())
                )
                self.conn.commit()
            return True
        except Exception as e:
            print(f"Error indexing {image_path}: {e}")
            return False
    
    def find_duplicates(self) -> List[Tuple[str, str]]:
        """Find duplicate images using database grouping (optimized for large collections)"""
        if not self.enabled:
            return []
        
        duplicates = []
        
        # Use database grouping to find duplicates - much more efficient for large collections
        cursor = self.conn.execute("""
            SELECT phash, GROUP_CONCAT(path) as paths 
            FROM image_hashes 
            WHERE phash != '' 
            GROUP BY phash 
            HAVING COUNT(*) > 1
        """)
        
        for row in cursor.fetchall():
            paths = row[1].split(',')
            for i in range(len(paths)):
                for j in range(i+1, len(paths)):
                    duplicates.append((paths[i], paths[j]))
        
        return duplicates
    
    def cleanup_duplicates(self, keep_newest: bool = True) -> int:
        """Remove duplicate images"""
        if not self.enabled:
            return 0
        
        deleted = 0
        
        # Use database grouping for efficiency
        cursor = self.conn.execute("""
            SELECT phash, GROUP_CONCAT(path || '|' || COALESCE(created_at, '')) as paths 
            FROM image_hashes 
            WHERE phash != '' 
            GROUP BY phash 
            HAVING COUNT(*) > 1
        """)
        
        for row in cursor.fetchall():
            # Parse paths with creation times
            items = []
            for item in row[1].split(','):
                if '|' in item:
                    path, created = item.split('|', 1)
                    items.append((path, created))
                else:
                    items.append((item, ''))
            
            if keep_newest:
                items.sort(key=lambda x: x[1] if x[1] else '', reverse=True)
            else:
                items.sort(key=lambda x: x[1] if x[1] else '')
            
            kept = items[0][0]
            for path, _ in items[1:]:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                        deleted += 1
                        self.conn.execute("DELETE FROM image_hashes WHERE path = ?", (path,))
                    except:
                        pass
        
        self.conn.commit()
        return deleted
    
    def scan_folder(self, folder_path: str, progress_callback=None, stop_event=None) -> Tuple[int, int]:
        """Scan a folder and index all images with ability to stop"""
        if not self.enabled:
            return 0, 0
        
        supported = (".jpg", ".jpeg", ".png", ".gif", ".webp")
        indexed = 0
        existing = 0
        
        for file in os.listdir(folder_path):
            # Check if we should stop
            if stop_event and stop_event.is_set():
                break
                
            if file.lower().endswith(supported):
                full_path = os.path.join(folder_path, file)
                cursor = self.conn.execute("SELECT path FROM image_hashes WHERE path = ?", (full_path,))
                if cursor.fetchone():
                    existing += 1
                else:
                    if self.index_image(full_path):
                        indexed += 1
                        if progress_callback:
                            # Call in main thread if needed
                            if threading.current_thread() is threading.main_thread():
                                progress_callback(f"Indexed: {file}", indexed)
                            else:
                                # For thread safety, we'll let the caller handle UI updates
                                pass
        
        return indexed, existing
    
    def check_before_download(self, temp_path: str) -> Tuple[bool, str]:
        """Check if image is duplicate before downloading"""
        if not self.enabled:
            return False, ""
        
        phash = self.get_image_hash(temp_path)
        if not phash:
            return False, ""
        
        cursor = self.conn.execute("SELECT path FROM image_hashes WHERE phash = ?", (phash,))
        result = cursor.fetchone()
        if result:
            return True, result[0]
        return False, ""
    
    def get_stats(self) -> dict:
        """Get statistics using efficient database queries"""
        cursor = self.conn.execute("SELECT COUNT(*) FROM image_hashes")
        total = cursor.fetchone()[0]
        
        cursor = self.conn.execute("SELECT COUNT(DISTINCT phash) FROM image_hashes")
        unique = cursor.fetchone()[0]
        
        cursor = self.conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT phash FROM image_hashes GROUP BY phash HAVING COUNT(*) > 1
            )
        """)
        duplicate_groups = cursor.fetchone()[0]
        
        return {
            "enabled": self.enabled,
            "total_indexed": total,
            "unique_hashes": unique,
            "duplicate_groups": duplicate_groups,
            "duplicate_count": total - unique
        }
    
    def close(self):
        self.conn.close()

# ============================================================================
# WALLHAVEN API
# ============================================================================

class WallhavenAPI:
    BASE_URL = "https://wallhaven.cc/api/v1"
    
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"X-API-Key": api_key})
        self.session.headers.update({"User-Agent": "Wallhaven-Changer/1.0"})
    
    def search(self, **params):
        url = f"{self.BASE_URL}/search"
        
        if "categories" in params:
            cats = params.pop("categories")
            if isinstance(cats, dict):
                cat_str = f"{cats.get('general', 1)}{cats.get('anime', 1)}{cats.get('people', 1)}"
                params["categories"] = cat_str
        
        if "purity" in params:
            pur = params.pop("purity")
            if isinstance(pur, dict):
                pur_str = f"{pur.get('sfw', 1)}{pur.get('sketchy', 0)}{pur.get('nsfw', 0)}"
                params["purity"] = pur_str
        
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def download_image(self, url, save_path):
        response = self.session.get(url, stream=True)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return save_path

# ============================================================================
# WALLHAVEN SOURCE
# ============================================================================

class WallhavenSource:
    def __init__(self, api_key=None, filters=None, enabled=True):
        self.name = "Wallhaven"
        self.enabled = enabled
        self.api_key = api_key
        self.filters = filters or {}
        self.api = WallhavenAPI(api_key)
    
    def get_images(self, count=10, tags=None):
        try:
            params = {
                "page": random.randint(1, 5),
                "sorting": "date_added",
                "order": "desc",
                "atleast": self.filters.get("min_resolution", "1920x1080")
            }
            
            if tags:
                params["q"] = tags if isinstance(tags, str) else " ".join(tags)
            
            results = self.api.search(**params)
            
            images = []
            for item in results.get('data', []):
                images.append({
                    'id': f"wallhaven_{item['id']}",
                    'download_url': item['path'],
                    'source': 'wallhaven',
                    'resolution': item.get('resolution', ''),
                    'tags': [tag['name'] for tag in item.get('tags', [])]
                })
            
            return images[:count]
        except Exception as e:
            print(f"Wallhaven error: {e}")
            return []
    
    def search(self, query, count=10):
        return self.get_images(count, query)

# ============================================================================
# SOURCE MANAGER
# ============================================================================

class SourceManager:
    def __init__(self, api_key=None, filters=None):
        self.api_key = api_key
        self.filters = filters or {}
        self.source = WallhavenSource(api_key, filters)
    
    def update_filters(self, filters):
        self.filters = filters
        self.source.filters = filters
    
    def get_images(self, count=10, tags=None):
        if not self.source.enabled:
            return []
        return self.source.get_images(count, tags)
    
    def search(self, query, count=10):
        if not self.source.enabled:
            return []
        return self.source.search(query, count)

# ============================================================================
# FAVORITES DATABASE
# ============================================================================

class FavoritesDatabase:
    def __init__(self):
        db_dir = os.path.dirname(DATABASE_FILE)
        os.makedirs(db_dir, exist_ok=True)
        
        self.conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
        self.lock = threading.Lock()
        self.create_tables()
    
    def create_tables(self):
        with self.lock:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS favorites (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    resolution TEXT,
                    file_type TEXT DEFAULT 'static',
                    download_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_used DATETIME,
                    use_count INTEGER DEFAULT 0,
                    source TEXT DEFAULT 'wallhaven'
                )
            ''')
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wallpaper_id TEXT,
                    set_time DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            self.conn.commit()
    
    def add_favorite(self, wallpaper_data):
        with self.lock:
            try:
                self.conn.execute('''
                    INSERT OR REPLACE INTO favorites 
                    (id, path, resolution, file_type, source, download_date)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    wallpaper_data['id'],
                    wallpaper_data['path'],
                    wallpaper_data.get('resolution', ''),
                    wallpaper_data.get('file_type', 'static'),
                    wallpaper_data.get('source', 'wallhaven')
                ))
                self.conn.commit()
                return True
            except:
                return False
    
    def remove_favorite(self, wallpaper_id):
        with self.lock:
            self.conn.execute('DELETE FROM favorites WHERE id = ?', (wallpaper_id,))
            self.conn.commit()
    
    def get_favorites(self, limit=50):
        with self.lock:
            cursor = self.conn.execute('''
                SELECT * FROM favorites ORDER BY download_date DESC LIMIT ?
            ''', (limit,))
            return cursor.fetchall()
    
    def is_favorite(self, wallpaper_id):
        with self.lock:
            cursor = self.conn.execute('SELECT 1 FROM favorites WHERE id = ?', (wallpaper_id,))
            return cursor.fetchone() is not None
    
    def record_use(self, wallpaper_id):
        with self.lock:
            self.conn.execute('''
                UPDATE favorites SET last_used = CURRENT_TIMESTAMP, use_count = use_count + 1 WHERE id = ?
            ''', (wallpaper_id,))
            self.conn.execute('INSERT INTO history (wallpaper_id) VALUES (?)', (wallpaper_id,))
            self.conn.commit()
    
    def close(self):
        self.conn.close()

# ============================================================================
# FAVORITES FOLDER MANAGER
# ============================================================================

class FavoritesFolderManager:
    def __init__(self, config):
        self.config = config
        self.favorites_folder = config.get("favorites_folder", FAVORITES_FOLDER)
        self.copy_enabled = config.get("copy_to_favorites", True)
        os.makedirs(self.favorites_folder, exist_ok=True)
    
    def copy_to_favorites(self, source_path):
        if not self.copy_enabled:
            return None
        
        try:
            filename = os.path.basename(source_path)
            dest_path = os.path.join(self.favorites_folder, filename)
            
            if os.path.exists(dest_path):
                name, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(os.path.join(self.favorites_folder, f"{name}_{counter}{ext}")):
                    counter += 1
                dest_path = os.path.join(self.favorites_folder, f"{name}_{counter}{ext}")
            
            shutil.copy2(source_path, dest_path)
            return dest_path
        except:
            return None
    
    def get_all_favorites(self):
        files = []
        if os.path.exists(self.favorites_folder):
            for f in os.listdir(self.favorites_folder):
                if f.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    file_path = os.path.join(self.favorites_folder, f)
                    files.append({
                        'path': file_path,
                        'name': f,
                        'size': os.path.getsize(file_path),
                        'modified': os.path.getmtime(file_path)
                    })
        return sorted(files, key=lambda x: x['modified'], reverse=True)

# ============================================================================
# QUOTA MANAGER
# ============================================================================

class QuotaManager:
    def __init__(self, download_folder, enabled=True, max_size_mb=1000):
        self.download_folder = download_folder
        self.enabled = enabled
        self.max_size_mb = max_size_mb
        self.max_size_bytes = max_size_mb * 1024 * 1024
    
    def get_folder_size_mb(self):
        total_size = 0
        if os.path.exists(self.download_folder):
            for f in os.listdir(self.download_folder):
                fp = os.path.join(self.download_folder, f)
                if os.path.isfile(fp):
                    total_size += os.path.getsize(fp)
        return total_size / (1024 * 1024)
    
    def can_download(self, file_size_mb):
        if not self.enabled:
            return True
        return (self.get_folder_size_mb() + file_size_mb) <= self.max_size_mb

# ============================================================================
# KEYWORD MANAGER
# ============================================================================

class KeywordManager:
    def __init__(self):
        self.keywords = []
        self.downloads_per_keyword = 10
        self.last_download = {}
        self.load_keywords()
    
    def load_keywords(self):
        if os.path.exists(KEYWORDS_FILE):
            try:
                with open(KEYWORDS_FILE, 'r') as f:
                    data = json.load(f)
                    self.keywords = data.get('keywords', [])
                    self.downloads_per_keyword = data.get('downloads_per_keyword', 10)
                    self.last_download = data.get('last_download', {})
            except:
                pass
        
        if not self.keywords:
            self.keywords = ["nature", "landscape", "city", "space", "abstract"]
            self.save_keywords()
    
    def save_keywords(self):
        data = {
            'keywords': self.keywords,
            'downloads_per_keyword': self.downloads_per_keyword,
            'last_download': self.last_download
        }
        with open(KEYWORDS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_keyword(self, keyword):
        if keyword and keyword not in self.keywords:
            self.keywords.append(keyword)
            self.save_keywords()
            return True
        return False
    
    def remove_keyword(self, keyword):
        if keyword in self.keywords:
            self.keywords.remove(keyword)
            self.save_keywords()
            return True
        return False
    
    def get_keywords_for_download(self):
        return [k for k in self.keywords if self.can_download_today(k)]
    
    def can_download_today(self, keyword):
        if keyword not in self.last_download:
            return True
        last = datetime.fromisoformat(self.last_download[keyword])
        return last.date() < datetime.now().date()
    
    def record_download(self, keyword):
        self.last_download[keyword] = datetime.now().isoformat()
        self.save_keywords()

# ============================================================================
# BATCH DOWNLOADER
# ============================================================================

class BatchDownloader:
    def __init__(self, source_manager, download_folder, quota_manager=None, duplicate_detector=None):
        self.source_manager = source_manager
        self.download_folder = download_folder
        self.quota_manager = quota_manager
        self.duplicate_detector = duplicate_detector
        self.is_downloading = False
        self.progress_callback = None
        self.complete_callback = None
        self.stop_event = threading.Event()
    
    def download_keyword(self, keyword, count=10):
        results = []
        skipped = 0
        
        try:
            images = self.source_manager.search(keyword, count * 2)
            
            for img in images[:count]:
                if self.stop_event.is_set():
                    break
                
                try:
                    if self.quota_manager and not self.quota_manager.can_download(5):
                        break
                    
                    # Download to temp file first
                    response = requests.get(img['download_url'], timeout=30)
                    file_ext = os.path.splitext(img['download_url'])[1] or '.jpg'
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                        tmp_file.write(response.content)
                        temp_path = tmp_file.name
                    
                    # Check for duplicates
                    if self.duplicate_detector and self.duplicate_detector.enabled:
                        is_dup, existing = self.duplicate_detector.check_before_download(temp_path)
                        if is_dup:
                            os.unlink(temp_path)
                            skipped += 1
                            if self.progress_callback:
                                self.progress_callback(f"Skipped duplicate: {img['id']}")
                            continue
                    
                    # Save final file
                    filename = f"{keyword}_{img['source']}_{img['id']}{file_ext}"
                    save_path = os.path.join(self.download_folder, filename)
                    shutil.move(temp_path, save_path)
                    
                    # Index in duplicate detector
                    if self.duplicate_detector and self.duplicate_detector.enabled:
                        self.duplicate_detector.index_image(save_path)
                    
                    results.append(save_path)
                    time.sleep(0.5)
                    
                except Exception as e:
                    print(f"Error downloading: {e}")
            
        except Exception as e:
            print(f"Error downloading keyword {keyword}: {e}")
        
        return results, skipped
    
    def download_all(self, keywords, per_keyword=10):
        if not keywords:
            if self.progress_callback:
                self.progress_callback("No keywords to download")
            return {}
        
        self.is_downloading = True
        self.stop_event.clear()
        all_results = {}
        total_skipped = 0
        
        for keyword in keywords:
            if self.stop_event.is_set():
                break
            
            if self.progress_callback:
                self.progress_callback(f"Starting: {keyword}")
            
            results, skipped = self.download_keyword(keyword, per_keyword)
            all_results[keyword] = results
            total_skipped += skipped
            
            if self.progress_callback:
                self.progress_callback(f"Downloaded {len(results)} for '{keyword}' (skipped {skipped})")
        
        self.is_downloading = False
        
        if self.complete_callback:
            self.complete_callback(all_results, total_skipped)
        
        return all_results
    
    def stop_download(self):
        self.stop_event.set()
        self.is_downloading = False

# ============================================================================
# WALLPAPER CHANGER CORE
# ============================================================================

class WallpaperChanger:
    def __init__(self, config=None, app=None):
        self.app = app
        self.config = config or self.load_config()
        self.paused = False
        
        if not self.config.get("download_folder"):
            self.config["download_folder"] = WALLHAVEN_FOLDER
        
        # Get API key securely
        api_key = SecureConfig.get_api_key(self.config)
        self.api = WallhavenAPI(api_key)
        self.db = FavoritesDatabase()
        self.quota = QuotaManager(
            self.config["download_folder"],
            self.config.get("quota_enabled", True),
            self.config.get("quota_size", 1000)
        )
        self.favorites_folder_manager = FavoritesFolderManager(self.config)
        self.validator = WallpaperValidator()
        self.running = False
        self.timer = None
        self.current_wallpaper = None
        self.current_wallpaper_id = None
        self.current_wallpaper_type = "static"
        self.downloaded_wallpapers = []
        self.current_nav_index = -1
        self.notification_callback = None
        self.duplicate_detector = None
        
        os.makedirs(self.config["download_folder"], exist_ok=True)
        
        if self.config.get("remember_last_wallpaper", True):
            self.load_last_wallpaper()
        
        self.scan_downloaded_wallpapers()
    
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    merged = DEFAULT_CONFIG.copy()
                    merged.update(config)
                    return merged
            except:
                pass
        return DEFAULT_CONFIG.copy()
    
    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def get_interval_seconds(self):
        value = self.config.get("interval_value", 30)
        unit = self.config.get("interval_unit", "minutes")
        
        if unit == "minutes":
            return value * 60
        elif unit == "hours":
            return value * 3600
        elif unit == "days":
            return value * 86400
        return value * 60
    
    def load_last_wallpaper(self):
        if os.path.exists(LAST_WALLPAPER_FILE):
            try:
                with open(LAST_WALLPAPER_FILE, 'r') as f:
                    data = json.load(f)
                    path = data.get('path', '')
                    if os.path.exists(path) and self.validator.is_valid_image(path):
                        self.set_wallpaper(path, data.get('id'), data.get('type', 'static'))
            except:
                pass
    
    def scan_downloaded_wallpapers(self):
        folder = self.config["download_folder"]
        self.downloaded_wallpapers = []
        
        if os.path.exists(folder):
            for file in sorted(os.listdir(folder)):
                if file.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    full_path = os.path.join(folder, file)
                    if self.validator.is_valid_image(full_path):
                        self.downloaded_wallpapers.append(full_path)
        
        if self.current_wallpaper in self.downloaded_wallpapers:
            self.current_nav_index = self.downloaded_wallpapers.index(self.current_wallpaper)
        else:
            self.current_nav_index = -1
    
    def delete_current_wallpaper(self):
        if not self.current_wallpaper:
            return False, "No wallpaper to delete"
        
        try:
            if self.current_wallpaper_id and self.db.is_favorite(self.current_wallpaper_id):
                return False, "Cannot delete favorite"
            
            if self.current_wallpaper in self.downloaded_wallpapers:
                self.downloaded_wallpapers.remove(self.current_wallpaper)
            
            # Remove from duplicate detector
            if self.duplicate_detector and self.duplicate_detector.enabled:
                try:
                    self.duplicate_detector.conn.execute("DELETE FROM image_hashes WHERE path = ?", (self.current_wallpaper,))
                    self.duplicate_detector.conn.commit()
                except:
                    pass
            
            os.remove(self.current_wallpaper)
            
            if self.downloaded_wallpapers:
                next_idx = min(self.current_nav_index, len(self.downloaded_wallpapers) - 1)
                if next_idx >= 0:
                    self.set_wallpaper(self.downloaded_wallpapers[next_idx])
            
            return True, "Wallpaper deleted"
        except Exception as e:
            return False, f"Error: {e}"
    
    def next_wallpaper(self):
        if self.config.get("random_order", True):
            return self.shuffle_wallpaper()
        else:
            return self.next_sequential()
    
    def previous_wallpaper(self):
        if self.config.get("random_order", True):
            return self.shuffle_wallpaper(avoid_current=True)
        else:
            return self.previous_sequential()
    
    def shuffle_wallpaper(self, avoid_current=False):
        folder = self.config.get("download_folder")
        if not os.path.exists(folder):
            return False
        
        supported = (".jpg", ".jpeg", ".png", ".gif")
        all_files = [f for f in os.listdir(folder) if f.lower().endswith(supported)]
        
        if not all_files:
            return False
        
        if avoid_current and self.current_wallpaper:
            current_name = os.path.basename(self.current_wallpaper)
            candidates = [f for f in all_files if f != current_name]
            if not candidates:
                candidates = all_files
        else:
            candidates = all_files
        
        # Try up to 5 times to find a valid image
        for _ in range(5):
            selected = random.choice(candidates)
            full_path = os.path.join(folder, selected)
            
            if self.validator.is_valid_image(full_path):
                file_type = "gif" if selected.lower().endswith('.gif') else "static"
                wallpaper_id = f"local_{int(time.time())}"
                self.set_wallpaper(full_path, wallpaper_id, file_type)
                return True
        
        return False
    
    def next_sequential(self):
        if self.current_nav_index < len(self.downloaded_wallpapers) - 1:
            self.current_nav_index += 1
            path = self.downloaded_wallpapers[self.current_nav_index]
            
            if self.validator.is_valid_image(path):
                file_type = "gif" if path.lower().endswith('.gif') else "static"
                self.set_wallpaper(path, f"local_{int(time.time())}", file_type)
                return True
        return False
    
    def previous_sequential(self):
        if self.current_nav_index > 0:
            self.current_nav_index -= 1
            path = self.downloaded_wallpapers[self.current_nav_index]
            
            if self.validator.is_valid_image(path):
                file_type = "gif" if path.lower().endswith('.gif') else "static"
                self.set_wallpaper(path, f"local_{int(time.time())}", file_type)
                return True
        return False
    
    def set_wallpaper_style(self, style):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Control Panel\\Desktop", 0, winreg.KEY_SET_VALUE)
            style_values = {
                'fill': ('10', '0'), 'fit': ('6', '0'), 'stretch': ('2', '0'),
                'tile': ('0', '1'), 'center': ('0', '0'), 'span': ('22', '0')
            }
            if style in style_values:
                wallpaper_style, tile_wallpaper = style_values[style]
                winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, wallpaper_style)
                winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, tile_wallpaper)
            winreg.CloseKey(key)
        except:
            pass
    
    def set_wallpaper(self, image_path, wallpaper_id=None, file_type="static"):
        # Validate image before setting
        if not self.validator.is_valid_image(image_path):
            if self.app:
                self.app.status_var.set("Invalid image file")
            return False
        
        self.set_wallpaper_style(self.config.get("wallpaper_style", "fill"))
        
        image_path = os.path.abspath(image_path)
        ctypes.windll.user32.SystemParametersInfoW(20, 0, image_path, 3)
        
        self.current_wallpaper = image_path
        self.current_wallpaper_id = wallpaper_id
        self.current_wallpaper_type = file_type
        
        if image_path in self.downloaded_wallpapers:
            self.current_nav_index = self.downloaded_wallpapers.index(image_path)
        
        if wallpaper_id and self.db.is_favorite(wallpaper_id):
            self.db.record_use(wallpaper_id)
        
        try:
            with open(LAST_WALLPAPER_FILE, 'w') as f:
                json.dump({'path': image_path, 'id': wallpaper_id, 'type': file_type}, f)
        except:
            pass
        
        if self.config.get("notifications", True) and self.notification_callback:
            self.notification_callback("Wallpaper Changed", os.path.basename(image_path))
        
        return True
    
    def start_auto_change(self):
        if self.running:
            return
        self.running = True
        self.paused = False
        self.auto_change_loop()
    
    def stop_auto_change(self):
        self.running = False
        if self.timer:
            self.timer.cancel()
            self.timer = None
    
    def toggle_pause(self):
        if not self.running:
            self.start_auto_change()
            result = "Started"
        else:
            self.paused = not self.paused
            result = "Paused" if self.paused else "Resumed"
        
        # Update system tray menu if available
        if hasattr(self, 'app') and self.app and hasattr(self.app, 'tray'):
            try:
                self.app.tray.update_menu()
            except:
                pass
        
        return result
    
    def auto_change_loop(self):
        if not self.running:
            return
        
        if not self.paused:
            try:
                self.change_wallpaper()
            except Exception as e:
                print(f"Error in auto-change: {e}")
                if self.app:
                    self.app.status_var.set(f"Auto-change error: {str(e)[:50]}")
        
        self.timer = threading.Timer(self.get_interval_seconds(), self.auto_change_loop)
        self.timer.daemon = True
        self.timer.start()
    
    def change_wallpaper(self):
        try:
            images = self.api.search(page=random.randint(1, 5), sorting="random")
            if images and images.get('data'):
                selected = random.choice(images['data'])
                img_url = selected['path']
                file_ext = os.path.splitext(img_url)[1] or '.jpg'
                filename = f"wallhaven_{selected['id']}{file_ext}"
                save_path = os.path.join(self.config["download_folder"], filename)
                
                self.api.download_image(img_url, save_path)
                
                # Validate downloaded image
                if not self.validator.is_valid_image(save_path):
                    os.remove(save_path)
                    return False
                
                self.set_wallpaper(save_path, selected['id'], "static")
                
                # Index in duplicate detector
                if self.duplicate_detector and self.duplicate_detector.enabled:
                    self.duplicate_detector.index_image(save_path)
                
                return True
            return False
        except Exception as e:
            print(f"Error changing wallpaper: {e}")
            return False
    
    def toggle_favorite_current(self):
        if not self.current_wallpaper_id:
            return False, "No wallpaper"
        
        if self.db.is_favorite(self.current_wallpaper_id):
            self.db.remove_favorite(self.current_wallpaper_id)
            return False, "Removed from favorites"
        else:
            fav_data = {
                'id': self.current_wallpaper_id,
                'path': self.current_wallpaper,
                'resolution': '',
                'file_type': self.current_wallpaper_type,
                'source': 'local' if self.current_wallpaper_id.startswith('local_') else 'wallhaven'
            }
            self.db.add_favorite(fav_data)
            return True, "Added to favorites"
    
    def get_navigation_info(self):
        total = len(self.downloaded_wallpapers)
        current = self.current_nav_index + 1 if self.current_nav_index >= 0 else 0
        return current, total

# ============================================================================
# MODERN UI WIDGETS
# ============================================================================

class ModernCard(tk.Frame):
    def __init__(self, parent, colors, **kwargs):
        super().__init__(parent, bg=colors["card_bg"], **kwargs)
        self.colors = colors
        self.configure(relief='flat', bd=0)
        self.inner = tk.Frame(self, bg=colors["card_bg"])
        self.inner.pack(fill='both', expand=True, padx=12, pady=12)

class ModernButton(tk.Button):
    def __init__(self, parent, text="", command=None, variant="primary", **kwargs):
        # Try to get colors from parent, fallback to light scheme
        if hasattr(parent, 'colors'):
            colors = parent.colors
        else:
            # Walk up the widget hierarchy to find colors
            colors = COLOR_SCHEMES["light"]
            p = parent
            while p:
                if hasattr(p, 'colors'):
                    colors = p.colors
                    break
                p = p.master
        
        variants = {
            "primary": {"bg": colors["accent"], "fg": "white", "hover": colors["accent_light"]},
            "secondary": {"bg": colors["card_bg"], "fg": colors["fg"], "hover": colors["card_shadow"]},
            "success": {"bg": colors["success"], "fg": "white", "hover": "#34d399"},
            "danger": {"bg": colors["error"], "fg": "white", "hover": "#f87171"},
            "info": {"bg": colors["info"], "fg": "white", "hover": colors["accent_light"]}
        }
        
        style = variants.get(variant, variants["primary"])
        
        super().__init__(parent, text=text, command=command,
                        bg=style["bg"], fg=style["fg"],
                        font=('Segoe UI', 10),
                        relief='flat', bd=0,
                        padx=16, pady=8,
                        cursor='hand2',
                        activebackground=style["hover"],
                        activeforeground="white",
                        **kwargs)
        
        self.bind('<Enter>', lambda e: self.config(bg=style["hover"]))
        self.bind('<Leave>', lambda e: self.config(bg=style["bg"]))

class ModernToggle(tk.Frame):
    def __init__(self, parent, text="", variable=None, **kwargs):
        # Find colors from parent hierarchy
        self.colors = COLOR_SCHEMES["light"]  # default
        p = parent
        while p:
            if hasattr(p, 'colors'):
                self.colors = p.colors
                break
            p = p.master
        
        super().__init__(parent, bg=self.colors["bg"])
        self.variable = variable or tk.BooleanVar()
        
        if text:
            self.label = tk.Label(self, text=text, bg=self.colors["bg"], fg=self.colors["fg"])
            self.label.pack(side='left', padx=(0, 10))
        
        self.canvas = tk.Canvas(self, width=50, height=26, bg=self.colors["bg"], highlightthickness=0)
        self.canvas.pack(side='left')
        
        self.draw_toggle()
        self.canvas.bind('<Button-1>', self.toggle)
        self.variable.trace('w', lambda *args: self.draw_toggle())
    
    def draw_toggle(self):
        self.canvas.delete("all")
        if self.variable.get():
            self.canvas.create_rectangle(0, 0, 50, 26, fill=self.colors["accent"], outline="")
            self.canvas.create_oval(26, 2, 48, 24, fill="white", outline="")
        else:
            self.canvas.create_rectangle(0, 0, 50, 26, fill=self.colors["trough_color"], outline="")
            self.canvas.create_oval(2, 2, 24, 24, fill="white", outline="")
    
    def toggle(self, event=None):
        self.variable.set(not self.variable.get())

# ============================================================================
# SYSTEM TRAY
# ============================================================================

class SystemTray:
    def __init__(self, changer, app):
        self.changer = changer
        self.app = app
        self.icon = None
        self.create_icon()
    
    def create_icon(self):
        icon_size = 64
        colors = COLOR_SCHEMES[self.app.current_scheme]
        
        image = Image.new('RGB', (icon_size, icon_size), color=colors["accent"])
        draw = ImageDraw.Draw(image)
        draw.rectangle([10, 10, 54, 54], fill=colors["card_bg"], outline=colors["accent_dark"], width=2)
        draw.rectangle([20, 20, 44, 44], fill=colors["accent"])
        
        pause_status = "⏸️ Paused" if self.changer.paused else "▶️ Running"
        
        menu = pystray.Menu(
            pystray.MenuItem(f"Status: {pause_status}", None, enabled=False),
            pystray.MenuItem("Next Wallpaper", self.next_wallpaper),
            pystray.MenuItem("Previous Wallpaper", self.previous_wallpaper),
            pystray.MenuItem("Delete Current", self.delete_wallpaper),
            pystray.MenuItem("⏯️ Pause/Resume", self.toggle_pause),
            pystray.MenuItem(
                "Favorites",
                pystray.Menu(
                    pystray.MenuItem("Add Current", self.add_to_favorites),
                    pystray.MenuItem("Random Favorite", self.random_favorite),
                )
            ),
            pystray.MenuItem(
                "Duplicate Detector",
                pystray.Menu(
                    pystray.MenuItem("Scan for Duplicates", self.scan_duplicates),
                    pystray.MenuItem("Cleanup Duplicates", self.cleanup_duplicates),
                )
            ),
            pystray.MenuItem(
                "Theme",
                pystray.Menu(
                    pystray.MenuItem("Light", lambda: self.app.change_color_scheme("light")),
                    pystray.MenuItem("Dark", lambda: self.app.change_color_scheme("dark"))
                )
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Download Folder", self.open_folder),
            pystray.MenuItem("Settings", self.show_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self.exit_app)
        )
        
        self.icon = pystray.Icon("wallpaper_changer", image, "Wallpaper Changer", menu)
        self.changer.notification_callback = self.show_notification
    
    def next_wallpaper(self):
        self.app.root.after(0, self.app.next_wallpaper)
    
    def previous_wallpaper(self):
        self.app.root.after(0, self.app.previous_wallpaper)
    
    def delete_wallpaper(self):
        self.app.root.after(0, self.app.delete_current_wallpaper)
    
    def toggle_pause(self):
        self.app.root.after(0, self.app.toggle_pause)
        self.update_menu()
    
    def add_to_favorites(self):
        self.app.toggle_favorite()
    
    def random_favorite(self):
        favorites = self.changer.db.get_favorites(limit=100)
        if favorites:
            favorite = random.choice(favorites)
            file_type = favorite[3] if len(favorite) > 3 else "static"
            self.changer.set_wallpaper(favorite[1], favorite[0], file_type)
            self.app.update_preview()
    
    def scan_duplicates(self):
        self.app.root.after(0, lambda: self.app.show_duplicate_tab())
        self.app.root.after(500, lambda: self.app.duplicate_tab.find_duplicates())
    
    def cleanup_duplicates(self):
        self.app.root.after(0, lambda: self.app.show_duplicate_tab())
        self.app.root.after(500, lambda: self.app.duplicate_tab.cleanup_duplicates())
    
    def open_folder(self):
        folder = self.changer.config["download_folder"]
        if os.path.exists(folder):
            os.startfile(folder)
    
    def show_settings(self):
        self.app.show_window()
    
    def exit_app(self):
        self.changer.stop_auto_change()
        self.changer.db.close()
        if hasattr(self.app, 'duplicate_detector'):
            self.app.duplicate_detector.close()
        self.icon.stop()
        self.app.quit()
    
    def show_notification(self, title, message):
        if self.icon and self.changer.config.get("notifications", True):
            self.icon.notify(message, title)
    
    def update_menu(self):
        """Update the system tray menu"""
        if self.icon:
            self.icon.stop()
            self.create_icon()
            threading.Thread(target=self.icon.run, daemon=True).start()
    
    def run(self):
        threading.Thread(target=self.icon.run, daemon=True).start()

# ============================================================================
# DUPLICATE DETECTOR TAB
# ============================================================================

class DuplicateDetectorTab:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.config = app.changer.config
        self.duplicate_detector = app.duplicate_detector
        self.scan_stop_event = threading.Event()
        
        self.setup_ui()
        self.update_stats()
    
    def setup_ui(self):
        header = tk.Frame(self.parent, bg=self.colors["bg"])
        header.pack(fill='x', pady=10)
        
        tk.Label(header, text="🔄 Duplicate Detector", 
                bg=self.colors["bg"], fg=self.colors["accent"],
                font=('Segoe UI', 16, 'bold')).pack(side='left')
        
        status_frame = tk.Frame(header, bg=self.colors["bg"])
        status_frame.pack(side='right', padx=10)
        
        self.duplicate_enabled = tk.BooleanVar(value=self.config.get("duplicate_detection_enabled", True))
        self.duplicate_enabled.trace('w', lambda *args: self.toggle_duplicate())
        
        self.duplicate_toggle = ModernToggle(status_frame, text="Detection", variable=self.duplicate_enabled)
        self.duplicate_toggle.pack(side='left')
        
        # Stats Card
        stats_card = ModernCard(self.parent, self.colors)
        stats_card.pack(fill='x', pady=5)
        
        self.stats_var = tk.StringVar(value="Loading...")
        tk.Label(stats_card.inner, textvariable=self.stats_var,
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=5)
        
        # Settings Card
        settings_card = ModernCard(self.parent, self.colors)
        settings_card.pack(fill='x', pady=5)
        
        # Hash Size
        hash_frame = tk.Frame(settings_card.inner, bg=self.colors["card_bg"])
        hash_frame.pack(fill='x', pady=5)
        
        tk.Label(hash_frame, text="Hash Size:", bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(side='left')
        self.hash_size_var = tk.IntVar(value=self.config.get("duplicate_hash_size", 8))
        tk.Spinbox(hash_frame, from_=4, to=16, textvariable=self.hash_size_var,
                  bg=self.colors["entry_bg"], fg=self.colors["fg"], width=5).pack(side='left', padx=5)
        
        # Keep Newest
        keep_frame = tk.Frame(settings_card.inner, bg=self.colors["card_bg"])
        keep_frame.pack(fill='x', pady=5)
        
        self.keep_newest_var = tk.BooleanVar(value=self.config.get("duplicate_keep_newest", True))
        tk.Checkbutton(keep_frame, text="Keep newest file when cleaning", variable=self.keep_newest_var,
                      bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w')
        
        # Action Buttons
        action_card = ModernCard(self.parent, self.colors)
        action_card.pack(fill='x', pady=5)
        
        btn_frame = tk.Frame(action_card.inner, bg=self.colors["card_bg"])
        btn_frame.pack(fill='x', pady=5)
        
        ModernButton(btn_frame, text="🔍 Scan Folder", command=self.scan_folder).pack(side='left', padx=2)
        ModernButton(btn_frame, text="🔎 Find Duplicates", command=self.find_duplicates, variant="info").pack(side='left', padx=2)
        ModernButton(btn_frame, text="🧹 Cleanup", command=self.cleanup_duplicates, variant="danger").pack(side='left', padx=2)
        ModernButton(btn_frame, text="⏹️ Stop Scan", command=self.stop_scan, variant="warning").pack(side='left', padx=2)
        ModernButton(btn_frame, text="💾 Save Settings", command=self.save_settings, variant="success").pack(side='left', padx=2)
        
        # Progress
        progress_card = ModernCard(self.parent, self.colors)
        progress_card.pack(fill='x', pady=5)
        
        self.progress_var = tk.StringVar(value="Ready")
        tk.Label(progress_card.inner, textvariable=self.progress_var,
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=5)
        
        self.progress_bar = ttk.Progressbar(progress_card.inner, mode='indeterminate')
        self.progress_bar.pack(fill='x', pady=5)
    
    def toggle_duplicate(self):
        self.config["duplicate_detection_enabled"] = self.duplicate_enabled.get()
        self.duplicate_detector.enabled = self.duplicate_enabled.get()
        self.app.changer.save_config()
        self.update_stats()
    
    def update_stats(self):
        stats = self.duplicate_detector.get_stats()
        self.stats_var.set(f"Indexed: {stats['total_indexed']} | Unique: {stats['unique_hashes']} | Duplicates: {stats['duplicate_count']}")
        self.parent.after(5000, self.update_stats)
    
    def scan_folder(self):
        folder = self.app.changer.config["download_folder"]
        if messagebox.askyesno("Confirm", f"Scan {folder}?"):
            self.scan_stop_event.clear()
            self.progress_bar.start()
            self.progress_var.set("Scanning...")
            
            def do_scan():
                def update_progress(msg, count):
                    self.app.root.after(0, lambda: self.progress_var.set(f"Indexed: {count}"))
                
                indexed, existing = self.duplicate_detector.scan_folder(
                    folder, 
                    update_progress,
                    self.scan_stop_event
                )
                self.app.root.after(0, lambda: self.scan_done(indexed, existing))
            
            threading.Thread(target=do_scan, daemon=True).start()
    
    def stop_scan(self):
        self.scan_stop_event.set()
        self.progress_var.set("Stopping scan...")
    
    def scan_done(self, indexed, existing):
        self.progress_bar.stop()
        self.progress_var.set(f"Scan complete! Indexed: {indexed} new, {existing} existing.")
        self.update_stats()
    
    def find_duplicates(self):
        self.progress_bar.start()
        self.progress_var.set("Finding duplicates...")
        
        def do_find():
            duplicates = self.duplicate_detector.find_duplicates()
            self.app.root.after(0, lambda: self.show_duplicates(duplicates))
        
        threading.Thread(target=do_find, daemon=True).start()
    
    def show_duplicates(self, duplicates):
        self.progress_bar.stop()
        
        if not duplicates:
            messagebox.showinfo("No Duplicates", "No duplicates found!")
            return
        
        dialog = tk.Toplevel(self.app.root)
        dialog.title(f"Found {len(duplicates)} Duplicates")
        dialog.geometry("500x400")
        dialog.transient(self.app.root)
        dialog.configure(bg=self.colors["bg"])
        
        listbox = tk.Listbox(dialog, bg=self.colors["entry_bg"], fg=self.colors["fg"])
        listbox.pack(fill='both', expand=True, padx=10, pady=10)
        
        for file1, file2 in duplicates[:50]:
            listbox.insert(tk.END, f"{os.path.basename(file1)} == {os.path.basename(file2)}")
        
        ModernButton(dialog, text="Close", command=dialog.destroy).pack(pady=10)
    
    def cleanup_duplicates(self):
        if messagebox.askyesno("Confirm", "Delete duplicate files?"):
            self.progress_bar.start()
            self.progress_var.set("Cleaning up...")
            
            def do_cleanup():
                deleted = self.duplicate_detector.cleanup_duplicates(self.keep_newest_var.get())
                self.app.root.after(0, lambda: self.cleanup_done(deleted))
            
            threading.Thread(target=do_cleanup, daemon=True).start()
    
    def cleanup_done(self, deleted):
        self.progress_bar.stop()
        self.progress_var.set(f"Deleted {deleted} duplicate files")
        self.update_stats()
        self.app.changer.scan_downloaded_wallpapers()
        self.app.update_navigation_display()
    
    def save_settings(self):
        self.config["duplicate_hash_size"] = self.hash_size_var.get()
        self.config["duplicate_keep_newest"] = self.keep_newest_var.get()
        self.duplicate_detector.hash_size = self.hash_size_var.get()
        self.app.changer.save_config()
        messagebox.showinfo("Success", "Settings saved!")

# ============================================================================
# KEYWORDS TAB
# ============================================================================

class KeywordsTab:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.keyword_manager = KeywordManager()
        self.batch_downloader = None
        
        self.setup_ui()
    
    def setup_ui(self):
        # Keywords List
        card = ModernCard(self.parent, self.colors)
        card.pack(fill='both', expand=True, pady=5)
        
        tk.Label(card.inner, text="🔑 Keywords", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=5)
        
        # Add keyword
        add_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        add_frame.pack(fill='x', pady=5)
        
        self.keyword_var = tk.StringVar()
        tk.Entry(add_frame, textvariable=self.keyword_var,
                bg=self.colors["entry_bg"], fg=self.colors["fg"], width=30).pack(side='left', padx=5)
        
        ModernButton(add_frame, text="Add", command=self.add_keyword).pack(side='left')
        
        # Keywords listbox
        list_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        list_frame.pack(fill='both', expand=True, pady=5)
        
        self.keywords_listbox = tk.Listbox(list_frame, height=8, bg=self.colors["entry_bg"], fg=self.colors["fg"])
        self.keywords_listbox.pack(side='left', fill='both', expand=True)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side='right', fill='y')
        self.keywords_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.keywords_listbox.yview)
        
        # Buttons
        btn_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        btn_frame.pack(fill='x', pady=5)
        
        ModernButton(btn_frame, text="Remove Selected", command=self.remove_keyword, variant="danger").pack(side='left', padx=2)
        ModernButton(btn_frame, text="Download Now", command=self.download_now, variant="success").pack(side='right', padx=2)
        
        # Settings
        settings_card = ModernCard(self.parent, self.colors)
        settings_card.pack(fill='x', pady=5)
        
        per_frame = tk.Frame(settings_card.inner, bg=self.colors["card_bg"])
        per_frame.pack(fill='x', pady=5)
        
        tk.Label(per_frame, text="Per keyword:", bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(side='left')
        self.per_keyword_var = tk.IntVar(value=self.keyword_manager.downloads_per_keyword)
        tk.Spinbox(per_frame, from_=1, to=50, textvariable=self.per_keyword_var, width=5).pack(side='left', padx=5)
        ModernButton(per_frame, text="Save", command=self.save_settings).pack(side='left', padx=5)
        
        # Progress
        progress_card = ModernCard(self.parent, self.colors)
        progress_card.pack(fill='x', pady=5)
        
        self.progress_var = tk.StringVar(value="Ready")
        tk.Label(progress_card.inner, textvariable=self.progress_var,
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=5)
        
        self.progress_bar = ttk.Progressbar(progress_card.inner, mode='indeterminate')
        self.progress_bar.pack(fill='x', pady=5)
        
        self.stop_btn = ModernButton(progress_card.inner, text="Stop", command=self.stop_download, variant="danger", state='disabled')
        self.stop_btn.pack(pady=5)
        
        self.load_keywords()
    
    def load_keywords(self):
        self.keywords_listbox.delete(0, tk.END)
        for kw in self.keyword_manager.keywords:
            self.keywords_listbox.insert(tk.END, kw)
    
    def add_keyword(self):
        kw = self.keyword_var.get().strip()
        if kw and self.keyword_manager.add_keyword(kw):
            self.load_keywords()
            self.keyword_var.set("")
    
    def remove_keyword(self):
        sel = self.keywords_listbox.curselection()
        if sel:
            kw = self.keywords_listbox.get(sel[0])
            self.keyword_manager.remove_keyword(kw)
            self.load_keywords()
    
    def save_settings(self):
        self.keyword_manager.downloads_per_keyword = self.per_keyword_var.get()
        self.keyword_manager.save_keywords()
    
    def download_now(self):
        if not self.keyword_manager.keywords:
            messagebox.showinfo("No Keywords", "Add some keywords first!")
            return
        
        self.batch_downloader = BatchDownloader(
            self.app.source_manager,
            self.app.changer.config["download_folder"],
            self.app.changer.quota,
            self.app.duplicate_detector
        )
        self.batch_downloader.progress_callback = self.update_progress
        self.batch_downloader.complete_callback = self.download_complete
        
        self.progress_bar.start()
        self.stop_btn.config(state='normal')
        self.progress_var.set("Starting download...")
        
        def download_thread():
            results = self.batch_downloader.download_all(
                self.keyword_manager.keywords,
                self.keyword_manager.downloads_per_keyword
            )
            for kw in self.keyword_manager.keywords:
                self.keyword_manager.record_download(kw)
        
        threading.Thread(target=download_thread, daemon=True).start()
    
    def update_progress(self, msg):
        self.progress_var.set(msg)
    
    def download_complete(self, results, skipped):
        self.progress_bar.stop()
        self.stop_btn.config(state='disabled')
        total = sum(len(paths) for paths in results.values())
        self.progress_var.set(f"Downloaded {total} (skipped {skipped})")
        self.app.changer.scan_downloaded_wallpapers()
        self.app.update_navigation_display()
    
    def stop_download(self):
        if self.batch_downloader:
            self.batch_downloader.stop_download()
            self.progress_var.set("Stopped")

# ============================================================================
# SETTINGS TAB (UPDATED with Security Status)
# ============================================================================

class SettingsTab:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.config = app.changer.config
        
        self.setup_ui()
        self.check_keyring_status()
    
    def check_keyring_status(self):
        """Check and display keyring status"""
        if HAS_KEYRING:
            try:
                # Test keyring by setting and getting a test value
                test_key = "test_connection"
                keyring.set_password("WallpaperChanger", test_key, "working")
                result = keyring.get_password("WallpaperChanger", test_key)
                keyring.delete_password("WallpaperChanger", test_key)
                
                if result == "working":
                    # Determine which backend is being used
                    backend = str(keyring.get_keyring())
                    if "Windows" in backend:
                        storage = "Windows Credential Manager"
                    else:
                        storage = "Keyring"
                    
                    self.keyring_status.config(
                        text=f"✅ Active - Keys stored in {storage}", 
                        fg=self.colors["success"]
                    )
                else:
                    self.keyring_status.config(
                        text="⚠️ Keyring test failed - using config file", 
                        fg=self.colors["warning"]
                    )
            except Exception as e:
                self.keyring_status.config(
                    text=f"⚠️ Keyring error: {str(e)[:50]} - using config file", 
                    fg=self.colors["warning"]
                )
        else:
            self.keyring_status.config(
                text="⚠️ Keyring not installed - API keys stored in config file", 
                fg=self.colors["warning"]
            )
    
    def setup_ui(self):
        card = ModernCard(self.parent, self.colors)
        card.pack(fill='x', pady=5)
        
        # ===== SECURITY STATUS SECTION =====
        security_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        security_frame.pack(fill='x', pady=5)
        
        tk.Label(security_frame, text="🔐 Security Status:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        self.keyring_status = tk.Label(security_frame, text="Checking...",
                                       bg=self.colors["card_bg"], fg=self.colors["fg"],
                                       font=('Segoe UI', 9))
        self.keyring_status.pack(anchor='w', pady=2)
        
        # Info about where keys are stored
        if HAS_KEYRING:
            tk.Label(security_frame, 
                    text="✓ API keys can be stored securely in Windows Credential Manager",
                    bg=self.colors["card_bg"], fg=self.colors["fg"],
                    font=('Segoe UI', 8)).pack(anchor='w', padx=10)
        else:
            tk.Label(security_frame, 
                    text="⚠️ Install keyring for secure storage: pip install keyring",
                    bg=self.colors["card_bg"], fg=self.colors["warning"],
                    font=('Segoe UI', 8)).pack(anchor='w', padx=10)
        
        # Separator
        ttk.Separator(card.inner, orient='horizontal').pack(fill='x', pady=10)
        
        # ===== API KEY SECTION =====
        api_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        api_frame.pack(fill='x', pady=5)
        
        tk.Label(api_frame, text="Wallhaven API Key:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        # API Key entry
        api_row = tk.Frame(api_frame, bg=self.colors["card_bg"])
        api_row.pack(fill='x', pady=2)
        
        # Get current API key (might be in keyring)
        current_key = SecureConfig.get_api_key(self.config)
        self.api_key_var = tk.StringVar(value=current_key)
        
        self.api_key_entry = tk.Entry(api_row, textvariable=self.api_key_var, width=40, show="*")
        self.api_key_entry.pack(side='left', fill='x', expand=True)
        
        # Show/hide key checkbox
        self.show_api_key = tk.BooleanVar(value=False)
        def toggle_api_key():
            self.api_key_entry.config(show="" if self.show_api_key.get() else "*")
        
        tk.Checkbutton(api_row, text="Show", variable=self.show_api_key,
                      command=toggle_api_key, bg=self.colors["card_bg"]).pack(side='left', padx=2)
        
        # Secure storage option (if keyring available)
        if HAS_KEYRING:
            self.use_keyring = tk.BooleanVar(value=self.config.get("api_key_use_keyring", False))
            tk.Checkbutton(api_frame, text="Store securely in Windows Credential Manager", 
                          variable=self.use_keyring, bg=self.colors["card_bg"]).pack(anchor='w', pady=2)
            
            # Info label about Windows Credential Manager
            tk.Label(api_frame, 
                    text="(Keys will be stored in Windows Credential Manager, not in config file)",
                    bg=self.colors["card_bg"], fg=self.colors["fg"],
                    font=('Segoe UI', 8)).pack(anchor='w', padx=20)
        
        # Buttons
        btn_row = tk.Frame(api_frame, bg=self.colors["card_bg"])
        btn_row.pack(fill='x', pady=5)
        
        ModernButton(btn_row, text="💾 Save API Key", command=self.save_api_key,
                    variant="success").pack(side='left', padx=2)
        
        ModernButton(btn_row, text="🗑️ Delete API Key", command=self.delete_api_key,
                    variant="danger").pack(side='left', padx=2)
        
        ModernButton(btn_row, text="🔍 Test Keyring", command=self.test_keyring,
                    variant="info").pack(side='left', padx=2)
        
        # Separator
        ttk.Separator(card.inner, orient='horizontal').pack(fill='x', pady=10)
        
        # ===== INTERVAL SECTION =====
        interval_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        interval_frame.pack(fill='x', pady=5)
        
        tk.Label(interval_frame, text="Change Interval:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        row = tk.Frame(interval_frame, bg=self.colors["card_bg"])
        row.pack(fill='x', pady=2)
        
        self.interval_value_var = tk.IntVar(value=self.config.get("interval_value", 30))
        tk.Spinbox(row, from_=1, to=999, textvariable=self.interval_value_var, width=8).pack(side='left', padx=2)
        
        self.interval_unit_var = tk.StringVar(value=self.config.get("interval_unit", "minutes"))
        ttk.Combobox(row, textvariable=self.interval_unit_var, values=["minutes", "hours", "days"], width=10).pack(side='left', padx=2)
        
        # Separator
        ttk.Separator(card.inner, orient='horizontal').pack(fill='x', pady=10)
        
        # ===== DOWNLOAD FOLDER SECTION =====
        folder_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        folder_frame.pack(fill='x', pady=5)
        
        tk.Label(folder_frame, text="Download Folder:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        row = tk.Frame(folder_frame, bg=self.colors["card_bg"])
        row.pack(fill='x', pady=2)
        
        self.folder_var = tk.StringVar(value=self.config.get("download_folder", ""))
        tk.Entry(row, textvariable=self.folder_var, width=40).pack(side='left', fill='x', expand=True)
        ModernButton(row, text="Browse", command=self.browse_folder).pack(side='right')
        
        # Separator
        ttk.Separator(card.inner, orient='horizontal').pack(fill='x', pady=10)
        
        # ===== OPTIONS SECTION =====
        options_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        options_frame.pack(fill='x', pady=5)
        
        tk.Label(options_frame, text="Options:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        self.notifications_var = tk.BooleanVar(value=self.config.get("notifications", True))
        tk.Checkbutton(options_frame, text="Show notifications", variable=self.notifications_var,
                      bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=2)
        
        self.random_var = tk.BooleanVar(value=self.config.get("random_order", True))
        tk.Checkbutton(options_frame, text="Random order", variable=self.random_var,
                      bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=2)
        
        self.auto_start_var = tk.BooleanVar(value=self.config.get("auto_start_enabled", True))
        tk.Checkbutton(options_frame, text="Start auto-change on launch", variable=self.auto_start_var,
                      bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=2)
        
        # Separator
        ttk.Separator(card.inner, orient='horizontal').pack(fill='x', pady=10)
        
        # ===== SAVE ALL BUTTON =====
        ModernButton(self.parent, text="💾 Save All Settings", command=self.save_all, variant="success").pack(pady=10)
    
    def save_api_key(self):
        api_key = self.api_key_var.get().strip()
        use_keyring = HAS_KEYRING and hasattr(self, 'use_keyring') and self.use_keyring.get()
        
        if SecureConfig.set_api_key(self.config, api_key, use_keyring):
            self.app.changer.save_config()
            
            # Update API instance
            self.app.source_manager.api_key = SecureConfig.get_api_key(self.config)
            self.app.source_manager.source.api_key = self.app.source_manager.api_key
            
            if use_keyring:
                messagebox.showinfo("Success", 
                    "✅ API Key saved securely in Windows Credential Manager!\n\n"
                    "You can view it in:\n"
                    "Control Panel → User Accounts → Credential Manager → Windows Credentials")
            else:
                messagebox.showinfo("Success", "✅ API Key saved to config file!")
            
            # Clear the entry for security
            self.api_key_var.set("")
            self.check_keyring_status()  # Update status
        else:
            messagebox.showerror("Error", "❌ Failed to save API key!")
    
    def delete_api_key(self):
        if messagebox.askyesno("Confirm", "Delete API key from secure storage?"):
            SecureConfig.delete_api_key(self.config)
            self.app.changer.save_config()
            self.api_key_var.set("")
            self.check_keyring_status()  # Update status
            messagebox.showinfo("Success", "✅ API key deleted!")
    
    def test_keyring(self):
        """Test keyring functionality"""
        status, message = SecureConfig.verify_keyring()
        if status:
            messagebox.showinfo("Keyring Status", 
                f"✅ {message}\n\nYour API keys are stored securely in Windows Credential Manager.")
        else:
            messagebox.showwarning("Keyring Status", 
                f"⚠️ {message}\n\nAPI keys will be stored in config file instead.")
        self.check_keyring_status()
    
    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get())
        if folder:
            self.folder_var.set(folder)
    
    def save_all(self):
        self.config["download_folder"] = self.folder_var.get().strip()
        self.config["interval_value"] = self.interval_value_var.get()
        self.config["interval_unit"] = self.interval_unit_var.get()
        self.config["notifications"] = self.notifications_var.get()
        self.config["random_order"] = self.random_var.get()
        self.config["auto_start_enabled"] = self.auto_start_var.get()
        self.app.changer.save_config()
        messagebox.showinfo("Success", "✅ All settings saved!")

# ============================================================================
# FILTERS TAB
# ============================================================================

class FiltersTab:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.config = app.changer.config
        
        self.setup_ui()
    
    def setup_ui(self):
        card = ModernCard(self.parent, self.colors)
        card.pack(fill='x', pady=5)
        
        # Purity with NSFW warning
        purity_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        purity_frame.pack(fill='x', pady=5)
        
        tk.Label(purity_frame, text="Purity:", bg=self.colors["card_bg"], fg=self.colors["fg"], font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        self.pur_sfw = tk.BooleanVar(value=self.config["purity"].get("sfw", 1))
        self.pur_sketchy = tk.BooleanVar(value=self.config["purity"].get("sketchy", 0))
        self.pur_nsfw = tk.BooleanVar(value=self.config["purity"].get("nsfw", 0))
        
        tk.Checkbutton(purity_frame, text="SFW", variable=self.pur_sfw, 
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      command=self.check_nsfw).pack(anchor='w')
        tk.Checkbutton(purity_frame, text="Sketchy", variable=self.pur_sketchy, 
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      command=self.check_nsfw).pack(anchor='w')
        tk.Checkbutton(purity_frame, text="NSFW", variable=self.pur_nsfw, 
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      command=self.check_nsfw).pack(anchor='w')
        
        if self.pur_nsfw.get() and not self.config.get("nsfw_acknowledged", False):
            tk.Label(purity_frame, text="⚠️ NSFW requires acknowledgment", 
                    bg=self.colors["card_bg"], fg=self.colors["warning"]).pack(anchor='w', pady=2)
        
        # Categories
        cat_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        cat_frame.pack(fill='x', pady=5)
        
        tk.Label(cat_frame, text="Categories:", bg=self.colors["card_bg"], fg=self.colors["fg"], font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        self.cat_general = tk.BooleanVar(value=self.config["categories"].get("general", 1))
        self.cat_anime = tk.BooleanVar(value=self.config["categories"].get("anime", 1))
        self.cat_people = tk.BooleanVar(value=self.config["categories"].get("people", 1))
        
        tk.Checkbutton(cat_frame, text="General", variable=self.cat_general, bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w')
        tk.Checkbutton(cat_frame, text="Anime", variable=self.cat_anime, bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w')
        tk.Checkbutton(cat_frame, text="People", variable=self.cat_people, bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w')
        
        # Resolutions
        res_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        res_frame.pack(fill='x', pady=5)
        
        tk.Label(res_frame, text="Resolution:", bg=self.colors["card_bg"], fg=self.colors["fg"], font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        self.res_4k = tk.BooleanVar(value=self.config["resolution_presets"].get("4k", False))
        self.res_2k = tk.BooleanVar(value=self.config["resolution_presets"].get("2k", False))
        self.res_1080p = tk.BooleanVar(value=self.config["resolution_presets"].get("1080p", True))
        
        tk.Checkbutton(res_frame, text="4K (3840x2160)", variable=self.res_4k, bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w')
        tk.Checkbutton(res_frame, text="2K (2560x1440)", variable=self.res_2k, bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w')
        tk.Checkbutton(res_frame, text="1080p (1920x1080)", variable=self.res_1080p, bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w')
        
        ModernButton(self.parent, text="Apply Filters", command=self.apply_filters, variant="success").pack(pady=10)
    
    def check_nsfw(self):
        """Show warning when NSFW is enabled"""
        if self.pur_nsfw.get() and not self.config.get("nsfw_acknowledged", False):
            if messagebox.askyesno("NSFW Warning", NSFW_WARNING):
                self.config["nsfw_acknowledged"] = True
                self.app.changer.save_config()
            else:
                self.pur_nsfw.set(False)
    
    def apply_filters(self):
        self.config["purity"] = {
            "sfw": 1 if self.pur_sfw.get() else 0,
            "sketchy": 1 if self.pur_sketchy.get() else 0,
            "nsfw": 1 if self.pur_nsfw.get() else 0
        }
        
        self.config["categories"] = {
            "general": 1 if self.cat_general.get() else 0,
            "anime": 1 if self.cat_anime.get() else 0,
            "people": 1 if self.cat_people.get() else 0
        }
        
        self.config["resolution_presets"] = {
            "4k": self.res_4k.get(),
            "2k": self.res_2k.get(),
            "1080p": self.res_1080p.get()
        }
        
        if self.res_4k.get():
            self.config["min_resolution"] = "3840x2160"
        elif self.res_2k.get():
            self.config["min_resolution"] = "2560x1440"
        else:
            self.config["min_resolution"] = "1920x1080"
        
        self.app.changer.save_config()
        self.app.source_manager.update_filters(self.config)
        self.app.status_var.set("Filters applied")

# ============================================================================
# SHORTCUTS TAB
# ============================================================================

class ShortcutsTab:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.shortcut_manager = app.shortcut_manager
        
        self.setup_ui()
    
    @property
    def config(self):
        return self.app.changer.config
    
    def setup_ui(self):
        card = ModernCard(self.parent, self.colors)
        card.pack(fill='x', pady=5)
        
        shortcuts = [
            ("Next Wallpaper", "next", "ctrl+alt+right"),
            ("Previous Wallpaper", "previous", "ctrl+alt+left"),
            ("Delete Current", "delete", "ctrl+alt+del"),
            ("Pause/Resume", "pause", "alt+p")
        ]
        
        self.entries = {}
        
        for label, key, default in shortcuts:
            frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
            frame.pack(fill='x', pady=5)
            
            tk.Label(frame, text=f"{label}:", bg=self.colors["card_bg"], fg=self.colors["fg"], width=15, anchor='w').pack(side='left')
            
            var = tk.StringVar(value=self.config.get("shortcuts", {}).get(key, default))
            entry = tk.Entry(frame, textvariable=var, width=20)
            entry.pack(side='left', padx=5)
            self.entries[key] = var
            
            tk.Label(frame, text="e.g., ctrl+alt+right", bg=self.colors["card_bg"], fg=self.colors["fg"], font=('Segoe UI', 8)).pack(side='left')
        
        ModernButton(self.parent, text="Save Shortcuts", command=self.save_shortcuts, variant="success").pack(pady=10)
    
    def save_shortcuts(self):
        new_shortcuts = {key: var.get() for key, var in self.entries.items()}
        self.shortcut_manager.update_shortcuts(new_shortcuts)
        messagebox.showinfo("Success", "Shortcuts saved!")

# ============================================================================
# QUOTA TAB
# ============================================================================

class QuotaTab:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.config = app.changer.config
        self.quota = app.changer.quota
        
        self.setup_ui()
    
    def setup_ui(self):
        card = ModernCard(self.parent, self.colors)
        card.pack(fill='x', pady=5)
        
        # Enable toggle
        toggle_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        toggle_frame.pack(fill='x', pady=5)
        
        self.quota_enabled = tk.BooleanVar(value=self.config.get("quota_enabled", True))
        tk.Checkbutton(toggle_frame, text="Enable Disk Quota", variable=self.quota_enabled,
                      bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w')
        
        # Size
        size_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        size_frame.pack(fill='x', pady=5)
        
        tk.Label(size_frame, text="Max Size (MB):", bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(side='left')
        self.quota_size = tk.IntVar(value=self.config.get("quota_size", 1000))
        tk.Spinbox(size_frame, from_=50, to=100000, textvariable=self.quota_size, width=8).pack(side='left', padx=5)
        
        # Usage
        self.usage_label = tk.Label(card.inner, text="Calculating...", bg=self.colors["card_bg"], fg=self.colors["fg"])
        self.usage_label.pack(anchor='w', pady=5)
        
        self.progress = ttk.Progressbar(card.inner, length=300, mode='determinate')
        self.progress.pack(fill='x', pady=5)
        
        # Buttons
        btn_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        btn_frame.pack(fill='x', pady=5)
        
        ModernButton(btn_frame, text="Save", command=self.save_settings, variant="success").pack(side='left', padx=2)
        ModernButton(btn_frame, text="Refresh", command=self.update_display, variant="info").pack(side='left', padx=2)
        
        self.update_display()
    
    def update_display(self):
        used = self.quota.get_folder_size_mb()
        max_mb = self.quota.max_size_mb
        self.usage_label.config(text=f"Used: {used:.1f} MB / {max_mb} MB")
        
        if self.quota.enabled:
            percent = min(100, (used / max_mb) * 100)
            self.progress['value'] = percent
        
        self.parent.after(5000, self.update_display)
    
    def save_settings(self):
        self.config["quota_enabled"] = self.quota_enabled.get()
        self.config["quota_size"] = self.quota_size.get()
        
        self.quota.enabled = self.quota_enabled.get()
        self.quota.max_size_mb = self.quota_size.get()
        
        self.app.changer.save_config()

# ============================================================================
# MAIN APPLICATION
# ============================================================================

class ModernWallpaperChangerApp:
    def __init__(self):
        self.changer = WallpaperChanger(app=self)
        self.source_manager = SourceManager(
            SecureConfig.get_api_key(self.changer.config),
            self.changer.config
        )
        self.keyword_manager = KeywordManager()
        self.duplicate_detector = DuplicateDetector(
            DUPLICATE_DB_FILE,
            self.changer.config.get("duplicate_detection_enabled", True),
            self.changer.config.get("duplicate_hash_size", 8)
        )
        self.shortcut_manager = ShortcutManager(self)
        self.current_scheme = self.changer.config.get("theme", "light")
        
        # Link to changer
        self.changer.duplicate_detector = self.duplicate_detector
        
        self.colors = COLOR_SCHEMES[self.current_scheme]
        
        self.root = tk.Tk()
        self.root.title("Wallpaper Changer")
        self.root.geometry("900x800+100+100")
        self.root.configure(bg=self.colors["bg"])
        
        self.status_var = tk.StringVar(value="Ready")
        
        self.setup_ui()
        
        if self.changer.config.get("change_on_startup", True):
            self.root.after(100, self.change_on_startup)
        else:
            self.root.after(100, self.load_initial_preview)
        
        if self.changer.config.get("auto_start_enabled", True):
            self.root.after(500, self.start_auto_change)
        
        self.tray = SystemTray(self.changer, self)
        self.tray.run()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def start_auto_change(self):
        self.changer.start_auto_change()
        self.status_var.set(f"Auto-change started")
    
    def change_on_startup(self):
        self.status_var.set("Getting wallpaper...")
        
        def do_change():
            images = self.source_manager.get_images(1)
            if images:
                img = images[0]
                try:
                    response = requests.get(img['download_url'], timeout=30)
                    file_ext = os.path.splitext(img['download_url'])[1] or '.jpg'
                    filename = f"{img['source']}_{img['id']}{file_ext}"
                    save_path = os.path.join(self.changer.config["download_folder"], filename)
                    
                    with open(save_path, 'wb') as f:
                        f.write(response.content)
                    
                    self.changer.set_wallpaper(save_path, img['id'], "static")
                    
                    if self.duplicate_detector and self.duplicate_detector.enabled:
                        self.duplicate_detector.index_image(save_path)
                    
                    self.root.after(0, self.change_done)
                except Exception as e:
                    print(f"Startup error: {e}")
                    self.root.after(0, self.load_initial_preview)
            else:
                self.root.after(0, self.load_initial_preview)
        
        threading.Thread(target=do_change, daemon=True).start()
    
    def change_done(self):
        self.status_var.set("Wallpaper changed")
        self.changer.scan_downloaded_wallpapers()
        self.update_preview()
        self.update_navigation_display()
    
    def toggle_pause(self):
        result = self.changer.toggle_pause()
        self.status_var.set(f"Auto-change: {result}")
        # Tray menu will be updated by the changer's toggle_pause method
    
    def show_duplicate_tab(self):
        for i, tab in enumerate(self.notebook.tabs()):
            if self.notebook.tab(tab, "text") == "🔄 Duplicates":
                self.notebook.select(i)
                break
    
    def setup_ui(self):
        # Header
        header = tk.Frame(self.root, bg=self.colors["accent"], height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(header, text="🎨 Wallpaper Changer", bg=self.colors["accent"], fg="white",
                font=('Segoe UI', 18, 'bold')).pack(side='left', padx=20)
        
        theme_btn = ModernButton(header, text="🌓 Theme", command=self.toggle_theme, variant="secondary")
        theme_btn.pack(side='right', padx=20)
        
        # Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Dashboard
        dash_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(dash_frame, text="🏠 Dashboard")
        self.setup_dashboard(dash_frame)
        
        # Filters
        filters_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(filters_frame, text="🔞 Filters")
        self.filters_tab = FiltersTab(filters_frame, self)
        
        # Keywords
        keywords_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(keywords_frame, text="🔑 Keywords")
        self.keywords_tab = KeywordsTab(keywords_frame, self)
        
        # Duplicates
        duplicate_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(duplicate_frame, text="🔄 Duplicates")
        self.duplicate_tab = DuplicateDetectorTab(duplicate_frame, self)
        
        # Quota
        quota_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(quota_frame, text="💾 Quota")
        self.quota_tab = QuotaTab(quota_frame, self)
        
        # Shortcuts
        shortcuts_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(shortcuts_frame, text="⌨️ Shortcuts")
        self.shortcuts_tab = ShortcutsTab(shortcuts_frame, self)
        
        # Settings
        settings_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(settings_frame, text="⚙️ Settings")
        self.settings_tab = SettingsTab(settings_frame, self)
        
        # Status bar
        status_bar = tk.Frame(self.root, bg=self.colors["accent"], height=25)
        status_bar.pack(fill='x', side='bottom')
        status_bar.pack_propagate(False)
        
        tk.Label(status_bar, textvariable=self.status_var, bg=self.colors["accent"],
                fg="white", anchor='w', padx=10).pack(fill='both', expand=True)
    
    def setup_dashboard(self, parent):
        # Current wallpaper card
        card = ModernCard(parent, self.colors)
        card.pack(fill='x', pady=5)
        
        tk.Label(card.inner, text="Current Wallpaper", bg=self.colors["card_bg"],
                fg=self.colors["accent"], font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        
        self.preview_label = tk.Label(card.inner, text="No wallpaper", bg=self.colors["card_bg"], fg=self.colors["fg"])
        self.preview_label.pack(pady=10)
        
        # Navigation
        nav_frame = tk.Frame(card.inner, bg=self.colors["card_bg"])
        nav_frame.pack(fill='x', pady=5)
        
        self.prev_btn = ModernButton(nav_frame, text="◀ Previous", command=self.previous_wallpaper, variant="info")
        self.prev_btn.pack(side='left', padx=2)
        
        self.next_btn = ModernButton(nav_frame, text="Next ▶", command=self.next_wallpaper, variant="info")
        self.next_btn.pack(side='left', padx=2)
        
        self.nav_label = tk.Label(nav_frame, text="0/0", bg=self.colors["card_bg"], fg=self.colors["accent"])
        self.nav_label.pack(side='left', padx=10)
        
        ModernButton(nav_frame, text="🗑️ Delete", command=self.delete_current_wallpaper, variant="danger").pack(side='left', padx=2)
        ModernButton(nav_frame, text="❤️ Favorite", command=self.toggle_favorite, variant="warning").pack(side='left', padx=2)
        
        # Stats columns
        columns = tk.Frame(parent, bg=self.colors["bg"])
        columns.pack(fill='both', expand=True, pady=5)
        
        left = tk.Frame(columns, bg=self.colors["bg"], width=250)
        left.pack(side='left', fill='both', expand=True, padx=(0,5))
        left.pack_propagate(False)
        
        right = tk.Frame(columns, bg=self.colors["bg"])
        right.pack(side='right', fill='both', expand=True)
        
        # Quota card
        quota_card = ModernCard(left, self.colors)
        quota_card.pack(fill='x', pady=2)
        
        tk.Label(quota_card.inner, text="💾 Quota", bg=self.colors["card_bg"],
                fg=self.colors["accent"], font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        
        self.quota_usage = tk.Label(quota_card.inner, text="Loading...", bg=self.colors["card_bg"], fg=self.colors["fg"])
        self.quota_usage.pack(anchor='w', pady=2)
        
        self.quota_progress = ttk.Progressbar(quota_card.inner, length=200, mode='determinate')
        self.quota_progress.pack(fill='x', pady=2)
        
        # Duplicate card
        dup_card = ModernCard(left, self.colors)
        dup_card.pack(fill='x', pady=2)
        
        tk.Label(dup_card.inner, text="🔄 Duplicates", bg=self.colors["card_bg"],
                fg=self.colors["accent"], font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        
        self.dup_status = tk.Label(dup_card.inner, text="Checking...", bg=self.colors["card_bg"], fg=self.colors["fg"])
        self.dup_status.pack(anchor='w', pady=2)
        
        ModernButton(dup_card.inner, text="Manage", command=self.show_duplicate_tab, variant="info").pack(anchor='w', pady=2)
        
        # Right column placeholder
        placeholder = ModernCard(right, self.colors)
        placeholder.pack(fill='both', expand=True)
        
        self.update_quota_display()
        self.update_duplicate_status()
        self.update_navigation_display()
    
    def update_duplicate_status(self):
        stats = self.duplicate_detector.get_stats()
        self.dup_status.config(text=f"Duplicates: {stats['duplicate_count']}")
        self.root.after(10000, self.update_duplicate_status)
    
    def update_quota_display(self):
        used = self.changer.quota.get_folder_size_mb()
        max_mb = self.changer.quota.max_size_mb
        self.quota_usage.config(text=f"Used: {used:.1f}MB / {max_mb}MB")
        
        if self.changer.quota.enabled:
            percent = min(100, (used / max_mb) * 100)
            self.quota_progress['value'] = percent
        
        self.root.after(5000, self.update_quota_display)
    
    def update_navigation_display(self):
        current, total = self.changer.get_navigation_info()
        self.nav_label.config(text=f"{current}/{total}")
    
    def next_wallpaper(self):
        if self.changer.next_wallpaper():
            self.update_preview()
            self.update_navigation_display()
    
    def previous_wallpaper(self):
        if self.changer.previous_wallpaper():
            self.update_preview()
            self.update_navigation_display()
    
    def delete_current_wallpaper(self):
        success, msg = self.changer.delete_current_wallpaper()
        if success:
            self.update_preview()
            self.update_navigation_display()
        self.status_var.set(msg)
    
    def toggle_favorite(self):
        success, msg = self.changer.toggle_favorite_current()
        self.status_var.set(msg)
    
    def update_preview(self):
        if self.changer.current_wallpaper and os.path.exists(self.changer.current_wallpaper):
            try:
                # Temporarily increase limit for preview
                original_limit = Image.MAX_IMAGE_PIXELS
                Image.MAX_IMAGE_PIXELS = None
                
                img = Image.open(self.changer.current_wallpaper)
                img.thumbnail((300, 200))
                photo = ImageTk.PhotoImage(img)
                self.preview_label.config(image=photo, text="")
                self.preview_label.image = photo
                
                # Restore limit
                Image.MAX_IMAGE_PIXELS = original_limit
            except Exception as e:
                self.preview_label.config(image="", text="Preview unavailable")
                print(f"Preview error: {e}")
    
    def load_initial_preview(self):
        if self.changer.current_wallpaper:
            self.update_preview()
            self.update_navigation_display()
    
    def toggle_theme(self):
        new = "dark" if self.current_scheme == "light" else "light"
        self.change_color_scheme(new)
    
    def change_color_scheme(self, scheme):
        self.current_scheme = scheme
        self.colors = COLOR_SCHEMES[scheme]
        self.changer.config["theme"] = scheme
        self.changer.save_config()
        
        self.root.configure(bg=self.colors["bg"])
        
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.setup_ui()
        
        if self.changer.current_wallpaper:
            self.update_preview()
    
    def show_window(self):
        self.root.deiconify()
        self.root.lift()
    
    def on_closing(self):
        self.root.withdraw()
    
    def quit(self):
        self.changer.stop_auto_change()
        self.changer.db.close()
        self.duplicate_detector.close()
        self.root.quit()
    
    def run(self):
        self.root.mainloop()

# ============================================================================
# KEYBOARD SHORTCUT MANAGER
# ============================================================================

class ShortcutManager:
    def __init__(self, app):
        self.app = app
        self.register_shortcuts()
    
    def register_shortcuts(self):
        try:
            keyboard.unhook_all()
        except:
            pass
        
        config = self.app.changer.config.get("shortcuts", DEFAULT_CONFIG["shortcuts"])
        
        if config.get("next"):
            try:
                keyboard.add_hotkey(config["next"], lambda: self.app.root.after(0, self.app.next_wallpaper))
            except:
                pass
        
        if config.get("previous"):
            try:
                keyboard.add_hotkey(config["previous"], lambda: self.app.root.after(0, self.app.previous_wallpaper))
            except:
                pass
        
        if config.get("delete"):
            try:
                keyboard.add_hotkey(config["delete"], lambda: self.app.root.after(0, self.app.delete_current_wallpaper))
            except:
                pass
        
        if config.get("pause"):
            try:
                keyboard.add_hotkey(config["pause"], lambda: self.app.root.after(0, self.app.toggle_pause))
            except:
                pass
    
    def update_shortcuts(self, new_config):
        self.app.changer.config["shortcuts"] = new_config
        self.app.changer.save_config()
        self.register_shortcuts()

# ============================================================================
# MAIN
# ============================================================================

def main():
    app = ModernWallpaperChangerApp()
    app.run()

if __name__ == "__main__":
    main()
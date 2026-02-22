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
from tkinter import ttk, messagebox, filedialog, colorchooser
from datetime import datetime, timedelta
from PIL import Image, ImageTk, ImageDraw, ImageSequence, ImageFilter
import io
import pystray
from pathlib import Path
import subprocess
import tempfile
import shutil
import pickle
import hashlib
import math

# Try to import keyboard, install if not present
try:
    import keyboard
except ImportError:
    import subprocess
    import sys
    print("Installing keyboard module...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "keyboard"])
    import keyboard

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG_FILE = "wallpaper_changer_config.json"
DATABASE_FILE = "wallhaven_favorites.db"
THEME_FILE = "theme_settings.json"
LAST_WALLPAPER_FILE = "last_wallpaper.dat"
SAVED_FOLDERS_FILE = "saved_folders.json"
SCHEDULES_FILE = "schedules.json"
SOURCES_FILE = "sources.json"
KEYWORDS_FILE = "keywords.json"
FAVORITES_FOLDER_FILE = "favorites_folder.json"

# Get user's Pictures folder
PICTURES_FOLDER = os.path.join(os.path.expanduser("~"), "Pictures")
WALLHAVEN_FOLDER = os.path.join(PICTURES_FOLDER, "Wallhaven")
FAVORITES_FOLDER = os.path.join(WALLHAVEN_FOLDER, "Favorites")

# Ensure the base Pictures folder exists
os.makedirs(PICTURES_FOLDER, exist_ok=True)

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
    "resolutions": ["1920x1080"],
    "resolution_presets": {
        "4k": False,
        "2k": False,
        "1080p": True,
        "ultrawide": False
    },
    "min_resolution": "1920x1080",
    "aspect_ratios": ["landscape"],
    "color": "",
    "sorting": "date_added",
    "order": "desc",
    "wallpaper_style": "fill",
    "auto_start": False,
    "search_query": "",
    "pre_download_count": 3,
    "notifications": True,
    "theme": "light",
    "accent_color": "#3b82f6",
    "corner_radius": 0,
    "animation": True,
    "live_wallpaper_enabled": False,
    "live_wallpaper_path": "",
    "gif_speed": 1.0,
    "video_volume": 0.5,
    "wallpaper_type": "static",
    "remember_last_wallpaper": True,
    "saved_folders": [],
    "active_schedule": None,
    "pause_on_battery": False,
    "pause_on_fullscreen": False,
    "random_order": True,
    "blur_amount": 0,
    "darken_amount": 0,
    "keywords": [],
    "downloads_per_keyword": 10,
    "last_keyword_download": {},
    "quota_enabled": True,
    "quota_size": 1000,
    "shortcuts": {
        "next": "ctrl+alt+right",
        "previous": "ctrl+alt+left",
        "delete": "ctrl+alt+del"
    },
    "copy_to_favorites": True,
    "change_on_startup": True
}

# ============================================================================
# FAVORITES FOLDER MANAGER
# ============================================================================

class FavoritesFolderManager:
    """Manages the favorites folder - copies wallpapers to a dedicated folder when favorited"""
    
    def __init__(self, config):
        self.config = config
        self.favorites_folder = config.get("favorites_folder", FAVORITES_FOLDER)
        self.copy_enabled = config.get("copy_to_favorites", True)
        
        # Create favorites folder if it doesn't exist
        try:
            os.makedirs(self.favorites_folder, exist_ok=True)
        except Exception as e:
            print(f"Error creating favorites folder: {e}")
            # Fallback to a temp folder
            self.favorites_folder = os.path.join(tempfile.gettempdir(), "WallpaperFavorites")
            os.makedirs(self.favorites_folder, exist_ok=True)
    
    def get_favorites_folder(self):
        """Get the favorites folder path"""
        return self.favorites_folder
    
    def set_favorites_folder(self, path):
        """Set a new favorites folder"""
        self.favorites_folder = path
        try:
            os.makedirs(self.favorites_folder, exist_ok=True)
        except:
            pass
        self.config["favorites_folder"] = path
        return True
    
    def copy_to_favorites(self, source_path, wallpaper_id, file_type):
        """Copy a wallpaper to the favorites folder"""
        if not self.copy_enabled:
            return None, "Copy disabled"
        
        try:
            # Generate filename
            filename = os.path.basename(source_path)
            dest_path = os.path.join(self.favorites_folder, filename)
            
            # If file already exists, add a number
            if os.path.exists(dest_path):
                name, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(os.path.join(self.favorites_folder, f"{name}_{counter}{ext}")):
                    counter += 1
                dest_path = os.path.join(self.favorites_folder, f"{name}_{counter}{ext}")
            
            # Copy the file
            shutil.copy2(source_path, dest_path)
            return dest_path, f"Copied to favorites folder"
        except Exception as e:
            return None, f"Error copying: {e}"
    
    def remove_from_favorites(self, filename):
        """Remove a file from favorites folder"""
        try:
            file_path = os.path.join(self.favorites_folder, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                return True, "Removed from favorites folder"
        except Exception as e:
            return False, f"Error removing: {e}"
        return False, "File not found"
    
    def get_all_favorites(self):
        """Get all files in favorites folder"""
        files = []
        if os.path.exists(self.favorites_folder):
            for f in os.listdir(self.favorites_folder):
                if f.endswith(('.jpg', '.jpeg', '.png', '.gif', '.mp4', '.webm')):
                    file_path = os.path.join(self.favorites_folder, f)
                    files.append({
                        'path': file_path,
                        'name': f,
                        'size': os.path.getsize(file_path),
                        'modified': os.path.getmtime(file_path)
                    })
        return sorted(files, key=lambda x: x['modified'], reverse=True)
    
    def toggle_copy(self, enabled):
        """Toggle whether to copy files to favorites folder"""
        self.copy_enabled = enabled
        self.config["copy_to_favorites"] = enabled

# ============================================================================
# FAVORITES FOLDER BROWSER
# ============================================================================

class FavoritesFolderBrowser:
    """Browse and manage the favorites folder"""
    
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.manager = app.changer.favorites_folder_manager
        
        self.window = tk.Toplevel(parent.root)
        self.window.title("Favorites Folder")
        self.window.geometry("800x500")
        self.window.transient(parent.root)
        self.window.grab_set()
        self.window.configure(bg=self.colors["bg"])
        
        self.current_files = []
        self.current_index = -1
        
        self.setup_ui()
        self.load_favorites()
    
    def setup_ui(self):
        # Header
        header = tk.Frame(self.window, bg=self.colors["accent"], height=50)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        title = tk.Label(header, text="📁 Favorites Folder", 
                        bg=self.colors["accent"], fg="white",
                        font=('Segoe UI', 14, 'bold'))
        title.pack(side='left', padx=15, pady=10)
        
        # Folder path
        path_frame = tk.Frame(header, bg=self.colors["accent"])
        path_frame.pack(side='right', padx=15, pady=10)
        
        tk.Label(path_frame, text="Folder:", 
                bg=self.colors["accent"], fg="white").pack(side='left')
        
        self.path_label = tk.Label(path_frame, text=self.manager.favorites_folder,
                                   bg=self.colors["accent"], fg="white",
                                   font=('Segoe UI', 9))
        self.path_label.pack(side='left', padx=5)
        
        ModernButton(path_frame, text="📂 Open", 
                    command=self.open_folder,
                    variant="secondary").pack(side='left', padx=2)
        
        # Main content
        main_frame = tk.Frame(self.window, bg=self.colors["bg"])
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Left panel - Files list
        left_frame = tk.Frame(main_frame, bg=self.colors["bg"], width=300)
        left_frame.pack(side='left', fill='both', expand=True, padx=(0, 5))
        left_frame.pack_propagate(False)
        
        tk.Label(left_frame, text="Favorites:", 
                bg=self.colors["bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        list_frame = tk.Frame(left_frame, bg=self.colors["bg"])
        list_frame.pack(fill='both', expand=True, pady=5)
        
        self.files_listbox = tk.Listbox(list_frame, bg=self.colors["entry_bg"],
                                        fg=self.colors["fg"],
                                        selectbackground=self.colors["accent"],
                                        selectforeground="white",
                                        font=('Segoe UI', 9))
        self.files_listbox.pack(side='left', fill='both', expand=True)
        self.files_listbox.bind('<<ListboxSelect>>', self.on_file_select)
        self.files_listbox.bind('<Double-Button-1>', self.set_selected_wallpaper)
        
        scrollbar = tk.Scrollbar(self.files_listbox)
        scrollbar.pack(side='right', fill='y')
        self.files_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.files_listbox.yview)
        
        # Right panel - Preview
        right_frame = tk.Frame(main_frame, bg=self.colors["bg"])
        right_frame.pack(side='right', fill='both', expand=True, padx=(5, 0))
        
        tk.Label(right_frame, text="Preview:", 
                bg=self.colors["bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        preview_frame = tk.Frame(right_frame, bg=self.colors["card_bg"],
                                 relief='flat', bd=0)
        preview_frame.pack(fill='both', expand=True, pady=5)
        
        self.preview_label = tk.Label(preview_frame, text="Select a wallpaper to preview",
                                      bg=self.colors["card_bg"],
                                      fg=self.colors["fg"])
        self.preview_label.pack(expand=True)
        
        # Navigation buttons
        nav_frame = tk.Frame(right_frame, bg=self.colors["bg"])
        nav_frame.pack(fill='x', pady=5)
        
        self.prev_btn = ModernButton(nav_frame, text="◀ Previous", 
                                     command=self.previous_wallpaper,
                                     variant="info")
        self.prev_btn.pack(side='left', padx=2)
        
        self.next_btn = ModernButton(nav_frame, text="Next ▶", 
                                     command=self.next_wallpaper,
                                     variant="info")
        self.next_btn.pack(side='left', padx=2)
        
        self.counter_label = tk.Label(nav_frame, text="0/0",
                                      bg=self.colors["bg"],
                                      fg=self.colors["fg"])
        self.counter_label.pack(side='left', padx=10)
        
        # Action buttons
        action_frame = tk.Frame(right_frame, bg=self.colors["bg"])
        action_frame.pack(fill='x', pady=5)
        
        ModernButton(action_frame, text="Set as Wallpaper", 
                    command=self.set_selected_wallpaper,
                    variant="primary",
                    icon="🖼️").pack(side='left', padx=2)
        
        ModernButton(action_frame, text="Remove from Favorites", 
                    command=self.remove_selected,
                    variant="danger",
                    icon="🗑️").pack(side='left', padx=2)
        
        ModernButton(action_frame, text="Open File Location", 
                    command=self.open_selected_location,
                    variant="info",
                    icon="📂").pack(side='left', padx=2)
        
        # Bottom frame for settings
        bottom_frame = tk.Frame(self.window, bg=self.colors["bg"])
        bottom_frame.pack(fill='x', padx=10, pady=5)
        
        # Copy toggle
        toggle_frame = tk.Frame(bottom_frame, bg=self.colors["bg"])
        toggle_frame.pack(side='left')
        
        self.copy_var = tk.BooleanVar(value=self.manager.copy_enabled)
        toggle = ModernToggle(toggle_frame, text="Copy to favorites folder when favoriting", 
                             variable=self.copy_var)
        toggle.pack(side='left')
        
        self.copy_var.trace('w', lambda *args: self.toggle_copy())
        
        # Change folder button
        ModernButton(bottom_frame, text="Change Favorites Folder", 
                    command=self.change_folder,
                    variant="secondary").pack(side='right', padx=2)
        
        ModernButton(bottom_frame, text="Open in Explorer", 
                    command=self.open_folder,
                    variant="info").pack(side='right', padx=2)
        
        # Status bar
        self.status_var = tk.StringVar()
        status_bar = tk.Label(self.window, textvariable=self.status_var,
                             bg=self.colors["accent"], fg="white",
                             anchor='w', padx=10)
        status_bar.pack(side='bottom', fill='x')
    
    def load_favorites(self):
        """Load all files from favorites folder"""
        self.files_listbox.delete(0, tk.END)
        self.current_files = self.manager.get_all_favorites()
        
        for file_info in self.current_files:
            # Add icon based on file type
            if file_info['name'].lower().endswith(('.gif')):
                icon = "🎬 "
            elif file_info['name'].lower().endswith(('.mp4', '.webm')):
                icon = "🎥 "
            else:
                icon = "🖼️ "
            
            # Format file size
            size = file_info['size'] / 1024  # KB
            if size > 1024:
                size_str = f"{size/1024:.1f}MB"
            else:
                size_str = f"{size:.0f}KB"
            
            # Format date
            date = datetime.fromtimestamp(file_info['modified']).strftime("%Y-%m-%d")
            
            display = f"{icon}{file_info['name']} ({size_str}, {date})"
            self.files_listbox.insert(tk.END, display)
        
        self.status_var.set(f"Total: {len(self.current_files)} favorites")
        self.current_index = -1
        self.update_navigation()
    
    def on_file_select(self, event):
        """Handle file selection"""
        selection = self.files_listbox.curselection()
        if selection:
            self.current_index = selection[0]
            self.update_navigation()
            self.show_preview()
    
    def show_preview(self):
        """Show preview of selected file"""
        if 0 <= self.current_index < len(self.current_files):
            file_info = self.current_files[self.current_index]
            try:
                if file_info['name'].lower().endswith('.gif'):
                    img = Image.open(file_info['path'])
                    img.seek(0)
                    img.thumbnail((350, 250))
                else:
                    img = Image.open(file_info['path'])
                    img.thumbnail((350, 250))
                
                photo = ImageTk.PhotoImage(img)
                self.preview_label.config(image=photo, text="")
                self.preview_label.image = photo
            except:
                self.preview_label.config(image="", text="Preview not available")
    
    def update_navigation(self):
        """Update navigation display"""
        total = len(self.current_files)
        if total > 0 and self.current_index >= 0:
            self.counter_label.config(text=f"{self.current_index + 1}/{total}")
            self.prev_btn.config(state='normal' if self.current_index > 0 else 'disabled')
            self.next_btn.config(state='normal' if self.current_index < total - 1 else 'disabled')
        else:
            self.counter_label.config(text=f"0/{total}")
            self.prev_btn.config(state='disabled')
            self.next_btn.config(state='disabled')
    
    def next_wallpaper(self):
        """Go to next wallpaper"""
        if self.current_index < len(self.current_files) - 1:
            self.current_index += 1
            self.files_listbox.selection_clear(0, tk.END)
            self.files_listbox.selection_set(self.current_index)
            self.files_listbox.see(self.current_index)
            self.show_preview()
            self.update_navigation()
    
    def previous_wallpaper(self):
        """Go to previous wallpaper"""
        if self.current_index > 0:
            self.current_index -= 1
            self.files_listbox.selection_clear(0, tk.END)
            self.files_listbox.selection_set(self.current_index)
            self.files_listbox.see(self.current_index)
            self.show_preview()
            self.update_navigation()
    
    def set_selected_wallpaper(self, event=None):
        """Set selected wallpaper as current wallpaper"""
        if 0 <= self.current_index < len(self.current_files):
            file_info = self.current_files[self.current_index]
            filename = file_info['name']
            file_ext = os.path.splitext(filename)[1].lower()
            
            file_type = "static"
            if file_ext == '.gif':
                file_type = "gif"
            elif file_ext in ['.mp4', '.webm']:
                file_type = "video"
            
            wallpaper_id = f"favorites_{int(time.time())}"
            self.app.changer.set_wallpaper(file_info['path'], wallpaper_id, file_type)
            self.app.update_preview()
            self.app.update_favorite_status()
            self.app.update_navigation_display()
            self.app.status_var.set(f"Set favorite: {filename}")
    
    def remove_selected(self):
        """Remove selected file from favorites folder"""
        if 0 <= self.current_index < len(self.current_files):
            file_info = self.current_files[self.current_index]
            if messagebox.askyesno("Confirm", f"Remove '{file_info['name']}' from favorites?"):
                success, message = self.manager.remove_from_favorites(file_info['name'])
                if success:
                    self.load_favorites()
                    self.app.status_var.set(message)
                else:
                    messagebox.showerror("Error", message)
    
    def open_selected_location(self):
        """Open the folder containing the selected file"""
        if 0 <= self.current_index < len(self.current_files):
            file_info = self.current_files[self.current_index]
            folder = os.path.dirname(file_info['path'])
            os.startfile(folder)
    
    def open_folder(self):
        """Open the favorites folder in explorer"""
        if os.path.exists(self.manager.favorites_folder):
            os.startfile(self.manager.favorites_folder)
    
    def change_folder(self):
        """Change the favorites folder location"""
        folder = filedialog.askdirectory(
            title="Select Favorites Folder",
            initialdir=self.manager.favorites_folder
        )
        if folder:
            self.manager.set_favorites_folder(folder)
            self.path_label.config(text=folder)
            self.load_favorites()
            self.app.status_var.set(f"Favorites folder changed to: {folder}")
    
    def toggle_copy(self):
        """Toggle copy to favorites folder setting"""
        self.manager.toggle_copy(self.copy_var.get())
        self.app.changer.save_config()
        self.app.status_var.set(f"Copy to favorites: {'ON' if self.copy_var.get() else 'OFF'}")

# ============================================================================
# KEYBOARD SHORTCUT MANAGER
# ============================================================================

class ShortcutManager:
    """Manage keyboard shortcuts"""
    
    def __init__(self, app):
        self.app = app
        self.shortcuts = {}
        self.register_shortcuts()
    
    def register_shortcuts(self):
        """Register all keyboard shortcuts"""
        config = self.app.changer.config.get("shortcuts", DEFAULT_CONFIG["shortcuts"])
        
        # Clear any existing shortcuts
        try:
            keyboard.unhook_all()
        except:
            pass
        
        # Register next wallpaper shortcut
        if config.get("next"):
            try:
                keyboard.add_hotkey(config["next"], self.next_wallpaper, suppress=True)
                self.shortcuts["next"] = config["next"]
                print(f"Registered next shortcut: {config['next']}")
            except Exception as e:
                print(f"Failed to register next shortcut {config['next']}: {e}")
        
        # Register previous wallpaper shortcut
        if config.get("previous"):
            try:
                keyboard.add_hotkey(config["previous"], self.previous_wallpaper, suppress=True)
                self.shortcuts["previous"] = config["previous"]
                print(f"Registered previous shortcut: {config['previous']}")
            except Exception as e:
                print(f"Failed to register previous shortcut {config['previous']}: {e}")
        
        # Register delete wallpaper shortcut
        if config.get("delete"):
            try:
                keyboard.add_hotkey(config["delete"], self.delete_wallpaper, suppress=True)
                self.shortcuts["delete"] = config["delete"]
                print(f"Registered delete shortcut: {config['delete']}")
            except Exception as e:
                print(f"Failed to register delete shortcut {config['delete']}: {e}")
    
    def next_wallpaper(self):
        """Next wallpaper shortcut handler"""
        print("Next wallpaper shortcut triggered")
        self.app.root.after(0, self.app.next_wallpaper)
    
    def previous_wallpaper(self):
        """Previous wallpaper shortcut handler"""
        print("Previous wallpaper shortcut triggered")
        self.app.root.after(0, self.app.previous_wallpaper)
    
    def delete_wallpaper(self):
        """Delete current wallpaper shortcut handler"""
        print("Delete wallpaper shortcut triggered")
        self.app.root.after(0, self.app.delete_current_wallpaper)
    
    def update_shortcuts(self, new_config):
        """Update shortcuts with new configuration"""
        # Update config
        self.app.changer.config["shortcuts"] = new_config
        self.app.changer.save_config()
        
        # Re-register shortcuts
        self.register_shortcuts()
    
    def get_shortcut_display(self, name):
        """Get display text for a shortcut"""
        return self.shortcuts.get(name, "Not set")

# ============================================================================
# COLOR SCHEMES (Light and Dark)
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
        "frame_bg": "#f8fafd",
        "trough_color": "#e2e8f0",
        "scrollbar_bg": "#94a3b8",
        "scrollbar_active": "#3b82f6",
        "highlight": "#3b82f6",
        "gradient_start": "#3b82f6",
        "gradient_end": "#10b981"
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
        "frame_bg": "#0f172a",
        "trough_color": "#1e293b",
        "scrollbar_bg": "#475569",
        "scrollbar_active": "#3b82f6",
        "highlight": "#3b82f6",
        "gradient_start": "#3b82f6",
        "gradient_end": "#10b981"
    }
}

# ============================================================================
# QUOTA MANAGER
# ============================================================================

class QuotaManager:
    """Manage disk quota for download folder"""
    
    def __init__(self, download_folder, enabled=True, max_size_mb=1000):
        self.download_folder = download_folder
        self.enabled = enabled
        self.max_size_mb = max_size_mb
        self.max_size_bytes = max_size_mb * 1024 * 1024
    
    def get_folder_size(self):
        """Get current folder size in bytes"""
        total_size = 0
        if os.path.exists(self.download_folder):
            for dirpath, dirnames, filenames in os.walk(self.download_folder):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.exists(fp):
                        total_size += os.path.getsize(fp)
        return total_size
    
    def get_folder_size_mb(self):
        """Get current folder size in MB"""
        return self.get_folder_size() / (1024 * 1024)
    
    def get_folder_size_gb(self):
        """Get current folder size in GB"""
        return self.get_folder_size() / (1024 * 1024 * 1024)
    
    def is_quota_exceeded(self):
        """Check if quota is exceeded"""
        if not self.enabled:
            return False
        return self.get_folder_size() >= self.max_size_bytes
    
    def get_free_space_mb(self):
        """Get free space in MB before quota"""
        if not self.enabled:
            return float('inf')
        used = self.get_folder_size()
        free = self.max_size_bytes - used
        return max(0, free) / (1024 * 1024)
    
    def can_download(self, file_size_mb):
        """Check if we can download a file of given size"""
        if not self.enabled:
            return True
        return (self.get_folder_size() + (file_size_mb * 1024 * 1024)) <= self.max_size_bytes
    
    def cleanup_oldest(self, target_mb=None):
        """Delete oldest files to free up space"""
        if target_mb is None:
            target_mb = self.max_size_mb * 0.8  # Target 80% of quota
        
        target_bytes = target_mb * 1024 * 1024
        current_size = self.get_folder_size()
        
        if current_size <= target_bytes:
            return 0
        
        # Get all files with their modification times
        files = []
        if os.path.exists(self.download_folder):
            for f in os.listdir(self.download_folder):
                fp = os.path.join(self.download_folder, f)
                if os.path.isfile(fp):
                    files.append((fp, os.path.getmtime(fp), os.path.getsize(fp)))
        
        # Sort by oldest first
        files.sort(key=lambda x: x[1])
        
        deleted = 0
        deleted_size = 0
        target_delete = current_size - target_bytes
        
        for fp, mtime, size in files:
            if deleted_size >= target_delete:
                break
            try:
                os.remove(fp)
                deleted += 1
                deleted_size += size
            except:
                pass
        
        return deleted

# ============================================================================
# API STATUS CHECKER
# ============================================================================

class APIStatusChecker:
    """Check if Wallhaven API is working"""
    
    @staticmethod
    def check_wallhaven(api_key=None):
        """Check Wallhaven API status"""
        try:
            url = "https://wallhaven.cc/api/v1/search"
            params = {"page": 1, "q": "nature"}
            headers = {}
            if api_key and api_key != "YOUR_WALLHAVEN_API_KEY":
                headers["X-API-Key"] = api_key
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('data') is not None:
                    return True, "API is working"
                else:
                    return False, "Invalid response format"
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                return False, f"Error {response.status_code}"
        except requests.exceptions.Timeout:
            return False, "Connection timeout"
        except requests.exceptions.ConnectionError:
            return False, "Connection error"
        except Exception as e:
            return False, str(e)

# ============================================================================
# FILTERS MANAGER
# ============================================================================

class FiltersManager:
    """Manage NSFW/SFW filters and resolution settings"""
    
    RESOLUTION_PRESETS = {
        "4k": "3840x2160",
        "2k": "2560x1440",
        "1080p": "1920x1080",
        "ultrawide": "3440x1440"
    }
    
    def __init__(self, config):
        self.config = config
    
    def get_purity_options(self):
        """Get purity options as list"""
        purity = self.config.get("purity", {"sfw": 1, "sketchy": 0, "nsfw": 0})
        options = []
        if purity.get("sfw", 0):
            options.append("SFW")
        if purity.get("sketchy", 0):
            options.append("Sketchy")
        if purity.get("nsfw", 0):
            options.append("NSFW")
        return options
    
    def get_purity_string(self):
        """Get purity as string for API"""
        purity = self.config.get("purity", {"sfw": 1, "sketchy": 0, "nsfw": 0})
        return f"{purity.get('sfw', 1)}{purity.get('sketchy', 0)}{purity.get('nsfw', 0)}"
    
    def get_categories_string(self):
        """Get categories as string for API"""
        cats = self.config.get("categories", {"general": 1, "anime": 1, "people": 1})
        return f"{cats.get('general', 1)}{cats.get('anime', 1)}{cats.get('people', 1)}"
    
    def get_resolution_filter(self):
        """Get resolution filter based on presets and manual entry"""
        presets = self.config.get("resolution_presets", {})
        resolutions = []
        
        # Add preset resolutions
        for preset, enabled in presets.items():
            if enabled and preset in self.RESOLUTION_PRESETS:
                resolutions.append(self.RESOLUTION_PRESETS[preset])
        
        # Add manual resolutions
        manual = self.config.get("resolutions", [])
        resolutions.extend(manual)
        
        # Use the highest resolution as minimum
        if resolutions:
            # Sort by total pixels (rough estimate)
            def get_pixels(res):
                try:
                    w, h = res.split('x')
                    return int(w) * int(h)
                except:
                    return 0
            
            resolutions.sort(key=get_pixels, reverse=True)
            return resolutions[0]
        
        return self.config.get("min_resolution", "1920x1080")
    
    def get_exact_resolutions(self):
        """Get exact resolutions"""
        return self.config.get("resolutions", [])
    
    def get_aspect_ratios(self):
        """Get aspect ratios"""
        return self.config.get("aspect_ratios", [])

# ============================================================================
# KEYWORD MANAGER
# ============================================================================

class KeywordManager:
    """Manages keywords for downloading wallpapers"""
    
    def __init__(self):
        self.keywords = []
        self.downloads_per_keyword = 10
        self.last_download = {}
        self.load_keywords()
    
    def load_keywords(self):
        """Load keywords from file"""
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
        """Save keywords to file"""
        data = {
            'keywords': self.keywords,
            'downloads_per_keyword': self.downloads_per_keyword,
            'last_download': self.last_download
        }
        with open(KEYWORDS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_keyword(self, keyword):
        """Add a new keyword"""
        if keyword and keyword not in self.keywords:
            self.keywords.append(keyword)
            self.save_keywords()
            return True
        return False
    
    def remove_keyword(self, keyword):
        """Remove a keyword"""
        if keyword in self.keywords:
            self.keywords.remove(keyword)
            self.save_keywords()
            return True
        return False
    
    def can_download_today(self, keyword):
        """Check if we can download for this keyword today"""
        if keyword not in self.last_download:
            return True
        
        last = datetime.fromisoformat(self.last_download[keyword])
        now = datetime.now()
        
        return last.date() < now.date()
    
    def record_download(self, keyword):
        """Record that we downloaded for this keyword"""
        self.last_download[keyword] = datetime.now().isoformat()
        self.save_keywords()
    
    def get_keywords_for_download(self):
        """Get keywords that need downloading today"""
        return [k for k in self.keywords if self.can_download_today(k)]

# ============================================================================
# BATCH DOWNLOADER
# ============================================================================

class BatchDownloader:
    """Downloads multiple wallpapers based on keywords"""
    
    def __init__(self, source_manager, download_folder, quota_manager=None):
        self.source_manager = source_manager
        self.download_folder = download_folder
        self.quota_manager = quota_manager
        self.is_downloading = False
        self.progress_callback = None
        self.complete_callback = None
    
    def download_keyword(self, keyword, count=10):
        """Download wallpapers for a single keyword"""
        results = []
        try:
            images = self.source_manager.search(keyword, count * 2)
            
            seen = set()
            unique_images = []
            for img in images:
                if img['id'] not in seen:
                    seen.add(img['id'])
                    unique_images.append(img)
            
            unique_images = unique_images[:count]
            
            for i, img in enumerate(unique_images):
                if not self.is_downloading:
                    break
                
                if self.progress_callback:
                    self.progress_callback(f"Downloading {keyword}: {i+1}/{count}")
                
                try:
                    # Check quota before downloading
                    if self.quota_manager and not self.quota_manager.can_download(5):  # Assume 5MB per image
                        if self.progress_callback:
                            self.progress_callback(f"Quota exceeded, stopping download")
                        break
                    
                    response = requests.get(img['download_url'], timeout=30)
                    file_ext = os.path.splitext(img['download_url'])[1] or '.jpg'
                    if '?' in file_ext:
                        file_ext = '.jpg'
                    filename = f"{keyword}_{img['source']}_{img['id']}{file_ext}"
                    save_path = os.path.join(self.download_folder, filename)
                    
                    with open(save_path, 'wb') as f:
                        f.write(response.content)
                    
                    results.append(save_path)
                    time.sleep(0.5)
                except Exception as e:
                    print(f"Error downloading {img['id']}: {e}")
            
        except Exception as e:
            print(f"Error downloading keyword {keyword}: {e}")
        
        return results
    
    def download_all(self, keywords, per_keyword=10):
        """Download wallpapers for all keywords"""
        self.is_downloading = True
        all_results = {}
        
        for keyword in keywords:
            if not self.is_downloading:
                break
            
            if self.progress_callback:
                self.progress_callback(f"Starting download for: {keyword}")
            
            results = self.download_keyword(keyword, per_keyword)
            all_results[keyword] = results
            
            if self.progress_callback:
                self.progress_callback(f"Downloaded {len(results)} for '{keyword}'")
        
        self.is_downloading = False
        
        if self.complete_callback:
            self.complete_callback(all_results)
        
        return all_results
    
    def stop_download(self):
        """Stop ongoing download"""
        self.is_downloading = False

# ============================================================================
# FAVORITES DATABASE
# ============================================================================

class FavoritesDatabase:
    def __init__(self):
        self.conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
        self.lock = threading.Lock()
        self.create_tables()
        self.migrate_database()
    
    def create_tables(self):
        with self.lock:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS favorites (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    url TEXT,
                    thumbnail_url TEXT,
                    resolution TEXT,
                    category TEXT,
                    purity TEXT,
                    tags TEXT,
                    file_type TEXT DEFAULT 'static',
                    rating INTEGER DEFAULT 0,
                    download_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_used DATETIME,
                    use_count INTEGER DEFAULT 0,
                    notes TEXT,
                    source TEXT DEFAULT 'wallhaven',
                    folder_name TEXT DEFAULT '',
                    keyword TEXT DEFAULT '',
                    in_favorites_folder BOOLEAN DEFAULT 0
                )
            ''')
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wallpaper_id TEXT,
                    wallpaper_type TEXT DEFAULT 'static',
                    set_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (wallpaper_id) REFERENCES favorites(id)
                )
            ''')
            self.conn.commit()
    
    def migrate_database(self):
        """Migrate database to newer versions"""
        with self.lock:
            try:
                cursor = self.conn.execute("PRAGMA table_info(favorites)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'file_type' not in columns:
                    print("Migrating database: adding file_type column")
                    self.conn.execute('ALTER TABLE favorites ADD COLUMN file_type TEXT DEFAULT "static"')
                    self.conn.commit()
                
                if 'source' not in columns:
                    print("Migrating database: adding source column")
                    self.conn.execute('ALTER TABLE favorites ADD COLUMN source TEXT DEFAULT "wallhaven"')
                    self.conn.commit()
                
                if 'folder_name' not in columns:
                    print("Migrating database: adding folder_name column")
                    self.conn.execute('ALTER TABLE favorites ADD COLUMN folder_name TEXT DEFAULT ""')
                    self.conn.commit()
                
                if 'keyword' not in columns:
                    print("Migrating database: adding keyword column")
                    self.conn.execute('ALTER TABLE favorites ADD COLUMN keyword TEXT DEFAULT ""')
                    self.conn.commit()
                
                if 'in_favorites_folder' not in columns:
                    print("Migrating database: adding in_favorites_folder column")
                    self.conn.execute('ALTER TABLE favorites ADD COLUMN in_favorites_folder BOOLEAN DEFAULT 0')
                    self.conn.commit()
                
                cursor = self.conn.execute("PRAGMA table_info(history)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'wallpaper_type' not in columns:
                    print("Migrating database: adding wallpaper_type column to history")
                    self.conn.execute('ALTER TABLE history ADD COLUMN wallpaper_type TEXT DEFAULT "static"')
                    self.conn.commit()
            except Exception as e:
                print(f"Migration error: {e}")
    
    def add_favorite(self, wallpaper_data):
        with self.lock:
            try:
                self.conn.execute('''
                    INSERT OR REPLACE INTO favorites 
                    (id, path, url, thumbnail_url, resolution, category, purity, tags, file_type, source, folder_name, keyword, in_favorites_folder, download_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    wallpaper_data['id'],
                    wallpaper_data['path'],
                    wallpaper_data.get('url', ''),
                    wallpaper_data.get('thumbnail', ''),
                    wallpaper_data.get('resolution', ''),
                    wallpaper_data.get('category', ''),
                    wallpaper_data.get('purity', ''),
                    wallpaper_data.get('tags', ''),
                    wallpaper_data.get('file_type', 'static'),
                    wallpaper_data.get('source', 'wallhaven'),
                    wallpaper_data.get('folder_name', ''),
                    wallpaper_data.get('keyword', ''),
                    wallpaper_data.get('in_favorites_folder', 0)
                ))
                self.conn.commit()
                return True
            except Exception as e:
                print(f"Error adding favorite: {e}")
                return False
    
    def add_local_favorite(self, file_path, folder_name="", keyword="", in_favorites_folder=False):
        """Add a local file to favorites"""
        try:
            file_name = os.path.basename(file_path)
            file_ext = os.path.splitext(file_path)[1].lower()
            wallpaper_id = "local_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(random.randint(1000, 9999))
            
            file_type = "static"
            if file_ext == '.gif':
                file_type = "gif"
            elif file_ext in ['.mp4', '.webm', '.avi', '.mov']:
                file_type = "video"
            
            resolution = ""
            try:
                if file_type == "static" or file_type == "gif":
                    with Image.open(file_path) as img:
                        resolution = f"{img.width}x{img.height}"
            except:
                pass
            
            wallpaper_data = {
                'id': wallpaper_id,
                'path': file_path,
                'url': '',
                'thumbnail': '',
                'resolution': resolution,
                'category': 'local',
                'purity': 'sfw',
                'tags': 'local',
                'file_type': file_type,
                'source': 'local',
                'folder_name': folder_name,
                'keyword': keyword,
                'in_favorites_folder': 1 if in_favorites_folder else 0
            }
            
            return self.add_favorite(wallpaper_data)
        except Exception as e:
            print(f"Error adding local favorite: {e}")
            return False
    
    def remove_favorite(self, wallpaper_id):
        with self.lock:
            self.conn.execute('DELETE FROM favorites WHERE id = ?', (wallpaper_id,))
            self.conn.commit()
    
    def get_favorites(self, limit=50, offset=0, tag=None, file_type=None, source=None, folder_name=None, keyword=None, in_favorites_folder=None):
        with self.lock:
            try:
                query = "SELECT * FROM favorites"
                params = []
                
                conditions = []
                if tag:
                    conditions.append("tags LIKE ?")
                    params.append(f"%{tag}%")
                if file_type:
                    conditions.append("file_type = ?")
                    params.append(file_type)
                if source:
                    conditions.append("source = ?")
                    params.append(source)
                if folder_name:
                    conditions.append("folder_name = ?")
                    params.append(folder_name)
                if keyword:
                    conditions.append("keyword = ?")
                    params.append(keyword)
                if in_favorites_folder is not None:
                    conditions.append("in_favorites_folder = ?")
                    params.append(1 if in_favorites_folder else 0)
                
                if conditions:
                    query += " WHERE " + " AND ".join(conditions)
                
                query += " ORDER BY download_date DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])
                
                cursor = self.conn.execute(query, params)
                return cursor.fetchall()
            except:
                cursor = self.conn.execute('''
                    SELECT * FROM favorites 
                    ORDER BY download_date DESC
                    LIMIT ? OFFSET ?
                ''', (limit, offset))
                return cursor.fetchall()
    
    def get_favorites_by_keyword(self, keyword):
        """Get all favorites for a specific keyword"""
        with self.lock:
            cursor = self.conn.execute('''
                SELECT * FROM favorites 
                WHERE keyword = ?
                ORDER BY download_date DESC
            ''', (keyword,))
            return cursor.fetchall()
    
    def get_all_keywords(self):
        """Get all unique keywords"""
        with self.lock:
            cursor = self.conn.execute('''
                SELECT DISTINCT keyword FROM favorites 
                WHERE keyword != ''
                ORDER BY keyword
            ''')
            return [row[0] for row in cursor.fetchall()]
    
    def is_favorite(self, wallpaper_id):
        with self.lock:
            cursor = self.conn.execute(
                'SELECT 1 FROM favorites WHERE id = ?', 
                (wallpaper_id,)
            )
            return cursor.fetchone() is not None
    
    def record_use(self, wallpaper_id, wallpaper_type="static"):
        with self.lock:
            self.conn.execute('''
                UPDATE favorites 
                SET last_used = CURRENT_TIMESTAMP, 
                    use_count = use_count + 1 
                WHERE id = ?
            ''', (wallpaper_id,))
            self.conn.execute('''
                INSERT INTO history (wallpaper_id, wallpaper_type) VALUES (?, ?)
            ''', (wallpaper_id, wallpaper_type))
            self.conn.commit()
    
    def get_stats(self):
        with self.lock:
            try:
                cursor = self.conn.execute('''
                    SELECT 
                        COUNT(*) as total_favorites,
                        COALESCE(SUM(use_count), 0) as total_uses,
                        COUNT(DISTINCT date(download_date)) as days_active,
                        (SELECT COUNT(*) FROM history WHERE date(set_time) = date('now')) as today_uses,
                        COALESCE(SUM(CASE WHEN file_type = 'gif' THEN 1 ELSE 0 END), 0) as gif_count,
                        COALESCE(SUM(CASE WHEN file_type = 'video' THEN 1 ELSE 0 END), 0) as video_count,
                        COALESCE(SUM(CASE WHEN source = 'local' THEN 1 ELSE 0 END), 0) as local_count,
                        COALESCE(SUM(in_favorites_folder), 0) as in_folder_count
                    FROM favorites
                ''')
                result = cursor.fetchone()
                return tuple(0 if x is None else x for x in result)
            except:
                cursor = self.conn.execute('''
                    SELECT 
                        COUNT(*) as total_favorites,
                        COALESCE(SUM(use_count), 0) as total_uses,
                        COUNT(DISTINCT date(download_date)) as days_active,
                        (SELECT COUNT(*) FROM history WHERE date(set_time) = date('now')) as today_uses
                    FROM favorites
                ''')
                result = cursor.fetchone()
                return (result[0], result[1], result[2], result[3], 0, 0, 0, 0)
    
    def get_most_used(self, limit=10):
        with self.lock:
            cursor = self.conn.execute('''
                SELECT * FROM favorites 
                WHERE use_count > 0
                ORDER BY use_count DESC, last_used DESC
                LIMIT ?
            ''', (limit,))
            return cursor.fetchall()
    
    def close(self):
        self.conn.close()

# ============================================================================
# WALLHAVEN API WRAPPER
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
    
    def get_wallpaper(self, wallpaper_id):
        url = f"{self.BASE_URL}/w/{wallpaper_id}"
        response = self.session.get(url)
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
# WALLPAPER CHANGER CORE
# ============================================================================

class WallpaperChanger:
    def __init__(self, config=None):
        self.config = config or self.load_config()
        
        # Ensure download folder is set correctly
        if not self.config.get("download_folder") or self.config["download_folder"] == "":
            self.config["download_folder"] = WALLHAVEN_FOLDER
            print(f"Set download folder to default: {WALLHAVEN_FOLDER}")
        
        self.api = WallhavenAPI(self.config.get("api_key", ""))
        self.db = FavoritesDatabase()
        self.filters = FiltersManager(self.config)
        self.quota = QuotaManager(
            self.config["download_folder"],
            self.config.get("quota_enabled", True),
            self.config.get("quota_size", 1000)
        )
        self.favorites_folder_manager = FavoritesFolderManager(self.config)
        self.running = False
        self.timer = None
        self.current_wallpaper = None
        self.current_wallpaper_id = None
        self.current_wallpaper_type = "static"
        self.wallpaper_queue = []
        self.tray_icon = None
        self.notification_callback = None
        self.downloaded_wallpapers = []
        self.current_nav_index = -1
        
        # Create download folder if it doesn't exist
        try:
            os.makedirs(self.config["download_folder"], exist_ok=True)
            print(f"Download folder ready: {self.config['download_folder']}")
        except Exception as e:
            print(f"Error creating download folder: {e}")
            # Fallback to temp folder
            self.config["download_folder"] = os.path.join(tempfile.gettempdir(), "WallpaperDownloads")
            os.makedirs(self.config["download_folder"], exist_ok=True)
            print(f"Using fallback folder: {self.config['download_folder']}")
        
        if self.config.get("remember_last_wallpaper", True):
            self.load_last_wallpaper()
        
        self.scan_downloaded_wallpapers()
    
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    # Merge with defaults
                    merged = DEFAULT_CONFIG.copy()
                    merged.update(config)
                    
                    # Ensure download folder is set
                    if not merged.get("download_folder") or merged["download_folder"] == "":
                        merged["download_folder"] = WALLHAVEN_FOLDER
                        print(f"Config missing download folder, using default: {WALLHAVEN_FOLDER}")
                    
                    return merged
            except Exception as e:
                print(f"Error loading config: {e}")
                return DEFAULT_CONFIG.copy()
        print(f"No config file found, using defaults with download folder: {WALLHAVEN_FOLDER}")
        return DEFAULT_CONFIG.copy()
    
    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def get_interval_seconds(self):
        """Get interval in seconds based on unit"""
        value = self.config.get("interval_value", 30)
        unit = self.config.get("interval_unit", "minutes")
        
        if unit == "minutes":
            return value * 60
        elif unit == "hours":
            return value * 3600
        elif unit == "days":
            return value * 86400
        else:
            return value * 60
    
    def load_last_wallpaper(self):
        """Load the last used wallpaper on startup"""
        if os.path.exists(LAST_WALLPAPER_FILE):
            try:
                with open(LAST_WALLPAPER_FILE, 'r') as f:
                    data = json.load(f)
                    if os.path.exists(data.get('path', '')):
                        self.set_wallpaper(data['path'], data.get('id'), data.get('type', 'static'))
            except:
                pass
    
    def scan_downloaded_wallpapers(self):
        """Scan download folder for wallpapers"""
        folder = self.config["download_folder"]
        self.downloaded_wallpapers = []
        
        if os.path.exists(folder):
            for file in sorted(os.listdir(folder)):
                if file.endswith(('.jpg', '.jpeg', '.png', '.gif', '.mp4', '.webm')):
                    file_path = os.path.join(folder, file)
                    self.downloaded_wallpapers.append(file_path)
        
        if self.current_wallpaper in self.downloaded_wallpapers:
            self.current_nav_index = self.downloaded_wallpapers.index(self.current_wallpaper)
        else:
            self.current_nav_index = -1
    
    def delete_current_wallpaper(self):
        """Delete the current wallpaper file"""
        if not self.current_wallpaper:
            return False, "No wallpaper to delete"
        
        try:
            # Check if it's a favorite
            if self.current_wallpaper_id and self.db.is_favorite(self.current_wallpaper_id):
                return False, "Cannot delete favorite wallpaper"
            
            # Remove from list
            if self.current_wallpaper in self.downloaded_wallpapers:
                self.downloaded_wallpapers.remove(self.current_wallpaper)
            
            # Delete file
            os.remove(self.current_wallpaper)
            
            # Update navigation
            self.current_nav_index = min(self.current_nav_index, len(self.downloaded_wallpapers) - 1)
            
            # Set next wallpaper if available
            if self.downloaded_wallpapers:
                next_idx = min(self.current_nav_index, len(self.downloaded_wallpapers) - 1)
                if next_idx >= 0:
                    self.set_wallpaper(self.downloaded_wallpapers[next_idx])
            
            return True, "Wallpaper deleted"
        except Exception as e:
            return False, f"Error deleting: {e}"
    
    def next_wallpaper(self):
        """Go to next wallpaper in download folder"""
        if self.current_nav_index < len(self.downloaded_wallpapers) - 1:
            self.current_nav_index += 1
            wallpaper_path = self.downloaded_wallpapers[self.current_nav_index]
            
            filename = os.path.basename(wallpaper_path)
            wallpaper_id = filename.replace('wallhaven_', '').split('.')[0] if 'wallhaven_' in filename else "local_" + filename
            file_ext = os.path.splitext(wallpaper_path)[1].lower()
            
            file_type = "static"
            if file_ext == '.gif':
                file_type = "gif"
            elif file_ext in ['.mp4', '.webm']:
                file_type = "video"
            
            self.set_wallpaper(wallpaper_path, wallpaper_id, file_type)
            return True
        return False
    
    def previous_wallpaper(self):
        """Go to previous wallpaper in download folder"""
        if self.current_nav_index > 0:
            self.current_nav_index -= 1
            wallpaper_path = self.downloaded_wallpapers[self.current_nav_index]
            
            filename = os.path.basename(wallpaper_path)
            wallpaper_id = filename.replace('wallhaven_', '').split('.')[0] if 'wallhaven_' in filename else "local_" + filename
            file_ext = os.path.splitext(wallpaper_path)[1].lower()
            
            file_type = "static"
            if file_ext == '.gif':
                file_type = "gif"
            elif file_ext in ['.mp4', '.webm']:
                file_type = "video"
            
            self.set_wallpaper(wallpaper_path, wallpaper_id, file_type)
            return True
        return False
    
    def get_navigation_info(self):
        """Get current navigation info"""
        total = len(self.downloaded_wallpapers)
        current = self.current_nav_index + 1 if self.current_nav_index >= 0 else 0
        return current, total
    
    def set_wallpaper_style(self, style):
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Control Panel\\Desktop",
            0, winreg.KEY_SET_VALUE
        )
        
        style_values = {
            'fill': ('10', '0'),
            'fit': ('6', '0'),
            'stretch': ('2', '0'),
            'tile': ('0', '1'),
            'center': ('0', '0'),
            'span': ('22', '0')
        }
        
        if style in style_values:
            wallpaper_style, tile_wallpaper = style_values[style]
            winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, wallpaper_style)
            winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, tile_wallpaper)
        
        winreg.CloseKey(key)
    
    def set_wallpaper(self, image_path, wallpaper_id=None, file_type="static"):
        self.set_wallpaper_style(self.config.get("wallpaper_style", "fill"))
        
        image_path = os.path.abspath(image_path)
        ctypes.windll.user32.SystemParametersInfoW(20, 0, image_path, 3)
        
        self.current_wallpaper = image_path
        self.current_wallpaper_id = wallpaper_id
        self.current_wallpaper_type = file_type
        
        if image_path in self.downloaded_wallpapers:
            self.current_nav_index = self.downloaded_wallpapers.index(image_path)
        
        if wallpaper_id and self.db.is_favorite(wallpaper_id):
            self.db.record_use(wallpaper_id, file_type)
        
        self.log_change(image_path, wallpaper_id, file_type)
        
        try:
            with open(LAST_WALLPAPER_FILE, 'w') as f:
                json.dump({
                    'path': image_path,
                    'id': wallpaper_id,
                    'type': file_type,
                    'time': time.time()
                }, f)
        except:
            pass
        
        if self.config.get("notifications", True) and self.notification_callback:
            self.notification_callback("Wallpaper Changed", os.path.basename(image_path))
        
        return True, "Wallpaper set successfully"
    
    def log_change(self, image_path, wallpaper_id=None, wallpaper_type="static"):
        log_file = os.path.join(self.config["download_folder"], "wallpaper_log.txt")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fav_status = "★" if wallpaper_id and self.db.is_favorite(wallpaper_id) else "☆"
        type_indicator = {
            "static": "🖼️",
            "gif": "🎬",
            "video": "🎥"
        }.get(wallpaper_type, "🖼️")
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{timestamp} {type_indicator} {fav_status} - {image_path}\n")
    
    def start_auto_change(self):
        if self.running:
            return
        
        self.running = True
        self.auto_change_loop()
        
        if self.notification_callback:
            interval_text = f"{self.config['interval_value']} {self.config['interval_unit']}"
            self.notification_callback("Auto-Change Started", f"Changing every {interval_text}")
    
    def stop_auto_change(self):
        self.running = False
        if self.timer:
            self.timer.cancel()
            self.timer = None
        
        if self.notification_callback:
            self.notification_callback("Auto-Change Stopped", "Manual mode activated")
    
    def auto_change_loop(self):
        if not self.running:
            return
        
        if self.notification_callback:
            self.notification_callback("Auto-Change", "Changing wallpaper...")
        
        interval = self.get_interval_seconds()
        self.timer = threading.Timer(interval, self.auto_change_loop)
        self.timer.daemon = True
        self.timer.start()
    
    def toggle_favorite_current(self):
        if not self.current_wallpaper_id:
            return False, "No wallpaper selected"
        
        if self.db.is_favorite(self.current_wallpaper_id):
            self.db.remove_favorite(self.current_wallpaper_id)
            
            # Also remove from favorites folder if it's there
            if self.favorites_folder_manager.copy_enabled:
                filename = os.path.basename(self.current_wallpaper)
                self.favorites_folder_manager.remove_from_favorites(filename)
            
            return False, "Removed from favorites"
        else:
            try:
                folder_name = ""
                keyword = ""
                in_favorites_folder = 0
                
                if self.current_wallpaper_id.startswith('local_'):
                    folder_name = os.path.basename(os.path.dirname(self.current_wallpaper))
                
                # Copy to favorites folder if enabled
                if self.favorites_folder_manager.copy_enabled:
                    dest_path, message = self.favorites_folder_manager.copy_to_favorites(
                        self.current_wallpaper, 
                        self.current_wallpaper_id, 
                        self.current_wallpaper_type
                    )
                    if dest_path:
                        in_favorites_folder = 1
                
                fav_data = {
                    'id': self.current_wallpaper_id,
                    'path': self.current_wallpaper,
                    'url': '',
                    'thumbnail': '',
                    'resolution': '',
                    'category': 'local' if self.current_wallpaper_id.startswith('local_') else 'wallhaven',
                    'purity': 'sfw',
                    'tags': 'favorite',
                    'file_type': self.current_wallpaper_type,
                    'source': 'local' if self.current_wallpaper_id.startswith('local_') else 'wallhaven',
                    'folder_name': folder_name,
                    'keyword': keyword,
                    'in_favorites_folder': in_favorites_folder
                }
                
                self.db.add_favorite(fav_data)
                return True, "Added to favorites"
            except Exception as e:
                return False, f"Error: {e}"
    
    def get_next_change_time(self):
        if self.running and self.timer:
            interval = self.get_interval_seconds()
            next_time = datetime.now() + timedelta(seconds=interval)
            return next_time.strftime("%H:%M:%S")
        return "Not scheduled"

# ============================================================================
# WALLHAVEN SOURCE
# ============================================================================

class WallhavenSource:
    """Wallhaven API integration"""
    def __init__(self, api_key=None, filters=None, enabled=True):
        self.name = "Wallhaven"
        self.enabled = enabled
        self.api_key = api_key
        self.filters = filters or {}
        self.api = WallhavenAPI(api_key)
    
    def get_filters(self):
        """Get current filters"""
        return {
            "categories": self.filters.get("categories", {"general": 1, "anime": 1, "people": 1}),
            "purity": self.filters.get("purity", {"sfw": 1, "sketchy": 0, "nsfw": 0}),
            "atleast": self.filters.get("min_resolution", "1920x1080"),
            "resolutions": self.filters.get("resolutions", []),
            "ratios": self.filters.get("aspect_ratios", [])
        }
    
    def get_images(self, count=10, tags=None):
        try:
            params = {
                "page": random.randint(1, 5),
                "sorting": "date_added",
                "order": "desc",
                "atleast": self.filters.get("min_resolution", "1920x1080")
            }
            
            filters = self.get_filters()
            params["categories"] = filters["categories"]
            params["purity"] = filters["purity"]
            
            if tags:
                if isinstance(tags, list):
                    params["q"] = " ".join(tags)
                else:
                    params["q"] = tags
            
            if filters["resolutions"]:
                params["resolutions"] = ",".join(filters["resolutions"])
            
            if filters["ratios"]:
                params["ratios"] = ",".join(filters["ratios"])
            
            results = self.api.search(**params)
            
            images = []
            for item in results.get('data', []):
                images.append({
                    'id': f"wallhaven_{item['id']}",
                    'url': item['path'],
                    'download_url': item['path'],
                    'thumbnail': item.get('thumbs', {}).get('small', item['path']),
                    'title': f"Wallhaven {item['id']}",
                    'author': 'Wallhaven',
                    'author_url': f"https://wallhaven.cc/w/{item['id']}",
                    'source': 'wallhaven',
                    'width': item.get('resolution', '').split('x')[0] if 'x' in item.get('resolution', '') else 1920,
                    'height': item.get('resolution', '').split('x')[1] if 'x' in item.get('resolution', '') else 1080,
                    'resolution': item.get('resolution', ''),
                    'category': item.get('category', ''),
                    'purity': item.get('purity', ''),
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
    """Manages Wallhaven source"""
    
    def __init__(self, api_key=None, filters=None):
        self.api_key = api_key
        self.filters = filters or {}
        self.source = WallhavenSource(api_key, filters)
        self.load_config()
    
    def load_config(self):
        """Load source configuration"""
        if os.path.exists(SOURCES_FILE):
            try:
                with open(SOURCES_FILE, 'r') as f:
                    config = json.load(f)
                    if "Wallhaven" in config:
                        self.source.enabled = config["Wallhaven"].get('enabled', True)
                        if 'api_key' in config["Wallhaven"]:
                            self.source.api_key = config["Wallhaven"]['api_key']
            except:
                pass
    
    def save_config(self):
        """Save source configuration"""
        config = {
            "Wallhaven": {
                'enabled': self.source.enabled,
                'api_key': self.source.api_key
            }
        }
        with open(SOURCES_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    
    def update_filters(self, filters):
        """Update filters for source"""
        self.filters = filters
        self.source.filters = filters
    
    def get_images(self, count=10, tags=None):
        """Get images from Wallhaven"""
        if not self.source.enabled:
            return []
        return self.source.get_images(count, tags)
    
    def search(self, query, count=10):
        """Search Wallhaven"""
        if not self.source.enabled:
            return []
        return self.source.search(query, count)

# ============================================================================
# SCHEDULE CLASS
# ============================================================================

class Schedule:
    """Represents a wallpaper schedule"""
    def __init__(self, name, schedule_type="interval"):
        self.name = name
        self.schedule_type = schedule_type
        self.enabled = True
        self.priority = 0
        self.interval_value = 30
        self.interval_unit = "minutes"
        self.time_ranges = []
        self.time_tags = {}
        self.weekday_settings = {}
        self.weather_conditions = []
        self.weather_location = None
        self.tags = []
        self.categories = {"general": 1, "anime": 1, "people": 1}
        self.purity = {"sfw": 1, "sketchy": 0, "nsfw": 0}
        self.sources = []
        self.blur_amount = 0
        self.darken_amount = 0
    
    def to_dict(self):
        return {
            'name': self.name,
            'type': self.schedule_type,
            'enabled': self.enabled,
            'priority': self.priority,
            'interval_value': self.interval_value,
            'interval_unit': self.interval_unit,
            'time_ranges': self.time_ranges,
            'time_tags': self.time_tags,
            'weekday_settings': self.weekday_settings,
            'weather_conditions': self.weather_conditions,
            'weather_location': self.weather_location,
            'tags': self.tags,
            'categories': self.categories,
            'purity': self.purity,
            'sources': self.sources,
            'blur_amount': self.blur_amount,
            'darken_amount': self.darken_amount
        }
    
    @classmethod
    def from_dict(cls, data):
        schedule = cls(data.get('name', 'New Schedule'))
        schedule.schedule_type = data.get('type', 'interval')
        schedule.enabled = data.get('enabled', True)
        schedule.priority = data.get('priority', 0)
        schedule.interval_value = data.get('interval_value', 30)
        schedule.interval_unit = data.get('interval_unit', 'minutes')
        schedule.time_ranges = data.get('time_ranges', [])
        schedule.time_tags = data.get('time_tags', {})
        schedule.weekday_settings = data.get('weekday_settings', {})
        schedule.weather_conditions = data.get('weather_conditions', [])
        schedule.weather_location = data.get('weather_location')
        schedule.tags = data.get('tags', [])
        schedule.categories = data.get('categories', {"general": 1, "anime": 1, "people": 1})
        schedule.purity = data.get('purity', {"sfw": 1, "sketchy": 0, "nsfw": 0})
        schedule.sources = data.get('sources', [])
        schedule.blur_amount = data.get('blur_amount', 0)
        schedule.darken_amount = data.get('darken_amount', 0)
        return schedule

# ============================================================================
# SCHEDULE MANAGER
# ============================================================================

class ScheduleManager:
    """Manages schedules"""
    
    def __init__(self):
        self.schedules = []
        self.active_schedule = None
        self.load_schedules()
    
    def load_schedules(self):
        """Load schedules from file"""
        if os.path.exists(SCHEDULES_FILE):
            try:
                with open(SCHEDULES_FILE, 'r') as f:
                    data = json.load(f)
                    self.schedules = [Schedule.from_dict(s) for s in data.get('schedules', [])]
                    active_name = data.get('active_schedule')
                    if active_name:
                        for s in self.schedules:
                            if s.name == active_name:
                                self.active_schedule = s
                                break
            except:
                pass
        
        if not self.schedules:
            self.create_default_schedules()
    
    def save_schedules(self):
        """Save schedules to file"""
        data = {
            'schedules': [s.to_dict() for s in self.schedules],
            'active_schedule': self.active_schedule.name if self.active_schedule else None
        }
        with open(SCHEDULES_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def create_default_schedules(self):
        """Create default schedules"""
        morning = Schedule("Morning", "time_of_day")
        morning.time_ranges = [("06:00", "12:00")]
        morning.tags = ["sunrise", "morning", "nature"]
        morning.priority = 1
        self.schedules.append(morning)
        
        afternoon = Schedule("Afternoon", "time_of_day")
        afternoon.time_ranges = [("12:00", "18:00")]
        afternoon.tags = ["landscape", "city", "day"]
        afternoon.priority = 1
        self.schedules.append(afternoon)
        
        evening = Schedule("Evening", "time_of_day")
        evening.time_ranges = [("18:00", "22:00")]
        evening.tags = ["sunset", "evening", "city_lights"]
        evening.priority = 1
        self.schedules.append(evening)
        
        night = Schedule("Night", "time_of_day")
        night.time_ranges = [("22:00", "06:00")]
        night.tags = ["night", "space", "stars", "moon"]
        night.priority = 1
        self.schedules.append(night)
        
        self.save_schedules()
    
    def add_schedule(self, schedule):
        """Add a new schedule"""
        self.schedules.append(schedule)
        self.save_schedules()
    
    def update_schedule(self, schedule):
        """Update an existing schedule"""
        for i, s in enumerate(self.schedules):
            if s.name == schedule.name:
                self.schedules[i] = schedule
                break
        self.save_schedules()
    
    def delete_schedule(self, schedule):
        """Delete a schedule"""
        self.schedules.remove(schedule)
        self.save_schedules()
    
    def get_current_schedule(self):
        """Get the currently active schedule based on conditions"""
        if not self.schedules:
            return None
        
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        current_time = f"{current_hour:02d}:{current_minute:02d}"
        current_weekday = now.strftime("%A").lower()
        
        matches = []
        for schedule in self.schedules:
            if not schedule.enabled:
                continue
            
            match = False
            
            if schedule.schedule_type == "time_of_day":
                for start, end in schedule.time_ranges:
                    if start <= current_time <= end:
                        match = True
                        break
            
            elif schedule.schedule_type == "interval":
                match = True
            
            if match:
                matches.append(schedule)
        
        if matches:
            return max(matches, key=lambda s: s.priority)
        
        return None
    
    def get_current_tags(self):
        """Get tags for current schedule"""
        schedule = self.get_current_schedule()
        if schedule:
            return schedule.tags
        return []

# ============================================================================
# SCHEDULE EDITOR
# ============================================================================

class ScheduleEditor:
    """Edit schedule details"""
    
    def __init__(self, parent, schedule, save_callback):
        self.parent = parent
        self.schedule = schedule
        self.save_callback = save_callback
        self.colors = parent.colors
        
        self.window = tk.Toplevel(parent.root)
        self.window.title(f"Edit Schedule: {schedule.name}")
        self.window.geometry("500x600")
        self.window.transient(parent.root)
        self.window.grab_set()
        self.window.configure(bg=self.colors["bg"])
        
        self.setup_ui()
    
    def setup_ui(self):
        # Title
        title = tk.Label(self.window, text=f"✏️ Edit Schedule", 
                        bg=self.colors["bg"], fg=self.colors["accent"],
                        font=('Segoe UI', 16, 'bold'))
        title.pack(pady=10)
        
        # Main card
        card = ModernCard(self.window, self.colors)
        card.pack(fill='both', expand=True, padx=10, pady=10)
        
        content = card.inner
        
        # Name
        name_frame = tk.Frame(content, bg=self.colors["card_bg"])
        name_frame.pack(fill='x', pady=5)
        
        tk.Label(name_frame, text="Schedule Name:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        self.name_var = tk.StringVar(value=self.schedule.name)
        tk.Entry(name_frame, textvariable=self.name_var,
                bg=self.colors["entry_bg"], fg=self.colors["fg"],
                relief='flat', width=40).pack(fill='x', pady=5)
        
        # Type
        type_frame = tk.Frame(content, bg=self.colors["card_bg"])
        type_frame.pack(fill='x', pady=5)
        
        tk.Label(type_frame, text="Schedule Type:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        self.type_var = tk.StringVar(value=self.schedule.schedule_type)
        type_combo = ttk.Combobox(type_frame, textvariable=self.type_var,
                                  values=["interval", "time_of_day"],
                                  state="readonly", width=20)
        type_combo.pack(anchor='w', pady=5)
        type_combo.bind('<<ComboboxSelected>>', self.on_type_change)
        
        # Priority
        priority_frame = tk.Frame(content, bg=self.colors["card_bg"])
        priority_frame.pack(fill='x', pady=5)
        
        tk.Label(priority_frame, text="Priority (higher = more important):", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        self.priority_var = tk.IntVar(value=self.schedule.priority)
        tk.Spinbox(priority_frame, from_=0, to=10, textvariable=self.priority_var,
                  bg=self.colors["entry_bg"], fg=self.colors["fg"],
                  relief='flat', width=5).pack(anchor='w', pady=5)
        
        # Dynamic settings based on type
        self.settings_frame = tk.Frame(content, bg=self.colors["card_bg"])
        self.settings_frame.pack(fill='x', pady=10)
        
        self.update_settings_ui()
        
        # Tags
        tags_frame = tk.Frame(content, bg=self.colors["card_bg"])
        tags_frame.pack(fill='x', pady=5)
        
        tk.Label(tags_frame, text="Tags (comma separated):", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        self.tags_var = tk.StringVar(value=", ".join(self.schedule.tags))
        tk.Entry(tags_frame, textvariable=self.tags_var,
                bg=self.colors["entry_bg"], fg=self.colors["fg"],
                relief='flat', width=40).pack(fill='x', pady=5)
        
        # Buttons
        btn_frame = tk.Frame(self.window, bg=self.colors["bg"])
        btn_frame.pack(fill='x', pady=10)
        
        ModernButton(btn_frame, text="Save", 
                    command=self.save,
                    variant="success").pack(side='right', padx=5)
        
        ModernButton(btn_frame, text="Cancel", 
                    command=self.window.destroy,
                    variant="danger").pack(side='right', padx=5)
    
    def on_type_change(self, event=None):
        """Handle schedule type change"""
        self.update_settings_ui()
    
    def update_settings_ui(self):
        """Update settings UI based on schedule type"""
        for widget in self.settings_frame.winfo_children():
            widget.destroy()
        
        schedule_type = self.type_var.get()
        
        if schedule_type == "interval":
            self.setup_interval_ui()
        elif schedule_type == "time_of_day":
            self.setup_time_of_day_ui()
    
    def setup_interval_ui(self):
        """Setup interval settings UI"""
        frame = self.settings_frame
        
        tk.Label(frame, text="Interval Settings:", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=5)
        
        row = tk.Frame(frame, bg=self.colors["card_bg"])
        row.pack(fill='x', pady=2)
        
        tk.Label(row, text="Every:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(side='left')
        
        self.interval_value_var = tk.IntVar(value=self.schedule.interval_value)
        tk.Spinbox(row, from_=1, to=999, textvariable=self.interval_value_var,
                  bg=self.colors["entry_bg"], fg=self.colors["fg"],
                  relief='flat', width=8).pack(side='left', padx=5)
        
        self.interval_unit_var = tk.StringVar(value=self.schedule.interval_unit)
        unit_combo = ttk.Combobox(row, textvariable=self.interval_unit_var,
                                  values=["minutes", "hours", "days"],
                                  state="readonly", width=10)
        unit_combo.pack(side='left', padx=5)
    
    def setup_time_of_day_ui(self):
        """Setup time of day settings UI"""
        frame = self.settings_frame
        
        tk.Label(frame, text="Time Ranges:", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=5)
        
        # Show existing time ranges
        self.time_ranges = []
        for i, (start, end) in enumerate(self.schedule.time_ranges):
            self.add_time_range_row(i, start, end)
        
        # Add new range button
        ModernButton(frame, text="+ Add Time Range", 
                    command=self.add_time_range,
                    variant="info").pack(pady=5)
    
    def add_time_range_row(self, index, start="", end=""):
        """Add a time range row"""
        row = tk.Frame(self.settings_frame, bg=self.colors["card_bg"])
        row.pack(fill='x', pady=2)
        
        start_var = tk.StringVar(value=start)
        start_entry = tk.Entry(row, textvariable=start_var,
                              bg=self.colors["entry_bg"], fg=self.colors["fg"],
                              relief='flat', width=10)
        start_entry.pack(side='left', padx=2)
        
        tk.Label(row, text="to", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(side='left', padx=2)
        
        end_var = tk.StringVar(value=end)
        end_entry = tk.Entry(row, textvariable=end_var,
                            bg=self.colors["entry_bg"], fg=self.colors["fg"],
                            relief='flat', width=10)
        end_entry.pack(side='left', padx=2)
        
        tk.Label(row, text="(HH:MM format)", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 8)).pack(side='left', padx=5)
        
        ModernButton(row, text="✖", 
                    command=lambda: self.remove_time_range(row),
                    variant="danger", width=2).pack(side='right', padx=2)
        
        self.time_ranges.append((start_var, end_var, row))
    
    def add_time_range(self):
        """Add a new time range"""
        self.add_time_range_row(len(self.time_ranges))
    
    def remove_time_range(self, row):
        """Remove a time range"""
        row.destroy()
        self.time_ranges = [tr for tr in self.time_ranges if tr[2] != row]
    
    def save(self):
        """Save schedule changes"""
        self.schedule.name = self.name_var.get()
        self.schedule.schedule_type = self.type_var.get()
        self.schedule.priority = self.priority_var.get()
        
        # Parse tags
        tags_text = self.tags_var.get()
        self.schedule.tags = [t.strip() for t in tags_text.split(",") if t.strip()]
        
        # Save type-specific settings
        if self.schedule.schedule_type == "interval":
            self.schedule.interval_value = self.interval_value_var.get()
            self.schedule.interval_unit = self.interval_unit_var.get()
        
        elif self.schedule.schedule_type == "time_of_day":
            ranges = []
            for start_var, end_var, _ in self.time_ranges:
                start = start_var.get().strip()
                end = end_var.get().strip()
                if start and end:
                    ranges.append((start, end))
            self.schedule.time_ranges = ranges
        
        self.save_callback(self.schedule)
        self.window.destroy()

# ============================================================================
# WALLPAPER EFFECTS
# ============================================================================

class WallpaperEffects:
    """Apply effects to wallpapers"""
    
    @staticmethod
    def apply_blur(image_path, blur_amount=5):
        """Apply blur effect to image"""
        try:
            img = Image.open(image_path)
            if blur_amount > 0:
                img = img.filter(ImageFilter.GaussianBlur(radius=blur_amount))
            
            temp_path = image_path.replace('.', '_blurred.')
            img.save(temp_path)
            return temp_path
        except Exception as e:
            print(f"Error applying blur: {e}")
            return image_path
    
    @staticmethod
    def apply_darken(image_path, darken_amount=0.3):
        """Apply darkening effect"""
        try:
            img = Image.open(image_path).convert('RGBA')
            if darken_amount > 0:
                overlay = Image.new('RGBA', img.size, (0, 0, 0, int(255 * darken_amount)))
                img = Image.alpha_composite(img, overlay)
            
            img = img.convert('RGB')
            
            temp_path = image_path.replace('.', '_darkened.')
            img.save(temp_path)
            return temp_path
        except Exception as e:
            print(f"Error applying darken: {e}")
            return image_path
    
    @staticmethod
    def apply_effects(image_path, blur=0, darken=0):
        """Apply multiple effects"""
        result = image_path
        if blur > 0:
            result = WallpaperEffects.apply_blur(result, blur)
        if darken > 0:
            result = WallpaperEffects.apply_darken(result, darken)
        return result

# ============================================================================
# MODERN UI WIDGETS
# ============================================================================

class ModernCard(tk.Frame):
    """A beautiful card widget with shadow and rounded corners"""
    def __init__(self, parent, colors, **kwargs):
        super().__init__(parent, bg=colors["card_bg"], **kwargs)
        self.colors = colors
        self.configure(relief='flat', bd=0)
        self.inner = tk.Frame(self, bg=colors["card_bg"])
        self.inner.pack(fill='both', expand=True, padx=12, pady=12)

class ModernButton(tk.Button):
    """Modern styled button"""
    def __init__(self, parent, text="", command=None, variant="primary", icon=None, **kwargs):
        colors = parent.colors if hasattr(parent, 'colors') else COLOR_SCHEMES["light"]
        
        variants = {
            "primary": {"bg": colors["accent"], "fg": "white", "hover": colors["accent_light"]},
            "secondary": {"bg": colors["card_bg"], "fg": colors["fg"], "hover": colors["card_shadow"]},
            "success": {"bg": colors["success"], "fg": "white", "hover": "#34d399"},
            "warning": {"bg": colors["warning"], "fg": "white", "hover": "#fbbf24"},
            "danger": {"bg": colors["error"], "fg": "white", "hover": "#f87171"},
            "info": {"bg": colors["info"], "fg": "white", "hover": colors["accent_light"]}
        }
        
        style = variants.get(variant, variants["primary"])
        
        if icon:
            display_text = f"{icon} {text}" if text else icon
        else:
            display_text = text
        
        super().__init__(parent, text=display_text, command=command,
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
    """Modern toggle switch"""
    def __init__(self, parent, text="", variable=None, **kwargs):
        super().__init__(parent, bg=parent.colors["bg"] if hasattr(parent, 'colors') else "#f0f7ff")
        self.colors = parent.colors if hasattr(parent, 'colors') else COLOR_SCHEMES["light"]
        self.variable = variable or tk.BooleanVar()
        
        if text:
            self.label = tk.Label(self, text=text, bg=self.colors["bg"], fg=self.colors["fg"],
                                  font=('Segoe UI', 10))
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
            self.canvas.create_text(15, 13, text="ON", fill="white", font=('Segoe UI', 8, 'bold'))
        else:
            self.canvas.create_rectangle(0, 0, 50, 26, fill=self.colors["trough_color"], outline="")
            self.canvas.create_oval(2, 2, 24, 24, fill="white", outline="")
            self.canvas.create_text(38, 13, text="OFF", fill=self.colors["fg"], font=('Segoe UI', 8, 'bold'))
    
    def toggle(self, event=None):
        self.variable.set(not self.variable.get())

class ModernSlider(tk.Frame):
    """Modern slider with value display"""
    def __init__(self, parent, text="", from_=0, to=100, variable=None, **kwargs):
        super().__init__(parent, bg=parent.colors["bg"] if hasattr(parent, 'colors') else "#f0f7ff")
        self.colors = parent.colors if hasattr(parent, 'colors') else COLOR_SCHEMES["light"]
        self.variable = variable or tk.IntVar()
        
        if text:
            self.label = tk.Label(self, text=text, bg=self.colors["bg"], fg=self.colors["fg"],
                                  font=('Segoe UI', 10))
            self.label.pack(side='left', padx=(0, 10))
        
        self.slider = tk.Scale(self, from_=from_, to=to, orient='horizontal',
                               variable=self.variable, showvalue=False,
                               bg=self.colors["bg"], fg=self.colors["fg"],
                               highlightbackground=self.colors["bg"],
                               troughcolor=self.colors["trough_color"],
                               activebackground=self.colors["accent"])
        self.slider.pack(side='left', fill='x', expand=True, padx=5)
        
        self.value_label = tk.Label(self, text=str(self.variable.get()), 
                                    bg=self.colors["bg"], fg=self.colors["accent"],
                                    font=('Segoe UI', 10, 'bold'), width=4)
        self.value_label.pack(side='left')
        
        self.variable.trace('w', lambda *args: self.value_label.config(text=str(self.variable.get())))

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
        draw.line([20, 44, 30, 30, 40, 40, 44, 36], fill=colors["button_fg"], width=2)
        
        interval_text = f"{self.changer.config['interval_value']} {self.changer.config['interval_unit']}"
        
        menu = pystray.Menu(
            pystray.MenuItem("Next Wallpaper", self.next_wallpaper),
            pystray.MenuItem("Previous Wallpaper", self.previous_wallpaper),
            pystray.MenuItem("Delete Current", self.delete_wallpaper),
            pystray.MenuItem(
                "Auto-Change",
                pystray.Menu(
                    pystray.MenuItem("Start", self.start_auto, checked=lambda item: False),
                    pystray.MenuItem("Stop", self.stop_auto, checked=lambda item: False),
                    pystray.MenuItem(f"Interval: {interval_text}", self.show_interval, enabled=False)
                )
            ),
            pystray.MenuItem(
                "Favorites",
                pystray.Menu(
                    pystray.MenuItem("Add Current", self.add_to_favorites),
                    pystray.MenuItem("View Favorites", self.view_favorites),
                    pystray.MenuItem("Random from Favorites", self.random_favorite),
                    pystray.MenuItem("Open Favorites Folder", self.open_favorites_folder)
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
        
        self.icon = pystray.Icon(
            "wallpaper_changer",
            image,
            "Wallpaper Changer",
            menu
        )
        
        self.changer.notification_callback = self.show_notification
    
    def next_wallpaper(self):
        self.app.root.after(0, self.app.next_wallpaper)
    
    def previous_wallpaper(self):
        self.app.root.after(0, self.app.previous_wallpaper)
    
    def delete_wallpaper(self):
        self.app.root.after(0, self.app.delete_current_wallpaper)
    
    def start_auto(self):
        self.app.toggle_auto()
        self.update_menu()
    
    def stop_auto(self):
        self.app.toggle_auto()
        self.update_menu()
    
    def add_to_favorites(self):
        self.app.toggle_favorite()
    
    def view_favorites(self):
        self.app.show_favorites_window()
    
    def random_favorite(self):
        favorites = self.changer.db.get_favorites(limit=100)
        if favorites:
            favorite = random.choice(favorites)
            file_type = favorite[8] if len(favorite) > 8 else "static"
            self.changer.set_wallpaper(favorite[1], favorite[0], file_type)
            self.app.update_preview()
    
    def open_favorites_folder(self):
        """Open the favorites folder"""
        folder = self.changer.favorites_folder_manager.favorites_folder
        if os.path.exists(folder):
            os.startfile(folder)
        else:
            os.makedirs(folder, exist_ok=True)
            os.startfile(folder)
    
    def show_interval(self):
        pass
    
    def open_folder(self):
        folder = self.changer.config["download_folder"]
        if os.path.exists(folder):
            os.startfile(folder)
    
    def show_settings(self):
        self.app.show_window()
    
    def exit_app(self):
        self.changer.stop_auto_change()
        self.changer.db.close()
        self.icon.stop()
        self.app.quit()
    
    def show_notification(self, title, message):
        if self.icon and self.changer.config.get("notifications", True):
            self.icon.notify(message, title)
    
    def update_menu(self):
        if self.icon:
            self.icon.stop()
            self.create_icon()
            threading.Thread(target=self.icon.run, daemon=True).start()
    
    def run(self):
        threading.Thread(target=self.icon.run, daemon=True).start()

# ============================================================================
# FAVORITES WINDOW
# ============================================================================

class FavoritesWindow:
    def __init__(self, parent, changer):
        self.changer = changer
        self.parent = parent
        self.colors = parent.colors
        
        self.window = tk.Toplevel(parent.root)
        self.window.title("Favorites")
        self.window.geometry("600x400")
        self.window.transient(parent.root)
        self.window.grab_set()
        self.window.configure(bg=self.colors["bg"])
        
        tk.Label(self.window, text="❤️ Your Favorites", 
                bg=self.colors["bg"], fg=self.colors["fg"],
                font=('Segoe UI', 16, 'bold')).pack(pady=10)
        
        listbox = tk.Listbox(self.window, bg=self.colors["entry_bg"],
                            fg=self.colors["fg"], height=15)
        listbox.pack(fill='both', expand=True, padx=10, pady=10)
        
        favorites = self.changer.db.get_favorites(limit=50)
        for fav in favorites:
            # Add icon if in favorites folder
            icon = "📁 " if len(fav) > 14 and fav[14] else "❤️ "
            listbox.insert(tk.END, f"{icon}{fav[0][:8]}... - {fav[4] if fav[4] else 'Unknown'}")

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
        header = tk.Frame(self.parent, bg=self.colors["bg"])
        header.pack(fill='x', pady=10)
        
        tk.Label(header, text="🔑 Keyword Downloads", 
                bg=self.colors["bg"], fg=self.colors["accent"],
                font=('Segoe UI', 16, 'bold')).pack(side='left')
        
        settings_frame = tk.Frame(self.parent, bg=self.colors["bg"])
        settings_frame.pack(fill='x', pady=10)
        
        card = ModernCard(settings_frame, self.colors)
        card.pack(fill='x')
        
        content = card.inner
        
        tk.Label(content, text="Download Settings", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=5)
        
        per_keyword_frame = tk.Frame(content, bg=self.colors["card_bg"])
        per_keyword_frame.pack(fill='x', pady=5)
        
        tk.Label(per_keyword_frame, text="Wallpapers per keyword:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(side='left')
        
        self.per_keyword_var = tk.IntVar(value=self.keyword_manager.downloads_per_keyword)
        tk.Spinbox(per_keyword_frame, from_=1, to=50, textvariable=self.per_keyword_var,
                  bg=self.colors["entry_bg"], fg=self.colors["fg"],
                  relief='flat', width=5).pack(side='left', padx=5)
        
        ModernButton(per_keyword_frame, text="Save", 
                    command=self.save_settings,
                    variant="success").pack(side='left', padx=10)
        
        keywords_frame = tk.Frame(self.parent, bg=self.colors["bg"])
        keywords_frame.pack(fill='both', expand=True, pady=10)
        
        list_card = ModernCard(keywords_frame, self.colors)
        list_card.pack(fill='both', expand=True)
        
        list_content = list_card.inner
        
        tk.Label(list_content, text="Your Keywords", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=5)
        
        add_frame = tk.Frame(list_content, bg=self.colors["card_bg"])
        add_frame.pack(fill='x', pady=5)
        
        self.keyword_var = tk.StringVar()
        tk.Entry(add_frame, textvariable=self.keyword_var,
                bg=self.colors["entry_bg"], fg=self.colors["fg"],
                relief='flat', width=30).pack(side='left', padx=5)
        
        ModernButton(add_frame, text="Add Keyword", 
                    command=self.add_keyword,
                    variant="primary").pack(side='left', padx=5)
        
        listbox_frame = tk.Frame(list_content, bg=self.colors["card_bg"])
        listbox_frame.pack(fill='both', expand=True, pady=10)
        
        self.keywords_listbox = tk.Listbox(listbox_frame, height=8,
                                          bg=self.colors["entry_bg"],
                                          fg=self.colors["fg"],
                                          selectbackground=self.colors["accent"],
                                          selectforeground="white",
                                          font=('Segoe UI', 10))
        self.keywords_listbox.pack(side='left', fill='both', expand=True)
        
        scrollbar = tk.Scrollbar(listbox_frame)
        scrollbar.pack(side='right', fill='y')
        self.keywords_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.keywords_listbox.yview)
        
        btn_frame = tk.Frame(list_content, bg=self.colors["card_bg"])
        btn_frame.pack(fill='x', pady=10)
        
        ModernButton(btn_frame, text="Remove Selected", 
                    command=self.remove_keyword,
                    variant="danger").pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="Download All Today", 
                    command=self.download_today,
                    variant="success",
                    icon="📥").pack(side='right', padx=5)
        
        ModernButton(btn_frame, text="Download Now", 
                    command=self.download_now,
                    variant="primary",
                    icon="⚡").pack(side='right', padx=5)
        
        progress_frame = tk.Frame(self.parent, bg=self.colors["bg"])
        progress_frame.pack(fill='x', pady=10)
        
        progress_card = ModernCard(progress_frame, self.colors)
        progress_card.pack(fill='x')
        
        progress_content = progress_card.inner
        
        tk.Label(progress_content, text="Download Progress", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=5)
        
        self.progress_var = tk.StringVar(value="Ready to download")
        tk.Label(progress_content, textvariable=self.progress_var,
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=5)
        
        self.progress_bar = ttk.Progressbar(progress_content, mode='indeterminate')
        self.progress_bar.pack(fill='x', pady=5)
        
        self.stop_btn = ModernButton(progress_content, text="Stop Download", 
                                     command=self.stop_download,
                                     variant="danger",
                                     state='disabled')
        self.stop_btn.pack(pady=5)
        
        self.load_keywords()
    
    def load_keywords(self):
        self.keywords_listbox.delete(0, tk.END)
        for keyword in self.keyword_manager.keywords:
            self.keywords_listbox.insert(tk.END, keyword)
    
    def add_keyword(self):
        keyword = self.keyword_var.get().strip()
        if keyword:
            if self.keyword_manager.add_keyword(keyword):
                self.load_keywords()
                self.keyword_var.set("")
                self.app.status_var.set(f"Added keyword: {keyword}")
            else:
                messagebox.showinfo("Info", "Keyword already exists or invalid")
    
    def remove_keyword(self):
        selection = self.keywords_listbox.curselection()
        if selection:
            keyword = self.keywords_listbox.get(selection[0])
            if self.keyword_manager.remove_keyword(keyword):
                self.load_keywords()
                self.app.status_var.set(f"Removed keyword: {keyword}")
    
    def save_settings(self):
        self.keyword_manager.downloads_per_keyword = self.per_keyword_var.get()
        self.keyword_manager.save_keywords()
        self.app.status_var.set("Settings saved")
    
    def download_today(self):
        keywords = self.keyword_manager.get_keywords_for_download()
        if not keywords:
            messagebox.showinfo("Info", "All keywords have been downloaded today!")
            return
        self.start_download(keywords)
    
    def download_now(self):
        if not self.keyword_manager.keywords:
            messagebox.showinfo("Info", "No keywords to download")
            return
        self.start_download(self.keyword_manager.keywords)
    
    def start_download(self, keywords):
        self.batch_downloader = BatchDownloader(
            self.app.source_manager,
            self.app.changer.config["download_folder"],
            self.app.changer.quota
        )
        self.batch_downloader.progress_callback = self.update_progress
        self.batch_downloader.complete_callback = self.download_complete
        
        self.progress_bar.start()
        self.stop_btn.config(state='normal')
        self.progress_var.set(f"Starting download of {len(keywords)} keywords...")
        
        def download_thread():
            results = self.batch_downloader.download_all(
                keywords, 
                self.keyword_manager.downloads_per_keyword
            )
            
            for keyword in keywords:
                self.keyword_manager.record_download(keyword)
            
            # Check quota after download
            if self.app.changer.quota.enabled:
                used = self.app.changer.quota.get_folder_size_mb()
                max_size = self.app.changer.quota.max_size_mb
                self.app.status_var.set(f"Quota: {used:.1f}MB / {max_size}MB used")
        
        threading.Thread(target=download_thread, daemon=True).start()
    
    def update_progress(self, message):
        self.progress_var.set(message)
        self.app.status_var.set(message)
    
    def download_complete(self, results):
        self.progress_bar.stop()
        self.stop_btn.config(state='disabled')
        
        total = sum(len(paths) for paths in results.values())
        self.progress_var.set(f"Download complete! {total} wallpapers added.")
        self.app.status_var.set(f"Downloaded {total} wallpapers")
        
        self.app.changer.scan_downloaded_wallpapers()
        self.app.update_navigation_display()
        
        # Update quota display
        if self.app.changer.quota.enabled:
            used = self.app.changer.quota.get_folder_size_mb()
            max_size = self.app.changer.quota.max_size_mb
            self.app.status_var.set(f"Downloaded {total} wallpapers - Quota: {used:.1f}MB / {max_size}MB")
    
    def stop_download(self):
        if self.batch_downloader:
            self.batch_downloader.stop_download()
            self.progress_var.set("Download stopped")
            self.progress_bar.stop()
            self.stop_btn.config(state='disabled')

# ============================================================================
# FILTERS TAB
# ============================================================================

class FiltersTab:
    """Filters tab for NSFW/SFW and resolution settings"""
    
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.config = app.changer.config
        
        self.setup_ui()
    
    def setup_ui(self):
        # Purity/Categories card
        purity_card = ModernCard(self.parent, self.colors)
        purity_card.pack(fill='x', pady=5)
        
        content = purity_card.inner
        
        tk.Label(content, text="🔞 Content Filters", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=5)
        
        # Purity (NSFW/SFW)
        purity_frame = tk.Frame(content, bg=self.colors["card_bg"])
        purity_frame.pack(fill='x', pady=5)
        
        tk.Label(purity_frame, text="Content Purity:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        purity_row = tk.Frame(purity_frame, bg=self.colors["card_bg"])
        purity_row.pack(fill='x', pady=5)
        
        self.pur_sfw = tk.BooleanVar(value=self.config["purity"].get("sfw", 1))
        self.pur_sketchy = tk.BooleanVar(value=self.config["purity"].get("sketchy", 0))
        self.pur_nsfw = tk.BooleanVar(value=self.config["purity"].get("nsfw", 0))
        
        tk.Checkbutton(purity_row, text="SFW", variable=self.pur_sfw,
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      selectcolor=self.colors["accent"]).pack(side='left', padx=10)
        tk.Checkbutton(purity_row, text="Sketchy", variable=self.pur_sketchy,
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      selectcolor=self.colors["accent"]).pack(side='left', padx=10)
        tk.Checkbutton(purity_row, text="NSFW", variable=self.pur_nsfw,
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      selectcolor=self.colors["accent"]).pack(side='left', padx=10)
        
        # Categories
        cat_frame = tk.Frame(content, bg=self.colors["card_bg"])
        cat_frame.pack(fill='x', pady=5)
        
        tk.Label(cat_frame, text="Categories:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        cat_row = tk.Frame(cat_frame, bg=self.colors["card_bg"])
        cat_row.pack(fill='x', pady=5)
        
        self.cat_general = tk.BooleanVar(value=self.config["categories"].get("general", 1))
        self.cat_anime = tk.BooleanVar(value=self.config["categories"].get("anime", 1))
        self.cat_people = tk.BooleanVar(value=self.config["categories"].get("people", 1))
        
        tk.Checkbutton(cat_row, text="General", variable=self.cat_general,
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      selectcolor=self.colors["accent"]).pack(side='left', padx=10)
        tk.Checkbutton(cat_row, text="Anime", variable=self.cat_anime,
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      selectcolor=self.colors["accent"]).pack(side='left', padx=10)
        tk.Checkbutton(cat_row, text="People", variable=self.cat_people,
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      selectcolor=self.colors["accent"]).pack(side='left', padx=10)
        
        # Resolution card
        res_card = ModernCard(self.parent, self.colors)
        res_card.pack(fill='x', pady=5)
        
        res_content = res_card.inner
        
        tk.Label(res_content, text="📐 Resolution Settings", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=5)
        
        # Resolution presets
        preset_frame = tk.Frame(res_content, bg=self.colors["card_bg"])
        preset_frame.pack(fill='x', pady=5)
        
        tk.Label(preset_frame, text="Resolution Presets:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w')
        
        preset_row = tk.Frame(preset_frame, bg=self.colors["card_bg"])
        preset_row.pack(fill='x', pady=5)
        
        # Get current preset values
        presets = self.config.get("resolution_presets", {
            "4k": False,
            "2k": False,
            "1080p": True,
            "ultrawide": False
        })
        
        self.res_4k = tk.BooleanVar(value=presets.get("4k", False))
        self.res_2k = tk.BooleanVar(value=presets.get("2k", False))
        self.res_1080p = tk.BooleanVar(value=presets.get("1080p", True))
        self.res_ultrawide = tk.BooleanVar(value=presets.get("ultrawide", False))
        
        tk.Checkbutton(preset_row, text="4K (3840x2160)", variable=self.res_4k,
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      selectcolor=self.colors["accent"]).pack(side='left', padx=10)
        tk.Checkbutton(preset_row, text="2K (2560x1440)", variable=self.res_2k,
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      selectcolor=self.colors["accent"]).pack(side='left', padx=10)
        
        preset_row2 = tk.Frame(preset_frame, bg=self.colors["card_bg"])
        preset_row2.pack(fill='x', pady=5)
        
        tk.Checkbutton(preset_row2, text="1080p (1920x1080)", variable=self.res_1080p,
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      selectcolor=self.colors["accent"]).pack(side='left', padx=10)
        tk.Checkbutton(preset_row2, text="Ultrawide (3440x1440)", variable=self.res_ultrawide,
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      selectcolor=self.colors["accent"]).pack(side='left', padx=10)
        
        # Manual resolutions
        manual_frame = tk.Frame(res_content, bg=self.colors["card_bg"])
        manual_frame.pack(fill='x', pady=5)
        
        tk.Label(manual_frame, text="Custom Resolutions (comma separated):", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w')
        
        resolutions = self.config.get("resolutions", [])
        self.exact_res_var = tk.StringVar(value=", ".join(resolutions))
        tk.Entry(manual_frame, textvariable=self.exact_res_var,
                bg=self.colors["entry_bg"], fg=self.colors["fg"],
                relief='flat', width=40).pack(fill='x', pady=5)
        
        # Aspect ratios
        ratio_frame = tk.Frame(res_content, bg=self.colors["card_bg"])
        ratio_frame.pack(fill='x', pady=5)
        
        tk.Label(ratio_frame, text="Aspect Ratios (comma separated, e.g., 16x9):", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w')
        
        ratios = self.config.get("aspect_ratios", [])
        self.ratio_var = tk.StringVar(value=", ".join(ratios))
        tk.Entry(ratio_frame, textvariable=self.ratio_var,
                bg=self.colors["entry_bg"], fg=self.colors["fg"],
                relief='flat', width=40).pack(fill='x', pady=5)
        
        # Apply button
        ModernButton(self.parent, text="Apply Filters", 
                    command=self.apply_filters,
                    variant="success",
                    icon="✅").pack(pady=10)
    
    def apply_filters(self):
        """Apply filter settings"""
        # Update config
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
        
        # Update resolution presets
        self.config["resolution_presets"] = {
            "4k": self.res_4k.get(),
            "2k": self.res_2k.get(),
            "1080p": self.res_1080p.get(),
            "ultrawide": self.res_ultrawide.get()
        }
        
        # Determine min resolution based on presets
        min_res = "1920x1080"  # Default
        if self.res_4k.get():
            min_res = "3840x2160"
        elif self.res_2k.get():
            min_res = "2560x1440"
        elif self.res_ultrawide.get():
            min_res = "3440x1440"
        elif self.res_1080p.get():
            min_res = "1920x1080"
        
        self.config["min_resolution"] = min_res
        
        if self.exact_res_var.get().strip():
            self.config["resolutions"] = [r.strip() for r in self.exact_res_var.get().split(",")]
        else:
            self.config["resolutions"] = []
        
        if self.ratio_var.get().strip():
            self.config["aspect_ratios"] = [r.strip() for r in self.ratio_var.get().split(",")]
        else:
            self.config["aspect_ratios"] = []
        
        # Save config
        self.app.changer.save_config()
        
        # Update source manager filters
        self.app.source_manager.update_filters({
            "purity": self.config["purity"],
            "categories": self.config["categories"],
            "min_resolution": self.config["min_resolution"],
            "resolutions": self.config["resolutions"],
            "aspect_ratios": self.config["aspect_ratios"]
        })
        
        self.app.status_var.set("Filters applied")

# ============================================================================
# QUOTA TAB
# ============================================================================

class QuotaTab:
    """Disk quota settings tab"""
    
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.config = app.changer.config
        self.quota = app.changer.quota
        
        self.setup_ui()
        self.update_display()
    
    def setup_ui(self):
        tk.Label(self.parent, text="💾 Disk Quota", 
                bg=self.colors["bg"], fg=self.colors["accent"],
                font=('Segoe UI', 16, 'bold')).pack(pady=10)
        
        # Quota card
        quota_card = ModernCard(self.parent, self.colors)
        quota_card.pack(fill='x', padx=20, pady=10)
        
        content = quota_card.inner
        
        # Enable toggle
        toggle_frame = tk.Frame(content, bg=self.colors["card_bg"])
        toggle_frame.pack(fill='x', pady=5)
        
        self.quota_enabled = tk.BooleanVar(value=self.config.get("quota_enabled", True))
        toggle = ModernToggle(toggle_frame, text="Enable Disk Quota", variable=self.quota_enabled)
        toggle.pack(side='left')
        
        # Quota size
        size_frame = tk.Frame(content, bg=self.colors["card_bg"])
        size_frame.pack(fill='x', pady=10)
        
        tk.Label(size_frame, text="Maximum Size (MB):", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(side='left')
        
        self.quota_size = tk.IntVar(value=self.config.get("quota_size", 1000))
        tk.Spinbox(size_frame, from_=50, to=100000, textvariable=self.quota_size,
                  bg=self.colors["entry_bg"], fg=self.colors["fg"],
                  relief='flat', width=8).pack(side='left', padx=5)
        
        tk.Label(size_frame, text="MB (minimum 50)", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 8)).pack(side='left')
        
        # Current usage
        usage_frame = tk.Frame(content, bg=self.colors["card_bg"])
        usage_frame.pack(fill='x', pady=10)
        
        tk.Label(usage_frame, text="Current Usage:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        self.usage_label = tk.Label(usage_frame, text="Calculating...",
                                    bg=self.colors["card_bg"], fg=self.colors["fg"])
        self.usage_label.pack(anchor='w', pady=2)
        
        self.free_label = tk.Label(usage_frame, text="",
                                   bg=self.colors["card_bg"], fg=self.colors["fg"])
        self.free_label.pack(anchor='w', pady=2)
        
        # Progress bar
        self.progress = ttk.Progressbar(usage_frame, length=300, mode='determinate')
        self.progress.pack(fill='x', pady=5)
        
        # Action buttons
        btn_frame = tk.Frame(content, bg=self.colors["card_bg"])
        btn_frame.pack(fill='x', pady=10)
        
        ModernButton(btn_frame, text="Save Settings", 
                    command=self.save_settings,
                    variant="success",
                    icon="💾").pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="Cleanup Old Files", 
                    command=self.cleanup_files,
                    variant="warning",
                    icon="🧹").pack(side='left', padx=5)
        
        ModernButton(btn_frame, text="Refresh", 
                    command=self.update_display,
                    variant="info",
                    icon="🔄").pack(side='left', padx=5)
    
    def update_display(self):
        """Update usage display"""
        try:
            used_mb = self.quota.get_folder_size_mb()
            max_mb = self.quota.max_size_mb
            
            self.usage_label.config(text=f"Used: {used_mb:.2f} MB / {max_mb} MB")
            
            if self.quota.enabled:
                free_mb = max(0, max_mb - used_mb)
                self.free_label.config(text=f"Free: {free_mb:.2f} MB")
                
                # Update progress bar
                percent = min(100, (used_mb / max_mb) * 100)
                self.progress['value'] = percent
            else:
                self.free_label.config(text="Quota disabled")
                self.progress['value'] = 0
            
            # Update every 5 seconds
            self.parent.after(5000, self.update_display)
        except:
            pass
    
    def save_settings(self):
        """Save quota settings"""
        self.config["quota_enabled"] = self.quota_enabled.get()
        self.config["quota_size"] = self.quota_size.get()
        
        # Update quota manager
        self.quota.enabled = self.quota_enabled.get()
        self.quota.max_size_mb = self.quota_size.get()
        self.quota.max_size_bytes = self.quota_size.get() * 1024 * 1024
        
        self.app.changer.save_config()
        self.app.status_var.set("Quota settings saved")
        self.update_display()
    
    def cleanup_files(self):
        """Clean up old files"""
        if messagebox.askyesno("Confirm", "Delete oldest files to free up space?"):
            deleted = self.quota.cleanup_oldest()
            self.app.status_var.set(f"Deleted {deleted} old files")
            self.update_display()
            self.app.changer.scan_downloaded_wallpapers()
            self.app.update_navigation_display()

# ============================================================================
# SCHEDULES TAB
# ============================================================================

class SchedulesTab:
    """Schedules management tab"""
    
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.manager = app.schedule_manager
        
        self.setup_ui()
    
    def setup_ui(self):
        header = tk.Frame(self.parent, bg=self.colors["bg"])
        header.pack(fill='x', pady=10)
        
        tk.Label(header, text="⏰ Wallpaper Schedules", 
                bg=self.colors["bg"], fg=self.colors["accent"],
                font=('Segoe UI', 16, 'bold')).pack(side='left')
        
        ModernButton(header, text="Add Schedule", 
                    command=self.add_schedule,
                    variant="primary",
                    icon="➕").pack(side='right', padx=5)
        
        ModernButton(header, text="Save Schedules", 
                    command=self.save_schedules,
                    variant="success",
                    icon="💾").pack(side='right', padx=5)
        
        canvas = tk.Canvas(self.parent, bg=self.colors["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(self.parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors["bg"])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        for schedule in self.manager.schedules:
            card = ModernCard(scrollable_frame, self.colors)
            card.pack(fill='x', pady=5)
            
            content = card.inner
            
            header_row = tk.Frame(content, bg=self.colors["card_bg"])
            header_row.pack(fill='x')
            
            icons = {"interval": "🔄", "time_of_day": "⏰"}
            icon = icons.get(schedule.schedule_type, "⏰")
            
            tk.Label(header_row, text=f"{icon} {schedule.name}", 
                    bg=self.colors["card_bg"], fg=self.colors["fg"],
                    font=('Segoe UI', 12, 'bold')).pack(side='left')
            
            enabled_var = tk.BooleanVar(value=schedule.enabled)
            toggle = ModernToggle(header_row, variable=enabled_var)
            toggle.pack(side='right')
            
            def update_enabled(s=schedule, var=enabled_var):
                s.enabled = var.get()
                self.manager.save_schedules()
            
            enabled_var.trace('w', lambda *args, s=schedule, var=enabled_var: update_enabled(s, var))
            
            details = tk.Frame(content, bg=self.colors["card_bg"])
            details.pack(fill='x', pady=5)
            
            if schedule.schedule_type == "interval":
                text = f"Every {schedule.interval_value} {schedule.interval_unit}"
            elif schedule.schedule_type == "time_of_day":
                ranges = [f"{start}-{end}" for start, end in schedule.time_ranges]
                text = f"Times: {', '.join(ranges)}"
            else:
                text = f"Tags: {', '.join(schedule.tags[:3])}" if schedule.tags else "No tags"
            
            tk.Label(details, text=text, 
                    bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w')
            
            btn_frame = tk.Frame(content, bg=self.colors["card_bg"])
            btn_frame.pack(fill='x', pady=5)
            
            ModernButton(btn_frame, text="Edit", 
                        command=lambda s=schedule: self.edit_schedule(s),
                        variant="info").pack(side='left', padx=2)
            
            ModernButton(btn_frame, text="Delete", 
                        command=lambda s=schedule: self.delete_schedule(s),
                        variant="danger").pack(side='left', padx=2)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def add_schedule(self):
        name = tk.simpledialog.askstring("New Schedule", "Enter schedule name:")
        if name:
            schedule = Schedule(name)
            self.manager.add_schedule(schedule)
            self.refresh_tab()
    
    def edit_schedule(self, schedule):
        ScheduleEditor(self.app, schedule, self.update_schedule)
    
    def update_schedule(self, schedule):
        self.manager.update_schedule(schedule)
        self.refresh_tab()
    
    def delete_schedule(self, schedule):
        if messagebox.askyesno("Confirm", f"Delete schedule '{schedule.name}'?"):
            self.manager.delete_schedule(schedule)
            self.refresh_tab()
    
    def save_schedules(self):
        self.manager.save_schedules()
        self.app.status_var.set("Schedules saved")
        messagebox.showinfo("Success", "Schedules saved successfully!")
    
    def refresh_tab(self):
        for widget in self.parent.winfo_children():
            widget.destroy()
        self.setup_ui()

# ============================================================================
# EFFECTS TAB
# ============================================================================

class EffectsTab:
    """Wallpaper effects tab"""
    
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.config = app.changer.config
        
        self.setup_ui()
    
    def setup_ui(self):
        card = ModernCard(self.parent, self.colors)
        card.pack(fill='x', pady=10)
        
        content = card.inner
        
        tk.Label(content, text="✨ Wallpaper Effects", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 16, 'bold')).pack(anchor='w', pady=10)
        
        blur_frame = tk.Frame(content, bg=self.colors["card_bg"])
        blur_frame.pack(fill='x', pady=10)
        
        self.blur_var = tk.IntVar(value=self.config.get("blur_amount", 0))
        slider = ModernSlider(blur_frame, text="Blur Amount:", from_=0, to=20,
                             variable=self.blur_var)
        slider.pack(fill='x')
        
        darken_frame = tk.Frame(content, bg=self.colors["card_bg"])
        darken_frame.pack(fill='x', pady=10)
        
        self.darken_var = tk.IntVar(value=self.config.get("darken_amount", 0))
        slider2 = ModernSlider(darken_frame, text="Darken Amount:", from_=0, to=100,
                              variable=self.darken_var)
        slider2.pack(fill='x')
        
        ModernButton(content, text="Apply Effects", 
                    command=self.apply_effects_preview,
                    variant="primary",
                    icon="✨").pack(pady=20)
    
    def apply_effects_preview(self):
        if self.app.changer.current_wallpaper:
            blur = self.blur_var.get()
            darken = self.darken_var.get() / 100.0
            
            result = WallpaperEffects.apply_effects(self.app.changer.current_wallpaper, blur, darken)
            os.startfile(result)
            self.app.status_var.set("Effects preview generated")

# ============================================================================
# SHORTCUTS TAB
# ============================================================================

class ShortcutsTab:
    """Keyboard shortcuts settings tab"""
    
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.shortcut_manager = app.shortcut_manager
        
        self.setup_ui()
    
    def setup_ui(self):
        tk.Label(self.parent, text="⌨️ Keyboard Shortcuts", 
                bg=self.colors["bg"], fg=self.colors["accent"],
                font=('Segoe UI', 16, 'bold')).pack(pady=10)
        
        card = ModernCard(self.parent, self.colors)
        card.pack(fill='x', padx=20, pady=10)
        
        content = card.inner
        
        # Next wallpaper
        next_frame = tk.Frame(content, bg=self.colors["card_bg"])
        next_frame.pack(fill='x', pady=10)
        
        tk.Label(next_frame, text="Next Wallpaper:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        next_row = tk.Frame(next_frame, bg=self.colors["card_bg"])
        next_row.pack(fill='x', pady=5)
        
        self.next_shortcut = tk.StringVar(value=self.app.changer.config.get("shortcuts", {}).get("next", "ctrl+alt+right"))
        tk.Entry(next_row, textvariable=self.next_shortcut,
                bg=self.colors["entry_bg"], fg=self.colors["fg"],
                relief='flat', width=30).pack(side='left', padx=5)
        
        tk.Label(next_row, text="Example: ctrl+alt+right", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 8)).pack(side='left', padx=5)
        
        # Previous wallpaper
        prev_frame = tk.Frame(content, bg=self.colors["card_bg"])
        prev_frame.pack(fill='x', pady=10)
        
        tk.Label(prev_frame, text="Previous Wallpaper:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        prev_row = tk.Frame(prev_frame, bg=self.colors["card_bg"])
        prev_row.pack(fill='x', pady=5)
        
        self.prev_shortcut = tk.StringVar(value=self.app.changer.config.get("shortcuts", {}).get("previous", "ctrl+alt+left"))
        tk.Entry(prev_row, textvariable=self.prev_shortcut,
                bg=self.colors["entry_bg"], fg=self.colors["fg"],
                relief='flat', width=30).pack(side='left', padx=5)
        
        tk.Label(prev_row, text="Example: ctrl+alt+left", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 8)).pack(side='left', padx=5)
        
        # Delete wallpaper
        delete_frame = tk.Frame(content, bg=self.colors["card_bg"])
        delete_frame.pack(fill='x', pady=10)
        
        tk.Label(delete_frame, text="Delete Current:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        delete_row = tk.Frame(delete_frame, bg=self.colors["card_bg"])
        delete_row.pack(fill='x', pady=5)
        
        self.delete_shortcut = tk.StringVar(value=self.app.changer.config.get("shortcuts", {}).get("delete", "ctrl+alt+del"))
        tk.Entry(delete_row, textvariable=self.delete_shortcut,
                bg=self.colors["entry_bg"], fg=self.colors["fg"],
                relief='flat', width=30).pack(side='left', padx=5)
        
        tk.Label(delete_row, text="Example: ctrl+alt+del", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 8)).pack(side='left', padx=5)
        
        # Save button
        ModernButton(self.parent, text="Save Shortcuts", 
                    command=self.save_shortcuts,
                    variant="success",
                    icon="💾").pack(pady=20)
        
        # Current shortcuts display
        current_frame = tk.Frame(self.parent, bg=self.colors["bg"])
        current_frame.pack(fill='x', pady=10)
        
        current_card = ModernCard(current_frame, self.colors)
        current_card.pack(fill='x')
        
        current_content = current_card.inner
        
        tk.Label(current_content, text="Active Shortcuts:", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=5)
        
        shortcuts = self.app.changer.config.get("shortcuts", {})
        
        tk.Label(current_content, text=f"Next: {shortcuts.get('next', 'Not set')}", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=2)
        
        tk.Label(current_content, text=f"Previous: {shortcuts.get('previous', 'Not set')}", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=2)
        
        tk.Label(current_content, text=f"Delete: {shortcuts.get('delete', 'Not set')}", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=2)
    
    def save_shortcuts(self):
        """Save shortcut settings"""
        new_shortcuts = {
            "next": self.next_shortcut.get(),
            "previous": self.prev_shortcut.get(),
            "delete": self.delete_shortcut.get()
        }
        
        self.shortcut_manager.update_shortcuts(new_shortcuts)
        self.app.status_var.set("Shortcuts saved")
        messagebox.showinfo("Success", "Keyboard shortcuts saved! They will take effect immediately.")

# ============================================================================
# FAVORITES FOLDER TAB
# ============================================================================

class FavoritesFolderTab:
    """Favorites folder management tab"""
    
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.manager = app.changer.favorites_folder_manager
        
        self.setup_ui()
    
    def setup_ui(self):
        tk.Label(self.parent, text="📁 Favorites Folder", 
                bg=self.colors["bg"], fg=self.colors["accent"],
                font=('Segoe UI', 16, 'bold')).pack(pady=10)
        
        card = ModernCard(self.parent, self.colors)
        card.pack(fill='x', padx=20, pady=10)
        
        content = card.inner
        
        # Folder path
        path_frame = tk.Frame(content, bg=self.colors["card_bg"])
        path_frame.pack(fill='x', pady=10)
        
        tk.Label(path_frame, text="Folder Location:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        path_row = tk.Frame(path_frame, bg=self.colors["card_bg"])
        path_row.pack(fill='x', pady=5)
        
        self.path_var = tk.StringVar(value=self.manager.favorites_folder)
        tk.Entry(path_row, textvariable=self.path_var,
                bg=self.colors["entry_bg"], fg=self.colors["fg"],
                relief='flat', width=50).pack(side='left', padx=5, fill='x', expand=True)
        
        ModernButton(path_row, text="Browse", 
                    command=self.browse_folder,
                    variant="info").pack(side='right', padx=2)
        
        ModernButton(path_row, text="Open", 
                    command=self.open_folder,
                    variant="secondary").pack(side='right', padx=2)
        
        # Copy toggle
        toggle_frame = tk.Frame(content, bg=self.colors["card_bg"])
        toggle_frame.pack(fill='x', pady=10)
        
        self.copy_var = tk.BooleanVar(value=self.manager.copy_enabled)
        toggle = ModernToggle(toggle_frame, text="Copy to favorites folder when favoriting", 
                             variable=self.copy_var)
        toggle.pack(side='left')
        
        self.copy_var.trace('w', lambda *args: self.toggle_copy())
        
        # Stats
        stats_frame = tk.Frame(content, bg=self.colors["card_bg"])
        stats_frame.pack(fill='x', pady=10)
        
        tk.Label(stats_frame, text="Folder Statistics:", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        self.update_stats()
        
        # Action buttons
        btn_frame = tk.Frame(content, bg=self.colors["card_bg"])
        btn_frame.pack(fill='x', pady=10)
        
        ModernButton(btn_frame, text="Browse Favorites", 
                    command=self.browse_favorites,
                    variant="primary",
                    icon="📂").pack(side='left', padx=2)
        
        ModernButton(btn_frame, text="Save Settings", 
                    command=self.save_settings,
                    variant="success",
                    icon="💾").pack(side='left', padx=2)
        
        ModernButton(btn_frame, text="Refresh Stats", 
                    command=self.update_stats,
                    variant="info",
                    icon="🔄").pack(side='left', padx=2)
    
    def update_stats(self):
        """Update folder statistics"""
        stats_frame = None
        for widget in self.parent.winfo_children():
            if isinstance(widget, tk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, ModernCard):
                        for inner in child.inner.winfo_children():
                            if isinstance(inner, tk.Frame) and inner.winfo_children():
                                if inner.winfo_children()[0].cget("text") == "Folder Statistics":
                                    stats_frame = inner
                                    break
        
        if stats_frame:
            # Clear old stats
            for widget in stats_frame.winfo_children()[1:]:
                widget.destroy()
            
            # Get stats
            favorites = self.manager.get_all_favorites()
            total = len(favorites)
            size_mb = sum(f['size'] for f in favorites) / (1024 * 1024)
            
            # Show stats
            tk.Label(stats_frame, text=f"Total files: {total}", 
                    bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=2)
            tk.Label(stats_frame, text=f"Total size: {size_mb:.2f} MB", 
                    bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=2)
    
    def browse_folder(self):
        """Browse for new favorites folder"""
        folder = filedialog.askdirectory(
            title="Select Favorites Folder",
            initialdir=self.manager.favorites_folder
        )
        if folder:
            self.path_var.set(folder)
            self.manager.set_favorites_folder(folder)
            self.update_stats()
            self.app.status_var.set(f"Favorites folder changed to: {folder}")
    
    def open_folder(self):
        """Open the favorites folder in explorer"""
        if os.path.exists(self.manager.favorites_folder):
            os.startfile(self.manager.favorites_folder)
    
    def toggle_copy(self):
        """Toggle copy setting"""
        self.manager.toggle_copy(self.copy_var.get())
    
    def save_settings(self):
        """Save folder settings"""
        if self.path_var.get() != self.manager.favorites_folder:
            self.manager.set_favorites_folder(self.path_var.get())
        self.manager.toggle_copy(self.copy_var.get())
        self.app.changer.save_config()
        self.app.status_var.set("Favorites folder settings saved")
    
    def browse_favorites(self):
        """Open the favorites folder browser"""
        FavoritesFolderBrowser(self.app, self.app)

# ============================================================================
# SETTINGS TAB
# ============================================================================

class SettingsTab:
    """Settings tab with API key management and startup options"""
    
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.colors = app.colors
        self.config = app.changer.config
        
        self.setup_ui()
    
    def setup_ui(self):
        card = ModernCard(self.parent, self.colors)
        card.pack(fill='x', pady=10)
        
        content = card.inner
        
        tk.Label(content, text="⚙️ Settings", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 16, 'bold')).pack(anchor='w', pady=10)
        
        # API Key with Add/Delete buttons
        api_frame = tk.Frame(content, bg=self.colors["card_bg"])
        api_frame.pack(fill='x', pady=10)
        
        tk.Label(api_frame, text="Wallhaven API Key:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        api_row = tk.Frame(api_frame, bg=self.colors["card_bg"])
        api_row.pack(fill='x', pady=5)
        
        self.api_key_var = tk.StringVar(value=self.config.get("api_key", ""))
        api_entry = tk.Entry(api_row, textvariable=self.api_key_var,
                             bg=self.colors["entry_bg"], fg=self.colors["fg"],
                             relief='flat', width=40, show="*")
        api_entry.pack(side='left', padx=5, fill='x', expand=True)
        
        # Add/Save button
        ModernButton(api_row, text="➕ Add/Save", 
                    command=self.save_api_key,
                    variant="success",
                    icon="💾").pack(side='left', padx=2)
        
        # Delete button
        ModernButton(api_row, text="🗑️ Delete", 
                    command=self.delete_api_key,
                    variant="danger",
                    icon="❌").pack(side='left', padx=2)
        
        # Show/Hide toggle
        self.show_api_key = tk.BooleanVar(value=False)
        def toggle_api_key():
            api_entry.config(show="" if self.show_api_key.get() else "*")
        
        tk.Checkbutton(api_row, text="Show", variable=self.show_api_key,
                      command=toggle_api_key,
                      bg=self.colors["card_bg"], fg=self.colors["fg"],
                      selectcolor=self.colors["accent"]).pack(side='left', padx=2)
        
        # API Status
        status_row = tk.Frame(api_frame, bg=self.colors["card_bg"])
        status_row.pack(fill='x', pady=5)
        
        tk.Label(status_row, text="Status:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(side='left')
        
        self.api_status_label = tk.Label(status_row, text="Not checked",
                                         bg=self.colors["card_bg"], fg=self.colors["warning"])
        self.api_status_label.pack(side='left', padx=5)
        
        ModernButton(status_row, text="Check Now", 
                    command=self.check_api_status,
                    variant="info").pack(side='left', padx=5)
        
        # Startup option
        startup_frame = tk.Frame(content, bg=self.colors["card_bg"])
        startup_frame.pack(fill='x', pady=15)
        
        tk.Label(startup_frame, text="Startup Options:", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=5)
        
        self.change_on_startup = tk.BooleanVar(value=self.config.get("change_on_startup", True))
        toggle = ModernToggle(startup_frame, text="Change wallpaper when app starts", 
                             variable=self.change_on_startup)
        toggle.pack(anchor='w')
        
        tk.Label(startup_frame, text="(If disabled, last wallpaper will be shown)", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 9)).pack(anchor='w', padx=(30,0), pady=2)
        
        # Download folder
        folder_frame = tk.Frame(content, bg=self.colors["card_bg"])
        folder_frame.pack(fill='x', pady=10)
        
        tk.Label(folder_frame, text="Download Folder:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        folder_row = tk.Frame(folder_frame, bg=self.colors["card_bg"])
        folder_row.pack(fill='x', pady=5)
        
        self.folder_var = tk.StringVar()
        tk.Entry(folder_row, textvariable=self.folder_var,
                bg=self.colors["entry_bg"], fg=self.colors["fg"],
                relief='flat', width=50, font=('Segoe UI', 9)).pack(side='left', padx=5, fill='x', expand=True)
        
        ModernButton(folder_row, text="Browse", 
                    command=self.browse_folder,
                    variant="info",
                    icon="📁").pack(side='right')
        
        # Interval
        interval_frame = tk.Frame(content, bg=self.colors["card_bg"])
        interval_frame.pack(fill='x', pady=10)
        
        tk.Label(interval_frame, text="Change Interval:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        interval_row = tk.Frame(interval_frame, bg=self.colors["card_bg"])
        interval_row.pack(fill='x', pady=5)
        
        self.interval_value_var = tk.IntVar(value=self.config.get("interval_value", 30))
        tk.Spinbox(interval_row, from_=1, to=999, 
                  textvariable=self.interval_value_var,
                  bg=self.colors["entry_bg"], fg=self.colors["fg"],
                  relief='flat', width=8, font=('Segoe UI', 9)).pack(side='left', padx=5)
        
        self.interval_unit_var = tk.StringVar(value=self.config.get("interval_unit", "minutes"))
        ttk.Combobox(interval_row, textvariable=self.interval_unit_var,
                    values=["minutes", "hours", "days"],
                    state="readonly", width=10, font=('Segoe UI', 9)).pack(side='left', padx=5)
        
        # Options
        options_frame = tk.Frame(content, bg=self.colors["card_bg"])
        options_frame.pack(fill='x', pady=10)
        
        tk.Label(options_frame, text="Options:", 
                bg=self.colors["card_bg"], fg=self.colors["fg"],
                font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        
        toggles = [
            ("Show notifications", "notifications_var"),
            ("Remember last wallpaper", "remember_last_var"),
            ("Random order", "random_order_var")
        ]
        
        for text, attr in toggles:
            var_name = attr
            if not hasattr(self.app, var_name):
                setattr(self.app, var_name, tk.BooleanVar(value=self.config.get(var_name.replace('_var', ''), False)))
            
            toggle_row = tk.Frame(options_frame, bg=self.colors["card_bg"])
            toggle_row.pack(fill='x', pady=2)
            
            var = getattr(self.app, var_name)
            toggle = ModernToggle(toggle_row, text=text, variable=var)
            toggle.pack(side='left')
        
        # Save All Settings button
        ModernButton(self.parent, text="Save All Settings", 
                    command=self.save_all_settings,
                    variant="success",
                    icon="💾").pack(pady=20)
    
    def save_api_key(self):
        """Save the API key"""
        self.config["api_key"] = self.api_key_var.get().strip()
        self.app.changer.save_config()
        
        # Update source manager
        self.app.source_manager.api_key = self.config["api_key"]
        self.app.source_manager.source.api_key = self.config["api_key"]
        
        self.app.status_var.set("API Key saved")
        self.check_api_status()
    
    def delete_api_key(self):
        """Delete the API key"""
        if messagebox.askyesno("Confirm", "Delete API key?"):
            self.api_key_var.set("")
            self.config["api_key"] = ""
            self.app.changer.save_config()
            
            # Update source manager
            self.app.source_manager.api_key = ""
            self.app.source_manager.source.api_key = ""
            
            self.app.status_var.set("API Key deleted")
            self.api_status_label.config(text="Not configured", fg=self.colors["warning"])
    
    def check_api_status(self):
        """Check API status"""
        def do_check():
            api_key = self.api_key_var.get()
            status, message = APIStatusChecker.check_wallhaven(api_key)
            
            if status:
                self.parent.after(0, lambda: self.api_status_label.config(
                    text="✓ Connected", fg=self.colors["success"]))
            else:
                self.parent.after(0, lambda: self.api_status_label.config(
                    text=f"✗ {message}", fg=self.colors["error"]))
        
        threading.Thread(target=do_check, daemon=True).start()
    
    def browse_folder(self):
        """Browse for download folder"""
        folder = filedialog.askdirectory(
            title="Select Download Folder",
            initialdir=self.folder_var.get() or os.path.expanduser("~")
        )
        if folder:
            self.folder_var.set(folder)
    
    def save_all_settings(self):
        """Save all settings"""
        self.config["download_folder"] = self.folder_var.get().strip()
        self.config["interval_value"] = self.interval_value_var.get()
        self.config["interval_unit"] = self.interval_unit_var.get()
        self.config["change_on_startup"] = self.change_on_startup.get()
        
        if hasattr(self.app, 'notifications_var'):
            self.config["notifications"] = self.app.notifications_var.get()
        if hasattr(self.app, 'remember_last_var'):
            self.config["remember_last_wallpaper"] = self.app.remember_last_var.get()
        if hasattr(self.app, 'random_order_var'):
            self.config["random_order"] = self.app.random_order_var.get()
        
        self.app.changer.save_config()
        
        self.app.status_var.set("All settings saved")
        messagebox.showinfo("Success", "Settings saved successfully!")

# ============================================================================
# MODERN MAIN APPLICATION
# ============================================================================

class ModernWallpaperChangerApp:
    def __init__(self):
        self.changer = WallpaperChanger()
        self.source_manager = SourceManager(
            self.changer.config.get("api_key", ""),
            {
                "purity": self.changer.config.get("purity", {"sfw": 1, "sketchy": 0, "nsfw": 0}),
                "categories": self.changer.config.get("categories", {"general": 1, "anime": 1, "people": 1}),
                "min_resolution": self.changer.config.get("min_resolution", "1920x1080"),
                "resolutions": self.changer.config.get("resolutions", []),
                "aspect_ratios": self.changer.config.get("aspect_ratios", [])
            }
        )
        self.schedule_manager = ScheduleManager()
        self.keyword_manager = KeywordManager()
        self.shortcut_manager = ShortcutManager(self)
        self.current_scheme = self.changer.config.get("theme", "light")
        
        if self.current_scheme not in COLOR_SCHEMES:
            self.current_scheme = "light"
        
        self.colors = COLOR_SCHEMES[self.current_scheme]
        
        self.root = tk.Tk()
        self.root.title("Wallpaper Changer")
        self.root.geometry("1000x900+100+100")
        self.root.configure(bg=self.colors["bg"])
        
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        
        self.setup_ui()
        self.load_config_to_ui()
        
        # Change wallpaper on startup if enabled
        if self.changer.config.get("change_on_startup", True):
            self.root.after(100, self.change_on_startup)
        else:
            self.root.after(100, self.load_initial_preview)
        
        self.tray = SystemTray(self.changer, self)
        self.tray.run()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def change_on_startup(self):
        """Change wallpaper on app startup"""
        self.status_var.set("Getting new wallpaper...")
        
        def do_change():
            tags = []  # No schedule tags for now
            
            images = self.source_manager.get_images(1, tags=tags if tags else None)
            
            if images:
                img = images[0]
                try:
                    # Check quota before downloading
                    if not self.changer.quota.can_download(5):  # Assume 5MB
                        self.root.after(0, lambda: self.status_var.set("Quota exceeded - cannot download"))
                        self.load_initial_preview()
                        return
                    
                    response = requests.get(img['download_url'], timeout=30)
                    file_ext = os.path.splitext(img['download_url'])[1] or '.jpg'
                    if '?' in file_ext:
                        file_ext = '.jpg'
                    filename = f"{img['source']}_{img['id']}{file_ext}"
                    save_path = os.path.join(self.changer.config["download_folder"], filename)
                    
                    print(f"Saving to: {save_path}")  # Debug print
                    
                    with open(save_path, 'wb') as f:
                        f.write(response.content)
                    
                    self.changer.set_wallpaper(save_path, img['id'], "static")
                    self.root.after(0, lambda: self.change_done(True))
                except Exception as e:
                    print(f"Error downloading: {e}")
                    self.root.after(0, lambda: self.load_initial_preview())
            else:
                self.root.after(0, lambda: self.load_initial_preview())
        
        threading.Thread(target=do_change, daemon=True).start()
    
    def change_done(self, success):
        """Called when wallpaper change is complete"""
        if success:
            self.status_var.set("Wallpaper changed successfully")
            # Scan the folder to update the list
            self.changer.scan_downloaded_wallpapers()
            self.update_preview()
            self.update_favorite_status()
            self.update_type_label()
            self.update_navigation_display()
            print(f"Current download folder: {self.changer.config['download_folder']}")
        else:
            self.status_var.set("Failed to change wallpaper")
            messagebox.showerror("Error", "Failed to download or set wallpaper")
    
    def setup_ui(self):
        header = tk.Frame(self.root, bg=self.colors["accent"], height=70)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        title_frame = tk.Frame(header, bg=self.colors["accent"])
        title_frame.pack(side='left', padx=25)
        
        tk.Label(title_frame, text="🎨", bg=self.colors["accent"], fg="white",
                font=('Segoe UI', 24)).pack(side='left')
        
        tk.Label(title_frame, text="Wallpaper Changer", 
                bg=self.colors["accent"], fg="white",
                font=('Segoe UI', 20, 'bold')).pack(side='left', padx=(10,0))
        
        header_buttons = tk.Frame(header, bg=self.colors["accent"])
        header_buttons.pack(side='right', padx=20)
        
        theme_btn = ModernButton(header_buttons, text="Theme", 
                                 command=self.toggle_theme,
                                 variant="secondary")
        theme_btn.pack(side='left', padx=5)
        
        main_container = tk.Frame(self.root, bg=self.colors["bg"])
        main_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        self.notebook = ttk.Notebook(main_container)
        self.notebook.pack(fill='both', expand=True)
        
        style = ttk.Style()
        style.configure('TNotebook', background=self.colors["bg"], borderwidth=0)
        style.configure('TNotebook.Tab', 
                       background=self.colors["card_bg"],
                       foreground=self.colors["fg"],
                       padding=[20, 10],
                       borderwidth=0,
                       font=('Segoe UI', 10))
        style.map('TNotebook.Tab',
                 background=[('selected', self.colors["accent"]),
                            ('active', self.colors["accent_light"])],
                 foreground=[('selected', '#ffffff'),
                            ('active', self.colors["fg"])])
        
        dashboard_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(dashboard_frame, text="🏠 Dashboard")
        self.setup_dashboard_tab(dashboard_frame)
        
        filters_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(filters_frame, text="🔞 Filters")
        self.filters_tab = FiltersTab(filters_frame, self)
        
        keywords_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(keywords_frame, text="🔑 Keywords")
        self.keywords_tab = KeywordsTab(keywords_frame, self)
        
        favorites_folder_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(favorites_folder_frame, text="📁 Favorites")
        self.favorites_folder_tab = FavoritesFolderTab(favorites_folder_frame, self)
        
        schedules_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(schedules_frame, text="⏰ Schedules")
        self.schedules_tab = SchedulesTab(schedules_frame, self)
        
        quota_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(quota_frame, text="💾 Quota")
        self.quota_tab = QuotaTab(quota_frame, self)
        
        effects_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(effects_frame, text="✨ Effects")
        self.effects_tab = EffectsTab(effects_frame, self)
        
        shortcuts_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(shortcuts_frame, text="⌨️ Shortcuts")
        self.shortcuts_tab = ShortcutsTab(shortcuts_frame, self)
        
        settings_frame = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(settings_frame, text="⚙️ Settings")
        self.settings_tab = SettingsTab(settings_frame, self)
        
        status_bar = tk.Frame(self.root, bg=self.colors["accent"], height=30)
        status_bar.pack(fill='x', side='bottom')
        status_bar.pack_propagate(False)
        
        status_label = tk.Label(status_bar, textvariable=self.status_var,
                               bg=self.colors["accent"], fg="white",
                               anchor='w', padx=20, font=('Segoe UI', 9))
        status_label.pack(fill='both', expand=True)
    
    def setup_dashboard_tab(self, parent):
        current_card = ModernCard(parent, self.colors)
        current_card.pack(fill='x', pady=10)
        
        content = current_card.inner
        
        tk.Label(content, text="Current Wallpaper", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        
        preview_container = tk.Frame(content, bg=self.colors["card_bg"])
        preview_container.pack(fill='both', expand=True, pady=15)
        
        self.preview_label = tk.Label(preview_container, text="No wallpaper selected",
                                      bg=self.colors["card_bg"],
                                      fg=self.colors["fg"])
        self.preview_label.pack()
        
        nav_frame = tk.Frame(content, bg=self.colors["card_bg"])
        nav_frame.pack(fill='x', pady=10)
        
        self.prev_btn = ModernButton(nav_frame, text="◀ Previous", 
                                     command=self.previous_wallpaper,
                                     variant="info")
        self.prev_btn.pack(side='left', padx=5)
        
        self.next_btn = ModernButton(nav_frame, text="Next ▶", 
                                     command=self.next_wallpaper,
                                     variant="info")
        self.next_btn.pack(side='left', padx=5)
        
        self.delete_btn = ModernButton(nav_frame, text="🗑️ Delete", 
                                       command=self.delete_current_wallpaper,
                                       variant="danger")
        self.delete_btn.pack(side='left', padx=5)
        
        self.nav_label = tk.Label(nav_frame, text="0/0",
                                  bg=self.colors["card_bg"],
                                  fg=self.colors["accent"],
                                  font=('Segoe UI', 10, 'bold'))
        self.nav_label.pack(side='left', padx=10)
        
        ModernButton(nav_frame, text="🔄 Scan Folder", 
                    command=self.scan_folder,
                    variant="secondary").pack(side='left', padx=5)
        
        info_container = tk.Frame(content, bg=self.colors["card_bg"])
        info_container.pack(fill='x', pady=10)
        
        self.fav_status_var = tk.StringVar(value="☆ Not favorited")
        fav_status = tk.Label(info_container, textvariable=self.fav_status_var,
                             bg=self.colors["card_bg"], fg=self.colors["fg"])
        fav_status.pack(side='left', padx=5)
        
        self.type_label = tk.Label(info_container, text="🖼️ Static", 
                                   bg=self.colors["card_bg"],
                                   fg=self.colors["accent"],
                                   font=('Segoe UI', 9, 'bold'))
        self.type_label.pack(side='left', padx=20)
        
        controls = tk.Frame(content, bg=self.colors["card_bg"])
        controls.pack(fill='x', pady=10)
        
        ModernButton(controls, text="Favorite", 
                    command=self.toggle_favorite,
                    variant="warning",
                    icon="❤️").pack(side='left', padx=5)
        
        ModernButton(controls, text="Preview", 
                    command=self.preview_current,
                    variant="info",
                    icon="👁️").pack(side='left', padx=5)
        
        columns = tk.Frame(parent, bg=self.colors["bg"])
        columns.pack(fill='both', expand=True, pady=10)
        
        left_col = tk.Frame(columns, bg=self.colors["bg"], width=300)
        left_col.pack(side='left', fill='both', expand=True, padx=(0, 10))
        left_col.pack_propagate(False)
        
        # Quota info card
        quota_card = ModernCard(left_col, self.colors)
        quota_card.pack(fill='x')
        
        qc_content = quota_card.inner
        tk.Label(qc_content, text="💾 Disk Quota", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        
        self.quota_usage_label = tk.Label(qc_content, text="Loading...",
                                          bg=self.colors["card_bg"], fg=self.colors["fg"])
        self.quota_usage_label.pack(anchor='w', pady=5)
        
        self.quota_progress = ttk.Progressbar(qc_content, length=250, mode='determinate')
        self.quota_progress.pack(fill='x', pady=5)
        
        # Update quota display
        self.update_quota_display()
        
        # Schedule info card
        schedule_card = ModernCard(left_col, self.colors)
        schedule_card.pack(fill='x', pady=10)
        
        sc_content = schedule_card.inner
        tk.Label(sc_content, text="⏰ Active Schedule", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        
        self.schedule_name_label = tk.Label(sc_content, text="No active schedule",
                                           bg=self.colors["card_bg"], fg=self.colors["fg"])
        self.schedule_name_label.pack(anchor='w', pady=5)
        
        # Favorites folder info card
        fav_folder_card = ModernCard(left_col, self.colors)
        fav_folder_card.pack(fill='x', pady=10)
        
        fc_content = fav_folder_card.inner
        tk.Label(fc_content, text="📁 Favorites Folder", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        
        self.fav_folder_status = tk.Label(fc_content, text="Loading...",
                                          bg=self.colors["card_bg"], fg=self.colors["fg"])
        self.fav_folder_status.pack(anchor='w', pady=5)
        
        ModernButton(fc_content, text="Browse", 
                    command=self.browse_favorites_folder,
                    variant="info").pack(anchor='w', pady=5)
        
        self.update_favorites_folder_info()
        
        # Shortcuts info card
        shortcuts_card = ModernCard(left_col, self.colors)
        shortcuts_card.pack(fill='x', pady=10)
        
        sc_content = shortcuts_card.inner
        tk.Label(sc_content, text="⌨️ Active Shortcuts", 
                bg=self.colors["card_bg"], fg=self.colors["accent"],
                font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        
        shortcuts = self.changer.config.get("shortcuts", {})
        tk.Label(sc_content, text=f"Next: {shortcuts.get('next', 'Not set')}", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=2)
        tk.Label(sc_content, text=f"Previous: {shortcuts.get('previous', 'Not set')}", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=2)
        tk.Label(sc_content, text=f"Delete: {shortcuts.get('delete', 'Not set')}", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack(anchor='w', pady=2)
        
        # Right column - empty now (recent wallpapers removed)
        right_col = tk.Frame(columns, bg=self.colors["bg"])
        right_col.pack(side='right', fill='both', expand=True)
        
        # Just a placeholder to maintain layout balance
        placeholder_card = ModernCard(right_col, self.colors)
        placeholder_card.pack(fill='both', expand=True)
        
        placeholder_content = placeholder_card.inner
        tk.Label(placeholder_content, text="", 
                bg=self.colors["card_bg"], fg=self.colors["fg"]).pack()
        
        self.update_navigation_display()
    
    def update_favorites_folder_info(self):
        """Update favorites folder info in dashboard"""
        try:
            favorites = self.changer.favorites_folder_manager.get_all_favorites()
            total = len(favorites)
            folder = self.changer.favorites_folder_manager.favorites_folder
            
            self.fav_folder_status.config(text=f"Folder: {os.path.basename(folder)}\n{total} files")
            
            # Update every 5 seconds
            self.root.after(5000, self.update_favorites_folder_info)
        except:
            pass
    
    def browse_favorites_folder(self):
        """Open the favorites folder browser"""
        FavoritesFolderBrowser(self, self)
    
    def update_quota_display(self):
        """Update quota display in dashboard"""
        try:
            used_mb = self.changer.quota.get_folder_size_mb()
            max_mb = self.changer.quota.max_size_mb
            
            if self.changer.quota.enabled:
                self.quota_usage_label.config(text=f"Used: {used_mb:.1f}MB / {max_mb}MB")
                percent = min(100, (used_mb / max_mb) * 100)
                self.quota_progress['value'] = percent
            else:
                self.quota_usage_label.config(text="Quota disabled")
                self.quota_progress['value'] = 0
            
            # Update every 5 seconds
            self.root.after(5000, self.update_quota_display)
        except:
            pass
    
    def update_navigation_display(self):
        current, total = self.changer.get_navigation_info()
        self.nav_label.config(text=f"{current}/{total}")
        
        if current <= 1:
            self.prev_btn.config(state='disabled')
        else:
            self.prev_btn.config(state='normal')
        
        if current >= total or total == 0:
            self.next_btn.config(state='disabled')
        else:
            self.next_btn.config(state='normal')
    
    def next_wallpaper(self):
        if self.changer.next_wallpaper():
            self.update_preview()
            self.update_favorite_status()
            self.update_type_label()
            self.update_navigation_display()
            self.status_var.set("Next wallpaper")
    
    def previous_wallpaper(self):
        if self.changer.previous_wallpaper():
            self.update_preview()
            self.update_favorite_status()
            self.update_type_label()
            self.update_navigation_display()
            self.status_var.set("Previous wallpaper")
    
    def delete_current_wallpaper(self):
        success, message = self.changer.delete_current_wallpaper()
        if success:
            self.update_preview()
            self.update_favorite_status()
            self.update_type_label()
            self.update_navigation_display()
        self.status_var.set(message)
    
    def scan_folder(self):
        self.changer.scan_downloaded_wallpapers()
        self.update_navigation_display()
        self.status_var.set("Folder scanned")
    
    def check_api_status(self):
        """Check API status from settings tab"""
        self.settings_tab.check_api_status()
    
    def save_api_key(self):
        """Save API key from settings tab"""
        self.settings_tab.save_api_key()
    
    def delete_api_key(self):
        """Delete API key from settings tab"""
        self.settings_tab.delete_api_key()
    
    def toggle_favorite(self):
        success, message = self.changer.toggle_favorite_current()
        self.status_var.set(message)
        self.update_favorite_status()
    
    def update_favorite_status(self):
        if self.changer.current_wallpaper_id and self.changer.db.is_favorite(self.changer.current_wallpaper_id):
            self.fav_status_var.set("❤️ In favorites")
        else:
            self.fav_status_var.set("☆ Not favorited")
    
    def update_type_label(self):
        type_icons = {
            "static": "🖼️ Static",
            "gif": "🎬 GIF",
            "video": "🎥 Video"
        }
        self.type_label.config(text=type_icons.get(self.changer.current_wallpaper_type, "🖼️ Static"))
    
    def update_preview(self):
        if self.changer.current_wallpaper and os.path.exists(self.changer.current_wallpaper):
            try:
                if self.changer.current_wallpaper.lower().endswith('.gif'):
                    img = Image.open(self.changer.current_wallpaper)
                    img.seek(0)
                    img.thumbnail((500, 300))
                else:
                    img = Image.open(self.changer.current_wallpaper)
                    img.thumbnail((500, 300))
                
                photo = ImageTk.PhotoImage(img)
                self.preview_label.config(image=photo, text="")
                self.preview_label.image = photo
            except:
                self.preview_label.config(image="", text="Preview not available")
    
    def preview_current(self):
        if self.changer.current_wallpaper and os.path.exists(self.changer.current_wallpaper):
            os.startfile(self.changer.current_wallpaper)
        else:
            messagebox.showinfo("Info", "No wallpaper has been set yet")
    
    def load_initial_preview(self):
        if self.changer.current_wallpaper:
            self.update_preview()
            self.update_favorite_status()
            self.update_type_label()
            self.update_navigation_display()
            self.status_var.set(f"Loaded last wallpaper: {os.path.basename(self.changer.current_wallpaper)}")
    
    def toggle_theme(self):
        new_theme = "dark" if self.current_scheme == "light" else "light"
        self.change_color_scheme(new_theme)
    
    def change_color_scheme(self, scheme_id):
        self.current_scheme = scheme_id
        self.colors = COLOR_SCHEMES[scheme_id]
        self.changer.config["theme"] = scheme_id
        self.changer.save_config()
        
        self.root.configure(bg=self.colors["bg"])
        
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.setup_ui()
        self.load_config_to_ui()
        
        if self.changer.current_wallpaper:
            self.update_preview()
        
        self.tray.update_menu()
        
        self.status_var.set(f"Changed to {self.colors['name']}")
    
    def load_config_to_ui(self):
        config = self.changer.config
        
        # Settings will be loaded when settings tab is created
        pass
    
    def show_favorites_window(self):
        FavoritesWindow(self, self.changer)
    
    def show_window(self):
        self.root.deiconify()
        self.root.lift()
    
    def on_closing(self):
        self.root.withdraw()
        if self.changer.config.get("notifications", True):
            self.tray.show_notification("Wallpaper Changer", 
                                       "Application minimized to system tray")
    
    def quit(self):
        self.changer.stop_auto_change()
        self.changer.db.close()
        self.root.quit()
    
    def run(self):
        self.root.mainloop()

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    app = ModernWallpaperChangerApp()
    app.run()

if __name__ == "__main__":
    main()
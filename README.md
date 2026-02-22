# 🎨 Wallpaper Changer

A beautiful, feature-rich Windows wallpaper changer with Wallhaven integration, light/dark themes, and keyboard shortcuts.

![App Screenshot](assets/screenshot.png)

## ✨ Features

### 🌐 **Wallhaven Integration**
- Search and download wallpapers from Wallhaven.cc
- API key management (add/delete)
- Real-time API status checking

### 🎨 **Beautiful UI**
- Light and Dark themes (toggle with one click)
- Clean, modern card-based design
- No clutter - recent wallpapers removed for cleaner interface

### 🔞 **Content Filters**
- SFW / Sketchy / NSFW filtering
- Category selection (General/Anime/People)
- Resolution presets (4K, 2K, 1080p, Ultrawide)
- Custom resolution input

### 🔑 **Keyword Downloads**
- Add up to 10+ keywords
- Download 10 wallpapers per keyword
- Daily tracking - remembers when you last downloaded
- "Download Today" vs "Download Now" options
- Progress bar with stop button

### 📁 **Favorites Folder**
- Automatically copies favorited wallpapers to dedicated folder
- Browse favorites with preview
- Remove from favorites folder
- Open in Explorer button
- Folder statistics (total files, size)

### 💾 **Disk Quota**
- Set maximum folder size (default 1000MB)
- Real-time usage display with progress bar
- Auto-stop downloads when quota exceeded
- Cleanup old files button

### ⏰ **Schedules**
- Time-based wallpaper changes
- Morning/Afternoon/Evening/Night presets
- Custom schedule creation
- Priority system

### ⌨️ **Keyboard Shortcuts**
- `Ctrl+Alt+Right` - Next wallpaper
- `Ctrl+Alt+Left` - Previous wallpaper
- `Ctrl+Alt+Del` - Delete current wallpaper
- Fully customizable in Settings

### 🖼️ **Wallpaper Navigation**
- Previous/Next buttons
- Delete button
- Scan folder to refresh list
- Favorite status indicator

### ⚙️ **Settings**
- Save/Delete API key
- Change wallpaper on startup option
- Download folder selection
- Customizable interval (minutes/hours/days)
- Notification toggles

## 🚀 **Installation**

### Option 1: Run from Source
```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/wallpaper-changer.git
cd wallpaper-changer

# Install requirements
pip install -r requirements.txt

# Run the app
python wallpaper_changer.py
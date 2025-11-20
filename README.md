# Vavoo Maker Playlists v1.2

[![Python package](https://github.com/Belfagor2005/VavooMaker/actions/workflows/pylint.yml/badge.svg)](https://github.com/Belfagor2005/VavooMaker/actions/workflows/pylint.yml)
![Version](https://img.shields.io/badge/Version-1.2-blue.svg)
![License](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-green.svg)
![Python](https://img.shields.io/badge/Python-2%20%26%203-yellow.svg)
![Platform](https://img.shields.io/badge/Platform-Enigma2-orange.svg)


<img src="https://raw.githubusercontent.com/Belfagor2005/VavooMaker/main/screen/main.jpg">


## 📖 Description

Vavoo Maker Playlists is a powerful plugin that automatically generates organized IPTV bouquets from Vavoo's extensive channel database. Featuring a completely redesigned interface and intelligent channel categorization.

## ✨ Features

### 🎯 Dual View System
- **Country View** - Browse channels by geographical location
- **Category View** - Organize by content type (Movies, Sports, News, etc.)

### 🎨 Modern Interface
- HD/FHD optimized skin
- Intuitive color-coded navigation
- Professional icon set
- Responsive design

### ⚡ Performance
- Optimized channel loading
- Efficient bouquet management
- Automatic updates
- Stable error handling

### 🔧 User Experience
- One-click bouquet creation
- Selective export options
- Plugin information panel
- Easy installation/removal

## 🚀 Installation

### Method 1: IPK Installation
```bash
# Upload .ipk file to your receiver and install via software management
# or use command line:
opkg install vavoo-maker_1.2_all.ipk
```

### Method 2: Manual Installation
```bash
# Copy files to extensions directory
cp -r vavoo-maker /usr/lib/enigma2/python/Plugins/Extensions/
# Restart Enigma2
```

## 📋 Usage

1. **Launch** the plugin from Extensions menu
2. **Choose** view mode (Countries or Categories)
3. **Select** desired countries/categories
4. **Create** bouquets with Green button
5. **Access** channels from your TV bouquet list

## 🎮 Controls

| Button | Function |
|--------|----------|
| **OK** | Select/Deselect item |
| **Green** | Create selected bouquets |
| **Yellow** | Toggle all selections |
| **Blue** | Remove all Vavoo bouquets |
| **Red** | Cancel/Back |

## 🛠 Technical Details

- **Platform**: Enigma2
- **Python**: 2.x & 3.x compatible
- **Resolution**: HD (1280x720) & FHD (1920x1080)
- **Dependencies**: None
- **License**: CC BY-NC-SA 4.0

## 📁 File Structure

```
vavoo-maker/
├── plugin.py              # Main plugin code
├── vavoo_lib.py           # Utility functions
├── __init__.py            # Package initialization
├── icons/                 # Graphic assets
│   ├── key_red.png
│   ├── key_green.png
│   └── ...
└── skin/                  # Interface definitions
```

## 🔄 Changelog

### v1.2 (2025-11-20)
- Added dual view mode (Countries/Categories)
- Completely redesigned interface
- Enhanced performance and stability
- Professional installation scripts
- Added plugin information panel

### v1.0 (2025-02-11)
- Initial release
- Basic bouquet creation
- Country-based organization

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## 📄 License

This project is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License - see the [LICENSE](LICENSE) file for details.

## 🙏 Credits

- **Developer**: [Lululla](https://github.com/Belfagor2005)
- **Testing**: Warder
- **Communities**: 
  - [Linuxsat-support.com](https://www.linuxsat-support.com)
  - [Corvoboys.org](https://www.corvoboys.org)

## ❤️ Support

If you find this plugin useful, consider supporting the development:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support-orange?logo=buy-me-a-coffee)](https://github.com/Belfagor2005)

---

**⭐ If you like this project, please give it a star on GitHub!**

---

*Professional IPTV bouquet management for Enigma2 receivers* 🚀
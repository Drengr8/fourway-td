# Four-Way Tower Defense Game

A Starcraft-style tower defense game where enemies use pathfinding to navigate around your strategically placed towers.

## Features

- **Grid-based tower placement** - Place towers on a 5x5 grid
- **A* Pathfinding** - Enemies intelligently navigate around your towers
- **Dynamic path recalculation** - Enemies find new routes when you place towers
- **Resource management** - HP and gold system
- **Touch controls** - Optimized for mobile devices

## How to Get the APK

### Option 1: GitHub Actions (Recommended)

1. **Create a GitHub repository** and push this code to it
2. **The APK will build automatically** when you push to main/master
3. **Download the APK** from the Actions tab in your GitHub repository
4. **Install on your device** or test in Android Studio emulator

### Option 2: Google Colab

1. Open the `build_apk_colab.ipynb` file in Google Colab
2. Upload your project files when prompted
3. Run all cells to build and download the APK

## Game Controls

- **Tap any grid cell** to place a tower (costs 10 gold)
- **Towers block enemy movement** - enemies will pathfind around them
- **Enemies spawn every 2 seconds** from the top row
- **Lose HP** when enemies reach the bottom
- **Strategic placement** is key to success!

## Testing

### On Android Device:
1. Enable "Install from unknown sources" in settings
2. Transfer and install the APK
3. Launch the game and start defending!

### In Android Studio:
1. Start an Android emulator
2. Drag and drop the APK onto the emulator window
3. The game will install and launch automatically

## Development

To run locally on desktop:
```bash
pip install kivy kivymd numpy scipy
python main.py
```

## Files

- `main.py` - Main game logic and Kivy app
- `pathfinding.py` - A* pathfinding algorithm
- `requirements.txt` - Python dependencies
- `.github/workflows/build-apk.yml` - Automated APK building
- `build_apk_colab.ipynb` - Manual APK building in Google Colab
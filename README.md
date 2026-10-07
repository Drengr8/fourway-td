# FourWay TD

**Hold the crossroads.** A four-direction lane tower defense—enemies pathfind in from every side, and every tower you place reshapes the map.

[Play overview & launch page →](https://drengr8.github.io/fourway-td/) · [GitHub Actions APK](https://github.com/Drengr8/fourway-td/actions)

## The fantasy

- **Four fronts** — waves arrive from N / E / S / W, not a single drip lane
- **Starcraft-minded pathfinding** — towers block; enemies recalculate with A*
- **Merge & escalate** — place the same tower type on itself to climb tiers (mobile + desktop)
- **Touch-first** — Android APK via Kivy; desktop pygame prototype for the deepest toybox

## Play

### Desktop (richest prototype)

```bash
pip install -r requirements.txt
python desktop_main.py
```

Drag towers onto the 5×5 grid. Merge same-type towers to upgrade. Survive enemies approaching from all four roads.

### Android APK

1. Push to `main` (or run the **Build Android APK** workflow manually)
2. Download `fourwaytd-apk` from the Actions artifact
3. Install on device (unknown sources / emulator)

Local mobile entrypoint:

```bash
pip install -r requirements.txt
python main.py
```

Pick Bolt / Frost / Beam from the tray, tap a cell to place, tap the **same type again** to merge up to tier 4. Towers shoot; Frost slows. Enemies approach from all four sides.

### Colab build

Open `build_apk_colab.ipynb` in Google Colab if you prefer a notebook APK build.

## Controls (quick)

| Surface | Action |
|--------|--------|
| Desktop | Drag tower from the tray onto a cell; merge by stacking same type |
| Mobile | Select a tower in the tray; tap empty cell to place; tap same type to merge |

Lose HP when an enemy reaches the opposite edge. Gold funds placement and merges.

## Repo map

| File | Role |
|------|------|
| `desktop_main.py` | Full pygame prototype (four-way, merges, multiple tower types) |
| `main.py` | Kivy / Android launch build (four-way, merge tiers, combat) |
| `buildozer.spec` | Android packaging config |
| `docs/` | Landing page (GitHub Pages) |
| `.github/workflows/build-apk.yml` | Automated APK |

## Status

Prototype / early access. Mobile now carries four-front pathfinding **and** merge/tier combat; desktop still has the widest tower/bullet toybox.

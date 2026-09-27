# 7th Sea Mappa Mundi — Tile Pipeline

Scripts for generating and compressing equirectangular tiles for the
interactive 3D globe (`index.html` / Three.js).

---

## Files

| File | Role |
|------|------|
| `grid.json` | Configuration — the only file you edit manually |
| `gen_tiles.py` | Reads `grid.json`, cuts the source map into PNG tiles |
| `compress_tiles.py` | Converts PNG tiles → WebP, reverses polar correction |
| `index.html` | 3D globe — reads `grid.json` on startup |

---

## grid.json — configuration

```json
{
  "tile_out": 1024,
  "max_correction": 8.0,
  "views": {
    "far": {
      "cols": 8,
      "rows": 4,
      "lat_stretch": false,
      "seg": 40,
      "desc": "45x45 degrees per tile"
    },
    "near": {
      "cols": 72,
      "rows": 36,
      "lat_stretch": true,
      "seg": 60,
      "desc": "5x5 degrees per tile"
    }
  }
}
```

| Parameter | Description |
|-----------|-------------|
| `tile_out` | Output tile size in pixels (width = height) |
| `max_correction` | Maximum polar stretch multiplier (8.0 ≈ 83°N/S) |
| `cols` / `rows` | Number of tiles horizontally / vertically |
| `lat_stretch` | Stretch tile height by 1/cos(lat) to compensate polar distortion (NEAR only) |
| `seg` | Three.js geometry segments per tile |

---

## Source map requirements

### Aspect ratio
The source map must be **equirectangular 2:1** (width = 2 × height),
covering the full 360° × 180°.

### Size
The script rescales the map to `tile_out × cols` × `tile_out × rows`
before cutting. With default settings (`tile_out = 1024`):

| View | Grid | Normalised size |
|------|------|-----------------|
| FAR  | 8×4  | **8192×4096 px** |
| NEAR | 72×36 | 73728×36864 px (internal — you don't export at this size) |

**Recommended export size:** `8192×4096 px` or any 2:1 resolution —
the script rescales automatically. NEAR tiles are upscaled from the same
source, so the input file does not need to be enormous.

### Wonderdraft workflow
Each NEAR tile produced by `gen_tiles.py` has dimensions `1024 × H` px,
where H > 1024 near the poles (1/cos(lat) correction). Import such a file
into Wonderdraft as a land mask — land shapes will appear proportional
despite the stretch. `compress_tiles.py` squeezes the tile back to
`1024×1024` before saving as WebP.

### Format
- PNG or JPG (PNG recommended for B&W masks)
- RGB or RGBA

---

## gen_tiles.py

### Requirements
```bash
pip install Pillow
```

### Usage
```bash
# Both views (FAR + NEAR)
python3 gen_tiles.py map.png

# FAR only
python3 gen_tiles.py map.png --view far

# NEAR only
python3 gen_tiles.py map.png --view near

# Custom output directory and grid.json path
python3 gen_tiles.py map.png --out ./tiles_png --grid ./grid.json
```

### Options
| Option | Default | Description |
|--------|---------|-------------|
| `--view` | `all` | `far`, `near`, or `all` |
| `--out` | `tiles_png/` next to the script | Output directory |
| `--grid` | `grid.json` next to the script | Path to configuration file |

### Output structure
```
tiles_png/
├── tile_sizes.txt     ← tile dimensions summary
├── far/
│   ├── 0_0.png        ← row 0, column 0
│   ├── 0_1.png
│   └── …              (32 files, each 1024×1024 px)
└── near/
    ├── 0_0.png        ← polar row, 1024×8192 px (max correction)
    ├── 17_0.png       ← equatorial row, 1024×1024 px
    └── …              (2592 files, always 1024 px wide)
```

---

## compress_tiles.py

### Requirements
```bash
pip install Pillow
```

### Usage
```bash
# FAR
python3 compress_tiles.py tiles_png/far  --out tiles/far

# NEAR
python3 compress_tiles.py tiles_png/near --out tiles/near

# Higher WebP quality
python3 compress_tiles.py tiles_png/near --out tiles/near --webp-quality 85

# Also generate PNG fallback
python3 compress_tiles.py tiles_png/near --out tiles/near --png-fallback
```

### Options
| Option | Default | Description |
|--------|---------|-------------|
| `--out` | `<input>_compressed` | Output directory |
| `--webp-quality` | `82` | WebP quality (75–85 is the sweet spot) |
| `--png-compress` | `9` | PNG fallback compression level (0–9) |
| `--png-fallback` | off | Also write an optimised PNG alongside the WebP |

The script reads `grid.json` from its own directory (project root) —
no need to specify the path manually.

---

## Full workflow

```bash
# 1. Edit grid.json if you want to change grid parameters

# 2. Generate PNG tiles from your B&W source map
python3 gen_tiles.py map.png --view far  --out tiles_png
python3 gen_tiles.py map.png --view near --out tiles_png

# 3. Import tiles from tiles_png/near/ into Wonderdraft
#    (each file as a land mask; canvas size = file size)
#    → edit, export back to tiles_png/near/

# 4. Compress to WebP
python3 compress_tiles.py tiles_png/far  --out tiles/far
python3 compress_tiles.py tiles_png/near --out tiles/near

# 5. Serve locally and open the globe
python3 -m http.server 8000
# → http://localhost:8000/index.html
```

---

## Project structure

```
project/
├── grid.json              ← configuration — read by all scripts and index.html
├── gen_tiles.py
├── compress_tiles.py
├── index.html
└── tiles/                 ← files served by GitHub Pages
    ├── stars_babylon.webp
    ├── polar_n.webp
    ├── polar_s.webp
    ├── far/
    │   └── *.webp         (32 files)
    └── near/
        └── *.webp         (2592 files)
```

#!/usr/bin/env python3
"""
gen_tiles.py — PNG tile generator for globe.html / 7th Sea Mappa Mundi
=======================================================================

Reads grid.json for all configuration — do not hardcode parameters here.
Place grid.json in the same directory as this script, or pass --grid.

Output layout
─────────────
  <out>/
    far/   0_0.png … 3_7.png
    near/  0_0.png … 35_71.png
  tile_sizes.txt

Default <out> is tiles_png/ next to this script, regardless of the
current working directory.

Usage
─────
  python3 gen_tiles.py <map.png>
  python3 gen_tiles.py <map.png> --view far
  python3 gen_tiles.py <map.png> --view near
  python3 gen_tiles.py <map.png> --out ./tiles_png --grid ./grid.json

Requirements:  pip install Pillow
"""

import sys
import math
import json
import argparse
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Missing Pillow library. Install with: pip install Pillow")
    sys.exit(1)

Image.MAX_IMAGE_PIXELS = None

DEFAULT_OUT_DIR  = Path(__file__).parent / 'tiles_png'
DEFAULT_GRID     = Path(__file__).parent / 'grid.json'
OVERLAP_SRC      = 2   # source-px overlap on each edge (anti-seam LANCZOS fix)


def load_grid(grid_path):
    path = Path(grid_path)
    if not path.exists():
        print(f"Error: grid.json not found at '{path}'")
        sys.exit(1)
    grid = json.loads(path.read_text())
    print(f"  [grid.json] tile_out={grid['tile_out']}, max_correction={grid['max_correction']}")
    for v, cfg in grid['views'].items():
        print(f"    {v}: {cfg['cols']}×{cfg['rows']}, lat_stretch={cfg['lat_stretch']}, seg={cfg['seg']}")
    return grid


def lat_correction(row, rows, max_correction):
    lat_mid = 90.0 - (row + 0.5) * (180.0 / rows)
    return min(1.0 / math.cos(math.radians(lat_mid)), max_correction)


def polar_row_visible(row, rows, polar_lat_cap):
    """
    Returns True if the tile row is at least partially visible
    (not entirely covered by a polar cap).

    A row is FULLY covered when its entire latitude range lies at or beyond
    the polar cap boundary:
      - North cap: lat_bottom >= polar_lat_cap  (both edges north of cap)
      - South cap: lat_top    <= -polar_lat_cap (both edges south of cap)

    Because grid boundaries land exactly on the cap edge (5° tiles, cap=60°)
    there is no partial-overlap case — every row is either fully inside or
    fully outside the cap.
    """
    deg_per_row = 180.0 / rows
    lat_top = 90.0 - row * deg_per_row
    lat_bot = 90.0 - (row + 1) * deg_per_row
    if lat_bot >= polar_lat_cap:   # fully under north cap
        return False
    if lat_top <= -polar_lat_cap:  # fully under south cap
        return False
    return True


def gen_view(norm_img, view_name, view_cfg, tile_out, max_correction, out_dir,
             polar_lat_cap=None):
    cols        = view_cfg['cols']
    rows        = view_cfg['rows']
    lat_stretch = view_cfg['lat_stretch']

    src_w, src_h = norm_img.size
    tile_src_w   = src_w // cols
    tile_src_h   = src_h // rows
    scale_x      = tile_out / tile_src_w

    tile_out_dir = Path(out_dir) / view_name
    tile_out_dir.mkdir(parents=True, exist_ok=True)

    # Determine which rows to skip (polar cap optimisation — lat_stretch views only)
    if lat_stretch and polar_lat_cap is not None:
        skip_rows = {r for r in range(rows)
                     if not polar_row_visible(r, rows, polar_lat_cap)}
    else:
        skip_rows = set()

    total        = rows * cols
    skipped      = len(skip_rows) * cols
    generated    = total - skipped
    skip_info    = (f", skipping {len(skip_rows)} polar rows ({skipped} tiles)"
                    if skip_rows else "")
    print(f"  [{view_name}] {cols}×{rows} = {total} tiles  "
          f"(source {tile_src_w}×{tile_src_h}px → {tile_out}×H px"
          + (" lat-stretched" if lat_stretch else f", H={tile_out}") +
          f")  [{view_cfg['desc']}]{skip_info}")
    if skip_rows:
        print(f"    Polar skip (cap={polar_lat_cap}°): "
              f"rows {sorted(skip_rows)[:6]}{'…' if len(skip_rows) > 6 else ''} "
              f"(N) + "
              f"rows {sorted(skip_rows)[-6:][::-1][:6][::-1]}"
              f"{'…' if len(skip_rows) > 6 else ''} (S)  → {generated} tiles generated")

    for row in range(rows):
        if row in skip_rows:
            continue  # ← kafelek pod czapą polarną — pomijamy

        correction = lat_correction(row, rows, max_correction) if lat_stretch else 1.0
        out_h      = round(tile_out * correction)
        scale_y    = out_h / tile_src_h

        for col in range(cols):
            x0 = col * tile_src_w
            y0 = row * tile_src_h

            # Padded crop to avoid LANCZOS seam artifacts at tile edges
            cx0 = max(0,     x0 - OVERLAP_SRC)
            cy0 = max(0,     y0 - OVERLAP_SRC)
            cx1 = min(src_w, x0 + tile_src_w + OVERLAP_SRC)
            cy1 = min(src_h, y0 + tile_src_h + OVERLAP_SRC)

            tile = norm_img.crop((cx0, cy0, cx1, cy1))

            pad_w = round((cx1 - cx0) * scale_x)
            pad_h = round((cy1 - cy0) * scale_y)
            tile  = tile.resize((pad_w, pad_h), Image.LANCZOS)

            left = round((x0 - cx0) * scale_x)
            top  = round((y0 - cy0) * scale_y)
            tile = tile.crop((left, top, left + tile_out, top + out_h))

            tile.save(tile_out_dir / f"{row}_{col}.png", 'PNG', optimize=True)

        done_rows = row + 1 - sum(1 for r in skip_rows if r <= row)
        pct  = done_rows * 100 // max(generated // cols, 1)
        bar  = '#' * min(20, pct // 5) + '.' * max(0, 20 - pct // 5)
        print(f"\r    [{bar}] {pct:3d}%  ({done_rows * cols}/{generated})", end='', flush=True)

    print(f"\r  [{view_name}] Done — {generated}/{total} tiles generated → {tile_out_dir}/          ")


def write_tile_sizes(grid, out_dir, norm_w, norm_h):
    """
    Writes tile_sizes.txt — a helper for creating maps in Wonderdraft before tile import.

    For each view and each row lists the exact PNG tile size in pixels
    (width × height), accounting for lat-stretch correction.
    NEAR tiles have varying heights depending on latitude — the file groups
    consecutive rows with the same size and shows their lat range.
    """
    tile_out    = grid['tile_out']
    max_corr    = grid['max_correction']
    polar_cap   = grid.get('polar_lat_cap')
    lines       = []

    lines.append("tile_sizes.txt — PNG tile sizes for Wonderdraft")
    lines.append("=" * 54)
    lines.append(f"Source map:     {norm_w} × {norm_h} px")
    lines.append(f"tile_out:       {tile_out} px")
    if polar_cap:
        lines.append(f"Polar cap:      ±{polar_cap}° (tiles beyond this range are not generated)")
    lines.append("")

    for view_name, view_cfg in grid['views'].items():
        cols        = view_cfg['cols']
        rows        = view_cfg['rows']
        lat_stretch = view_cfg['lat_stretch']
        deg_lon     = 360.0 / cols
        deg_lat     = 180.0 / rows

        lines.append(f"[{view_name.upper()}]  {cols} × {rows} tiles  ({deg_lon:.2f}° × {deg_lat:.2f}° per tile)")
        lines.append("-" * 54)

        if not lat_stretch:
            lines.append(f"  Every tile:  {tile_out} × {tile_out} px")
        else:
            groups = []
            for row in range(rows):
                if polar_cap and not polar_row_visible(row, rows, polar_cap):
                    continue
                correction = lat_correction(row, rows, max_corr)
                out_h      = round(tile_out * correction)
                lat_top    = 90.0 - row * deg_lat
                lat_bot    = 90.0 - (row + 1) * deg_lat
                if groups and groups[-1][1] == out_h:
                    prev = groups[-1]
                    groups[-1] = (prev[0], prev[1], prev[2], row, prev[4], lat_bot)
                else:
                    groups.append((tile_out, out_h, row, row, lat_top, lat_bot))

            lines.append(f"  Width of every tile:  {tile_out} px (constant)")
            lines.append(f"  Height varies with latitude (lat-stretch):")
            lines.append("")
            lines.append(f"  {'Rows':>12}  {'Lat range':>16}  {'Size (px)':>14}")
            lines.append(f"  {'-'*12}  {'-'*16}  {'-'*14}")
            for (out_w, out_h, r0, r1, lat_top, lat_bot) in groups:
                row_range = f"{r0}" if r0 == r1 else f"{r0}–{r1}"
                lat_range = f"{lat_top:+.0f}° → {lat_bot:+.0f}°"
                size_str  = f"{out_w} × {out_h}"
                lines.append(f"  {row_range:>12}  {lat_range:>16}  {size_str:>14}")

        lines.append("")

    out_path = Path(out_dir) / "tile_sizes.txt"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  tile_sizes.txt → {out_path}")


def gen_tiles(src_path, grid_path, view='all', out_dir=DEFAULT_OUT_DIR):
    src_path = Path(src_path)
    if not src_path.exists():
        print(f"Error: '{src_path}' not found.")
        sys.exit(1)

    grid        = load_grid(grid_path)
    tile_out    = grid['tile_out']
    max_corr    = grid['max_correction']
    polar_cap   = grid.get('polar_lat_cap', None)
    norm_w      = tile_out * grid['views']['far']['cols']   # e.g. 1024*8 = 8192
    norm_h      = tile_out * grid['views']['far']['rows']   # e.g. 1024*4 = 4096

    print(f"Loading: {src_path}")
    with Image.open(src_path) as img:
        src_img = img.convert('RGBA')
        src_w, src_h = src_img.size
    print(f"Source: {src_w}×{src_h} px")

    if (src_w, src_h) != (norm_w, norm_h):
        print(f"Rescaling to {norm_w}×{norm_h} px…")
        norm_img = src_img.resize((norm_w, norm_h), Image.LANCZOS)
    else:
        norm_img = src_img

    Path(out_dir).mkdir(parents=True, exist_ok=True)

    views_to_run = (list(grid['views'].items()) if view == 'all'
                    else [(view, grid['views'][view])])

    for view_name, view_cfg in views_to_run:
        gen_view(norm_img, view_name, view_cfg, tile_out, max_corr, out_dir,
                 polar_lat_cap=polar_cap)

    write_tile_sizes(grid, out_dir, norm_w, norm_h)
    print("\nDone!")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='PNG tile generator for globe.html')
    ap.add_argument('map',
        help='Equirectangular PNG/JPG source map')
    ap.add_argument('--grid', default=DEFAULT_GRID, metavar='PATH',
        help=f'Path to grid.json (default: next to this script)')
    ap.add_argument('--view', choices=['far', 'near', 'all'], default='all',
        help="View to generate: 'far', 'near', or 'all' (default: all)")
    ap.add_argument('--out', default=DEFAULT_OUT_DIR,
        help='Output directory (default: tiles_png/ next to this script)')
    args = ap.parse_args()
    gen_tiles(src_path=args.map, grid_path=args.grid,
              view=args.view, out_dir=args.out)

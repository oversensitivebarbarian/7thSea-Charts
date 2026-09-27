#!/usr/bin/env python3
"""
gen_polar_tiles.py — Generator kafelków polarnych w rzucie gnomonicznym
=======================================================================

Konwertuje oryginalną mapę equirectangular (np. world.tif lub mapa 7th Sea)
na dwa kafelki polarne w rzucie gnomonicznym:
  tiles/polar_n.png  — biegun północny
  tiles/polar_s.png  — biegun południowy

RZUT GNOMONICZNY (tangent plane projection)
--------------------------------------------
Płaszczyzna rzutowania jest styczna do sfery w punkcie bieguna.
Każdy punkt sfery (lat, lon) jest rzutowany wzdłuż promienia przechodzącego
przez środek sfery na tę płaszczyznę.

Wzory:
  Kąt od bieguna: d = 90° − |lat|            (dla bieguna N; dla S: d = 90° + lat)
  Promień w rzucie: r = tan(d)               (w jednostkach sfery jednostkowej)
  Azimut: φ = lon                            (wschód = prawo w mapie N, lewo w S)

  x_img = cx + r · cos(φ) · scale
  y_img = cy − r · sin(φ) · scale            (Y odwrócone — góra obrazu = N)

  gdzie cx, cy = środek obrazu, scale = rozmiar_obrazu / (2 · tan(d_max))

PARAMETRY
----------
  SOURCE        — ścieżka do mapy equirectangular źródłowej (dowolny rozmiar)
  OUTPUT_DIR    — katalog docelowy (tworzony jeśli nie istnieje)
  OUTPUT_SIZE   — rozmiar kwadratowego kafelka polarnego w pikselach
  LAT_CAP_DEG   — granica czapy (jak w globe.html — domyślnie 60°)
  BLEND_DEG     — strefa blend ponad granicą (domyślnie 5° — jak w globe.html)
  OVERSAMPLE    — współczynnik nadpróbkowania przy próbkowaniu (1=brak, 2=2x)

UŻYCIE
------
  python3 gen_polar_tiles.py --source mapa.png --output tiles/

Wymagania: Pillow (pip install Pillow), numpy (pip install numpy)

INTEGRACJA Z globe.html
------------------------
Wygenerowane pliki PNG należy umieścić w:
  tiles/polar_n.png
  tiles/polar_s.png
globe.html automatycznie je załaduje. Jeśli pliki nie istnieją,
używana jest proceduralna tekstura demonstracyjna (patrz makePolarFallback).

ORIENTACJA TEKSTURY
--------------------
Biegun N (polar_n.png):
  - Centrum obrazu = biegun północny (90°N)
  - Prawy brzeg = lon 0° (południk Greenwich) → E po prawej
  - Górny brzeg = lon 90°W
  Tekstura jest "widokiem z góry" — tak jak typowe mapy polarne.

Biegun S (polar_s.png):
  - Centrum obrazu = biegun południowy (90°S)
  - Orientacja lustrzana względem N (żeby E/W zgadzało się z equirectangular)
  - Prawy brzeg = lon 0°

TRYB DEMONSTRACYJNY
--------------------
Jeśli nie podano --source, skrypt generuje syntetyczną mapę demonstracyjną
(gradient kolorów z siatką południkową) zamiast prawdziwej mapy świata.
Przydatne do testowania bez posiadania rzeczywistego pliku źródłowego.
"""

import argparse
import math
import os
import sys
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("Błąd: wymagane biblioteki Pillow i numpy.")
    print("Zainstaluj je: pip install Pillow numpy")
    sys.exit(1)


# ── Domyślne parametry (muszą być zgodne z globe.html) ──
LAT_CAP_DEG   = 60      # granica czapy polarnej (stopnie)
BLEND_DEG     = 5       # strefa blend ponad granicą
OUTPUT_SIZE   = 2048    # rozmiar wynikowego PNG (px × px)
OVERSAMPLE    = 2       # nadpróbkowanie przy bilinearnym próbkowaniu


def equirect_to_gnomonic(source_img: Image.Image,
                          is_north: bool,
                          lat_cap_deg: float = LAT_CAP_DEG,
                          blend_deg: float = BLEND_DEG,
                          output_size: int = OUTPUT_SIZE,
                          oversample: int = OVERSAMPLE) -> Image.Image:
    """
    Konwertuje mapę equirectangular na kafelek gnomoniczny dla danego bieguna.

    Parametry:
        source_img   — obraz equirectangular (dowolny rozmiar, RGB lub RGBA)
        is_north     — True = biegun N, False = biegun S
        lat_cap_deg  — granica czapy (stopnie szerokości geogr.)
        blend_deg    — strefa blend (stopnie)
        output_size  — rozmiar kwadratowego wyjścia (piksele)
        oversample   — nadpróbkowanie (int ≥ 1)

    Zwraca: Image RGBA (output_size × output_size)
    """
    # Granica rzutu z marginesem blend
    lat_max = lat_cap_deg + blend_deg    # maksymalna szer. geogr. w czapce
    d_max   = math.radians(90 - (lat_cap_deg - blend_deg))  # kąt od bieguna
    r_max   = math.tan(d_max)           # promień gnomoniczny przy krawędzi

    src_w, src_h = source_img.size
    src_arr = np.array(source_img.convert('RGBA'), dtype=np.float32)

    sz    = output_size * oversample
    cx    = sz / 2.0
    cy    = sz / 2.0
    scale = sz / (2.0 * r_max)         # pikseli na jednostkę gnomoniczną

    # Siatka pikseli wynikowego obrazu
    ys, xs = np.mgrid[0:sz, 0:sz]
    dx = (xs - cx) / scale             # odległość od centrum w jednostkach r
    dy = (cy - ys) / scale             # Y odwrócone

    # Promień gnomoniczny i azimut
    r   = np.sqrt(dx**2 + dy**2)
    phi = np.arctan2(dy, dx)           # azimut (kąt od osi X)

    # Kąt od bieguna (odległość kątowa)
    d = np.arctan(r)                   # d = arctan(r) w rzucie gnomonicznym

    # Szerokość i długość geograficzna
    if is_north:
        lat = np.degrees(math.pi/2 - d)   # od bieguna N
        lon = np.degrees(phi)              # azimut = długość
    else:
        lat = -np.degrees(math.pi/2 - d)  # biegun S — ujemna lat
        # Biegun S: orientacja lustrzana żeby E/W było spójne z N
        lon = np.degrees(-phi)

    # Normalizacja lon do [0, 360) → kolumna w equirectangular
    lon = ((lon % 360) + 360) % 360

    # Przekształcenie (lat, lon) → (px_x, px_y) w obrazie źródłowym
    px_x = lon / 360.0 * (src_w - 1)
    px_y = (90.0 - lat) / 180.0 * (src_h - 1)
    px_x = np.clip(px_x, 0, src_w - 1)
    px_y = np.clip(px_y, 0, src_h - 1)

    # Bilinearne próbkowanie
    x0 = np.floor(px_x).astype(int)
    y0 = np.floor(px_y).astype(int)
    x1 = np.clip(x0 + 1, 0, src_w - 1)
    y1 = np.clip(y0 + 1, 0, src_h - 1)
    fx = (px_x - x0)[..., np.newaxis]  # ułamek X
    fy = (px_y - y0)[..., np.newaxis]  # ułamek Y

    c00 = src_arr[y0, x0]
    c10 = src_arr[y0, x1]
    c01 = src_arr[y1, x0]
    c11 = src_arr[y1, x1]
    colors = (c00 * (1-fx) * (1-fy) +
              c10 *    fx  * (1-fy) +
              c01 * (1-fx) *    fy  +
              c11 *    fx  *    fy)

    # Maska: piksele poza zakresem czapy (r > r_max) są przezroczyste
    outside = r > r_max
    colors[outside, 3] = 0

    # Alpha blend przy krawędzi
    r_cap   = math.tan(math.radians(90 - lat_cap_deg))
    blend   = np.clip((r_max - r) / (r_max - r_cap), 0, 1)
    colors[..., 3] *= blend

    # Downscale jeśli nadpróbkowane
    result = Image.fromarray(np.clip(colors, 0, 255).astype(np.uint8), 'RGBA')
    if oversample > 1:
        result = result.resize((output_size, output_size), Image.LANCZOS)

    return result


def make_demo_equirectangular(width: int = 4096, height: int = 2048) -> Image.Image:
    """
    Tworzy syntetyczną mapę equirectangular do testów.
    Niebieski = ocean, zielony = ląd (symulowany szumem).
    Siatka południków i równoleżników co 30°.
    """
    import random
    rng = random.Random(42)

    arr = np.zeros((height, width, 3), dtype=np.uint8)

    for py in range(height):
        lat = 90.0 - py / height * 180.0
        for px in range(width):
            lon = px / width * 360.0 - 180.0

            # Prosty szum do symulacji lądów
            noise = (math.sin(lat * 0.3) * math.cos(lon * 0.25) +
                     math.sin(lon * 0.4) * 0.5 +
                     math.cos(lat * 0.5 + lon * 0.2) * 0.4)

            if noise > 0.3:  # ląd
                r = int(100 + 60 * noise)
                g = int(130 + 50 * noise)
                b = int(60  + 30 * noise)
            else:  # ocean
                depth = abs(lat) / 90.0
                r = int(20  + 30  * depth)
                g = int(60  + 60  * depth)
                b = int(130 + 80  * depth)

            arr[py, px] = [r, g, b]

    img = Image.fromarray(arr, 'RGB')

    # Siatka południkowa
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    for lon in range(-180, 181, 30):
        px = int((lon + 180) / 360.0 * width)
        draw.line([(px, 0), (px, height)], fill=(255, 255, 255, 80), width=1)
    for lat in range(-90, 91, 30):
        py = int((90 - lat) / 180.0 * height)
        draw.line([(0, py), (width, py)], fill=(255, 255, 255, 80), width=1)

    return img


def main():
    parser = argparse.ArgumentParser(
        description='Generuje kafelki polarne w rzucie gnomonicznym z mapy equirectangular.')
    parser.add_argument('--source', '-s',
        help='Ścieżka do mapy equirectangular źródłowej (PNG, JPEG, TIFF itp.).'
             ' Jeśli nie podano, użyta zostanie syntetyczna mapa demonstracyjna.')
    parser.add_argument('--output', '-o', default='tiles',
        help='Katalog docelowy (domyślnie: tiles/)')
    parser.add_argument('--size', type=int, default=OUTPUT_SIZE,
        help=f'Rozmiar kafelka w pikselach (domyślnie: {OUTPUT_SIZE})')
    parser.add_argument('--lat-cap', type=float, default=LAT_CAP_DEG,
        help=f'Granica czapy polarnej w stopniach (domyślnie: {LAT_CAP_DEG}°)')
    parser.add_argument('--blend', type=float, default=BLEND_DEG,
        help=f'Strefa blend w stopniach (domyślnie: {BLEND_DEG}°)')
    parser.add_argument('--oversample', type=int, default=OVERSAMPLE,
        help=f'Nadpróbkowanie (domyślnie: {OVERSAMPLE})')
    args = parser.parse_args()

    # ── Załaduj lub wygeneruj mapę źródłową ──
    if args.source:
        print(f"Ładowanie mapy źródłowej: {args.source}")
        try:
            src = Image.open(args.source)
            print(f"  Rozmiar: {src.size[0]}×{src.size[1]} px, tryb: {src.mode}")
        except Exception as e:
            print(f"Błąd ładowania: {e}")
            sys.exit(1)
    else:
        print("Brak mapy źródłowej — generuję syntetyczną mapę demonstracyjną...")
        src = make_demo_equirectangular()
        print(f"  Wygenerowano: {src.size[0]}×{src.size[1]} px")

    # ── Utwórz katalog wyjściowy ──
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Generuj oba kafelki ──
    for is_north in [True, False]:
        pole_name = "północny" if is_north else "południowy"
        fname     = "polar_n.png" if is_north else "polar_s.png"
        out_path  = out_dir / fname

        print(f"\nGeneruję biegun {pole_name} ({fname})...")
        print(f"  Granica czapy: {args.lat_cap}°, blend: {args.blend}°")
        print(f"  Rozmiar wyjścia: {args.size}×{args.size} px"
              f" (oversample ×{args.oversample})")

        result = equirect_to_gnomonic(
            source_img   = src,
            is_north     = is_north,
            lat_cap_deg  = args.lat_cap,
            blend_deg    = args.blend,
            output_size  = args.size,
            oversample   = args.oversample,
        )

        result.save(out_path, 'PNG', optimize=False, compress_level=6)
        file_size = out_path.stat().st_size / 1024
        print(f"  Zapisano: {out_path}  ({file_size:.0f} KB)")

    print(f"\n✓ Gotowe! Pliki zapisane w: {out_dir.resolve()}")
    print(f"\nNastępny krok:")
    print(f"  Skopiuj {out_dir}/polar_n.png i polar_s.png do katalogu tiles/")
    print(f"  Uruchom: python3 -m http.server 8000")
    print(f"  Otwórz:  http://localhost:8000/globe.html")


if __name__ == '__main__':
    main()

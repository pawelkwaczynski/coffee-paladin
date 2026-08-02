#!/bin/bash
# zrob_ikone.sh - buduje AppIcon.icns z portretu paladyna.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "uzycie: tools/zrob_ikone.sh branding/paladin.png AppIcon.icns" >&2
  exit 2
fi

WEJSCIE="$1"
WYJSCIE="$2"

if [ ! -f "$WEJSCIE" ]; then
  echo "brak pliku PNG: $WEJSCIE" >&2
  exit 1
fi
if ! command -v sips >/dev/null 2>&1; then
  echo "brak sips - nie moge zbudowac rozmiarow ikon" >&2
  exit 1
fi
if ! command -v iconutil >/dev/null 2>&1; then
  echo "brak iconutil - nie moge zlozyc icns" >&2
  exit 1
fi

OUTDIR="$(dirname "$WYJSCIE")"
mkdir -p "$OUTDIR"
TMPDIR_ICON="$(mktemp -d)"
if [ -n "${COFFEE_PALADIN_KEEP_ICONSET:-}" ]; then
  trap 'echo "$TMPDIR_ICON" >&2' EXIT
else
  trap 'rm -rf "$TMPDIR_ICON"' EXIT
fi

MASTER="$TMPDIR_ICON/AppIcon-master.png"
ICONSET="$TMPDIR_ICON/AppIcon.iconset"
mkdir -p "$ICONSET"

# PNG ma biale tlo, wiec nie wystarczy czytac kanalu alfa. Flood fill z krawedzi
# usuwa tylko tlo polaczone z brzegiem i zostawia jasne detale wewnatrz postaci.
/usr/bin/python3 - "$WEJSCIE" "$MASTER" <<'PY'
import binascii
import math
import struct
import sys
import zlib
from collections import deque

src, dst = sys.argv[1], sys.argv[2]
data = open(src, "rb").read()
if data[:8] != b"\x89PNG\r\n\x1a\n":
    raise SystemExit("to nie jest PNG")

pos = 8
width = height = bit_depth = color_type = None
idat = bytearray()
while pos < len(data):
    length = int.from_bytes(data[pos:pos + 4], "big")
    name = data[pos + 4:pos + 8]
    body = data[pos + 8:pos + 8 + length]
    pos += 12 + length
    if name == b"IHDR":
        width, height, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", body)
    elif name == b"IDAT":
        idat.extend(body)
    elif name == b"IEND":
        break

if bit_depth != 8 or color_type not in (2, 6):
    raise SystemExit("obslugiwany jest tylko PNG RGB/RGBA 8-bit")

channels = 4 if color_type == 6 else 3
bpp = channels
raw = zlib.decompress(bytes(idat))
stride = width * channels
rows = []
idx = 0
prev = bytearray(stride)

def paeth(a, b, c):
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c

for _y in range(height):
    filtr = raw[idx]
    idx += 1
    row = bytearray(raw[idx:idx + stride])
    idx += stride
    for i, val in enumerate(row):
        left = row[i - bpp] if i >= bpp else 0
        up = prev[i]
        up_left = prev[i - bpp] if i >= bpp else 0
        if filtr == 1:
            row[i] = (val + left) & 255
        elif filtr == 2:
            row[i] = (val + up) & 255
        elif filtr == 3:
            row[i] = (val + ((left + up) >> 1)) & 255
        elif filtr == 4:
            row[i] = (val + paeth(left, up, up_left)) & 255
        elif filtr != 0:
            raise SystemExit("nieznany filtr PNG")
    rows.append(row)
    prev = row

rgba = bytearray(width * height * 4)
for y, row in enumerate(rows):
    for x in range(width):
        si = x * channels
        di = (y * width + x) * 4
        rgba[di:di + 3] = row[si:si + 3]
        rgba[di + 3] = row[si + 3] if channels == 4 else 255

def prawie_biale(p):
    i = p * 4
    r, g, b, a = rgba[i:i + 4]
    return a <= 5 or (r >= 245 and g >= 245 and b >= 245)

seen = bytearray(width * height)
q = deque()
for x in range(width):
    for y in (0, height - 1):
        p = y * width + x
        if not seen[p] and prawie_biale(p):
            seen[p] = 1
            q.append(p)
for y in range(height):
    for x in (0, width - 1):
        p = y * width + x
        if not seen[p] and prawie_biale(p):
            seen[p] = 1
            q.append(p)

while q:
    p = q.popleft()
    x = p % width
    y = p // width
    for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
        if 0 <= nx < width and 0 <= ny < height:
            np = ny * width + nx
            if not seen[np] and prawie_biale(np):
                seen[np] = 1
                q.append(np)

min_x, min_y = width, height
max_x = max_y = -1
for p, bg in enumerate(seen):
    if bg:
        rgba[p * 4 + 3] = 0
        continue
    if rgba[p * 4 + 3] == 0:
        continue
    x = p % width
    y = p // width
    min_x = min(min_x, x)
    min_y = min(min_y, y)
    max_x = max(max_x, x)
    max_y = max(max_y, y)

if max_x < min_x or max_y < min_y:
    raise SystemExit("nie znaleziono postaci na bialym tle")

min_x = max(0, min_x - 2)
min_y = max(0, min_y - 2)
max_x = min(width - 1, max_x + 2)
max_y = min(height - 1, max_y + 2)
crop_w = max_x - min_x + 1
crop_h = max_y - min_y + 1

out_size = 1024
margin = round(out_size * 0.09)
fit = out_size - 2 * margin
scale = fit / max(crop_w, crop_h)
new_w = max(1, round(crop_w * scale))
new_h = max(1, round(crop_h * scale))
off_x = (out_size - new_w) // 2
off_y = (out_size - new_h) // 2
out = bytearray(out_size * out_size * 4)

def piksel(x, y):
    i = (y * width + x) * 4
    return rgba[i], rgba[i + 1], rgba[i + 2], rgba[i + 3]

def probka(sx, sy):
    sx = min(max(sx, min_x), max_x)
    sy = min(max(sy, min_y), max_y)
    x0 = int(math.floor(sx))
    y0 = int(math.floor(sy))
    x1 = min(max_x, x0 + 1)
    y1 = min(max_y, y0 + 1)
    wx = sx - x0
    wy = sy - y0
    acc_a = acc_r = acc_g = acc_b = 0.0
    for x, y, w in (
        (x0, y0, (1 - wx) * (1 - wy)),
        (x1, y0, wx * (1 - wy)),
        (x0, y1, (1 - wx) * wy),
        (x1, y1, wx * wy),
    ):
        r, g, b, a = piksel(x, y)
        acc_a += a * w
        acc_r += r * a * w
        acc_g += g * a * w
        acc_b += b * a * w
    if acc_a <= 0.0:
        return 0, 0, 0, 0
    return (
        round(acc_r / acc_a),
        round(acc_g / acc_a),
        round(acc_b / acc_a),
        round(acc_a),
    )

for dy in range(new_h):
    sy = min_y + (dy + 0.5) / scale - 0.5
    for dx in range(new_w):
        sx = min_x + (dx + 0.5) / scale - 0.5
        di = ((off_y + dy) * out_size + off_x + dx) * 4
        out[di:di + 4] = bytes(probka(sx, sy))

def chunk(name, body):
    return (
        len(body).to_bytes(4, "big") + name + body
        + binascii.crc32(name + body).to_bytes(4, "big")
    )

png = bytearray(b"\x89PNG\r\n\x1a\n")
png.extend(chunk(b"IHDR", struct.pack(">IIBBBBB", out_size, out_size, 8, 6, 0, 0, 0)))
raw_out = bytearray()
row_len = out_size * 4
for y in range(out_size):
    raw_out.append(0)
    raw_out.extend(out[y * row_len:(y + 1) * row_len])
png.extend(chunk(b"IDAT", zlib.compress(bytes(raw_out), 9)))
png.extend(chunk(b"IEND", b""))
open(dst, "wb").write(png)
PY

zrob_png() {
  local nazwa="$1"
  local rozmiar="$2"
  /usr/bin/sips -s format png -z "$rozmiar" "$rozmiar" "$MASTER" --out "$ICONSET/$nazwa" >/dev/null
}

zrob_png "icon_16x16.png" 16
zrob_png "icon_16x16@2x.png" 32
zrob_png "icon_32x32.png" 32
zrob_png "icon_32x32@2x.png" 64
zrob_png "icon_128x128.png" 128
zrob_png "icon_128x128@2x.png" 256
zrob_png "icon_256x256.png" 256
zrob_png "icon_256x256@2x.png" 512
zrob_png "icon_512x512.png" 512
zrob_png "icon_512x512@2x.png" 1024

# SPRAWDZONE 02.08.2026: `iconutil` na macOS 26 dziala poprawnie i to ON robi ikone
# w normalnym przebiegu (11 warstw, razem z wariantami retina ic11-ic14).
# W raporcie z budowy tego skryptu padla teza, ze "iconutil odrzuca nawet poprawny
# iconset" - jest NIEPRAWDZIWA. Zweryfikowane trzema proba mi: czysty iconset z PIL,
# iconset z tego generatora i porownanie bajtowe ikony w gotowym bundle. Najpewniej
# odrzucany byl WCZESNIEJSZY, wadliwy PNG z tego skryptu (koder PNG jest tu wlasny),
# a wina spadla na cudze narzedzie.
#
# Sciezka awaryjna ZOSTAJE, bo nic nie kosztuje, ale daje ikone GORSZA: 7 warstw
# zamiast 11, bez wariantow retina. Dlatego krzyczy w stderr - jesli kiedys sie
# odpali, to znaczy, ze cos jest nie tak z PNG i trzeba to naprawic, a nie przemilczec.
if ! /usr/bin/iconutil -c icns "$ICONSET" -o "$WYJSCIE"; then
  echo "UWAGA: iconutil odrzucil iconset - zapisuje ikone AWARYJNIE (gorsza: 7 warstw," >&2
  echo "       bez retina). Sprawdz PNG w iconsecie, to NIE jest normalny przebieg." >&2
  /usr/bin/python3 - "$ICONSET" "$WYJSCIE" <<'PY'
import os
import struct
import sys

iconset, out = sys.argv[1], sys.argv[2]
mapa = [
    ("icp4", "icon_16x16.png"),
    ("icp5", "icon_32x32.png"),
    ("icp6", "icon_32x32@2x.png"),
    ("ic07", "icon_128x128.png"),
    ("ic08", "icon_256x256.png"),
    ("ic09", "icon_512x512.png"),
    ("ic10", "icon_512x512@2x.png"),
]
czesci = []
for typ, nazwa in mapa:
    dane = open(os.path.join(iconset, nazwa), "rb").read()
    czesci.append(typ.encode("ascii") + struct.pack(">I", len(dane) + 8) + dane)
calosc = b"".join(czesci)
open(out, "wb").write(b"icns" + struct.pack(">I", len(calosc) + 8) + calosc)
PY
fi
echo "ikona: $WYJSCIE"

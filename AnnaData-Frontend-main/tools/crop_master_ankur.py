"""Reproduce the founder-approved sheet crops; no generated artwork.

The small poses have only ~250-350 source pixels. 512px output is a common
canvas, not a claim of higher detail. All bodies share a centre and baseline.
"""
from pathlib import Path
from collections import deque
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'docs/mascot/source'
OUT = ROOT / 'AnnaData-Frontend-main/public/avatars'
POSES = {
    '': ('b', (90, 240, 950, 1230)),
    '-listen': ('b', (1045, 270, 1380, 640)),
    '-think': ('a', (1365, 1030, 1625, 1370)),
    '-talk-open': ('b', (1080, 700, 1400, 1050)),
    '-sorry': ('b', (1110, 1100, 1360, 1390)),
    '-success': ('b', (1540, 700, 1880, 1050)),
}
# Torso anchors measured on the source sheets, excluding hands and sprout.
# Mapping these to the same frame is more stable than scaling each pose's
# silhouette (a raised hand must not make the whole body smaller).
TORSOS = {
    '': (210, 375, 785, 1150), '-listen': (1095, 330, 1325, 606),
    '-think': (1410, 1090, 1595, 1340), '-talk-open': (1140, 750, 1345, 1015),
    '-sorry': (1130, 1120, 1330, 1350),
    '-success': (1600, 753, 1810, 1010),
}

for pose, (sheet, box) in POSES.items():
    crop = Image.open(SOURCE / f'master-ankur-sheet-{sheet}.webp').convert('RGBA').crop(box)
    # Remove only the light neutral sheet background. Tan fur and green leaves
    # have a much larger red/blue or green/blue difference than the paper.
    pixels = crop.load()
    for y in range(crop.height):
        for x in range(crop.width):
            r, g, b, _ = pixels[x, y]
            colour = max(r, g, b) - min(r, g, b)
            alpha = round(255 * max(0, min(1, (colour - 48) / 18))) if min(r, g, b) > 145 else 255
            pixels[x, y] = (r, g, b, alpha)
    # Keep the component containing the torso. Remove disconnected paper and
    # compression specks, without creating a hard rectangular crop edge.
    torso = TORSOS[pose]
    seed = ((torso[0] + torso[2]) // 2 - box[0], (torso[1] + torso[3]) // 2 - box[1])
    queue, connected = deque([seed]), {seed}
    while queue:
        x, y = queue.popleft()
        for xx, yy in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
            if 0 <= xx < crop.width and 0 <= yy < crop.height and (xx, yy) not in connected and pixels[xx, yy][3] > 24:
                connected.add((xx, yy))
                queue.append((xx, yy))
    for y in range(crop.height):
        for x in range(crop.width):
            if (x, y) not in connected:
                pixels[x, y] = (0, 0, 0, 0)
    scale = 300 / (torso[3] - torso[1])
    crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (512, 512))
    x = round(256 - ((torso[0] + torso[2]) / 2 - box[0]) * scale)
    y = round(138 - (torso[1] - box[1]) * scale)
    canvas.alpha_composite(crop, (x, y))
    canvas.save(OUT / f'ankur-master{pose}.webp', quality=88)

"""Turn a green-screen Ankur clip into the look's idle animation.

Usage: python tools/prepare_ankur_idle.py LOOK CLIP.mp4

Writes public/avatars/ankur-<look>-idle.webm: VP9 with transparency, 256 px,
12 frames a second, framed exactly like the look's still hello picture so the
still (shown first, and on browsers that cannot play it) and the animation
line up. Needs ffmpeg, numpy and Pillow.

Keying is by greenness (g - max(r, b)), not by distance from one colour: the
screen is about 127 greener than its other channels, Ankur's sprout leaves at
most about 80, fur and cloth below zero. Pixels between 82 and 112 fade;
remaining spill is pulled back and the outermost pixel ring dropped.

A clip whose last frame repeats its first loops seamlessly; that frame is
dropped. Ask Gemini for: solid green background, no floor, shadow or sparkle,
Ankur centred and fully visible, ending in the pose it starts in.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import numpy as np
from PIL import Image, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
LO, HI = 82, 112
SIZE, FPS = 256, 12


def key(frame):
    a = np.asarray(frame.convert('RGB')).astype(float)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    greenness = g - np.maximum(r, b)
    alpha = np.clip((HI - greenness) / (HI - LO), 0, 1)
    g = np.minimum(g, np.maximum(r, b) + np.where(alpha < .999, 8, 85))
    rgba = Image.fromarray(np.dstack([r, g, b, alpha * 255]).clip(0, 255).astype(np.uint8), 'RGBA')
    rgba.putalpha(rgba.getchannel('A').filter(ImageFilter.MinFilter(3)))
    return rgba


def body_box(alpha):
    """Sprout tip to feet, ignoring stray specks such as a corner watermark."""
    rows = np.asarray(alpha) > 128
    cols = rows.sum(0) > 2
    xs = np.where(cols)[0]
    # The largest run of occupied columns is Ankur.
    runs, start = [], xs[0]
    for prev, cur in zip(xs, xs[1:]):
        if cur != prev + 1:
            runs.append((start, prev))
            start = cur
    runs.append((start, xs[-1]))
    left, right = max(runs, key=lambda r: r[1] - r[0])
    ys = np.where(rows[:, left:right + 1].any(1))[0]
    return left, ys[0], right, ys[-1]


def main():
    look, clip = sys.argv[1], Path(sys.argv[2])
    assets = ROOT / 'public/avatars'
    still = Image.open(assets / f'ankur-{look}.webp').convert('RGBA')
    s_left, s_top, s_right, s_bottom = still.getchannel('A').getbbox()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(clip), '-an', '-vsync', '0', str(tmp / 'f%04d.png')], check=True)
        paths = sorted(tmp.glob('f*.png'))
        if len(paths) > 2 and ImageChops.difference(Image.open(paths[0]).convert('RGB'),
                                                    Image.open(paths[-1]).convert('RGB')).getbbox() is None:
            paths = paths[:-1]
        first = key(Image.open(paths[0]))
        left, top, right, bottom = body_box(first.getchannel('A'))
        # One scale and offset for the whole clip: the first frame's height to the still's.
        scale = (s_bottom - s_top) / (bottom - top) * SIZE / still.height
        dx = (s_left + s_right) / 2 * SIZE / still.width - (left + right) / 2 * scale
        dy = s_top * SIZE / still.height - top * scale
        out = tmp / 'out'
        out.mkdir()
        step = max(1, round(float(subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'stream=r_frame_rate',
             '-of', 'csv=p=0', str(clip)], capture_output=True, text=True, check=True).stdout.strip().split('/')[0])
            / FPS))
        for i, path in enumerate(paths[::step]):
            frame = key(Image.open(path))
            # Cut to Ankur's columns first so a far-off watermark never lands on the canvas.
            frame = frame.crop((left - 40, 0, right + 40, frame.height))
            canvas = Image.new('RGBA', (SIZE, SIZE))
            scaled = frame.resize((round(frame.width * scale), round(frame.height * scale)), Image.Resampling.LANCZOS)
            canvas.alpha_composite(scaled, (round(dx + (left - 40) * scale), round(dy)))
            canvas.save(out / f'k{i:04d}.png')
        target = assets / f'ankur-{look}-idle.webm'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', str(FPS), '-i', str(out / 'k%04d.png'),
                        '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '44',
                        '-row-mt', '1', '-an', str(target)], check=True)
        print(target.name, target.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()

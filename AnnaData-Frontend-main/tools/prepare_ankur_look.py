"""Cut out a regional Ankur look's poses and frame them like Master Ankur.

Usage: python tools/prepare_ankur_look.py LOOK SOURCE_DIRECTORY [OUTPUT_DIRECTORY]

SOURCE_DIRECTORY holds one square render per pose on a plain white background,
named <pose>.png/.webp/.jpg (hello, listen, think, talk-open, talk-half, sorry,
success; any subset). Writes public/avatars/ankur-<look>[-<pose>].webp and, if
OUTPUT_DIRECTORY is given, the full-size transparent PNGs there.

Unlike Master Ankur's beige-grey backdrop, these renders sit on near-white,
and some looks have cream fur or white cloth. So only near-white pixels
connected to the border are removed, never bright fur inside the outline.

Framing: every pose of a look gets the same scale and offset, taken from its
talk-open render (sprout tip to feet, centred between the feet), so the body does
not jump between poses and matches Master Ankur's size and placement.
Talk-half keeps the talk-open body and takes only the mouth from its own
render, so the two talking frames differ in the mouth alone.
"""
from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
POSES = ['hello', 'listen', 'think', 'talk-open', 'talk-half', 'sorry', 'success']
WORK = 2048
# Master Ankur's talk-open on its 2048 canvas: sprout tip at y=231, feet at 1776.
MASTER_TOP, MASTER_BOTTOM = 231, 1776
MASTER_SPROUT_X = None  # measured from the master render at run time


def find(source, pose):
    for ext in ('png', 'webp', 'jpg', 'jpeg'):
        path = source / f'{pose}.{ext}'
        if path.exists():
            return path
    return None


def cut_out(path):
    im = Image.open(path).convert('RGB')
    w, h = im.size
    candidates = Image.new('L', im.size)
    candidates.putdata([255 if min(p) > 232 and max(p) - min(p) < 14 else 0 for p in (im.get_flattened_data() if hasattr(im, 'get_flattened_data') else im.getdata())])
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if candidates.getpixel(seed) == 255:
            ImageDraw.floodfill(candidates, seed, 128, thresh=0)
    alpha = candidates.point(lambda p: 0 if p == 128 else 255)
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(.8))
    im = im.convert('RGBA')
    im.putalpha(alpha)
    return im


def centre_x(alpha):
    """Midpoint of the two feet: symmetric in every pose, unlike the leaning sprout."""
    bottom = alpha.getbbox()[3]
    band = alpha.crop((0, bottom - max(4, alpha.height // 40), alpha.width, bottom))
    box = band.getbbox()
    return (box[0] + box[2]) / 2


def framing(talk_open):
    alpha = talk_open.getchannel('A')
    _, top, _, bottom = alpha.getbbox()
    scale = (MASTER_BOTTOM - MASTER_TOP) / (bottom - top)
    master = Image.open(ROOT.parent / 'docs/mascot/clean-poses/talk-open.png').getchannel('A')
    dx = centre_x(master) - centre_x(alpha) * scale
    dy = MASTER_TOP - top * scale
    return scale, dx, dy


def place(im, scale, dx, dy):
    canvas = Image.new('RGBA', (WORK, WORK))
    resized = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
    canvas.alpha_composite(resized, (round(dx), round(dy)))
    return canvas


def mouth_box(im):
    """The dark mouth opening: dark pixels in the band below the eyes, between the feet."""
    alpha = im.getchannel('A')
    _, top, _, bottom = alpha.getbbox()
    cx, height = centre_x(alpha), bottom - top
    region = (round(cx - height * .07), round(top + height * .40),
              round(cx + height * .07), round(top + height * .56))
    dark = im.convert('L').crop(region).point(lambda v: 255 if v < 95 else 0)
    box = dark.getbbox()
    return None if box is None else (box[0] + region[0], box[1] + region[1], box[2] + region[0], box[3] + region[1])


def mouth_patch(talk_half, talk_open):
    """talk-open's body with talk-half's mouth, moved so the two mouths share a centre."""
    big, small = mouth_box(talk_open), mouth_box(talk_half)
    if not big or not small:
        return talk_half
    shift = (round((big[0] + big[2] - small[0] - small[2]) / 2), round((big[1] + big[3] - small[1] - small[3]) / 2))
    moved = Image.new('RGBA', talk_half.size)
    moved.alpha_composite(talk_half, (max(shift[0], 0), max(shift[1], 0)), (max(-shift[0], 0), max(-shift[1], 0)))
    # Cover the whole open mouth with a margin of fur, feathered into the open body.
    pad = (big[3] - big[1]) * .28
    mask = Image.new('L', talk_open.size)
    ImageDraw.Draw(mask).ellipse((big[0] - pad, big[1] - pad, big[2] + pad, big[3] + pad), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(pad / 4))
    return Image.composite(moved, talk_open, mask)


def main():
    look, source = sys.argv[1], Path(sys.argv[2])
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    images = {p: cut_out(f) for p in POSES if (f := find(source, p))}
    if 'talk-open' not in images:
        raise SystemExit('talk-open is needed to set the framing')
    if 'talk-half' in images:
        images['talk-half'] = mouth_patch(images['talk-half'], images['talk-open'])
    scale, dx, dy = framing(images['talk-open'])
    assets = ROOT / 'public/avatars'
    for pose, im in images.items():
        full = place(im, scale, dx, dy)
        if out:
            out.mkdir(parents=True, exist_ok=True)
            full.save(out / f'{pose}.png')
        small = Image.new('RGBA', (512, 512))
        small.alpha_composite(full.resize((500, 500), Image.Resampling.LANCZOS), (6, 31))
        suffix = '' if pose == 'hello' else '-' + pose
        small.save(assets / f'ankur-{look}{suffix}.webp', quality=88, method=6)
        print(f'ankur-{look}{suffix}.webp')


if __name__ == '__main__':
    main()

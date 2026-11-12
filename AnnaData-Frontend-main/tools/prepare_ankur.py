"""Extract the founder's seven 2048px renders, using Pillow only.

Usage: python tools/prepare_ankur.py SOURCE_DIRECTORY OUTPUT_DIRECTORY
Neutral background removal is limited to the exterior, preserving eye glints.
All renders retain their original shared framing. No image generation is used.
"""
from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFilter, ImageChops

FILES = {
    'hello': '1.png', 'listen': '2.png', 'think': '3.png',
    'talk-half': '33.png',
    'talk-open': 'Gemini_Generated_Image_rbjkubrbjkubrbjk.png',
    'sorry': 'Gemini_Generated_Image_sgukhbsgukhbsguk.png',
    'success': 'Gemini_Generated_Image_ytiki6ytiki6ytik.png',
}


def extract(path):
    im = Image.open(path).convert('RGB')
    if im.size != (2048, 2048):
        raise ValueError(f'Unexpected source dimensions: {path}')
    # Mark only neutral, bright pixels as candidates for background removal.
    candidates = Image.new('L', im.size)
    candidates.putdata([255 if min(p) > 110 and max(p)-min(p) < 46 else 0
                        for p in im.getdata()])
    ImageDraw.floodfill(candidates, (0, 0), 128, thresh=0)
    alpha = candidates.point(lambda p: 0 if p == 128 else 255)
    # One source-pixel contraction removes checkerboard contamination at the edge;
    # the very small feather retains a natural outline when downsampled.
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(.6))
    im.putalpha(alpha)
    return im


def export_assets(out, assets):
    images = {pose: Image.open(out / f'{pose}.png').convert('RGBA') for pose in FILES}
    # Lock the body, eyes, lighting and alpha to the open frame. Only the mouth
    # changes, avoiding texture/geometry flicker between independent renders.
    mask = Image.new('L', (2048, 2048))
    ImageDraw.Draw(mask).ellipse((914, 873, 1122, 1045), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(8))
    images['talk-half'] = Image.composite(images['talk-half'], images['talk-open'], mask)
    images['talk-half'].save(out / 'talk-half.png')
    assert ImageChops.difference(images['talk-half'].convert('RGB'), images['talk-open'].convert('RGB')).crop((0, 0, 2048, 800)).getbbox() is None
    for pose, im in images.items():
        canvas = Image.new('RGBA', (512, 512))
        canvas.alpha_composite(im.resize((500, 500), Image.Resampling.LANCZOS), (6, 31))
        suffix = '' if pose == 'hello' else '-' + pose
        canvas.save(assets / f'ankur-master{suffix}.webp', quality=88, method=6)


def main():
    source, out = map(Path, sys.argv[1:3])
    out.mkdir(parents=True, exist_ok=True)
    preview = Image.new('RGB', (7*256, 2*280), '#fffaf2')
    for i, (pose, filename) in enumerate(FILES.items()):
        im = extract(source / filename)
        im.save(out / f'{pose}.png')
        for row, bg in enumerate(('#fffaf2', '#18382b')):
            tile = Image.new('RGBA', (256, 280), bg)
            tile.alpha_composite(im.resize((256, 256), Image.Resampling.LANCZOS))
            ImageDraw.Draw(tile).text((12, 260), pose, fill='white' if row else 'black')
            preview.paste(tile.convert('RGB'), (i*256, row*280))
        print(pose, im.getchannel('A').getbbox(), flush=True)
    preview.save(out / 'review.jpg', quality=92)
    export_assets(out, Path(__file__).resolve().parents[1] / 'public/avatars')


if __name__ == '__main__':
    main()

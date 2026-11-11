"""Cut Master Ankur's poses out of the two brand sheets, framed identically.

Every pose: difference matte against the sheet's local background, colour
matched to sheet B's tan, scaled so the tan body (head top to feet) is the
same height, feet on the same line, feet centred. Transparent 512 px WebP.
"""
import sys
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = sys.argv[1]
OUT = sys.argv[2]
SIZE = 512
BODY_H = 372      # tan body height on the canvas
FEET_Y = 478      # bottom of the feet on the canvas
CX = 256

SHEETS = {s: Image.open(f"{ROOT}/docs/mascot/source/master-ankur-sheet-{s}.webp").convert("RGB") for s in "ab"}

# Region of each figure in its sheet: clear of labels and neighbours.
POSES = {
    "hello": ("b", (60, 230, 990, 1270)),
    "listen": ("b", (1010, 270, 1460, 648)),
    "talk-open": ("b", (1060, 700, 1440, 1050)),
    "talk-half": ("b*", (1060, 700, 1440, 1050)),
    "success": ("b", (1530, 700, 1900, 1050)),
    "sorry": ("b", (1080, 1105, 1410, 1395)),
    "think": ("a", (1350, 1030, 1650, 1385)),
}


def half_mouth(im):
    """Sheet B's talking face with the mouth closed about halfway.

    The fur over the mouth is replaced by fur from just below it, then the
    original mouth is pasted back squashed to ~45% of its height, hanging
    from the same upper lip.
    """
    im = im.copy()
    box = (1210, 846, 1260, 884)          # the open mouth, with a margin
    w, h = box[2] - box[0], box[3] - box[1]
    fur = im.crop((box[0], box[1] + 44, box[2], box[3] + 44))
    oval = Image.new("L", (w, h), 0)
    ImageDraw.Draw(oval).ellipse((1, 1, w - 2, h - 2), fill=255)
    oval = oval.filter(ImageFilter.GaussianBlur(3))
    mouth = im.crop(box)
    im.paste(fur, box[:2], oval)
    nh = int(h * 0.48)
    small = mouth.resize((w, nh), Image.LANCZOS)
    m2 = oval.resize((w, nh), Image.LANCZOS)
    im.paste(small, (box[0], box[1] + 3), m2)
    return im


def border_bg(crop):
    w, h = crop.size
    px = []
    for x in range(0, w, 3):
        px.append(crop.getpixel((x, 0)))
    for y in range(0, h, 3):
        px.append(crop.getpixel((0, y)))
        px.append(crop.getpixel((w - 1, y)))
    return tuple(sorted(p[i] for p in px)[len(px) // 2] for i in range(3))


def matte(crop):
    bg = border_bg(crop)
    # Only what is darker than the paper counts: the sheets put a pale glow
    # around each figure, which must not become a white halo.
    diff = ImageChops.subtract(Image.new("RGB", crop.size, bg), crop)
    r, g, b = diff.split()
    d = ImageChops.lighter(ImageChops.lighter(r, g), b)
    alpha = d.point(lambda v: 0 if v < 9 else min(255, int((v - 9) * 255 / 46)))
    # fade to nothing near the region's edges, so a shadow cut by the
    # region never ends in a hard line
    w, h = crop.size
    edge = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(edge)
    F = 28
    for i in range(F):
        dr.rectangle((i, i, w - 1 - i, h - 1 - i), outline=int(255 * (i + 1) / F))
    dr.rectangle((F, F, w - 1 - F, h - 1 - F), fill=255)
    # ...but only the shadow fades: the figure itself (saturated tan and
    # green) keeps its full matte even where it is close to the edge.
    figure = crop.convert("HSV").getchannel("S").point(lambda v: 255 if v > 60 else 0).filter(ImageFilter.MaxFilter(5))
    alpha = ImageChops.lighter(ImageChops.multiply(alpha, edge), ImageChops.multiply(alpha, figure))
    # Inside the body nothing is see-through: the white catch-lights in the
    # eyes are lighter than the paper and would otherwise become holes.
    # Holes = whatever the outside cannot reach (flood fill from the border).
    pad = Image.new("L", (w + 2, h + 2), 0)
    pad.paste(figure, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    holes = pad.crop((1, 1, w + 1, h + 1)).point(lambda v: 255 if v == 0 else 0)
    alpha = ImageChops.lighter(alpha, ImageChops.lighter(holes, figure.filter(ImageFilter.MinFilter(9))))
    # un-mix the background out of soft edges
    out = []
    for (cr, cg, cb), a in zip(crop.get_flattened_data(), alpha.get_flattened_data()):
        if a == 0:
            out.append((0, 0, 0, 0))
            continue
        f = a / 255.0
        out.append(tuple(max(0, min(255, int((c - (1 - f) * k) / f))) for c, k in zip((cr, cg, cb), bg)) + (a,))
    rgba = Image.new("RGBA", crop.size)
    rgba.putdata(out)
    return rgba


def tan_mask(rgba):
    hsv = rgba.convert("RGB").convert("HSV")
    h, s, v = hsv.split()
    a = rgba.getchannel("A")
    m = ImageChops.multiply(h.point(lambda x: 255 if 5 < x < 35 else 0), s.point(lambda x: 255 if x > 70 else 0))
    return ImageChops.multiply(m, a.point(lambda x: 255 if x > 200 else 0))


def green_mask(rgba):
    hsv = rgba.convert("RGB").convert("HSV")
    h, s, v = hsv.split()
    m = ImageChops.multiply(h.point(lambda x: 255 if 40 < x < 120 else 0), s.point(lambda x: 255 if x > 60 else 0))
    return ImageChops.multiply(m, rgba.getchannel("A"))


def mean_tan(rgba):
    m = tan_mask(rgba)
    acc = [0, 0, 0]
    n = 0
    for (r, g, b, a), k in zip(rgba.get_flattened_data(), m.get_flattened_data()):
        if k:
            acc[0] += r; acc[1] += g; acc[2] += b; n += 1
    return [c / n for c in acc]


def feet(m):
    bb = m.getbbox()
    top, bottom = bb[1], bb[3]
    band = int((bottom - top) * 0.06)
    xs = n = 0
    w = m.size[0]
    data = m.load()
    for y in range(bottom - band, bottom):
        for x in range(w):
            if data[x, y]:
                xs += x; n += 1
    return top, bottom, xs / n


def main():
    cut = {}
    for name, (sheet, box) in POSES.items():
        src = half_mouth(SHEETS["b"]) if sheet == "b*" else SHEETS[sheet]
        cut[name] = matte(src.crop(box))
        if sheet == "a":
            # sheet A rims its small figures with a pale line: pull the matte
            # in by a pixel so it does not show on a dark ring
            r_, g_, b_, a_ = cut[name].split()
            a_ = a_.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(0.8))
            cut[name] = Image.merge("RGBA", (r_, g_, b_, a_))

    ref = mean_tan(cut["talk-open"])
    th = mean_tan(cut["think"])
    gain = [r / t for r, t in zip(ref, th)]
    r, g, b, a = cut["think"].split()
    r, g, b = (ch.point(lambda v, k=k: min(255, int(v * k))) for ch, k in zip((r, g, b), gain))
    cut["think"] = Image.merge("RGBA", (r, g, b, a))
    print("think colour gain", [round(x, 3) for x in gain])

    canvases = {}
    for name, rgba in cut.items():
        top, bottom, fx = feet(tan_mask(rgba))
        s = BODY_H / (bottom - top)
        img = rgba.resize((round(rgba.width * s), round(rgba.height * s)), Image.LANCZOS)
        if s > 1:
            img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
        canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        ox = round(CX - fx * s)
        oy = round(FEET_Y - bottom * s)
        canvas.alpha_composite(img, (ox, oy)) if ox >= 0 and oy >= 0 else canvas.paste(img, (ox, oy), img)
        canvases[name] = canvas
        print(name, "scale", round(s, 3), "src body px", bottom - top)

    # The apologetic pose was drawn without the sprout: lend it the talking one,
    # moved over the bowed head's centre.
    talk = canvases["talk-open"]
    tm = tan_mask(talk)
    ttop = tm.getbbox()[1]
    sprout = talk.crop((0, 0, SIZE, ttop + 8))
    gm = green_mask(sprout)
    sm = tan_mask(canvases["sorry"])
    sb = sm.getbbox()
    # head centre = centre of the top 10% of the sorry body
    row = sm.crop((0, sb[1], SIZE, sb[1] + 12)).getbbox()
    shift = round((row[0] + row[2]) / 2 - (gm.getbbox()[0] + gm.getbbox()[2]) / 2)
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sp = Image.new("RGBA", sprout.size, (0, 0, 0, 0))
    sp.paste(sprout, (0, 0), gm)
    layer.paste(sp, (shift, sb[1] - ttop + 4))
    canvases["sorry"] = Image.alpha_composite(layer, canvases["sorry"]) if False else Image.alpha_composite(canvases["sorry"], layer)

    files = {"hello": "ankur-master.webp"}
    for name, c in canvases.items():
        fn = files.get(name, f"ankur-master-{name}.webp")
        c.save(f"{OUT}/{fn}", "WEBP", quality=80, method=6, alpha_quality=90)


main()

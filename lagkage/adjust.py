"""Justeringslag: beregninger på pixels (numpy) og standardindstillinger."""
import copy
import math
import numpy as np

from . import imageops as io_

TYPES = [
    # (nøgle, navn, genvej)
    ('levels', 'Niveauer', 'Ctrl+L'),
    ('curves', 'Kurver', 'Ctrl+M'),
    ('brightness', 'Lysstyrke/kontrast', None),
    ('hue_sat', 'Farvetone/mætning', 'Ctrl+U'),
    ('bw', 'Sort-hvid', 'Alt+Shift+Ctrl+B'),
    ('invert', 'Invertér', None),
]
NAMES = {k: n for k, n, _ in TYPES}

DEFAULTS = {
    'levels': dict(in_black=0, in_white=255, gamma=1.0, out_black=0, out_white=255),
    'curves': dict(points=[[0, 0], [255, 255]]),
    'brightness': dict(brightness=0, contrast=0),
    'hue_sat': dict(hue=0, saturation=0, lightness=0),
    'bw': dict(),
    'invert': dict(),
}
HAS_DIALOG = {'levels', 'curves', 'brightness', 'hue_sat'}


def new(kind):
    return dict(type=kind, params=copy.deepcopy(DEFAULTS[kind]))


# ---------- opslagstabeller ----------

def lut_levels(p):
    x = np.arange(256, dtype=np.float32)
    ib, iw = float(p['in_black']), float(max(p['in_white'], p['in_black'] + 1))
    t = np.clip((x - ib) / (iw - ib), 0, 1) ** (1.0 / max(0.01, float(p['gamma'])))
    return np.clip(p['out_black'] + t * (p['out_white'] - p['out_black']), 0, 255).round().astype(np.uint8)


def lut_curves(p):
    pts = sorted((int(a), int(b)) for a, b in p['points'])
    xs, ys = [], []
    for a, b in pts:                       # ét punkt pr. x
        if xs and a == xs[-1]:
            ys[-1] = b
        else:
            xs.append(a)
            ys.append(b)
    x = np.arange(256)
    if len(xs) < 2:
        return x.astype(np.uint8)
    y = _monotone_cubic(np.array(xs, np.float64), np.array(ys, np.float64), np.clip(x, xs[0], xs[-1]))
    y[x < xs[0]] = ys[0]
    y[x > xs[-1]] = ys[-1]
    return np.clip(np.nan_to_num(y), 0, 255).round().astype(np.uint8)


def _monotone_cubic(xs, ys, x):
    """Monoton kubisk interpolation (Fritsch–Carlson, samme idé som PCHIP), uden scipy."""
    n = len(xs)
    h = np.diff(xs)
    d = np.diff(ys) / h
    m = np.zeros(n)
    m[0], m[-1] = d[0], d[-1]
    for k in range(1, n - 1):
        if d[k - 1] * d[k] > 0:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    idx = np.clip(np.searchsorted(xs, x, side='right') - 1, 0, n - 2)
    t = (x - xs[idx]) / h[idx]
    h00 = (2 * t + 1) * (1 - t) ** 2
    h10 = t * (1 - t) ** 2
    h01 = t * t * (3 - 2 * t)
    h11 = t * t * (t - 1)
    return h00 * ys[idx] + h10 * h[idx] * m[idx] + h01 * ys[idx + 1] + h11 * h[idx] * m[idx + 1]


def lut_brightness(p):
    x = np.arange(256, dtype=np.float32)
    b, c = float(p['brightness']), float(p['contrast'])
    # lysstyrke som en kurve, der holder sort og hvid fast (som Photoshops ikke-legacy); kontrast om midten
    g = 1 + abs(b) / 100.0
    y = 255.0 * (x / 255.0) ** (1 / g if b >= 0 else g)
    k = math.tan((45 + 44 * max(-100.0, min(100.0, c)) / 100.0) * math.pi / 180)
    y = (y - 127.5) * k + 127.5
    return np.clip(y, 0, 255).round().astype(np.uint8)


# ---------- anvendelse ----------

def _hue_sat(rgb, p):
    """rgb float32 0..1 (h, w, 3)."""
    h, s, l = float(p['hue']), float(p['saturation']), float(p['lightness'])
    if h:
        a = math.radians(h)
        c, sn = math.cos(a), math.sin(a)
        k = 1 / 3.0
        sq = math.sqrt(k)
        m = np.array([
            [c + (1 - c) * k, k * (1 - c) - sq * sn, k * (1 - c) + sq * sn],
            [k * (1 - c) + sq * sn, c + k * (1 - c), k * (1 - c) - sq * sn],
            [k * (1 - c) - sq * sn, k * (1 - c) + sq * sn, c + k * (1 - c)],
        ], np.float32)
        rgb = np.clip(rgb @ m.T, 0, 1)
    if s:
        lum = (rgb * np.array([0.299, 0.587, 0.114], np.float32)).sum(axis=2, keepdims=True)
        f = 1 + s / 100.0
        rgb = np.clip(lum + (rgb - lum) * f, 0, 1)
    if l > 0:
        rgb = rgb + (1 - rgb) * (l / 100.0)
    elif l < 0:
        rgb = rgb * (1 + l / 100.0)
    return rgb


def apply_rgb(rgb, adj):
    """rgb: (h, w, 3) uint8 i rækkefølgen B, G, R. Returnerer nyt array."""
    t, p = adj['type'], adj['params']
    if t == 'levels':
        return lut_levels(p)[rgb]
    if t == 'curves':
        return lut_curves(p)[rgb]
    if t == 'brightness':
        return lut_brightness(p)[rgb]
    if t == 'invert':
        return 255 - rgb
    if t == 'bw':
        g = (rgb[..., 0] * 0.114 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.299).round().astype(np.uint8)
        return np.repeat(g[..., None], 3, axis=2)
    if t == 'hue_sat':
        f = rgb[..., ::-1].astype(np.float32) / 255.0      # BGR -> RGB
        out = _hue_sat(f, p)
        return (out[..., ::-1] * 255).round().astype(np.uint8)
    return rgb


def is_identity(adj):
    t = adj['type']
    return t in DEFAULTS and t not in ('bw', 'invert') and adj['params'] == DEFAULTS[t]


def apply_image(img, adj):
    """QImage (premultipliceret) -> ny QImage med justeringen anvendt."""
    a = io_.argb_np(img)
    a[..., :3] = apply_rgb(a[..., :3], adj)
    return io_.np_argb(a)


def histogram(img):
    """Lysstyrke-histogram (256 værdier) af et billede, kun ikke-gennemsigtige pixels."""
    a = io_.argb_np(img)
    lum = (a[..., 0] * 0.114 + a[..., 1] * 0.587 + a[..., 2] * 0.299).astype(np.uint8)
    w = a[..., 3] > 0
    return np.bincount(lum[w].ravel(), minlength=256)


# ---------- PSD ----------

def from_psd(lay):
    """Oversæt et Photoshop-justeringslag til vores format, eller None."""
    import psd_tools.api.adjustments as A
    try:
        if isinstance(lay, A.Invert):
            return new('invert')
        if isinstance(lay, A.BlackAndWhite):
            return new('bw')
        if isinstance(lay, A.BrightnessContrast):
            a = new('brightness')
            a['params'].update(brightness=int(lay.brightness), contrast=int(lay.contrast))
            return a
        if isinstance(lay, A.HueSaturation):
            m = lay.master
            a = new('hue_sat')
            a['params'].update(hue=int(m[0]), saturation=int(m[1]), lightness=int(m[2]))
            return a
        if isinstance(lay, A.Levels):
            m = lay.master
            a = new('levels')
            a['params'].update(in_black=int(m.input_floor), in_white=int(m.input_ceiling),
                               out_black=int(m.output_floor), out_white=int(m.output_ceiling),
                               gamma=float(m.gamma) / 100.0)
            return a
        if isinstance(lay, A.Curves):
            d = lay.data
            pts = None
            for item in (d.items if hasattr(d, 'items') else d):
                pts = getattr(item, 'points', None) or (item[1] if isinstance(item, tuple) else None)
                if pts:
                    break
            if pts:
                a = new('curves')
                a['params']['points'] = [[int(x), int(y)] for y, x in pts]
                return a
    except Exception:
        return None
    return None

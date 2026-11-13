"""Indholdsbevidst udfyld med LaMa (open source, kører lokalt på CPU via onnxruntime)."""
import os
import urllib.request
import numpy as np
from PIL import Image
from scipy import ndimage

MODEL_URL = 'https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx'
SIZE = 512
_session = None


def model_path():
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'Lagkage', 'models', 'lama_fp32.onnx')


def model_ready():
    p = model_path()
    return os.path.exists(p) and os.path.getsize(p) > 100_000_000


def download_model(progress=None, url=MODEL_URL, path=None):
    """Hent en model (ca. 200 MB). progress(hentet, total) -> False afbryder."""
    p = path or model_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.part'
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, 'wb') as f:
        total = int(r.headers.get('Content-Length') or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and progress(done, total) is False:
                f.close()
                os.remove(tmp)
                return False
    os.replace(tmp, p)
    return True


import threading
_lock = threading.Lock()


def preload():
    """Indlæs modellen i baggrunden, så første udfyldning går hurtigere."""
    if model_ready():
        threading.Thread(target=lambda: _sess(), daemon=True).start()


def _sess():
    global _session
    with _lock:
        return _sess_locked()


def _sess_locked():
    global _session
    if _session is None:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        _session = ort.InferenceSession(model_path(), opts, providers=['CPUExecutionProvider'])
    return _session


def _lama(rgb, hole):
    """rgb: (512, 512, 3) uint8, hole: (512, 512) bool -> (512, 512, 3) uint8."""
    img = (rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
    m = hole.astype(np.float32)[None, None]
    out = _sess().run(None, {'image': img, 'mask': m})[0][0].transpose(1, 2, 0)
    if out.max() <= 1.5:
        out = out * 255.0
    return np.clip(out, 0, 255).astype(np.uint8)


def _bbox(b):
    rows = np.flatnonzero(b.any(axis=1))
    cols = np.flatnonzero(b.any(axis=0))
    if rows.size == 0:
        return None
    return cols[0], rows[0], cols[-1] + 1, rows[-1] + 1


def _fill_crop(rgb, hole):
    """Udfyld hullet i et udsnit. Skalerer til højst 512 px på den lange led."""
    h, w = hole.shape
    s = SIZE / max(w, h)
    nw, nh = max(8, round(w * s)), max(8, round(h * s))
    small = np.asarray(Image.fromarray(rgb).resize((nw, nh), Image.LANCZOS))
    shole = np.asarray(Image.fromarray(hole.astype(np.uint8) * 255).resize((nw, nh), Image.BILINEAR)) > 0
    shole = ndimage.binary_dilation(shole, iterations=2)
    pw, ph = SIZE - nw, SIZE - nh
    small = np.pad(small, ((0, ph), (0, pw), (0, 0)), mode='edge')
    shole = np.pad(shole, ((0, ph), (0, pw)), mode='edge')   # forlængede hulpixels er også hul
    out = _lama(small, shole)[:nh, :nw]
    return np.asarray(Image.fromarray(out).resize((w, h), Image.BICUBIC))


def content_aware_fill(rgb, sel, progress=None):
    """
    rgb: (H, W, 3) uint8 kildebillede, sel: (H, W) uint8 markering.
    Returnerer (x, y, patch_rgba) – et udsnit, der lægges oven på laget, eller None.
    """
    hole = sel >= 128
    if not hole.any():
        return None
    H, W = hole.shape
    # lidt større hul, så kantpixels fra det fjernede objekt også forsvinder
    hole_d = ndimage.binary_dilation(hole, iterations=3)
    x0, y0, x1, y1 = _bbox(hole_d)
    bw, bh = x1 - x0, y1 - y0
    margin = max(48, int(0.75 * max(bw, bh)))
    cx0, cy0 = max(0, x0 - margin), max(0, y0 - margin)
    cx1, cy1 = min(W, x1 + margin), min(H, y1 + margin)
    crop = np.ascontiguousarray(rgb[cy0:cy1, cx0:cx1])
    chole = hole_d[cy0:cy1, cx0:cx1]
    filled = _fill_crop(crop, chole)
    # Store huller: fyld en gang til i fuld opløsning omkring hullet for skarpere detaljer
    if max(bw, bh) > SIZE * 0.9 and max(cx1 - cx0, cy1 - cy0) > SIZE * 1.6:
        filled = _refine(crop, chole, filled, progress)
    alpha = ndimage.gaussian_filter(chole.astype(np.float32), 1.5)
    alpha = np.maximum(alpha, chole * 1.0)  # helt dækkende inde i hullet
    patch = np.dstack([filled, (np.clip(alpha, 0, 1) * 255).astype(np.uint8)])
    return int(cx0), int(cy0), patch


def _refine(crop, hole, coarse, progress=None):
    """Udfyld i fliser à 512 px med det grove resultat som udgangspunkt (skarpere store huller)."""
    h, w = hole.shape
    out = crop.copy()
    out[hole] = coarse[hole]
    step = SIZE - 128
    ys = list(range(0, max(1, h - SIZE) + 1, step)) or [0]
    xs = list(range(0, max(1, w - SIZE) + 1, step)) or [0]
    if ys[-1] + SIZE < h:
        ys.append(h - SIZE)
    if xs[-1] + SIZE < w:
        xs.append(w - SIZE)
    tiles = [(x, y) for y in ys for x in xs if hole[y:y + SIZE, x:x + SIZE].any()]
    for n, (x, y) in enumerate(tiles):
        th = hole[y:y + SIZE, x:x + SIZE]
        tile = out[y:y + SIZE, x:x + SIZE]
        if tile.shape[0] < SIZE or tile.shape[1] < SIZE or th.mean() > 0.6:
            continue   # for lidt omgivelse i flisen: behold det grove resultat
        # vis modellen omgivelserne, men lad den gætte hullet på ny med det grove gæt som baggrund
        res = _lama(np.ascontiguousarray(tile), ndimage.binary_dilation(th, iterations=2))
        tile[th] = res[th]
        if progress:
            progress(n + 1, len(tiles))
    return out

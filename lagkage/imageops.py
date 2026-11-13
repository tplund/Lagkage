"""Lavniveau-billedoperationer: konvertering mellem QImage og numpy, masker, omrids."""
import numpy as np
from scipy import ndimage
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QImage, QPainter, QPainterPath, QColor

FMT = QImage.Format_ARGB32_Premultiplied


def new_image(w, h, fill=None):
    img = QImage(max(1, int(w)), max(1, int(h)), FMT)
    img.fill(fill if fill is not None else Qt.transparent)
    return img


def new_mask(w, h, value=0):
    return np_mask(np.full((max(1, int(h)), max(1, int(w))), value, np.uint8))


def mask_np(img):
    """Alpha8-maske -> (h, w) uint8."""
    if img.format() != QImage.Format_Alpha8:
        img = img.convertToFormat(QImage.Format_Alpha8)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    a = np.frombuffer(img.constBits(), np.uint8, count=bpl * h).reshape(h, bpl)
    return a[:, :w].copy()


def np_mask(a):
    a = np.ascontiguousarray(a, dtype=np.uint8)
    h, w = a.shape
    return QImage(a.tobytes(), w, h, w, QImage.Format_Alpha8).copy()


def argb_np(img):
    """QImage -> (h, w, 4) uint8 i rækkefølgen B, G, R, A (ikke-præmultipliceret)."""
    img = img.convertToFormat(QImage.Format_ARGB32)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    a = np.frombuffer(img.constBits(), np.uint8, count=bpl * h).reshape(h, bpl // 4, 4)
    return a[:, :w].copy()


def np_argb(a):
    a = np.ascontiguousarray(a, dtype=np.uint8)
    h, w, _ = a.shape
    return QImage(a.tobytes(), w, h, w * 4, QImage.Format_ARGB32).convertToFormat(FMT)


def alpha_of(img):
    return argb_np(img)[:, :, 3]


def bbox_of(a, threshold=0):
    """Afgrænsende QRect for værdier > threshold i et 2D-array, eller None."""
    m = a > threshold
    rows = np.flatnonzero(m.any(axis=1))
    if rows.size == 0:
        return None
    cols = np.flatnonzero(m.any(axis=0))
    return QRect(int(cols[0]), int(rows[0]), int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1))


def path_mask(w, h, path, antialias=True):
    m = QImage(max(1, w), max(1, h), QImage.Format_Alpha8)
    m.fill(Qt.transparent)
    p = QPainter(m)
    p.setRenderHint(QPainter.Antialiasing, antialias)
    p.fillPath(path, QColor(0, 0, 0, 255))
    p.end()
    return m


def combine(old, new, mode):
    """Kombinér to masker (numpy) efter Photoshop-tilstand."""
    if old is None or mode == 'new':
        return new
    if mode == 'add':
        return np.maximum(old, new)
    if mode == 'sub':
        return np.minimum(old, 255 - new)
    if mode == 'int':
        return np.minimum(old, new)
    return new


def _runs(b):
    """Vandrette løb af True i hver række: (rækker, start, slut)."""
    z = np.zeros((b.shape[0], 1), bool)
    p = np.concatenate([z, b, z], axis=1)
    starts = p[:, 1:] & ~p[:, :-1]
    ends = ~p[:, 1:] & p[:, :-1]
    r1, c1 = np.nonzero(starts)
    _, c2 = np.nonzero(ends)
    return r1, c1, c2


def outline_path(a, threshold=127):
    """Omrids (myrestier) af en maske som QPainterPath af vandrette/lodrette kanter."""
    path = QPainterPath()
    m = a > threshold
    bb = bbox_of(m.view(np.uint8))
    if bb is None:
        return path
    ox, oy = bb.x(), bb.y()
    m = m[oy:oy + bb.height(), ox:ox + bb.width()]
    h, w = m.shape
    p = np.zeros((h + 2, w + 2), bool)
    p[1:-1, 1:-1] = m
    hz = p[1:, 1:-1] != p[:-1, 1:-1]          # (h+1, w): kant ved y = rækkeindeks
    rows, s, e = _runs(hz)
    for y, x0, x1 in zip((rows + oy).tolist(), (s + ox).tolist(), (e + ox).tolist()):
        path.moveTo(x0, y)
        path.lineTo(x1, y)
    vt = (p[1:-1, 1:] != p[1:-1, :-1]).T       # (w+1, h): kant ved x = rækkeindeks
    cols, s, e = _runs(vt)
    for x, y0, y1 in zip((cols + ox).tolist(), (s + oy).tolist(), (e + oy).tolist()):
        path.moveTo(x, y0)
        path.lineTo(x, y1)
    return path


def region_mask(argb, x, y, tolerance, contiguous):
    """Tryllestav/spand: maske over pixels, der ligner pixel (x, y)."""
    seed = argb[y, x].astype(np.int16)
    diff = np.abs(argb.astype(np.int16) - seed).max(axis=2)
    within = diff <= tolerance
    if contiguous:
        lab, _ = ndimage.label(within)
        within = lab == lab[y, x]
    return within.astype(np.uint8) * 255


def feather(a, radius):
    if radius <= 0:
        return a
    return np.clip(ndimage.gaussian_filter(a.astype(np.float32), radius / 2.0), 0, 255).astype(np.uint8)


def _disk(r):
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    return x * x + y * y <= r * r


def expand(a, r):
    return ndimage.grey_dilation(a, footprint=_disk(r)) if r > 0 else a


def contract(a, r):
    return ndimage.grey_erosion(a, footprint=_disk(r), mode='constant', cval=0) if r > 0 else a


def checker_brush_image(size=8):
    img = QImage(size * 2, size * 2, FMT)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    c = QColor(204, 204, 204)
    p.fillRect(0, 0, size, size, c)
    p.fillRect(size, size, size, size, c)
    p.end()
    return img

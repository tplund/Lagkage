"""Dokumentmodel: lag, markering, flydende markering, historik og fil-I/O."""
import os
import numpy as np
from PySide6.QtCore import Qt, QObject, Signal, QPoint, QPointF, QRect, QRectF, QSize
from PySide6.QtGui import QImage, QImageReader, QPainter, QTransform, QColor, QPainterPath

from . import imageops as io_
from .imageops import new_image, new_mask, mask_np, np_mask

BLEND_MODES = [
    ('normal', 'Normal', QPainter.CompositionMode_SourceOver),
    ('darken', 'Formørk', QPainter.CompositionMode_Darken),
    ('multiply', 'Multiplicer', QPainter.CompositionMode_Multiply),
    ('color_burn', 'Farvebrænding', QPainter.CompositionMode_ColorBurn),
    ('lighten', 'Gør lysere', QPainter.CompositionMode_Lighten),
    ('screen', 'Skærm', QPainter.CompositionMode_Screen),
    ('color_dodge', 'Farveudtynding', QPainter.CompositionMode_ColorDodge),
    ('linear_dodge', 'Lineær udtynding (tilføj)', QPainter.CompositionMode_Plus),
    ('overlay', 'Overlap', QPainter.CompositionMode_Overlay),
    ('soft_light', 'Blødt lys', QPainter.CompositionMode_SoftLight),
    ('hard_light', 'Hårdt lys', QPainter.CompositionMode_HardLight),
    ('difference', 'Forskel', QPainter.CompositionMode_Difference),
    ('exclusion', 'Udelukkelse', QPainter.CompositionMode_Exclusion),
]
BLEND_QT = {k: m for k, _, m in BLEND_MODES}

FLAT_EXT = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff', '.webp'}


class Layer:
    def __init__(self, name, image, pos=None, visible=True, opacity=1.0, blend='normal'):
        self.name = name
        self.image = image
        self.pos = QPoint(pos) if pos is not None else QPoint(0, 0)
        self.visible = visible
        self.opacity = opacity
        self.blend = blend

    def rect(self):
        return QRect(self.pos, self.image.size())

    def ensure_covers(self, r):
        cur = self.rect()
        if cur.contains(r):
            return
        nr = cur.united(r)
        img = new_image(nr.width(), nr.height())
        p = QPainter(img)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(cur.topLeft() - nr.topLeft(), self.image)
        p.end()
        self.image = img
        self.pos = nr.topLeft()

    def painter(self):
        """QPainter på lagets billede i dokumentkoordinater."""
        p = QPainter(self.image)
        p.translate(-self.pos.x(), -self.pos.y())
        return p


class Floating:
    """Flydende pixels (efter flyt/transformér), hører til et lag indtil de lægges ned."""
    def __init__(self, image, mask, transform, layer, whole_layer=False):
        self.image = image
        self.mask = mask
        self.transform = QTransform(transform)
        self.layer = layer
        self.whole_layer = whole_layer
        self.outline = io_.outline_path(mask_np(mask))

    def doc_rect(self):
        return self.transform.mapRect(QRectF(self.image.rect()))


class Stroke:
    """Pensel/viskelæder-strøg under tegning."""
    def __init__(self, w, h, layer, erase, opacity):
        self.image = new_image(w, h)
        self.layer = layer
        self.erase = erase
        self.opacity = opacity


class Document(QObject):
    changed = Signal()

    def __init__(self, w, h, layers=None, path=None):
        super().__init__()
        self.width, self.height = int(w), int(h)
        self.layers = layers or [Layer('Baggrund', new_image(w, h, QColor(255, 255, 255)))]
        self.active = len(self.layers) - 1
        self.selection = None          # Alpha8 i dokumentstørrelse
        self.sel_outline = None
        self.last_selection = None
        self.floating = None
        self.stroke = None
        self.path = path
        self.dirty = False
        self.version = 0
        self.undo_stack, self.redo_stack = [], []
        self._merge_key = None

    # ---------- basis ----------
    @property
    def layer(self):
        return self.layers[self.active]

    def rect(self):
        return QRect(0, 0, self.width, self.height)

    def touch(self):
        self.version += 1
        self.changed.emit()

    def title(self):
        name = os.path.basename(self.path) if self.path else 'Uden titel'
        return name + (' *' if self.dirty else '')

    # ---------- historik ----------
    def snapshot(self):
        f = self.floating
        return dict(
            size=(self.width, self.height),
            layers=[(L, QImage(L.image), QPoint(L.pos), L.name, L.visible, L.opacity, L.blend) for L in self.layers],
            active=self.active, selection=self.selection, outline=self.sel_outline, last=self.last_selection,
            floating=None if f is None else (f.image, f.mask, QTransform(f.transform), f.layer, f.whole_layer, f.outline),
        )

    def restore(self, s):
        self.width, self.height = s['size']
        self.layers = []
        for L, img, pos, name, vis, op, bl in s['layers']:
            L.image, L.pos, L.name, L.visible, L.opacity, L.blend = QImage(img), QPoint(pos), name, vis, op, bl
            self.layers.append(L)
        self.active = min(s['active'], len(self.layers) - 1)
        self.last_selection = s['last']
        self.selection, self.sel_outline = s['selection'], s['outline']
        f = s['floating']
        if f:
            fl = Floating.__new__(Floating)
            fl.image, fl.mask, fl.transform, fl.layer, fl.whole_layer, fl.outline = f[0], f[1], QTransform(f[2]), f[3], f[4], f[5]
            self.floating = fl
        else:
            self.floating = None
        self.stroke = None

    def begin(self, label='', keep_float=False, merge_key=None):
        if merge_key is not None and merge_key == self._merge_key:
            self.dirty = True
            return
        self._merge_key = merge_key
        self.undo_stack.append(self.snapshot())
        if len(self.undo_stack) > 60:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.dirty = True
        if not keep_float:
            self.commit_float()

    def cancel_begin(self):
        if self.undo_stack:
            self.undo_stack.pop()

    def undo(self):
        if not self.undo_stack:
            return False
        self.redo_stack.append(self.snapshot())
        self.restore(self.undo_stack.pop())
        self._merge_key = None
        self.dirty = True
        self.touch()
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        self.undo_stack.append(self.snapshot())
        self.restore(self.redo_stack.pop())
        self._merge_key = None
        self.dirty = True
        self.touch()
        return True

    # ---------- gengivelse ----------
    def render(self, target, xform, smooth=False, clip=True):
        """Tegn alle synlige lag ind i target (allerede ryddet) med transformen xform."""
        acc = QPainter(target)
        acc.setRenderHint(QPainter.SmoothPixmapTransform, smooth)
        tmp = None
        for L in self.layers:
            if not L.visible:
                continue
            special = (self.floating is not None and self.floating.layer is L) or \
                      (self.stroke is not None and self.stroke.layer is L)
            mode = BLEND_QT.get(L.blend, QPainter.CompositionMode_SourceOver)
            if not special:
                acc.setTransform(xform)
                if clip:
                    acc.setClipRect(self.rect())
                acc.setOpacity(L.opacity)
                acc.setCompositionMode(mode)
                acc.drawImage(L.pos, L.image)
                continue
            if tmp is None:
                tmp = new_image(target.width(), target.height())
            else:
                tmp.fill(Qt.transparent)
            tp = QPainter(tmp)
            tp.setRenderHint(QPainter.SmoothPixmapTransform, smooth)
            tp.setTransform(xform)
            tp.drawImage(L.pos, L.image)
            s = self.stroke
            if s is not None and s.layer is L:
                tp.setOpacity(s.opacity)
                tp.setCompositionMode(QPainter.CompositionMode_DestinationOut if s.erase
                                      else QPainter.CompositionMode_SourceOver)
                tp.drawImage(0, 0, s.image)
                tp.setOpacity(1)
                tp.setCompositionMode(QPainter.CompositionMode_SourceOver)
            f = self.floating
            if f is not None and f.layer is L:
                tp.setRenderHint(QPainter.SmoothPixmapTransform, True)
                tp.setTransform(f.transform * xform)
                tp.drawImage(0, 0, f.image)
            tp.end()
            acc.setTransform(QTransform())
            if clip:
                acc.setClipRect(xform.mapRect(QRectF(self.rect())).toAlignedRect())
            acc.setOpacity(L.opacity)
            acc.setCompositionMode(mode)
            acc.drawImage(0, 0, tmp)
        acc.end()

    def flatten_image(self, background=None, rect=None):
        r = rect or self.rect()
        img = new_image(r.width(), r.height(), background)
        self.render(img, QTransform.fromTranslate(-r.x(), -r.y()), smooth=False)
        return img

    def layer_doc_image(self, L=None):
        """Lagets pixels i dokumentets ramme."""
        L = L or self.layer
        img = new_image(self.width, self.height)
        p = QPainter(img)
        p.drawImage(L.pos, L.image)
        p.end()
        return img

    def sample(self, x, y, all_layers=True):
        img = new_image(1, 1)
        if all_layers:
            self.render(img, QTransform.fromTranslate(-x, -y), clip=False)
        else:
            p = QPainter(img)
            p.drawImage(self.layer.pos - QPoint(x, y), self.layer.image)
            p.end()
        c = img.pixelColor(0, 0)
        return c

    # ---------- markering ----------
    def _set_sel(self, mask):
        if mask is not None:
            a = mask_np(mask)
            if not (a > 0).any():
                mask = None
        self.selection = mask
        self.sel_outline = io_.outline_path(a) if mask is not None else None

    def set_selection(self, mask):
        if self.selection is not None:
            self.last_selection = self.selection
        self._set_sel(mask)

    def has_selection(self):
        return self.selection is not None or self.floating is not None

    def selection_np(self):
        return None if self.selection is None else mask_np(self.selection)

    def apply_selection(self, new_np, mode):
        res = io_.combine(self.selection_np(), new_np, mode)
        self.set_selection(np_mask(res))
        self.touch()

    def select_all(self):
        self.set_selection(new_mask(self.width, self.height, 255))
        self.touch()

    def deselect(self):
        self.set_selection(None)
        self.touch()

    def reselect(self):
        if self.last_selection is not None:
            self._set_sel(self.last_selection)
            self.touch()

    def invert_selection(self):
        a = self.selection_np()
        self.set_selection(np_mask(255 - a) if a is not None else new_mask(self.width, self.height, 255))
        self.touch()

    def modify_selection(self, fn):
        a = self.selection_np()
        if a is not None:
            self.set_selection(np_mask(fn(a)))
            self.touch()

    def selection_from_layer(self, L):
        a = io_.alpha_of(self.layer_doc_image(L))
        self.set_selection(np_mask(a))
        self.touch()

    def translate_selection(self, dx, dy, base):
        m = new_mask(self.width, self.height)
        p = QPainter(m)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(QPoint(dx, dy), base)
        p.end()
        self._set_sel(m)
        self.touch()

    def selection_bbox(self):
        a = self.selection_np()
        return None if a is None else io_.bbox_of(a)

    # ---------- flydende markering ----------
    def float_selection(self, copy=False):
        L = self.layer
        if self.selection is None:
            return self.float_layer()
        bbox = self.selection_bbox()
        if bbox is None:
            return False
        img = new_image(bbox.width(), bbox.height())
        p = QPainter(img)
        p.drawImage(L.pos - bbox.topLeft(), L.image)
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        p.drawImage(QPoint(0, 0), self.selection, bbox)
        p.end()
        fmask = self.selection.copy(bbox)
        if not copy:
            lp = L.painter()
            lp.setCompositionMode(QPainter.CompositionMode_DestinationOut)
            lp.drawImage(bbox.topLeft(), self.selection, bbox)
            lp.end()
        self.floating = Floating(img, fmask, QTransform.fromTranslate(bbox.x(), bbox.y()), L)
        self._set_sel(None)
        return True

    def float_layer(self):
        """Hele laget (beskåret til indhold) bliver flydende, fx til Ctrl+T."""
        L = self.layer
        a = io_.alpha_of(L.image)
        bb = io_.bbox_of(a)
        if bb is None:
            return False
        img = L.image.copy(bb)
        mask = new_mask(bb.width(), bb.height(), 255)
        L.image = new_image(L.image.width(), L.image.height())
        self.floating = Floating(img, mask, QTransform.fromTranslate(L.pos.x() + bb.x(), L.pos.y() + bb.y()),
                                 L, whole_layer=True)
        return True

    def stamp_float(self):
        """Alt-træk: læg en kopi af de flydende pixels ned og fortsæt med at flytte."""
        f = self.floating
        if f is None:
            return
        self._paint_float_into(f, f.layer)

    def _paint_float_into(self, f, L):
        r = f.doc_rect().toAlignedRect()
        L.ensure_covers(r)
        p = QPainter(L.image)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setTransform(f.transform * QTransform.fromTranslate(-L.pos.x(), -L.pos.y()))
        p.drawImage(0, 0, f.image)
        p.end()

    def commit_float(self):
        f = self.floating
        if f is None:
            return
        self.floating = None
        if f.layer in self.layers:
            self._paint_float_into(f, f.layer)
        if f.whole_layer:
            self._set_sel(None)
        else:
            m = new_mask(self.width, self.height)
            p = QPainter(m)
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            p.setTransform(f.transform)
            p.drawImage(0, 0, f.mask)
            p.end()
            self._set_sel(m)
        self.touch()

    def ensure_float(self):
        if self.floating is None:
            return self.float_selection()
        return True

    def transform_float(self, m):
        """Gang en dokument-transformation på de flydende pixels (fx spejl om centrum)."""
        f = self.floating
        c = f.doc_rect().center()
        t = QTransform.fromTranslate(-c.x(), -c.y()) * m * QTransform.fromTranslate(c.x(), c.y())
        f.transform = f.transform * t
        self.touch()

    # ---------- lag ----------
    def add_layer(self, name=None, image=None, pos=None, above=True):
        name = name or self.next_layer_name()
        L = Layer(name, image if image is not None else new_image(self.width, self.height), pos)
        idx = self.active + 1 if above else self.active
        self.layers.insert(idx, L)
        self.active = idx
        self.touch()
        return L

    def next_layer_name(self):
        n = 1
        names = {L.name for L in self.layers}
        while f'Lag {n}' in names:
            n += 1
        return f'Lag {n}'

    def delete_layer(self):
        if len(self.layers) <= 1:
            self.layers[0].image = new_image(self.width, self.height)
        else:
            self.layers.pop(self.active)
            self.active = max(0, self.active - 1)
        self.touch()

    def duplicate_layer(self):
        L = self.layer
        n = Layer(L.name + ' kopi', L.image.copy(), L.pos, L.visible, L.opacity, L.blend)
        self.layers.insert(self.active + 1, n)
        self.active += 1
        self.touch()

    def copy_selection_pixels(self, L=None):
        """Lagets pixels inden for markeringen, beskåret. Returnerer (billede, position)."""
        L = L or self.layer
        if self.selection is None:
            bb = io_.bbox_of(io_.alpha_of(L.image))
            if bb is None:
                return None, None
            return L.image.copy(bb), L.pos + bb.topLeft()
        bb = self.selection_bbox()
        if bb is None:
            return None, None
        img = new_image(bb.width(), bb.height())
        p = QPainter(img)
        p.drawImage(L.pos - bb.topLeft(), L.image)
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        p.drawImage(QPoint(0, 0), self.selection, bb)
        p.end()
        return img, bb.topLeft()

    def layer_via(self, cut=False):
        if self.selection is None:
            self.duplicate_layer()
            return
        img, pos = self.copy_selection_pixels()
        if img is None:
            return
        if cut:
            self.clear_selection_pixels(touch=False)
        L = self.layer
        n = Layer(self.next_layer_name(), img, pos, True, 1.0, 'normal')
        self.layers.insert(self.active + 1, n)
        self.active += 1
        self.touch()

    def merge_down(self):
        if self.active == 0:
            return
        up, lo = self.layers[self.active], self.layers[self.active - 1]
        if up.visible:
            lo.ensure_covers(up.rect())
            p = lo.painter()
            p.setOpacity(up.opacity)
            p.setCompositionMode(BLEND_QT.get(up.blend, QPainter.CompositionMode_SourceOver))
            p.drawImage(up.pos, up.image)
            p.end()
        self.layers.pop(self.active)
        self.active -= 1
        self.touch()

    def merge_visible(self):
        vis = [L for L in self.layers if L.visible]
        if len(vis) < 2:
            return
        img = self.flatten_image()
        base = vis[0]
        for L in vis[1:]:
            self.layers.remove(L)
        base.image, base.pos, base.opacity, base.blend = img, QPoint(0, 0), 1.0, 'normal'
        self.active = self.layers.index(base)
        self.touch()

    def flatten(self):
        img = self.flatten_image(QColor(255, 255, 255))
        self.layers = [Layer('Baggrund', img)]
        self.active = 0
        self.touch()

    def move_layer(self, src, dst):
        dst = max(0, min(len(self.layers) - 1, dst))
        if src == dst:
            return
        L = self.layers.pop(src)
        self.layers.insert(dst, L)
        self.active = dst
        self.touch()

    # ---------- pixeloperationer ----------
    def clear_selection_pixels(self, touch=True):
        L = self.layer
        if self.selection is None:
            L.image = new_image(L.image.width(), L.image.height())
        else:
            p = L.painter()
            p.setCompositionMode(QPainter.CompositionMode_DestinationOut)
            p.drawImage(0, 0, self.selection)
            p.end()
        if touch:
            self.touch()

    def fill(self, color, opacity=1.0, preserve=False, mask=None):
        """Fyld markeringen (eller hele lærredet) på det aktive lag."""
        L = self.layer
        target = self.rect()
        L.ensure_covers(target)
        src = new_image(self.width, self.height, color)
        m = mask if mask is not None else self.selection
        if m is not None:
            p = QPainter(src)
            p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            p.drawImage(0, 0, m)
            p.end()
        if preserve:
            p = QPainter(src)
            p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            p.drawImage(L.pos, L.image)
            p.end()
        p = L.painter()
        p.setOpacity(opacity)
        if preserve:
            p.setCompositionMode(QPainter.CompositionMode_SourceAtop)
        p.drawImage(0, 0, src)
        p.end()
        self.touch()

    def content_aware_fill(self, progress=None):
        """Udfyld markeringen med indhold, der ligner omgivelserne. Returnerer False hvis intet skete."""
        from scipy import ndimage
        from . import inpaint
        sel = self.selection_np()
        if sel is None:
            return False
        hole = sel >= 128
        L = self.layer
        layer_img = self.layer_doc_image()
        la = io_.alpha_of(layer_img)
        ring = ndimage.binary_dilation(hole, iterations=12) & ~hole
        use_layer = ring.any() and la[ring].mean() > 230
        src = layer_img if use_layer else self.flatten_image()
        rgb = io_.argb_np(src)[:, :, [2, 1, 0]]
        res = inpaint.content_aware_fill(np.ascontiguousarray(rgb), sel, progress)
        if res is None:
            return False
        x, y, patch = res
        bgra = np.ascontiguousarray(patch[:, :, [2, 1, 0, 3]])
        img = io_.np_argb(bgra)
        r = QRect(x, y, img.width(), img.height())
        L.ensure_covers(r)
        p = L.painter()
        p.drawImage(r.topLeft(), img)
        p.end()
        self.touch()
        return True

    def region(self, x, y, tolerance, contiguous, all_layers):
        img = self.flatten_image() if all_layers else self.layer_doc_image()
        a = io_.argb_np(img)
        return io_.region_mask(a, x, y, tolerance, contiguous)

    def paste_image(self, img, pos):
        self.add_layer(image=img.convertToFormat(io_.FMT), pos=pos)

    # ---------- billede ----------
    def transform_canvas(self, t, nw, nh):
        lin = QTransform(t.m11(), t.m12(), t.m21(), t.m22(), 0, 0)
        for L in self.layers:
            r = t.mapRect(QRectF(L.rect()))
            L.image = L.image.transformed(lin, Qt.FastTransformation)
            L.pos = QPoint(round(r.x()), round(r.y()))
        if self.selection is not None:
            self._set_sel(self.selection.transformed(lin, Qt.FastTransformation))
        self.last_selection = None
        self.width, self.height = nw, nh
        self.touch()

    def rotate_canvas(self, kind):
        W, H = self.width, self.height
        if kind == 'cw':
            self.transform_canvas(QTransform(0, 1, -1, 0, H, 0), H, W)
        elif kind == 'ccw':
            self.transform_canvas(QTransform(0, -1, 1, 0, 0, W), H, W)
        elif kind == '180':
            self.transform_canvas(QTransform(-1, 0, 0, -1, W, H), W, H)
        elif kind == 'fh':
            self.transform_canvas(QTransform(-1, 0, 0, 1, W, 0), W, H)
        elif kind == 'fv':
            self.transform_canvas(QTransform(1, 0, 0, -1, 0, H), W, H)

    def resize_image(self, nw, nh):
        sx, sy = nw / self.width, nh / self.height
        for L in self.layers:
            w = max(1, round(L.image.width() * sx))
            h = max(1, round(L.image.height() * sy))
            L.image = L.image.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            L.pos = QPoint(round(L.pos.x() * sx), round(L.pos.y() * sy))
        if self.selection is not None:
            self._set_sel(self.selection.scaled(nw, nh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        self.last_selection = None
        self.width, self.height = nw, nh
        self.touch()

    def resize_canvas(self, nw, nh, ax=0.5, ay=0.5):
        dx, dy = round((nw - self.width) * ax), round((nh - self.height) * ay)
        self.crop(QRect(-dx, -dy, nw, nh))

    def crop(self, r):
        for L in self.layers:
            L.pos = L.pos - r.topLeft()
        if self.selection is not None:
            m = new_mask(r.width(), r.height())
            p = QPainter(m)
            p.setCompositionMode(QPainter.CompositionMode_Source)
            p.drawImage(-r.topLeft(), self.selection)
            p.end()
            self._set_sel(m)
        self.last_selection = None
        self.width, self.height = r.width(), r.height()
        self.touch()


# ======================= fil-I/O =======================

def read_flat_image(path):
    r = QImageReader(path)
    r.setAutoTransform(True)
    img = r.read()
    if img.isNull():
        from PIL import Image, ImageOps
        pil = ImageOps.exif_transpose(Image.open(path)).convert('RGBA')
        img = QImage(pil.tobytes('raw', 'BGRA'), pil.width, pil.height, pil.width * 4, QImage.Format_ARGB32).copy()
    return img.convertToFormat(io_.FMT)


def pil_to_qimage(pil):
    pil = pil.convert('RGBA')
    return QImage(pil.tobytes('raw', 'BGRA'), pil.width, pil.height, pil.width * 4,
                  QImage.Format_ARGB32).convertToFormat(io_.FMT)


def qimage_to_pil(img):
    from PIL import Image
    a = io_.argb_np(img)
    return Image.fromarray(a[:, :, [2, 1, 0, 3]], 'RGBA')


def _psd_blend_key(bm):
    name = getattr(bm, 'name', str(bm)).lower()
    return name if name in BLEND_QT else 'normal'


def load_psd(path):
    from psd_tools import PSDImage
    from psd_tools.constants import BlendMode
    psd = PSDImage.open(path)
    W, H = psd.width, psd.height
    layers, warnings = [], []

    def walk(group, parent_visible):
        for lay in group:
            if lay.is_group():
                walk(lay, parent_visible and lay.visible)
                continue
            kind = lay.kind
            if kind == 'adjustment':
                warnings.append(f'Justeringslaget „{lay.name}“ er udeladt.')
                continue
            vis, op, bm = lay.visible, lay.opacity, lay.blend_mode
            try:
                lay.visible, lay.opacity, lay.blend_mode = True, 255, BlendMode.NORMAL
                pil = lay.composite()
                if pil is None or pil.width == 0:
                    pil = lay.topil()
            except Exception:
                pil = None
            finally:
                lay.visible, lay.opacity, lay.blend_mode = vis, op, bm
            if pil is None:
                warnings.append(f'Laget „{lay.name}“ kunne ikke læses.')
                continue
            if kind in ('type', 'smartobject', 'shape'):
                warnings.append(f'„{lay.name}“ er rasteriseret ({kind}).')
            left, top = lay.bbox[0], lay.bbox[1]
            layers.append(Layer(lay.name, pil_to_qimage(pil), QPoint(left, top),
                                vis and parent_visible, op / 255.0, _psd_blend_key(bm)))

    try:
        walk(psd, True)
    except Exception as e:  # noqa
        layers = []
        warnings.append(f'Lagene kunne ikke læses ({e}); indlæst som ét billede.')
    if not layers:
        comp = psd.composite()
        layers = [Layer('Baggrund', pil_to_qimage(comp))]
    doc = Document(W, H, layers, path)
    return doc, warnings


def save_psd(doc, path):
    from psd_tools import PSDImage
    from psd_tools.api.layers import PixelLayer
    from psd_tools.constants import BlendMode
    doc.commit_float()
    psd = PSDImage.new('RGB', (doc.width, doc.height))
    for L in doc.layers:
        bb = io_.bbox_of(io_.alpha_of(L.image))
        if bb is None:
            img, pos = new_image(1, 1), L.pos
        else:
            img, pos = L.image.copy(bb), L.pos + bb.topLeft()
        pl = PixelLayer.frompil(qimage_to_pil(img), psd, L.name, pos.y(), pos.x())
        pl.opacity = round(L.opacity * 255)
        pl.visible = L.visible
        try:
            pl.blend_mode = getattr(BlendMode, L.blend.upper())
        except AttributeError:
            pass
        psd.append(pl)
    psd.save(path)


def load_document(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.psd', '.psb'):
        return load_psd(path)
    img = read_flat_image(path)
    if img.isNull():
        raise IOError('Billedet kunne ikke åbnes.')
    return Document(img.width(), img.height(), [Layer('Baggrund', img)], path), []


def save_flat(doc, path, quality=92):
    ext = os.path.splitext(path)[1].lower()
    opaque = ext in ('.jpg', '.jpeg', '.bmp')
    img = doc.flatten_image(QColor(255, 255, 255) if opaque else None)
    if opaque:
        img = img.convertToFormat(QImage.Format_RGB32)
    if not img.save(path, None, quality if ext in ('.jpg', '.jpeg', '.webp') else -1):
        qimage_to_pil(img).save(path)

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


GRAY = QImage.Format_Grayscale8


def gray_image(w, h, value=255):
    m = QImage(max(1, int(w)), max(1, int(h)), GRAY)
    m.fill(QColor(value, value, value))
    return m


def gray_to_alpha(g):
    """Gråtonemaske -> Alpha8 (samme bytes, tolket som gennemsigtighed)."""
    w, h, bpl = g.width(), g.height(), g.bytesPerLine()
    a = np.frombuffer(g.constBits(), np.uint8, count=bpl * h).reshape(h, bpl)[:, :w]
    return np_mask(a)


def gray_np(g):
    w, h, bpl = g.width(), g.height(), g.bytesPerLine()
    return np.frombuffer(g.constBits(), np.uint8, count=bpl * h).reshape(h, bpl)[:, :w].copy()


def np_gray(a):
    a = np.ascontiguousarray(a, dtype=np.uint8)
    h, w = a.shape
    return QImage(a.tobytes(), w, h, w, GRAY).copy()


class Layer:
    def __init__(self, name, image, pos=None, visible=True, opacity=1.0, blend='normal', kind='pixel', adjust=None):
        self.name = name
        self.image = image
        self._pos = QPoint(pos) if pos is not None else QPoint(0, 0)
        self.visible = visible
        self.opacity = opacity
        self.blend = blend
        self.kind = kind                # 'pixel' eller 'adjust'
        self.adjust = adjust            # dict(type=..., params=...) for justeringslag
        self.mask = None                # Grayscale8: hvid = vis, sort = skjul
        self.mask_pos = QPoint(0, 0)
        self.mask_default = 255         # værdien uden for maskens billede
        self.mask_enabled = True
        self._alpha_cache = (None, None)

    # position flytter masken med (lag og maske er kædet sammen som i Photoshop)
    @property
    def pos(self):
        return self._pos

    @pos.setter
    def pos(self, p):
        p = QPoint(p)
        d = p - self._pos
        self._pos = p
        self.mask_pos = self.mask_pos + d

    @property
    def is_adjust(self):
        return self.kind == 'adjust'

    def rect(self):
        return QRect(self._pos, self.image.size())

    def ensure_covers(self, r):
        self.ensure_mask_covers(r)
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
        self._pos = nr.topLeft()

    def painter(self):
        """QPainter på lagets billede i dokumentkoordinater."""
        p = QPainter(self.image)
        p.translate(-self._pos.x(), -self._pos.y())
        return p

    # ---------- maske ----------
    def has_mask(self):
        return self.mask is not None

    def mask_rect(self):
        return QRect(self.mask_pos, self.mask.size()) if self.mask is not None else QRect()

    def add_mask(self, doc_rect, value=255):
        r = doc_rect.united(self.rect()) if not self.is_adjust else doc_rect
        self.mask = gray_image(r.width(), r.height(), value)
        self.mask_pos = r.topLeft()
        self.mask_default = value
        self.mask_enabled = True

    def ensure_mask_covers(self, r):
        if self.mask is None:
            return
        cur = self.mask_rect()
        if cur.contains(r):
            return
        nr = cur.united(r)
        m = gray_image(nr.width(), nr.height(), self.mask_default)
        p = QPainter(m)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(cur.topLeft() - nr.topLeft(), self.mask)
        p.end()
        self.mask = m
        self.mask_pos = nr.topLeft()

    def mask_painter(self):
        p = QPainter(self.mask)
        p.translate(-self.mask_pos.x(), -self.mask_pos.y())
        return p

    def mask_alpha(self):
        """Masken som Alpha8 (til sammensætning), gemt så den kun beregnes ved ændringer."""
        key = self.mask.cacheKey()
        if self._alpha_cache[0] != key:
            self._alpha_cache = (key, gray_to_alpha(self.mask))
        return self._alpha_cache[1]

    def masked_pixels(self):
        """Lagets pixels med masken anvendt (til flet og PSD)."""
        if self.mask is None or not self.mask_enabled:
            return self.image
        img = self.image.copy()
        p = QPainter(img)
        p.translate(-self._pos.x(), -self._pos.y())
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        p.drawImage(self.mask_pos, self.mask_alpha())
        if self.mask_default == 0:
            from PySide6.QtGui import QRegion
            p.setClipRegion(QRegion(self.rect()).subtracted(QRegion(self.mask_rect())))
            p.setCompositionMode(QPainter.CompositionMode_Clear)
            p.fillRect(self.rect(), Qt.transparent)
        p.end()
        return img

    # ---------- tilstand til fortryd ----------
    def state(self):
        import copy
        return (QImage(self.image), QPoint(self._pos), self.name, self.visible, self.opacity, self.blend,
                self.kind, copy.deepcopy(self.adjust), QImage(self.mask) if self.mask is not None else None,
                QPoint(self.mask_pos), self.mask_default, self.mask_enabled)

    def set_state(self, st):
        import copy
        (img, pos, self.name, self.visible, self.opacity, self.blend, self.kind, adj, mask, mpos,
         self.mask_default, self.mask_enabled) = st
        self.image, self._pos = QImage(img), QPoint(pos)
        self.adjust = copy.deepcopy(adj)
        self.mask = QImage(mask) if mask is not None else None
        self.mask_pos = QPoint(mpos)

    def clone(self, name=None):
        n = Layer(name or self.name, self.image.copy(), self._pos, self.visible, self.opacity, self.blend,
                  self.kind, None)
        n.set_state(self.state())
        n.name = name or self.name
        n.image = self.image.copy()
        if self.mask is not None:
            n.mask = self.mask.copy()
        return n


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
    def __init__(self, w, h, layer, erase, opacity, on_mask=False):
        self.image = new_image(w, h)
        self.layer = layer
        self.erase = erase
        self.opacity = opacity
        self.on_mask = on_mask      # maler på lagmasken (gråtoner) i stedet for pixels


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
        self.mask_target = False       # True: værktøjerne arbejder på det aktive lags maske
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

    def editing_mask(self):
        """Arbejder værktøjerne på masken (justeringslag altid, ellers når masken er valgt)?"""
        L = self.layer
        return L.mask is not None and (L.is_adjust or self.mask_target)

    # ---------- historik ----------
    def snapshot(self):
        f = self.floating
        return dict(
            size=(self.width, self.height),
            layers=[(L, L.state()) for L in self.layers], mask_target=self.mask_target,
            active=self.active, selection=self.selection, outline=self.sel_outline, last=self.last_selection,
            floating=None if f is None else (f.image, f.mask, QTransform(f.transform), f.layer, f.whole_layer, f.outline),
        )

    def restore(self, s):
        self.width, self.height = s['size']
        self.layers = []
        for L, st in s['layers']:
            L.set_state(st)
            self.layers.append(L)
        self.mask_target = s.get('mask_target', False)
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
    def _effective_mask(self, L):
        """Lagets maske som Alpha8, inkl. et maskestrøg under tegning."""
        st = self.stroke
        if st is None or st.layer is not L or not st.on_mask:
            return L.mask_alpha()
        g = L.mask.copy()
        p = QPainter(g)
        p.translate(-L.mask_pos.x(), -L.mask_pos.y())
        p.setOpacity(st.opacity)
        p.drawImage(0, 0, st.image)
        p.end()
        return gray_to_alpha(g)

    def _apply_mask(self, painter_target, L, xform, smooth):
        """Gang lagets maske på et allerede tegnet midlertidigt billede."""
        tp = QPainter(painter_target)
        tp.setRenderHint(QPainter.SmoothPixmapTransform, smooth)
        tp.setTransform(xform)
        tp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        tp.drawImage(L.mask_pos, self._effective_mask(L))
        if L.mask_default == 0:
            from PySide6.QtGui import QRegion
            full = QRegion(xform.mapRect(QRectF(self.rect().united(L.mask_rect()).adjusted(-1, -1, 1, 1)))
                           .toAlignedRect().united(painter_target.rect()))
            inner = QRegion(xform.mapRect(QRectF(L.mask_rect())).toAlignedRect())
            tp.setTransform(QTransform())
            tp.setClipRegion(full.subtracted(inner))
            tp.setCompositionMode(QPainter.CompositionMode_Clear)
            tp.fillRect(painter_target.rect(), Qt.transparent)
        tp.end()

    def render(self, target, xform, smooth=False, clip=True, upto=None):
        """Tegn de synlige lag (eventuelt kun lagene under indeks upto) ind i target med transformen xform."""
        from . import adjust as adj_
        acc = QPainter(target)
        acc.setRenderHint(QPainter.SmoothPixmapTransform, smooth)
        tmp = None
        layers = self.layers if upto is None else self.layers[:upto]
        dev_clip = xform.mapRect(QRectF(self.rect())).toAlignedRect()
        for L in layers:
            if not L.visible:
                continue
            mode = BLEND_QT.get(L.blend, QPainter.CompositionMode_SourceOver)
            has_mask = L.mask is not None and L.mask_enabled
            if L.is_adjust:
                if adj_.is_identity(L.adjust):
                    continue
                acc.end()
                adj_img = adj_.apply_image(target, L.adjust)
                if has_mask:
                    self._apply_mask(adj_img, L, xform, smooth)
                acc = QPainter(target)
                acc.setRenderHint(QPainter.SmoothPixmapTransform, smooth)
                if clip:
                    acc.setClipRect(dev_clip)
                acc.setOpacity(L.opacity)
                acc.setCompositionMode(mode)
                acc.drawImage(0, 0, adj_img)
                continue
            special = has_mask or (self.floating is not None and self.floating.layer is L) or \
                (self.stroke is not None and self.stroke.layer is L)
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
            if s is not None and s.layer is L and not s.on_mask:
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
            if has_mask:
                self._apply_mask(tmp, L, xform, smooth)
            acc.setTransform(QTransform())
            if clip:
                acc.setClipRect(dev_clip)
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
        n = L.clone(L.name + ' kopi')
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
        if self.selection is None or self.layer.is_adjust:
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
        if lo.is_adjust:
            return False
        if lo.mask is not None:          # anvend den nederste maske først
            lo.image, lo.mask = lo.masked_pixels(), None
        if up.visible and up.is_adjust:
            from . import adjust as adj_
            adjusted = adj_.apply_image(lo.image, up.adjust)
            if up.mask is not None and up.mask_enabled:
                tmp = Layer('', adjusted, lo.pos)
                tmp.mask, tmp.mask_pos, tmp.mask_default = up.mask, QPoint(up.mask_pos), up.mask_default
                adjusted = tmp.masked_pixels()
            p = lo.painter()
            p.setOpacity(up.opacity)
            p.setCompositionMode(QPainter.CompositionMode_SourceAtop)
            p.drawImage(lo.pos, adjusted)
            p.end()
        elif up.visible:
            lo.ensure_covers(up.rect())
            p = lo.painter()
            p.setOpacity(up.opacity)
            p.setCompositionMode(BLEND_QT.get(up.blend, QPainter.CompositionMode_SourceOver))
            p.drawImage(up.pos, up.masked_pixels())
            p.end()
        self.layers.pop(self.active)
        self.active -= 1
        self.mask_target = False
        self.touch()
        return True

    def merge_visible(self):
        vis = [L for L in self.layers if L.visible]
        if len(vis) < 2:
            return
        img = self.flatten_image()
        base = vis[0]
        for L in vis[1:]:
            self.layers.remove(L)
        base.kind, base.adjust, base.mask = 'pixel', None, None
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
    def clear_selection_pixels(self, touch=True, bg=None):
        L = self.layer
        if self.editing_mask():
            self.fill(bg if bg is not None else QColor(255, 255, 255))
            return
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
        """Fyld markeringen (eller hele lærredet) på det aktive lag – eller dets maske."""
        L = self.layer
        if self.editing_mask():
            c = QColor(color)
            g = round(c.red() * 0.299 + c.green() * 0.587 + c.blue() * 0.114)
            L.ensure_mask_covers(self.rect())
            src = new_image(self.width, self.height, QColor(g, g, g))
            m = mask if mask is not None else self.selection
            if m is not None:
                p = QPainter(src)
                p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
                p.drawImage(0, 0, m)
                p.end()
            p = L.mask_painter()
            p.setOpacity(opacity)
            p.drawImage(0, 0, src)
            p.end()
            self.touch()
            return
        if L.is_adjust:
            return
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

    def invert_target(self):
        """Ctrl+I: invertér masken eller lagets pixels (inden for markeringen)."""
        L = self.layer
        sel = self.selection_np()
        if self.editing_mask():
            L.ensure_mask_covers(self.rect())
            g = gray_np(L.mask)
            if sel is None:
                g = 255 - g
            else:
                x, y = -L.mask_pos.x(), -L.mask_pos.y()
                sub = g[y:y + self.height, x:x + self.width].astype(np.float32)
                w = sel.astype(np.float32) / 255.0
                g[y:y + self.height, x:x + self.width] = (sub * (1 - w) + (255 - sub) * w).round().astype(np.uint8)
            L.mask = np_gray(g)
        elif not L.is_adjust:
            a = io_.argb_np(L.image)
            inv = a.copy()
            inv[..., :3] = 255 - inv[..., :3]
            if sel is not None:
                full = np.zeros((L.image.height(), L.image.width()), np.float32)
                r = QRect(0, 0, self.width, self.height).intersected(L.rect())
                if not r.isEmpty():
                    full[r.y() - L.pos.y():r.bottom() + 1 - L.pos.y(), r.x() - L.pos.x():r.right() + 1 - L.pos.x()] = \
                        sel[r.y():r.bottom() + 1, r.x():r.right() + 1] / 255.0
                w = full[..., None]
                inv[..., :3] = (a[..., :3] * (1 - w) + inv[..., :3] * w).round().astype(np.uint8)
            L.image = io_.np_argb(inv)
        self.touch()

    # ---------- masker ----------
    def add_mask(self, mode='reveal_all'):
        """reveal_all / hide_all / reveal_sel / hide_sel"""
        L = self.layer
        if L.mask is not None:
            return False
        value = 0 if mode in ('hide_all', 'reveal_sel') else 255
        L.add_mask(self.rect(), value)
        sel = self.selection_np()
        if sel is not None and mode in ('reveal_sel', 'hide_sel'):
            g = gray_np(L.mask)
            x, y = -L.mask_pos.x(), -L.mask_pos.y()
            g[y:y + self.height, x:x + self.width] = sel if mode == 'reveal_sel' else 255 - sel
            L.mask = np_gray(g)
            self._set_sel(None)
        self.mask_target = True
        self.touch()
        return True

    def delete_mask(self, apply=False):
        L = self.layer
        if L.mask is None or L.is_adjust:
            return False
        if apply:
            L.image = L.masked_pixels()
        L.mask = None
        self.mask_target = False
        self.touch()
        return True

    def selection_from_mask(self, L):
        m = new_mask(self.width, self.height, L.mask_default)
        p = QPainter(m)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(L.mask_pos, L.mask_alpha())
        p.end()
        self.set_selection(m)
        self.touch()

    def add_adjustment(self, adj):
        from . import adjust as adj_
        L = Layer(adj_.NAMES[adj['type']], new_image(1, 1), QPoint(0, 0), kind='adjust', adjust=adj)
        sel = self.selection_np()
        L.add_mask(self.rect(), 255)
        if sel is not None:          # som i Photoshop: markeringen bliver lagets maske
            L.mask = np_gray(sel)
            L.mask_pos = QPoint(0, 0)
            L.mask_default = 0
            self._set_sel(None)
        self.layers.insert(self.active + 1, L)
        self.active += 1
        self.mask_target = True
        self.touch()
        return L

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
            mr = t.mapRect(QRectF(L.mask_rect())) if L.mask is not None else None
            L._pos = QPoint(round(r.x()), round(r.y()))
            if mr is not None:
                L.mask = L.mask.transformed(lin, Qt.FastTransformation)
                L.mask_pos = QPoint(round(mr.x()), round(mr.y()))
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
            L._pos = QPoint(round(L.pos.x() * sx), round(L.pos.y() * sy))
            if L.mask is not None:
                mw = max(1, round(L.mask.width() * sx))
                mh = max(1, round(L.mask.height() * sy))
                L.mask = L.mask.scaled(mw, mh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                L.mask_pos = QPoint(round(L.mask_pos.x() * sx), round(L.mask_pos.y() * sy))
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


def _mask_from_psd(lay):
    """Lagmaske fra PSD som (gråtonebillede, position, standardværdi) eller None."""
    try:
        if not lay.has_mask() or lay.mask is None:
            return None
        mk = lay.mask
        pil = mk.topil()
        default = int(getattr(mk, 'background_color', 255) or 0)
        default = 255 if default >= 128 else 0
        if pil is None or mk.width == 0 or mk.height == 0:
            return None
        pil = pil.convert('L')
        return np_gray(np.asarray(pil)), QPoint(mk.left, mk.top), default
    except Exception:
        return None


def load_psd(path):
    from psd_tools import PSDImage
    from psd_tools.constants import BlendMode
    from . import adjust as adj_
    psd = PSDImage.open(path)
    W, H = psd.width, psd.height
    layers, warnings = [], []

    def walk(group, parent_visible):
        for lay in group:
            if lay.is_group():
                walk(lay, parent_visible and lay.visible)
                continue
            kind = lay.kind
            vis, op, bm = lay.visible, lay.opacity, lay.blend_mode
            if kind == 'adjustment':
                adj = adj_.from_psd(lay)
                if adj is None:
                    warnings.append(f'Justeringslaget „{lay.name}“ kendes ikke og er udeladt.')
                    continue
                L = Layer(lay.name, new_image(1, 1), QPoint(0, 0), vis and parent_visible, op / 255.0,
                          _psd_blend_key(bm), kind='adjust', adjust=adj)
                L.add_mask(QRect(0, 0, W, H), 255)
                m = _mask_from_psd(lay)
                if m is not None:
                    L.mask, L.mask_pos, L.mask_default = m
                layers.append(L)
                continue
            m = _mask_from_psd(lay) if kind == 'pixel' else None
            pil = None
            try:
                if m is not None:
                    pil = lay.topil()          # rå pixels; masken holdes redigerbar
                if pil is None:
                    lay.visible, lay.opacity, lay.blend_mode = True, 255, BlendMode.NORMAL
                    pil = lay.composite()
                    m = None
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
            L = Layer(lay.name, pil_to_qimage(pil), QPoint(left, top),
                      vis and parent_visible, op / 255.0, _psd_blend_key(bm))
            if m is not None:
                L.mask, L.mask_pos, L.mask_default = m
                L.ensure_mask_covers(QRect(0, 0, W, H).united(L.rect()))
            layers.append(L)

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


def doc_needs_baking(doc):
    """Har dokumentet noget, PSD ikke kan gemme redigerbart (justeringslag)?"""
    return any(L.is_adjust for L in doc.layers)


def save_psd(doc, path):
    from psd_tools import PSDImage
    from psd_tools.api.layers import PixelLayer
    from psd_tools.constants import BlendMode
    from PIL import Image
    from . import adjust as adj_
    doc.commit_float()
    psd = PSDImage.new('RGB', (doc.width, doc.height))
    for i, L in enumerate(doc.layers):
        mask_for_psd = None
        if L.is_adjust:
            # bag justeringen: resultatet af lagene under, justeret, med masken som gennemsigtighed
            below = new_image(doc.width, doc.height)
            doc.render(below, QTransform(), upto=i)
            img = adj_.apply_image(below, L.adjust)
            if L.mask is not None and L.mask_enabled:
                t = Layer('', img, QPoint(0, 0))
                t.mask, t.mask_pos, t.mask_default = L.mask, QPoint(L.mask_pos), L.mask_default
                img = t.masked_pixels()
            pos = QPoint(0, 0)
            name = f'{L.name} (bagt)'
        else:
            name = L.name
            bb = io_.bbox_of(io_.alpha_of(L.image))
            if bb is None:
                img, pos = new_image(1, 1), L.pos
            else:
                img, pos = L.image.copy(bb), L.pos + bb.topLeft()
            if L.mask is not None:
                mask_for_psd = L
        pl = PixelLayer.frompil(qimage_to_pil(img), psd, name, pos.y(), pos.x())
        pl.opacity = round(L.opacity * 255)
        pl.visible = L.visible
        try:
            pl.blend_mode = getattr(BlendMode, L.blend.upper())
        except AttributeError:
            pass
        psd.append(pl)
        if mask_for_psd is not None:
            try:
                # psd-tools lægger masken i lagets egen ramme, så beskær den præcis dertil
                r = QRect(pos, img.size())
                L.ensure_mask_covers(r)
                g = gray_np(L.mask)
                ox, oy = r.x() - L.mask_pos.x(), r.y() - L.mask_pos.y()
                g = np.ascontiguousarray(g[oy:oy + r.height(), ox:ox + r.width()])
                if pl.has_mask():          # frompil giver laget en tom standardmaske
                    pl.remove_mask()
                mk = pl.create_mask(Image.fromarray(g, 'L'), top=r.y(), left=r.x())
                try:
                    mk.background_color = L.mask_default
                except Exception:
                    pass
                if not L.mask_enabled:
                    try:
                        mk.disabled = True
                    except Exception:
                        pass
            except Exception:
                pass
    psd.save(path)


# ---------- Lagkages eget format (.lagkage): alt forbliver redigerbart ----------

def save_lagkage(doc, path):
    import json
    import zipfile
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    doc.commit_float()

    def png(img):
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, 'PNG')
        buf.close()
        return bytes(ba)

    meta = dict(format='lagkage', version=1, width=doc.width, height=doc.height, active=doc.active, layers=[])
    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for i, L in enumerate(doc.layers):
            d = dict(name=L.name, kind=L.kind, adjust=L.adjust, x=L.pos.x(), y=L.pos.y(), visible=L.visible,
                     opacity=L.opacity, blend=L.blend)
            if not L.is_adjust:
                d['image'] = f'layers/{i}.png'
                z.writestr(d['image'], png(L.image))
            if L.mask is not None:
                d.update(mask=f'masks/{i}.png', mask_x=L.mask_pos.x(), mask_y=L.mask_pos.y(),
                         mask_default=L.mask_default, mask_enabled=L.mask_enabled)
                z.writestr(d['mask'], png(L.mask))
            meta['layers'].append(d)
        z.writestr('document.json', json.dumps(meta, ensure_ascii=False, indent=1))
        z.writestr('preview.png', png(doc.flatten_image()))
    os.replace(tmp, path)


def load_lagkage(path):
    import json
    import zipfile
    with zipfile.ZipFile(path) as z:
        meta = json.loads(z.read('document.json'))
        layers = []
        for d in meta['layers']:
            if d.get('image'):
                img = QImage.fromData(z.read(d['image']), 'PNG').convertToFormat(io_.FMT)
            else:
                img = new_image(1, 1)
            L = Layer(d['name'], img, QPoint(d['x'], d['y']), d['visible'], d['opacity'], d['blend'],
                      d.get('kind', 'pixel'), d.get('adjust'))
            if d.get('mask'):
                L.mask = QImage.fromData(z.read(d['mask']), 'PNG').convertToFormat(GRAY)
                L.mask_pos = QPoint(d['mask_x'], d['mask_y'])
                L.mask_default = d.get('mask_default', 255)
                L.mask_enabled = d.get('mask_enabled', True)
            layers.append(L)
    doc = Document(meta['width'], meta['height'], layers, path)
    doc.active = min(meta.get('active', len(layers) - 1), len(layers) - 1)
    return doc, []


def load_document(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.psd', '.psb'):
        return load_psd(path)
    if ext == '.lagkage':
        return load_lagkage(path)
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

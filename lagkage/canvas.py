"""Lærredet: visning, zoom/panorering og alle værktøjer."""
import math
from PySide6.QtCore import Qt, QPointF, QPoint, QRectF, QRect, QTimer, QLineF
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QTransform, QPainterPath, QPolygonF,
                           QImage, QCursor)
from PySide6.QtWidgets import QWidget

from . import imageops as io_
from .imageops import new_image, np_mask, mask_np
from .document import Stroke

ZOOM_LEVELS = [0.01, 0.02, 0.03, 0.04, 0.05, 0.0625, 0.0833, 0.125, 0.1667, 0.25, 0.3333, 0.5, 0.6667,
               1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 24, 32, 64]
HANDLES = [(0, 0), (0.5, 0), (1, 0), (1, 0.5), (1, 1), (0.5, 1), (0, 1), (0, 0.5)]


def _mode_from_mods(mods, default):
    shift, alt = bool(mods & Qt.ShiftModifier), bool(mods & Qt.AltModifier)
    if shift and alt:
        return 'int'
    if shift:
        return 'add'
    if alt:
        return 'sub'
    return default


class Canvas(QWidget):
    def __init__(self, doc, win):
        super().__init__()
        self.doc, self.win = doc, win
        self.zoom = 1.0
        self.offset = QPointF(0, 0)
        self._cache, self._cache_key = None, None
        self._checker = QBrush(io_.checker_brush_image(8))
        self.drag = None
        self.poly = None
        self.mouse = None           # skærmposition
        self.space = False
        self.transforming = False
        self.last_brush = None
        self.ant_phase = 0
        self._fitted = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(200, 200)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(180)
        doc.changed.connect(self.update)

    # ---------- visning ----------
    def view(self):
        return QTransform(self.zoom, 0, 0, self.zoom, self.offset.x(), self.offset.y())

    def to_doc(self, p):
        return QPointF((p.x() - self.offset.x()) / self.zoom, (p.y() - self.offset.y()) / self.zoom)

    def to_screen(self, p):
        return QPointF(p.x() * self.zoom + self.offset.x(), p.y() * self.zoom + self.offset.y())

    def fit(self, max_zoom=None):
        W, H = self.doc.width, self.doc.height
        aw, ah = max(50, self.width() - 40), max(50, self.height() - 40)
        z = min(aw / W, ah / H)
        if max_zoom:
            z = min(z, max_zoom)
        self.zoom = z
        self.offset = QPointF((self.width() - W * z) / 2, (self.height() - H * z) / 2)
        self.update()
        self.win.update_status()

    def actual_pixels(self):
        c = QPointF(self.width() / 2, self.height() / 2)
        self.zoom_at(1.0, c)

    def zoom_at(self, z, pt):
        z = max(0.01, min(64.0, z))
        d = self.to_doc(pt)
        self.zoom = z
        self.offset = QPointF(pt.x() - d.x() * z, pt.y() - d.y() * z)
        self.update()
        self.win.update_status()

    def zoom_step(self, direction, pt=None):
        pt = pt or QPointF(self.width() / 2, self.height() / 2)
        if direction > 0:
            nz = next((z for z in ZOOM_LEVELS if z > self.zoom * 1.001), 64)
        else:
            nz = next((z for z in reversed(ZOOM_LEVELS) if z < self.zoom * 0.999), 0.01)
        self.zoom_at(nz, pt)

    def view_center_doc(self):
        return self.to_doc(QPointF(self.width() / 2, self.height() / 2))

    def showEvent(self, e):
        if not self._fitted:
            self._fitted = True
            QTimer.singleShot(0, lambda: self.fit(max_zoom=1.0))

    def _tick(self):
        if self.doc.has_selection() or self.poly or self.transforming:
            self.ant_phase = (self.ant_phase + 1) % 8
            self.update()

    # ---------- tegning ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#202020'))
        vt = self.view()
        docr = vt.mapRect(QRectF(self.doc.rect()))
        p.fillRect(docr, self._checker)
        dpr = self.devicePixelRatioF()
        key = (self.doc.version, self.zoom, self.offset.x(), self.offset.y(), self.width(), self.height(), dpr)
        if key != self._cache_key:
            img = new_image(int(self.width() * dpr), int(self.height() * dpr))
            self.doc.render(img, vt * QTransform.fromScale(dpr, dpr), smooth=self.zoom < 1)
            img.setDevicePixelRatio(dpr)
            self._cache, self._cache_key = img, key
        p.drawImage(QPointF(0, 0), self._cache)
        p.setPen(QPen(QColor(0, 0, 0, 160), 1))
        p.drawRect(docr.adjusted(-0.5, -0.5, 0.5, 0.5))
        self._paint_ants(p, vt)
        self._paint_tool(p, vt)
        p.end()

    def _ant_pens(self):
        w = QPen(QColor(255, 255, 255), 1)
        w.setCosmetic(True)
        b = QPen(QColor(0, 0, 0), 1)
        b.setCosmetic(True)
        b.setDashPattern([4, 4])
        b.setDashOffset(self.ant_phase)
        return w, b

    def _stroke_path(self, p, path, xf):
        w, b = self._ant_pens()
        p.save()
        p.setTransform(xf)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setBrush(Qt.NoBrush)
        p.setPen(w)
        p.drawPath(path)
        p.setPen(b)
        p.drawPath(path)
        p.restore()

    def _paint_ants(self, p, vt):
        f = self.doc.floating
        if f is not None:
            self._stroke_path(p, f.outline, f.transform * vt)
        elif self.doc.sel_outline is not None:
            self._stroke_path(p, self.doc.sel_outline, vt)

    def _paint_tool(self, p, vt):
        d = self.drag
        if d and d['kind'] == 'marquee':
            path = self._marquee_path(d, self.to_doc(self.mouse))
            if path is not None:
                self._stroke_path(p, path, vt)
        if d and d['kind'] == 'lasso' and len(d['pts']) > 1:
            path = QPainterPath()
            path.addPolygon(QPolygonF(d['pts']))
            self._stroke_path(p, path, vt)
        if self.poly:
            path = QPainterPath()
            path.addPolygon(QPolygonF(self.poly + ([self.to_doc(self.mouse)] if self.mouse else [])))
            self._stroke_path(p, path, vt)
        if self.transforming and self.doc.floating is not None:
            self._paint_transform_box(p, vt)
        tool = self.effective_tool()
        if tool in ('brush', 'eraser') and self.mouse is not None and self.underMouse():
            r = max(1.0, self.win.opt['size'] * self.zoom / 2)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(0, 0, 0, 200), 1))
            p.drawEllipse(self.mouse, r + 1, r + 1)
            p.setPen(QPen(QColor(255, 255, 255, 220), 1))
            p.drawEllipse(self.mouse, r, r)
            p.drawPoint(self.mouse)

    def _transform_points(self, vt):
        f = self.doc.floating
        w, h = f.image.width(), f.image.height()
        xf = f.transform * vt
        return [xf.map(QPointF(hx * w, hy * h)) for hx, hy in HANDLES]

    def _paint_transform_box(self, p, vt):
        pts = self._transform_points(vt)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor('#1e90ff'), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(QPolygonF([pts[0], pts[2], pts[4], pts[6]]))
        p.setBrush(QColor(255, 255, 255))
        for q in pts:
            p.drawRect(QRectF(q.x() - 3.5, q.y() - 3.5, 7, 7))
        c = (pts[0] + pts[4]) / 2
        p.drawEllipse(c, 3, 3)

    # ---------- hjælpere ----------
    def effective_tool(self):
        if self.space:
            return 'hand'
        return self.win.tool

    def _mods(self):
        from PySide6.QtWidgets import QApplication
        return QApplication.keyboardModifiers()

    def update_cursor(self):
        t = self.effective_tool()
        if self.drag and self.drag['kind'] == 'pan':
            self.setCursor(Qt.ClosedHandCursor)
        elif t == 'hand':
            self.setCursor(Qt.OpenHandCursor)
        elif t in ('brush', 'eraser'):
            self.setCursor(Qt.BlankCursor)
        elif t == 'move' or (self._mods() & Qt.ControlModifier and t not in ('zoom',)):
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.setCursor(Qt.CrossCursor)

    def _marquee_path(self, d, cur):
        s = d['start']
        x0, y0, x1, y1 = s.x(), s.y(), cur.x(), cur.y()
        mods = self._mods()
        if d['mode_mods_free']:
            if mods & Qt.ShiftModifier:
                side = max(abs(x1 - x0), abs(y1 - y0))
                x1 = x0 + math.copysign(side, x1 - x0 or 1)
                y1 = y0 + math.copysign(side, y1 - y0 or 1)
            if mods & Qt.AltModifier:
                x0, y0 = 2 * x0 - x1, 2 * y0 - y1
        if d['tool'] == 'rect':
            x0, y0, x1, y1 = round(x0), round(y0), round(x1), round(y1)
        r = QRectF(QPointF(x0, y0), QPointF(x1, y1)).normalized()
        if r.width() < 1 or r.height() < 1:
            return None
        path = QPainterPath()
        if d['tool'] == 'rect':
            path.addRect(r)
        else:
            path.addEllipse(r)
        return path

    def _apply_path_selection(self, path, mode, antialias):
        doc = self.doc
        m = mask_np(io_.path_mask(doc.width, doc.height, path, antialias))
        m = io_.feather(m, self.win.opt['feather'])
        doc.begin('Markering')
        doc.apply_selection(m, mode)

    def _in_selection(self, pt):
        s = self.doc.selection
        x, y = int(math.floor(pt.x())), int(math.floor(pt.y()))
        if s is None or not (0 <= x < s.width() and 0 <= y < s.height()):
            return False
        return s.pixelColor(x, y).alpha() >= 128

    def _in_doc(self, pt):
        return 0 <= pt.x() < self.doc.width and 0 <= pt.y() < self.doc.height

    def _transform_hit(self, sp):
        pts = self._transform_points(self.view())
        for i, q in enumerate(pts):
            if QLineF(q, sp).length() <= 7:
                return ('scale', i)
        poly = QPolygonF([pts[0], pts[2], pts[4], pts[6]])
        if poly.containsPoint(sp, Qt.OddEvenFill):
            return ('move', None)
        return ('rotate', None)

    # ---------- mus ----------
    def mousePressEvent(self, e):
        self.setFocus()
        sp = e.position()
        pos = self.to_doc(sp)
        self.mouse = sp
        mods = e.modifiers()
        doc = self.doc
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and self.effective_tool() == 'hand'):
            self.drag = dict(kind='pan', start=sp, off=QPointF(self.offset))
            self.update_cursor()
            return
        if e.button() != Qt.LeftButton:
            return
        if self.transforming and doc.floating is not None:
            kind, idx = self._transform_hit(sp)
            self.drag = dict(kind='t_' + kind, idx=idx, start=pos, T0=QTransform(doc.floating.transform))
            return
        tool = self.effective_tool()
        if tool == 'zoom':
            self.zoom_step(-1 if mods & Qt.AltModifier else 1, sp)
            return
        if mods & Qt.ControlModifier and tool not in ('hand', 'zoom') and not self.poly:
            tool = 'move'
        if tool == 'move':
            self._press_move(pos, mods)
        elif tool in ('rect', 'ellipse', 'lasso'):
            mode = _mode_from_mods(mods, self.win.opt['selmode'])
            no_mods = not (mods & (Qt.ShiftModifier | Qt.AltModifier))
            if no_mods and mode == 'new' and doc.floating is None and self._in_selection(pos):
                doc.begin('Flyt markering')
                self.drag = dict(kind='movesel', start=pos, base=doc.selection, moved=False)
            elif tool == 'lasso':
                self.drag = dict(kind='lasso', pts=[pos], mode=mode)
            else:
                self.drag = dict(kind='marquee', tool=tool, start=pos, mode=mode,
                                 mode_mods_free=no_mods or not doc.has_selection())
        elif tool == 'poly':
            self._press_poly(pos, sp, mods)
        elif tool == 'wand':
            if self._in_doc(pos):
                mode = _mode_from_mods(mods, self.win.opt['selmode'])
                doc.begin('Tryllestav')
                from PySide6.QtWidgets import QApplication
                QApplication.setOverrideCursor(Qt.WaitCursor)
                arr = doc.region(int(pos.x()), int(pos.y()), self.win.opt['tolerance'],
                                 self.win.opt['contiguous'], self.win.opt['sample_all'])
                doc.apply_selection(arr, mode)
                QApplication.restoreOverrideCursor()
        elif tool == 'eyedropper':
            self._sample(pos, mods)
            self.drag = dict(kind='eyedrop')
        elif tool in ('brush', 'eraser'):
            if tool == 'brush' and mods & Qt.AltModifier:
                self._sample(pos, Qt.NoModifier)
                self.drag = dict(kind='eyedrop')
                return
            if not doc.layer.visible:
                self.win.flash('Laget er skjult. Gør det synligt for at male på det.')
                return
            doc.begin('Viskelæder' if tool == 'eraser' else 'Pensel')
            doc.stroke = Stroke(doc.width, doc.height, doc.layer, tool == 'eraser',
                                self.win.opt['opacity'] / 100.0)
            start = self.last_brush if (mods & Qt.ShiftModifier and self.last_brush is not None) else pos
            self._stroke_to(start, pos)
            self.drag = dict(kind='stroke', last=pos)
        elif tool == 'bucket':
            if mods & Qt.AltModifier:
                self._sample(pos, Qt.NoModifier)
                return
            if self._in_doc(pos):
                doc.begin('Spand')
                arr = doc.region(int(pos.x()), int(pos.y()), self.win.opt['tolerance'],
                                 self.win.opt['contiguous'], self.win.opt['sample_all'])
                sel = doc.selection_np()
                if sel is not None:
                    import numpy as np
                    arr = np.minimum(arr, sel)
                doc.fill(self.win.fg, self.win.opt['opacity'] / 100.0, mask=np_mask(arr))

    def _press_move(self, pos, mods):
        doc = self.doc
        alt = bool(mods & Qt.AltModifier)
        if not doc.layer.visible and doc.floating is None:
            self.win.flash('Laget er skjult.')
            return
        if doc.floating is not None or doc.selection is not None:
            doc.begin('Flyt', keep_float=True)
            if doc.floating is None:
                if not doc.float_selection(copy=alt):
                    doc.cancel_begin()
                    return
            elif alt:
                doc.stamp_float()
            self.drag = dict(kind='float', start=pos, T0=QTransform(doc.floating.transform), moved=False, alt=alt)
        else:
            doc.begin('Flyt')
            if alt:
                doc.duplicate_layer()
            self.drag = dict(kind='layer', start=pos, p0=QPoint(doc.layer.pos), L=doc.layer, moved=False, alt=alt)
        doc.touch()

    def _press_poly(self, pos, sp, mods):
        if self.poly is None:
            self.poly = [pos]
            self.poly_mode = _mode_from_mods(mods, self.win.opt['selmode'])
            return
        first = self.to_screen(self.poly[0])
        if len(self.poly) >= 3 and QLineF(first, sp).length() < 8:
            self.close_poly()
        else:
            self.poly.append(pos)
        self.update()

    def close_poly(self):
        pts = self.poly
        self.poly = None
        if pts and len(pts) >= 3:
            path = QPainterPath()
            path.addPolygon(QPolygonF(pts))
            path.closeSubpath()
            self._apply_path_selection(path, self.poly_mode, self.win.opt['antialias'])
        self.update()

    def _sample(self, pos, mods):
        if not self._in_doc(pos):
            return
        c = self.doc.sample(int(pos.x()), int(pos.y()), self.win.opt['eyedrop_all'] or self.win.tool != 'eyedropper')
        if c.alpha() == 0:
            return
        c.setAlpha(255)
        if mods & Qt.AltModifier:
            self.win.set_bg(c)
        else:
            self.win.set_fg(c)

    def _stroke_to(self, a, b):
        doc = self.doc
        s = doc.stroke
        size = self.win.opt['size']
        col = QColor(self.win.fg) if not s.erase else QColor(0, 0, 0)
        p = QPainter(s.image)
        p.setRenderHint(QPainter.Antialiasing, size > 2)
        if QLineF(a, b).length() < 0.01:
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            if size <= 1:
                p.fillRect(QRectF(math.floor(b.x()), math.floor(b.y()), 1, 1), col)
            else:
                p.drawEllipse(b, size / 2, size / 2)
        else:
            pen = QPen(col, size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            p.drawLine(a, b)
        if doc.selection is not None:
            r = QRectF(a, b).normalized().adjusted(-size, -size, size, size).toAlignedRect().intersected(doc.rect())
            p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            p.drawImage(r.topLeft(), doc.selection, r)
        p.end()
        self.last_brush = b
        doc.touch()

    def _commit_stroke(self):
        doc = self.doc
        s = doc.stroke
        if s is None:
            return
        doc.stroke = None
        L = s.layer
        if not s.erase:
            L.ensure_covers(doc.rect())
        p = L.painter()
        p.setOpacity(s.opacity)
        if s.erase:
            p.setCompositionMode(QPainter.CompositionMode_DestinationOut)
        p.drawImage(0, 0, s.image)
        p.end()
        doc.touch()

    def mouseMoveEvent(self, e):
        sp = e.position()
        self.mouse = sp
        pos = self.to_doc(sp)
        self.win.update_status(pos)
        d = self.drag
        doc = self.doc
        if d is None:
            if self.transforming and doc.floating is not None:
                kind, idx = self._transform_hit(sp)
                self.setCursor({'move': Qt.SizeAllCursor, 'rotate': Qt.CrossCursor}.get(
                    kind, Qt.SizeFDiagCursor if idx in (0, 4) else Qt.SizeBDiagCursor if idx in (2, 6)
                    else Qt.SizeVerCursor if idx in (1, 5) else Qt.SizeHorCursor))
            else:
                self.update_cursor()
            self.update()
            return
        k = d['kind']
        if k == 'pan':
            self.offset = d['off'] + (sp - d['start'])
            self.update()
        elif k in ('float', 'layer', 'movesel'):
            dx, dy = pos.x() - d['start'].x(), pos.y() - d['start'].y()
            if e.modifiers() & Qt.ShiftModifier:
                if abs(dx) > abs(dy):
                    dy = 0
                else:
                    dx = 0
            dx, dy = round(dx), round(dy)
            if dx or dy:
                d['moved'] = True
            if k == 'float':
                doc.floating.transform = d['T0'] * QTransform.fromTranslate(dx, dy)
                doc.touch()
            elif k == 'layer':
                d['L'].pos = d['p0'] + QPoint(dx, dy)
                doc.touch()
            else:
                doc.translate_selection(dx, dy, d['base'])
        elif k == 'marquee':
            self.update()
        elif k == 'lasso':
            if QLineF(d['pts'][-1], pos).length() * self.zoom >= 1.5:
                d['pts'].append(pos)
            self.update()
        elif k == 'stroke':
            self._stroke_to(d['last'], pos)
            d['last'] = pos
        elif k == 'eyedrop':
            self._sample(pos, e.modifiers())
        elif k.startswith('t_'):
            self._drag_transform(d, pos, e.modifiers())

    def _drag_transform(self, d, pos, mods):
        f = self.doc.floating
        T0 = d['T0']
        if d['kind'] == 't_move':
            f.transform = T0 * QTransform.fromTranslate(pos.x() - d['start'].x(), pos.y() - d['start'].y())
        elif d['kind'] == 't_rotate':
            c = T0.mapRect(QRectF(f.image.rect())).center()
            a0 = math.degrees(math.atan2(d['start'].y() - c.y(), d['start'].x() - c.x()))
            a1 = math.degrees(math.atan2(pos.y() - c.y(), pos.x() - c.x()))
            ang = a1 - a0
            if mods & Qt.ShiftModifier:
                ang = round(ang / 15) * 15
            r = QTransform()
            r.rotate(ang)
            f.transform = T0 * (QTransform.fromTranslate(-c.x(), -c.y()) * r * QTransform.fromTranslate(c.x(), c.y()))
        else:
            w, h = f.image.width(), f.image.height()
            i = d['idx']
            hx, hy = HANDLES[i]
            ax, ay = HANDLES[(i + 4) % 8]
            hx, hy, ax, ay = hx * w, hy * h, ax * w, ay * h
            inv, ok = T0.inverted()
            m = inv.map(pos)
            sx = (m.x() - ax) / (hx - ax) if hx != ax else 1.0
            sy = (m.y() - ay) / (hy - ay) if hy != ay else 1.0
            corner = i in (0, 2, 4, 6)
            proportional = corner != bool(mods & Qt.ShiftModifier)
            if mods & Qt.AltModifier:   # skalér om centrum
                ax, ay = w / 2, h / 2
                sx = (m.x() - ax) / (hx - ax) if hx != ax else 1.0
                sy = (m.y() - ay) / (hy - ay) if hy != ay else 1.0
            if proportional:
                if hx == ax:
                    sx = sy
                elif hy == ay:
                    sy = sx
                else:
                    s = sx if abs(sx) > abs(sy) else sy
                    sx = math.copysign(abs(s), sx)
                    sy = math.copysign(abs(s), sy)
            if abs(sx) < 0.002:
                sx = 0.002
            if abs(sy) < 0.002:
                sy = 0.002
            M = QTransform.fromTranslate(-ax, -ay) * QTransform.fromScale(sx, sy) * QTransform.fromTranslate(ax, ay)
            f.transform = M * T0
        self.doc.touch()
        self.win.update_status(pos)

    def mouseReleaseEvent(self, e):
        d = self.drag
        self.drag = None
        if d is None:
            return
        doc = self.doc
        pos = self.to_doc(e.position())
        k = d['kind']
        if k in ('float', 'layer'):
            if not d['moved'] and not d['alt']:
                doc.cancel_begin()
        elif k == 'movesel':
            if not d['moved']:
                doc.deselect()
        elif k == 'marquee':
            path = self._marquee_path(d, pos)
            if path is None:
                if d['mode'] == 'new' and doc.has_selection():
                    doc.begin('Fravælg')
                    doc.deselect()
            else:
                self._apply_path_selection(path, d['mode'], d['tool'] == 'rect' or self.win.opt['antialias'])
        elif k == 'lasso':
            pts = d['pts']
            if len(pts) < 3:
                if d['mode'] == 'new' and doc.has_selection():
                    doc.begin('Fravælg')
                    doc.deselect()
            else:
                path = QPainterPath()
                path.addPolygon(QPolygonF(pts))
                path.closeSubpath()
                self._apply_path_selection(path, d['mode'], self.win.opt['antialias'])
        elif k == 'stroke':
            self._commit_stroke()
        self.update_cursor()
        self.update()
        self.win.refresh_layers()

    def mouseDoubleClickEvent(self, e):
        if self.poly is not None:
            self.close_poly()
        else:
            self.mousePressEvent(e)

    def leaveEvent(self, e):
        self.update()

    def wheelEvent(self, e):
        mods = e.modifiers()
        dy = e.angleDelta().y() or e.angleDelta().x()
        if mods & (Qt.ControlModifier | Qt.AltModifier):
            self.zoom_at(self.zoom * (1.2 ** (dy / 120)), e.position())
        elif mods & Qt.ShiftModifier:
            self.offset += QPointF(dy * 0.6, 0)
            self.update()
        else:
            self.offset += QPointF(e.angleDelta().x() * 0.6, e.angleDelta().y() * 0.6)
            self.update()

    # ---------- tastatur ----------
    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Space and not e.isAutoRepeat():
            self.space = True
            self.update_cursor()
            return
        if k in (Qt.Key_Return, Qt.Key_Enter):
            if self.transforming:
                self.end_transform(True)
            elif self.poly is not None:
                self.close_poly()
            return
        if k == Qt.Key_Escape:
            if self.transforming:
                self.end_transform(False)
            elif self.poly is not None:
                self.poly = None
                self.update()
            elif self.drag and self.drag['kind'] in ('marquee', 'lasso'):
                self.drag = None
                self.update()
            return
        arrows = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        if k in arrows:
            dx, dy = arrows[k]
            n = 10 if e.modifiers() & Qt.ShiftModifier else 1
            self.nudge(dx * n, dy * n)
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self.space = False
            self.update_cursor()
            return
        if e.key() in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift):
            self.update_cursor()
        super().keyReleaseEvent(e)

    def nudge(self, dx, dy):
        doc = self.doc
        tool = self.win.tool
        if tool in ('rect', 'ellipse', 'lasso', 'poly', 'wand') and doc.selection is not None and doc.floating is None:
            doc.begin('Skub markering', merge_key=None)
            doc.translate_selection(dx, dy, doc.selection)
            return
        if tool != 'move' and not self.transforming:
            return
        doc.begin('Skub', keep_float=True, merge_key=('nudge', id(doc.layer)))
        if doc.floating is not None or doc.selection is not None:
            if not doc.ensure_float():
                return
            doc.floating.transform = doc.floating.transform * QTransform.fromTranslate(dx, dy)
        else:
            doc.layer.pos = doc.layer.pos + QPoint(dx, dy)
        doc.touch()

    # ---------- frit transformér ----------
    def start_transform(self):
        doc = self.doc
        if self.transforming:
            return True
        doc.begin('Frit transformér', keep_float=True)
        if not doc.ensure_float():
            doc.cancel_begin()
            self.win.flash('Der er ingen pixels at transformere på dette lag.')
            return False
        self.transforming = True
        self.win.on_transform_mode(True)
        doc.touch()
        return True

    def end_transform(self, commit):
        doc = self.doc
        if not self.transforming:
            return
        self.transforming = False
        if commit:
            if doc.floating is not None and doc.floating.whole_layer:
                doc.commit_float()
        else:
            doc.undo()
            doc.redo_stack.clear()
        self.win.on_transform_mode(False)
        self.update_cursor()
        doc.touch()
        self.win.refresh_layers()

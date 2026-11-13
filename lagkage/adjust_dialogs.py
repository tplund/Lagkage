"""Dialoger til justeringslag med live forhåndsvisning."""
import copy
import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QPolygonF
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QSlider, QSpinBox,
                               QDoubleSpinBox, QDialogButtonBox, QLabel, QWidget, QPushButton)

from . import adjust


class Histogram(QWidget):
    def __init__(self, hist, parent=None):
        super().__init__(parent)
        self.hist = hist
        self.setMinimumSize(256, 110)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#262626'))
        h = self.hist
        if h is None or h.max() == 0:
            return
        v = np.sqrt(h.astype(np.float64))
        v = v / v.max()
        W, H = self.width(), self.height()
        p.setPen(QPen(QColor('#9a9a9a')))
        for i in range(256):
            x = i * W / 256.0
            p.drawLine(QPointF(x, H), QPointF(x, H - v[i] * (H - 4)))


class CurveWidget(QWidget):
    """Kurver som i Photoshop: klik tilføjer et punkt, træk flytter, træk ud af feltet sletter."""
    changed = Signal()

    def __init__(self, points, hist, parent=None):
        super().__init__(parent)
        self.points = [list(p) for p in points]
        self.hist = hist
        self.drag = None
        self.setMinimumSize(300, 300)
        self.setMouseTracking(True)
        self.info = ''

    def _m(self):
        return 12

    def to_screen(self, x, y):
        m = self._m()
        s = self.width() - 2 * m, self.height() - 2 * m
        return QPointF(m + x / 255.0 * s[0], m + (255 - y) / 255.0 * s[1])

    def to_val(self, pt):
        m = self._m()
        s = self.width() - 2 * m, self.height() - 2 * m
        return (pt.x() - m) / s[0] * 255.0, 255 - (pt.y() - m) / s[1] * 255.0

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        m = self._m()
        r = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        p.fillRect(r, QColor('#262626'))
        if self.hist is not None and self.hist.max() > 0:
            v = np.sqrt(self.hist.astype(np.float64))
            v = v / v.max()
            p.setPen(QPen(QColor('#3c3c3c')))
            for i in range(256):
                x = r.left() + i * r.width() / 256.0
                p.drawLine(QPointF(x, r.bottom()), QPointF(x, r.bottom() - v[i] * r.height() * 0.9))
        p.setPen(QPen(QColor('#444'), 1))
        for i in range(1, 4):
            x = r.left() + r.width() * i / 4
            y = r.top() + r.height() * i / 4
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        p.setPen(QPen(QColor('#555'), 1, Qt.DashLine))
        p.drawLine(r.bottomLeft(), r.topRight())
        lut = adjust.lut_curves(dict(points=self.points))
        path = QPainterPath()
        for i in range(256):
            q = self.to_screen(i, int(lut[i]))
            path.moveTo(q) if i == 0 else path.lineTo(q)
        p.setPen(QPen(QColor('#e8e8e8'), 1.6))
        p.drawPath(path)
        p.setPen(QPen(QColor('#e8e8e8'), 1))
        for i, (x, y) in enumerate(self.points):
            q = self.to_screen(x, y)
            p.setBrush(QColor('#1473e6') if self.drag == i else QColor('#323232'))
            p.drawRect(QRectF(q.x() - 4, q.y() - 4, 8, 8))
        p.setPen(QColor('#aaa'))
        p.drawText(QRectF(m, self.height() - m, self.width(), m), Qt.AlignLeft | Qt.AlignVCenter, self.info)

    def _hit(self, pt):
        for i, (x, y) in enumerate(self.points):
            if (self.to_screen(x, y) - pt).manhattanLength() < 10:
                return i
        return None

    def mousePressEvent(self, e):
        i = self._hit(e.position())
        if i is None:
            x, y = self.to_val(e.position())
            x = int(round(min(255, max(0, x))))
            y = int(round(min(255, max(0, y))))
            if any(abs(px - x) < 4 for px, _ in self.points):
                return
            self.points.append([x, y])
            self.points.sort()
            i = self.points.index([x, y])
            self.changed.emit()
        self.drag = i
        self.update()

    def mouseMoveEvent(self, e):
        x, y = self.to_val(e.position())
        self.info = f'Input {int(min(255, max(0, x)))}   Output {int(min(255, max(0, y)))}'
        if self.drag is None:
            self.update()
            return
        i = self.drag
        lo = self.points[i - 1][0] + 1 if i > 0 else 0
        hi = self.points[i + 1][0] - 1 if i < len(self.points) - 1 else 255
        inside = -20 <= x <= 275 and -20 <= y <= 275
        if not inside and 0 < i < len(self.points) - 1:
            self.points.pop(i)        # træk ud af feltet sletter punktet
            self.drag = None
        else:
            self.points[i] = [int(round(min(hi, max(lo, x)))), int(round(min(255, max(0, y))))]
        self.changed.emit()
        self.update()

    def mouseReleaseEvent(self, e):
        self.drag = None
        self.update()


def _slider_row(form, label, lo, hi, value, on_change, decimals=0, scale=1):
    row = QHBoxLayout()
    sl = QSlider(Qt.Horizontal)
    sl.setRange(int(lo * scale), int(hi * scale))
    sl.setValue(int(round(value * scale)))
    if decimals:
        sp = QDoubleSpinBox()
        sp.setDecimals(decimals)
        sp.setSingleStep(1 / scale)
    else:
        sp = QSpinBox()
    sp.setRange(lo, hi)
    sp.setValue(value)
    sp.setMinimumWidth(70)

    def from_slider(v):
        sp.blockSignals(True)
        sp.setValue(v / scale)
        sp.blockSignals(False)
        on_change(v / scale if decimals else int(v / scale))

    def from_spin(v):
        sl.blockSignals(True)
        sl.setValue(int(round(v * scale)))
        sl.blockSignals(False)
        on_change(v)
    sl.valueChanged.connect(from_slider)
    sp.valueChanged.connect(from_spin)
    row.addWidget(sl, 1)
    row.addWidget(sp)
    form.addRow(label, row)
    return sl, sp


class AdjustDialog(QDialog):
    """Ændrer layer.adjust live; Annullér sætter de gamle værdier tilbage."""

    def __init__(self, win, doc, layer, hist):
        super().__init__(win)
        self.doc, self.layer = doc, layer
        self.orig = copy.deepcopy(layer.adjust)
        self.p = layer.adjust['params']
        kind = layer.adjust['type']
        self.setWindowTitle(adjust.NAMES[kind])
        lay = QVBoxLayout(self)
        form = QFormLayout()
        if kind == 'levels':
            lay.addWidget(Histogram(hist))
            self._ib = _slider_row(form, 'Sort input:', 0, 253, self.p['in_black'], lambda v: self.set('in_black', v))[1]
            _slider_row(form, 'Gamma:', 0.1, 9.99, self.p['gamma'], lambda v: self.set('gamma', v), 2, 100)
            self._iw = _slider_row(form, 'Hvid input:', 2, 255, self.p['in_white'], lambda v: self.set('in_white', v))[1]
            _slider_row(form, 'Sort output:', 0, 255, self.p['out_black'], lambda v: self.set('out_black', v))
            _slider_row(form, 'Hvid output:', 0, 255, self.p['out_white'], lambda v: self.set('out_white', v))
            auto = QPushButton('Auto')
            auto.setToolTip('Stræk tonerne, så de mørkeste og lyseste 0,1 % bliver sort og hvid')
            auto.clicked.connect(lambda: self._auto_levels(hist))
            form.addRow('', auto)
            self._levels_form = form
        elif kind == 'curves':
            cw = CurveWidget(self.p['points'], hist)
            cw.changed.connect(lambda: self.set('points', [list(q) for q in cw.points]))
            lay.addWidget(cw, 1)
            hint = QLabel('Klik for at tilføje et punkt · træk for at flytte · træk et punkt ud af feltet for at slette')
            hint.setStyleSheet('color:#999')
            lay.addWidget(hint)
            reset = QPushButton('Nulstil')
            reset.clicked.connect(lambda: (setattr(cw, 'points', [[0, 0], [255, 255]]), cw.changed.emit(), cw.update()))
            form.addRow('', reset)
        elif kind == 'brightness':
            _slider_row(form, 'Lysstyrke:', -150, 150, self.p['brightness'], lambda v: self.set('brightness', v))
            _slider_row(form, 'Kontrast:', -50, 100, self.p['contrast'], lambda v: self.set('contrast', v))
        elif kind == 'hue_sat':
            _slider_row(form, 'Farvetone:', -180, 180, self.p['hue'], lambda v: self.set('hue', v))
            _slider_row(form, 'Mætning:', -100, 100, self.p['saturation'], lambda v: self.set('saturation', v))
            _slider_row(form, 'Lyshed:', -100, 100, self.p['lightness'], lambda v: self.set('lightness', v))
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.resize(420 if kind != 'curves' else 380, self.sizeHint().height())

    def set(self, key, value):
        self.p[key] = value
        self.doc.touch()

    def _auto_levels(self, hist):
        if hist is None or hist.sum() == 0:
            return
        c = np.cumsum(hist) / hist.sum()
        lo = int(np.searchsorted(c, 0.001))
        hi = int(np.searchsorted(c, 0.999))
        self._ib.setValue(min(lo, 253))
        self._iw.setValue(max(hi, lo + 2))

    def reject(self):
        self.layer.adjust = self.orig
        self.doc.touch()
        super().reject()

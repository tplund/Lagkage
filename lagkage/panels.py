"""Paneler: værktøjslinje, farvefelter, indstillingslinje og lagpanel."""
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, QSize, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics, QBrush
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QButtonGroup, QLabel,
                               QSpinBox, QCheckBox, QComboBox, QScrollArea, QLineEdit, QFrame,
                               QSizePolicy, QColorDialog)

from .icons import icon, svg_pixmap
from .imageops import checker_brush_image
from .document import BLEND_MODES

TOOLS = [
    ('move', 'Flyt (V)'),
    ('rect', 'Rektangulær markering (M)'),
    ('ellipse', 'Elliptisk markering (Shift+M)'),
    ('lasso', 'Lasso (L)'),
    ('poly', 'Polygonlasso (Shift+L)'),
    ('wand', 'Tryllestav (W)'),
    ('crop', None),
    ('eyedropper', 'Pipette (I)'),
    ('brush', 'Pensel (B)'),
    ('eraser', 'Viskelæder (E)'),
    ('bucket', 'Malerspand (G)'),
    ('hand', 'Hånd (H) – eller hold mellemrum'),
    ('zoom', 'Zoom (Z) – Alt-klik zoomer ud'),
]


class ColorSwatches(QWidget):
    """Forgrunds-/baggrundsfarve som i Photoshop."""
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setFixedSize(52, 56)
        self.setToolTip('Forgrundsfarve / baggrundsfarve\nD: standardfarver · X: byt om')

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        bg = QRect(20, 22, 24, 24)
        fg = QRect(6, 8, 24, 24)
        for r, c in ((bg, self.win.bg), (fg, self.win.fg)):
            p.setPen(QPen(QColor(0, 0, 0), 1))
            p.setBrush(c)
            p.drawRect(r)
            p.setPen(QPen(QColor(255, 255, 255), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r.adjusted(1, 1, -1, -1))
        # små ikoner: standard og byt
        p.setPen(QPen(QColor(0, 0, 0), 1))
        p.setBrush(QColor(0, 0, 0))
        p.drawRect(6, 38, 6, 6)
        p.setBrush(QColor(255, 255, 255))
        p.drawRect(10, 42, 6, 6)
        p.drawPixmap(34, 2, svg_pixmap('swap', 14))

    def mousePressEvent(self, e):
        x, y = e.position().x(), e.position().y()
        if x >= 32 and y <= 18:
            self.win.swap_colors()
        elif x <= 18 and y >= 36:
            self.win.default_colors()
        elif QRect(6, 8, 24, 24).contains(int(x), int(y)):
            self._pick('fg')
        elif QRect(20, 22, 24, 24).contains(int(x), int(y)):
            self._pick('bg')

    def _pick(self, which):
        cur = self.win.fg if which == 'fg' else self.win.bg
        c = QColorDialog.getColor(cur, self, 'Vælg forgrundsfarve' if which == 'fg' else 'Vælg baggrundsfarve')
        if c.isValid():
            (self.win.set_fg if which == 'fg' else self.win.set_bg)(c)


class ToolBox(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName('toolbox')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(1)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for name, tip in TOOLS:
            if tip is None:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setStyleSheet('color:#444')
                lay.addWidget(line)
                continue
            b = QToolButton()
            b.setIcon(icon(name, 20))
            b.setIconSize(QSize(20, 20))
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.NoFocus)
            b.setFixedSize(32, 30)
            b.clicked.connect(lambda _=False, n=name: win.set_tool(n))
            self.group.addButton(b)
            self.buttons[name] = b
            lay.addWidget(b, 0, Qt.AlignHCenter)
        lay.addSpacing(10)
        self.swatches = ColorSwatches(win)
        lay.addWidget(self.swatches, 0, Qt.AlignHCenter)
        lay.addStretch(1)

    def select(self, name):
        if name in self.buttons:
            self.buttons[name].setChecked(True)


# ---------------- indstillingslinje ----------------

SEL_OPTS = [('mode',), ('spin', 'feather', 'Blødgør:', 0, 250, ' px')]
OPTION_SPECS = {
    'move': [('label', 'Alt-træk kopierer  ·  Shift låser retningen  ·  Ctrl+T transformerer  ·  piletaster skubber 1 px (Shift: 10 px)')],
    'rect': SEL_OPTS,
    'ellipse': SEL_OPTS + [('check', 'antialias', 'Udjævning')],
    'lasso': SEL_OPTS + [('check', 'antialias', 'Udjævning')],
    'poly': SEL_OPTS + [('check', 'antialias', 'Udjævning'),
                        ('label', 'Klik for hjørner · dobbeltklik eller Enter lukker · Esc annullerer')],
    'wand': [('mode',), ('spin', 'tolerance', 'Tolerance:', 0, 255, ''),
             ('check', 'contiguous', 'Sammenhængende'), ('check', 'sample_all', 'Prøve fra alle lag')],
    'eyedropper': [('check', 'eyedrop_all', 'Prøve fra alle lag'), ('label', 'Alt-klik sætter baggrundsfarven')],
    'brush': [('spin', 'size', 'Størrelse:', 1, 2500, ' px'), ('spin', 'opacity', 'Opacitet:', 1, 100, ' %'),
              ('label', '[ og ] ændrer størrelse  ·  Shift-klik tegner en lige linje  ·  Alt-klik tager farve')],
    'eraser': [('spin', 'size', 'Størrelse:', 1, 2500, ' px'), ('spin', 'opacity', 'Opacitet:', 1, 100, ' %')],
    'bucket': [('spin', 'tolerance', 'Tolerance:', 0, 255, ''), ('check', 'contiguous', 'Sammenhængende'),
               ('check', 'sample_all', 'Prøve fra alle lag'), ('spin', 'opacity', 'Opacitet:', 1, 100, ' %')],
    'hand': [('label', 'Træk for at panorere  ·  Ctrl+0 tilpasser  ·  Ctrl+1 = 100 %')],
    'zoom': [('label', 'Klik zoomer ind  ·  Alt-klik zoomer ud  ·  Ctrl/Alt + hjul zoomer')],
}
MODE_BTNS = [('new', 'mode_new', 'Ny markering'), ('add', 'mode_add', 'Føj til markering (Shift)'),
             ('sub', 'mode_sub', 'Træk fra markering (Alt)'), ('int', 'mode_int', 'Fællesmængde (Shift+Alt)')]


class OptionsBar(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName('optionsbar')
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(10, 3, 10, 3)
        self.lay.setSpacing(8)
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    def _clear(self):
        while self.lay.count():
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()

    def build(self, tool, transforming=False):
        self._clear()
        tl = QLabel()
        tl.setPixmap(svg_pixmap(tool if tool != 'hand' or True else 'hand', 20))
        self.lay.addWidget(tl)
        self.lay.addSpacing(6)
        if transforming:
            l = QLabel('Frit transformér:  træk i håndtag for at skalere (Shift: frit)  ·  '
                       'udenfor for at rotere (Shift: 15°)  ·  Alt: om centrum')
            l.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            self.lay.addWidget(l, 1)
            for txt, commit in (('✕  Annullér (Esc)', False), ('✓  Udfør (Enter)', True)):
                b = QToolButton()
                b.setText(txt)
                b.setFocusPolicy(Qt.NoFocus)
                b.clicked.connect(lambda _=False, c=commit: self.win.canvas().end_transform(c))
                self.lay.addWidget(b)
            return
        opt = self.win.opt
        for spec in OPTION_SPECS.get(tool, []):
            kind = spec[0]
            if kind == 'label':
                l = QLabel(spec[1])
                l.setStyleSheet('color:#9a9a9a')
                l.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                l.setMinimumWidth(40)
                self.lay.addWidget(l)
            elif kind == 'mode':
                grp = QButtonGroup(self)
                for key, ic, tip in MODE_BTNS:
                    b = QToolButton()
                    b.setIcon(icon(ic, 18))
                    b.setCheckable(True)
                    b.setToolTip(tip)
                    b.setFocusPolicy(Qt.NoFocus)
                    b.setChecked(opt['selmode'] == key)
                    b.clicked.connect(lambda _=False, k=key: opt.__setitem__('selmode', k))
                    grp.addButton(b)
                    self.lay.addWidget(b)
                self.lay.addSpacing(8)
            elif kind == 'spin':
                _, key, label, lo, hi, suffix = spec
                self.lay.addWidget(QLabel(label))
                s = QSpinBox()
                s.setRange(lo, hi)
                s.setValue(opt[key])
                s.setSuffix(suffix)
                s.setKeyboardTracking(False)
                s.valueChanged.connect(lambda v, k=key: opt.__setitem__(k, v))
                s.editingFinished.connect(lambda: self.win.canvas() and self.win.canvas().setFocus())
                self.lay.addWidget(s)
            elif kind == 'check':
                _, key, label = spec
                c = QCheckBox(label)
                c.setChecked(opt[key])
                c.setFocusPolicy(Qt.NoFocus)
                c.toggled.connect(lambda v, k=key: opt.__setitem__(k, v))
                self.lay.addWidget(c)
        self.lay.addStretch(1)


# ---------------- lagpanel ----------------

ROW_H = 44
EYE_W = 30
THUMB = 36


class LayersList(QWidget):
    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.setMouseTracking(True)
        self.drag = None
        self.editor = None
        self._thumbs = {}
        self._checker = QBrush(checker_brush_image(4))

    @property
    def doc(self):
        return self.panel.win.doc()

    def sizeHint(self):
        n = len(self.doc.layers) if self.doc else 0
        return QSize(220, n * ROW_H)

    def refresh(self):
        n = len(self.doc.layers) if self.doc else 0
        self.setMinimumHeight(n * ROW_H)
        self.update()

    def row_layer_index(self, y):
        doc = self.doc
        row = int(y // ROW_H)
        if not doc or row < 0 or row >= len(doc.layers):
            return None
        return len(doc.layers) - 1 - row

    def _thumb(self, L):
        doc = self.doc
        key = (id(L), L.image.cacheKey(), L.pos.x(), L.pos.y(), doc.width, doc.height,
               id(doc.floating) if doc.floating and doc.floating.layer is L else 0)
        t = self._thumbs.get(id(L))
        if t and t[0] == key:
            return t[1]
        from PySide6.QtGui import QImage, QTransform
        from .imageops import new_image
        s = min(THUMB / doc.width, THUMB / doc.height)
        w, h = max(1, round(doc.width * s)), max(1, round(doc.height * s))
        img = new_image(w, h)
        p = QPainter(img)
        p.fillRect(img.rect(), self._checker)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.scale(s, s)
        p.drawImage(L.pos, L.image)
        p.end()
        self._thumbs[id(L)] = (key, img)
        return img

    def paintEvent(self, e):
        doc = self.doc
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#2b2b2b'))
        if not doc:
            return
        fm = QFontMetrics(self.font())
        n = len(doc.layers)
        for row in range(n):
            i = n - 1 - row
            L = doc.layers[i]
            y = row * ROW_H
            r = QRect(0, y, self.width(), ROW_H)
            if i == doc.active:
                p.fillRect(r, QColor('#46505c'))
            p.setPen(QColor('#1d1d1d'))
            p.drawLine(0, y + ROW_H - 1, self.width(), y + ROW_H - 1)
            p.drawLine(EYE_W, y, EYE_W, y + ROW_H - 1)
            if L.visible:
                p.drawPixmap(EYE_W // 2 - 9, y + ROW_H // 2 - 9, svg_pixmap('eye', 18))
            t = self._thumb(L)
            tx = EYE_W + 8 + (THUMB - t.width()) // 2
            ty = y + (ROW_H - t.height()) // 2
            p.drawImage(tx, ty, t)
            p.setPen(QColor('#111'))
            p.drawRect(tx - 1, ty - 1, t.width() + 1, t.height() + 1)
            p.setPen(QColor('#e8e8e8') if L.visible else QColor('#8a8a8a'))
            nx = EYE_W + THUMB + 18
            name = fm.elidedText(L.name, Qt.ElideRight, self.width() - nx - 8)
            has_info = L.opacity < 1 or L.blend != 'normal'
            name_rect = QRect(nx, y + 4, self.width() - nx - 4, ROW_H // 2 - 2) if has_info else                 QRect(nx, y, self.width() - nx - 4, ROW_H)
            p.drawText(name_rect, (Qt.AlignBottom if has_info else Qt.AlignVCenter) | Qt.AlignLeft, name)
            if has_info:
                p.setPen(QColor('#8a8a8a'))
                small = QFont(self.font())
                small.setPointSizeF(self.font().pointSizeF() * 0.85)
                p.setFont(small)
                info = f'{round(L.opacity * 100)} %' + ('' if L.blend == 'normal' else '  ' + dict(
                    (k, v) for k, v, _ in BLEND_MODES)[L.blend])
                p.drawText(QRect(nx, y + ROW_H // 2 + 2, self.width() - nx - 4, ROW_H // 2 - 2),
                           Qt.AlignTop | Qt.AlignLeft, info)
                p.setFont(self.font())
        if self.drag and self.drag.get('moving'):
            row = self.drag['target_row']
            p.setPen(QPen(QColor('#1e90ff'), 2))
            p.drawLine(0, row * ROW_H, self.width(), row * ROW_H)

    def mousePressEvent(self, e):
        doc = self.doc
        if not doc:
            return
        x, y = e.position().x(), e.position().y()
        i = self.row_layer_index(y)
        if i is None:
            return
        win = self.panel.win
        L = doc.layers[i]
        if x < EYE_W:
            if e.modifiers() & Qt.AltModifier:
                others = [M for M in doc.layers if M is not L]
                solo = all(not M.visible for M in others)
                for M in others:
                    M.visible = solo
                L.visible = True
            else:
                L.visible = not L.visible
            doc.dirty = True
            doc.touch()
            win.refresh_layers()
            return
        if e.modifiers() & Qt.ControlModifier and x < EYE_W + THUMB + 14:
            doc.begin('Indlæs markering')
            doc.selection_from_layer(L)
            win.refresh_layers()
            return
        win.set_active_layer(i)
        self.drag = dict(start=e.position(), index=i, moving=False, target_row=0)

    def mouseMoveEvent(self, e):
        if not self.drag or not (e.buttons() & Qt.LeftButton):
            return
        if abs(e.position().y() - self.drag['start'].y()) > 5:
            self.drag['moving'] = True
        if self.drag['moving']:
            n = len(self.doc.layers)
            self.drag['target_row'] = max(0, min(n, round(e.position().y() / ROW_H)))
            self.update()

    def mouseReleaseEvent(self, e):
        d = self.drag
        self.drag = None
        if d and d['moving']:
            n = len(self.doc.layers)
            row = d['target_row']
            src = d['index']
            src_row = n - 1 - src
            dst_row = row if row <= src_row else row - 1
            dst = n - 1 - dst_row
            if dst != src:
                self.doc.begin('Flyt lag')
                self.doc.move_layer(src, dst)
            self.panel.win.refresh_layers()
        self.update()

    def contextMenuEvent(self, e):
        from PySide6.QtWidgets import QMenu
        win = self.panel.win
        if not self.doc:
            return
        i = self.row_layer_index(e.pos().y())
        if i is not None:
            win.set_active_layer(i)
        m = QMenu(self)
        for text, fn, key in (('Nyt lag', win.new_layer, 'Ctrl+Shift+N'),
                              ('Duplikér lag', win.duplicate_layer, 'Ctrl+J'),
                              ('Omdøb lag', win.rename_layer, 'F2'),
                              (None, None, None),
                              ('Flet ned', win.merge_down, 'Ctrl+E'),
                              ('Flet synlige', win.merge_visible, 'Ctrl+Shift+E'),
                              ('Gør til ét lag', win.flatten, ''),
                              (None, None, None),
                              ('Flyt op', lambda: win.arrange('up'), 'Ctrl+]'),
                              ('Flyt ned', lambda: win.arrange('down'), 'Ctrl+['),
                              (None, None, None),
                              ('Slet lag', win.delete_layer, '')):
            if text is None:
                m.addSeparator()
                continue
            a = m.addAction(text + (f'	{key}' if key else ''))
            a.triggered.connect(lambda _=False, f=fn: (f(), win.refresh_layers()))
        m.exec(e.globalPos())

    def mouseDoubleClickEvent(self, e):
        i = self.row_layer_index(e.position().y())
        if i is None or e.position().x() < EYE_W + THUMB + 14:
            return
        self.start_rename(i)

    def start_rename(self, i):
        doc = self.doc
        n = len(doc.layers)
        row = n - 1 - i
        nx = EYE_W + THUMB + 14
        ed = QLineEdit(doc.layers[i].name, self)
        ed.setGeometry(nx, row * ROW_H + 10, self.width() - nx - 6, ROW_H - 20)
        ed.selectAll()
        ed.show()
        ed.setFocus()
        self.editor = ed

        def done():
            if self.editor is not ed:
                return
            self.editor = None
            txt = ed.text().strip()
            if txt and txt != doc.layers[i].name:
                doc.begin('Omdøb lag')
                doc.layers[i].name = txt
                doc.touch()
            ed.deleteLater()
            self.panel.win.refresh_layers()
            c = self.panel.win.canvas()
            if c:
                c.setFocus()
        ed.editingFinished.connect(done)


class LayersPanel(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._updating = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        top = QHBoxLayout()
        top.setContentsMargins(6, 6, 6, 6)
        self.blend = QComboBox()
        for key, label, _ in BLEND_MODES:
            self.blend.addItem(label, key)
        self.blend.setFocusPolicy(Qt.NoFocus)
        self.blend.currentIndexChanged.connect(self._blend_changed)
        top.addWidget(self.blend, 1)
        top.addWidget(QLabel('Opacitet:'))
        self.opacity = QSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setSuffix(' %')
        self.opacity.valueChanged.connect(self._opacity_changed)
        top.addWidget(self.opacity)
        lay.addLayout(top)
        self.list = LayersList(self)
        sa = QScrollArea()
        sa.setWidget(self.list)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        lay.addWidget(sa, 1)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(6, 4, 6, 4)
        bottom.addStretch(1)
        for ic, tip, fn in (('new_layer', 'Nyt lag (Ctrl+Shift+N)', win.new_layer),
                            ('dup_layer', 'Duplikér lag (Ctrl+J)', win.duplicate_layer),
                            ('merge', 'Flet ned (Ctrl+E)', win.merge_down),
                            ('trash', 'Slet lag', win.delete_layer)):
            b = QToolButton()
            b.setIcon(icon(ic, 18))
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(fn)
            bottom.addWidget(b)
        lay.addLayout(bottom)

    def refresh(self):
        doc = self.win.doc()
        self._updating = True
        enabled = doc is not None
        self.blend.setEnabled(enabled)
        self.opacity.setEnabled(enabled)
        if doc:
            L = doc.layer
            self.blend.setCurrentIndex(max(0, self.blend.findData(L.blend)))
            self.opacity.setValue(round(L.opacity * 100))
        self._updating = False
        self.list.refresh()

    def _blend_changed(self, idx):
        doc = self.win.doc()
        if self._updating or not doc:
            return
        doc.begin('Blandingstilstand')
        doc.layer.blend = self.blend.itemData(idx)
        doc.touch()
        self.list.update()

    def _opacity_changed(self, v):
        doc = self.win.doc()
        if self._updating or not doc:
            return
        doc.begin('Opacitet', keep_float=True, merge_key=('opacity', id(doc.layer)))
        doc.layer.opacity = v / 100.0
        doc.touch()
        self.list.update()

"""Hovedvinduet: menuer, genveje, faner og filhåndtering."""
import os
from PySide6.QtCore import Qt, QSettings, QPoint, QPointF, QTimer, QRect
from PySide6.QtGui import QAction, QKeySequence, QColor, QImage, QTransform, QIcon
from PySide6.QtWidgets import (QMainWindow, QTabWidget, QDockWidget, QFileDialog, QMessageBox, QLabel,
                               QWidget, QHBoxLayout, QVBoxLayout, QDialog, QFormLayout, QSpinBox,
                               QComboBox, QDialogButtonBox, QCheckBox, QInputDialog, QApplication,
                               QColorDialog, QStatusBar)

from .document import Document, Layer, load_document, save_psd, save_flat, FLAT_EXT
from .imageops import new_image, FMT
from . import imageops as io_
from .canvas import Canvas
from .panels import ToolBox, OptionsBar, LayersPanel
from .icons import icon

APP = 'Lagkage'
OPEN_FILTER = 'Billeder (*.psd *.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp);;Alle filer (*)'
SAVE_FILTERS = {
    'Photoshop (*.psd)': '.psd', 'PNG (*.png)': '.png', 'JPEG (*.jpg)': '.jpg',
    'BMP (*.bmp)': '.bmp', 'WebP (*.webp)': '.webp', 'TIFF (*.tif)': '.tif',
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP)
        self.settings = QSettings(APP, APP)
        self.fg, self.bg = QColor(0, 0, 0), QColor(255, 255, 255)
        self.tool = 'move'
        self.opt = dict(selmode='new', feather=0, antialias=True, tolerance=32, contiguous=True,
                        sample_all=False, eyedrop_all=True, size=20, hardness=100, opacity=100)
        self.clip_origin = None
        self._last_marquee, self._last_lasso = 'rect', 'lasso'

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.empty = QLabel('Træk et billede herind, eller tryk Ctrl+O for at åbne,\n'
                            'Ctrl+N for et nyt dokument, Ctrl+V for at indsætte fra udklipsholderen.')
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet('color:#777; font-size:14px')
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self.options = OptionsBar(self)
        cl.addWidget(self.options)
        self.update_bar = self._make_update_bar()
        cl.addWidget(self.update_bar)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.toolbox = ToolBox(self)
        body.addWidget(self.toolbox)
        body.addWidget(self.tabs, 1)
        body.addWidget(self.empty, 1)
        cl.addLayout(body, 1)
        self.setCentralWidget(central)

        self.layers_panel = LayersPanel(self)
        dock = QDockWidget('Lag', self)
        dock.setObjectName('layers')
        dock.setWidget(self.layers_panel)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        dock.setMinimumWidth(250)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        sb = QStatusBar()
        self.setStatusBar(sb)
        self.st_zoom, self.st_size, self.st_pos, self.st_msg = QLabel(), QLabel(), QLabel(), QLabel()
        for w in (self.st_zoom, self.st_size, self.st_pos):
            w.setMinimumWidth(110)
            sb.addWidget(w)
        sb.addWidget(self.st_msg, 1)

        self._build_menus()
        self.setAcceptDrops(True)
        self.set_tool('move')
        self._update_empty()
        QTimer.singleShot(2000, self._preload_inpaint)
        from .updater import UpdateChecker, is_installed
        self.updater = UpdateChecker(self)
        self.updater.found.connect(self._on_update_found)
        self.updater.none.connect(lambda msg: QMessageBox.information(self, APP, msg))
        if is_installed():
            QTimer.singleShot(4000, lambda: self.updater.check(quiet=True))
        geo = self.settings.value('geometry')
        if geo:
            self.restoreGeometry(geo)
        else:
            self.resize(1400, 900)

    # ================= opdatering =================
    def _make_update_bar(self):
        from PySide6.QtWidgets import QPushButton
        bar = QWidget()
        bar.setObjectName('updatebar')
        bar.setStyleSheet('#updatebar { background:#1f4f8f; } #updatebar QLabel { color:white; }')
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 4, 12, 4)
        self.update_label = QLabel()
        lay.addWidget(self.update_label, 1)
        now = QPushButton('Opdatér nu')
        later = QPushButton('Senere')
        now.clicked.connect(lambda: self.do_update(self._update_info))
        later.clicked.connect(bar.hide)
        lay.addWidget(now)
        lay.addWidget(later)
        bar.hide()
        self._update_info = None
        return bar

    def _on_update_found(self, info):
        from . import __version__
        self._update_info = info
        self.update_label.setText(f"Lagkage {info['version']} er klar (du har {__version__}). "
                                  "Opdateringen tager et øjeblik, og programmet starter selv igen.")
        self.update_bar.show()

    def check_updates(self):
        from .updater import is_installed
        if not is_installed():
            QMessageBox.information(self, APP, 'Dette er udviklingsudgaven af Lagkage, som opdateres direkte fra '
                                    'koden. Den installerede udgave tjekker selv for opdateringer.')
            return
        self.updater.check(quiet=False)

    def do_update(self, info):
        from PySide6.QtWidgets import QProgressDialog
        from . import updater
        if not info:
            return
        # luk dokumenterne først (spørger om at gemme)
        while self.tabs.count():
            if self.close_tab(self.tabs.count() - 1) is False:
                return
        dlg = QProgressDialog(f"Henter Lagkage {info['version']} …", 'Annullér', 0, 100, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.show()

        def prog(done, total):
            dlg.setValue(int(done * 100 / total) if total else 0)
            QApplication.processEvents()
            return not dlg.wasCanceled()
        try:
            path = updater.download(info, prog)
        except Exception as e:
            dlg.close()
            QMessageBox.warning(self, APP, 'Opdateringen kunne ikke hentes: ' + str(e))
            return
        dlg.close()
        if not path:
            return
        updater.run_installer(path)
        self.settings.setValue('geometry', self.saveGeometry())
        QApplication.quit()

    def show_about(self):
        from . import __version__
        QMessageBox.about(self, 'Om Lagkage', f'<b>Lagkage {__version__}</b><br>'
                          'En lille billededitor med Photoshops genveje.<br><br>'
                          '<a href="https://github.com/tplund/Lagkage">github.com/tplund/Lagkage</a>')

    def _preload_inpaint(self):
        try:
            from . import inpaint
            inpaint.preload()
        except Exception:
            pass

    # ================= hjælpere =================
    def canvas(self):
        w = self.tabs.currentWidget()
        return w if isinstance(w, Canvas) else None

    def doc(self):
        c = self.canvas()
        return c.doc if c else None

    def flash(self, msg, ms=4000):
        self.st_msg.setText(msg)
        QTimer.singleShot(ms, lambda: self.st_msg.text() == msg and self.st_msg.setText(''))

    def update_status(self, pos=None):
        c = self.canvas()
        if not c:
            self.st_zoom.setText('')
            self.st_size.setText('')
            self.st_pos.setText('')
            return
        self.st_zoom.setText(f'{c.zoom * 100:.4g} %')
        self.st_size.setText(f'{c.doc.width} × {c.doc.height} px')
        if pos is not None:
            self.st_pos.setText(f'X {int(pos.x())}  Y {int(pos.y())}')

    def _update_empty(self):
        has = self.tabs.count() > 0
        self.tabs.setVisible(has)
        self.empty.setVisible(not has)

    def refresh_layers(self):
        self.layers_panel.refresh()
        self._update_tab_title()

    def _update_tab_title(self):
        c = self.canvas()
        if c:
            self.tabs.setTabText(self.tabs.currentIndex(), c.doc.title())
            self.setWindowTitle(f'{c.doc.title()} – {APP}')
        else:
            self.setWindowTitle(APP)

    def _tab_changed(self, _):
        self.refresh_layers()
        self.update_status()
        c = self.canvas()
        if c and self.tool == 'crop' and c.crop is None:
            c.start_crop()
        self.options.build(self.tool, bool(c and c.transforming))
        if c:
            c.setFocus()

    def _doc_changed(self):
        self.layers_panel.list.update()
        self._update_tab_title()

    # ================= værktøjer og farver =================
    def set_tool(self, name):
        c = self.canvas()
        if c and c.transforming:
            c.end_transform(True)
        if c and c.poly is not None and name != 'poly':
            c.poly = None
        if c:
            if name == 'crop':
                c.start_crop()
            else:
                c.cancel_crop()
        self.tool = name
        if name in ('rect', 'ellipse'):
            self._last_marquee = name
        if name in ('lasso', 'poly'):
            self._last_lasso = name
        self.toolbox.select(name)
        self.options.build(name)
        if c:
            c.update_cursor()
            c.update()
            c.setFocus()

    def cycle(self, a, b, last_attr):
        last = getattr(self, last_attr)
        if self.tool in (a, b):
            self.set_tool(b if self.tool == a else a)
        else:
            self.set_tool(last)

    def set_fg(self, c):
        self.fg = QColor(c)
        self.toolbox.swatches.update()

    def set_bg(self, c):
        self.bg = QColor(c)
        self.toolbox.swatches.update()

    def swap_colors(self):
        self.fg, self.bg = self.bg, self.fg
        self.toolbox.swatches.update()

    def default_colors(self):
        self.fg, self.bg = QColor(0, 0, 0), QColor(255, 255, 255)
        self.toolbox.swatches.update()

    def brush_size(self, d):
        s = self.opt['size']
        step = 1 if s < 10 else 5 if s < 50 else 10 if s < 100 else 25 if s < 300 else 50
        self.opt['size'] = max(1, min(2500, s + d * step))
        self.options.build(self.tool)
        c = self.canvas()
        if c:
            c.update()
            c.setFocus()

    def brush_hardness(self, d):
        self.opt['hardness'] = max(0, min(100, self.opt['hardness'] + d))
        self.options.build(self.tool)
        self.flash(f"Hårdhed {self.opt['hardness']} %", 1500)
        c = self.canvas()
        if c:
            c.setFocus()

    def on_transform_mode(self, on):
        self.options.build(self.tool, on)

    def on_transform_mode_refresh(self):
        pass

    # ================= menuer =================
    def _act(self, menu, text, fn, keys=None, tip=None):
        a = QAction(text, self)
        if keys:
            if isinstance(keys, (list, tuple)):
                a.setShortcuts([QKeySequence(k) for k in keys])
            else:
                a.setShortcut(QKeySequence(keys))
        a.setShortcutContext(Qt.WindowShortcut)
        a.triggered.connect(lambda _=False: fn())
        if menu is not None:
            menu.addAction(a)
        else:
            self.addAction(a)
        return a

    def _need(self, fn, label=None, keep_float=False):
        """Pak en handling ind, så den kun kører med et åbent dokument."""
        def run():
            d = self.doc()
            if d is None:
                return
            c = self.canvas()
            if c.transforming and fn.__name__ not in ('_undo',):
                c.end_transform(True)
            fn()
            self.refresh_layers()
        return run

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu('&Filer')
        self._act(m, 'Ny…', self.new_document, 'Ctrl+N')
        self._act(m, 'Åbn…', self.open_dialog, 'Ctrl+O')
        self.recent_menu = m.addMenu('Åbn seneste')
        self._fill_recent()
        m.addSeparator()
        self._act(m, 'Indsæt fil som lag…', self._need(self.place_file), 'Ctrl+Shift+P')
        m.addSeparator()
        self._act(m, 'Luk', lambda: self.close_tab(self.tabs.currentIndex()), 'Ctrl+W')
        self._act(m, 'Gem', self._need(self.save), 'Ctrl+S')
        self._act(m, 'Gem som…', self._need(self.save_as), 'Ctrl+Shift+S')
        self._act(m, 'Eksportér hurtigt som PNG', self._need(lambda: self.save_as('.png')), 'Ctrl+Alt+Shift+W')
        m.addSeparator()
        self._act(m, 'Afslut', self.close, 'Ctrl+Q')

        m = mb.addMenu('&Rediger')
        self._act(m, 'Fortryd', self._undo, 'Ctrl+Z')
        self._act(m, 'Annuller fortryd', self._redo, ['Ctrl+Shift+Z', 'Ctrl+Y'])
        self._act(m, 'Træd tilbage', self._undo, 'Ctrl+Alt+Z')
        m.addSeparator()
        self._act(m, 'Klip', self._need(self.cut), 'Ctrl+X')
        self._act(m, 'Kopiér', self._need(self.copy), 'Ctrl+C')
        self._act(m, 'Kopiér flettet', self._need(self.copy_merged), 'Ctrl+Shift+C')
        self._act(m, 'Sæt ind', self.paste, 'Ctrl+V')
        self._act(m, 'Sæt ind på stedet', lambda: self.paste(in_place=True), 'Ctrl+Shift+V')
        self._act(m, 'Ryd', self._clear_or_poly, ['Del', 'Backspace'])
        m.addSeparator()
        self._act(m, 'Udfyld…', self._need(self.fill_dialog), ['Shift+F5', 'Shift+Backspace'])
        self._act(m, 'Indholdsbevidst udfyld', self._need(self.content_aware))
        self._act(m, 'Udfyld med forgrundsfarve', self._need(lambda: self.quick_fill(self.fg)), 'Alt+Backspace')
        self._act(m, 'Udfyld med baggrundsfarve', self._need(lambda: self.quick_fill(self.bg)), 'Ctrl+Backspace')
        self._act(m, 'Udfyld forgrund, bevar gennemsigtighed', self._need(lambda: self.quick_fill(self.fg, True)),
                  'Shift+Alt+Backspace')
        self._act(m, 'Udfyld baggrund, bevar gennemsigtighed', self._need(lambda: self.quick_fill(self.bg, True)),
                  'Shift+Ctrl+Backspace')
        m.addSeparator()
        self._act(m, 'Frit transformér', self._need(lambda: self.canvas().start_transform()), 'Ctrl+T')
        t = m.addMenu('Transformér')
        self._act(t, 'Rotér 180°', self._need(lambda: self.layer_transform(QTransform().rotate(180))))
        self._act(t, 'Rotér 90° med uret', self._need(lambda: self.layer_transform(QTransform().rotate(90))))
        self._act(t, 'Rotér 90° mod uret', self._need(lambda: self.layer_transform(QTransform().rotate(-90))))
        t.addSeparator()
        self._act(t, 'Spejlvend vandret', self._need(lambda: self.layer_transform(QTransform.fromScale(-1, 1))))
        self._act(t, 'Spejlvend lodret', self._need(lambda: self.layer_transform(QTransform.fromScale(1, -1))))

        m = mb.addMenu('&Billede')
        self._act(m, 'Billedstørrelse…', self._need(self.image_size_dialog), 'Ctrl+Alt+I')
        self._act(m, 'Lærredsstørrelse…', self._need(self.canvas_size_dialog), 'Ctrl+Alt+C')
        r = m.addMenu('Billedrotation')
        for txt, k in (('180°', '180'), ('90° med uret', 'cw'), ('90° mod uret', 'ccw')):
            self._act(r, txt, self._need(lambda k=k: self.rotate_canvas(k)))
        r.addSeparator()
        self._act(r, 'Spejlvend lærred vandret', self._need(lambda: self.rotate_canvas('fh')))
        self._act(r, 'Spejlvend lærred lodret', self._need(lambda: self.rotate_canvas('fv')))
        m.addSeparator()
        self._act(m, 'Beskær til markering', self._need(self.crop))
        self._act(m, 'Beskær til indhold (fjern gennemsigtig kant)', self._need(self.trim))

        m = mb.addMenu('&Lag')
        self._act(m, 'Nyt lag', self._need(self.new_layer), 'Ctrl+Shift+N')
        self._act(m, 'Nyt lag (uden spørgsmål)', self._need(self.new_layer), 'Ctrl+Alt+Shift+N')
        self._act(m, 'Duplikér lag', self._need(self.duplicate_layer))
        self._act(m, 'Slet lag', self._need(self.delete_layer))
        self._act(m, 'Omdøb lag…', self._need(self.rename_layer), 'F2')
        m.addSeparator()
        self._act(m, 'Lag via kopiering', self._need(lambda: self._doc_op('Lag via kopiering', lambda d: d.layer_via(False))), 'Ctrl+J')
        self._act(m, 'Lag via klip', self._need(lambda: self._doc_op('Lag via klip', lambda d: d.layer_via(True))), 'Ctrl+Shift+J')
        m.addSeparator()
        a = m.addMenu('Arrangér')
        self._act(a, 'Placér øverst', self._need(lambda: self.arrange('top')), 'Ctrl+Shift+]')
        self._act(a, 'Flyt frem', self._need(lambda: self.arrange('up')), 'Ctrl+]')
        self._act(a, 'Flyt tilbage', self._need(lambda: self.arrange('down')), 'Ctrl+[')
        self._act(a, 'Placér nederst', self._need(lambda: self.arrange('bottom')), 'Ctrl+Shift+[')
        m.addSeparator()
        self._act(m, 'Flet ned', self._need(lambda: self._doc_op('Flet ned', lambda d: d.merge_down())), 'Ctrl+E')
        self._act(m, 'Flet synlige', self._need(lambda: self._doc_op('Flet synlige', lambda d: d.merge_visible())), 'Ctrl+Shift+E')
        self._act(m, 'Gør til ét lag', self._need(lambda: self._doc_op('Gør til ét lag', lambda d: d.flatten())))
        m.addSeparator()
        self._act(m, 'Vælg lag ovenover', self._need(lambda: self.select_layer_rel(1)), 'Alt+]')
        self._act(m, 'Vælg lag nedenunder', self._need(lambda: self.select_layer_rel(-1)), 'Alt+[')

        m = mb.addMenu('&Marker')
        self._act(m, 'Alt', self._need(lambda: self._doc_op('Marker alt', lambda d: d.select_all())), 'Ctrl+A')
        self._act(m, 'Fravælg', self._need(lambda: self._doc_op('Fravælg', lambda d: d.deselect())), 'Ctrl+D')
        self._act(m, 'Vælg igen', self._need(lambda: self._doc_op('Vælg igen', lambda d: d.reselect())), 'Ctrl+Shift+D')
        self._act(m, 'Omvendt', self._need(lambda: self._doc_op('Omvendt markering', lambda d: d.invert_selection())),
                  ['Ctrl+Shift+I', 'Shift+F7'])
        m.addSeparator()
        mm = m.addMenu('Rediger')
        self._act(mm, 'Blødgør…', self._need(lambda: self.modify_sel('Blødgør', io_.feather)), 'Shift+F6')
        self._act(mm, 'Udvid…', self._need(lambda: self.modify_sel('Udvid', io_.expand)))
        self._act(mm, 'Formindsk…', self._need(lambda: self.modify_sel('Formindsk', io_.contract)))
        self._act(m, 'Motiv', self._need(self.select_subject))
        m.addSeparator()
        self._act(m, 'Indlæs lagets pixels som markering', self._need(
            lambda: self._doc_op('Indlæs markering', lambda d: d.selection_from_layer(d.layer))))

        m = mb.addMenu('&Vis')
        self._act(m, 'Zoom ind', self._need(lambda: self.canvas().zoom_step(1)), ['Ctrl++', 'Ctrl+='])
        self._act(m, 'Zoom ud', self._need(lambda: self.canvas().zoom_step(-1)), 'Ctrl+-')
        self._act(m, 'Tilpas skærmen', self._need(lambda: self.canvas().fit()), 'Ctrl+0')
        self._act(m, '100 %', self._need(lambda: self.canvas().actual_pixels()), ['Ctrl+1', 'Ctrl+Alt+0'])

        m = mb.addMenu('&Hjælp')
        self._act(m, 'Tastaturgenveje', self.show_help, 'F1')
        m.addSeparator()
        self._act(m, 'Søg efter opdateringer…', self.check_updates)
        self._act(m, 'Om Lagkage', self.show_about)

        # værktøjsgenveje (uden menu)
        for key, name in (('V', 'move'), ('I', 'eyedropper'), ('B', 'brush'), ('E', 'eraser'),
                          ('G', 'bucket'), ('H', 'hand'), ('Z', 'zoom'), ('W', 'wand'), ('C', 'crop')):
            self._act(None, name, lambda n=name: self.set_tool(n), key)
        self._act(None, 'marquee', lambda: self.set_tool(self._last_marquee if self.tool not in ('rect', 'ellipse') else self.tool), 'M')
        self._act(None, 'marquee2', lambda: self.cycle('rect', 'ellipse', '_last_marquee'), 'Shift+M')
        self._act(None, 'lasso', lambda: self.set_tool(self._last_lasso if self.tool not in ('lasso', 'poly') else self.tool), 'L')
        self._act(None, 'lasso2', lambda: self.cycle('lasso', 'poly', '_last_lasso'), 'Shift+L')
        self._act(None, 'D', self.default_colors, 'D')
        self._act(None, 'X', self.swap_colors, 'X')
        self._act(None, '[', lambda: self.brush_size(-1), '[')
        self._act(None, ']', lambda: self.brush_size(1), ']')
        self._act(None, '{', lambda: self.brush_hardness(-25), ['Shift+[', '{'])
        self._act(None, '}', lambda: self.brush_hardness(25), ['Shift+]', '}'])

    # ================= dokumenter =================
    def add_document(self, doc, warnings=()):
        c = Canvas(doc, self)
        doc.changed.connect(self._doc_changed)
        i = self.tabs.addTab(c, doc.title())
        self.tabs.setCurrentIndex(i)
        self._update_empty()
        self.refresh_layers()
        c.setFocus()
        if warnings:
            self.flash(' '.join(warnings[:3]) + (' …' if len(warnings) > 3 else ''), 9000)
        return c

    def new_document(self):
        clip = QApplication.clipboard().image()
        w, h = (clip.width(), clip.height()) if not clip.isNull() else (1920, 1080)
        dlg = QDialog(self)
        dlg.setWindowTitle('Nyt dokument')
        f = QFormLayout(dlg)
        sw, sh = QSpinBox(), QSpinBox()
        for s, v in ((sw, w), (sh, h)):
            s.setRange(1, 30000)
            s.setValue(v)
            s.setSuffix(' px')
        bgc = QComboBox()
        bgc.addItems(['Hvid', 'Gennemsigtig', 'Baggrundsfarve', 'Sort'])
        f.addRow('Bredde:', sw)
        f.addRow('Højde:', sh)
        f.addRow('Baggrund:', bgc)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        if dlg.exec() != QDialog.Accepted:
            return
        W, H = sw.value(), sh.value()
        fill = [QColor(255, 255, 255), None, self.bg, QColor(0, 0, 0)][bgc.currentIndex()]
        name = 'Baggrund' if fill is not None else 'Lag 1'
        doc = Document(W, H, [Layer(name, new_image(W, H, fill))])
        self.add_document(doc)

    def open_dialog(self):
        start = self.settings.value('last_dir', os.path.expanduser('~/Pictures'))
        paths, _ = QFileDialog.getOpenFileNames(self, 'Åbn', start, OPEN_FILTER)
        for p in paths:
            self.open_path(p)

    def open_path(self, path):
        path = os.path.abspath(path)
        for i in range(self.tabs.count()):
            c = self.tabs.widget(i)
            if c.doc.path and os.path.normcase(c.doc.path) == os.path.normcase(path):
                self.tabs.setCurrentIndex(i)
                return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            doc, warnings = load_document(path)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, APP, f'Kunne ikke åbne {os.path.basename(path)}:\n{e}')
            return
        QApplication.restoreOverrideCursor()
        self.settings.setValue('last_dir', os.path.dirname(path))
        self._add_recent(path)
        self.add_document(doc, warnings)

    def _add_recent(self, path):
        rec = [p for p in (self.settings.value('recent') or []) if os.path.normcase(p) != os.path.normcase(path)]
        rec.insert(0, path)
        self.settings.setValue('recent', rec[:12])
        self._fill_recent()

    def _fill_recent(self):
        self.recent_menu.clear()
        rec = self.settings.value('recent') or []
        if isinstance(rec, str):
            rec = [rec]
        for p in rec:
            a = self.recent_menu.addAction(os.path.basename(p) + '   —   ' + os.path.dirname(p))
            a.triggered.connect(lambda _=False, p=p: self.open_path(p))
        if not rec:
            self.recent_menu.addAction('(ingen)').setEnabled(False)

    def place_file(self):
        start = self.settings.value('last_dir', os.path.expanduser('~/Pictures'))
        path, _ = QFileDialog.getOpenFileName(self, 'Indsæt fil som lag', start, OPEN_FILTER)
        if not path:
            return
        try:
            d2, _ = load_document(path)
            img = d2.flatten_image()
        except Exception as e:
            QMessageBox.warning(self, APP, f'Kunne ikke åbne filen:\n{e}')
            return
        self._paste_image(img, None, os.path.splitext(os.path.basename(path))[0])

    def close_tab(self, i):
        if i < 0:
            return
        c = self.tabs.widget(i)
        if c.doc.dirty:
            self.tabs.setCurrentIndex(i)
            r = QMessageBox.question(self, APP, f'Vil du gemme ændringerne i „{c.doc.title().rstrip(" *")}“?',
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if r == QMessageBox.Cancel:
                return False
            if r == QMessageBox.Save and not self.save():
                return False
        self.tabs.removeTab(i)
        c.deleteLater()
        self._update_empty()
        self.refresh_layers()
        self.update_status()
        return True

    def closeEvent(self, e):
        while self.tabs.count():
            if self.close_tab(self.tabs.count() - 1) is False:
                e.ignore()
                return
        self.settings.setValue('geometry', self.saveGeometry())
        e.accept()

    def save(self):
        doc = self.doc()
        if not doc:
            return False
        ext = os.path.splitext(doc.path or '')[1].lower()
        if not doc.path or (ext in FLAT_EXT and len(doc.layers) > 1):
            return self.save_as('.psd' if len(doc.layers) > 1 else None)
        return self._write(doc, doc.path)

    def save_as(self, prefer=None):
        doc = self.doc()
        if not doc:
            return False
        base = os.path.splitext(doc.path)[0] if doc.path else os.path.join(
            self.settings.value('last_dir', os.path.expanduser('~/Pictures')), 'Uden titel')
        ext = prefer or (os.path.splitext(doc.path)[1].lower() if doc.path else '.psd')
        if ext == '.jpeg':
            ext = '.jpg'
        filt = next((k for k, v in SAVE_FILTERS.items() if v == ext), 'Photoshop (*.psd)')
        path, chosen = QFileDialog.getSaveFileName(self, 'Gem som', base + ext, ';;'.join(SAVE_FILTERS), filt)
        if not path:
            return False
        if not os.path.splitext(path)[1]:
            path += SAVE_FILTERS.get(chosen, '.psd')
        ok = self._write(doc, path)
        if ok:
            self._add_recent(path)
        return ok

    def _write(self, doc, path):
        ext = os.path.splitext(path)[1].lower()
        c = self.canvas()
        if c and c.transforming:
            c.end_transform(True)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if ext in ('.psd', '.psb'):
                save_psd(doc, path)
            else:
                save_flat(doc, path)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, APP, f'Kunne ikke gemme:\n{e}')
            return False
        QApplication.restoreOverrideCursor()
        if ext in ('.psd', '.psb') or len(doc.layers) == 1:
            doc.path = path
            doc.dirty = False
        else:
            self.flash(f'Eksporteret som {os.path.basename(path)} (lagene er bevaret i dokumentet).')
        self.settings.setValue('last_dir', os.path.dirname(path))
        self._update_tab_title()
        self.flash(f'Gemt: {path}')
        return True

    # ================= drag og drop =================
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        if md.hasUrls():
            paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
            if self.doc() and e.modifiers() & Qt.ShiftModifier:
                for p in paths:
                    try:
                        d2, _ = load_document(p)
                        self._paste_image(d2.flatten_image(), None, os.path.splitext(os.path.basename(p))[0])
                    except Exception as ex:
                        self.flash(f'Kunne ikke indsætte {os.path.basename(p)}: {ex}')
            else:
                for p in paths:
                    self.open_path(p)
        elif md.hasImage():
            img = QImage(md.imageData())
            self._paste_image(img, None)

    # ================= rediger =================
    def _doc_op(self, label, fn, keep_float=False):
        d = self.doc()
        d.begin(label, keep_float=keep_float)
        fn(d)
        d.touch()

    def _undo(self):
        c = self.canvas()
        if not c:
            return
        if c.transforming:
            c.end_transform(False)
            return
        c.poly = None
        c.doc.undo()
        self.refresh_layers()

    def _redo(self):
        c = self.canvas()
        if c and not c.transforming:
            c.doc.redo()
            self.refresh_layers()

    def _clipboard_set(self, img, origin):
        self.clip_origin = (origin, img.cacheKey())
        QApplication.clipboard().setImage(img)
        self.clip_key = QApplication.clipboard().image().cacheKey()

    def copy(self):
        d = self.doc()
        if d.floating is not None:
            f = d.floating
            r = f.doc_rect().toAlignedRect()
            img = new_image(r.width(), r.height())
            from PySide6.QtGui import QPainter
            p = QPainter(img)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.setTransform(f.transform * QTransform.fromTranslate(-r.x(), -r.y()))
            p.drawImage(0, 0, f.image)
            p.end()
            self._clipboard_set(img, r.topLeft())
            return
        img, pos = d.copy_selection_pixels()
        if img is None:
            self.flash('Der er ingen pixels at kopiere i markeringen.')
            return
        self._clipboard_set(img, pos)

    def copy_merged(self):
        d = self.doc()
        bb = d.selection_bbox() if d.selection is not None else d.rect()
        if bb is None:
            return
        img = d.flatten_image(rect=bb)
        if d.selection is not None:
            from PySide6.QtGui import QPainter
            p = QPainter(img)
            p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            p.drawImage(QPoint(0, 0), d.selection, bb)
            p.end()
        self._clipboard_set(img, bb.topLeft())

    def cut(self):
        d = self.doc()
        if d.floating is not None:
            self.copy()
            d.begin('Klip', keep_float=True)
            d.floating = None
            d.touch()
            return
        self.copy()
        d.begin('Klip')
        d.clear_selection_pixels()

    def paste(self, in_place=False):
        img = QApplication.clipboard().image()
        if img.isNull():
            md = QApplication.clipboard().mimeData()
            if md and md.hasUrls():
                for u in md.urls():
                    if u.isLocalFile():
                        self.open_path(u.toLocalFile())
                return
            self.flash('Udklipsholderen indeholder ikke et billede.')
            return
        if not self.doc():
            doc = Document(img.width(), img.height(), [Layer('Lag 1', img.convertToFormat(FMT))])
            self.add_document(doc)
            return
        origin = None
        if in_place and self.clip_origin is not None and getattr(self, 'clip_key', None) == img.cacheKey():
            origin = self.clip_origin[0]
        elif in_place and self.clip_origin is not None:
            origin = self.clip_origin[0]
        self._paste_image(img, origin)

    def _paste_image(self, img, origin, name=None):
        c = self.canvas()
        if not c:
            doc = Document(img.width(), img.height(), [Layer(name or 'Lag 1', img.convertToFormat(FMT))])
            self.add_document(doc)
            return
        d = c.doc
        if origin is None:
            ctr = c.view_center_doc()
            # hold indsat billede inden for lærredet, hvis visningen er udenfor
            cx = min(max(ctr.x(), 0), d.width)
            cy = min(max(ctr.y(), 0), d.height)
            origin = QPoint(round(cx - img.width() / 2), round(cy - img.height() / 2))
        d.begin('Sæt ind')
        d.paste_image(img, origin)
        if name:
            d.layer.name = name
        d.set_selection(None)
        self.refresh_layers()
        self.set_tool('move') if self.tool not in ('move',) else None

    def _clear_or_poly(self):
        c = self.canvas()
        if not c:
            return
        if c.poly:
            c.poly.pop()
            if not c.poly:
                c.poly = None
            c.update()
            return
        d = c.doc
        if c.transforming:
            c.end_transform(True)
        if d.floating is not None:
            d.begin('Ryd', keep_float=True)
            f = d.floating
            d.floating = None
            if not f.whole_layer:
                from PySide6.QtGui import QPainter
                m = io_.new_mask(d.width, d.height)
                p = QPainter(m)
                p.setTransform(f.transform)
                p.drawImage(0, 0, f.mask)
                p.end()
                d._set_sel(m)
            d.touch()
        else:
            d.begin('Ryd')
            d.clear_selection_pixels()
        self.refresh_layers()

    def quick_fill(self, color, preserve=False):
        d = self.doc()
        d.begin('Udfyld')
        d.fill(color, 1.0, preserve)

    def fill_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle('Udfyld')
        f = QFormLayout(dlg)
        what = QComboBox()
        what.addItems(['Forgrundsfarve', 'Baggrundsfarve', 'Farve…', 'Sort', '50 % grå', 'Hvid',
                       'Indholdsbevidst'])
        what.setCurrentIndex(int(self.settings.value('fill_choice', 6)))
        op = QSpinBox()
        op.setRange(1, 100)
        op.setValue(100)
        op.setSuffix(' %')
        mode = QComboBox()
        from .document import BLEND_MODES
        pres = QCheckBox('Bevar gennemsigtighed')
        f.addRow('Indhold:', what)
        f.addRow('Opacitet:', op)
        f.addRow('', pres)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        if dlg.exec() != QDialog.Accepted:
            return
        i = what.currentIndex()
        self.settings.setValue('fill_choice', i)
        if i == 6:
            self.content_aware()
            return
        if i == 2:
            col = QColorDialog.getColor(self.fg, self, 'Vælg farve')
            if not col.isValid():
                return
        else:
            col = [self.fg, self.bg, None, QColor(0, 0, 0), QColor(128, 128, 128), QColor(255, 255, 255)][i]
        d = self.doc()
        d.begin('Udfyld')
        d.fill(col, op.value() / 100.0, pres.isChecked())

    def content_aware(self):
        from . import inpaint
        from PySide6.QtWidgets import QProgressDialog
        d = self.doc()
        d.commit_float()
        if d.selection is None:
            self.flash('Markér det, der skal fjernes, og prøv igen.')
            return
        if not self._ensure_model(inpaint, 'Indholdsbevidst udfyld bruger en open source-model (LaMa, ca. 200 MB)'):
            return
        self.flash('Udfylder …', 60000)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            d.begin('Indholdsbevidst udfyld')
            ok = d.content_aware_fill(lambda *_: QApplication.processEvents())
            if not ok:
                d.cancel_begin()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            d.cancel_begin()
            QMessageBox.warning(self, APP, 'Indholdsbevidst udfyld fejlede: ' + str(e))
            return
        QApplication.restoreOverrideCursor()
        self.flash('Udfyldt. Ctrl+D fravælger, Ctrl+Z fortryder.')
        self.refresh_layers()

    def _ensure_model(self, module, what):
        """Spørg og hent en lokal model første gang, den bruges."""
        from PySide6.QtWidgets import QProgressDialog
        if module.model_ready():
            return True
        r = QMessageBox.question(self, APP, what + ', der kører på din egen computer. Skal den hentes nu?')
        if r != QMessageBox.Yes:
            return False
        dlg = QProgressDialog('Henter model…', 'Annullér', 0, 100, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.show()

        def prog(done, total):
            dlg.setValue(int(done * 100 / total) if total else 0)
            QApplication.processEvents()
            return not dlg.wasCanceled()
        try:
            ok = module.download_model(prog)
        except Exception as e:
            dlg.close()
            QMessageBox.warning(self, APP, 'Modellen kunne ikke hentes: ' + str(e))
            return False
        dlg.close()
        return bool(ok)

    def select_subject(self):
        from . import subject
        d = self.doc()
        c = self.canvas()
        if c.transforming:
            c.end_transform(True)
        if not self._ensure_model(subject, 'Marker motiv bruger en open source-model (ISNet, ca. 180 MB)'):
            return
        mods = QApplication.keyboardModifiers()
        mode = 'add' if mods & Qt.ShiftModifier else 'sub' if mods & Qt.AltModifier else 'new'
        self.flash('Finder motivet …', 60000)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            d.begin('Marker motiv')
            rgb = io_.argb_np(d.flatten_image(QColor(255, 255, 255)))[:, :, [2, 1, 0]]
            import numpy as np
            m = subject.subject_mask(np.ascontiguousarray(rgb))
            d.apply_selection(m, mode)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            d.cancel_begin()
            QMessageBox.warning(self, APP, 'Marker motiv fejlede: ' + str(e))
            return
        QApplication.restoreOverrideCursor()
        self.flash('Motivet er markeret. Shift/Alt med et markeringsværktøj retter til.' if d.selection is not None
                   else 'Der blev ikke fundet et tydeligt motiv.')
        self.refresh_layers()

    def layer_transform(self, m):
        c = self.canvas()
        d = c.doc
        d.begin('Transformér', keep_float=True)
        if not d.ensure_float():
            d.cancel_begin()
            return
        d.transform_float(m)
        if d.floating.whole_layer and not c.transforming:
            d.commit_float()

    # ================= billede =================
    def rotate_canvas(self, k):
        self._doc_op('Billedrotation', lambda d: d.rotate_canvas(k))
        self.canvas().fit(max_zoom=self.canvas().zoom)

    def image_size_dialog(self):
        d = self.doc()
        dlg = QDialog(self)
        dlg.setWindowTitle('Billedstørrelse')
        f = QFormLayout(dlg)
        sw, sh = QSpinBox(), QSpinBox()
        for s, v in ((sw, d.width), (sh, d.height)):
            s.setRange(1, 30000)
            s.setValue(v)
            s.setSuffix(' px')
        pct = QSpinBox()
        pct.setRange(1, 1000)
        pct.setValue(100)
        pct.setSuffix(' %')
        keep = QCheckBox('Bevar proportioner')
        keep.setChecked(True)
        lock = [False]

        def from_w(v):
            if lock[0] or not keep.isChecked():
                return
            lock[0] = True
            sh.setValue(max(1, round(v * d.height / d.width)))
            pct.setValue(round(v * 100 / d.width))
            lock[0] = False

        def from_h(v):
            if lock[0] or not keep.isChecked():
                return
            lock[0] = True
            sw.setValue(max(1, round(v * d.width / d.height)))
            pct.setValue(round(v * 100 / d.height))
            lock[0] = False

        def from_p(v):
            if lock[0]:
                return
            lock[0] = True
            sw.setValue(max(1, round(d.width * v / 100)))
            sh.setValue(max(1, round(d.height * v / 100)))
            lock[0] = False
        sw.valueChanged.connect(from_w)
        sh.valueChanged.connect(from_h)
        pct.valueChanged.connect(from_p)
        f.addRow('Procent:', pct)
        f.addRow('Bredde:', sw)
        f.addRow('Højde:', sh)
        f.addRow('', keep)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        if dlg.exec() == QDialog.Accepted and (sw.value(), sh.value()) != (d.width, d.height):
            self._doc_op('Billedstørrelse', lambda d: d.resize_image(sw.value(), sh.value()))
            self.canvas().fit(max_zoom=1.0)

    def canvas_size_dialog(self):
        d = self.doc()
        dlg = QDialog(self)
        dlg.setWindowTitle('Lærredsstørrelse')
        f = QFormLayout(dlg)
        sw, sh = QSpinBox(), QSpinBox()
        for s, v in ((sw, d.width), (sh, d.height)):
            s.setRange(1, 30000)
            s.setValue(v)
            s.setSuffix(' px')
        anchor = QComboBox()
        anchors = [('Midten', .5, .5), ('Øverst til venstre', 0, 0), ('Øverst', .5, 0), ('Øverst til højre', 1, 0),
                   ('Venstre', 0, .5), ('Højre', 1, .5), ('Nederst til venstre', 0, 1), ('Nederst', .5, 1),
                   ('Nederst til højre', 1, 1)]
        anchor.addItems([a[0] for a in anchors])
        f.addRow('Bredde:', sw)
        f.addRow('Højde:', sh)
        f.addRow('Anker:', anchor)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        if dlg.exec() == QDialog.Accepted:
            _, ax, ay = anchors[anchor.currentIndex()]
            self._doc_op('Lærredsstørrelse', lambda d: d.resize_canvas(sw.value(), sh.value(), ax, ay))
            self.canvas().fit(max_zoom=1.0)

    def crop(self):
        d = self.doc()
        d.commit_float()
        bb = d.selection_bbox()
        if bb is None:
            self.flash('Lav en markering først.')
            return
        bb = bb.intersected(d.rect())
        self._doc_op('Beskær', lambda d: (d.crop(bb), d.set_selection(None)))
        self.canvas().fit(max_zoom=1.0)

    def trim(self):
        d = self.doc()
        d.commit_float()
        a = io_.alpha_of(d.flatten_image())
        bb = io_.bbox_of(a)
        if bb is None or bb == d.rect():
            return
        self._doc_op('Beskær til indhold', lambda d: d.crop(bb))
        self.canvas().fit(max_zoom=1.0)

    # ================= lag =================
    def set_active_layer(self, i):
        d = self.doc()
        if i == d.active:
            return
        c = self.canvas()
        if c.transforming:
            c.end_transform(True)
        d.commit_float()
        d.active = i
        d.touch()
        self.refresh_layers()

    def select_layer_rel(self, step):
        d = self.doc()
        self.set_active_layer(max(0, min(len(d.layers) - 1, d.active + step)))

    def new_layer(self):
        if not self.doc():
            return
        self._doc_op('Nyt lag', lambda d: d.add_layer())
        self.refresh_layers()

    def duplicate_layer(self):
        if not self.doc():
            return
        self._doc_op('Duplikér lag', lambda d: d.duplicate_layer())
        self.refresh_layers()

    def delete_layer(self):
        if not self.doc():
            return
        self._doc_op('Slet lag', lambda d: d.delete_layer())
        self.refresh_layers()

    def merge_down(self):
        if self.doc():
            self._doc_op('Flet ned', lambda d: d.merge_down())
            self.refresh_layers()

    def merge_visible(self):
        if self.doc():
            self._doc_op('Flet synlige', lambda d: d.merge_visible())
            self.refresh_layers()

    def flatten(self):
        if self.doc():
            self._doc_op('Gør til ét lag', lambda d: d.flatten())
            self.refresh_layers()

    def rename_layer(self):
        d = self.doc()
        self.layers_panel.list.start_rename(d.active)

    def arrange(self, how):
        d = self.doc()
        i = d.active
        dst = {'top': len(d.layers) - 1, 'up': i + 1, 'down': i - 1, 'bottom': 0}[how]
        self._doc_op('Arrangér', lambda d: d.move_layer(i, dst))

    def modify_sel(self, label, fn):
        d = self.doc()
        d.commit_float()
        if d.selection is None:
            self.flash('Der er ingen markering.')
            return
        v, ok = QInputDialog.getInt(self, label, f'{label} med (pixels):', 5, 1, 500)
        if ok:
            self._doc_op(label, lambda d: d.modify_selection(lambda a: fn(a, v)))

    def show_help(self):
        QMessageBox.information(self, 'Tastaturgenveje', HELP)


HELP = """Værktøjer
V flyt · M markering (Shift+M skifter rektangel/ellipse) · L lasso (Shift+L polygon)
W tryllestav · C beskær · I pipette · B pensel · E viskelæder · G spand · H hånd · Z zoom
Mellemrum = hånd · Ctrl+mellemrum = zoom ind · Ctrl+Alt+mellemrum = zoom ud · Ctrl = flyt midlertidigt
Højreklik på billedet vælger et af lagene under musen
[ ] penselstørrelse · Shift+[ ] hårdhed

Markering
Shift = tilføj · Alt = træk fra · Shift+Alt = fællesmængde
Ctrl+A alt · Ctrl+D fravælg · Ctrl+Shift+D vælg igen · Ctrl+Shift+I omvendt · Shift+F6 blødgør
Træk inde i en markering med et markeringsværktøj for at flytte omridset
Ctrl-klik på et lags miniature indlæser lagets pixels som markering
Marker > Motiv (eller knappen Marker motiv) markerer personen/tingen i billedet

Flyt og transformér
Flyt med markering flytter pixels; uden markering flyttes hele laget
Alt-træk kopierer · Shift låser retningen · piletaster skubber (Shift: 10 px)
Ctrl+T frit transformér · Enter udfør · Esc annullér

Udfyld
Alt+Backspace forgrund · Ctrl+Backspace baggrund · Shift+F5 / Shift+Backspace udfyld (også indholdsbevidst)
Shift+Alt+Backspace bevarer gennemsigtighed · Delete/Backspace rydder
D standardfarver · X byt farver

Lag
Ctrl+Shift+N nyt lag · Ctrl+J lag via kopiering · Ctrl+Shift+J lag via klip
Ctrl+E flet ned · Ctrl+Shift+E flet synlige · Ctrl+[ / Ctrl+] flyt lag ned/op
Alt+[ / Alt+] vælg lag nedenunder/ovenover · Alt-klik på øjet viser kun det lag

Udklipsholder
Ctrl+C / Ctrl+X / Ctrl+V · Ctrl+Shift+C kopiér flettet · Ctrl+Shift+V sæt ind på stedet
Shift-træk en fil ind for at lægge den som nyt lag

Vis
Ctrl++ / Ctrl+- zoom · Ctrl+0 tilpas · Ctrl+1 100 % · Ctrl/Alt + hjul zoomer"""

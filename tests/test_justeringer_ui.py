import os, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tempfile
OUT = os.path.join(tempfile.gettempdir(), 'lagkage-test')
os.makedirs(OUT, exist_ok=True)
SHOTS = '--shots' in sys.argv
if not SHOTS:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtCore import Qt, QPoint, QPointF, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
import lagkage.main as M
app = QApplication([])
app.setStyle('Fusion'); app.setStyleSheet(M.STYLE)
from lagkage.window import MainWindow
from lagkage import panels


def check(name, cond):
    print(('OK   ' if cond else 'FAIL ') + name)


def run_dialog_then(fn, delay=300):
    """Næste modale dialog: kør fn(dialog) og tryk OK."""
    def go():
        d = QApplication.activeModalWidget()
        if d is None:
            QTimer.singleShot(100, go)
            return
        fn(d)
        if SHOTS:
            d.grab().save(OUT + r'\dlg_' + d.windowTitle().replace('/', '_') + '.png')
        d.accept()
    QTimer.singleShot(delay, go)


def main():
    try:
        w = MainWindow(); w.resize(1400, 860); w.show(); app.processEvents()
        w.open_path(r'C:\Windows\Web\Wallpaper\Lenovo\LenovoWallPaper.jpg'); app.processEvents()
        c = w.canvas(); c.fit(); app.processEvents()
        d = c.doc
        sp = lambda x, y: QPoint(round(c.to_screen(QPointF(x, y)).x()), round(c.to_screen(QPointF(x, y)).y()))
        before = d.flatten_image().pixelColor(300, 300)

        # 1 kurver via Ctrl+M med en S-kurve
        from lagkage.adjust_dialogs import CurveWidget
        def set_curve(dlg):
            cw = dlg.findChild(CurveWidget)
            cw.points = [[0, 0], [64, 30], [190, 230], [255, 255]]
            cw.changed.emit()
        run_dialog_then(set_curve)
        QTest.keyClick(c, Qt.Key_M, Qt.ControlModifier); app.processEvents()
        w.activateWindow(); c.setFocus(); app.processEvents()
        after = d.flatten_image().pixelColor(300, 300)
        check(f'kurve-justeringslag: {before.getRgb()[:3]} -> {after.getRgb()[:3]}',
              d.layer.is_adjust and d.layer.adjust['type'] == 'curves' and after != before)

        # 2 maske på justeringslaget: mal sort på venstre del -> originalen kommer frem dér
        w.set_tool('brush'); w.opt['size'] = 300; w.opt['hardness'] = 100; w.default_colors()
        QTest.mousePress(c, Qt.LeftButton, Qt.NoModifier, sp(300, 300))
        QTest.mouseMove(c, sp(320, 320))
        QTest.mouseRelease(c, Qt.LeftButton, Qt.NoModifier, sp(320, 320)); app.processEvents()
        masked = d.flatten_image().pixelColor(300, 300)
        check(f'sort på masken viser originalen: {masked.getRgb()[:3]} == {before.getRgb()[:3]}',
              masked.getRgb() == before.getRgb())
        other = d.flatten_image().pixelColor(1500, 700)

        # 3 Ctrl+I inverterer masken
        w.activateWindow(); c.setFocus(); app.processEvents()
        QTest.keyClick(c, Qt.Key_I, Qt.ControlModifier); app.processEvents()
        inv = d.flatten_image().pixelColor(300, 300)
        check('Ctrl+I inverterer masken', inv.getRgb() == after.getRgb())
        QTest.keyClick(c, Qt.Key_Z, Qt.ControlModifier); app.processEvents()

        # 4 farvetone/mætning
        def set_hue(dlg):
            dlg.p['hue'] = 120
            dlg.doc.touch()
        run_dialog_then(set_hue)
        QTest.keyClick(c, Qt.Key_U, Qt.ControlModifier); app.processEvents()
        w.activateWindow(); c.setFocus(); app.processEvents()
        check(f'farvetone-lag: {len(d.layers)} lag', len(d.layers) == 3 and d.layer.adjust['params']['hue'] == 120)

        # 5 annullér et nyt justeringslag fjerner det igen
        def cancel(dlg):
            dlg.reject = dlg.reject
        def go_cancel():
            dlg = QApplication.activeModalWidget()
            if dlg is None:
                QTimer.singleShot(100, go_cancel)
                return
            dlg.reject()
        QTimer.singleShot(300, go_cancel)
        QTest.keyClick(c, Qt.Key_L, Qt.ControlModifier); app.processEvents()
        w.activateWindow(); c.setFocus(); app.processEvents()
        check('annulleret niveauer-lag fjernes', len(d.layers) == 3)

        # 6 pixellag med maske fra markering + skift mål via miniature
        w.set_active_layer(0)
        w.set_tool('rect')
        QTest.mousePress(c, Qt.LeftButton, Qt.NoModifier, sp(1000, 200))
        QTest.mouseMove(c, sp(1500, 900))
        QTest.mouseRelease(c, Qt.LeftButton, Qt.NoModifier, sp(1500, 900)); app.processEvents()
        w.duplicate_layer() if False else None
        QTest.keyClick(c, Qt.Key_J, Qt.ControlModifier); app.processEvents()   # markering -> nyt lag
        w.add_mask('reveal_all'); app.processEvents()
        L = d.layer
        check('maske tilføjet, mål = maske', L.mask is not None and d.editing_mask())
        lst = w.layers_panel.list
        n = len(d.layers); row = n - 1 - d.active
        t1, t2, nx = lst._cols(L)
        QTest.mouseClick(lst, Qt.LeftButton, Qt.NoModifier, QPoint(t1 + 10, row * panels.ROW_H + 20)); app.processEvents()
        check('klik på billedminiature: mål = pixels', not d.editing_mask())
        QTest.mouseClick(lst, Qt.LeftButton, Qt.NoModifier, QPoint(t2 + 10, row * panels.ROW_H + 20)); app.processEvents()
        check('klik på maskeminiature: mål = maske', d.editing_mask())

        # 7 gem som .lagkage og åbn igen
        path = OUT + r'\ui.lagkage'
        ok = w._write(d, path)
        ref = d.flatten_image()
        d.dirty = False
        w.open_path(path) if False else None
        from lagkage.document import load_lagkage
        from lagkage.imageops import argb_np
        import numpy as np
        d2, _ = load_lagkage(path)
        same = np.array_equal(argb_np(ref), argb_np(d2.flatten_image()))
        check(f'.lagkage gemt og genåbnet identisk ({len(d2.layers)} lag)', ok and same)

        if SHOTS:
            w.set_active_layer(1); d.mask_target = True; d.touch(); w.refresh_layers(); app.processEvents()
            w.grab().save(OUT + r'\ui_adjust.png')
            # åbn kurvedialogen igen til skærmbillede
            w.set_active_layer(1)
            run_dialog_then(lambda dlg: None, 400)
            w.edit_adjustment()
        for i in range(w.tabs.count()):
            w.tabs.widget(i).doc.dirty = False
        print('done')
    except Exception:
        traceback.print_exc()
    app.quit()


QTimer.singleShot(500, main)
app.exec()

import os, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
OUT = os.path.join(tempfile.gettempdir(), 'lagkage-test')
os.makedirs(OUT, exist_ok=True)
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPainterPath
from PySide6.QtCore import QPoint, QRectF
app = QApplication([])
from lagkage.document import Document, Layer, save_psd, load_psd, save_lagkage, load_lagkage
from lagkage.imageops import new_image, path_mask, mask_np
from lagkage import adjust


def check(name, cond):
    print(('OK   ' if cond else 'FAIL ') + name)


def px(doc, x, y):
    c = doc.flatten_image().pixelColor(x, y)
    return (c.red(), c.green(), c.blue(), c.alpha())


try:
    doc = Document(200, 100, [Layer('Baggrund', new_image(200, 100, QColor(100, 150, 200)))])
    # 1 invertér-justeringslag over hele billedet
    doc.begin('adj'); doc.add_adjustment(adjust.new('invert'))
    check(f'invert: {px(doc, 10, 10)}', px(doc, 10, 10)[:3] == (155, 105, 55))
    # 2 maske: skjul venstre halvdel (mal sort på masken)
    L = doc.layer
    doc.begin('m'); doc.selection = None
    p = QPainterPath(); p.addRect(QRectF(0, 0, 100, 100))
    doc._set_sel(path_mask(200, 100, p))
    doc.fill(QColor(0, 0, 0))             # mask_target -> fylder masken med sort
    doc._set_sel(None)
    check(f'maske skjuler venstre: {px(doc, 10, 10)} / højre {px(doc, 150, 10)}',
          px(doc, 10, 10)[:3] == (100, 150, 200) and px(doc, 150, 10)[:3] == (155, 105, 55))
    # 3 fortryd masken
    doc.undo()
    check('fortryd maskefyld', px(doc, 10, 10)[:3] == (155, 105, 55))
    doc.redo()
    # 4 niveauer og kurver, hue/sat, bw, brightness kører
    for k in ('levels', 'curves', 'brightness', 'hue_sat', 'bw'):
        a = adjust.new(k)
        if k == 'levels': a['params'].update(in_black=50, in_white=200, gamma=1.5)
        if k == 'curves': a['params']['points'] = [[0, 0], [100, 160], [255, 255]]
        if k == 'brightness': a['params'].update(brightness=40, contrast=30)
        if k == 'hue_sat': a['params'].update(hue=90, saturation=30, lightness=-10)
        out = adjust.apply_image(new_image(4, 4, QColor(100, 150, 200)), a).pixelColor(1, 1)
        check(f'{k}: {(out.red(), out.green(), out.blue())}', out.alpha() == 255)
    # 5 pixellag med maske + flyt følger med
    d2 = Document(200, 100, [Layer('Baggrund', new_image(200, 100, QColor(255, 255, 255)))])
    d2.add_layer('Rød', new_image(50, 50, QColor(255, 0, 0)), QPoint(10, 10))
    d2._set_sel(path_mask(200, 100, (lambda q: (q.addRect(QRectF(10, 10, 25, 50)), q)[1])(QPainterPath())))
    d2.add_mask('reveal_sel')
    check(f'vis markering: venstre rød {px(d2, 15, 20)}, højre hvid {px(d2, 50, 20)}',
          px(d2, 15, 20)[:3] == (255, 0, 0) and px(d2, 50, 20)[:3] == (255, 255, 255))
    d2.layer.pos = QPoint(110, 10)
    check(f'maske følger laget: {px(d2, 115, 20)} {px(d2, 150, 20)}',
          px(d2, 115, 20)[:3] == (255, 0, 0) and px(d2, 150, 20)[:3] == (255, 255, 255))
    # 6 .lagkage roundtrip
    save_lagkage(doc, OUT + r'\t.lagkage')
    d3, _ = load_lagkage(OUT + r'\t.lagkage')
    a1, a2 = doc.flatten_image(), d3.flatten_image()
    from lagkage.imageops import argb_np
    check(f'.lagkage identisk, lag: {[(L.kind, L.mask is not None) for L in d3.layers]}',
          np.array_equal(argb_np(a1), argb_np(a2)) and d3.layers[1].is_adjust)
    # 7 PSD med pixelmaske + bagt justering
    save_psd(d2, OUT + r'\m.psd')
    d4, w = load_psd(OUT + r'\m.psd')
    diff = np.abs(argb_np(d2.flatten_image()).astype(int) - argb_np(d4.flatten_image()).astype(int)).max()
    check(f'PSD med maske: maske bevaret={d4.layers[1].mask is not None}, maxdiff {diff} {w}', diff <= 2)
    save_psd(doc, OUT + r'\a.psd')
    d5, w = load_psd(OUT + r'\a.psd')
    diff = np.abs(argb_np(doc.flatten_image()).astype(int) - argb_np(d5.flatten_image()).astype(int)).max()
    check(f'PSD med bagt justering: maxdiff {diff}', diff <= 2)
    # 8 flet justering ned
    doc.begin('flet'); ok = doc.merge_down()
    check(f'flet justering ned: {ok}, {len(doc.layers)} lag, {px(doc, 150, 10)} {px(doc, 10, 10)}',
          len(doc.layers) == 1 and px(doc, 150, 10)[:3] == (155, 105, 55) and px(doc, 10, 10)[:3] == (100, 150, 200))
    print('done')
except Exception:
    traceback.print_exc()

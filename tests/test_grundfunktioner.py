import os, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
OUT = os.path.join(tempfile.gettempdir(), 'lagkage-test')
os.makedirs(OUT, exist_ok=True)
from PIL import Image, ImageDraw
im = Image.new('RGB', (800, 600), (70, 130, 200))
d = ImageDraw.Draw(im); d.rectangle((100, 100, 300, 300), fill=(240, 200, 40)); d.ellipse((450, 200, 700, 450), fill=(200, 40, 60))
im.save(OUT + r'\photo.jpg')
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from lagkage.main import STYLE
app = QApplication([])
app.setStyle('Fusion'); app.setStyleSheet(STYLE)
from lagkage.window import MainWindow
w = MainWindow(); w.resize(1300, 850); w.show(); app.processEvents()
w.open_path(OUT + r'\photo.jpg'); app.processEvents()
c = w.canvas(); c.fit(max_zoom=1.0); app.processEvents()
doc = c.doc
def sp(x, y):  # doc -> screen QPoint
    p = c.to_screen(QPointF(x, y)); return QPoint(round(p.x()), round(p.y()))
def drag(a, b, mods=Qt.NoModifier):
    QTest.mousePress(c, Qt.LeftButton, mods, sp(*a)); 
    for t in (0.3, 0.6, 1.0):
        x = a[0] + (b[0]-a[0])*t; y = a[1] + (b[1]-a[1])*t
        QTest.mouseMove(c, sp(x, y))
    QTest.mouseRelease(c, Qt.LeftButton, mods, sp(*b)); app.processEvents()
def check(name, cond):
    print(('OK   ' if cond else 'FAIL ') + name)
try:
    # 1 rect marquee around yellow square
    w.set_tool('rect'); drag((100, 100), (301, 301))
    check('rect selection', doc.selection is not None and doc.selection_bbox().width() == 201)
    # 2 move pixels
    w.set_tool('move'); drag((200, 200), (250, 220))
    check('floating created', doc.floating is not None)
    img = doc.flatten_image()
    check('moved pixel yellow at 340,310', img.pixelColor(340, 310).red() > 200 and img.pixelColor(340,310).green() > 150)
    check('hole transparent at 110,110', img.pixelColor(110, 110).alpha() == 0)
    # move again -> hole remains, original area not destroyed further
    drag((300, 300), (300, 400))
    img = doc.flatten_image()
    check('second move keeps float', doc.floating is not None and img.pixelColor(340, 410).red() > 200)
    # 3 deselect commits
    QTest.keyClick(c, Qt.Key_D, Qt.ControlModifier); app.processEvents()
    check('deselect commits float', doc.floating is None and doc.selection is None)
    # 4 undo x3 restores original
    for _ in range(3): QTest.keyClick(c, Qt.Key_Z, Qt.ControlModifier)
    img = doc.flatten_image()
    check('undo restores', img.pixelColor(110, 110).alpha() == 255 and img.pixelColor(200,200).green() > 150)
    # 5 wand on red ellipse, copy, paste -> new layer
    w.set_tool('wand'); QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, sp(575, 325)); app.processEvents()
    bb = doc.selection_bbox(); check(f'wand bbox {bb}', bb is not None and 240 <= bb.width() <= 255)
    QTest.keyClick(c, Qt.Key_C, Qt.ControlModifier); QTest.keyClick(c, Qt.Key_V, Qt.ControlModifier); app.processEvents()
    check('paste new layer', len(doc.layers) == 2 and doc.layer.image.width() == bb.width())
    # 6 Ctrl+J on background with selection
    w.set_active_layer(0); w.set_tool('rect'); drag((100,100),(200,200))
    QTest.keyClick(c, Qt.Key_J, Qt.ControlModifier); app.processEvents()
    check('ctrl+J', len(doc.layers) == 3 and doc.active == 1)
    # 7 fill with fg (alt+backspace) on new layer, select area first
    w.set_tool('ellipse'); drag((400, 50), (500, 150))
    w.set_fg(QColor(0, 255, 0)); QTest.keyClick(c, Qt.Key_Backspace, Qt.AltModifier); app.processEvents()
    img = doc.flatten_image(); check('fill fg', img.pixelColor(450, 100).green() == 255 and img.pixelColor(450,100).red() == 0)
    # 8 ctrl+T scale whole layer (no selection)
    QTest.keyClick(c, Qt.Key_D, Qt.ControlModifier)
    QTest.keyClick(c, Qt.Key_T, Qt.ControlModifier); app.processEvents()
    check('transform mode', c.transforming and doc.floating is not None)
    f = doc.floating; r = f.doc_rect(); 
    drag((r.right(), r.bottom()), (r.right()+100, r.bottom()+100))
    QTest.keyClick(c, Qt.Key_Return); app.processEvents()
    check(f'transform committed, layer bbox', not c.transforming and doc.floating is None)
    # 9 merge down & brush
    QTest.keyClick(c, Qt.Key_E, Qt.ControlModifier); app.processEvents()
    check('merge down', len(doc.layers) == 2)
    w.set_tool('brush'); w.set_fg(QColor(255,0,255)); drag((50, 500), (300, 500))
    img = doc.flatten_image(); check('brush', img.pixelColor(150, 500).blue() == 255 and img.pixelColor(150,500).green() == 0)
    # 10 lasso polygon
    w.set_tool('poly')
    for pt in ((600,50),(750,50),(750,150)):
        QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, sp(*pt))
    QTest.keyClick(c, Qt.Key_Return); app.processEvents()
    check('poly lasso', doc.selection is not None)
    QTest.keyClick(c, Qt.Key_Delete); app.processEvents()
    # 11 save psd + reopen
    from lagkage.document import save_psd, load_psd
    doc.layers[-1].opacity = 0.5; doc.layers[-1].blend = 'multiply'
    save_psd(doc, OUT + r'\test.psd')
    d2, warn = load_psd(OUT + r'\test.psd')
    check(f'psd roundtrip {len(d2.layers)} layers {[(L.name, round(L.opacity,2), L.blend) for L in d2.layers]} {warn}', len(d2.layers) == 2 and d2.layers[-1].blend == 'multiply')
    a = doc.flatten_image(); b = d2.flatten_image()
    import numpy as np
    from lagkage.imageops import argb_np
    diff = np.abs(argb_np(a).astype(int) - argb_np(b).astype(int)).max()
    check(f'psd pixels match (maxdiff {diff})', diff <= 2)
    # 12 rotate canvas, image size
    doc.begin('x'); doc.rotate_canvas('cw'); check('rotate', (doc.width, doc.height) == (600, 800))
    doc.undo()
    w.set_tool('rect'); drag((100,100),(300,300))
    w.grab().save(OUT + r'\shot.png')
    print('done')
except Exception:
    traceback.print_exc()

import os, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
OUT = os.path.join(tempfile.gettempdir(), 'lagkage-test')
os.makedirs(OUT, exist_ok=True)
import numpy as np
from PySide6.QtCore import Qt, QPoint, QPointF, QRect
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPainter
app = QApplication([])
from lagkage.window import MainWindow
from lagkage.document import Document, Layer
from lagkage.imageops import new_image, argb_np, mask_np

w = MainWindow(); w.resize(1300, 850); w.show(); app.processEvents()


def check(name, cond):
    print(('OK   ' if cond else 'FAIL ') + name)


try:
    doc = Document(400, 300)
    top = new_image(100, 100, QColor(255, 0, 0))
    doc.layers.append(Layer('Rød firkant', top, QPoint(50, 50)))
    doc.active = 1
    c = w.add_document(doc); c.fit(); app.processEvents()
    sp = lambda x, y: QPoint(round(c.to_screen(QPointF(x, y)).x()), round(c.to_screen(QPointF(x, y)).y()))

    # 1 højreklik: lag under musen
    check('lag under musen (firkant)', c.layers_at(QPointF(80, 80)) == [1, 0])
    check('lag under musen (kun baggrund)', c.layers_at(QPointF(300, 250)) == [0])

    # 2 blød pensel
    w.set_tool('brush'); w.opt['size'] = 40; w.opt['hardness'] = 0; w.set_fg(QColor(0, 0, 0))
    doc.active = 0
    QTest.mousePress(c, Qt.LeftButton, Qt.NoModifier, sp(200, 200))
    for x in range(200, 330, 10):
        QTest.mouseMove(c, sp(x, 200))
    QTest.mouseRelease(c, Qt.LeftButton, Qt.NoModifier, sp(330, 200)); app.processEvents()
    img = doc.flatten_image()
    centre, edge = img.pixelColor(260, 200).red(), img.pixelColor(260, 216).red()
    check(f'blød pensel: midte {centre}, kant {edge} (kant lysere og ikke hvid)', centre < 40 and 60 < edge < 250)
    w.opt['hardness'] = 100

    # 3 beskæring
    w.set_tool('crop'); app.processEvents()
    check('beskæringsramme = hele billedet', c.crop is not None and c.crop.toRect() == doc.rect())
    QTest.mousePress(c, Qt.LeftButton, Qt.NoModifier, sp(400, 300))   # nederste højre håndtag
    QTest.mouseMove(c, sp(300, 250)); QTest.mouseMove(c, sp(250, 200))
    QTest.mouseRelease(c, Qt.LeftButton, Qt.NoModifier, sp(250, 200)); app.processEvents()
    check(f'træk i håndtag: {c.crop}', c.crop.toRect() == QRect(0, 0, 250, 200))
    QTest.keyClick(c, Qt.Key_Return); app.processEvents()
    check(f'beskåret til {doc.width}x{doc.height}', (doc.width, doc.height) == (250, 200))
    QTest.keyClick(c, Qt.Key_Z, Qt.ControlModifier); app.processEvents()
    check('fortryd beskæring', (doc.width, doc.height) == (400, 300))
    w.set_tool('move')
    check('beskæringsramme væk ved værktøjsskift', c.crop is None)
    doc.dirty = False

    # 4 marker motiv
    w.open_path(r'C:\Windows\Web\Wallpaper\Spotlight\img14.jpg'); app.processEvents()
    d2 = w.doc()
    t = time.time(); w.select_subject(); dt = time.time() - t
    m = d2.selection_np()
    frac = (m > 127).mean() if m is not None else 0
    check(f'marker motiv: {dt:.1f} s, {frac*100:.0f} % markeret', m is not None and 0.2 < frac < 0.75)
    # visualisering: motivet i fuld farve, resten nedtonet
    big = d2.flatten_image()
    vis = new_image(big.width(), big.height(), QColor(40, 40, 40))
    p = QPainter(vis)
    p.setOpacity(0.25); p.drawImage(0, 0, big); p.setOpacity(1)
    cut = big.copy()
    q = QPainter(cut); q.setCompositionMode(QPainter.CompositionMode_DestinationIn); q.drawImage(0, 0, d2.selection); q.end()
    p.drawImage(0, 0, cut); p.end()
    vis.scaled(960, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(OUT + r'\subject.png')
    d2.dirty = False
    print('done')
except Exception:
    traceback.print_exc()

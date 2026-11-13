import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor, QIcon
from PySide6.QtWidgets import QApplication

from .window import MainWindow
from .icons import svg_pixmap

STYLE = """
QMainWindow, QWidget { background:#323232; color:#dcdcdc; font-size:12px; }
QMenuBar { background:#3a3a3a; border-bottom:1px solid #222; }
QMenuBar::item { padding:5px 10px; background:transparent; }
QMenuBar::item:selected { background:#4a4a4a; }
QMenu { background:#3c3c3c; border:1px solid #1e1e1e; padding:4px 0; }
QMenu::item { padding:5px 28px 5px 22px; }
QMenu::item:selected { background:#1473e6; color:white; }
QMenu::item:disabled { color:#777; }
QMenu::separator { height:1px; background:#2a2a2a; margin:4px 8px; }
#toolbox { background:#2b2b2b; border-right:1px solid #1d1d1d; }
#optionsbar { background:#3a3a3a; border-bottom:1px solid #1d1d1d; }
QToolButton { background:transparent; border:1px solid transparent; border-radius:3px; padding:2px; }
QToolButton:hover { background:#454545; }
QToolButton:checked { background:#1f1f1f; border:1px solid #555; }
QTabWidget::pane { border:none; }
QTabBar { background:#2b2b2b; }
QTabBar::tab { background:#2b2b2b; color:#aaa; padding:6px 12px; border-right:1px solid #1d1d1d; }
QTabBar::tab:selected { background:#454545; color:#fff; }
QDockWidget { color:#ddd; font-weight:bold; }
QDockWidget::title { background:#2b2b2b; padding:6px; border-bottom:1px solid #1d1d1d; }
QSpinBox, QComboBox, QLineEdit { background:#262626; border:1px solid #1a1a1a; border-radius:2px; padding:2px 4px; color:#eee; min-height:18px; }
QComboBox QAbstractItemView { background:#3c3c3c; selection-background-color:#1473e6; }
QCheckBox { spacing:5px; }
QStatusBar { background:#2b2b2b; border-top:1px solid #1d1d1d; }
QStatusBar QLabel { color:#aaa; padding:0 8px; }
QPushButton { background:#4a4a4a; border:1px solid #222; border-radius:3px; padding:5px 14px; }
QPushButton:hover { background:#555; }
QPushButton:default { border:1px solid #1473e6; }
QScrollBar:vertical { background:#2b2b2b; width:10px; }
QScrollBar::handle:vertical { background:#555; border-radius:4px; min-height:20px; }
QToolTip { background:#202020; color:#eee; border:1px solid #555; padding:4px; }
"""


def main():
    os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')
    app = QApplication(sys.argv)
    app.setApplicationName('Lagkage')
    # danske standardknapper (Annullér, Ja, Nej, Gem …)
    from PySide6.QtCore import QTranslator, QLibraryInfo, QLocale
    tr = QTranslator(app)
    if tr.load(QLocale(QLocale.Danish), 'qtbase', '_', QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(tr)
    app.setStyle('Fusion')
    pal = QPalette()
    for role, col in ((QPalette.Window, '#323232'), (QPalette.WindowText, '#dcdcdc'), (QPalette.Base, '#262626'),
                      (QPalette.AlternateBase, '#2e2e2e'), (QPalette.Text, '#eeeeee'), (QPalette.Button, '#454545'),
                      (QPalette.ButtonText, '#eeeeee'), (QPalette.Highlight, '#1473e6'),
                      (QPalette.HighlightedText, '#ffffff'), (QPalette.ToolTipBase, '#202020'),
                      (QPalette.ToolTipText, '#eeeeee')):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)
    here = os.path.dirname(os.path.abspath(__file__))
    ico = os.path.join(here, 'lagkage.ico')
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    win = MainWindow()
    win.show()
    for arg in sys.argv[1:]:
        if os.path.isfile(arg):
            win.open_path(arg)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

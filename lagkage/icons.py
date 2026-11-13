"""Værktøjsikoner som små SVG'er."""
from PySide6.QtCore import QByteArray, Qt, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

S = 'fill="none" stroke="#d6d6d6" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'
F = 'fill="#d6d6d6"'

SVG = {
    'move': f'<path {S} d="M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3"/>',
    'rect': f'<rect {S} x="4" y="5" width="16" height="14" stroke-dasharray="2.5 2"/>',
    'ellipse': f'<ellipse {S} cx="12" cy="12" rx="8.5" ry="6.5" stroke-dasharray="2.5 2"/>',
    'lasso': f'<path {S} d="M6 15c-3-3 0-9 7-9s9 4 6 7-9 3-11 2M8 15c-1 2 0 4 2 4"/>',
    'poly': f'<path {S} d="M5 18 L7 6 L17 4 L19 13 L11 12 Z"/>',
    'wand': f'<path {S} d="M5 19 L15 9"/><path {S} d="M17 3v4M15 5h4M20 9v2M19 10h2M11 3v2M10 4h2"/>',
    'eyedropper': f'<path {S} d="M4 20l2-1 9-9-2-2-9 9-1 2zM13 8l3-3a2 2 0 0 1 3 3l-3 3M12 7l5 5"/>',
    'brush': f'<path {S} d="M20 4L11 13M11 13c-2-1-4 0-5 2s-1 4-3 5c3 1 7 0 8-2s1-3 0-5z"/>',
    'eraser': f'<path {S} d="M4 16l9-9 6 6-6 6H8zM9 19h11M10 10l6 6"/>',
    'bucket': f'<path {S} d="M5 12l7-7 7 7-7 7zM12 5l-3-3M19 12c1 2 2 3 2 4a2 2 0 0 1-4 0c0-1 1-2 2-4z"/>',
    'hand': f'<path {S} d="M8 12V6a1.5 1.5 0 0 1 3 0v5M11 11V4.5a1.5 1.5 0 0 1 3 0V11M14 11V6a1.5 1.5 0 0 1 3 0v7c0 4-2 7-6 7-3 0-4-1-6-4l-2-4a1.5 1.5 0 0 1 2.5-1.5L8 13"/>',
    'zoom': f'<circle {S} cx="10" cy="10" r="6"/><path {S} d="M14.5 14.5L20 20M7.5 10h5M10 7.5v5"/>',
    'crop': f'<path {S} d="M6 2v16h16M2 6h16v16"/>',
    'new_layer': f'<rect {S} x="4" y="4" width="16" height="16" rx="1"/><path {S} d="M12 8v8M8 12h8"/>',
    'dup_layer': f'<rect {S} x="7" y="3" width="13" height="13" rx="1"/><path {S} d="M4 8v12h12"/>',
    'merge': f'<path {S} d="M5 4h14M5 9h14M12 12v8M8 16l4 4 4-4"/>',
    'trash': f'<path {S} d="M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13M10 11v6M14 11v6"/>',
    'eye': f'<path {S} d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6S2 12 2 12z"/><circle {F} cx="12" cy="12" r="3"/>',
    'mode_new': f'<rect {F} x="5" y="5" width="14" height="14"/>',
    'mode_add': f'<rect {F} x="3" y="3" width="11" height="11"/><rect {F} x="10" y="10" width="11" height="11"/>',
    'mode_sub': f'<rect {F} x="3" y="3" width="11" height="11"/><rect fill="#323232" stroke="#d6d6d6" stroke-width="1.2" x="10" y="10" width="11" height="11"/>',
    'mode_int': f'<rect {S} x="3" y="3" width="11" height="11"/><rect {S} x="10" y="10" width="11" height="11"/><rect {F} x="10" y="10" width="4" height="4"/>',
    'swap': f'<path {S} d="M6 4h9a3 3 0 0 1 3 3v9M15 16l3 3 3-3M6 4l3-3M6 4l3 3"/>',
}


def svg_pixmap(name, size=24):
    data = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{SVG[name]}</svg>'
    r = QSvgRenderer(QByteArray(data.encode()))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    r.render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


def icon(name, size=24):
    return QIcon(svg_pixmap(name, size))

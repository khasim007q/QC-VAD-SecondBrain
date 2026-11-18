"""Draw the app icon (open book with a speech line) and save it as a multi-size .ico."""

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen

OUT = Path(__file__).resolve().parents[1] / "src" / "classnotes" / "ui" / "icon.ico"


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256.0
    p.scale(s, s)
    # background tile
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#14532d"))
    p.drawRoundedRect(QRectF(8, 8, 240, 240), 48, 48)
    # open book: two pages
    page = QColor("#f8fafc")
    p.setBrush(page)
    left = QPainterPath(QPointF(128, 92))
    left.cubicTo(100, 74, 64, 72, 40, 80)
    left.lineTo(40, 196)
    left.cubicTo(64, 188, 100, 190, 128, 208)
    left.closeSubpath()
    right = QPainterPath(QPointF(128, 92))
    right.cubicTo(156, 74, 192, 72, 216, 80)
    right.lineTo(216, 196)
    right.cubicTo(192, 188, 156, 190, 128, 208)
    right.closeSubpath()
    p.drawPath(left)
    p.drawPath(right)
    # spine
    p.setPen(QPen(QColor("#14532d"), 6, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(128, 96), QPointF(128, 204))
    # text lines (right page) and a sound wave (left page)
    p.setPen(QPen(QColor("#16a34a"), 9, Qt.SolidLine, Qt.RoundCap))
    for y in (118, 142, 166):
        p.drawLine(QPointF(148, y), QPointF(198, y - 4))
    for x, h in ((58, 14), (74, 34), (90, 22), (106, 10)):
        p.drawLine(QPointF(x, 142 - h), QPointF(x, 142 + h))
    p.end()
    return img


def main() -> int:
    QGuiApplication(sys.argv)
    # Qt's ICO writer stores one image; write the largest and let Windows scale.
    img = draw(256)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not img.save(str(OUT), "ICO"):
        print("ICO save failed", file=sys.stderr)
        return 1
    img.save(str(OUT.with_suffix(".png")), "PNG")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

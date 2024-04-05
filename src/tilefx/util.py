from __future__ import annotations
from collections import defaultdict
from typing import Any, Generic, Optional, Iterable, Hashable, Sequence

import math
from typing import TypeVar

from PySide2 import QtGui, QtCore, QtWidgets
from PySide2.QtCore import Qt


# Type aliases
H = TypeVar("H", bound=Hashable)
K = TypeVar("K")
V = TypeVar("V")


def invertedDict(d: dict[K, V]) -> dict[V, K]:
    return {v: k for k, v in d.items()}


def validSizeHint(item: QtWidgets.QGraphicsItem, which: Qt.SizeHint,
                  constraint: QtCore.QSizeF) -> QtCore.QSizeF:
    hint = item.sizeHint(which, constraint)
    if hint.width() < 0:
        if which == Qt.MinimumSize:
            w = 0.0
        elif which == Qt.MaximumSize:
            w = 999999.0
        else:
            w = 64.0
        hint.setWidth(w)
    if hint.height() < 0:
        if which == Qt.MinimumSize:
            h = 0.0
        elif which == Qt.MaximumSize:
            h = 999999.0
        else:
            h = 64.0
        hint.setHeight(h)
    return hint


def drawTextDocument(painter: QtGui.QPainter, rect: QtCore.QRectF,
                     doc: QtGui.QTextDocument, palette: QtGui.QPalette,
                     color: QtGui.QColor = None,
                     role: QtGui.QPalette.ColorRole = QtGui.QPalette.WindowText
                     ) -> None:
    tx = rect.x()
    ty = rect.y()
    height = doc.size().height()
    align = doc.defaultTextOption().alignment()
    if align & Qt.AlignVCenter:
        ty += rect.height() / 2 - height / 2
    elif align & Qt.AlignBottom:
        ty = rect.bottom() - height

    painter.translate(tx, ty)
    text_rect = rect.translated(-tx, -ty)
    # painter.setClipRect(rect, Qt.IntersectClip)

    # QAbstractTextDocumentLayout is hardcoded to draw the text using
    # the Text role, but we want to use WindowText for values (and also
    # for it to be configurable), so I have to munge the palette and
    # pass that to the draw() method
    if color:
        palette.setColor(palette.Text, color)
    elif role != palette.Text:
        palette.setBrush(palette.Text, palette.brush(role))

    context = QtGui.QAbstractTextDocumentLayout.PaintContext()
    context.palette = palette
    context.cursorPosition = -1
    context.clip = text_rect
    doc.documentLayout().draw(painter, context)


def drawChasingArc(painter: QtGui.QPainter, rect: QtCore.QRect,
                   timestep: int, color: QtGui.QColor = None) -> None:
    color = color or QtGui.QColor.fromRgbF(1.0, 1.0, 1.0)
    pen = QtGui.QPen(color, 1.0)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    sweep = abs(math.sin((timestep % 500) / 500 * math.pi)) * 140 + 10
    degrees = -(timestep % 360)
    start_ticks = int((degrees - sweep / 2) * 16)
    sweep_ticks = int(sweep * 16)
    painter.drawArc(rect, start_ticks, sweep_ticks)


def drawFadingRings(painter: QtGui.QPainter, rect: QtCore.QRectF,
                    timestep: int, color: QtGui.QColor = None, ring_count=3
                    ) -> None:
    color = color or QtGui.QColor.fromRgbF(1.0, 1.0, 1.0)
    half = rect.width() / 2
    ctr = rect.center()
    interval = (half * 1.5) / ring_count
    pct = (timestep % 100) / 100
    for i in range(ring_count + 1):
        r = i * interval + (interval * pct)
        color.setAlphaF(1.0 - max(0.0, r / half))
        painter.setPen(QtGui.QPen(color, 1.5))
        painter.drawEllipse(ctr, r, r)


def recolorPixmap(pixmap: QtGui.QPixmap, color: QtGui.QColor) -> None:
    if pixmap.isNull():
        return
    p = QtGui.QPainter(pixmap)
    p.setCompositionMode(p.CompositionMode_SourceAtop)
    p.fillRect(pixmap.rect(), color)
    p.end()


def find_object(name: str) -> Any:
    if "." not in name:
        raise ValueError(f"Name {name} must be fully qualified")
    modname, clsname = name.rsplit(".", 1)
    mod = __import__(modname, fromlist=[clsname])
    cls = getattr(mod, clsname)
    return cls


def containingRectF(rects: Sequence[QtCore.QRectF]) -> QtCore.QRectF:
    rect = QtCore.QRectF()
    if rects:
        x1: Optional[float] = None
        y1: Optional[float] = None
        x2: Optional[float] = None
        y2: Optional[float] = None
        for r in rects:
            if x1 is None or r.x() < x1:
                x1 = r.x()
            if y1 is None or r.y() < y1:
                y1 = r.y()
            if x2 is None or r.right() > x2:
                x2 = r.right()
            if y2 is None or r.bottom() > y2:
                y2 = r.bottom()
        rect.setCoords(x1, y1, x2, y2)
    return rect


def alignedRectF(direction: Qt.LayoutDirection, alignment: Qt.Alignment,
                 size: QtCore.QSizeF, rectangle: QtCore.QSizeF
                 ) -> QtCore.QRectF:
    alignment = QtWidgets.QStyle.visualAlignment(direction, alignment)
    x = rectangle.x()
    y = rectangle.y()
    w = size.width()
    h = size.height()

    if alignment & Qt.AlignVCenter:
        y = rectangle.center().y() - h / 2.0
    elif alignment & Qt.AlignBottom:
        y = rectangle.bottom() - h

    if alignment & Qt.AlignRight:
        x = rectangle.right() - w
    elif alignment & Qt.AlignHCenter:
        x = rectangle.center().x() - w / 2.0

    return QtCore.QRectF(x, y, w, h)


class CircularDependencyError(Exception):
    pass


class DependencyGraph(Generic[H]):
    def __init__(self, values: Iterable[H] = None):
        self._values = list(values) if values else []
        self._value_set: set[H] = set(self._values)
        self._prereqs: defaultdict[H, set[H]] = defaultdict(set)
        self._resolved: set[H] = set()
        self._unresolved: set[H] = set()

    def add(self, value: H) -> None:
        if value not in self._value_set:
            self._value_set.add(value)
            self._values.append(value)

    def depends_on(self, value: H, prereq: H) -> None:
        if value not in self._value_set:
            self.add(value)
        if prereq not in self._value_set:
            self.add(prereq)
        self._prereqs[value].add(prereq)

    def resolve(self, values: Sequence[H] = None) -> Iterable[H]:
        values = values or self._values
        for v in values:
            if v in self._resolved:
                continue
            if v in self._unresolved:
                raise CircularDependencyError(v)

            self._unresolved.add(v)
            if v in self._prereqs:
                prevs = list(self._prereqs[v])
                prevs.sort(key=lambda x: self._values.index(x))
                for prev in self.resolve(prevs):
                    yield prev

            self._unresolved.remove(v)
            self._resolved.add(v)
            yield v

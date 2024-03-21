from __future__ import annotations

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt


class ColorBlendEffect(QtWidgets.QGraphicsEffect):
    def __init__(self, parent: QtCore.QObject = None):
        super().__init__(parent)
        self._color = QtGui.QColor("#ff00ff")
        self._strength = 0.5

    def color(self) -> QtGui.QColor:
        return QtGui.QColor(self._color)

    def setColor(self, color: QtGui.QColor) -> None:
        self._color = color
        self.update()

    def strength(self) -> float:
        return self._strength

    def setStrength(self, strength: float):
        self._strength = strength
        self.update()

    def draw(self, painter: QtGui.QPainter) -> None:
        strength = self.strength()
        if strength:
            offset = QtCore.QPoint()
            pixmap = self.sourcePixmap()
            p = QtGui.QPainter(pixmap)
            p.setCompositionMode(painter.CompositionMode_SourceAtop)
            color = self.color()
            color.setAlphaF(self.strength())
            brush = QtGui.QBrush(color)
            p.fillRect(pixmap.rect(), brush)
            p.end()
            painter.drawPixmap(offset, pixmap)
        else:
            self.drawSource(painter)

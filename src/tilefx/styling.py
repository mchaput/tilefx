from __future__ import annotations
import enum
from typing import Iterable, Sequence, Union

from PySide2 import QtCore, QtGui, QtWidgets, QtSvg
from PySide2.QtCore import Qt

from . import converters


class TextSize(enum.IntEnum):
    small_label = 10
    label = 12
    tiny = 10
    xsmall = 11
    small = 12
    medium = 13
    large = 16
    xlarge = 20
    huge = 28


TONE_LIGHTNESS = (1.0, 0.6, 0.8, 0.4, 0.2, 0.9, 0.7, 0.5, 0.3)

_icon_cache: dict[tuple[str, int, str], QtGui.QPixmap] = {}
warning_svg = """
<svg width="24" height="24" stroke-width="1.5" viewBox="0 0 24 24" fill="none" stroke="#ffffff" xmlns="http://www.w3.org/2000/svg">
<path d="M20.0429 21H3.95705C2.41902 21 1.45658 19.3364 2.22324 18.0031L10.2662 4.01533C11.0352 2.67792 12.9648 2.67791 13.7338 4.01532L21.7768 18.0031C22.5434 19.3364 21.581 21 20.0429 21Z" stroke="#ffffff" stroke-linecap="round"/>
<path d="M12 9V13" stroke="#ffffff" stroke-linecap="round"/>
<path d="M12 17.01L12.01 16.9989" stroke="#ffffff" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""
gear_svg = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="#ffffff">
<path d="M 13.187 3 L 13.031 3.812 L 12.437 6.781 C 11.484 7.156 
10.625 7.683 9.843 8.312 L 6.937 7.312 L 6.156 7.062 L 5.75 7.781 
L 3.75 11.218 L 3.343 11.937 L 3.937 12.468 L 6.187 14.437 
C 6.105 14.949 6 15.460 6 16 C 6 16.539 6.105 17.050 6.187 
17.562 L 3.937 19.531 L 3.343 20.062 L 3.75 20.781 L 5.75 24.218 
L 6.156 24.937 L 6.937 24.687 L 9.843 23.687 C 10.625 24.316 
11.484 24.843 12.437 25.218 L 13.031 28.187 L 13.187 29 L 18.812 29 
L 18.968 28.187 L 19.562 25.218 C 20.515 24.843 21.375 24.316 
22.156 23.687 L 25.062 24.687 L 25.843 24.937 L 26.25 24.218 
L 28.25 20.781 L 28.656 20.062 L 28.062 19.531 L 25.812 17.562 
C 25.894 17.050 26 16.539 26 16 C 26 15.460 25.894 14.949 
25.812 14.437 L 28.062 12.468 L 28.656 11.937 L 28.25 11.218 
L 26.25 7.781 L 25.843 7.062 L 25.062 7.312 L 22.156 8.312 
C 21.375 7.683 20.515 7.156 19.562 6.781 L 18.968 3.812 
L 18.812 3 Z M 14.812 5 L 17.187 5 L 17.687 7.593 L 17.812 8.187 
L 18.375 8.375 C 19.511 8.730 20.542 9.332 21.406 10.125 
L 21.843 10.531 L 22.406 10.343 L 24.937 9.468 L 26.125 11.5 
L 24.125 13.281 L 23.656 13.656 L 23.812 14.25 C 23.941 14.820 24 
15.402 24 16 C 24 16.597 23.941 17.179 23.812 17.75 L 23.687 
18.343 L 24.125 18.718 L 26.125 20.5 L 24.937 22.531 L 22.406 21.656 
L 21.843 21.468 L 21.406 21.875 C 20.542 22.667 19.511 23.269 
18.375 23.625 L 17.812 23.812 L 17.687 24.406 L 17.187 27 L 14.812 27 
L 14.312 24.406 L 14.187 23.812 L 13.625 23.625 C 12.488 23.269 
11.457 22.667 10.593 21.875 L 10.156 21.468 L 9.593 21.656 
L 7.062 22.531 L 5.875 20.5 L 7.875 18.718 L 8.343 18.343 L 8.187 
17.75 C 8.058 17.179 8 16.597 8 16 C 8 15.402 8.058 14.820 
8.187 14.25 L 8.343 13.656 L 7.875 13.281 L 5.875 11.5 L 7.062 9.468 
L 9.593 10.343 L 10.156 10.531 L 10.593 10.125 C 11.457 9.332 
12.488 8.730 13.625 8.375 L 14.187 8.187 L 14.312 7.593 Z M 16 11 
C 13.25 11 11 13.25 11 16 C 11 18.75 13.25 21 16 21 C 18.75 21 21 18.75 21 16 
C 21 13.25 18.75 11 16 11 Z M 16 13 C 17.667 13 19 14.332 19 16 C 19 
17.667 17.667 19 16 19 C 14.332 19 13 17.667 13 16 C 13 14.332 
14.332 13 16 13 Z"/></svg>
"""


def makeSvgPixmap(svg_text: str, size: int, hex_color: str = "#ffffff"
                  ) -> QtGui.QPixmap:
    svg_bytes = svg_text.replace("#ffffff", hex_color).encode("utf-8")
    svgr = QtSvg.QSvgRenderer(svg_bytes)
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    svgr.render(painter)
    painter.end()
    return pixmap


def svgPixmap(svg_text: str, size: int,
              color: Union[str, QtGui.QColor] = "#ffffff") -> QtGui.QPixmap:
    if isinstance(color, QtGui.QColor):
        color = color.name()
    key = (svg_text, size, color)
    if key in _icon_cache:
        pixmap = _icon_cache[key]
    else:
        pixmap = _icon_cache[key] = makeSvgPixmap(svg_text, size, color)
    return pixmap


def warningPixmap(color: Union[str, QtGui.QColor], size: int) -> QtGui.QPixmap:
    return svgPixmap(warning_svg, size, color)


def gearPixmap(color: Union[str, QtGui.QColor], size: int) -> QtGui.QPixmap:
    return svgPixmap(gear_svg, size, color)


def paintColorChip(painter: QtGui.QPainter, rect: QtCore.QRectF,
                   fill: QtGui.QBrush, pen: QtGui.QPen = Qt.NoPen,
                   chip_size=8.0) -> None:
    chip_size = min(chip_size, rect.width(), rect.height())
    x = rect.x() + chip_size / 2.0
    y = rect.center().y() - chip_size / 2.0
    chiprect = QtCore.QRectF(x, y, chip_size, chip_size)
    painter.setPen(pen)
    painter.setBrush(fill)
    painter.drawEllipse(chiprect)


class TextStyle(enum.Enum):
    text = enum.auto()
    number = enum.auto()
    label = enum.auto()
    warning = enum.auto()
    error = enum.auto()


class BorderSides(enum.Enum):
    none = enum.auto()
    all_sides = enum.auto()
    left_side = enum.auto()
    top_side = enum.auto()
    right_side = enum.auto()
    bottom_side = enum.auto()
    corners = enum.auto()
    octants = enum.auto()
    brackets_v = enum.auto()
    brackets_h = enum.auto()


def tonePolicy(color: QtGui.QColor) -> ColorLookupPolicy:
    tones = []
    for tl in TONE_LIGHTNESS:
        c = QtGui.QColor.fromHslF(color.hueF(), color.saturationF(), tl)
        tones.append(QtGui.QBrush(c))
    return ColorLookupPolicy(tones)


def setLabelStyle(label: QtWidgets.QLabel, size: int = None, family: str = None,
                  bold: bool = None, italic: bool = None,
                  underline: bool = None, color: QtGui.QColor = None,
                  bgcolor: QtGui.QColor = None, weight: int = None,
                  role: QtGui.QPalette.ColorRole = None,
                  line_height: int = None, letter_spacing_percent: int = None,
                  letter_spacing_absolute: int = None):
    if family or size or bold is not None or italic is not None or \
            letter_spacing_percent or letter_spacing_absolute:
        f = label.font()
        if family:
            f.setFamily(family)
        if size:
            f.setPixelSize(size)
        if bold is not None:
            f.setBold(bold)
        if italic is not None:
            f.setItalic(italic)
        if underline is not None:
            f.setUnderline(underline)
        if weight is not None:
            f.setWeight(weight)
        if letter_spacing_percent:
            f.setLetterSpacing(f.PercentageSpacing, letter_spacing_percent)
        if letter_spacing_absolute:
            f.setLetterSpacing(f.AbsoluteSpacing, letter_spacing_absolute)
        label.setFont(f)
    if color or bgcolor:
        p = label.palette()
        if color:
            p.setColor(p.Text, color)
            label.setForegroundRole(p.Text)
        if bgcolor:
            p.setColor(p.Window, bgcolor)
            label.setAutoFillBackground(True)
        label.setPalette(p)

    if role:
        label.setForegroundRole(role)


class ColorPolicy:
    def __repr__(self):
        return f"<{type(self).__name__} {self.__dict__}>"

    def brushForIndex(self, index: int, length: int, value: float
                      ) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        return QtGui.QBrush(QtGui.QColor(128, 128, 128,))

    def mono(self) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        return QtGui.QBrush(QtGui.QColor(128, 128, 128, ))


class ColorLookupPolicy(ColorPolicy):
    def __init__(self, brushes: Iterable[Union[QtGui.QBrush, QtGui.QColor, str]]):
        self.brushes = [converters.brushConverter(b) for b in brushes]

    def __repr__(self):
        return f"<{type(self).__name__} {self.brushes}>"

    def brushForIndex(self, index: int, length: int, value: float
                      ) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        return QtGui.QBrush(self.brushes[index % len(self.brushes)])

    def mono(self) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        return self.brushes[0].color()


class RoleListPolicy(ColorPolicy):
    def __init__(self, roles: Sequence[QtGui.QPalette.ColorRole]):
        self.roles = roles

    def __repr__(self):
        return f"<{type(self).__name__} {self.roles}>"

    def brushForIndex(self, index: int, length: int, value: float
                      ) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        index = index % len(self.roles)
        return self.roles[index]

    def mono(self) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        return self.roles[0]


class RotatingColorPolicy(ColorPolicy):
    def __init__(self, base_hue=0.0, saturation=1.0, lightness=0.5):
        self.base_hue = base_hue
        self.saturation = saturation
        self.lightness = lightness

    def __repr__(self):
        return (f"<{type(self).__name__} {self.base_hue} "
                f"{self.saturation} {self.lightness}>")

    def brushForIndex(self, index: int, length: int, value: float
                      ) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        hue = self.base_hue + (1.0 / length * index)
        c = QtGui.QColor.fromHslF(hue, self.saturation, self.lightness)
        return QtGui.QBrush(c)

    def mono(self) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        return QtGui.QColor.fromHslF(self.base_hue, self.saturation,
                                     self.lightness)


class GradientColorPolicy(ColorPolicy):
    def __init__(self, color1: QtGui.QColor, color2: QtGui.QColor):
        self._color1 = color1
        self._color2 = color2

    def __repr__(self):
        return f"<{type(self).__name__} {self._color1} {self._color2}>"

    def brushForIndex(self, index: int, length: int, value: float
                      ) -> QtGui.QColor:
        from .themes import blend
        pct = index / length
        c = blend(self._color1, self._color2, pct)
        return QtGui.QBrush(c)

    def mono(self) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        return self._color1


class ValueGradientColorPolicy(GradientColorPolicy):
    def brushForIndex(self, index: int, length: int, value: float
                      ) -> QtGui.QColor:
        from .themes import blend
        c = blend(self._color1, self._color2, value)
        return QtGui.QBrush(c)


class MonochromeColorPolicy(ColorPolicy):
    def __init__(self, color: QtGui.QColor):
        self.color = color

    def __repr__(self):
        return f"<{type(self).__name__} {self.color}>"

    def brushForIndex(self, index: int, length: int, value: float
                      ) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        return QtGui.QBrush(self.color)

    def mono(self) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        return self.color


class MonochromeRolePolicy(ColorPolicy):
    def __init__(self, role):
        self.role = role

    def brushForIndex(self, index: int, length: int, value: float
                      ) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        return self.mono()

    def mono(self) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        return self.role


class OverrideColorPolicy(ColorPolicy):
    def __init__(self, policy: ColorPolicy):
        self._policy = policy
        self._overrides: dict[int, QtGui.QBrush] = {}

    def addOverride(self, index: int, brush: QtGui.QBrush):
        self._overrides[index] = brush

    def brushForIndex(self, index: int, length: int, value: float
                      ) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        if index in self._overrides:
            return QtGui.QBrush(self._overrides[index])
        else:
            return self._policy.brushForIndex(index, length, value)

    def mono(self) -> Union[QtGui.QBrush, QtGui.QPalette.ColorRole]:
        return self._policy.mono()


class Border:
    def __init__(self, sides: BorderSides = BorderSides.none,
                 color: QtGui.QColor = Qt.black, width=1.0,
                 penstyle: Qt.PenStyle = Qt.SolidLine):
        self._bordersides = sides
        self._pen = QtGui.QPen(color)
        self._pen.setJoinStyle(Qt.MiterJoin)
        self._pen.setWidthF(width)
        self._pen.setStyle(penstyle)

    def isValid(self) -> bool:
        return self._bordersides != BorderSides.none and self._pen.width() > 0

    def setBorderSides(self, sides: BorderSides):
        self._bordersides = sides

    def borderSides(self) -> BorderSides:
        return self._bordersides

    def setSolidBorder(self):
        self._pen.setStyle(Qt.SolidLine)

    def setDashedBorder(self, width=None):
        if width is not None:
            self.setBorderWidth(width)
        self._pen.setStyle(Qt.DotLine)

    def setStripedBorder(self, width: float = None, color: QtGui.QColor = None,
                         color2: QtGui.QColor = None):
        from . import themes
        color = color if color else self.borderColor()
        color2 = color2 if color2 else QtGui.QColor(0, 0, 0, 0)
        width = (self._pen.widthF() * 0.66) if width is None else width
        self.setBorderBrush(themes.stripes(color, color2, width=width))

    def setBorderColor(self, color: QtGui.QColor):
        if color:
            brush = self._pen.brush()
            brush.setColor(color)
            self._pen.setBrush(brush)

    def setBorderPenStyle(self, penstyle: Qt.PenStyle):
        self._pen.setStyle(penstyle)

    def setBorderBrushStyle(self, brushstyle: Qt.BrushStyle):
        brush = self.borderBrush()
        brush.setStyle(brushstyle)
        self.setBorderBrush(brush)

    def setBorderBrush(self, brush: QtGui.QBrush):
        self._pen.setBrush(brush)

    def setBorderWidth(self, width: float):
        self._pen.setWidthF(width)

    def borderPen(self) -> QtGui.QPen:
        return self._pen

    def borderBrush(self) -> QtGui.QBrush:
        return self._pen.brush()

    def borderWidth(self) -> float:
        return self._pen.widthF()

    def borderColor(self) -> QtGui.QColor:
        return self._pen.brush().color()

    def paintBorder(self, painter: QtGui.QPainter, rect: QtCore.QRect):
        sides = self._bordersides
        pen = self._pen
        penwidth = pen.widthF() * 1.0
        half = penwidth * 0.5
        ctr = QtCore.QRectF(rect).adjusted(half, half, -half, -half)

        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        shorter = ctr.width() if ctr.width() < ctr.height() else ctr.height()
        cornerwidth = 0
        oscale = 1.0
        if shorter >= penwidth * 8:
            cornerwidth = shorter / 8
            oscale = 2.0
        elif shorter >= penwidth * 5:
            cornerwidth = shorter / 5
            oscale = 2.0

        if cornerwidth:
            xoff = QtCore.QPointF(cornerwidth, 0)
            yoff = QtCore.QPointF(0, cornerwidth)
        else:
            xoff = yoff = QtCore.QPointF()

        if sides == BorderSides.all_sides:
            painter.drawRect(ctr)
        elif sides == BorderSides.left_side:
            painter.drawLine(ctr.topLeft(), ctr.bottomLeft())
        elif sides == BorderSides.top_side:
            painter.drawLine(ctr.topLeft(), ctr.topRight())
        elif sides == BorderSides.right_side:
            painter.drawLine(ctr.topRight(), ctr.bottomRight())
        elif sides == BorderSides.bottom_side:
            painter.drawLine(ctr.bottomLeft(), ctr.bottomRight())
        elif sides == BorderSides.brackets_v:
            painter.drawPolyline([ctr.topLeft() + xoff, ctr.topLeft(),
                                 ctr.bottomLeft(), ctr.bottomLeft() + xoff])
            painter.drawPolyline([ctr.topRight() - xoff, ctr.topRight(),
                                  ctr.bottomRight(), ctr.bottomRight() - xoff])
        elif sides == BorderSides.brackets_h:
            painter.drawPolyline([ctr.topLeft() + yoff, ctr.topLeft(),
                                  ctr.topRight(), ctr.topRight() + yoff])
            painter.drawPolyline([ctr.bottomLeft() - yoff, ctr.bottomLeft(),
                                  ctr.bottomRight(), ctr.bottomRight() - yoff])

        if ((sides == BorderSides.corners or sides == BorderSides.octants)
                and cornerwidth):
            painter.drawPolyline([ctr.topLeft() + yoff, ctr.topLeft(),
                                  ctr.topLeft() + xoff])
            painter.drawPolyline([ctr.topRight() + yoff, ctr.topRight(),
                                  ctr.topRight() - xoff])
            painter.drawPolyline([ctr.bottomLeft() - yoff, ctr.bottomLeft(),
                                  ctr.bottomLeft() + xoff])
            painter.drawPolyline([ctr.bottomRight() - yoff, ctr.bottomRight(),
                                  ctr.bottomRight() - xoff])
        if sides == BorderSides.octants and cornerwidth:
            xoff = xoff * oscale
            yoff = yoff * oscale
            painter.drawLine(ctr.topLeft() + xoff, ctr.topRight() - xoff)
            painter.drawLine(ctr.bottomLeft() + xoff, ctr.bottomRight() - xoff)
            painter.drawLine(ctr.topLeft() + yoff, ctr.bottomLeft() - yoff)
            painter.drawLine(ctr.topRight() + yoff, ctr.bottomRight() - yoff)

        painter.restore()


def checkmarkPoints(rect: QtCore.QRectF) -> Sequence[QtCore.QPointF]:
    x = rect.x()
    y = rect.y()
    w = rect.width()
    h = rect.height()
    return (
        QtCore.QPointF(x, y + h * 0.43),
        QtCore.QPointF(x + w * 0.43, y + h * 0.91),
        QtCore.QPointF(rect.right(), y + h * 0.1)
    )


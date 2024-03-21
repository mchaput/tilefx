from __future__ import annotations
import enum
import json
import os.path
import pathlib
from datetime import datetime
from types import CodeType
from typing import (TYPE_CHECKING, Any, Callable, Collection, Iterable, Mapping,
                    Optional, Sequence, TypeVar, Union)

import shiboken2
from PySide2 import QtCore, QtGui, QtWidgets, QtSvg
from PySide2.QtCore import Qt

from . import (config, converters, charts, formatting, graphics, layouts,
               models, styling, themes, views)
from .config import settable
from .editors.syntax import syntaxHighlighterConverter
from .graphics import FONT_FAMILY, NUMBER_FAMILY, graphictype, Graphic

if TYPE_CHECKING:
    import hou


# Do not scale these by hou.ui.scaledSize(), that is handled at another level
GRID_COL_WIDTH = 80
GRID_ROW_HEIGHT = 60
PANEL_WIDTH = 400
SCALES = [0.75, 0.865, 1.0, 1.2]
CHART_SIZES = [32, 48, 64, 128]
BASE_FONT_SIZE = 14

DEFAULT_LABEL_MARGIN = 4

DEFAULT_CHART_BG = QtGui.QBrush(QtGui.QColor.fromRgbF(1.0, 1.0, 1.0, 0.2))
DEFAULT_CHART_FG = QtGui.QBrush(QtGui.QColor.fromRgbF(1.0, 1.0, 1.0, 1.0))
DEFAULT_FILL_BRUSH = QtGui.QBrush()
DEFAULT_LABEL_COLOR = QtGui.QColor.fromRgbF(0.8, 0.9, 1.0, 1.0)
DEFAULT_VALUE_COLOR = QtGui.QColor.fromRgbF(1.0, 1.0, 1.0, 1.0)
DEFAULT_TEXT_SHADOW_COLOR = Qt.black
DEFAULT_TEXT_SHADOW_OFFSET = QtCore.QPointF(0.0, 1.0)
DEFUALT_TEXT_SHADOW_BLUR = 2
SECONDARY_ALPHA = 0.5
SMALL_LABEL_SIZE = 10
LABEL_SIZE = 12
XSMALL_TEXT_SIZE = 10
SMALL_TEXT_SIZE = 12
MEDIUM_TEXT_SIZE = 13
LARGE_TEXT_SIZE = 16
XLARGE_TEXT_SIZE = 20
HUGE_TEXT_SIZE = 28

T = TypeVar("T")


def qstyleoption_cast(option: QtWidgets.QStyleOption, cls: type[T]) -> T:
    (cpp_pointer,) = shiboken2.getCppPointer(option)
    return shiboken2.wrapInstance(cpp_pointer, cls)


def toPath(p: Union[str, pathlib.Path]) -> pathlib.Path:
    if isinstance(p, str):
        p = os.path.expanduser(os.path.expandvars(p))
    return pathlib.Path(p).resolve()


def textSize(size: Union[int, str]) -> int:
    if isinstance(size, str):
        size = size.lower().replace("-", "")
        if size == "xsmall":
            size = XSMALL_TEXT_SIZE
        elif size == "small":
            size = SMALL_TEXT_SIZE
        elif size == "medium":
            size = MEDIUM_TEXT_SIZE
        elif size == "large":
            size = LARGE_TEXT_SIZE
        elif size == "xlarge":
            size = XLARGE_TEXT_SIZE
        elif size == "huge":
            size = HUGE_TEXT_SIZE
        else:
            raise ValueError(f"Unknown size: {size}")
    elif not isinstance(size, int):
        raise TypeError(size)
    return size


def getEffect(obj: QtWidgets.QGraphicsItem, cls: type[QtWidgets.QGraphicsEffect]
              ) -> QtWidgets.QGraphicsBlurEffect:
    effect = obj.graphicsEffect()
    if not effect or not isinstance(effect, cls):
        effect = cls(obj)
        obj.setGraphicsEffect(effect)
    return effect


def getShadowEffect(obj: QtWidgets.QGraphicsItem
                    ) -> QtWidgets.QGraphicsDropShadowEffect:
    effect = obj.graphicsEffect()
    if not effect or not isinstance(effect,
                                    QtWidgets.QGraphicsDropShadowEffect):
        effect = QtWidgets.QGraphicsDropShadowEffect(obj)
        effect.setColor(QtGui.QColor.fromRgbF(0, 0, 0, 1.0))
        effect.setOffset(0, 1.0)
        effect.setBlurRadius(14.0)
        obj.setGraphicsEffect(effect)
    return effect


def addSquircle(path: QtGui.QPainterPath, rect: QtCore.QRectF):
    path = path or QtGui.QPainterPath()
    diff = (rect.width() - rect.height()) / 2.0
    ctr = rect.center()
    midleft = QtCore.QPointF(rect.left(), ctr.y())
    midtop = QtCore.QPointF(ctr.x(), rect.top())
    midright = QtCore.QPointF(rect.right(), ctr.y())
    midbottom = QtCore.QPointF(ctr.x(), rect.bottom())
    # Start
    start = midleft if diff >= 0 else QtCore.QPointF(midleft.x(),
                                                     midleft.y() - diff)
    path.moveTo(start)
    if diff < 0:
        path.lineTo(midleft.x(), midleft.y() + diff)
    # Top left
    if diff <= 0:
        path.cubicTo(rect.topLeft(), rect.topLeft(), midtop)
    else:
        path.cubicTo(rect.topLeft(), rect.topLeft(),
                     QtCore.QPointF(midtop.x() - diff, midtop.y()))
        path.lineTo(midtop.x() + diff, midtop.y())
    # Top right
    if diff >= 0:
        path.cubicTo(rect.topRight(), rect.topRight(), midright)
    else:
        path.cubicTo(rect.topRight(), rect.topRight(),
                     QtCore.QPointF(midright.x(), midright.y() + diff))
        path.lineTo(midright.x(), midright.y() - diff)
    # Bottom right
    if diff <= 0:
        path.cubicTo(rect.bottomRight(), rect.bottomRight(), midbottom)
    else:
        path.cubicTo(rect.bottomRight(), rect.bottomRight(),
                     QtCore.QPointF(midbottom.x() + diff, midbottom.y()))
        path.lineTo(midbottom.x() - diff, midbottom.y())
    # Finish
    path.cubicTo(rect.bottomLeft(), rect.bottomLeft(), start)


def loadImage(path: pathlib.Path, size: QtCore.QSize) -> QtGui.QPixmap:
    if path.suffix == ".svg":
        svgr = QtSvg.QSvgRenderer(str(path))
        pixmap = QtGui.QPixmap(size)
        pixmap.fill(Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        svgr.render(painter)
        painter.end()
    else:
        pixmap = QtGui.QPixmap(str(path))
    return pixmap


class TileBackground(QtWidgets.QGraphicsRectItem):
    def __init__(self, parent: QtWidgets.QGraphicsItem,
                 parent_tile: Tile = None) -> None:
        super().__init__(parent)
        self._parent_tile = parent_tile or parent
        self._fillrole: QtGui.QPalette.ColorRole = QtGui.QPalette.Base
        self._brush: Optional[QtGui.QBrush] = None
        self._linerole: QtGui.QPalette.ColorRole = QtGui.QPalette.Text
        self._linebrush: Optional[QtGui.QBrush] = None
        self._linewidth = 0.0
        self._outer_glow = 130
        self._radius = 8.0
        self._tint: Optional[QtGui.QColor] = None
        self._tintalpha = 0.2
        self.setFlag(self.ItemClipsChildrenToShape, True)

    @settable("fill_role", argtype=QtGui.QPalette.ColorRole)
    def setFillRole(self, role: QtGui.QPalette.ColorRole) -> None:
        self._fillrole = role
        self.update()

    @settable("fill_color", argtype=QtGui.QBrush)
    def setFillBrush(self, brush: QtGui.QBrush) -> None:
        self._brush = brush
        self.update()

    @settable("line_role", argtype=QtGui.QPalette.ColorRole)
    def setLineRole(self, role: QtGui.QPalette.ColorRole) -> None:
        self._linerole = role
        self.update()

    @settable("line_color", argtype=QtGui.QBrush)
    def setLineBrush(self, brush: QtGui.QBrush) -> None:
        self._linebrush = brush
        self.update()

    @settable()
    def setLineWidth(self, width: float) -> None:
        self._linewidth = width
        self.update()

    @settable()
    def setCornerRadius(self, radius: float) -> None:
        self._radius = radius
        self.update()

    @settable(argtype=QtGui.QColor)
    def setTint(self, color: QtGui.QColor):
        self._tint = color
        self.update()

    @settable()
    def setTintAlpha(self, alpha: float) -> None:
        self._tintalpha = alpha
        self.update()

    def shape(self) -> QtGui.QPainterPath:
        radius = self._radius
        if radius:
            path = QtGui.QPainterPath()
            path.addRoundedRect(self.rect(), radius, radius)
            return path
        else:
            return super().shape()

    def _tinted(self, brush: QtGui.QBrush) -> QtGui.QBrush:
        tint = self._tint
        if tint:
            brush = QtGui.QBrush(brush)
            brush.setColor(themes.blend(brush.color(), tint, self._tintalpha))
        return brush

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        palette = self._parent_tile.palette()
        rect = self.rect()
        radius = self._radius
        line_width = self._linewidth
        brush = self._brush
        if not brush:
            brush = self._tinted(palette.brush(self._fillrole))

        # og = self._outer_glow
        # if og and og != 100:
        #     c = brush.color()
        #     gradient = QtGui.QRadialGradient(0.5, 0.5, 0.75)
        #     gradient.setCoordinateMode(gradient.ObjectMode)
        #     gradient.setColorAt(0.0, c)
        #     gradient.setColorAt(0.5, c)
        #     gradient.setColorAt(1.0, c.lighter(og))
        #     brush = QtGui.QBrush(gradient)
        painter.setBrush(brush)

        if line_width:
            line_brush = self._linebrush
            if not line_brush:
                line_brush = palette.brush(self._linerole)
            line_brush = self._tinted(line_brush)
            hw = line_width / 2.0
            rect.adjust(hw, hw, -hw, -hw)
            painter.setPen(QtGui.QPen(line_brush, line_width))
        else:
            painter.setPen(Qt.NoPen)

        if radius:
            painter.drawRoundedRect(rect, radius, radius)
        else:
            painter.drawRect(rect)


settable()(TileBackground.setVisible)


class Tile(Graphic):
    property_aliases = {
        "label_color": "label.color",
        "label_role": "label.color_role",
        "label_align": "label.align",
        "bg_visible": "bg.visible",
        "bg_color": "bg.fill_color",
        "bg_role": "bg.fill_role",
    }

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self.setObjectName(f"tile_{id(self):x}")
        self._styles: dict[str, dict[str, Any]] = {}
        self._vars: dict[str, Any] = {}
        self._ignore_content_geometry = False
        self._tiles: list[Tile] = []

        self._bg = TileBackground(self)
        self._bg.setFillRole(QtGui.QPalette.Base)
        self._label_bg = TileBackground(self._bg, self)
        self._label_bg.setFillRole(QtGui.QPalette.AlternateBase)
        self._label_bg.setCornerRadius(0)

        self._label = graphics.StringGraphic(self)
        self._label.setElideMode(Qt.ElideRight)
        self._label.setForegroundRole(styling.LABEL_ROLE)
        self._label.setZValue(100)
        self._label.setFont(self.contentFont(size=LABEL_SIZE))
        self._label.visibleChanged.connect(self._onLabelVisibility)
        self._label.setMargins(QtCore.QMarginsF(6.0, 6.0, 6.0, 3.0))

        self._line_role = QtGui.QPalette.Text
        self._line_color: Optional[QtGui.QColor] = None
        self._line_width = 0.0
        self._labeloverlayed = False

        # shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        # shadow.setColor(QtGui.QColor.fromRgbF(0, 0, 0, 0.33))
        # shadow.setOffset(0, 1.0)
        # shadow.setBlurRadius(14.0)
        # shadow.setEnabled(True)
        # self.setGraphicsEffect(shadow)

        # self.setFlag(self.ItemSendsGeometryChanges, True)
        # self.setFlag(self.ItemClipsChildrenToShape, True)

        self._labeledge = Qt.TopEdge
        self._inner_margins = QtCore.QMarginsF(5.0, 5.0, 5.0, 5.0)
        self._ignore_margins = False

        self._size = self._layoutsize = QtCore.QSizeF(GRID_COL_WIDTH,
                                                      GRID_ROW_HEIGHT)
        self._content_rect = QtCore.QRectF()
        self._effect: Optional[QtWidgets.QGraphicsEffect] = None

        self._content: Optional[QtWidgets.QGraphicsProxyWidget] = None
        self.setFont(self.contentFont())

        self.geometryChanged.connect(self._updateContentArea)

        self.setHasWidthForHeight(True)

    def __del__(self):
        try:
            self._label.visibleChanged.disconnect()
        except RuntimeError:
            pass

    def updateableChildren(self) -> Iterable[Graphic]:
        return list(self._tiles)

    def _onLabelVisibility(self) -> None:
        self._label_bg.setVisible(self._label.isVisible())

    @staticmethod
    def contentFont(family=FONT_FAMILY, size=MEDIUM_TEXT_SIZE,
                    weight: QtGui.QFont.Weight = None) -> QtGui.QFont:
        font = QtGui.QFont(family)
        font.setPixelSize(size)
        if weight:
            font.setWeight(weight)
        return font

    def addChild(self, tile: Tile) -> None:
        super().addChild(tile)
        self._tiles.append(tile)

    @settable()
    def setStyles(self, styles: dict[str, dict[str, Any]]) -> None:
        self._styles = styles

    def hasNamedStyle(self, name: str) -> bool:
        if name in self._styles:
            return True
        parent = self.parentTile()
        if parent:
            return parent.hasNamedStyle(name)
        else:
            return False

    def namedStyle(self, name: str) -> dict[str, Any]:
        this_style = self._styles.get(name)
        parent = self.parentTile()
        if parent:
            combined = parent.namedStyle(name)
            if combined:
                if this_style:
                    combined.update(this_style)
                return combined
        return this_style

    @settable("style")
    def setStyleName(self, stylename: str) -> None:
        parent = self.parentTile()
        if parent:
            if stylename:
                style = parent.namedStyle(stylename)
            else:
                style = parent.namedStyle("*")
            if style:
                config.updateSettables(self, style)

    @classmethod
    def fromData(cls, data: dict[str, Any], parent: Tile = None,
                 controller: config.DataController = None) -> Tile:
        tile = cls(parent=parent)
        if parent:
            parent.prepChild(tile, data)
        tile.configureFromData(data, controller)
        return tile

    # def configureFromData(self, data: dict[str, Any],
    #                       controller: config.DataController = None) -> None:
    #     super().configureFromData(data, controller)

    def __repr__(self):
        return f"<{type(self).__name__} {self.objectName()}>"

    def _baseSize(self) -> QtCore.QSizeF:
        width = height = 0.0
        ms = self.contentsMargins()
        width += ms.left() + ms.right()
        height += ms.top() + ms.bottom()
        if self.labelIsVisible() and not self.labelIsOverlayed():
            le = self.labelEdge()
            lrh = self.label().size().height()
            if le == Qt.TopEdge or le == Qt.BottomEdge:
                height += lrh
            else:
                width += lrh
        return QtCore.QSizeF(width, height)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = ...
                 ) -> QtCore.QSizeF:
        size = self._baseSize()
        if self._content and which in (Qt.MinimumSize, Qt.PreferredSize):
            cw = constraint.width()
            ch = constraint.height()
            if cw >= 0:
                constraint.setWidth(max(0.0, cw - size.width()))
            if ch >= 0:
                constraint.setHeight(max(0.0, ch - size.height()))
            csize = self._content.effectiveSizeHint(which, constraint)
            if cw >= 0:
                csize.setWidth(constraint.width())
            if ch >= 0:
                csize.setHeight(constraint.height())
            size += csize
            return size
        return constraint

    def parentTile(self) -> Optional[Tile]:
        parent = self.parentItem()
        while parent and not isinstance(parent, Tile):
            parent = parent.parentItem()
        return parent

    def labelIsOverlayed(self) -> bool:
        return self._labeloverlayed

    @settable("overlay_label")
    def setLabelOverlayed(self, overlayed: bool):
        self._labeloverlayed = overlayed
        self.updateContents()

    @settable("label_bg", argtype=QtGui.QBrush)
    def setLabelBackgroundBrush(self, brush: QtGui.QBrush):
        self.labelBackground().setFillBrush(brush)

    @settable("label_bg_role", argtype=QtGui.QPalette.ColorRole)
    def setLabelBackgroundRole(self, role: QtGui.QPalette.ColorRole):
        self.labelBackground().setFillRole(role)

    @settable(argtype=QtGui.QColor)
    def setLabelLineColor(self, color: QtGui.QColor):
        self._line_color = color

    @settable(argtype=float)
    def setLabelLineWidth(self, width: float):
        self._line_width = width

    @settable(argtype=QtGui.QPalette.ColorRole)
    def setLabelLineRole(self, role: QtGui.QPalette.ColorRole):
        self._line_role = role

    def contentsRect(self) -> QtCore.QRectF:
        if self._content_rect.isValid():
            return QtCore.QRectF(self._content_rect)
        else:
            return super().contentsRect()

    def pathElement(self, name: str) -> Optional[QtCore.QObject]:
        if name == "bg":
            return self.background()
        elif name == "label_bg":
            return self.labelBackground()
        elif name == "label":
            return self.label()
        return super().pathElement(name)

    def background(self) -> TileBackground:
        return self._bg

    def labelBackground(self) -> TileBackground:
        return self._label_bg

    def label(self) -> graphics.StringGraphic:
        return self._label

    def labelText(self) -> str:
        return self.label().plainText()

    @settable("label")
    def setLabelText(self, text: str):
        self.label().setText(text)
        if not self.labelIsVisible():
            self.setLabelVisible(True)
            self._updateContentArea()
        else:
            self.update()

    @settable()
    def setLabelSize(self, size: Union[str, int]):
        size = textSize(size)
        label = self.label()
        font = label.font()
        font.setPixelSize(size)
        label.setFont(font)
        self._updateContentArea()

    def labelIsVisible(self) -> bool:
        return self.label().isVisible()

    @settable()
    def setLabelVisible(self, visible: bool):
        self.label().setVisible(visible)
        self._updateContentArea()

    def labelEdge(self) -> Qt.Edge:
        return self._labeledge

    @settable(argtype=Qt.Edge)
    def setLabelEdge(self, edge: Qt.Edge):
        if not isinstance(edge, Qt.Edge):
            raise TypeError(edge)
        self._labeledge = edge
        self._updateContentArea()

    def contentItem(self) -> Optional[QtWidgets.QGraphicsProxyWidget]:
        return self._content

    def contentWidget(self) -> Optional[QtWidgets.QWidget]:
        item = self.contentItem()
        if isinstance(item, QtWidgets.QGraphicsProxyWidget):
            return item.widget()

    def setContentWidget(self, w: QtWidgets.QWidget, transparent: bool = True):
        if self._content is None:
            self._content = QtWidgets.QGraphicsProxyWidget(self)
        if transparent is not None:
            w.setAttribute(Qt.WA_TranslucentBackground, transparent)
        self._content.setWidget(w)

    @settable(argtype=QtGui.QColor)
    def setTint(self, tint_color: QtGui.QColor):
        self.background().setTint(tint_color)
        self.labelBackground().setTint(tint_color)

    @settable()
    def setTintAlpha(self, alpha: float):
        self._tint.setAlphaF(alpha)

    def labelBackgroundIsVisible(self) -> bool:
        return self.labelBackground().isVisible()

    def effectiveLabelBackgroundVisible(self) -> bool:
        return (self.labelBackgroundIsVisible() and
                self.labelIsVisible() and
                not self.labelIsOverlayed())

    @settable("label_bg_visible", argtype=bool)
    def setLabelBackgroundVisible(self, visible: bool):
        self.labelBackground().setVisible(visible)

    def _positionLabel(self, rect: QtCore.QRectF) -> QtCore.QRectF:
        bg = self.background()
        bg.setRect(rect)

        lms = self.labelMargins()
        edge = self.labelEdge()
        fm = QtGui.QFontMetricsF(self.label().font())
        height = fm.lineSpacing() + lms.top() + lms.bottom()
        labelrect = QtCore.QRectF(rect.topLeft(),
                                  QtCore.QSizeF(rect.width(), height))
        # Split the tile rect into "label" and "content" sub-rects
        content_rect = QtCore.QRectF(rect)
        labelrot = 0.0
        if edge == Qt.TopEdge:
            content_rect.setTop(rect.y() + height)
        elif edge == Qt.LeftEdge:
            labelrot = -90.0
            labelrect.moveTo(rect.bottomLeft())
            labelrect.setWidth(rect.height())
            content_rect.setLeft(rect.x() + height)
        elif edge == Qt.BottomEdge:
            labelrect.moveTo(QtCore.QPointF(rect.x(), rect.bottom() - height))
            content_rect.setBottom(rect.bottom() - height)
        elif edge == Qt.RightEdge:
            labelrot = 90.0
            labelrect.moveTo(rect.topRight())
            labelrect.setWidth(rect.height())
            content_rect.setRight(rect.right() - height)
        else:
            raise ValueError(edge)

        label_bg = self.labelBackground()
        label_bg.setRect(labelrect)
        label_bg.setRotation(labelrot)

        label = self.label()
        self._label.setTransformOriginPoint(0, 0)
        label.setGeometry(labelrect)
        label.setRotation(labelrot)

        # label.setGeometry(labelrect.marginsRemoved(lms))
        if self.labelIsVisible() and not self.labelIsOverlayed():
            return content_rect
        else:
            return rect

    def labelMargins(self) -> QtCore.QMarginsF:
        return self.label().margins()

    @settable(argtype=QtCore.QMarginsF)
    def setLabelMargins(self, ms: QtCore.QMarginsF) -> None:
        self.label().setMargins(ms)
        self._updateContentArea()

    def contentsMargins(self) -> QtCore.QMarginsF:
        return self._inner_margins

    def setContentsMargins(self, left: float, top: float, right: float,
                           bottom: float) -> None:
        super().setContentsMargins(left, top, right, bottom)
        self._inner_margins = QtCore.QMarginsF(left, top, right, bottom)
        self._updateContentArea()

    @settable()
    def setLeftMargin(self, left: float):
        ms = self.contentsMargins()
        self.setContentsMargins(left, ms.top(), ms.right(), ms.bottom())

    @settable()
    def setTopMargin(self, top: float):
        ms = self.contentsMargins()
        self.setContentsMargins(ms.left(), top, ms.right(), ms.bottom())

    @settable()
    def setRightMargin(self, right: float):
        ms = self.contentsMargins()
        self.setContentsMargins(ms.left(), ms.top(), right, ms.bottom())

    @settable()
    def setBottomMargin(self, bottom: float):
        ms = self.contentsMargins()
        self.setContentsMargins(ms.left(), ms.top(), ms.right(), bottom)

    @settable("margins", argtype=QtCore.QMarginsF)
    def setInnerMargins(self, ms: QtCore.QMarginsF):
        super().setContentsMargins(ms)
        self._inner_margins = ms
        self.updateContents()

    def ignoreMargins(self) -> bool:
        return self._ignore_margins

    @settable()
    def setIgnoreMargins(self, ignore: bool):
        self._ignore_margins = ignore

    def _updateContentArea(self):
        self.setTransformOriginPoint(self.rect().center())
        rect = QtCore.QRectF(QtCore.QPointF(0, 0), self.size())
        # Position the label
        crect = self._positionLabel(rect)
        # Inset the content area
        crect = crect.marginsRemoved(self.contentsMargins())

        content = self.contentItem()
        if content:
            content.setGeometry(crect)
        self._content_rect = crect
        self.updateContents()
        self.update()

    def updateContents(self):
        if self._content:
            self._ignore_content_geometry = True
            self._content.setGeometry(self.contentsRect())
            self._ignore_content_geometry = False

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange,
                   value: Any) -> Any:
        if change == QtWidgets.QGraphicsItem.ItemVisibleHasChanged and value:
            self.updateGeometry()
        return super().itemChange(change, value)

    @settable()
    def setCornerRadius(self, radius: float) -> None:
        self.background().setCornerRadius(radius)

    def _blurEffect(self) -> QtWidgets.QGraphicsBlurEffect:
        return getEffect(self, QtWidgets.QGraphicsBlurEffect)

    def _shadowEffect(self) -> QtWidgets.QGraphicsDropShadowEffect:
        return getShadowEffect(self)

    def _contentBlurEffect(self) -> QtWidgets.QGraphicsBlurEffect:
        return getEffect(self.contentItem(), QtWidgets.QGraphicsBlurEffect)

    def _contentShadowEffect(self) -> QtWidgets.QGraphicsDropShadowEffect:
        return getShadowEffect(self.contentItem())

    @settable()
    def setBlur(self, blur_radius: float):
        self._blurEffect().setBlurRadius(blur_radius)

    @settable("shadow_visible", argtype=bool)
    def setShadowEnabled(self, shadow: bool):
        self._shadowEffect().setEnabled(shadow)

    @settable(argtype=QtGui.QColor)
    def setShadowColor(self, color: QtGui.QColor):
        self._shadowEffect().setColor(color)

    @settable()
    def setShadowBlur(self, radius: float):
        self._shadowEffect().setBlurRadius(radius)

    @settable()
    def setShadowOffsetX(self, dx: float):
        self._shadowEffect().setXOffset(dx)

    @settable(argtype=QtCore.QPointF)
    def setShadowOffset(self, delta: QtCore.QPointF) -> None:
        self._shadowEffect().setOffset(delta)

    @settable()
    def setShadowOffsetY(self, dy: float):
        self._shadowEffect().setYOffset(dy)

    @settable()
    def setContentBlur(self, radius: float):
        self._contentBlurEffect().setBlurRadius(radius)

    @settable("content_shadow_visible", argtype=bool)
    def setContentShadowEnabled(self, shadow: bool):
        self._contentShadowEffect().setEnabled(shadow)

    @settable(argtype=QtGui.QColor)
    def setContentShadowColor(self, color: QtGui.QColor):
        self._contentShadowEffect().setColor(color)

    @settable()
    def setContentShadowBlur(self, radius: float):
        self._contentShadowEffect().setBlurRadius(radius)

    @settable(argtype=QtCore.QPointF)
    def setContentShadowOffset(self, delta: QtCore.QPointF) -> None:
        self._contentShadowEffect().setOffset(delta)

    @settable()
    def setContentShadowOffsetX(self, dx: float):
        self._contentShadowEffect().setXOffset(dx)

    @settable()
    def setContentShadowOffsetY(self, dy: float):
        self._contentShadowEffect().setYOffset(dy)

    def shape(self) -> QtGui.QPainterPath:
        return self.background().shape()


@graphictype("text")
class TextTile(Tile):
    _font_family = FONT_FAMILY

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._valuemap: dict[str, str] = {}
        self._formatter: Callable[[Any], str] = str
        self._content = graphics.TextGraphic(self)
        self._content.setFont(self.contentFont(self._font_family))
        self._content.setForegroundRole(styling.VALUE_ROLE)
        self._hiliter: Optional[QtGui.QSyntaxHighlighter] = None

        ms = self.contentsMargins()
        self.setContentsMargins(ms.left(), 0, ms.right(), ms.bottom())

        self.setHasHeightForWidth(True)

    def formatter(self) -> Callable[[Any], str]:
        return self._formatter

    @settable("text_align", argtype=Qt.Alignment)
    def setTextAlignment(self, align: Qt.Alignment):
        self.contentItem().setTextAlignment(align)

    @settable()
    def setTextSize(self, size: Union[str, int]):
        size = textSize(size)
        font = self.contentItem().font()
        font.setPixelSize(size)
        self.contentItem().setFont(font)

    def textSize(self) -> int:
        return self.contentItem().font().pixelSize()

    @settable(argtype=QtGui.QFont.Weight)
    def setTextWeight(self, weight: int):
        w = self.contentItem()
        font = w.font()
        font.setWeight(weight)
        w.setFont(font)

    @settable()
    def setTextFamily(self, name: str):
        if name == "monospace":
            name = graphics.MONOSPACE_FAMILY

        w = self.contentItem()
        font = w.font()
        font.setFamily(name)
        w.setFont(font)

    @settable("text_role", converter=converters.colorRoleConverter)
    def setTextColorRole(self, role: QtGui.QPalette.ColorRole):
        self.contentItem().setForegroundRole(role)

    @settable("text_color", argtype=QtGui.QColor)
    def setDefaultTextColor(self, color: QtGui.QColor) -> None:
        self._content.setForegroundColor(color)

    @settable()
    def setValueMap(self, valuemap: dict[str, str]):
        self._valuemap = valuemap

    @settable(converter=syntaxHighlighterConverter)
    def setSyntaxColoring(
            self, hiliter: Union[QtGui.QSyntaxHighlighter, type[QtGui.QSyntaxHighlighter]]):
        doc = self._content.document()
        if issubclass(hiliter, QtGui.QSyntaxHighlighter):
            hiliter = hiliter(doc)
        if not isinstance(hiliter, QtGui.QSyntaxHighlighter):
            raise TypeError(hiliter)
        self._hiliter = hiliter
        self._hiliter.setDocument(doc)

    def updateContents(self):
        rect = self.contentsRect()
        content = self.contentItem()
        if content:
            content.setGeometry(rect)

    @settable()
    def setText(self, html: str) -> None:
        self.contentItem().setHtml(str(html))
        self.updateGeometry()

    @settable()
    def setPlainText(self, text: str) -> None:
        self.contentItem().setPlainText(text)

    @settable()
    def setValue(self, value: Union[str, int, float]):
        fmtr = self.formatter()
        text = fmtr(value)
        text = self._valuemap.get(text, text)
        self.setText(text)

    @settable()
    def setTextSelectable(self, selectable: bool) -> None:
        content = self.contentItem()
        if content:
            content.setTextSelectable(selectable)

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget]=None) -> None:
    #     painter.save()
    #     painter.setPen(Qt.yellow)
    #     painter.drawRect(self.contentsRect())
    #     painter.restore()


@graphictype("number")
class NumberTile(TextTile):
    _font_family = NUMBER_FAMILY

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._formatter: formatting.NumberFormatter = \
            formatting.NumberFormatter()
        self._formatter.setBriefMode(formatting.BriefMode.auto)

    @settable(converter=converters.formatConverter)
    def setFormatter(self, formatter: formatting.NumberFormatter):
        self._formatter = formatter

    def formatter(self) -> formatting.NumberFormatter:
        return self._formatter

    @settable("digits", argtype=int)
    def setAvailableDigits(self, digits: int):
        self.formatter().setAvailableDigits(digits)

    @settable(argtype=int)
    def setDecimalPlaces(self, places: int):
        self.formatter().setDecimalPlaces(places)

    @settable("brief")
    def setBriefMode(self, brief: formatting.BriefMode):
        self.formatter().setBriefMode(brief)

    @settable()
    def setValue(self, value: Union[str, int, float, None]):
        if value is None:
            self.setText("")
            return
        if isinstance(value, str):
            value = float(value)
        fmt = self.formatter()
        if not isinstance(value, (str, int, float)):
            raise ValueError(f"{self}: {value!r} is not a number")
        fmtnum = fmt.formatNumber(value)
        self.setText(fmtnum.html())


@graphictype("tuple")
class TupleTile(TextTile):
    _font_family = NUMBER_FAMILY

    def __init__(self, parent: QtWidgets.QGraphicsWidget = None):
        self._items: list[graphics.StringGraphic] = []
        super().__init__(parent)
        self._formatter = formatting.NumberFormatter()
        self._gap = 5.0
        self.setLength(3)
        self.setTextFamily(self._font_family)

    @settable("text_align", argtype=Qt.Alignment)
    def setTextAlignment(self, align: Qt.Alignment):
        for item in self._items:
            item.setTextAlignment(align)

    @settable()
    def setTextSize(self, size: Union[str, int]):
        size = textSize(size)
        font = self.contentItem().font()
        font.setPixelSize(size)
        for item in self._items:
            item.setFont(font)

    @settable(argtype=QtGui.QFont.Weight)
    def setTextWeight(self, weight: int):
        font = QtGui.QFont()
        font.setWeight(weight)
        for item in self._items:
            item.setFont(font)

    @settable()
    def setTextFamily(self, name: str):
        font = QtGui.QFont()
        font.setFamily(name)
        for item in self._items:
            item.setFont(font)

    @settable("color_role", converter=converters.colorRoleConverter)
    def setTextColorRole(self, role: QtGui.QPalette.ColorRole):
        for item in self._items:
            item.setForegroundRole(role)

    @settable("text_color", argtype=QtGui.QColor)
    def setDefaultTextColor(self, color: QtGui.QColor) -> None:
        for item in self._items:
            item.setForegroundColor(color)

    @settable(argtype=int)
    def setLength(self, length: int) -> None:
        self._items = [graphics.TextGraphic(self) for _ in range(length)]
        self.updateGeometry()

    @settable(converter=converters.formatConverter)
    def setFormatter(self, formatter: formatting.NumberFormatter):
        self._formatter = formatter
        for item in self._items:
            item.setFormatter(self._formatter)

    def formatter(self) -> formatting.NumberFormatter:
        return self._formatter

    @settable("digits", argtype=int)
    def setAvailableDigits(self, digits: int):
        self.formatter().setAvailableDigits(digits)

    @settable(argtype=int)
    def setDecimalPlaces(self, places: int):
        self.formatter().setDecimalPlaces(places)

    @settable("brief")
    def setBriefMode(self, brief: formatting.BriefMode):
        self.formatter().setBriefMode(brief)

    def clearText(self) -> None:
        for item in self._items:
            item.setPlainText("")

    @settable()
    def setValue(self, values: Union[list, tuple, str, None]):
        if values is None or values == "":
            self.clearText()
            return
        if isinstance(values, str):
            values = [float(v) for v
                      in values.lstrip("[").rstrip("]").split(",")]
        if not isinstance(values, (list, tuple)):
            raise ValueError(values)

        fmtr = self.formatter()
        for i, value in enumerate(values):
            fn = fmtr.formatNumber(value)
            self._items[i].setHtml(fn.html())

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = ...
                 ) -> QtCore.QSizeF:
        size = QtCore.QSizeF(-1, -1)
        if which in (Qt.MinimumSize, Qt.PreferredSize) and self._items:
            space = self._gap * (len(self._items) - 1)
            base_size = self._baseSize()
            cw = -1
            if constraint.width() >= base_size.width() + space:
                cw = (constraint.width() - base_size.width() - space) / 3
            item_sizes = [it.effectiveSizeHint(which, QtCore.QSizeF(cw, -1))
                          for it in self._items]
            w = sum(sz.width() for sz in item_sizes) + space
            h = max(sz.height() for sz in item_sizes)
            size = QtCore.QSizeF(base_size.width() + w, base_size.height() + h)
        return size

    def updateContents(self):
        rect = self.contentsRect()
        count = len(self._items)
        if not count:
            return
        avail = rect.width() - (self._gap * (count - 1))
        item_width = avail / len(self._items)
        for i, item in enumerate(self._items):
            x = rect.x() + (item_width + self._gap) * i
            irect = QtCore.QRectF(x, rect.y(), item_width, rect.height())
            item.setGeometry(irect)


@graphictype("path")
class PathTile(TextTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._weight: Union[str, int] = 700

    @settable()
    def setFilenameWeight(self, weight: Union[str, int]):
        self._weight = weight

    @settable()
    def setValue(self, text: str):
        text = self._valuemap.get(text, text)
        self.setText(formatting.markup_path(text, filename_weight=self._weight))


@graphictype("size")
class SizeTile(TextTile):
    _font_family = NUMBER_FAMILY

    @settable()
    def setValue(self, value: Sequence[Union[int, float]]):
        text = "\xd7".join(f"<b>{dim}</b>" for dim in value)
        super().setText(text)


@graphictype("datetime")
class DateTimeTile(TextTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._parse_string = "%d %b %Y %I:%M %p"
        self._html_format = "%I:%M %p<br><small>%d %b %Y</small>"
        self._dt = datetime.now()
        self._last_string = ""

    @settable()
    def setParseString(self, parse_string: str) -> None:
        self._parse_string = parse_string
        self._reparse()

    @settable()
    def setFormatString(self, format_string: str) -> None:
        self._html_format = format_string
        self._reformat()

    def _reparse(self) -> None:
        self._dt = datetime.strptime(self._last_string, self._parse_string)
        self._reformat()

    def _reformat(self) -> None:
        if self._dt is None:
            html = ""
        else:
            html = self._dt.strftime(self._html_format)
        self.setText(html)

    @settable()
    def setValue(self, value: Union[str, datetime, None]) -> None:
        if isinstance(value, str):
            self._last_string = value
            value = datetime.strptime(value, self._parse_string)
        if not isinstance(value, datetime) and value is not None:
            raise ValueError(value)
        self._dt = value
        self._reformat()


@graphictype("marquee")
class MarqueeTile(Tile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._content = graphics.MarqueeGraphic(self)

    @settable()
    def setText(self, text: str) -> None:
        self._content.setText(text)

    @settable()
    def setValue(self, text: str) -> None:
        self.setText(text)


class ContainerTile(Tile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._drawbg = False
        self._itemstyle: Optional[str] = None
        self.background().setVisible(False)
        self.setLabelVisible(False)
        self.setIgnoreMargins(True)

    def prepChild(self, child: Graphic, data: dict[str, Any]) -> None:
        if self._itemstyle and "style" not in data:
            data["style"] = self._itemstyle
        super().prepChild(child, data)

    @settable()
    def setItemStyle(self, style_name: str):
        self._itemstyle = style_name


class LayoutTile(ContainerTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._content = graphics.LayoutGraphic(self)
        layout = self._makeLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self._content.setLayout(layout)
        self.setHasHeightForWidth(True)

    def _makeLayout(self) -> QtWidgets.QGraphicsLayout:
        raise NotImplementedError

    def addChild(self, item: QtWidgets.QGraphicsLayoutItem):
        self._content.addChild(item)
        self._tiles.append(item)

    def contentLayout(self) -> QtWidgets.QGraphicsLayout:
        return self._content.layout()

    def contentArrangement(self) -> layouts.Arrangement:
        layout = self.contentLayout()
        if isinstance(layout, layouts.ArrangementLayout):
            return layout.arrangement()

    def pathElement(self, name: str) -> Optional[QtCore.QObject]:
        if name == "layout":
            return self.contentLayout()
        return super().pathElement(name)

    @settable("margins", argtype=QtCore.QMarginsF)
    def setMargins(self, left: Union[QtCore.QMarginsF, float], top=0.0,
                   right=0.0, bottom=0.0) -> None:
        super().setContentsMargins(left, top, right, bottom)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = ...
                 ) -> QtCore.QSizeF:
        basesize = self._baseSize()
        if constraint and constraint.width() >= 0:
            cw = constraint.width()
            ch = constraint.height()
            if cw >= 0:
                constraint.setWidth(max(0.0, cw - basesize.width()))

            if ch >= 0:
                constraint.setHeight(max(0.0, ch - basesize.height()))

            layout = self.contentLayout()
            hint = layout.sizeHint(which, constraint)
            return basesize + hint
        else:
            return super().sizeHint(which, constraint)


@graphictype("line")
class LinearLayoutTile(LayoutTile):
    default_orientation = Qt.Vertical

    def _makeLayout(self) -> QtWidgets.QGraphicsLayout:
        arrangement = layouts.LinearArrangement()
        arrangement.setMargins(0, 0, 0, 0)
        return layouts.ArrangementLayout(arrangement)
        # return QtWidgets.QGraphicsLinearLayout(self.default_orientation)

    @settable(argtype=Qt.Orientation)
    def setOrientation(self, orient: Qt.Orientation) -> None:
        # self.contentLayout().setOrientation(orient)
        self.contentArrangement().setOrientation(orient)

    @settable("spacing")
    def setSpacing(self, spacing: float) -> None:
        # self.contentLayout().setSpacing(spacing)
        self.contentArrangement().setSpacing(spacing)

    @settable("line:stretch")
    def setChildStretch(self, tile: Tile, factor: int) -> None:
        # self.contentLayout().setStretchFactor(tile, factor)
        self.contentArrangement().setStretchFactor(tile, factor)


@graphictype("matrix")
class MatrixTile(LayoutTile):
    property_aliases = {
        "h_space": "matrix.h_space",
        "v_space": "matrix.v_space",
        "spacing": "matrix.spacing",
        "min_column_width": "matrix.min_column_width",
        "max_column_width": "matrix.max_column_width",
        "row_height": "matrix.row_height",
        "orientation": "matrix.orientation",
    }

    def _makeLayout(self) -> QtWidgets.QGraphicsLayout:
        arrangement = layouts.Matrix()
        return layouts.ArrangementLayout(arrangement)

    def pathElement(self, name: str) -> Optional[QtCore.QObject]:
        if name == "matrix":
            return self.contentArrangement()
        return super().pathElement(name)


@graphictype("flow")
class FlowTile(LayoutTile):
    property_aliases = {
        "item_space": "flow.item_space",
        "line_space": "flow.line_space",
        "spacing": "flow.spacing",
        "orientation": "flow.orientation",
        "justify": "flow.justify",
        "item_align": "flow.item_align",
        "content_justify": "flow.content_justify",
        "min_item_length": "flow.min_item_length"
    }

    def _makeLayout(self) -> QtWidgets.QGraphicsLayout:
        arrangment = layouts.FlowArrangement()
        arrangment.setSpacing(10.0)
        return layouts.ArrangementLayout(arrangment)

    def pathElement(self, name: str) -> Optional[QtCore.QObject]:
        if name == "flow":
            return self.contentArrangement()
        return super().pathElement(name)


@graphictype("grid")
class GridTile(LayoutTile):
    property_aliases = {
        "orientation": "grid.orientation",
        "dense": "grid.dense",
        "cell_size": "grid.cell_size",
        "col_width": "grid.col_width",
        "row_height": "grid.row_height",
        "h_space": "grid.h_space",
        "v_space": "grid.v_space",
        "spacing": "grid.spacing",
        "stretch": "grid.stretch",
    }

    def __init__(self, parent: QtWidgets.QGraphicsItem):
        self._max_span = QtCore.QSize(-1, -1)
        super().__init__(parent)

    def _makeLayout(self) -> QtWidgets.QGraphicsLayout:
        arrangement = layouts.PackedGridArrangement()
        return layouts.ArrangementLayout(arrangement)

    def pathElement(self, name: str) -> Optional[QtCore.QObject]:
        if name == "grid":
            return self.contentArrangement()
        return super().pathElement(name)

    @settable("max_cols", argtype=int)
    def setMaximumColumns(self, cols: int):
        self._max_span.setWidth(cols)
        self.updateGeometry()

    @settable("max_rows", argtype=int)
    def setMaximumRows(self, rows: int):
        self._max_span.setHeight(rows)
        self.updateGeometry()

    @settable("grid:pos", argtype=QtCore.QPoint)
    def setChildPos(self, tile: Tile, pos: QtCore.QPoint) -> None:
        self.contentArrangement().setItemPos(tile, pos)

    @settable("grid:cols", argtype=int)
    def setChildColumnSpan(self, tile: Tile, cols: int) -> None:
        self.contentArrangement().setItemColumnSpan(tile, cols)

    @settable("grid:rows", argtype=int)
    def setChildRowSpan(self, tile: Tile, rows: int) -> None:
        self.contentArrangement().setItemRowSpan(tile, rows)

    @settable("grid:spans", argtype=QtCore.QSize)
    def setChildSpans(self, tile: Tile, spans: QtCore.QSize) -> None:
        self.contentArrangement().setItemSpans(tile, spans)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = ...
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        base = self._baseSize()
        layout = self.contentLayout()

        if which == Qt.MinimumSize:
            cellsize = layout.cellSize()
            return QtCore.QSizeF(cellsize.width() + base.width(),
                                 cellsize.height() + base.height())

        size = super().sizeHint(which, constraint)
        mx = layout.spanSize(self._max_span)
        mxw = mx.width() + base.width()
        mxh = mx.height() + base.height()
        if which == Qt.PreferredSize:
            if mx.width() > 0 and mxw < size.width():
                size.setWidth(mxw)
            if mx.height() > 0 and mxh < size.height():
                size.setHeight(mxh)
        elif which == Qt.MaximumSize:
            if mx.width() > 0:
                size.setWidth(mxw)
            if mx.height() > 0:
                size.setHeight(mxh)
        return size


class DataLayoutTile(ContainerTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._content = views.DataLayoutGraphic(self)
        self._content.setArrangement(self._makeArrangement())

    def _makeArrangement(self) -> layouts.Arrangement:
        raise NotImplementedError

    def contentArrangement(self) -> layouts.Arrangement:
        return self._content.arrangement()

    def dataProxy(self) -> Optional[Graphic]:
        return self._content

    def pathElement(self, name: str) -> Optional[QtCore.QObject]:
        if name == "layout":
            return self.contentArrangement()
        return super().pathElement(name)


@graphictype("data_matrix")
class DataMatrixTile(DataLayoutTile):
    property_aliases = {
        "h_space": "layout.h_space",
        "v_space": "layout.v_space",
        "spacing": "layout.spacing",
        "margins": "layout.margins",
        "min_column_width": "layout.min_column_width",
        "max_column_width": "layout.max_column_width",
        "row_height": "layout.row_height",
        "orientation": "layout.orientation",
    }

    def _makeArrangement(self) -> layouts.Arrangement:
        arrangement = layouts.Matrix()
        return arrangement


@graphictype("choice")
class ChoiceTile(ContainerTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)

    @settable()
    def setCurrentName(self, name: str):
        if not isinstance(name, str) or not name:
            raise ValueError(f"Name expression evaluated to {name!r}")
        for i, child in enumerate(self.childGraphics()):
            if child.objectName() == name:
                self.setShowIndex(i)
                break
        else:
            self.updateGeometry()

    @settable()
    def setCurrentIndex(self, index: int):
        if not isinstance(index, int):
            raise ValueError(f"Index expression evaluated to {index}")
        for i, child in enumerate(self.childGraphics()):
            if i == index:
                self._content = child
            child.setVisible(i == index)
        self.updateGeometry()


@graphictype("list")
class ListTile(Tile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._view = views.ListView(self)
        self._content = self._view

        self._hide_when_empty = False
        self._visible = True

        self.setHasHeightForWidth(True)

        # self._view.contentSizeChanged.connect(self._onContentResize)

    def updateContents(self):
        if self._content:
            self._ignore_content_geometry = True
            self._content.setGeometry(self.contentsRect())
            self._ignore_content_geometry = False

    def dataProxy(self) -> Optional[graphics.Graphic]:
        return self._view

    def extraVariables(self) -> dict[str, Any]:
        return self._view.extraVariables()

    def pathElement(self, name: str) -> Optional[QtCore.QObject]:
        if name == "contents":
            return self._view.contentsItem()
        elif name == "matrix":
            return self._view.contentsItem().matrix()
        return super().pathElement(name)

    def _onContentResize(self) -> None:
        self.prepareGeometryChange()
        current_size = self.size()
        base_size = self._baseSize()
        width = self.contentsRect().width()
        content_height = self._view.heightForWidth(width)
        self.resize(current_size.width(), base_size.height() + content_height)

    @settable()
    def setSectionKey(self, col_id: int|str) -> None:
        self._view.setSectionKey(col_id)

    @settable()
    def setVisible(self, visible: bool) -> None:
        self._visible = visible
        if self._hide_when_empty:
            visible = visible and self._view.rowCount()
        super().setVisible(visible)

    @settable()
    def setHideWhenEmpty(self, hide_when_empty: bool):
        self._hide_when_empty = hide_when_empty
        self._updateVisibility()

    @settable("h_spacing")
    def setHorizontalSpacing(self, hspace: float):
        self._view.setHorizontalSpacing(hspace)
        self.updateGeometry()

    @settable("v_spacing")
    def setVerticalSpacing(self, vspace: float):
        self._view.setVerticalSpacing(vspace)
        self.updateGeometry()

    @settable()
    def setSpacing(self, space: float):
        self._view.setSpacing(space)
        self.updateGeometry()

    def _updateVisibility(self) -> None:
        if self._visible and self._hide_when_empty:
            super().setVisible(bool(self._view.rowCount()))


@graphictype("chart")
class ChartTile(Tile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._autotext = False
        self._formatter = formatting.NumberFormatter()
        self._model = models.ChartTableModel()

    def chart(self) -> Optional[charts.Chart]:
        return self.contentWidget()

    @settable(converter=converters.chartConverter)
    def setChart(self, chart: charts.Chart):
        chart.setModel(self._model)
        self.setContentWidget(chart)
        self.updateContents()

    def formatter(self) -> formatting.NumberFormatter:
        return self._formatter

    @settable(converter=converters.formatConverter)
    def setFormatter(self, formatter: formatting.NumberFormatter):
        self._formatter = formatter

    def autoText(self):
        return self._autotext

    @settable()
    def setAutoText(self, auto: bool):
        self._autotext = auto

    @settable()
    def setText(self, text: str):
        chart = self.chart()
        if chart:
            chart.setText(text)

    @settable()
    def setNumber(self, num: float):
        formatted_num = self.formatter().formatNumber(num)
        self.chart().setText(formatted_num.html())

    # def setChartColorPolicy(self, policy: styling.ColorPolicy):
    #     self.contentWidget().setColorPolicy(policy)

    @settable()
    def setMonochrome(self, mono: bool) -> None:
        self.chart().setMonochrome(mono)

    @settable()
    def setValue(self, vs: Union[Sequence[Union[float, int]], int, float]):
        if isinstance(vs, (float, int)) and self.autoText():
            self.setNumber(vs)
        if not isinstance(vs, (tuple, list)):
            vs = [vs]
        self.setValues(vs)

    @settable()
    def setValues(self, values: Sequence[float]):
        if isinstance(values, (int, float)):
            values = [values]
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"Not a list: {values}")
        self._model.setValues(values)

    @settable()
    def setTotal(self, total: float):
        self.chart().setTotal(total)

    def updateContents(self):
        content = self.contentItem()
        if not content:
            return
        rect = self.contentsRect()
        content.setGeometry(rect)


@graphictype("duration")
class DurationTile(NumberTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._elapsed = 0.0
        self._formatter = formatting.DurationFormatter(decimal_places=0,
                                                       long=True)

    def formatter(self) -> formatting.DurationFormatter:
        return self._formatter

    @settable()
    def setValue(self, value: Union[str, int, float, None]):
        if isinstance(value, (float, int)):
            self._elapsed = value
        super().setValue(value)

    @settable("long")
    def setLongFormat(self, long: bool):
        self.formatter().setUseLongFormat(long)
        self.setValue(self._elapsed)


@graphictype("est_remaining")
class EstimatedRemainingTile(DurationTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._elapsed = 0.0
        self._fraction = 0.5

        formatter = formatting.DurationFormatter(decimal_places=0, long=True)
        self.setFormatter(formatter)

    @settable("percent_complete")
    def setPercentComplete(self, percent: float):
        if percent is None:
            return
        if not isinstance(percent, (int, float)):
            raise ValueError(f"Percent is not a number: {percent}")
        self.setFractionComplete(percent / 100.0)

    def fractionComplete(self) -> float:
        return self._fraction

    @settable("fraction_complete")
    def setFractionComplete(self, fraction: float):
        if not isinstance(fraction, (int, float)):
            raise ValueError(f"Fraction is not a number: {fraction}")
        self._fraction = fraction
        self._recalc()

    def elapsedSeconds(self) -> float:
        return self._elapsed

    @settable("elapsed")
    def setElapsedSeconds(self, seconds: float):
        if not isinstance(seconds, (int, float)):
            raise ValueError(f"Seconds is not a number: {seconds}")
        self._elapsed = seconds
        self._recalc()

    def _recalc(self):
        elapsed = self.elapsedSeconds()
        fraction = self.fractionComplete()
        if fraction:
            fmtr = self.formatter()
            text = fmtr(elapsed / fraction - elapsed)
        else:
            text = "?"
        self.setText(text)


class ChartSwitchTile(Tile):
    def __init__(self, parent: QtWidgets.QGraphicsWidget = None):
        super().__init__(parent=parent)
        self._setupModel()
        self._chart = self._setupChart()
        self._chartitem = graphics.makeProxyItem(self, self._chart)
        self._chartsize = 48.0
        self._space = 10.0
        self._breakwidth = -1

        sp = self.sizePolicy()
        sp.setHorizontalPolicy(sp.MinimumExpanding)
        sp.setVerticalPolicy(sp.Fixed)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

        self.setAcceptHoverEvents(True)

    def _setupModel(self):
        pass

    def _setupChart(self) -> charts.Chart:
        chart = charts.StackedDonutChart()
        # chart.setDrawFrame(True)
        chart.setInteractive(True)
        chart.setNormalization(models.FractionOfSum())
        chart.setPenWidth(0.125)
        chart.setPenCapStyle(Qt.FlatCap)
        chart.setTrackVisible(True)
        chart.label().setFont(self.contentFont(NUMBER_FAMILY))

        return chart

    @settable()
    def setChartStartAngle(self, degrees: float):
        self.chart().setStartAngle(degrees)

    @settable()
    def setChartGapAngle(self, degrees: float):
        self.chart().setGapAngle(degrees)

    @settable()
    def setChartClockwise(self, clockwise: bool):
        self.chart().setClockwise(clockwise)

    @settable(argtype=bool)
    def setChartInteractive(self, interactive: bool):
        self.chart().setInteractive(interactive)

    def chart(self) -> charts.StackedDonutChart:
        return self._chart

    def chartSize(self) -> float:
        return self._chartsize

    def setChartSize(self, extent: float):
        self._chartsize = extent

    @settable()
    def setBreakWidth(self, width: float):
        self._breakwidth = width

    def breakWidth(self) -> float:
        if self._breakwidth > 0:
            return self._breakwidth
        else:
            return self.chartSize() * 3

    def _vertical(self, width: float) -> bool:
        return width < self.breakWidth()

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = ...
                 ) -> QtCore.QSizeF:
        size = self._baseSize()
        content_item = self.contentItem()
        chart_item = self.chartItem()
        if chart_item.isVisible():
            chart_extent = self.chartSize()
        else:
            chart_extent = 0.0

        if constraint.width() >= 0 and content_item:
            constraint_width = constraint.width() - size.width() - self._space
            vert = self._vertical(constraint_width)
            if vert:
                content_size = content_item.sizeHint(
                    Qt.PreferredSize, QtCore.QSizeF(constraint_width, -1)
                )
                total_size = QtCore.QSizeF(
                    content_size.width(),
                    chart_extent + self._space + content_size.height()
                )
            else:
                content_size = content_item.sizeHint(
                    Qt.PreferredSize,
                    QtCore.QSizeF(constraint_width - chart_extent, -1)
                )
                total_size = QtCore.QSizeF(
                    chart_extent + self._space + content_size.width(),
                    max(chart_extent, content_size.height())
                )
            size += total_size
        else:
            size = constraint
        return size

    def chartItem(self) -> QtWidgets.QGraphicsProxyWidget:
        return self._chartitem

    @settable()
    def setChartVisible(self, visible: bool):
        self.chartItem().setVisible(visible)

    def hideChart(self):
        self.setChartVisible(False)

    def showChart(self):
        self.setChartVisible(True)

    @settable()
    def setChartSize(self, size: int):
        self.prepareGeometryChange()
        self.chart().setFixedSize(size, size)
        self.updateGeometry()

    @settable()
    def setChartText(self, text: str):
        self.chart().setText(str(text))

    @settable()
    def setChartTextSize(self, size: int):
        self.chart().setTextSize(size)

    @settable()
    def setChartValue(self, value: float):
        self.chart().setValue(value)

    @settable()
    def setChartTotal(self, total: float):
        self.chart().setTotal(total)

    @settable(argtype=QtGui.QPalette.ColorRole)
    def setChartColorRole(self, role: QtGui.QPalette.ColorRole):
        self.chart().setColorRole(role)

    def updateContents(self):
        rect = self.contentsRect()
        ci = self.chartItem()
        ce = self.chartSize() if ci.isVisible() else 0.0
        cg = ce + self._space if ci.isVisible() else 0.0
        vert = self._vertical(rect.width())
        if vert:
            cr = QtCore.QRectF(rect.topLeft(), QtCore.QSizeF(rect.width(), ce))
            tr = QtCore.QRectF(rect.x(), rect.y() + cg,
                               rect.width(), rect.height() - cg)
        else:
            cr = QtCore.QRectF(rect.topLeft(), QtCore.QSizeF(ce, ce))
            tr = QtCore.QRectF(rect.x() + cg, rect.y(),
                               rect.width() - cg, rect.height())
        ci.setGeometry(cr)
        if self._content:
            self._content.setGeometry(tr)


# @graphictype("table")
# class TableTile(Tile):
#     def __init__(self, parent: QtWidgets.QGraphicsWidget = None):
#         super().__init__(parent)
#         self._proxy = TileTableProxy()
#         self._view = QtWidgets.QTableView()
#         self._view.setModel(self._proxy)
#         self._content = makeProxyItem(self, self._view)
#
#     @settable()
#     def setColumnNames(self, names: Sequence[str]) -> None:
#         self._proxy.setColumnNames(names)
#
#     def tableModel(self) -> QtCore.QAbstractTableModel:
#         return self._proxy.sourceModel()
#
#     def setTableModel(self, model: QtCore.QAbstractTableModel):
#         self._proxy.setSourceModel(model)
#
#     def updateContents(self):
#         rect = self.contentsRect()
#         self._content.setGeometry(rect)


@graphictype("side_chart")
class SideChartTile(ChartSwitchTile):
    def __init__(self, parent: QtWidgets.QGraphicsWidget = None):
        super().__init__(parent)
        self.chart().setInteractive(False)

    def addChild(self, tile: Tile):
        super().addChild(tile)
        self._content = tile
        self.updateGeometry()


@graphictype("chart_table")
class ChartTableTile(ChartSwitchTile):
    def __init__(self, parent: QtWidgets.QGraphicsWidget = None):
        super().__init__(parent=parent)
        self._hide_when_empty = False
        self._sorting = False
        self._sortcol = 0
        self._sortdir = Qt.AscendingOrder
        self._value_key = None
        self._content = self._setupContent()

        chart = self.chart()
        content = self.contentItem()
        chart.rowHighlighted.connect(content.setHighlightedRow)
        content.rowHighlighted.connect(chart.setHighlightedRow)

    def _setupContent(self) -> QtWidgets.QGraphicsWidget:
        content = models.ChartTableGraphicWidget(self)
        content.setFont(self.contentFont())
        content.setDecimalPlaces(1)
        content.setModel(self._proxy)
        return content

    def _setupChart(self) -> charts.Chart:
        chart = super()._setupChart()
        chart.setModel(self._proxy)
        return chart

    def _setupModel(self):
        return
        self._source = models.ChartTableModel()
        self._proxy = models.ChartTableSortFilterModel()
        self._proxy.setSourceModel(self._source)

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.save()
    #     painter.setPen(Qt.red)
    #     painter.drawRect(self._content.geometry())
    #     painter.restore()

    @settable()
    def setHideWhenEmpty(self, hide_when_empty: bool):
        self._hide_when_empty = hide_when_empty

    def breakWidth(self) -> float:
        bw = self.chartSize()
        if self._content:
            bw += self._content.minimumColumnWidth()
        return bw

    @settable("min_column_width")
    def setMinimumColumnWidth(self, width: float) -> None:
        table: models.ChartTableGraphicWidget = self._content
        table.setMinimumColumnWidth(width)

    @settable("max_column_width")
    def setMaximumColumnWidth(self, width: float) -> None:
        table: models.ChartTableGraphicWidget = self._content
        table.setMaximumColumnWidth(width)

    @settable()
    def setRowHeight(self, height: float) -> None:
        table: models.ChartTableGraphicWidget = self._content
        table.setRowHeight(height)

    @settable()
    def setColumnGap(self, gap: float) -> None:
        table: models.ChartTableGraphicWidget = self._content
        table.setColumnGap(gap)

    @settable(argtype=bool)
    def setItemDecorationsVisible(self, visible: bool):
        table: models.ChartTableGraphicWidget = self._content
        table.setItemDecorationsVisible(visible)

    @settable()
    def setValueKey(self, key: str):
        self._value_key = key

    def formatter(self) -> formatting.NumberFormatter:
        return self._content.formatter()

    @settable(converter=converters.formatConverter)
    def setFormatter(self, formatter: formatting.NumberFormatter):
        table: models.ChartTableGraphicWidget = self._content
        table.setFormatter(formatter)

    @settable()
    def setDecimalPlaces(self, places: int) -> None:
        table: models.ChartTableGraphicWidget = self._content
        table.formatter().setDecimalPlaces(places)

    def setModel(self, model: models.ChartTableModel):
        table: models.ChartTableGraphicWidget = self._content
        self._source = model
        self._proxy.setSourceModel(self._source)
        self._chart.setModel(self._proxy)
        table.setModel(self._proxy)

    def model(self) -> models.ChartTableModel:
        return self._proxy

    def sortEnabled(self) -> bool:
        return self._sorting

    @settable("sorted")
    def setSortEnabled(self, sort: bool):
        self._sorting = sort

    @settable()
    def setKeyOrder(self, keys: Sequence[str]):
        self._source.setKeyOrder(keys)

    @settable()
    def setIncludeKeys(self, keys: Collection[str]):
        if isinstance(keys, str):
            keys = (keys,)
        self._source.setIncludeKeys(keys)

    @settable()
    def setExcludeKeys(self, keys: Collection[str]):
        if isinstance(keys, str):
            keys = (keys,)
        self._source.setExcludeKeys(keys)

    @settable()
    def setKeyLabelMap(self, mapping: Mapping[str, str]):
        self._source.setKeyLabelMap(mapping)

    @settable("rows")
    def setRowsFromData(self, rows: models.DataSource):
        rows = models.conditionChartData(
            rows, value_key=self._value_key
        )
        self._source.setValues(rows)
        self._resort()
        self._chart.repaint()
        if self._hide_when_empty:
            self.setVisible(
                rows and (self.showingZero() or any(v for k, v in rows))
            )

    @settable()
    def setTotal(self, total: float):
        self._chart.setTotal(total)

    def showingZero(self) -> bool:
        return self._proxy.showingZero()

    @settable()
    def setShowZero(self, show: bool):
        self._proxy.setShowZero(show)

    @settable()
    def setSortColumn(self, column: int):
        self._sortcol = column
        self._resort()

    def setSortRole(self, role: int):
        self._proxy.setSortRole(role)
        self._resort()

    @settable()
    def setReversed(self, reverse: bool):
        order = Qt.DescendingOrder if reverse else Qt.AscendingOrder
        self.setSortOrder(order)

    def setSortOrder(self, direction: Qt.SortOrder):
        self._sortdir = direction
        self._resort()

    def _resort(self):
        if self._sorting:
            self._proxy.sort(self._sortcol, self._sortdir)


@graphictype("xpu_devices")
class XpuDeviceTile(ChartTableTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)

    def _setupContent(self) -> QtWidgets.QGraphicsWidget:
        content = models.XpuDeviceGraphicsWidget(self)
        content.setFont(self.contentFont())
        content.setModel(self._model)
        return content

    def _setupModel(self):
        self._model = models.XpuDeviceModel()

    def _setupChart(self) -> charts.Chart:
        chart = charts.StackedDonutChart()
        chart.setAngleAndGap(90.0, 0.0)
        chart.setInteractive(False)
        chart.setNormalization(models.FractionOfSum())
        chart.setPenWidth(0.125)
        chart.setPenCapStyle(Qt.FlatCap)
        chart.setTrackVisible(False)
        chart.setModel(self._model)
        return chart

    def breakWidth(self) -> float:
        return 200.0

    @settable("rows")
    def setRowsFromData(self, rows: list[dict[str, Any]]) -> None:
        self._model.setFromData(rows)
        self.updateContents()

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = ...
                 ) -> QtCore.QSizeF:
        s = super().sizeHint(which, constraint)
        return s

    # def setGeometry(self, rect: QtCore.QRectF) -> None:
    #     super().setGeometry(rect)


class ImageTile(Tile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._colorize: Optional[QtWidgets.QGraphicsColorizeEffect] = None

    def _tintEffect(self) -> Optional[QtWidgets.QGraphicsColorizeEffect]:
        item = self.contentItem()
        if not self._colorize:
            self._colorize = QtWidgets.QGraphicsColorizeEffect(self)
        if item:
            item.setGraphicsEffect(self._colorize)
        return self._colorize

    @settable(argtype=bool)
    def setTintEnabled(self, tinted: bool):
        self._tintEffect().setEnabled(tinted)

    @settable(argtype=QtGui.QColor)
    def setTintColor(self, color: QtGui.QColor):
        self._tintEffect().setColor(color)

    @settable()
    def setTintAmount(self, strength: float):
        self._tintEffect().setStrength(strength)


@graphictype("logo")
class LogoTile(ImageTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        self._path: Optional[pathlib.Path] = None
        super().__init__(parent=parent)
        self._pixmap: Optional[QtGui.QPixmap] = None
        self._imagesize = QtCore.QSize(256, 256)
        self._alignment = Qt.AlignCenter
        self._stretch = False

    def setPixmap(self, pixmap: QtGui.QPixmap) -> None:
        self._pixmap = pixmap
        self.reload()

    @settable("stretch")
    def setStretchToFill(self, stretch: bool):
        self._stretch = stretch
        self.update()

    @settable(argtype=Qt.Alignment)
    def setAlignment(self, align: Qt.Alignment):
        self._alignment = align
        self.update()

    @settable()
    def setImagePath(self, filepath: Union[str, pathlib.Path]):
        self._path = toPath(filepath)
        self.reload()

    @settable(argtype=QtCore.QSize)
    def setImageSize(self, size: QtCore.QSize):
        self._imagesize = size
        self.reload()

    def reload(self):
        path = self._path
        if path and path.exists():
            self._pixmap = loadImage(path, self._imagesize)
            self.update()

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        rect = self.rect()
        pixmap = self._pixmap
        size = pixmap.size()
        resizing = (rect.width() < size.width() or
                    rect.height() < size.height() or
                    (
                        self._stretch and
                        rect.width() > size.width() and
                        rect.height() > size.height()
                    ))
        if resizing:
            if rect.width() < rect.height():
                pixmap = pixmap.scaledToWidth(int(rect.width()))
            else:
                pixmap = pixmap.scaledToHeight(int(rect.height()))
            size = pixmap.size()

        if size.width() < rect.width() or size.height() < rect.height():
            rect = styling.alignedRectF(self.layoutDirection(), self._alignment,
                                        size, rect)
        painter.drawPixmap(rect.topLeft(), pixmap)


@graphictype("logo_text")
class LogoTextTile(ImageTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._imagepath: Optional[pathlib.Path] = None
        self._gap = 10.0
        self._imagealign = Qt.AlignLeft | Qt.AlignVCenter

        self._logo_widget = QtWidgets.QLabel()
        self._logo_item = graphics.makeProxyItem(self, self._logo_widget)
        self._text_item = graphics.TextGraphic(self)
        self._text_item.setFont(self.contentFont())

        self._text_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    @settable()
    def setText(self, html: str) -> None:
        self._text_item.setHtml(html)

    @settable()
    def setTextSize(self, size: Union[str, int]):
        size = textSize(size)
        font = self._text_item.font()
        font.setPixelSize(size)
        self._text_item.setFont(font)

    @settable("text_align", argtype=Qt.Alignment)
    def setTextAlignment(self, align: Qt.Alignment):
        self._text_item.setTextAlignment(align)

    @settable()
    def setImagePath(self, filepath: Union[str, pathlib.Path]):
        self._imagepath = toPath(filepath)
        self.reload()

    @settable(argtype=QtCore.QSize)
    def setImageSize(self, size: QtCore.QSize):
        self._logo_widget.setFixedSize(size)
        self.reload()

    @settable(argtype=Qt.Alignment)
    def setImageAlignment(self, align: Qt.Alignment) -> None:
        self._imagealign = align
        self.updateContents()

    @settable()
    def setGap(self, gap: float):
        self._gap = gap
        self.updateContents()

    @settable()
    def setValue(self, text: str) -> None:
        self.setText(text)

    def updateContents(self):
        rect = self.contentsRect()
        w = self._logo_widget
        gap = self._gap
        img_align = self._imagealign
        img_size = QtCore.QSizeF(w.width(), w.height())
        img_rect = styling.alignedRectF(
            self.layoutDirection(), img_align, img_size, rect
        )
        self._logo_item.setGeometry(img_rect)

        text_rect = QtCore.QRectF(rect)
        if img_align & Qt.AlignRight:
            text_rect.setRight(img_rect.left() - gap)
        else:
            text_rect.setLeft(img_rect.right() + gap)
        self._text_item.setGeometry(text_rect)

    def reload(self):
        path = self._imagepath
        if path and path.exists():
            pixmap = loadImage(path, self._logo_widget.size())
            self._logo_widget.setPixmap(pixmap)
        self.updateContents()


@graphictype("houdini_icon")
class HoudiniIconTile(LogoTile):
    @settable()
    def setIconName(self, name: str) -> None:
        import hou
        icon = hou.qt.Icon(name, 256, 256)
        pixmap = icon.pixmap(256, 256)
        self.setPixmap(pixmap)
        self.updateContents()


@graphictype("blank")
class BlankTile(TextTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self.setLabelVisible(False)
        self.setTextSize(LABEL_SIZE)
        self.setTextColorRole(QtGui.QPalette.PlaceholderText)
        self.setTextAlignment(Qt.AlignCenter)
        self.setContentsMargins(0, 0, 0, 0)
        self.background().setVisible(False)

    @settable()
    def setText(self, html: str) -> None:
        super().setText(html)
        self._content.setVisible(bool(html))


@graphictype("button_tile")
class ButtonTile(TextTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self.setLabelVisible(False)
        self.setTextAlignment(Qt.AlignCenter)
        self.setContentsMargins(10, 5, 10, 5)
        self.background().setFillRole(QtGui.QPalette.Button)
        self.contentItem().setForegroundRole(QtGui.QPalette.ButtonText)
        self.setCursor(Qt.ArrowCursor)
        self._on_press: Optional[config.PythonValue] = None
        self._on_release: Optional[config.PythonValue] = None

    @settable()
    def setOnRelease(self, code: Union[str, CodeType, dict]) -> None:
        self._on_release = config.PythonValue.fromData(code)

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent
                        ) -> None:
        self.setScale(0.94)
        if self._on_press:
            v = self._on_press.evaluate(None, self.localEnv())

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent
                          ) -> None:
        self.animateScale(1.0)
        if self._on_release:
            v = self._on_release.evaluate(None, self.localEnv())

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.drawRect(self.rect())


@graphictype("surface")
class Surface(LinearLayoutTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self.setContentsMargins(5.0, 10.0, 5.0, 10.0)

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.drawRect(self.rect())


class TileViewWidget(graphics.GraphicViewWidget):
    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)

        self._message = graphics.TextGraphic()
        self._message.setZValue(100)
        self._message.setDocumentMargin(10)
        self._message.setTextAlignment(Qt.AlignCenter)
        self._message.setForegroundRole(QtGui.QPalette.PlaceholderText)
        font = QtGui.QFont()
        font.setFamily(FONT_FAMILY)
        font.setPixelSize(XLARGE_TEXT_SIZE)
        self._message.setFont(font)
        self._message.hide()

    def setScene(self, scene: TileScene) -> None:
        super().setScene(scene)
        scene.addItem(self._message)

    # TODO: replace built-in message with a stacked overlay in the tile config
    def message(self) -> graphics.TextGraphic:
        return self._message

    def setMessage(self, msg: graphics.TextGraphic):
        self._message = msg

    def messageText(self) -> str:
        return self.message().html()

    def setMessageText(self, text: str):
        msg = self.message()
        if msg:
            msg.setHtml(text)
            msg.show()

    def showMessage(self) -> None:
        msg = self.message()
        if msg:
            msg.show()

    def hideMessage(self) -> None:
        msg = self.message()
        if msg:
            msg.hide()

    def fitContents(self):
        super().fitContents()
        scene = self.scene()
        if not scene:
            return

        view_rect = self.viewRect()
        self._message.setGeometry(view_rect)


class TileScene(graphics.GraphicScene):
    def rootTile(self) -> Optional[Tile]:
        # Temporary alias for backwards compatibility
        return self.rootGraphic()

    def setRootTile(self, root: Tile) -> None:
        # Temporary alias for backwards compatibility
        self.setRootGraphic(root)


class GearMenuButton(QtWidgets.QPushButton):
    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self._gear = QtGui.QPixmap()
        self._trisize = 8
        self.setFlat(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setIconSize(QtCore.QSize(24, 24))
        self._updateicon()
        self.setGlobalScale(1.0)

    def _updateicon(self):
        c = self.palette().buttonText().color().name()
        self._gear = styling.makeSvgPixmap(styling.gear_svg, 64, c)

    def setGlobalScale(self, scale: float) -> None:
        iconsize = int(16 * scale)
        self.setIconSize(QtCore.QSize(iconsize, iconsize))
        margin = int(5 * scale)
        self.setFixedSize(iconsize + margin * 4, iconsize + margin * 2)
        self._trisize = int(8 * scale)

    def event(self, event: QtCore.QEvent) -> bool:
        super().event(event)
        if event.type() == QtCore.QEvent.PaletteChange:
            self._updateicon()
        return False

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(painter.Antialiasing)
        palette = self.palette()
        rect = self.rect()
        iconsize = self.iconSize()
        ts = self._trisize
        iconrect = QtWidgets.QStyle.alignedRect(
            self.layoutDirection(), Qt.AlignCenter, iconsize, rect
        )
        iconrect.translate(-ts // 2, 0)
        if self.isDown():
            painter.fillRect(rect, palette.button())
        painter.drawPixmap(iconrect, self._gear, self._gear.rect())

        tx = iconrect.right() + ts // 2
        ty = rect.center().y() - int(ts / 3)
        painter.setBrush(palette.buttonText())
        painter.setPen(Qt.NoPen)
        painter.drawPolygon([
            QtCore.QPoint(tx, ty),
            QtCore.QPoint(tx + ts, ty),
            QtCore.QPoint(tx + int(ts / 2), ty + int(ts * 0.66)),
        ], Qt.OddEvenFill)


class GearPolicy(enum.Enum):
    show_at_top = enum.auto()
    auto_show = enum.auto()
    always_visible = enum.auto()
    hidden = enum.auto()


class TileWidget(QtWidgets.QFrame):
    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self._template_path: Optional[pathlib.Path] = None
        self._global_scale = 1.0
        self._view = TileView(self)

        scene = TileScene(self)
        scene.setController(config.JsonPathController())
        self._view.setScene(scene)

        vsb = self._view.verticalScrollBar()
        vsb.valueChanged.connect(self._scrolled)
        # There's no signal for visibility, so we have to intercept visibility
        # events on the view's scrollbar
        vsb.installEventFilter(self)

        self._gearpolicy = GearPolicy.show_at_top
        self._gear = self._makeGearButton()
        self._setupActions()
        self.gearButton().setMenu(self._makeGearMenu())

    def setGlobalScale(self, scale: float) -> None:
        self._global_scale = scale
        self._view.setGlobalScale(scale)
        self._gear.setGlobalScale(scale)
        self._resized()

    def setGearButtonPolicy(self, policy: GearPolicy) -> None:
        self._gearpolicy = policy
        self._updateGearVisibility()

    def _makeGearButton(self) -> QtWidgets.QPushButton:
        gear = GearMenuButton(self)
        effect = QtWidgets.QGraphicsOpacityEffect(gear)
        gear.setGraphicsEffect(effect)
        return gear

    def _setupActions(self) -> None:
        pass

    def _makeGearMenu(self) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(self)
        menu.addAction(self._view.zoomInAction)
        menu.addAction(self._view.zoomOutAction)
        menu.addAction(self._view.unzoomAction)
        return menu

    def gearButton(self) -> QtWidgets.QPushButton:
        return self._gear

    def rootTile(self) -> Optional[Tile]:
        scene = self._view.scene()
        if scene and isinstance(scene, TileScene):
            return scene.rootTile()

    def controller(self) -> Optional[config.DataController]:
        scene = self._view.scene()
        if scene and isinstance(scene, TileScene):
            return scene.controller()

    def setController(self, controller: config.DataController) -> None:
        scene = self._view.scene()
        if scene and isinstance(scene, TileScene):
            scene.setController(controller)
        else:
            raise TypeError(f"Can't set controller on scene: {scene}")

    def loadTemplate(self, path: Union[str, pathlib.Path], force=False) -> None:
        if isinstance(path, str):
            path = pathlib.Path(path)
        if path and (force or path != self._template_path):
            with path.open() as f:
                template_data = json.load(f)
            self.setTemplate(template_data)
            self._template_path = path

    def setTemplate(self, template_data: dict[str, Any]) -> None:
        root = graphics.rootFromTemplate(template_data, self.controller())
        scene = self._view.scene()
        if scene and isinstance(scene, TileScene):
            scene.setRootTile(root)
        else:
            raise TypeError(f"Can't set root tile on scene: {scene}")

    def eventFilter(self, watched: QtCore.QObject,
                    event: QtCore.QEvent) -> bool:
        if watched == self._view.verticalScrollBar():
            if isinstance(event, (QtGui.QShowEvent, QtGui.QHideEvent)):
                self._repositionGear()
        return super().eventFilter(watched, event)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self._resized()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._resized()

    def _resized(self):
        rect = self.rect()
        self._view.setGeometry(rect)
        self._repositionGear()

    def _repositionGear(self):
        gear = self.gearButton()
        vsb = self._view.verticalScrollBar()
        w = self.rect().width()
        if vsb.isVisible():
            w -= vsb.width()
        gear.move(w - gear.width(), 0)

    def _updateGearVisibility(self):
        gear = self._gear
        policy = self._gearpolicy
        height = gear.height()
        effect: QtWidgets.QGraphicsOpacityEffect = gear.graphicsEffect()
        if policy == GearPolicy.hidden:
            gear.hide()
        elif policy == GearPolicy.always_visible:
            gear.show()
            effect.setOpacity(1.0)
        elif height and policy == GearPolicy.show_at_top:
            pos = self._view.verticalScrollBar().sliderPosition()
            if pos <= height:
                opacity = 1.0
            elif pos < height * 2:
                opacity = 1.0 - (pos - height) / height
            else:
                opacity = 0.0
            gear.setVisible(bool(opacity))
            effect.setOpacity(opacity)
        elif policy == GearPolicy.auto_show:
            # TODO: implement this
            pass

    def _scrolled(self):
        self._updateGearVisibility()


def generateImage(template_data: dict[str, Any], stats: dict[str, Any],
                  width: int, height=-1, scale=1.0, rotation=0.0
                  ) -> QtGui.QPixmap:
    from renderstats.images import normalize_stats

    controller = config.JsonPathController()
    stats = normalize_stats(stats)
    root = graphics.rootFromTemplate(template_data, controller)
    controller.updateFromData(stats)
    if scale != 1.0 or rotation != 0.0:
        xform = QtGui.QTransform()
        xform.rotate(rotation)
        xform.scale(scale, scale)
        root.setTransform(xform)

    scene = QtWidgets.QGraphicsScene()
    pal = themes.darkPalette()
    scene.setPalette(pal)
    scene.addItem(root)

    controller.updateFromData(stats)

    constraint = QtCore.QSizeF(width, height)
    tile_size = root.effectiveSizeHint(Qt.PreferredSize, constraint)
    root.resize(tile_size)

    scene.setSceneRect(scene.itemsBoundingRect())
    scene_size = scene.sceneRect().size().toSize()

    pixmap = QtGui.QPixmap(int(scene_size.width()), int(scene_size.height()))
    pixmap.fill(Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(painter.Antialiasing, True)
    scene.render(painter, source=scene.sceneRect())
    painter.end()
    return pixmap


# class TilePlayground(QtWidgets.QMainWindow):
#     def __init__(self, parent: QtWidgets.QWidget = None):
#         if not parent:
#             import hou
#             parent = hou.qt.mainWindow()
#         super().__init__(parent)
#
#         from hutil.qt.editors import JsonEditor
#         self._editor = JsonEditor()
#         self._editor.textChanged.connect(self._reparse)
#
#         self._view = StatsViewer()
#         self._view.setGearButtonPolicy(GearPolicy.hidden)
#
#         self._splitter = QtWidgets.QSplitter()
#         self._splitter.addWidget(self._editor)
#         self._splitter.addWidget(self._view)
#         self.setCentralWidget(self._splitter)
#
#     def _reparse(self):
#         try:
#             template_data = json.loads(self._editor.toPlainText())
#         except json.JSONDecodeError:
#             return
#         self._view.setTemplate(template_data)

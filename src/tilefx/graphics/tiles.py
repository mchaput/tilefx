from __future__ import annotations
import enum
import os.path
import pathlib
import weakref
from datetime import datetime
from typing import (TYPE_CHECKING, cast, Any, Callable, Collection, Iterable,
                    NamedTuple, Optional, Sequence, TypeVar, Union)

import shiboken2
from PySide2 import QtCore, QtGui, QtWidgets, QtSvg
from PySide2.QtCore import Qt

import tilefx.util
from .. import (config, converters, formatting, glyphs, models, styling, themes,
                util)
from ..config import settable
from ..editors.syntax import syntaxHighlighterConverter
from ..themes import ThemeColor
from . import controls, containers, core, layouts, charts, views, widgets
from .core import (FONT_FAMILY, NUMBER_FAMILY, graphictype, path_element,
                   Graphic, DynamicColor)

if TYPE_CHECKING:
    import hou


# Type aliases
T = TypeVar("T")

# Do not scale these by hou.ui.scaledSize(), that is handled at another level
GRID_COL_WIDTH = 80
GRID_ROW_HEIGHT = 60
PANEL_WIDTH = 400
SCALES = [0.75, 0.865, 1.0, 1.2]
CHART_SIZES = [32, 48, 64, 128]
BASE_FONT_SIZE = 14

DEFAULT_LABEL_MARGIN = 4
DEFAULT_TILE_CORNER_RADIUS = 8.0

DEFAULT_TEXT_SHADOW_COLOR = Qt.black
DEFAULT_TEXT_SHADOW_OFFSET = QtCore.QPointF(0.0, 1.0)
DEFUALT_TEXT_SHADOW_BLUR = 2
SECONDARY_ALPHA = 0.5
LABEL_Z = 50


class NoticeLook(NamedTuple):
    glyph: glyphs.Glyph
    color: themes.ThemeColor
    surface_color: themes.ThemeColor
    surface_fg_color: themes.ThemeColor


ERROR_LOOK = NoticeLook(glyphs.IconFX.error,
                        themes.ThemeColor.error,
                        themes.ThemeColor.error_surface,
                        themes.ThemeColor.error_surface_fg)
WARNING_LOOK = NoticeLook(glyphs.IconFX.warning,
                          themes.ThemeColor.warning,
                          themes.ThemeColor.warning_surface,
                          themes.ThemeColor.warning_surface_fg)
MESSAGE_LOOK = NoticeLook(glyphs.IconFX.info,
                          themes.ThemeColor.success,
                          themes.ThemeColor.success_surface,
                          themes.ThemeColor.success_surface_fg)
notice_style_map: dict[str, NoticeLook] = {
    "error": ERROR_LOOK,
    "warning": WARNING_LOOK,
    "message": MESSAGE_LOOK
}


def qstyleoption_cast(option: QtWidgets.QStyleOption, cls: type[T]) -> T:
    (cpp_pointer,) = shiboken2.getCppPointer(option)
    return shiboken2.wrapInstance(cpp_pointer, cls)


def toPath(p: Union[str, pathlib.Path]) -> pathlib.Path:
    if isinstance(p, str):
        p = os.path.expanduser(os.path.expandvars(p))
    return pathlib.Path(p).resolve()


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


@graphictype("_tile_label")
class TileLabel(controls.StringGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._button: Optional[Graphic] = None
        self._button_at_start = False
        self._button_gap = 5.0

        self.geometryChanged.connect(self._updateContents)

    def buttonBeforeLabel(self) -> bool:
        return self._button_at_start

    def setButtonBeforeLabel(self, before: bool) -> None:
        self._button_at_start = before
        self._updateContents()
        self.update()

    def hasButton(self) -> bool:
        return bool(self._button)

    def labelButton(self) -> Optional[Graphic]:
        return self._button

    # def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
    #              ) -> QtCore.QSizeF:
    #     constraint = constraint or QtCore.QSizeF(-1, -1)
    #     if which in (Qt.MinimumSize, Qt.PreferredSize, Qt.MaximumSize):
    #         bw = 0
    #         if self._button:
    #             bsize = self._button.sizeHint(which, QtCore.QSizeF(-1, -1))
    #             bw = bsize.width() + self._button_gap
    #         cw = constraint.width()
    #         if cw > 0:
    #             constraint.setWidth(cw - bw)
    #         return super().sizeHint(which, constraint)
    #     return constraint

    @settable(argtype=Graphic)
    def setLabelButton(self, button: controls.Graphic, at_start=False
                       ) -> None:
        self._button = button
        self._button_gap = 5.0
        self._button_at_start = at_start
        button.setParentItem(self)
        button.setZValue(1)

        self.updateGeometry()
        self._updateContents()
        self.update()

    def _updateContents(self) -> None:
        rect = self.rect().marginsRemoved(self._margins)
        button = self._button
        if button:
            inset_start = inset_end = 0.0
            bsize = button.size()
            bw = bsize.width()
            bh = bsize.height()
            by = rect.center().y() - bh / 2
            if self._button_at_start:
                bx = rect.x()
                inset_start = bw + self._button_gap
            else:
                bx = rect.right() - bw
                inset_end = bw + self._button_gap
            button.setGeometry(bx, by, bw, bh)
            self._insets = (inset_start, inset_end)
        else:
            self._insets = None


class Tile(core.RectangleGraphic):
    property_aliases = {
        "label_color": "label.text_color",
        "label_align": "label.text_align",
        "bg_color": "background.fill_color",
        "fill_color": "background.fill_color",
        "label_line_width": "label.line_width"
    }

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        # Call setObjectName on the superclass so we don't trigger logic for
        # renaming sub-items based on the tile name
        super().setObjectName(f"tile_{id(self):x}")
        self._vars: dict[str, Any] = {}
        self._tiles: list[Tile] = []
        # If the tile background is turned off, we also turn off the label bg,
        # but we want to remember the desired visibility separate from the
        # actual visibility, so turning the tile bg back on will also turn on
        # the label bg again in that case
        self._label_visible = True
        self._label_bg_visible = True
        self._label_bg_free = False
        self._label_overlayed = False
        self._label_sticky = False
        self._sticky_offset = 10.0
        self._sticky_fade = 0.2

        self._inside = False
        self._copy_button: Optional[controls.ToolButtonGraphic] = None
        self._copyable = True
        self._copy_button_alignment = Qt.AlignBottom | Qt.AlignRight

        self.setBrush(Qt.NoBrush)
        self.setPen(Qt.NoPen)
        self.setCornerRadius(DEFAULT_TILE_CORNER_RADIUS)

        self._bg = core.RectangleGraphic(self)
        self._bg.setFlag(self.ItemClipsChildrenToShape, True)
        self._bg.setFlag(self.ItemStacksBehindParent, True)
        self._bg.setFillColor(ThemeColor.surface)
        self._bg.setClipsToParentShape(True)

        self._label = TileLabel(self)
        self._label.setFillColor(ThemeColor.surface_low)
        self._label.setZValue(LABEL_Z)
        self._label.setClipsToParentShape(True)
        self._label.setElideMode(Qt.ElideRight)
        self._label.setTextColor(ThemeColor.fg)
        self._label.setFont(self.contentFont(size=converters.LABEL_SIZE))
        self._label.setMargins(QtCore.QMarginsF(8.0, 5.0, 8.0, 5.0))

        # shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        # shadow.setColor(QtGui.QColor.fromRgbF(0, 0, 0, 0.33))
        # shadow.setOffset(0, 1.0)
        # shadow.setBlurRadius(14.0)
        # shadow.setEnabled(True)
        # self.setGraphicsEffect(shadow)

        # self.setFlag(self.ItemClipsChildrenToShape, True)

        self._labeledge = Qt.TopEdge
        self._inner_margins = QtCore.QMarginsF(5.0, 5.0, 5.0, 5.0)
        self._ignore_margins = False
        self._side_label_rotated = True
        self._side_label_width = 0.0

        self._size = self._layoutsize = QtCore.QSizeF(GRID_COL_WIDTH,
                                                      GRID_ROW_HEIGHT)
        self._content_rect = QtCore.QRectF()
        self._effect: Optional[QtWidgets.QGraphicsEffect] = None

        self._content: Optional[QtWidgets.QGraphicsProxyWidget] = None
        self.setFont(self.contentFont())

        self.setHasWidthForHeight(True)
        # self.setSelectable(True)

        self._bg.visibleChanged.connect(self._updateLabelBgVisibility)

    def __del__(self):
        try:
            self._label.visibleChanged.disconnect()
        except RuntimeError:
            pass

    def resizeEvent(self, event) -> None:
        self._updateTile()

    def setObjectName(self, name: str) -> None:
        super().setObjectName(name)
        if hasattr(self, "_content") and self._content:
            self._content.setObjectName(f"{name}_content")

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange,
                   value: Any) -> Any:
        if change == self.ItemVisibleHasChanged and value:
            self.updateGeometry()
        elif change == self.ItemScenePositionHasChanged and self._label_sticky:
            self._updateTile()
        elif change == self.ItemSelectedHasChanged:
            self._updateCopyButtonVisibility()
        elif change == self.ItemSceneChange:
            self.sceneChanged(self.scene(), value)
        return super().itemChange(change, value)

    def sceneChanged(self, old_scene: QtWidgets.QGraphicsScene,
                     new_scene: QtWidgets.QGraphicsScene) -> None:
        if old_scene and isinstance(old_scene, core.GraphicScene):
            old_scene.viewportChanged.disconnect(self.viewportChanged)
        if isinstance(new_scene, core.GraphicScene):
            new_scene.viewportChanged.connect(self.viewportChanged)

    def updateableChildren(self) -> Iterable[Graphic]:
        return list(self._tiles)

    def copyButtonEnabled(self) -> bool:
        return self._copyable

    def _copyButton(self) -> controls.ToolButtonGraphic:
        if self._copy_button is None:
            self._setupCopyButton()
        return self._copy_button

    def _setupCopyButton(self) -> None:
        self._copy_button = controls.ToolButtonGraphic(self)
        self._copy_button.setTransparent(True)
        self._copy_button.setLabelMargins(QtCore.QMarginsF(0, 0, 0, 0))
        self._copy_button.setToolTip("Copy text to clipboard")
        self._copy_button.setGlyph(glyphs.MaterialIcons.content_copy)
        self._copy_button.setFixedSize(QtCore.QSizeF(20, 20))
        self._copy_button.setVisible(False)
        self._copy_button.clicked.connect(self.copyContentsToClipboard)
        self._copy_button.setZValue(100)

    def _positionCopyButton(self) -> None:
        visible = self._copyButtonVisible()
        if not (self._copyable and visible):
            return

        rect = self.contentsRect()
        button = self._copyButton()
        size = button.effectiveSizeHint(Qt.PreferredSize, QtCore.QSizeF(-1, -1))
        button_rect = util.alignedRectF(
            self.layoutDirection(), self._copy_button_alignment, size, rect
        )
        button.setGeometry(button_rect)

    def copyContentsToClipboard(self) -> None:
        core.copyItemContentsToClipboard((self,))

    def textToCopy(self) -> str:
        text = "; ".join(tile.textToCopy() for tile in self._tiles)
        return self._wrapTextToCopy(text)

    def _wrapTextToCopy(self, text: str) -> str:
        label_text = self.labelText()
        if label_text:
            text = f"{label_text}: {text}"
        return text

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent
                        ) -> None:
        super().hoverEnterEvent(event)
        self._inside = True
        self._updateCopyButtonVisibility()

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent
                        ) -> None:
        super().hoverLeaveEvent(event)
        self._inside = False
        self._updateCopyButtonVisibility()

    def _copyButtonVisible(self) -> bool:
        return self._inside and self.isSelected()

    def _updateCopyButtonVisibility(self) -> None:
        visible = self._copyButtonVisible()
        # The button is created lazily, so don't create it just to hide it
        if self._copy_button or visible:
            self._copyButton().setVisible(visible)
            self._positionCopyButton()

    def textIsCopyable(self) -> bool:
        return self._copyable

    @settable(argtype=bool)
    def setTextCopyable(self, enabled: bool) -> None:
        self._copyable = enabled
        if enabled:
            self.setAcceptHoverEvents(enabled)
            self.setSelectable(True)
        self._updateCopyButtonVisibility()

    @settable()
    def setCopyButtonAlignment(self, alignment: Qt.AlignBottom) -> None:
        self._copy_button_alignment = alignment
        self._updateContents()

    @staticmethod
    def contentFont(family=FONT_FAMILY, size=converters.MEDIUM_TEXT_SIZE,
                    weight: QtGui.QFont.Weight = None) -> QtGui.QFont:
        font = QtGui.QFont(family)
        font.setPixelSize(size)
        if weight:
            font.setWeight(weight)
        return font

    def addChild(self, tile: Tile) -> None:
        super().addChild(tile)
        self._tiles.append(tile)

    @classmethod
    def fromData(cls, data: dict[str, Any], parent: Tile = None,
                 controller: config.DataController = None) -> Tile:
        tile = cls(parent=parent)
        if parent:
            parent.prepChild(tile, data)
        tile.configureFromData(data, controller)
        return tile

    def __repr__(self):
        return f"<{type(self).__name__} {self.objectName()}>"

    def _baseSize(self) -> QtCore.QSizeF:
        width = height = 0.0
        ms = self.contentsMargins()
        width += ms.left() + ms.right()
        height += ms.top() + ms.bottom()
        if self.labelIsVisible() and not self.labelIsOverlayed():
            le = self.labelEdge()
            label_size = self.label().size()
            if le == Qt.TopEdge or le == Qt.BottomEdge:
                height += label_size.height()
            elif self._side_label_rotated:
                width += label_size.height()
            else:
                width += label_size.width()
        return QtCore.QSizeF(width, height)

    def _contentSizeHint(self, which: Qt.SizeHint,
                         constraint: QtCore.QSizeF = None) -> QtCore.QSizeF:
        if self._content:
            return self._content.effectiveSizeHint(which, constraint)
        else:
            return constraint

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSize(-1, -1)
        size = self._baseSize()
        if which in (Qt.MinimumSize, Qt.PreferredSize, Qt.MaximumSize):
            cw = constraint.width()
            ch = constraint.height()
            if cw >= 0:
                constraint.setWidth(max(0.0, cw - size.width()))
            if ch >= 0:
                constraint.setHeight(max(0.0, ch - size.height()))
            csize = self._contentSizeHint(which, constraint)
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

    def labelIsSticky(self) -> bool:
        return self._label_sticky

    @settable("label_sticky", argtype=bool)
    def setStickyLabel(self, sticky: bool) -> None:
        self._label_sticky = sticky
        if sticky:
            self.setFlag(self.ItemSendsScenePositionChanges, True)
            self.setClipping(True)
        self._updateTile()

    def viewportChanged(self) -> None:
        super().viewportChanged()
        if self._label_sticky:
            self._updateTile()

    def labelIsOverlayed(self) -> bool:
        return self._label_overlayed

    @settable("overlay_label")
    def setLabelOverlayed(self, overlayed: bool):
        self._label_overlayed = overlayed
        self._updateLabelBgVisibility()
        self._updateContents()

    @settable("label_bg", argtype=QtGui.QColor)
    def setLabelBackgroundColor(self, color: converters.ColorSpec):
        self.label().setFillColor(color)

    @settable(argtype=float)
    def setLabelLineWidth(self, width: float):
        self._line_width = width

    @path_element(core.RectangleGraphic)
    def background(self) -> core.RectangleGraphic:
        return self._bg

    @path_element(TileLabel)
    def label(self) -> TileLabel:
        return self._label

    def labelText(self) -> str:
        return self.label().text()

    @settable("label")
    def setLabelText(self, text: str):
        self.label().setText(text)
        if not self.labelIsVisible():
            self.setLabelVisible(True)
            self._updateTile()
        else:
            self.update()

    @settable(converter=converters.textSizeConverter)
    def setLabelSize(self, size: Union[str, int]):
        label = self.label()
        font = label.font()
        font.setPixelSize(size)
        label.setFont(font)
        self._updateTile()

    def labelIsVisible(self) -> bool:
        return self._label_visible

    @settable()
    def setLabelVisible(self, visible: bool):
        self._label_visible = visible
        self.label().setVisible(visible)
        self._updateTile()

    def labelEdge(self) -> Qt.Edge:
        return self._labeledge

    @settable(argtype=Qt.Edge)
    def setLabelEdge(self, edge: Qt.Edge):
        if not isinstance(edge, Qt.Edge):
            raise TypeError(edge)
        self._labeledge = edge
        self._updateTile()

    def sideLabelRotated(self) -> bool:
        return self._side_label_rotated

    @settable(argtype=bool)
    def setSideLabelRotated(self, rotated: bool) -> None:
        self._side_label_rotated = rotated
        self.updateGeometry()
        self._updateTile()

    def sideLabelWidth(self) -> float:
        return self._side_label_width

    @settable()
    def setSideLabelWidth(self, width: float) -> None:
        self._side_label_width = width
        self.updateGeometry()
        self._updateTile()

    @settable(argtype=Graphic)
    def setLabelButton(self, button: Graphic, at_start=False) -> None:
        self.label().setLabelButton(button, at_start=at_start)
        self.updateGeometry()

    @path_element(Graphic)
    def contentItem(self) -> Graphic:
        return self._content

    @settable("content_item", argtype=Graphic)
    def setContentItem(self, item: Optional[Graphic]) -> None:
        if item:
            if not item.objectName():
                item.setObjectName(f"{self.objectName()}_content")
            item.setParentItem(self)
        self._content = item
        self._updateContents()

    def contentWidget(self) -> Optional[QtWidgets.QWidget]:
        item = self.contentItem()
        if isinstance(item, QtWidgets.QGraphicsProxyWidget):
            return item.widget()

    def setContentWidget(self, w: QtWidgets.QWidget, transparent: bool = True):
        item = QtWidgets.QGraphicsProxyWidget(self)
        if transparent is not None:
            w.setAttribute(Qt.WA_TranslucentBackground, transparent)
        item.setWidget(w)
        self.setContentItem(item)

    @settable(argtype=QtGui.QColor)
    def setTint(self, tint_color: QtGui.QColor):
        self.background().setTint(tint_color)
        self.label().setTint(tint_color)

    @settable()
    def setTintAlpha(self, alpha: float):
        self._tint.setAlphaF(alpha)

    def backgroundVisible(self) -> bool:
        return self.background().isVisible()

    @settable("bg_visible", argtype=bool)
    def setBackgroundVisible(self, visible: bool) -> None:
        self.background().setVisible(visible)
        self._updateLabelBgVisibility()

    def labelBackgroundIsVisible(self) -> bool:
        return self.label().isBackgroundVisible()

    @settable("label_bg_visible", argtype=bool)
    def setLabelBackgroundVisible(self, visible: bool):
        self._label_bg_visible = visible
        self._updateLabelBgVisibility()

    @settable("label_bg_free", argtype=bool)
    def setLabelBackgroundFree(self, free: bool) -> None:
        self._label_bg_free = free
        self._updateLabelBgVisibility()

    def _updateLabelBgVisibility(self) -> None:
        # If the background is turned off, also turn off the label background
        effective_vis = (self._label_bg_visible and
                         (self._bg.isVisible() or self._label_bg_free) and
                         not self.labelIsOverlayed())
        self.label().setBackgroundVisible(effective_vis)

    def shape(self) -> QtGui.QPainterPath:
        if self._label_sticky:
            rect = self.stickyRect()
            pp = QtGui.QPainterPath()
            cr = self._corner_radius
            if cr:
                pp.addRoundedRect(rect, cr, cr)
            else:
                pp.addRect(rect)
            return pp
        else:
            return super().shape()

    def stickyRect(self) -> QtCore.QRectF:
        rect = self.rect()
        vis_rect = self.mapRectFromScene(self.viewportRect())
        vis_rect.adjust(0.0, self._sticky_offset, 0.0, -self._sticky_offset)

        label_edge = self.labelEdge()
        min_h = self._stickyMinHeight()
        if label_edge == Qt.TopEdge and rect.top() < vis_rect.top():
            rect.setTop(vis_rect.top())
            if rect.isValid() and rect.height() < min_h:
                rect.setTop(rect.bottom() - min_h)
        elif label_edge == Qt.BottomEdge and rect.bottom() > vis_rect.bottom():
            rect.setBottom(vis_rect.bottom())

        return rect

    def _stickyMinHeight(self) -> float:
        return self._labelHeight() * 2

    def _labelHeight(self) -> float:
        lms = self.labelMargins()
        fm = QtGui.QFontMetricsF(self.label().font())
        return fm.lineSpacing() + lms.top() + lms.bottom()

    def _labelWidth(self) -> float:
        slw = self.sideLabelWidth()
        if slw:
            return slw
        lms = self.labelMargins()
        fm = QtGui.QFontMetricsF(self.label().font())
        w = fm.horizontalAdvance(self.labelText())
        return w + lms.left() + lms.right()

    def _positionLabel(self, rect: QtCore.QRectF) -> None:
        # If the label is sticky, rect is the visible rect, not the actual rect
        edge = self.labelEdge()
        height = self._labelHeight()

        rotation = 0.0
        label_rect = QtCore.QRectF(rect.x(), rect.y(), rect.width(), height)
        rotated = self.sideLabelRotated()
        if edge == Qt.TopEdge:
            pass
        elif edge == Qt.LeftEdge:
            if rotated:
                rotation = -90.0
                label_rect.moveTop(rect.bottom())
                label_rect.setWidth(rect.height())
            else:
                label_rect.setWidth(self._labelWidth())
                label_rect.setHeight(rect.height())
        elif edge == Qt.BottomEdge:
            label_rect.moveTop(rect.bottom() - height)
        elif edge == Qt.RightEdge:
            if rotated:
                rotation = 90.0
                label_rect.moveTo(rect.topRight())
                label_rect.setWidth(rect.height())
            else:
                ltw = self._labelWidth()
                label_rect.setX(rect.right() - ltw)
                label_rect.setWidth(ltw)
                label_rect.setHeight(rect.height())
        else:
            raise ValueError(edge)

        label = self.label()
        label.setGeometry(label_rect)
        label.setTransformOriginPoint(0, 0)
        label.setRotation(rotation)

    def _contentsRect(self) -> QtCore.QRectF:
        # Returns the content area of the actual rect, (without regard to
        # sticky label)
        rect = self.rect()
        if not rect.isValid():
            return rect

        if self.labelIsVisible():
            height = self._labelHeight()
            edge = self.labelEdge()
            rotated = self.sideLabelRotated()

            if edge == Qt.TopEdge:
                rect.setTop(rect.y() + height)
            elif edge == Qt.LeftEdge:
                w = height if rotated else self._labelWidth()
                rect.setLeft(rect.x() + w)
            elif edge == Qt.BottomEdge:
                rect.setBottom(rect.bottom() - height)
            elif edge == Qt.RightEdge:
                w = height if rotated else self._labelWidth()
                rect.setRight(rect.right() - w)
            else:
                raise ValueError(edge)
        rect = rect.marginsRemoved(self.contentsMargins())
        return rect

    def contentsRect(self) -> QtCore.QRectF:
        if not self._content_rect.isValid():
            self._content_rect = self._contentsRect()
        return self._content_rect

    def _updateTile(self) -> None:
        rect = self.rect()
        self.setTransformOriginPoint(rect.center())
        vrect = self.stickyRect() if self.labelIsSticky() else rect
        self.background().setGeometry(vrect)
        self._positionLabel(vrect)

        self._content_rect = self._contentsRect()
        self._updateContents()
        self.update()

    def _updateContents(self):
        self._positionCopyButton()
        if self._content:
            self._content.setGeometry(self.contentsRect())

    def labelMargins(self) -> QtCore.QMarginsF:
        return self.label().margins()

    @settable(argtype=QtCore.QMarginsF)
    def setLabelMargins(self, ms: QtCore.QMarginsF) -> None:
        self.label().setMargins(ms)
        self._updateTile()

    def contentsMargins(self) -> QtCore.QMarginsF:
        return self._inner_margins

    def setContentsMargins(self, left: float, top: float, right: float,
                           bottom: float) -> None:
        super().setContentsMargins(left, top, right, bottom)
        self._inner_margins = QtCore.QMarginsF(left, top, right, bottom)
        self._updateTile()

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
        self._updateContents()

    def ignoreMargins(self) -> bool:
        return self._ignore_margins

    @settable()
    def setIgnoreMargins(self, ignore: bool):
        self._ignore_margins = ignore

    def _contentBlurEffect(self) -> QtWidgets.QGraphicsBlurEffect:
        return getEffect(self.contentItem(), QtWidgets.QGraphicsBlurEffect)

    def _contentShadowEffect(self) -> QtWidgets.QGraphicsDropShadowEffect:
        return getShadowEffect(self.contentItem())

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

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget]=None) -> None:
    #     painter.setPen(Qt.blue)
    #     painter.drawRect(self.rect())


@graphictype("text")
class TextTile(Tile):
    _font_family = FONT_FAMILY

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._text_selectable = True
        self._links_clickable = True
        self._valuemap: dict[str, str] = {}
        self._formatter: Callable[[Any], str] = str
        self.setContentItem(self._makeContentItem())
        self._hiliter: Optional[QtGui.QSyntaxHighlighter] = None

        self.setHasHeightForWidth(True)
        self.setTextCopyable(True)

    def __del__(self):
        if self._hiliter:
            # Detach the text editor's document from the syntax highlighter
            # to fix what appears to be a double-free issue at destruction
            # time due to object ownership issues.
            self._hiliter.setDocument(None)

    def _makeContentItem(self) -> Optional[QtWidgets.QGraphicsItem]:
        content = controls.TextGraphic(self)
        content.setFont(self.contentFont(self._font_family))
        content.setTextColor(ThemeColor.value)
        content.setTextSelectable(self._text_selectable)
        content.setLinksClickable(self._links_clickable)
        return content

    def formatter(self) -> Callable[[Any], str]:
        return self._formatter

    def textToCopy(self) -> str:
        item = cast(controls.TextGraphic, self.contentItem())
        text = item.plainText()
        text.replace(formatting.NEGATIVE_CHAR, "-")
        return self._wrapTextToCopy(text)

    @settable("text_align", argtype=Qt.Alignment)
    def setTextAlignment(self, align: Qt.Alignment):
        self.contentItem().setTextAlignment(align)

    @settable(converter=converters.textSizeConverter)
    def setTextSize(self, size: int) -> None:
        self.contentItem().setTextSize(size)

    def textSize(self) -> int:
        return self.contentItem().font().pixelSize()

    @settable(argtype=bool)
    def setTextBold(self, bold: bool) -> None:
        self.contentItem().setBold(bold)

    @settable(argtype=bool)
    def setTextItalic(self, italic: bool) -> None:
        self.contentItem().setItalic(italic)

    @settable(argtype=QtGui.QFont.Weight)
    def setTextWeight(self, weight: int):
        w = self.contentItem()
        w.setWeight(weight)

    @settable()
    def setTextFamily(self, name: str):
        if name == "monospace":
            name = core.MONOSPACE_FAMILY

        font = QtGui.QFont()
        font.setFamily(name)
        font.setPixelSize(self.contentItem().font().pixelSize())
        self.contentItem().setFont(font)

    @settable("text_color", argtype=QtGui.QColor)
    def setTextColor(self, color: converters.ColorSpec) -> None:
        self._content.setTextColor(color)

    @settable()
    def setValueMap(self, valuemap: dict[str, str]):
        self._valuemap = valuemap

    @settable(argtype=bool)
    def setTextSelectable(self, selectable: bool) -> None:
        self._text_selectable = selectable
        content = self.contentItem()
        if isinstance(content, controls.TextGraphic):
            content.setTextSelectable(selectable)

    @settable(argtype=bool)
    def setLinksClickable(self, clickable: bool) -> None:
        self._links_clickable = clickable
        content = self.contentItem()
        if isinstance(content, controls.TextGraphic):
            content.setLinksClickable(clickable)

    @settable(argtype=bool)
    def setWordWrap(self, wrap: bool) -> None:
        self.contentItem().setWordWrap(wrap)

    @settable()
    def setSyntaxColoring(self,
        hiliter: str | QtGui.QSyntaxHighlighter | type[QtGui.QSyntaxHighlighter]
    ):
        doc = self._content.document()
        if isinstance(hiliter, str):
            hiliter = util.find_object(hiliter)
        if issubclass(hiliter, QtGui.QSyntaxHighlighter):
            hiliter = hiliter(doc)
        if not isinstance(hiliter, QtGui.QSyntaxHighlighter):
            raise TypeError(hiliter)
        self._hiliter = hiliter
        self._hiliter.setDocument(doc)

    def _updateContents(self):
        rect = self.contentsRect()
        content = self.contentItem()
        if content:
            content.setGeometry(rect)
        self._positionCopyButton()

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


@graphictype("notice")
class NoticeTile(TextTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        self._icon: Union[controls.StringGraphic, controls.PixmapGraphic] = \
            controls.StringGraphic()
        self._icon.setObjectName("notice_icon")
        self._orientation = Qt.Horizontal
        self._gap = 10.0
        self._text_before_icon = False
        self._icon_size = QtCore.QSizeF(18, 18)
        super().__init__(parent)
        self._glyph_text_size = 14
        self._glyph_color: Optional[converters.ColorSpec] = None
        self.setLabelVisible(False)

        self._icon.setParentItem(self)
        self._icon_alignment = self._icon.textAlignment()
        self.setIconAlignment(Qt.AlignTop | Qt.AlignRight)

    def __repr__(self):
        content: controls.TextGraphic = self._content
        return (f"<{type(self).__name__} {id(self):x} {self.objectName()!r} "
                f"{content.plainText()!r}>")

    @path_element(Graphic)
    def iconItem(self) -> Union[controls.StringGraphic, controls.PixmapGraphic]:
        return self._icon

    @path_element(controls.StringGraphic)
    def glyphItem(self) -> controls.StringGraphic:
        if not isinstance(self._icon, controls.StringGraphic):
            self._icon = controls.StringGraphic(self)
            self._icon.setTextSize(self._glyph_text_size)
            self._icon.setTextAlignment(Qt.AlignCenter)
            self._icon.setFixedSize(self._icon_size)
            if self._glyph_color:
                self._icon.setTextColor(self._glyph_color)
        return self._icon

    def setGlyph(self, glyph: glyphs.Glyph) -> None:
        self.prepareGeometryChange()
        self.glyphItem().setGlyph(glyph)
        self.glyphItem().setTextSize(self._glyph_text_size)
        self.updateGeometry()
        self._updateContents()

    @path_element(controls.PixmapGraphic)
    def pixmapItem(self) -> controls.PixmapGraphic:
        if not isinstance(self._icon, controls.PixmapGraphic):
            self._icon = controls.PixmapGraphic(self)
            self._icon.setSize(self._icon_size)
        return self._icon

    @settable("image")
    def setImagePath(self, path: pathlib.Path | str) -> None:
        self.pixmapItem().setPath(path)

    def setIcon(self, icon: QtGui.QIcon) -> None:
        self.pixmapItem().setIcon(icon)

    @settable("houdini_icon")
    def setHoudiniIcon(self, name: str):
        self.pixmapItem().setHoudiniIcon(name)

    @settable("glyph")
    def setGlyphName(self, name: str) -> None:
        self.glyphItem().setGlyphName(name)

    @settable("glyph_size", converter=converters.textSizeConverter)
    def setGlyphSize(self, size: int) -> None:
        self._glyph_text_size = size
        icon = self.iconItem()
        if isinstance(icon, controls.StringGraphic):
            self.prepareGeometryChange()
            icon.setTextSize(size)
            self.updateGeometry()
            self._updateContents()

    @settable("glyph_color", argtype=QtGui.QColor)
    def setGlyphColor(self, color: converters.ColorSpec) -> None:
        self._glyph_color = color
        icon = self.iconItem()
        if isinstance(icon, controls.StringGraphic):
            icon.setTextColor(color)

    @settable()
    def setNoticeType(self, type_name: str) -> None:
        style = notice_style_map[type_name]
        self.setGlyph(style.glyph)
        self.setGlyphColor(style.color)
        self.setTextColor(style.color)
        self.update()

    def orientation(self) -> Qt.Orientation:
        return self._orientation

    @settable(argtype=Qt.Orientation)
    def setOrientation(self, orient: Qt.Orientation) -> None:
        self._orientation = orient
        self._updateContents()

    @settable(argtype=Qt.Alignment)
    def setIconAlignment(self, align: Qt.Alignment) -> None:
        self._icon_alignment = align
        if self._icon:
            self._icon.setTextAlignment(align)
        self.updateGeometry()
        self._updateContents()

    @settable()
    def setSpacing(self, gap: float) -> None:
        self.prepareGeometryChange()
        self._gap = gap
        self.updateGeometry()
        self._updateContents()

    def isTextBeforeIcon(self) -> bool:
        return self._text_before_icon

    @settable(argtype=bool)
    def setTextBeforeIcon(self, reverse: bool) -> None:
        self._text_before_icon = reverse
        self._updateContents()

    @settable(argtype=QtCore.QMarginsF)
    def setIconMargins(self, margins: QtCore.QMarginsF) -> None:
        self.prepareGeometryChange()
        self.iconItem().setMargins(margins)
        self.updateGeometry()
        self._updateContents()

    @settable(argtype=QtCore.QSizeF)
    def setIconSize(self, size: QtCore.QSizeF) -> None:
        self._icon_size = size
        self.prepareGeometryChange()
        self.iconItem().setSize(size)
        self.updateGeometry()
        self._updateContents()

    @settable(argtype=QtCore.QMarginsF)
    def setTextMargins(self, margins: QtCore.QMarginsF) -> None:
        self.prepareGeometryChange()
        self.textItem().setMargins(margins)
        self.updateGeometry()
        self._updateContents()

    def _contentSizeHint(self, which: Qt.SizeHint,
                         constraint: QtCore.QSizeF = None) -> QtCore.QSizeF:
        cw = constraint.width()
        horiz = self._orientation == Qt.Horizontal
        icon = self._icon
        icon_size = icon.implicitSize() if icon else QtCore.QSizeF()
        if horiz:
            if cw > 0:
                cw -= icon_size.width() + self._gap
        csize = super()._contentSizeHint(which,
                                         QtCore.QSizeF(cw, constraint.height()))
        if not horiz:
            csize.setHeight(csize.height() + icon_size.height() + self._gap)
        if csize.height() > -1 and csize.height() < icon_size.height():
            csize.setHeight(icon_size.height())
        return csize

    def _updateContents(self) -> None:
        icon = self.iconItem()
        if not icon:
            return super()._updateContents()

        rect = self.contentsRect()
        text = self.contentItem()
        horiz = self.orientation() == Qt.Horizontal
        rev_order = self.isTextBeforeIcon()
        if horiz:
            space = self._icon_size.width()
            tw = rect.width() - space - self._gap
            y = rect.y()
            h = rect.height()
            ix = rect.rigtht() - space if rev_order else rect.x()
            tx = rect.x() if rev_order else ix + space + self._gap
            icon_rect = QtCore.QRectF(ix, y, space, h)
            text_rect = QtCore.QRectF(tx, y, tw, h)
        else:
            space = self._icon_size.height()
            th = rect.height() - space - self._gap
            x = rect.x()
            w = rect.width()
            iy = rect.bottom() - space if rev_order else rect.y()
            ty = rect.y() if rev_order else iy + space + self._gap
            icon_rect = QtCore.QRectF(x, iy, w, space)
            text_rect = QtCore.QRectF(x, ty, w, th)
        icon.setGeometry(icon_rect)
        text.setGeometry(text_rect)
        self._positionCopyButton()


@graphictype("number")
class NumberTile(TextTile):
    _font_family = NUMBER_FAMILY

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._value: Optional[str, int, float] = None
        self._formatter: formatting.NumberFormatter = \
            formatting.NumberFormatter()
        self._formatter.setBriefMode(formatting.BriefMode.auto)

    def textToCopy(self) -> str:
        if self._value is not None:
            return self._wrapTextToCopy(str(self._value))
        else:
            return super().textToCopy()

    def formatter(self) -> formatting.NumberFormatter:
        return self._formatter

    @settable(converter=converters.formatConverter)
    def setFormatter(self, formatter: formatting.NumberFormatter):
        self._formatter = formatter

    @settable(argtype=int)
    def setDecimalPlaces(self, places: int):
        self.formatter().setDecimalPlaces(places)

    @settable("brief")
    def setBriefMode(self, brief: formatting.BriefMode):
        self.formatter().setBriefMode(brief)

    @settable()
    def setTextWeight(self, weight: int):
        self.setWholePartWeight(weight)

    @settable()
    def setWholePartWeight(self, weight: int | str) -> None:
        self.prepareGeometryChange()
        self.formatter().setWholeWeight(weight)
        self.updateGeometry()
        self._updateContents()

    @settable()
    def setFractionPartWeight(self, weight: int | str) -> None:
        self.prepareGeometryChange()
        self.formatter().setFractionWeight(weight)
        self.updateGeometry()
        self._updateContents()

    @settable()
    def setValue(self, value: Union[str, int, float, None]):
        if value is None:
            self.setText("")
            return
        if isinstance(value, str):
            value = float(value)
        self._value = value
        fmt = self.formatter()
        if not isinstance(value, (str, int, float)):
            raise ValueError(f"{self}: {value!r} is not a number")
        fmtnum = fmt.formatNumber(value)
        self.setText(fmtnum.html())


@graphictype("tuple")
class TupleTile(NumberTile):
    # Displays a row of numbers, such as a position or vector
    _font_family = NUMBER_FAMILY

    def __init__(self, parent: QtWidgets.QGraphicsWidget = None):
        self._items: list[controls.StringGraphic] = []
        super().__init__(parent)
        self._gap = 5.0
        self._formatter = formatting.NumberFormatter(decimal_places=8)
        self.setLength(3)
        self.setTextFamily(self._font_family)

    def _makeContentItem(self) -> Optional[QtWidgets.QGraphicsItem]:
        return None

    def _makeTupleItem(self) -> controls.FormattedNumberGraphic:
        item = controls.FormattedNumberGraphic(self)
        item.setFormatter(self._formatter)
        item.setTextSelectable(self._text_selectable)
        return item

    @settable("text_align", argtype=Qt.Alignment)
    def setTextAlignment(self, align: Qt.Alignment):
        for item in self._items:
            item.setTextAlignment(align)

    @settable(converter=converters.textSizeConverter)
    def setTextSize(self, size: int) -> None:
        self.prepareGeometryChange()
        font = QtGui.QFont()
        font.setPixelSize(size)
        for item in self._items:
            item.setFont(font)
        self.updateGeometry()
        self._updateContents()

    @settable()
    def setTextFamily(self, name: str):
        self.prepareGeometryChange()
        font = QtGui.QFont()
        font.setFamily(name)
        for item in self._items:
            item.setFont(font)
        self.updateGeometry()
        self._updateContents()

    @settable("text_color", argtype=QtGui.QColor)
    def setTextColor(self, color: QtGui.QColor) -> None:
        for item in self._items:
            item.setTextColor(color)

    @settable(argtype=int)
    def setLength(self, length: int) -> None:
        self.prepareGeometryChange()
        self._items = [self._makeTupleItem() for _ in range(length)]
        self.updateGeometry()
        self._updateContents()

    def textToCopy(self) -> str:
        text = "; ".join(str(item.number()) for item in self._items)
        return self._wrapTextToCopy(f"[{text}]")

    @settable(converter=converters.formatConverter)
    def setFormatter(self, formatter: formatting.NumberFormatter):
        self.prepareGeometryChange()
        self._formatter = formatter
        for item in self._items:
            item.setFormatter(self._formatter)
        self.updateGeometry()
        self._updateContents()

    def formatter(self) -> formatting.NumberFormatter:
        return self._formatter

    @settable(argtype=int)
    def setDecimalPlaces(self, places: int):
        self.prepareGeometryChange()
        self.formatter().setDecimalPlaces(places)
        self.updateGeometry()
        self._updateContents()

    @settable("brief")
    def setBriefMode(self, brief: formatting.BriefMode):
        self.prepareGeometryChange()
        self.formatter().setBriefMode(brief)
        self.updateGeometry()
        self._updateContents()

    def setTextSelectable(self, selectable: bool) -> None:
        for item in self._items:
            if isinstance(item, controls.TextGraphic):
                item.setTextSelectable(selectable)

    def clearText(self) -> None:
        self.prepareGeometryChange()
        for item in self._items:
            item.setPlainText("")

    @settable(converter=converters.vectorConverter)
    def setValue(self, values: Sequence[float]) -> None:
        self.prepareGeometryChange()
        if not values:
            self.clearText()
            return
        if not isinstance(values, (list, tuple)):
            raise ValueError(values)

        for i, value in enumerate(values):
            self._items[i].setNumber(value)

        self.updateGeometry()
        self._updateContents()

    def _contentSizeHint(self, which: Qt.SizeHint,
                         constraint: QtCore.QSizeF = None) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        if which == Qt.PreferredSize:
            space = self._gap * (len(self._items) - 1)
            col_w = (constraint.width() - space) / 3
            item_sizes = [it.effectiveSizeHint(which, QtCore.QSizeF(col_w, -1))
                          for it in self._items]
            w = sum(sz.width() for sz in item_sizes) + space
            h = max(sz.height() for sz in item_sizes)
            return QtCore.QSizeF(w, h)
        return constraint

    def _updateContents(self):
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
        self._positionCopyButton()

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
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


@graphictype("exploded_matrix")
class ExplodedMatrix(TextTile):
    _labels = ("Trans", "Rot", "Scale")
    _font_family = NUMBER_FAMILY

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        self._label_font_size = 10
        self._label_opacity = 0.66
        self._items: list[list[controls.StringGraphic]] = []
        self._spacing = QtCore.QSizeF(10.0, 5.0)
        super().__init__(parent)
        self._value: Optional[hou.Matrix4] = None
        self._labels_width = 20.0
        # This tile displays a Matrix4, but "exploded", without shears, so we
        # only need 3 rows (translate, rotate scale) and 3 columns (x, y, z) +
        # a label column
        for i in range(3):
            row: list[controls.StringGraphic] = []
            self._items.append(row)
            for j in range(4):
                item = controls.StringGraphic(self)
                item.setFont(self.font())
                row.append(item)
                if j == 0:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    item.setTextSize(self._label_font_size)
                    item.setText(self._labels[i])
                    item.setOpacity(self._label_opacity)
        self._updateSizes()

    def _makeContentItem(self) -> Optional[QtWidgets.QGraphicsItem]:
        return None

    def _labelItems(self) -> Iterable[Graphic]:
        for row in self._items:
            yield row[0]

    def setFont(self, font: QtGui.QFont) -> None:
        super().setFont(font)
        font = self.font()
        lab_font = QtGui.QFont(font)
        lab_font.setPixelSize(self._label_font_size)
        for row in self._items:
            for i, item in enumerate(row):
                item.setFont(lab_font if i == 0 else font)
        self._updateSizes()
        self.updateGeometry()

    @settable(converter=converters.textSizeConverter)
    def setTextSize(self, size: int) -> None:
        font = QtGui.QFont()
        font.setPixelSize(size)
        self.setFont(font)

    @settable(converter=converters.textSizeConverter)
    def setRowLabelTextSize(self, label_size: int) -> None:
        self._label_font_size = label_size
        font = self.font()
        font.setPixelSize(label_size)
        for lab_item in self._labelItems():
            lab_item.setFont(font)
        self._updateSizes()
        self.updateGeometry()

    @settable()
    def setRowLabelOpacity(self, opacity: float) -> None:
        self._label_opacity = opacity
        for lab_item in self._labelItems():
            lab_item.setOpacity(opacity)

    def clear(self) -> None:
        for row in self._items:
            for col in range(1, 4):
                row[col].setText("")

    def textToCopy(self) -> str:
        if self._value:
            return self._wrapTextToCopy(str(self._value))
        else:
            return ""

    @settable()
    def setTextFamily(self, name: str):
        self.prepareGeometryChange()
        font = QtGui.QFont()
        font.setFamily(name)
        for row in self._items:
            for item in row:
                item.setFont(font)
        self.updateGeometry()
        self._updateContents()

    @settable()
    def setValue(self, matrix: hou.Matrix4) -> None:
        try:
            import hou
        except ImportError:
            hou = None

        if hou and isinstance(matrix, hou.Matrix4):
            self._value = matrix
            xploded: dict[str, hou.Vector3] = matrix.explode()
            for i, key in enumerate(("translate", "rotate", "scale")):
                vec = xploded[key]
                row = self._items[i]
                for j in range(3):
                    num = round(vec[j], 2)
                    if key == "rotate":
                        text = f"{num}\xB0"
                    else:
                        text = str(num)
                    row[j + 1].setText(text)
        else:
            self.clear()

    def _contentSizeHint(self, which: Qt.SizeHint,
                         constraint: QtCore.QSizeF = None) -> QtCore.QSizeF:
        row_h = self.font().pixelSize()
        if which == Qt.PreferredSize:
            size = QtCore.QSizeF(max(200.0, constraint.width()), row_h * 3)
        elif which == Qt.MinimumSize:
            size = QtCore.QSizeF(120.0, row_h * 3)
        elif which == Qt.MaximumSize:
            size = QtCore.QSizeF(99999, 99999)
        else:
            size = constraint
        return size

    def _updateSizes(self):
        label_w = 0.0
        for row in self._items:
            label_w = max(label_w, row[0].implicitSize().width())
        self._labels_width = label_w

    def _updateContents(self):
        rect = self.contentsRect()
        h_space = self._spacing.width()
        v_space = self._spacing.height()
        label_w = self._labels_width
        col_w = (rect.width() - label_w) / 4
        row_h = self.font().pixelSize()
        lab_x = rect.x()
        col_x = lab_x + label_w + h_space
        for i, row in enumerate(self._items):
            y = rect.y() + i * (row_h + v_space)
            for j, item in enumerate(row):
                x = lab_x if j == 0 else col_x + (j - 1) * (col_w + h_space)
                w = label_w if j == 0 else col_w
                r = QtCore.QRectF(x, y, w, row_h)
                item.setGeometry(r)
        self._positionCopyButton()


@graphictype("math_matrix")
class MathMatrix(TextTile):
    _font_family = NUMBER_FAMILY

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        self._items: list[list[controls.StringGraphic]] = []
        self._spacing = QtCore.QSizeF(10.0, 5.0)
        super().__init__(parent)
        self._value: Optional[hou.Matrix4] = None
        for i in range(4):
            row: list[controls.StringGraphic] = []
            self._items.append(row)
            for j in range(4):
                item = controls.StringGraphic(self)
                item.setFont(self.font())
                row.append(item)

    def _makeContentItem(self) -> Optional[QtWidgets.QGraphicsItem]:
        return None

    def setFont(self, font: QtGui.QFont) -> None:
        super().setFont(font)
        for row in self._items:
            for i, item in enumerate(row):
                item.setFont(font)
        self.updateGeometry()

    @settable(converter=converters.textSizeConverter)
    def setTextSize(self, size: int) -> None:
        font = QtGui.QFont()
        font.setPixelSize(size)
        self.setFont(font)

    def clear(self) -> None:
        for row in self._items:
            for item in row:
                item.setText("")

    def textToCopy(self) -> str:
        if self._value:
            return self._wrapTextToCopy(str(self._value))
        else:
            return ""

    @settable()
    def setTextFamily(self, name: str):
        self.prepareGeometryChange()
        font = QtGui.QFont()
        font.setFamily(name)
        for row in self._items:
            for item in row:
                item.setFont(font)
        self.updateGeometry()
        self._updateContents()

    @settable()
    def setValue(self, matrix: hou.Matrix4) -> None:
        try:
            import hou
        except ImportError:
            hou = None

        if hou and isinstance(matrix, hou.Matrix4):
            self._value = matrix
            num_rows = matrix.asTupleOfTuples()
            for item_row, num_row in zip(self._items, num_rows):
                for item, num in zip(item_row, num_row):
                    item.setText(str(round(num, 2)))
        else:
            self.clear()

    def _contentSizeHint(self, which: Qt.SizeHint,
                         constraint: QtCore.QSizeF = None) -> QtCore.QSizeF:
        row_h = self.font().pixelSize()
        vspace = self._spacing.height()
        if which == Qt.PreferredSize:
            size = QtCore.QSizeF(max(200.0, constraint.width()),
                                 row_h * 4 + vspace * 3)
        elif which == Qt.MinimumSize:
            size = QtCore.QSizeF(1, row_h * 4)
        elif which == Qt.MaximumSize:
            size = QtCore.QSizeF(99999, 99999)
        else:
            size = constraint
        return size

    def _updateContents(self):
        rect = self.contentsRect()
        h_space = self._spacing.width()
        v_space = self._spacing.height()
        col_w = (rect.width() - h_space * 3) / 4
        row_h = (rect.height() - v_space * 3) / 4
        for i, row in enumerate(self._items):
            y = rect.y() + i * (row_h + v_space)
            for j, item in enumerate(row):
                x = rect.x() + j * (col_w + h_space)
                r = QtCore.QRectF(x, y, col_w, row_h)
                item.setGeometry(r)
        self._positionCopyButton()

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        painter.drawRect(self.contentsRect())


@graphictype("path")
class PathTile(TextTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._weight: Union[str, int] = 700
        self._collapse = False
        self._vars = ("HIP", "JOB", "HOME")
        self._path_str: str = ""

    @settable()
    def setFilenameWeight(self, weight: Union[str, int]):
        self._weight = weight
        self._updateText()

    @settable()
    def setCollapseCommonVars(self, collapse: bool) -> None:
        self._collapse = collapse
        self._updateText()

    @settable()
    def setCommonVars(self, var_names: str | Iterable[str]):
        if isinstance(var_names, str):
            var_names = var_names.split()
        self._vars = tuple(vn.removeprefix("$") for vn in var_names)
        self._updateText()

    @settable()
    def setValue(self, path_str: str):
        path_str = path_str or ""
        self._path_str = self._valuemap.get(path_str, path_str)
        self._updateText()

    def _updateText(self) -> None:
        path = pathlib.PurePosixPath(self._path_str)
        if self._collapse:
            for vname in self._vars:
                if vname in os.environ:
                    vpath = pathlib.PurePosixPath(os.environ[vname])
                    if path.is_relative_to(vpath):
                        path = f"${vname}" / path.relative_to(vpath)
                        break
        html = formatting.markup_path(str(path), filename_weight=self._weight)
        self.setText(html)


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
        self.setContentItem(controls.MarqueeGraphic(self))

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

    def localEnv(self) -> dict[str, Any]:
        return self._content.localEnv()

    def prepChild(self, child: Graphic, data: dict[str, Any]) -> None:
        if self._itemstyle and "style" not in data:
            data["style"] = self._itemstyle
        super().prepChild(child, data)

    @settable()
    def setItemStyle(self, style_name: str):
        self._itemstyle = style_name


class LayoutTile(ContainerTile):
    contentSizeChanged = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._sizes_to_children = False
        self.setContentItem(core.LayoutGraphic(self))
        # arrangement = self._makeArrangement()
        # self._content.setArrangement(arrangement)
        layout = self._makeLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self._content.setLayout(layout)

        self._content.geometryChanged.connect(self._onContentSizeChanged)
        self._content.installEventFilter(self)

        self.setHasHeightForWidth(True)
        self.setSelectable(False)

    def sizesToChildren(self) -> bool:
        return self._sizes_to_children

    def _onContentSizeChanged(self) -> None:
        self.prepareGeometryChange()
        self.contentSizeChanged.emit()
        self.updateGeometry()

    def eventFilter(self, watched: QtWidgets.QGraphicsWidget,
                    event: QtCore.QEvent) -> bool:
        if watched == self._content and event.type() == event.LayoutRequest:
            self._onContentSizeChanged()
        return super().eventFilter(watched, event)

    def _contentSizeHint(self, which: Qt.SizeHint,
                         constraint: QtCore.QSizeF = None) -> QtCore.QSizeF:
        return util.validSizeHint(self._content, which, constraint)

    def _makeArrangement(self) -> layouts.Arrangement:
        raise NotImplementedError

    def _makeLayout(self) -> QtWidgets.QGraphicsLayout:
        arr = self._makeArrangement()
        return layouts.ArrangementLayout(arr)
        # return QtWidgets.QGraphicsLinearLayout(self.default_orientation)

    def addChild(self, item: QtWidgets.QGraphicsLayoutItem):
        self._content.addChild(item)
        self._tiles.append(item)

    @path_element(QtWidgets.QGraphicsLayout)
    def contentLayout(self) -> QtWidgets.QGraphicsLayout:
        return self._content.layout()

    @path_element(layouts.Arrangement)
    def arrangement(self) -> layouts.Arrangement:
        layout = self.contentLayout()
        if isinstance(layout, layouts.ArrangementLayout):
            return layout.arrangement()

    @settable("margins", argtype=QtCore.QMarginsF)
    def setMargins(self, left: Union[QtCore.QMarginsF, float], top=0.0,
                   right=0.0, bottom=0.0) -> None:
        if isinstance(left, QtCore.QMarginsF):
            ms = left
            super().setContentsMargins(ms.left(), ms.top(),
                                       ms.right(), ms.bottom())
        else:
            super().setContentsMargins(left, top, right, bottom)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
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


@graphictype("grid")
class GridLayoutTile(LayoutTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._cols = 4
        self._x = 0
        self._y = 0
        self._positions: dict[int, QtCore.QPoint] = {}
        self._spans: dict[int, QtCore.QSize] = {}

    def _makeLayout(self) -> QtWidgets.QGraphicsLayout:
        return QtWidgets.QGraphicsGridLayout(self)

    def posForItem(self, item: Graphic) -> QtCore.QPoint:
        obj_id = id(item)
        if obj_id not in self._positions:
            self._spans[obj_id] = QtCore.QPoint(self._x, self._y)
            self._x += 1
            if self._x >= self._cols:
                self._x = 0
                self._y += 1
        return self._spans[obj_id]

    def spansForItem(self, item: Graphic) -> QtCore.QSize:
        obj_id = id(item)
        if obj_id not in self._spans:
            self._spans[obj_id] = QtCore.QSize(1, 1)
        return self._spans[obj_id]

    def addChild(self, item: QtWidgets.QGraphicsLayoutItem) -> None:
        layout = self._content.layout()
        pos = self.posForItem(item)
        spans = self.spansForItem(item)
        layout.addItem(item, pos.y(), pos.x(), spans.height(), spans.width())
        self._tiles.append(item)

    @settable()
    def setColumns(self, columns: int) -> None:
        self._cols = columns

    @settable("grid:pos", argtype=QtCore.QPoint, is_parent_method=True)
    def setChildPos(self, item: Graphic, pos: QtCore.QPoint) -> None:
        self._positions[id(item)] = pos

    @settable("grid:x", is_parent_method=True)
    def setChildGridX(self, item: Graphic, x: int) -> None:
        self.posForItem(item).setX(x)

    @settable("grid:x", is_parent_method=True)
    def setChildGridY(self, item: Graphic, y: int) -> None:
        self.posForItem(item).setY(y)

    @settable("grid:cols", argtype=int, is_parent_method=True)
    def setChildColumnSpan(self, item: Graphic, cols: int) -> None:
        self.spanForItem(item).setWidth(cols)

    @settable("grid:rows", argtype=int, is_parent_method=True)
    def setChildRowSpan(self, item: Graphic, rows: int) -> None:
        self.spanForItem(item).setHeight(rows)

    @settable("grid:spans", argtype=QtCore.QSize, is_parent_method=True)
    def setChildSpans(self, item: Graphic, spans: QtCore.QSize) -> None:
        self._spans[id(item)] = spans


@graphictype("line")
class LinearLayoutTile(LayoutTile):
    default_orientation = Qt.Vertical

    # property_aliases = {
    #     "h_space": "arrangement.h_space",
    #     "v_space": "arrangement.v_space",
    #     "spacing": "arrangement.spacing",
    #     "orientation": "arrangement.orientation",
    #     "justify": "arrangement.justify",
    #     "align": "arrangement.align"
    # }
    property_aliases = {
        "h_space": "contentLayout.h_space",
        "v_space": "contentLayout.v_space",
        "align": "contentLayout.align"
    }

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)

    # def _makeArrangement(self) -> layouts.Arrangement:
    #     arr = layouts.LinearArrangement()
    #     arr.setMargins(0, 0, 0, 0)
    #     return arr

    def _makeLayout(self) -> QtWidgets.QGraphicsLayout:
        # arr = self._makeArrangement()
        # return layouts.ArrangementLayout(arr)
        return QtWidgets.QGraphicsLinearLayout(self.default_orientation)

    @settable(argtype=Qt.Orientation)
    def setOrientation(self, orient: Qt.Orientation) -> None:
        self.contentLayout().setOrientation(orient)

    @settable()
    def setSpacing(self, spacing: float) -> None:
        self.contentLayout().setSpacing(spacing)

    @settable("line:stretch", is_parent_method=True)
    def setChildStretch(self, tile: Tile, factor: float) -> None:
        self.contentLayout().setStretchFactor(tile, factor)
        # self.contentArrangement().setStretchFactor(tile, factor)

    @settable("justify")
    def setJustification(self, justify) -> None:
        pass

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.setPen(Qt.red)
    #     painter.drawRect(self.rect())


@graphictype("split")
class SplitTile(LayoutTile):
    property_aliases = {
        "h_space": "arrangement.h_space",
        "v_space": "arrangement.v_space",
        "spacing": "arrangement.spacing",
    }

    def __init__(self, parent: QtWidgets.QGraphicsWidget = None):
        super().__init__(parent=parent)
        self.setBackgroundVisible(False)
        self.setLabelVisible(False)
        self.setHasHeightForWidth(True)

    def _makeArrangement(self) -> layouts.Arrangement:
        arr = layouts.SplitArrangement()
        arr.setMargins(0, 0, 0, 0)
        return arr

    def breakWidth(self) -> float:
        if self._breakwidth > 0:
            return self._breakwidth
        else:
            return self.chartSize() * 3

    @settable()
    def setBreakWidth(self, width: float):
        self.arrangement().setBreakWidth(width)

    @settable("h_split")
    def setHorizontalSplit(self, factor: float) -> None:
        self.arrangement().setHorizontalSplit(factor)

    @settable()
    def setSideWidth(self, width: float) -> None:
        self.arrangement().setSideWidth(width)


@graphictype("card")
class CardTile(LinearLayoutTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self.setLabelBackgroundVisible(False)
        self.background().setVisible(True)
        self.setShadowBlur(10.0)
        self.setShadowColor(QtGui.QColor.fromRgbF(0.0, 0.0, 0.0, 0.33))
        self.setShadowOffset(QtCore.QPointF(0.0, 2.0))
        self.setMargins(10, 10, 10, 10)

    def ancestorCardCount(self) -> int:
        # Number of ancestor cards (not counting self)
        count = 0
        parent = self.parentItem()
        while parent:
            if isinstance(parent, CardTile):
                return parent.ancestorCardCount() + 1
            parent = parent.parentItem()
        return count

    @staticmethod
    def _descendentCardCount(item: QtWidgets.QGraphicsItem) -> int:
        # Max depth of card descendents (INCLUDING THIS ITEM)
        depth = 0
        for subitem in item.childItems():
            depth = max(depth, CardTile._descendentCardCount(subitem))
        if isinstance(item, CardTile):
            depth += 1
        return depth

    def maximumDescendentCardDepth(self) -> int:
        return self._descendentCardCount(self)

    @staticmethod
    def depthToColor(depth: int | str) -> converters.ColorSpec:
        if depth == "lowest" or depth == -2:
            c = ThemeColor.surface_lowest
        elif depth == "low" or depth == -1:
            c = ThemeColor.surface_low
        elif depth == "normal" or depth == 0:
            c = ThemeColor.surface
        elif depth == "high" or depth == 1:
            c = ThemeColor.surface_high
        elif depth == "highest" or depth == 2:
            c = ThemeColor.surface_highest
        else:
            raise ValueError(f"Unknown depth value {depth}")
        return c

    def autoDepth(self) -> int:
        index = self.ancestorCardCount()
        descendents = self.maximumDescendentCardDepth()
        total_depth = index + descendents
        depth = 0
        if total_depth == 2:
            depth = index
        elif total_depth == 4:
            depth = -1 + index
        elif index < 2:
            depth = -2 + index
        elif index >= total_depth - 2:
            depth = index - (total_depth - 2)
        return depth

    @settable()
    def setDepth(self, depth: int | str) -> None:
        bg = self.background()
        c = self.depthToColor(depth)
        bg.setFillColor(c)


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

    def _makeArrangement(self) -> layouts.Arrangement:
        return layouts.Matrix()

    def _makeLayout(self) -> QtWidgets.QGraphicsLayout:
        arr = layouts.Matrix()
        return layouts.ArrangementLayout(arr)

    @path_element(layouts.Matrix)
    def matrix(self) -> layouts.Matrix:
        return self.arrangement()


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

    def _makeArrangement(self) -> layouts.Arrangement:
        arr = layouts.FlowArrangement()
        arr.setSpacing(10.0)
        return arr

    def _makeLayout(self) -> QtWidgets.QGraphicsLayout:
        arr = self._makeArrangement()
        return layouts.ArrangementLayout(arr)

    @path_element(layouts.FlowArrangement)
    def flow(self) -> layouts.FlowArrangement:
        return self.arrangement()


@graphictype("packed_grid")
class PackedGridTile(LayoutTile):
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

    def _makeArrangement(self) -> layouts.Arrangement:
        return layouts.PackedGridArrangement()

    def _makeLayout(self) -> QtWidgets.QGraphicsLayout:
        arr = self._makeArrangement()
        return layouts.ArrangementLayout(arr)

    @path_element(layouts.PackedGridArrangement)
    def grid(self) -> layouts.PackedGridArrangement:
        return self.arrangement()

    @settable("max_cols", argtype=int)
    def setMaximumColumns(self, cols: int):
        self._max_span.setWidth(cols)
        self.updateGeometry()

    @settable("max_rows", argtype=int)
    def setMaximumRows(self, rows: int):
        self._max_span.setHeight(rows)
        self.updateGeometry()

    @settable("grid:pos", argtype=QtCore.QPoint, is_parent_method=True)
    def setChildPos(self, tile: Tile, pos: QtCore.QPoint) -> None:
        self.arrangement().setItemPos(tile, pos)

    @settable("grid:cols", argtype=int, is_parent_method=True)
    def setChildColumnSpan(self, tile: Tile, cols: int) -> None:
        self.arrangement().setItemColumnSpan(tile, cols)

    @settable("grid:rows", argtype=int, is_parent_method=True)
    def setChildRowSpan(self, tile: Tile, rows: int) -> None:
        self.arrangement().setItemRowSpan(tile, rows)

    @settable("grid:spans", argtype=QtCore.QSize, is_parent_method=True)
    def setChildSpans(self, tile: Tile, spans: QtCore.QSize) -> None:
        self.arrangement().setItemSpans(tile, spans)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
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
    contentSizeChanged = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self.setHasHeightForWidth(True)

        self._visible = True
        self.setContentItem(views.DataLayoutGraphic(self))
        self._content.setArrangement(self._makeArrangement())
        self._content.visibleChanged.connect(self._updateVisibility)
        self._content.geometryChanged.connect(self._onContentSizeChanged)
        self._content.installEventFilter(self)
        self.setTextCopyable(True)

    def textToCopy(self) -> str:
        return self._wrapTextToCopy(self._content.textToCopy())

    def _onContentSizeChanged(self) -> None:
        self.prepareGeometryChange()
        self.contentSizeChanged.emit()
        self.updateGeometry()

    def eventFilter(self, watched: QtWidgets.QGraphicsWidget,
                    event: QtCore.QEvent) -> bool:
        if watched == self._content and event.type() == event.LayoutRequest:
            self._onContentSizeChanged()
        return super().eventFilter(watched, event)

    def dataProxy(self) -> Optional[core.DataGraphic]:
        return self._content

    def localEnv(self) -> dict[str, Any]:
        return super().localEnv() | {"model": self.dataProxy().model()}

    def _makeArrangement(self) -> layouts.Arrangement:
        raise NotImplementedError

    @path_element(layouts.Arrangement)
    def arrangement(self) -> layouts.Arrangement:
        return self._content.arrangement()

    @settable()
    def setHideWhenEmpty(self, hide_when_empty: bool):
        self._content.setHideWhenEmpty(hide_when_empty)
        self._updateVisibility()

    @settable()
    def setVisible(self, visible: bool) -> None:
        self._visible = visible
        self._updateVisibility()

    def _updateVisibility(self) -> None:
        visible = self._visible and self._content.shouldBeVisible()
        cur_vis = self.isVisible()
        if visible != cur_vis:
            super().setVisible(visible)

    def _contentSizeHint(self, which: Qt.SizeHint,
                         constraint: QtCore.QSizeF = None) -> QtCore.QSizeF:
        return util.validSizeHint(self._content, which, constraint)


@graphictype("data_line")
class DataLineTile(DataLayoutTile):
    property_aliases = {
        "h_space": "arrangement.h_space",
        "v_space": "arrangement.v_space",
        "spacing": "arrangement.spacing",
        "orientation": "arrangement.orientation",
        "justify": "arrangement.justify",
        "align": "arrangement.align"
    }

    def _makeArrangement(self) -> layouts.Arrangement:
        arrangement = layouts.LinearArrangement()
        return arrangement


@graphictype("data_matrix")
class DataMatrixTile(DataLayoutTile):
    property_aliases = {
        "h_space": "matrix.h_space",
        "v_space": "matrix.v_space",
        "spacing": "matrix.spacing",
        "margins": "matrix.margins",
        "min_column_width": "matrix.min_column_width",
        "max_column_width": "matrix.max_column_width",
        "row_height": "matrix.row_height",
        "orientation": "matrix.orientation",
        "column_stretch": "matrix.column_stretch",
        "fill_stretch": "matrix.fill_stretch",
    }

    def _makeArrangement(self) -> layouts.Arrangement:
        arrangement = layouts.Matrix()
        return arrangement

    @path_element(layouts.Matrix)
    def matrix(self) -> layouts.Matrix:
        return self.arrangement()

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.setPen(Qt.red)
    #     painter.drawRect(self.rect())


@graphictype("data_key_value")
class DataKeyValueTile(DataLayoutTile):
    property_aliases = {
        "h_space": "arrangement.h_space",
        "v_space": "arrangement.v_space",
        "spacing": "arrangement.spacing",
        "margins": "arrangement.margins",
    }

    @settable()
    def setKeyItemName(self, name: str) -> None:
        self.arrangement().setKeyItemName(name)

    @settable()
    def setValueItemName(self, name: str) -> None:
        self.arrangement().setValueItemName(name)

    def _makeArrangement(self) -> layouts.Arrangement:
        return layouts.KeyValueArrangement()

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.setPen(Qt.red)
    #     painter.drawRect(self.rect())


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
    property_aliases = {
        "use_sections": "contentsItem.use_sections",
        "section_key": "contentsItem.section_key",
        "measure_values": "contentsItem.measure_values",
        "dynamic_item_width": "contentsItem.dynamic_item_width",
        "on_copy_item_text": "contentsItem.on_copy_item_text",
        "prewarm": "contentsItem.prewarm",
        "h_space": "matrix.h_space",
        "v_space": "matrix.v_space",
        "spacing": "matrix.spacing",
        "margins": "matrix.margins",
        "min_column_width": "matrix.min_column_width",
        "max_column_width": "matrix.max_column_width",
        "row_height": "matrix.row_height",
        "orientation": "matrix.orientation",
        "column_stretch": "matrix.column_stretch",
        "fill_stretch": "matrix.fill_stretch",
    }

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        # self.setContentItem(views.ListView(self))
        self.setContentItem(self._makeContentItem())
        self._visible = True

        self.setHasHeightForWidth(True)
        self._content.contentSizeChanged.connect(self._onContentResize)
        self._content.visibleChanged.connect(self._updateVisibility)

        self._content.installEventFilter(self)
        self.setTextCopyable(True)

    def _makeContentItem(self) -> Graphic:
        return views.DataListGraphic(self)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._updateContents()

    def eventFilter(self, watched: QtWidgets.QGraphicsWidget,
                    event: QtCore.QEvent) -> bool:
        if watched == self._content and event.type() == event.LayoutRequest:
            self.prepareGeometryChange()
            self.updateGeometry()
            # self.updateContents()
        return super().eventFilter(watched, event)

    def _updateContents(self):
        if self._content:
            crect = self.contentsRect()
            self._content.setGeometry(crect)

    def dataProxy(self) -> Optional[Graphic]:
        return self._content

    def textToCopy(self) -> str:
        return self._wrapTextToCopy(self._content.textToCopy())

    def localEnv(self) -> dict[str, Any]:
        return self._content.localEnv()

    @path_element(views.DataListGraphic)
    def viewItem(self) -> views.DataListGraphic:
        return self._content

    @path_element(Graphic)
    def viewContentItem(self) -> Graphic:
        # return self._content.contentsItem()
        return self._content

    @path_element(layouts.Matrix)
    def matrix(self) -> layouts.Matrix:
        return self.viewContentItem().matrix()

    def _onContentResize(self) -> None:
        self.prepareGeometryChange()
        current_size = self.size()
        base_size = self._baseSize()
        width = self.contentsRect().width()
        self.updateGeometry()

    # @settable("section_key")
    # def setSectionKeyDataID(self, col_id: int|str) -> None:
    #     self._content.setSectionKeyDataID(col_id)

    @settable()
    def setValueFontMap(self, value_font_map: dict[str, QtGui.QFont]) -> None:
        content: views.DataListGraphic = self.contentItem()
        content.setValueFontMap(value_font_map)

    @settable()
    def setHideWhenEmpty(self, hide_when_empty: bool):
        self._content.setHideWhenEmpty(hide_when_empty)
        self._updateVisibility()

    @settable()
    def setVisible(self, visible: bool) -> None:
        self._visible = visible
        self._updateVisibility()

    def _updateVisibility(self) -> None:
        visible = self._visible and self._content.shouldBeVisible()
        cur_vis = self.isVisible()
        if visible != cur_vis:
            super().setVisible(visible)


@graphictype("editor")
class EditorTile(Tile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._size_to_content = True
        self._last_doc_height = 0.0
        self._saved = ""

        self._editor = QtWidgets.QPlainTextEdit()
        self._editor.setVerticalScrollBar(widgets.ScrollBar(Qt.Vertical))
        self._editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._editor.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # self._editor.setFrameStyle(self._editor.NoFrame)
        # self._editor.setMinimumHeight(60)
        self._editor.installEventFilter(self)

        self.setContentWidget(self._editor, transparent=False)
        self._commit_expr: Optional[config.Expr] = None

        self.setHasHeightForWidth(True)
        self._editor.textChanged.connect(self._onTextChanged)

    def eventFilter(self, watched: QtCore.QObject,
                    event: QtCore.QEvent) -> bool:
        if watched == self._editor:
            etype = event.type()
            if etype == event.FocusIn:
                self.saveContent()
            elif etype == event.FocusOut:
                self.commitChanges()
            elif etype == event.KeyPress and event.key() == Qt.Key_Escape:
                self.revertChanges()
        return super().eventFilter(watched, event)

    def localEnv(self) -> dict[str, Any]:
        return {
            "text": self.plainText()
        }

    def document(self) -> QtGui.QTextDocument:
        return self._editor.document()

    def saveContent(self) -> None:
        self._saved = self.text()

    def commitChanges(self) -> None:
        self._evaluateExpr(self._commit_expr)

    def revertChanges(self) -> None:
        self.setText(self._saved)

    @path_element(QtWidgets.QTextEdit)
    def editorWidget(self) -> QtWidgets.QTextEdit:
        return self._editor

    def text(self) -> str:
        return self._editor.toPlainText()

    def plainText(self) -> str:
        return self._editor.toPlainText()

    @settable()
    def setText(self, text: str) -> None:
        self._editor.setPlainText(text)
        self._updateContents()

    def sizingToContent(self) -> bool:
        return self._size_to_content

    @settable(argtype=bool)
    def setSizeToContent(self, size_to_content: bool) -> None:
        self._size_to_content = size_to_content
        self._updateContents()

    @settable("on_commit")
    def setOnCommitExpression(self, expr: Union[str, dict, config.PythonExpr]
                              ) -> None:
        expr = config.PythonExpr.fromData(expr)
        self._commit_expr = expr

    @settable("placeholder")
    def setPlaceholderText(self, text: str) -> None:
        self._editor.setPlaceholderText(text)

    def isReadOnly(self) -> bool:
        return self._editor.isReadOnly()

    @settable(argtype=bool)
    def setReadOnly(self, read_only: bool) -> None:
        self._editor.setReadOnly(read_only)
        self._editor.setAutoFillBackground(not read_only)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        size = super().sizeHint(which, constraint)
        return size

    def _contentSizeHint(self, which: Qt.SizeHint,
                         constraint: QtCore.QSizeF = None) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        cw = constraint.width()
        if which == Qt.PreferredSize:
            if self.sizingToContent():
                doc = self.document().clone()
                if cw > 0:
                    doc.setTextWidth(cw)
                    h = doc.size().height() + 28.0
                    h = max(28.0, h)
                else:
                    doc.setTextWidth(-1)
                    h = doc.size().height()
                return QtCore.QSizeF(cw, h)
        return super()._contentSizeHint(which, constraint)

    def _onTextChanged(self) -> None:
        if self.sizingToContent():
            self.prepareGeometryChange()
            doc = self._editor.document()
            h = doc.size().height()
            if h != self._last_doc_height:
                self.updateGeometry()
            self._last_doc_height = h

    def _updateContents(self) -> None:
        rect = self.contentsRect()
        content = self.contentItem()
        content.setGeometry(rect)
        h = self._editor.document().size().height()
        if h <= content.size().height():
            self._editor.verticalScrollBar().setValue(0)
        self._last_doc_height = h

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.setPen(Qt.red)
    #     painter.drawRect(self.rect())


@graphictype("switch")
class SwitchTile(Tile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self.setContentItem(controls.LabeledSwitchGraphic())

    def text(self) -> str:
        return self.contentItem().text()

    @settable()
    def setText(self, text: str) -> None:
        self.contentItem().setText(text)


@graphictype("chart")
class ChartTile(Tile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._autotext = False
        self._formatter = formatting.NumberFormatter()
        self._model = charts.makeChartModel()
        # If setValues() or setTotal() are called before setChartItem(),
        # remember the values so we can apply them when we have a chart
        self._values: Optional[Sequence[float]] = None
        self._total: float = 1.0

    def chart(self) -> Optional[charts.ChartGraphic]:
        return self.contentItem()

    @settable("chart", argtype=charts.ChartGraphic)
    def setChartItem(self, chart: Graphic) -> None:
        if self._content:
            old_chart = self._content
            # old_chart.setParentItem(None)
            old_chart.hide()

        chart.setModel(self.model())
        chart.setParentItem(self)
        if self._values:
            chart.setValues(self._values)
            chart.setTotal(self._total)
        self.setContentItem(chart)
        self._updateContents()

    def model(self) -> QtCore.QAbstractItemModel:
        return self._model

    def setModel(self, model: Optional[QtCore.QAbstractItemModel]) -> None:
        self._model = model
        chart = self.chart()
        if chart:
            chart.setModel(model)

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
        self._values = values
        chart = self.chart()
        if chart:
            chart.setValues(values)

    @settable()
    def setTotal(self, total: float):
        chart = self.chart()
        self._total = total
        if chart:
            chart.setTotal(total)

    def _updateContents(self):
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


@graphictype("shuffle")
class ShuffleTile(Tile):
    def __init__(self, parent: QtWidgets.QGraphicsWidget = None):
        super().__init__(parent=parent)
        self.setLabelVisible(False)
        self.background().hide()
        self.setIgnoreMargins(True)

        self.setContentItem(core.LayoutGraphic(self))
        layout = QtWidgets.QGraphicsLinearLayout(Qt.Vertical)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5.0)
        self._content.setLayout(layout)

        self._container = containers.ShuffleContainerGraphic()
        self._content.addChild(self._container)

        self._dots = controls.TabDotsGraphic()
        self._dots.setFixedHeight(16.0)
        self._content.addChild(self._dots)

        self._container.currentIndexChanged.connect(self._dots.setCurrentIndex)
        self._dots.dotClicked.connect(self._container.setCurrentIndex)

    def addChild(self, item: QtWidgets.QGraphicsItem) -> None:
        self._container.addChild(item)
        self._dots.setCount(self._container.count())
        self.updateGeometry()


class ExpandingTile(Tile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._open_rot = 0
        self._closed_rot = -90
        self._tile_label_toggles = True

        self._setupButton()
        super().setContentItem(self._makeExpandingItem())

        self.label().installEventFilter(self)
        self.setHasHeightForWidth(True)

        self._content.geometryChanged.connect(self.updateGeometry)
        self._content.installEventFilter(self)
        self._updateState()

    def _makeExpandingItem(self) -> Graphic:
        raise NotImplementedError

    def _setupButton(self) -> None:
        self._button = controls.ButtonGraphic()
        self._button.setTransparent(True)
        self._button.setGlyph(glyphs.FontAwesome.chevron_down)
        self._button.setFontSize(converters.LABEL_SIZE)
        self._button.setFixedSize(QtCore.QSizeF(24, 24))
        self._button.clicked.connect(lambda: self.toggle(animated=True))
        self.setLabelButton(self._button, at_start=True)

    def eventFilter(self, watched: QtWidgets.QGraphicsWidget,
                    event: QtCore.QEvent) -> bool:
        if watched == self._label and \
                event.type() == event.GraphicsSceneMousePress and \
                self._tile_label_toggles:
            self._button.click()
        elif watched == self._content and event.type() == event.LayoutRequest:
            self.updateGeometry()
        return super().eventFilter(watched, event)

    @path_element(Graphic)
    def contentItem(self) -> Graphic:
        return self._content.contentItem()

    @settable(argtype=Graphic)
    def setContentItem(self, item: Graphic) -> None:
        self._content.setContentItem(item)
        self.updateGeometry()

    @path_element(controls.ToolButtonGraphic)
    def button(self) -> controls.ToolButtonGraphic:
        return self._button

    def localEnv(self) -> dict[str, Any]:
        return self.contentItem().localEnv()

    def textToCopy(self) -> str:
        return self.contentItem().textToCopy()

    def updateableChildren(self) -> Iterable[Graphic]:
        if self._content:
            yield self._content

    def toggle(self, *, animated=False) -> None:
        self._content.toggle(animated=animated)
        self.updateGeometry()

    def isOpen(self) -> bool:
        return self._content.isOpen()

    @settable(argtype=bool)
    def setOpen(self, open: bool, animated=False) -> None:
        animated = animated and not self.animationDisabled()
        self._content.setOpen(open, animated=animated)
        self.updateGeometry()

    def _updateState(self, animated=True) -> None:
        animated = animated and not self.animationDisabled()
        rot = self._open_rot if self.isOpen() else self._closed_rot
        if animated:
            self._button.animateRotation(rot)
        else:
            self._button.setRotation(rot)


@graphictype("details")
class DetailsTile(ExpandingTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        # The tile only collapses properly if it has no margins; you need to
        # apply margins to the content item instead
        self.setInnerMargins(QtCore.QMarginsF(0, 0, 0, 0))

    def _makeExpandingItem(self) -> Graphic:
        rollup = containers.RollUpGraphic(self)
        rollup.setOpen(True, animated=False)
        rollup.openStateChanged.connect(self._updateState)
        return rollup


@graphictype("expanding_stack")
class ExpandingStackTile(ExpandingTile):
    def __init__(self, parent: QtWidgets.QGraphicsWidget = None):
        super().__init__(parent=parent)
        self.background().hide()
        self.setIgnoreMargins(True)

    def _makeExpandingItem(self) -> Graphic:
        stack = containers.ExpandingStackGraphic(self)
        stack.openStateChanged.connect(self._updateState)
        return stack

    def addChild(self, item: QtWidgets.QGraphicsItem) -> None:
        self._content.addChild(item)
        self.updateGeometry()
        self._content.update()


@graphictype("truncated")
class TruncatedTile(ExpandingTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._visible = True
        self._tile_label_toggles = False
        self._colors_changed = False
        self._shrinkable = True
        self._fade_color = themes.ThemeColor.surface
        self._updateColors()

    _fade_color: QtGui.QColor = core.DynamicColor()

    def _makeExpandingItem(self) -> containers.TruncatedGraphic:
        trunc = containers.TruncatedGraphic(self)
        trunc.visibleChanged.connect(self._updateVisibility)
        return trunc

    def updateableChildren(self) -> Iterable[Graphic]:
        yield self.contentItem()

    def _setupButton(self) -> None:
        self._fade_height = 24.0
        self._fade = QtWidgets.QGraphicsRectItem(self)
        self._fade.setPen(Qt.NoPen)
        self._fade.setZValue(2)

        # Create the "Show N more..." button
        self._button_align = Qt.AlignCenter
        self._button = controls.ToolButtonGraphic(self)
        self._button.setCornerRadius(0)
        self._button.setPillShaped(True)
        self._button.setFlat(True)
        self._button.setLabelMargins(QtCore.QMarginsF(8, 1, 8, 1))
        self._button.setHaloEnabled(False)
        self._button.setZValue(3)
        self._button.setTextSize(styling.TextSize.xsmall)
        self._button.setFillColor(ThemeColor.bg)
        self._button.setTextColor(ThemeColor.secondary)
        self._button.setBorderColor(ThemeColor.secondary_dim)
        self._button.setBorderWidth(1.0)
        self._button.clicked.connect(self._onButtonClicked)

    def dataProxy(self) -> Optional[Graphic]:
        return self.contentItem()

    def _onButtonClicked(self) -> None:
        self.setTruncated(False, animated=True)

    def canShrink(self) -> bool:
        return self._shrinkable

    def shrinkHeightTo(self, height: float) -> None:
        base_size = self._baseSize()
        self._content.shrinkHeightTo(height - base_size.height())
        self._updateState(animated=False)

    def unshrink(self) -> None:
        self.setTruncated(False)

    def isTruncated(self) -> bool:
        content: containers.TruncatedGraphic = self._content
        return content.isTruncated() and content.truncatedItemCount()

    @settable(argtype=bool)
    def setShrinkable(self, shrinkable: bool) -> None:
        self._shrinkable = shrinkable

    @settable("more_glyph")
    def setMoreGlyph(self, glyph: glyphs.Glyph) -> None:
        self._button.setGlyph(glyph)

    def shrunkenMinimumHeight(self) -> float:
        base_height = self._baseSize().height()
        smh = self._content.shrunkenMinimumHeight()
        return max(base_height + smh, self.minimumHeight())

    @settable("shrink_min")
    def setShrunkenMinimumHeight(self, height: float) -> None:
        self._content.setShrunkenMinimumHeight(height)
        self.updateGeometry()

    @settable("button_color")
    def setButtonColor(self, color: converters.ColorSpec) -> None:
        self._fade_color = color
        self._colors_changed = True

    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == event.PaletteChange:
            self._colors_changed = True

    def setTruncated(self, truncated: bool, *, animated=False) -> None:
        animated = animated and not self.animationDisabled()
        self._content.setTruncated(truncated, animated=animated)
        self._updateState(animated=animated)

    def truncatedItemCount(self) -> int:
        return self._content.truncatedItemCount()

    def _updateState(self, animated=True) -> None:
        trunc = self.isTruncated()
        button_opacity = 1.0 if trunc else 0.0
        if animated:
            self._button.fadeTo(button_opacity)
        else:
            self._button.setOpacity(button_opacity)

    def _updateColors(self) -> None:
        self._colors_changed = False
        gradient = QtGui.QLinearGradient(0.0, 0.0, 0.0, 1.0)
        gradient.setCoordinateMode(gradient.ObjectMode)
        gradient.setColorAt(0.0, Qt.transparent)
        gradient.setColorAt(0.5, self._fade_color)
        gradient.setColorAt(1.0, self._fade_color)
        brush = QtGui.QBrush(gradient)
        self._fade.setBrush(brush)

    def _updateContents(self) -> None:
        rect = self.rect()
        self._positionCopyButton()
        if self._content:
            self._content.setGeometry(self.contentsRect())

        frect = QtCore.QRectF(
            rect.x(), rect.bottom() - self._fade_height,
            rect.width(), self._fade_height
        )
        self._fade.setRect(frect)

        button = self._button
        bsize = button.implicitSize()
        button.setGeometry(util.alignedRectF(
            self.layoutDirection(), self._button_align, bsize, frect
        ))

        # The user may resize so the truncated count changes, or the view isn't
        # even truncated anymore, so we need to update that stuff here
        trunc = self.isTruncated()
        if trunc:
            trunc_count = self.truncatedItemCount()
            self._button.setText(f"Show {trunc_count} More")
        self._button.setOpacity(1.0 if trunc else 0.0)
        self._fade.setVisible(trunc)

    @settable()
    def setVisible(self, visible: bool) -> None:
        self._visible = visible
        self._updateVisibility()

    def _updateVisibility(self) -> None:
        visible = self._visible and self._content.shouldBeVisible()
        cur_vis = self.isVisible()
        if visible != cur_vis:
            super().setVisible(visible)

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        if self._colors_changed:
            self._updateColors()
        super().paint(painter, option, widget)


@graphictype("side_chart")
class ChartSwitchTile(Tile):
    def __init__(self, parent: QtWidgets.QGraphicsWidget = None):
        super().__init__(parent=parent)
        self._setupModel()
        self._chart: Optional[charts.ChartGraphic] = None
        self._chartsize = 48.0
        self._space = 10.0
        self._breakwidth = -1

        self.setHasHeightForWidth(True)
        self.setAcceptHoverEvents(True)

    def chartItem(self) -> charts.ChartGraphic:
        return self._chart

    @settable("chart", argtype=charts.ChartGraphic)
    def setChartItem(self, chart: charts.ChartGraphic):
        self.prepareGeometryChange()
        self._chart = chart
        self.updateGeometry()
        self._updateContents()

    def chartSize(self) -> float:
        return self._chartsize

    def setChartSize(self, extent: float):
        self.prepareGeometryChange()
        self._chartsize = extent
        self.updateGeometry()
        self._updateContents()

    def breakWidth(self) -> float:
        if self._breakwidth > 0:
            return self._breakwidth
        else:
            return self.chartSize() * 3

    @settable()
    def setBreakWidth(self, width: float):
        self._breakwidth = width

    def isVertical(self, width: float) -> bool:
        return width < self.breakWidth()

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
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
            vert = self.isVertical(constraint_width)
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

    @settable(argtype=bool)
    def setChartVisible(self, visible: bool):
        self.chartItem().setVisible(visible)

    # @settable()
    # def setChartText(self, text: str):
    #     self.chart().setText(str(text))
    #
    # @settable()
    # def setChartTextSize(self, size: int):
    #     self.chart().setTextSize(size)
    #
    # @settable()
    # def setChartValue(self, value: float):
    #     self.chart().setValue(value)
    #
    # @settable()
    # def setChartTotal(self, total: float):
    #     self.chart().setTotal(total)

    def _updateContents(self):
        rect = self.contentsRect()
        chart = self.chartItem()
        content = self.contentItem()
        if not (chart or content):
            return

        has_chart = chart and chart.isVisible()
        chart_extent = self.chartSize() if has_chart else 0.0
        offset = chart_extent + self._space if has_chart else 0.0
        vert = self.isVertical(rect.width())
        if vert:
            cr = QtCore.QRectF(rect.topLeft(),
                               QtCore.QSizeF(rect.width(), chart_extent))
            tr = QtCore.QRectF(rect.x(), rect.y() + offset,
                               rect.width(), rect.height() - offset)
        else:
            cr = QtCore.QRectF(rect.topLeft(),
                               QtCore.QSizeF(chart_extent, chart_extent))
            tr = QtCore.QRectF(rect.x() + offset, rect.y(),
                               rect.width() - offset, rect.height())
        if chart:
            chart.setGeometry(cr)
        if content:
            content.setGeometry(tr)


@graphictype("chart_table")
class ChartTableTile(ChartSwitchTile):
    def __init__(self, parent: QtWidgets.QGraphicsWidget = None):
        super().__init__(parent=parent)
        self._hide_when_empty = False
        self._sorting = False
        self._sortcol = 0
        self._sortdir = Qt.AscendingOrder
        self._value_key = None
        self.setContentItem(self._setupContent())

        chart = self.chartItem()
        content = self.contentItem()
        if isinstance(content, views.DataLayoutGraphic):
            chart.setInteractive(True)
            chart.rowHighlighted.connect(content.setHighlightedRow)

            content.setHoverHighlighting(True)
            content.rowHighlighted.connect(chart.setHighlightedRow)

    # def _setupContent(self) -> QtWidgets.QGraphicsWidget:
    #     content = models.ChartTableGraphicWidget(self)
    #     content.setFont(self.contentFont())
    #     content.setDecimalPlaces(1)
    #     content.setModel(self._proxy)
    #     return content
    #
    # def _setupChart(self) -> charts.Chart:
    #     chart = super()._setupChart()
    #     chart.setModel(self._proxy)
    #     return chart

    # def _setupModel(self):
    #     return
    #     self._source = models.ChartTableModel()
    #     self._proxy = models.ChartTableSortFilterModel()
    #     self._proxy.setSourceModel(self._source)

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.setPen(Qt.red)
    #     painter.drawRect(self._content.geometry())

    @settable()
    def setHideWhenEmpty(self, hide_when_empty: bool):
        self._hide_when_empty = hide_when_empty

    def breakWidth(self) -> float:
        bw = self.chartSize()
        if self._content:
            bw += self._content.minimumColumnWidth()
        return bw

    # @settable("min_column_width")
    # def setMinimumColumnWidth(self, width: float) -> None:
    #     table: models.ChartTableGraphicWidget = self._content
    #     table.setMinimumColumnWidth(width)
    #
    # @settable("max_column_width")
    # def setMaximumColumnWidth(self, width: float) -> None:
    #     table: models.ChartTableGraphicWidget = self._content
    #     table.setMaximumColumnWidth(width)
    #
    # @settable()
    # def setRowHeight(self, height: float) -> None:
    #     table: models.ChartTableGraphicWidget = self._content
    #     table.setRowHeight(height)
    #
    # @settable()
    # def setColumnGap(self, gap: float) -> None:
    #     table: models.ChartTableGraphicWidget = self._content
    #     table.setColumnGap(gap)
    #
    # @settable(argtype=bool)
    # def setItemDecorationsVisible(self, visible: bool):
    #     table: models.ChartTableGraphicWidget = self._content
    #     table.setItemDecorationsVisible(visible)

    # @settable()
    # def setValueKey(self, key: str):
    #     self._value_key = key
    #
    # def formatter(self) -> formatting.NumberFormatter:
    #     return self._content.formatter()
    #
    # @settable(converter=converters.formatConverter)
    # def setFormatter(self, formatter: formatting.NumberFormatter):
    #     table: models.ChartTableGraphicWidget = self._content
    #     table.setFormatter(formatter)

    # @settable()
    # def setDecimalPlaces(self, places: int) -> None:
    #     table: models.ChartTableGraphicWidget = self._content
    #     table.formatter().setDecimalPlaces(places)

    def setModel(self, model: models.ChartTableModel):
        table: models.ChartTableGraphicWidget = self._content
        self._source = model
        self._proxy.setSourceModel(self._source)
        self._chart.setModel(self._proxy)
        table.setModel(self._proxy)

    def model(self) -> models.ChartTableModel:
        return self._proxy

    # def sortEnabled(self) -> bool:
    #     return self._sorting
    #
    # @settable("sorted")
    # def setSortEnabled(self, sort: bool):
    #     self._sorting = sort

    # @settable()
    # def setKeyOrder(self, keys: Sequence[str]):
    #     self._source.setKeyOrder(keys)
    #
    # @settable()
    # def setIncludeKeys(self, keys: Collection[str]):
    #     if isinstance(keys, str):
    #         keys = (keys,)
    #     self._source.setIncludeKeys(keys)
    #
    # @settable()
    # def setExcludeKeys(self, keys: Collection[str]):
    #     if isinstance(keys, str):
    #         keys = (keys,)
    #     self._source.setExcludeKeys(keys)

    # @settable()
    # def setKeyLabelMap(self, mapping: Mapping[str, str]):
    #     self._source.setKeyLabelMap(mapping)
    #
    # @settable("rows")
    # def setRowsFromData(self, rows: models.DataSource):
    #     rows = models.conditionChartData(
    #         rows, value_key=self._value_key
    #     )
    #     self._source.setValues(rows)
    #     self._resort()
    #     self._chart.repaint()
    #     if self._hide_when_empty:
    #         self.setVisible(
    #             rows and (self.showingZero() or any(v for k, v in rows))
    #         )

    # @settable()
    # def setTotal(self, total: float):
    #     self._chart.setTotal(total)
    #
    # def showingZero(self) -> bool:
    #     return self._proxy.showingZero()
    #
    # @settable()
    # def setShowZero(self, show: bool):
    #     self._proxy.setShowZero(show)
    #
    # @settable()
    # def setSortColumn(self, column: int):
    #     self._sortcol = column
    #     self._resort()
    #
    # def setSortRole(self, role: int):
    #     self._proxy.setSortRole(role)
    #     self._resort()
    #
    # @settable()
    # def setReversed(self, reverse: bool):
    #     order = Qt.DescendingOrder if reverse else Qt.AscendingOrder
    #     self.setSortOrder(order)
    #
    # def setSortOrder(self, direction: Qt.SortOrder):
    #     self._sortdir = direction
    #     self._resort()
    #
    # def _resort(self):
    #     if self._sorting:
    #         self._proxy.sort(self._sortcol, self._sortdir)


# @graphictype("xpu_devices")
# class XpuDeviceTile(ChartTableTile):
#     def __init__(self, parent: QtWidgets.QGraphicsItem = None):
#         super().__init__(parent)
#
#     def _setupContent(self) -> QtWidgets.QGraphicsWidget:
#         content = models.XpuDeviceGraphicsWidget(self)
#         content.setFont(self.contentFont())
#         content.setModel(self._model)
#         return content
#
#     def _setupModel(self):
#         self._model = models.XpuDeviceModel()
#
#     def _setupChart(self) -> charts.Chart:
#         chart = charts.StackedDonutChart()
#         chart.setAngleAndGap(90.0, 0.0)
#         chart.setInteractive(False)
#         chart.setNormalization(models.FractionOfSum())
#         chart.setPenWidth(0.125)
#         chart.setPenCapStyle(Qt.FlatCap)
#         chart.setTrackVisible(False)
#         chart.setModel(self._model)
#         return chart
#
#     def breakWidth(self) -> float:
#         return 200.0
#
#     @settable("rows")
#     def setRowsFromData(self, rows: list[dict[str, Any]]) -> None:
#         self._model.setFromData(rows)
#         self.updateContents()
#
#     def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
#                  ) -> QtCore.QSizeF:
#         s = super().sizeHint(which, constraint)
#         return s
#
#     # def setGeometry(self, rect: QtCore.QRectF) -> None:
#     #     super().setGeometry(rect)


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
        rect = self.rect().marginsRemoved(self._inner_margins)
        pixmap = self._pixmap
        if not pixmap:
            return

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
                pixmap = pixmap.scaledToWidth(int(rect.width()),
                                              Qt.SmoothTransformation)
            else:
                pixmap = pixmap.scaledToHeight(int(rect.height()),
                                               Qt.SmoothTransformation)
            size = pixmap.size()

        if size.width() < rect.width() or size.height() < rect.height():
            rect = util.alignedRectF(self.layoutDirection(), self._alignment,
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
        self._logo_item = core.makeProxyItem(self, self._logo_widget)
        self._text_item = controls.TextGraphic(self)
        self._text_item.setFont(self.contentFont())

        self._text_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    @settable()
    def setText(self, html: str) -> None:
        self._text_item.setHtml(html)

    @settable(converter=converters.textSizeConverter)
    def setTextSize(self, size: int) -> None:
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
        self._updateContents()

    @settable()
    def setGap(self, gap: float):
        self._gap = gap
        self._updateContents()

    @settable()
    def setValue(self, text: str) -> None:
        self.setText(text)

    def _updateContents(self):
        rect = self.contentsRect()
        w = self._logo_widget
        gap = self._gap
        img_align = self._imagealign
        img_size = QtCore.QSizeF(w.width(), w.height())
        img_rect = util.alignedRectF(
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
        self._updateContents()


@graphictype("houdini_icon")
class HoudiniIconTile(LogoTile):
    @settable()
    def setIconName(self, name: str) -> None:
        import hou
        try:
            icon = hou.qt.Icon(name, 256, 256)
        except hou.OperationFailed:
            pixmap = QtGui.QPixmap(256, 256)
            pixmap.fill(Qt.transparent)
        else:
            pixmap = icon.pixmap(256, 256)
        self.setPixmap(pixmap)
        self._updateContents()


@graphictype("blank")
class BlankTile(TextTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self.setLabelVisible(False)
        self.setTextSize(converters.LABEL_SIZE)
        self.setTextColor(QtGui.QPalette.PlaceholderText)
        self.setTextAlignment(Qt.AlignCenter)
        self.setContentsMargins(0, 0, 0, 0)
        self.background().setVisible(False)

    @settable()
    def setText(self, html: str) -> None:
        super().setText(html)
        self._content.setVisible(bool(html))


@graphictype("surface")
class SurfaceTile(LinearLayoutTile):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._title_item: Optional[Graphic] = None
        self._title_target_name: Optional[str] = None
        self._title_target_item: Optional[Graphic] = None
        self._title_min_y = 0.0
        self._title_shown = False
        self._footer_item: Optional[Graphic] = None
        self._cutoff_name = ""
        self._cutoff_item: Optional[weakref.ref[QtWidgets.QGraphicsItem]] = None

        self.setSelectable(False)

    def showEvent(self, event):
        super().showEvent(event)
        self._updateTitleAndFooterVisibility()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._updateTitleAndFooterVisibility()

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange,
                   value: Any) -> Any:
        if change == self.ItemScenePositionHasChanged:
            self._updateTitleAndFooterVisibility()
        return super().itemChange(change, value)

    def sceneChanged(self, old_scene: QtWidgets.QGraphicsScene,
                     new_scene: QtWidgets.QGraphicsScene) -> None:
        if old_scene and isinstance(old_scene, core.GraphicScene):
            old_scene.viewportChanged.disconnect(self.viewportChanged)
        if isinstance(new_scene, core.GraphicScene):
            new_scene.viewportChanged.connect(self.viewportChanged)

    def updateableChildren(self) -> Iterable[Graphic]:
        yield from super().updateableChildren()
        if self._title_item:
            yield self._title_item
        if self._footer_item:
            yield self._footer_item

    @settable("title_item", argtype=Graphic)
    def setTitleItem(self, item: Graphic) -> None:
        self._title_item = item
        item.setParentItem(self)
        item.setZValue(3)
        self._updateTitleAndFooterVisibility(animated=False)

    def titleTargetItem(self) -> Optional[QtWidgets.QGraphicsWidget]:
        name = self._title_target_name
        item = self._title_target_item
        if name and not item:
            item = self.findElement(name, recursive=True)
            self._title_target_item = item
        return item

    @settable("title_target")
    def setTitleTargetName(self, object_name: str) -> None:
        self._title_target_name = object_name
        self._updateTitleAndFooterVisibility(animated=False)

    @settable("title_min_y")
    def setTitleMinimumY(self, min_y: float) -> None:
        self._title_min_y = min_y
        self._updateTitleAndFooterVisibility(animated=False)

    @settable("cutoff_item")
    def setCutoffItemName(self, object_name: str) -> None:
        self._cutoff_name = object_name

    def _cutoffItem(self) -> Optional[QtWidgets.QGraphicsItem]:
        if self._cutoff_item:
            return self._cutoff_item()

        cutoff = self.findElement(self._cutoff_name, recursive=True)
        if cutoff:
            self._cutoff_item = weakref.ref(cutoff)
        return cutoff

    def cutoffHeight(self) -> float:
        if cutoff := self._cutoffItem():
            return cutoff.pos().y()
        else:
            return self.size().height()

    def viewportChanged(self) -> None:
        super().viewportChanged()
        self._updateTitleAndFooterVisibility()

    def shouldShowTitle(self) -> bool:
        title = self._title_item
        scroll_y = self.scrollY()
        if not title:
            return False
        if scroll_y < self._title_min_y:
            return False
        if target := self.titleTargetItem():
            target_bottom = target.geometry().bottom() - scroll_y
            header_bottom = scroll_y + title.size().height()
            return target_bottom < header_bottom
        return True

    def footerItem(self) -> Optional[Graphic]:
        return self._footer_item

    @settable("footer_item", argtype=Graphic)
    def setFooterItem(self, item: Graphic) -> None:
        self._footer_item = item
        item.setParentItem(self)
        item.setZValue(3)
        self._updateContents()

    def shouldShowFooter(self) -> bool:
        footer = self._footer_item
        return bool(footer)

    def viewportRect(self) -> QtCore.QRectF:
        # This must return the visible rect in SCENE coordinates
        vport = self.parentViewportRect()
        if self.shouldShowTitle():
            title = self._title_item
            vport.setTop(vport.top() + title.size().height())
        if self.shouldShowFooter():
            footer = self._footer_item
            vport.setBottom(vport.bottom() - footer.size().height())
        return vport

    def scrollY(self) -> float:
        return self.parentViewportRect().y()

    def _updateTitleAndFooterVisibility(self, animated=True):
        animated = animated and not self.animationDisabled()
        title = self._title_item
        view_rect = self.parentViewportRect()
        vw = view_rect.width()
        constraint = QtCore.QSizeF(vw, -1)
        if title:
            # Keep track of _title_shown instead of just checking if the title
            # is currently visible, because it could be visible but already
            # fading out
            show_title = self.shouldShowTitle()
            tsize = title.effectiveSizeHint(Qt.PreferredSize, constraint)
            title.setGeometry(QtCore.QRectF(view_rect.topLeft(), tsize))
            if animated and show_title and not self._title_shown:
                title.fadeIn()
            elif animated and self._title_shown and not show_title:
                title.fadeOut()
            else:
                title.setVisible(show_title)
            self._title_shown = show_title
        footer = self._footer_item
        if footer:
            fsize = footer.effectiveSizeHint(Qt.PreferredSize, constraint)
            footer.setGeometry(QtCore.QRectF(view_rect.topLeft(), fsize))
            footer.setVisible(self.shouldShowFooter())

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.drawRect(self.rect())


# class TileViewWidget(GraphicView):
#     def __init__(self, parent: QtWidgets.QWidget = None):
#         super().__init__(parent)
#
#         self._message = controls.TextGraphic()
#         self._message.setZValue(100)
#         self._message.setDocumentMargin(10)
#         self._message.setTextAlignment(Qt.AlignCenter)
#         self._message.setTextColor(QtGui.QPalette.PlaceholderText)
#         font = QtGui.QFont()
#         font.setFamily(FONT_FAMILY)
#         font.setPixelSize(XLARGE_TEXT_SIZE)
#         self._message.setFont(font)
#         self._message.hide()
#
#     def setScene(self, scene: TileScene) -> None:
#         super().setScene(scene)
#         scene.addItem(self._message)
#
#     # TODO: replace built-in message with a stacked overlay in the tile config
#     def message(self) -> controls.TextGraphic:
#         return self._message
#
#     def setMessage(self, msg: controls.TextGraphic):
#         self._message = msg
#
#     def messageText(self) -> str:
#         return self.message().html()
#
#     def setMessageText(self, text: str):
#         msg = self.message()
#         if msg:
#             msg.setHtml(text)
#             msg.show()
#
#     def showMessage(self) -> None:
#         msg = self.message()
#         if msg:
#             msg.show()
#
#     def hideMessage(self) -> None:
#         msg = self.message()
#         if msg:
#             msg.hide()
#
#     def fitContents(self):
#         super().fitContents()
#         scene = self.scene()
#         if not scene:
#             return
#
#         view_rect = self.viewRect()
#         self._message.setGeometry(view_rect)


# class TileScene(GraphicScene):
#     def rootTile(self) -> Optional[Tile]:
#         # Temporary alias for backwards compatibility
#         return self.rootGraphic()
#
#     def setRootTile(self, root: Tile) -> None:
#         # Temporary alias for backwards compatibility
#         self.setRootGraphic(root)
#
#
# class GearMenuButton(QtWidgets.QPushButton):
#     def __init__(self, parent: QtWidgets.QWidget = None):
#         super().__init__(parent)
#         self._gear = QtGui.QPixmap()
#         self._trisize = 8
#         self.setFlat(True)
#         self.setFocusPolicy(Qt.NoFocus)
#         self.setIconSize(QtCore.QSize(24, 24))
#         self._updateicon()
#         self.setGlobalScale(1.0)
#
#     def _updateicon(self):
#         c = self.palette().buttonText().color().name()
#         self._gear = styling.makeSvgPixmap(styling.gear_svg, 64, c)
#
#     def setGlobalScale(self, scale: float) -> None:
#         iconsize = int(16 * scale)
#         self.setIconSize(QtCore.QSize(iconsize, iconsize))
#         margin = int(5 * scale)
#         self.setFixedSize(iconsize + margin * 4, iconsize + margin * 2)
#         self._trisize = int(8 * scale)
#
#     def event(self, event: QtCore.QEvent) -> bool:
#         super().event(event)
#         if event.type() == event.PaletteChange:
#             self._updateicon()
#         return False
#
#     def paintEvent(self, event: QtGui.QPaintEvent) -> None:
#         painter = QtGui.QPainter(self)
#         painter.setRenderHint(painter.Antialiasing)
#         palette = self.palette()
#         rect = self.rect()
#         iconsize = self.iconSize()
#         ts = self._trisize
#         iconrect = QtWidgets.QStyle.alignedRect(
#             self.layoutDirection(), Qt.AlignCenter, iconsize, rect
#         )
#         iconrect.translate(-ts // 2, 0)
#         if self.isDown():
#             painter.fillRect(rect, palette.button())
#         painter.drawPixmap(iconrect, self._gear, self._gear.rect())
#
#         tx = iconrect.right() + ts // 2
#         ty = rect.center().y() - int(ts / 3)
#         painter.setBrush(palette.buttonText())
#         painter.setPen(Qt.NoPen)
#         painter.drawPolygon([
#             QtCore.QPoint(tx, ty),
#             QtCore.QPoint(tx + ts, ty),
#             QtCore.QPoint(tx + int(ts / 2), ty + int(ts * 0.66)),
#         ], Qt.OddEvenFill)


# class GearPolicy(enum.Enum):
#     show_at_top = enum.auto()
#     auto_show = enum.auto()
#     always_visible = enum.auto()
#     hidden = enum.auto()


# class TileWidget(QtWidgets.QFrame):
#     def __init__(self, parent: QtWidgets.QWidget = None):
#         super().__init__(parent)
#         self._template_path: Optional[pathlib.Path] = None
#         self._global_scale = 1.0
#         self._view = TileView(self)
#
#         scene = TileScene(self)
#         scene.setController(config.JsonPathController())
#         self._view.setScene(scene)
#
#         vsb = self._view.verticalScrollBar()
#         vsb.valueChanged.connect(self._scrolled)
#         # There's no signal for visibility, so we have to intercept visibility
#         # events on the view's scrollbar
#         vsb.installEventFilter(self)
#
#         self._gearpolicy = GearPolicy.show_at_top
#         self._gear = self._makeGearButton()
#         self._setupActions()
#         self.gearButton().setMenu(self._makeGearMenu())
#
#     def setGlobalScale(self, scale: float) -> None:
#         self._global_scale = scale
#         self._view.setGlobalScale(scale)
#         self._gear.setGlobalScale(scale)
#         self._resized()
#
#     def setGearButtonPolicy(self, policy: GearPolicy) -> None:
#         self._gearpolicy = policy
#         self._updateGearVisibility()
#
#     def _makeGearButton(self) -> QtWidgets.QPushButton:
#         gear = GearMenuButton(self)
#         effect = QtWidgets.QGraphicsOpacityEffect(gear)
#         gear.setGraphicsEffect(effect)
#         return gear
#
#     def _setupActions(self) -> None:
#         pass
#
#     def _makeGearMenu(self) -> QtWidgets.QMenu:
#         menu = QtWidgets.QMenu(self)
#         menu.addAction(self._view.zoomInAction)
#         menu.addAction(self._view.zoomOutAction)
#         menu.addAction(self._view.unzoomAction)
#         return menu
#
#     def gearButton(self) -> QtWidgets.QPushButton:
#         return self._gear
#
#     def rootTile(self) -> Optional[Tile]:
#         scene = self._view.scene()
#         if scene and isinstance(scene, TileScene):
#             return scene.rootTile()
#
#     def loadTemplate(self, path: Union[str, pathlib.Path], force=False) -> None:
#         if isinstance(path, str):
#             path = pathlib.Path(path)
#         if path and (force or path != self._template_path):
#             with path.open() as f:
#                 template_data = json.load(f)
#             self.setTemplate(template_data)
#             self._template_path = path
#
#     def setTemplate(self, template_data: dict[str, Any]) -> None:
#         root = graphics.rootFromTemplate(template_data, self.controller())
#         scene = self._view.scene()
#         if scene and isinstance(scene, TileScene):
#             scene.setRootTile(root)
#         else:
#             raise TypeError(f"Can't set root tile on scene: {scene}")
#
#     def eventFilter(self, watched: QtCore.QObject,
#                     event: QtCore.QEvent) -> bool:
#         if watched == self._view.verticalScrollBar():
#             if isinstance(event, (QtGui.QShowEvent, QtGui.QHideEvent)):
#                 self._repositionGear()
#         return super().eventFilter(watched, event)
#
#     def showEvent(self, event: QtGui.QShowEvent) -> None:
#         super().showEvent(event)
#         self._resized()
#
#     def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
#         super().resizeEvent(event)
#         self._resized()
#
#     def _resized(self):
#         rect = self.rect()
#         self._view.setGeometry(rect)
#         self._repositionGear()
#
#     def _repositionGear(self):
#         gear = self.gearButton()
#         vsb = self._view.verticalScrollBar()
#         w = self.rect().width()
#         if vsb.isVisible():
#             w -= vsb.width()
#         gear.move(w - gear.width(), 0)
#
#     def _updateGearVisibility(self):
#         gear = self._gear
#         policy = self._gearpolicy
#         height = gear.height()
#         effect: QtWidgets.QGraphicsOpacityEffect = gear.graphicsEffect()
#         if policy == GearPolicy.hidden:
#             gear.hide()
#         elif policy == GearPolicy.always_visible:
#             gear.show()
#             effect.setOpacity(1.0)
#         elif height and policy == GearPolicy.show_at_top:
#             pos = self._view.verticalScrollBar().sliderPosition()
#             if pos <= height:
#                 opacity = 1.0
#             elif pos < height * 2:
#                 opacity = 1.0 - (pos - height) / height
#             else:
#                 opacity = 0.0
#             gear.setVisible(bool(opacity))
#             effect.setOpacity(opacity)
#         elif policy == GearPolicy.auto_show:
#             # TODO: implement this
#             pass
#
#     def _scrolled(self):
#         self._updateGearVisibility()


def generateImage(template_data: dict[str, Any], stats: dict[str, Any],
                  width: int, height=-1, scale=1.0, rotation=0.0
                  ) -> QtGui.QPixmap:
    from renderstats.images import normalize_stats

    controller = config.JsonPathController()
    stats = normalize_stats(stats)
    root = core.rootFromTemplate(template_data, controller)
    controller.updateFromData(stats)
    if scale != 1.0 or rotation != 0.0:
        xform = QtGui.QTransform()
        xform.rotate(rotation)
        xform.scale(scale, scale)
        root.setTransform(xform)

    scene = QtWidgets.QGraphicsScene()
    pal = themes.defaultPalette()
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

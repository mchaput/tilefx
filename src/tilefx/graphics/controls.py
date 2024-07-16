from __future__ import annotations
import enum
import math
import pathlib
from typing import Any, Iterable, Optional, Sequence, Union

from PySide2 import QtCore, QtGui, QtWidgets, QtSvg
from PySide2.QtCore import Qt

import tilefx.util
from .. import config, converters, formatting, glyphs, styling, themes, util
from ..config import settable
from ..themes import ThemeColor
from . import core, layouts, widgets
from .core import graphictype, path_element, Graphic, DynamicColor


class ScrollBarItem(QtWidgets.QGraphicsProxyWidget):
    def __init__(self, orientation: Qt.Orientation,
                 parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self.setWidget(InvisibleScrollBar(orientation=orientation))

        self._track_width = 4.0
        self._activeness = 0.0

        self._timeout = QtCore.QTimer()
        self._timeout.setInterval(700)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._onTimeout)

        self._pressed = False
        self.widget().rangeChanged.connect(self._updateContents)
        self.widget().valueChanged.connect(self._onValueChanged)
        self.widget().sliderPressed.connect(self._onPress)
        self.widget().sliderReleased.connect(self._onRelease)

        self._track = core.RectangleGraphic(self)
        self._track.setPillShaped(True)
        self._track.setFillColor(ThemeColor.surface_low)
        self._track.setOpacity(0.5)

        self._handle = ColorChangeRectangle(self)
        self._handle.setFillColor(ThemeColor.button)
        self._handle.setAltColor(ThemeColor.button_fg)
        self._handle.setPillShaped(True)

        self.geometryChanged.connect(self._updateContents)

    def activate(self, start_timer: bool, animated=False) -> None:
        self._handle.stopBlendAnimation()
        if animated:
            self._handle.animateBlend(1.0)
        else:
            self._handle.setBlendValue(1.0)

        if start_timer:
            self.deactivateLater()
        self._updateContents()

    def deactivate(self, animated=False) -> None:
        self._timeout.stop()
        if animated:
            self._handle.animateBlend(0.0)
        else:
            self._handle.setBlendValue(0.0)

    def deactivateLater(self) -> None:
        self._timeout.start()

    def hoverEnterEvent(self, event) -> None:
        self.activate(start_timer=False, animated=True)

    def hoverLeaveEvent(self, event) -> None:
        self.deactivate(animated=True)

    def _onPress(self) -> None:
        self.activate(start_timer=False)
        self._pressed = True
        self._updateContents()

    def _onRelease(self) -> None:
        self._pressed = False
        self._timeout.start()

    def _onValueChanged(self) -> None:
        if not self._pressed:
            self.activate(start_timer=True, animated=False)
        self._updateContents()

    def _onTimeout(self) -> None:
        self._handle.animateBlend(0.0, duration=200)

    def _updateContents(self) -> None:
        tr, hr = self.widget().trackAndHandleRects(self._track_width)
        self._track.setGeometry(tr)
        self._handle.setGeometry(hr)


class InvisibleScrollBar(widgets.ScrollBar):
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        # Override the widget's paint event to do nothing
        pass


class TransparentComboBox(QtWidgets.QComboBox):
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        # Override the widget's paint event to do nothing
        pass

    def wheelEvent(self, e):
        pass


def makeCheckmark(parent: QtWidgets.QGraphicsItem = None,
                  color: converters.ColorSpec = ThemeColor.primary):
    checkmark = StringGraphic(parent)
    checkmark.setTextAlignment(Qt.AlignCenter)
    checkmark.setGlyph(glyphs.FontAwesome.check)
    checkmark.setTextSize(converters.TINY_TEXT_SIZE)
    checkmark.setTextColor(color)
    return checkmark


@graphictype("controls.busy")
class BusyGraphic(Graphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._timestep = 0
        self._speed = 1
        self._color = QtGui.QColor.fromRgbF(1.0, 1.0, 1.0)
        self._timer = QtCore.QTimer()
        self._timer.setInterval(100)
        self._timer.timeout.connect(self.frameAdvance)

    _color = DynamicColor()

    def color(self) -> QtGui.QColor:
        return self._color

    def setColor(self, color: QtGui.QColor) -> None:
        self._color = color
        self.update()

    def speed(self) -> int:
        return self._speed

    def setSpeed(self, speed: int) -> None:
        self._speed = speed
        if not speed:
            self._timer.stop()
        elif not self._timer.isActive():
            self._timer.start()

    def interval(self) -> int:
        return self._timer.interval()

    def setInterval(self, interval_ms: int) -> None:
        self._timer.setInterval(interval_ms)

    def isActive(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def frameAdvance(self):
        self._timestep += 1
        self.update()

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        util.drawFadingRings(painter, self.rect(), timestep=self._timestep,
                             color=self._color)


@graphictype("svg")
class SvgGraphic(Graphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._renderer: Optional[QtSvg.QSvgRenderer] = None
        self._alignment = Qt.AlignCenter
        # self.setCacheMode(self.ItemCoordinateCache)
        self._color: Optional[QtGui.QColor] = None

    _color = DynamicColor()

    def monochromeColor(self) -> Optional[QtGui.QColor]:
        return self._color

    @settable("color", argtype=QtGui.QColor)
    def setMonochromeColor(self, color: QtGui.QColor) -> None:
        self._color = color
        self.update()

    def svgRenderer(self) -> Optional[QtSvg.QSvgRenderer]:
        return self._renderer

    def alignment(self) -> Qt.Alignment:
        return self._alignment

    @settable(argtype=Qt.Alignment)
    def setAlignment(self, align: Qt.Alignment) -> None:
        self._alignment = align
        self.update()

    @settable()
    def setSvgGlyph(self, name: str) -> None:
        # self._renderer = glyphs().renderer(name)
        self.update()

    def sizeHint(self, which: Qt.SizeHintRole, constraint=None):
        if which == Qt.PreferredSize:
            svg = self.svgRenderer()
            if svg:
                return svg.defaultSize()
        return constraint

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        svg = self.svgRenderer()
        if not svg:
            return

        rect = self.rect()
        src_size = svg.defaultSize()
        dest_size = rect.size()
        scale = min(dest_size.width() / src_size.width(),
                    dest_size.height() / src_size.height())
        size = src_size * scale
        svg_rect = util.alignedRectF(
            self.layoutDirection(), self.alignment(), size, rect
        )
        svg.render(painter, svg_rect)

        color = self.monochromeColor()
        if color:
            painter.setCompositionMode(painter.CompositionMode_SourceAtop)
            painter.fillRect(svg_rect, color)


@graphictype("controls.pixmap")
class PixmapGraphic(core.RectangleGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._image: Optional[QtGui.QIcon | QtGui.QPixmap] = None
        self._alignment: Qt.Alignment = Qt.AlignCenter

    @settable("align", argtype=Qt.Alignment)
    def setAlignment(self, align: Qt.Alignment) -> None:
        self._alignment = align
        self.update()

    @settable()
    def setHoudiniIcon(self, name: str) -> None:
        import hou
        self._image = hou.qt.Icon(name, 512, 512)
        self.update()

    def setIcon(self, icon: QtGui.QIcon) -> None:
        self._image = icon
        self.update()

    @settable()
    def setPath(self, path: Union[str, pathlib.Path]):
        self._image = QtGui.QPixmap(str(path))

    @settable(argtype=QtCore.QSizeF)
    def setSize(self, size: QtCore.QSizeF) -> None:
        self._implicit_size = size

    def implicitSize(self) -> QtCore.QSizeF:
        if self._implicit_size:
            size = self._implicit_size
        elif isinstance(self._image, QtGui.QIcon):
            size = QtCore.QSizeF(16, 16)
        elif isinstance(self._image, QtGui.QPixmap):
            size = self._image.size()
        else:
            size = QtCore.QSizeF()
        return size

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        super().paint(painter, option, widget)
        rect = self.rect()
        if isinstance(self._image, QtGui.QIcon):
            self._image.paint(painter, rect.toAlignedRect(),
                              alignment=self._alignment)
        elif isinstance(self._image, QtGui.QPixmap):
            painter.drawPixmap(rect, self._image)


@graphictype("controls.marquee")
class MarqueeGraphic(Graphic):
    class State(enum.Enum):
        stopped = enum.auto()
        at_start = enum.auto()
        rolling_forward = enum.auto()
        at_end = enum.auto()
        rolling_backward = enum.auto()

    class ReturnMode(enum.Enum):
        reverse = enum.auto()
        instant = enum.auto()
        fade = enum.auto()
        rollover = enum.auto()

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self.setClipping(True)
        self._group = Graphic(self)
        self._text1 = StringGraphic(self._group)
        self._text2 = StringGraphic(self._group)
        self._content = self._text1

        self._pretimer = QtCore.QTimer(self)
        self._pretimer.setInterval(2000)
        self._pretimer.setSingleShot(True)
        self._pretimer.timeout.connect(self._prerollFinished)
        self._posttimer = QtCore.QTimer(self)
        self._posttimer.setInterval(1000)
        self._posttimer.setSingleShot(True)
        self._posttimer.timeout.connect(self._postrollFinished)

        self._msec_per_pixel = 20
        self._roller = QtCore.QPropertyAnimation(self)
        self._roller.setPropertyName(b"pos")
        self._roller.finished.connect(self._rollFinished)
        self._roller.setEasingCurve(QtCore.QEasingCurve.Linear)
        self._roller.setTargetObject(self._group)
        self._state = self.State.stopped
        self._rollover_gap = 20.0
        self._return_mode = self.ReturnMode.rollover

        self.geometryChanged.connect(self.restart)
        self.resetContent()

    def text(self) -> str:
        return self._text1.text()

    @settable()
    def setText(self, text: str) -> None:
        self._text1.setText(text)
        self._text2.setText(text)
        self.resetContent()

    def textColor(self) -> QtGui.QColor:
        return self._text1.foregroundColor()

    def setTextColor(self, color: QtGui.QColor) -> None:
        self._text1.setTextColor(color)
        self._text2.setTextColor(color)

    def returnMode(self) -> MarqueeGraphic.ReturnMode:
        return self._return_mode

    def setReturnMode(self, mode: MarqueeGraphic.ReturnMode) -> None:
        self._return_mode = mode
        self.restart()

    def rolloverGap(self) -> float:
        return self._rollover_gap

    @settable()
    def setRolloverGap(self, gap: float) -> None:
        self._rollover_gap = gap
        self.restart()

    def shouldAnimate(self) -> bool:
        size = self.size()
        csize = self._text1.effectiveSizeHint(
            Qt.PreferredSize, QtCore.QSizeF(-1, size.height())
        )
        return csize.width() > self.size().width()

    def resetContent(self) -> None:
        size = self.size()
        csize = self._text1.effectiveSizeHint(
            Qt.PreferredSize, QtCore.QSizeF(-1, size.height())
        )
        r1 = QtCore.QRectF(QtCore.QPointF(0, 0), csize)
        r2 = QtCore.QRectF(r1).translated(r1.width() + self._rollover_gap, 0)
        self._group.setPos(0, 0)
        self._text1.setGeometry(r1)
        self._text2.setGeometry(r2)

        is_rollover = self._return_mode == self.ReturnMode.rollover
        self._text2.setVisible(is_rollover and self.shouldAnimate())

    def delayAtStart(self) -> int:
        return self._pretimer.interval()

    @settable()
    def setDelayAtStart(self, msecs: int) -> None:
        self._pretimer.setInterval(msecs)

    def delayAtEnd(self) -> int:
        return self._posttimer.interval()

    @settable()
    def setDelayAtEnd(self, msecs: int) -> None:
        self._posttimer.setInterval(msecs)

    def delayPerPixel(self) -> int:
        return self._msec_per_pixel

    @settable()
    def setDelayPerPixel(self, msecs: int) -> None:
        self._msec_per_pixel = msecs

    def easingCurve(self) -> QtCore.QEasingCurve:
        return self._roller.easingCurve()

    def setEasingCurve(self, curve: QtCore.QEasingCurve) -> None:
        self._roller.setEasingCurve(curve)

    def restart(self):
        self._pretimer.stop()
        self._posttimer.stop()
        self._roller.stop()

        self.resetContent()

        if not self._group.isVisible() or not self._group.opacity():
            self._group.fadeIn()
        self._state = self.State.at_start

        if self.shouldAnimate():
            self._pretimer.start()

    def stop(self) -> None:
        self._pretimer.stop()
        self._posttimer.stop()
        self._roller.stop()
        self._state = self.State.stopped
        self._text1.setPos(0, 0)

    def resizeEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self.restart()

    def showEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self.restart()

    def hideEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self.stop()

    def _animateRoll(self, backwards=False) -> None:
        is_rollver = self._return_mode == self.ReturnMode.rollover
        content = self._group if is_rollver else self._text1
        mode = self._return_mode
        delta_width = self.size().width() - self._text1.size().width()
        if mode == self.ReturnMode.rollover:
            delta_width = self._text1.size().width() + self._rollover_gap
            target_pos = QtCore.QPointF(-delta_width, 0)
        elif backwards:
            target_pos = QtCore.QPointF(0, 0)
        else:
            target_pos = QtCore.QPointF(-delta_width, 0)

        self._roller.setStartValue(content.pos())
        self._roller.setEndValue(target_pos)

        if backwards:
            duration = self._return_msec
        else:
            duration = int(delta_width * self._msec_per_pixel)
        self._roller.setDuration(duration)

        self._state = (self.State.rolling_backward if backwards
                       else self.State.rolling_forward)
        self._roller.start()

    def _prerollFinished(self) -> None:
        self._animateRoll()

    def _rollFinished(self) -> None:
        self._state = self.State.at_end
        if self._return_mode == self.ReturnMode.rollover:
            self.restart()
        elif self._state == self.State.rolling_forward:
            self._posttimer.start()
        elif self._state == self.State.rolling_backward:
            self.restart()

    def _postrollFinished(self) -> None:
        mode = self._return_mode
        if mode == self.ReturnMode.reverse:
            self._animateRoll(backwards=True)
        elif mode == self.ReturnMode.instant:
            self.restart()
        elif mode == self.ReturnMode.fade:
            self._group.fadeOut(callback=self.restart)


@graphictype("controls.placeholder")
class PlaceholderGraphic(core.AreaGraphic):
    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        parent = self.parentItem()
        if parent and self.clipsToParentShape():
            painter.setClipPath(self.mapFromParent(parent.shape()))
        r = self.rect()
        painter.setPen(Qt.red)
        painter.drawRect(r)
        painter.drawLine(r.topLeft(), r.bottomRight())
        painter.drawLine(r.bottomLeft(), r.topRight())


class AbstractTextGraphic(core.RectangleGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._color: QtGui.QColor = ThemeColor.value
        self._margins = QtCore.QMarginsF(0, 0, 0, 0)
        self._text_tint: Optional[QtGui.QColor] = None
        self._text_tint_amount = 0.5
        self._bg_visible = True

    _color = DynamicColor()
    _text_tint = DynamicColor()
    _over_color = DynamicColor()

    def isBackgroundVisible(self) -> bool:
        return self._bg_visible

    def setBackgroundVisible(self, visible: bool) -> None:
        self._bg_visible = visible
        self.update()

    # def font(self) -> QtGui.QFont:
    #     return self._item.font()

    @settable()
    def setFontFamily(self, family: str) -> None:
        font = self.font()
        font.setFamily(family)
        self.setFont(font)

    @settable()
    def setBold(self, bold: bool) -> None:
        font = self.font()
        font.setBold(bold)
        self.setFont(font)

    @settable()
    def setItalic(self, italic: bool) -> None:
        font = self.font()
        font.setItalic(italic)
        self.setFont(font)

    @settable(argtype=QtGui.QFont.Weight)
    def setWeight(self, weight: int) -> None:
        font = self.font()
        font.setWeight(weight)
        self.setFont(font)

    def margins(self) -> QtCore.QMarginsF:
        return self._margins

    @settable("margins", argtype=QtCore.QMarginsF)
    def setMargins(self, left: Union[QtCore.QMarginsF, float], top=0.0,
                   right=0.0, bottom=0.0) -> None:
        self._margins = converters.marginsArgs(left, top, right, bottom)
        self._updateContents()
        self.update()

    def textSize(self) -> int:
        return self.font().pixelSize()

    @settable(converter=converters.textSizeConverter)
    def setTextSize(self, size: int) -> None:
        font = self.font()
        font.setPixelSize(size)
        self.setFont(font)
        self.update()

    _textSize = QtCore.Property(int, textSize, setTextSize)

    @settable("text_tint_color", argtype=QtGui.QColor)
    def setTextTintColor(self, color: QtGui.QColor) -> None:
        self._text_tint = color
        self._updateColors()

    @settable("text_tint_amount")
    def setTextTintAmount(self, amount: float) -> None:
        self._text_tint_amount = amount
        self._updateColors()

    def textAlignment(self) -> Qt.Alignment:
        raise NotImplementedError

    @settable("text_align", argtype=Qt.Alignment)
    def setTextAlignment(self, align: Qt.Alignment) -> None:
        raise NotImplementedError

    def setGlyph(self, glyph: glyphs.Glyph) -> None:
        # self.setTextAlignment(Qt.AlignCenter)
        font = self.font()
        font_fam, font_weight = glyph.familyAndWeight()
        font.setFamily(font_fam)
        if font_weight is not None:
            font_weight = converters.fontWeightConverter(font_weight)
            font.setWeight(font_weight)
        self.setFont(font)
        self.setText(chr(glyph.value))
        # self.setCacheMode(self.ItemCoordinateCache)

    @settable("glyph")
    def setGlyphName(self, name: str) -> None:
        glyph = glyphs.forName(name)
        if glyph:
            self.setGlyph(glyph)

    def foregroundColor(self) -> Optional[QtGui.QColor]:
        return self._color

    @settable("text_color", argtype=QtGui.QColor)
    def setTextColor(self, color: converters.ColorSpec) -> None:
        self._color = color
        self._updateColors()

    def setOverrideColor(self, color: Optional[converters.ColorSpec]) -> None:
        # This is just a way to temporarily change the color (like to indicate
        # an error) without forgetting the "real" color
        self._over_color = color
        self._updateColors()

    def effectiveTextColor(self) -> QtGui.QColor:
        over_color = self._over_color
        if over_color:
            return over_color

        color = self._color
        text_tint = self._text_tint
        if color and text_tint and self._text_tint_amount:
            color = themes.blend(color, text_tint, self._text_tint_amount)
        return QtGui.QColor(color)

    def _updateColors(self) -> None:
        raise NotImplementedError

    def _updateContents(self) -> None:
        pass

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        if self._bg_visible:
            self._paintRectangle(painter)


@graphictype("controls.string")
class StringGraphic(AbstractTextGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._compact = False
        self._text = ""
        self._insets: Optional[tuple[float]] = None
        self._text_size = QtCore.QSizeF()
        # self._item = QtWidgets.QGraphicsSimpleTextItem(self)
        # self._item.setFlag(self.ItemIsFocusable, False)
        self._alignment = Qt.AlignLeft
        self._elide_mode: Qt.TextElideMode = Qt.ElideNone
        self._line_width = 0.0
        self._line_alpha = 0.1
        self._line_gap = 10.0

        # self.geometryChanged.connect(self._updateContents)
        self._updateSize()
        # self._updateContents()

    def textToCopy(self) -> str:
        return self._text

    @settable()
    def setLineMargin(self, gap: float) -> None:
        self._line_gap = gap
        self.update()

    @settable()
    def setLineWidth(self, width: float) -> None:
        self._line_width = width
        self.update()

    @settable()
    def setLineAlpha(self, alpha: float) -> None:
        self._line_alpha = alpha
        self.update()

    def text(self) -> str:
        return self._text

    @settable()
    def setText(self, text: str) -> None:
        self.prepareGeometryChange()
        self._text = str(text)
        self._updateSize()
        # self._updateContents()
        self.updateGeometry()

    def textAlignment(self) -> Qt.Alignment:
        return self._alignment

    @settable("text_align", argtype=Qt.Alignment)
    def setTextAlignment(self, align: Qt.Alignment) -> None:
        self._alignment = align
        self.update()

    # def font(self) -> QtGui.QFont:
    #     return self._item.font()

    def setFont(self, font: QtGui.QFont):
        super().setFont(font)
        self._updateSize()

    def textHeight(self) -> float:
        return self._text_height
        # return self._item.boundingRect().height() - 4.0

    def elideMode(self) -> Qt.TextElideMode:
        return self._elide_mode

    @settable("elide", argtype=Qt.TextElideMode)
    def setElideMode(self, elide: Qt.TextElideMode) -> None:
        self.prepareGeometryChange()
        self._elide_mode = elide
        # self._updateContents()
        self.updateGeometry()

    def isCompact(self) -> bool:
        return self._compact

    @settable(argtype=bool)
    def setCompact(self, compact: bool) -> None:
        self.prepareGeometryChange()
        self._compact = compact
        self.updateGeometry()

    def _updateSize(self) -> None:
        fm = QtGui.QFontMetricsF(self.font())
        self._text_size.setWidth(fm.horizontalAdvance(self._text))
        self._text_size.setHeight(fm.height())

    # def _updateContents(self):
    #     rect = self.rect().marginsRemoved(self.margins())
    #     width = rect.width()
    #     text_width = self._text_width
    #     elide = self._elide_mode
    #     text = self._text
    #     if text_width > width and elide != Qt.ElideNone:
    #         fm = QtGui.QFontMetricsF(self._item.font())
    #         text = fm.elidedText(text, elide, width)
    #         text_width = width
    #     self._item.setText(text)
    #
    #     text_size = QtCore.QSizeF(text_width, self.textHeight())
    #     text_rect = util.alignedRectF(
    #         self.layoutDirection(), self._alignment, text_size, rect
    #     )
    #     self._item.setPos(text_rect.x(), text_rect.y() - 2.0)
    #     self._updateColors()

    def _updateColors(self) -> None:
        self.update()
        # color = self.effectiveTextColor()
        # self._item.setBrush(color)

    def hasImplicitSize(self) -> bool:
        return True

    def implicitSize(self) -> QtCore.QSizeF:
        text = self.text()
        ms = self.margins()
        height = self._text_size.height() + ms.top() + ms.bottom()
        if text:
            width = self._text_size.width() + ms.left() + ms.right()
        else:
            width = 0.0
        return QtCore.QSizeF(width, height)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        if which == Qt.PreferredSize:
            size = self.implicitSize()
            if constraint.width() > size.width() and not self._compact:
                size.setWidth(constraint.width())
            return size
        return constraint

    def _paintDividerLine(self, painter: QtGui.QPainter) -> None:
        rect = self.rect()
        width = self._text_size.width()
        ctr = rect.center()
        y = ctr.y()
        gap = self._line_gap
        align = self.textAlignment()
        color = self.effectiveTextColor()
        color.setAlphaF(self._line_alpha)
        painter.setPen(QtGui.QPen(color, self._line_width))
        if align & Qt.AlignLeft:
            p1 = QtCore.QPointF(rect.x() + width + gap, y)
            p2 = QtCore.QPointF(rect.right(), y)
            painter.drawLine(p1, p2)
        elif align & Qt.AlignRight:
            p1 = QtCore.QPointF(rect.x(), y)
            p2 = QtCore.QPointF(rect.right() - width - gap, y)
            painter.drawLine(p1, p2)
        else:
            p1 = QtCore.QPointF(rect.x(), y)
            p2 = QtCore.QPointF(ctr.x() - width / 2 - gap, y)
            painter.drawLine(p1, p2)
            p1 = QtCore.QPointF(ctr.x() + width / 2 + gap, y)
            p2 = QtCore.QPointF(rect.right(), y)
            painter.drawLine(p1, p2)

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        super().paint(painter, option, widget)
        rect = self.rect().marginsRemoved(self._margins)
        if not rect.isValid():
            return

        if self._insets:
            rect.adjust(self._insets[0], 0, -self._insets[1], 0)

        color = self.effectiveTextColor()
        font = self.font()
        text = self.text()
        width = self._text_size.width()
        if width > rect.width() and self._elide_mode != Qt.ElideNone:
            fm = QtGui.QFontMetricsF(font)
            text = fm.elidedText(text, self._elide_mode, rect.width())

        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(rect, self._alignment, text)

        if self._line_width:
            self._paintDividerLine(painter)


@graphictype("controls.numeric_string")
class NumericStringGraphic(StringGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)
        self._value: Optional[str, int, float] = None
        self._formatter: formatting.NumberFormatter = \
            formatting.NumberFormatter()
        self._formatter.setBriefMode(formatting.BriefMode.auto)

    def textToCopy(self) -> str:
        return str(self._value)

    def formatter(self) -> formatting.NumberFormatter:
        return self._formatter

    @settable(converter=converters.formatConverter)
    def setFormatter(self, formatter: formatting.NumberFormatter):
        self._formatter = formatter

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
        self._value = value
        fmt = self.formatter()
        if not isinstance(value, (str, int, float)):
            raise ValueError(f"{self}: {value!r} is not a number")
        fmtnum = fmt.formatNumber(value)
        self.setText(fmtnum.plainText())


@graphictype("controls.divider")
class DividerGraphic(StringGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._line_width = 1.0


@graphictype("controls.text")
class TextGraphic(AbstractTextGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._colors_changed = False
        self._saved: tuple[str, bool] = ("", False)
        self._alignment = Qt.AlignLeft | Qt.AlignTop
        self._exapnd_h = True
        self._text_selectable = False
        self._links_clickable = False
        self._item = QtWidgets.QGraphicsTextItem(self)
        self._item.linkActivated.connect(self.linkClicked)
        self._item.installEventFilter(self)
        self._updateInteractionFlags()

        doc = self._item.document()
        doc.setDefaultFont(self.font())
        doc.setUndoRedoEnabled(False)
        doc.setDocumentMargin(0)

        self.setHasHeightForWidth(True)

        self.geometryChanged.connect(self._updateContents)
        # self._updateContents()

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent
                    ) -> bool:
        if watched == self._item and event.type() == event.FocusOut:
            self.clearSelection()
        return False

    def clearSelection(self) -> None:
        cur = self._item.textCursor()
        cur.clearSelection()
        self._item.setTextCursor(cur)

    # def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
    #     print("KEY:", event.key())

    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == event.PaletteChange:
            self._colors_changed = True

    # def contextMenuEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
    #     print("context menu=", event)
    #     # self.scene().sendEvent(self._item, event)
    #     event.accept()

    def document(self) -> QtGui.QTextDocument:
        return self._item.document()

    def setDocument(self, doc: QtGui.QTextDocument) -> None:
        self._item.setDocument(doc)
        self._updateContents()
        self.updateGeometry()

    def setFont(self, font: QtGui.QFont):
        super().setFont(font)
        self.prepareGeometryChange()
        self._item.setFont(font)
        self._item.document().setDefaultFont(font)
        self._updateContents()
        self.updateGeometry()

    @settable("text_align", argtype=Qt.Alignment)
    def setTextAlignment(self, align: Qt.Alignment):
        self._alignment = align
        self._updateContents()

    def expandsHorizontally(self) -> bool:
        return self._exapnd_h

    def setExpandsHorizontally(self, expand: bool) -> None:
        self.prepareGeometryChange()
        self._exapnd_h = expand
        self.updateGeometry()

    def plainText(self) -> str:
        return self._item.toPlainText()

    def textToCopy(self) -> str:
        return self.plainText()

    @settable("plain_text")
    def setPlainText(self, text: str):
        self._saved = (str(text), False)
        self.prepareGeometryChange()
        self._item.setPlainText(str(text))
        self.updateGeometry()

    def html(self) -> str:
        return self._item.toHtml()

    @settable("html")
    def setHtml(self, html: str):
        self._saved = (str(html), True)
        self.prepareGeometryChange()
        self._item.setHtml(html)
        self.updateGeometry()

    @settable("text")
    def setText(self, text: str):
        self.setHtml(text)

    @settable(argtype=bool)
    def setWordWrap(self, wrap: bool) -> None:
        doc = self.document()
        option = doc.defaultTextOption()
        option.setWrapMode(option.WordWrap if wrap else option.NoWrap)
        doc.setDefaultTextOption(option)

    def _updateContents(self):
        self.document().setDefaultTextOption(QtGui.QTextOption(self._alignment))
        rect = self.rect().marginsRemoved(self.margins())
        height = rect.height()
        self._item.setTextWidth(rect.width())
        text_height = self.document().size().height()
        y = 0.0
        if text_height < height:
            diff = height - text_height
            if self._alignment & Qt.AlignVCenter:
                y = diff / 2.0
            elif self._alignment & Qt.AlignBottom:
                y = diff
        self._item.setPos(rect.x(), rect.y() + y)
        self._updateColors()

    def _updateColors(self) -> None:
        item = self._item
        color = self.effectiveTextColor()
        item.setDefaultTextColor(color)

        hex = self.palette().link().color().name()
        ss = f"a {{color: {hex} }}"
        item.document().setDefaultStyleSheet(ss)
        string, is_rich = self._saved
        if is_rich:
            item.setHtml(string)
        else:
            item.setPlainText(string)
        self._colors_changed = False

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        # fm = QtGui.QFontMetricsF(self.font())
        ms = self.margins()
        size = QtCore.QSizeF(-1, -1)
        if which == Qt.PreferredSize:
            doc = self._item.document().clone()
            tw = doc.size().width()
            # saved_width = doc.textWidth()
            if constraint.width() >= 0:
                w = max(0.0, constraint.width() - ms.left() - ms.right())
                doc.setTextWidth(w)
                if tw < w and not self.expandsHorizontally():
                    w = tw + ms.left() + ms.right()
                else:
                    w = constraint.width()
                h = doc.size().height() + ms.top() + ms.bottom()
                size = QtCore.QSizeF(w, h)
            else:
                size = doc.size()
            # doc.setTextWidth(saved_width)
        return size

    @settable(argtype=bool)
    def setTextSelectable(self, selectable: bool) -> None:
        self._text_selectable = selectable
        self._updateInteractionFlags()

    @settable(argtype=bool)
    def setLinksClickable(self, clickable: bool) -> None:
        self._links_clickable = clickable
        self._updateInteractionFlags()

    def _updateInteractionFlags(self) -> None:
        flags = Qt.NoTextInteraction

        if self._text_selectable:
            flags |= Qt.TextSelectableByMouse

        if self._links_clickable:
            flags |= Qt.LinksAccessibleByMouse

        self._item.setTextInteractionFlags(flags)
        # self._item.setFlag(self.ItemIsFocusable, False)

    def linkClicked(self, url: str) -> None:
        # print("LINK=", url)
        scene = self.scene()
        if isinstance(scene, core.GraphicScene):
            scene.linkClicked(url)

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        if self._colors_changed:
            self._updateColors()
        super().paint(painter, option, widget)

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.setPen(Qt.red)
    #     painter.drawRect(self.rect())
    #     painter.setPen(Qt.yellow)
    #     painter.drawRect(self._item.boundingRect())

    #     super().paint(painter, option, widget)
    #     rect = self.rect().marginsRemoved(self._margins)
    #     doc = self._doc
    #     if not rect.isValid():
    #         return
    #
    #     if self._elided:
    #         text = self.plainText()
    #         fm = painter.fontMetrics()
    #         line_space = fm.lineSpacing()
    #         width = int(rect.width())
    #         height = rect.height()
    #         layout = QtGui.QTextLayout(text, painter.font())
    #         layout.beginLayout()
    #         y = 0
    #         while True:
    #             line = layout.createLine()
    #             if not line.isValid():
    #                 break
    #
    #             line.setLineWidth(width)
    #             nextY = y + line_space
    #
    #             if height >= nextY + line_space:
    #                 line.draw(painter, QtCore.QPoint(0, y))
    #                 y = nextY
    #             else:
    #                 last_line = text[line.textStart():]
    #                 elided = fm.elidedText(last_line, Qt.ElideRight, width)
    #                 painter.drawText(QtCore.QPoint(0, y + fm.ascent()), elided)
    #                 layout.createLine()
    #                 break
    #         layout.endLayout()
    #     else:
    #         drawTextDocument(painter, rect, doc, self.palette(),
    #                          color=self.foregroundColor(),
    #                          role=self.foregroundRole())


@graphictype("controls.formatted_number")
class FormattedNumberGraphic(TextGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._formatter = formatting.NumberFormatter()
        self._number: int | float = 0.0
        self._min_width = 0.0
        self._minus_width = 8.0
        self._digit_width = 8.0
        self._comma_width = 0.0
        self._comma_count = 0
        self._updateFontSizes()

        # Turn off word wrap in the text document
        doc = self.document()
        opt = doc.defaultTextOption()
        opt.setWrapMode(opt.NoWrap)
        doc.setDefaultTextOption(opt)

    def setFormatter(self, formatter: formatting.NumberFormatter) -> None:
        self._formatter = formatter
        self.updateGeometry()
        self._updateContents()

    def setFont(self, font: QtGui.QFont) -> None:
        super().setFont(font)
        self.updateGeometry()
        self._updateFontSizes()
        self._updateContents()

    def number(self) -> int | float:
        return self._number

    @settable()
    def setNumber(self, number: int | float) -> None:
        self._number = number
        self._comma_count = self._commaCount(number)
        self.updateGeometry()
        self._updateContents()

    @staticmethod
    def _commaCount(n: int) -> int:
        # Math is hard
        if not n:
            return 0
        return int(math.log10(abs(n)) / 3)

    def _updateFontSizes(self) -> None:
        # When the font changes, compute the fixed minimum width (the minus sign
        # and a decimal) and the digit width (using 0; this assumes
        # the font has tabular figures!!!)
        font = self.font()
        font.setBold(True)
        fm = QtGui.QFontMetricsF(font)
        self._minus_width = fm.horizontalAdvance(formatting.NEGATIVE_CHAR)
        self._min_width = self._minus_width + fm.horizontalAdvance(".")
        self._digit_width = fm.horizontalAdvance("0")
        self._comma_width = fm.horizontalAdvance(",")

    # def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
    #              ) -> QtCore.QSizeF:
    #     return QtCore.QSizeF(120, 24)

    def _updateContents(self) -> None:
        fmtr = self._formatter
        # Work out how much space is available for digits by subtracting the
        # width of a minus sign, a decimal place, and the number of commas that
        # will appear in tbhe current number
        avail = (self.size().width() - self._min_width -
                 self._comma_count * self._comma_width)
        avail_digits = int(avail / self._digit_width)

        fmt_num = fmtr.formatNumber(self._number, avail_digits=avail_digits)
        indent = 0 if self._number < 0 else self._minus_width
        html = fmt_num.html()
        if indent:
            html = f"<p style='margin-left: {int(indent)}'>{html}</p>"
        self.setHtml(html)

        self.document().setIndentWidth(indent)

        if fmt_num.type == formatting.NumberType.weird:
            over_color = ThemeColor.warning
        elif fmt_num.type == formatting.NumberType.error:
            over_color = ThemeColor.error
        else:
            over_color = None
        self.setOverrideColor(over_color)


class ColorChangeRectangle(core.RectangleGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._alt_color: converters.ColorSpec = ThemeColor.primary
        self._blend = 0.0

    _alt_color = DynamicColor()

    @settable(argtype=QtGui.QColor)
    def setAltColor(self, color: converters.ColorSpec) -> None:
        self._alt_color = color
        self.update()

    def blendValue(self) -> float:
        return self._blend

    def setBlendValue(self, blend: float) -> None:
        self._blend = blend
        self.update()

    blend = QtCore.Property(float, blendValue, setBlendValue)

    def animateBlend(self, blend: float, **kwargs) -> None:
        self.animateProperty(b"blend", self.blendValue(), blend, **kwargs)

    def stopBlendAnimation(self) -> None:
        self.stopPropertyAnimation(b"blend")

    def effectiveBrush(self) -> QtGui.QBrush:
        if self._blend == 0.0:
            return super().effectiveBrush()
        else:
            return QtGui.QBrush(self.effectiveFillColor())

    def effectiveFillColor(self) -> QtGui.QColor:
        c1 = super().effectiveFillColor()
        if not c1:
            return c1
        c2 = self._alt_color
        c = themes.blend(c1, c2, self._blend)
        return c


@graphictype("controls.switch")
class SwitchButtonGraphic(core.ClickableGraphic):
    stateChanged = QtCore.Signal(Qt.CheckState)
    toggled = QtCore.Signal(bool)

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._change_expr: Optional[config.PythonExpr] = None
        self._reversed = False
        self._radius = 8.0
        self._inner_margin = 3.0
        self._gap = 2.0
        self._duration = 250
        self._curve = QtCore.QEasingCurve.InOutBack
        self._checkstate = Qt.Unchecked

        self._bg = ColorChangeRectangle(self)
        self._bg.setPillShaped(True)
        self._bg.setFillColor(ThemeColor.button)
        self._bg.setAltColor(ThemeColor.primary)

        self._dot = ColorChangeRectangle(self)
        self._dot.setPillShaped(True)
        self._dot.setFillColor(ThemeColor.button_high)
        self._dot.setAltColor(ThemeColor.pressed)

        self._checkmark = makeCheckmark(self._dot)

        # TODO: update shadow when the palette changes
        shadow = QtWidgets.QGraphicsDropShadowEffect(self._dot)
        shadow.setBlurRadius(10.0)
        shadow.setColor(QtGui.QColor.fromRgbF(0.0, 0.0, 0.0, 0.75))
        shadow.setOffset(0, 2)
        self._dot.setGraphicsEffect(shadow)

        self.geometryChanged.connect(self._updateContents)
        self._updateContents()

    def localEnv(self) -> dict[str, Any]:
        return {
            "state": self.checkState(),
            "checked": self.isChecked()
        }

    @settable("on_state_change")
    def setOnStateChangeExpression(self,
                                   expr: Union[str, dict, config.PythonExpr]
                                   ) -> None:
        self._change_expr = config.PythonExpr.fromData(expr)

    @settable(argtype=QtGui.QColor)
    def setFillColor(self, color: QtGui.QColor) -> None:
        self._bg.setFillColor(color)

    @settable(argtype=QtGui.QColor)
    def setAltColor(self, color: QtGui.QColor) -> None:
        self._bg.setAltColor(color)

    def checkState(self) -> Qt.CheckState:
        return self._checkstate

    def setCheckState(self, state: Qt.CheckState, *, animated=False) -> None:
        animated = animated and not self.animationDisabled()
        old_state = self._checkstate
        if state != old_state:
            self._checkstate = state
            if state == Qt.PartiallyChecked:
                if animated:
                    self._dot.fadeOut()
                else:
                    self._dot.hide()
            else:
                checked = state == Qt.Checked
                if old_state == Qt.PartiallyChecked:
                    self._dot.fadeIn()

                blend = float(checked)
                if animated:
                    self._bg.animateBlend(float(checked),
                                          duration=self._duration,
                                          curve=self._curve)
                    self._dot.animateGeometry(self._dotRect(checked),
                                              duration=self._duration,
                                              curve=self._curve)
                    self._dot.animateBlend(blend)
                else:
                    self._updateContents()
                    self._dot.setBlendValue(blend)

                self._checkmark.setVisible(checked)
            self.stateChanged.emit(self._checkstate)
            self._evaluateExpr(self._change_expr)

    def isChecked(self) -> bool:
        return self._checkstate == Qt.Checked

    @settable()
    def setChecked(self, checked: bool, *, animated=False) -> None:
        self.setCheckState(Qt.Checked if checked else Qt.Unchecked,
                           animated=animated)

    def toggle(self, *, animated=True) -> None:
        self.setChecked(not self.isChecked(), animated=animated)
        self.toggled.emit(self.isChecked())

    @settable()
    def setDotRadius(self, radius: float) -> None:
        self.prepareGeometryChange()
        self._radius = radius
        self._updateContents()
        self.updateGeometry()

    def checkSize(self) -> int:
        return self._checkmark.textSize()

    def setCheckSize(self, size: int) -> None:
        self._checkmark.setTextSize(size)
        self._updateContents()

    def _dotRect(self, checked: bool) -> QtCore.QRectF:
        r = self._subRect()
        im = self._inner_margin
        diam = self._radius * 2
        y = r.y() + im
        x1 = r.x() + im
        x2 = r.right() - im - self._radius * 2
        if self._reversed:
            x = x1 if checked else x2
        else:
            x = x2 if checked else x1
        return QtCore.QRectF(x, y, diam, diam)

    def _updateContents(self) -> None:
        r = self._subRect()
        checked = self.isChecked()
        self._bg.setGeometry(r)
        self._bg.setCornerRadius(r.height() / 2)
        self._bg.setBlendValue(int(checked))

        dot_rect = self._dotRect(checked)
        self._dot.setBlendValue(float(checked))
        self._dot.setGeometry(dot_rect)

        dot_size = dot_rect.size()
        check_size = self._checkmark.implicitSize()
        check_x = dot_size.width() / 2 - check_size.width() / 2
        check_y = dot_size.height() / 2 - check_size.height() / 2
        check_rect = QtCore.QRectF(check_x, check_y,
                                   check_size.width(), check_size.height())
        self._checkmark.setGeometry(check_rect)
        self._checkmark.setVisible(self.isChecked())

    def implictSize(self) -> QtCore.QSizeF:
        im = self._inner_margin
        w = self._radius * 4 + im * 2 + self._gap
        h = self._radius * 2 + im * 2
        return QtCore.QSizeF(w, h)

    def _subRect(self) -> QtCore.QRectF:
        rect = self.rect()
        size = self.implictSize()
        return util.alignedRectF(self.layoutDirection(), Qt.AlignCenter,
                                 size, rect)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        if which in (Qt.MinimumSize, Qt.PreferredSize, Qt.MaximumSize):
            return self.implictSize()
        return constraint

    def onMousePress(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        event.accept()
        self.toggle()

    def onMouseRelease(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        event.accept()


@graphictype("controls.labeled_switch")
class LabeledSwitchGraphic(core.LayoutGraphic):
    property_aliases = {
        "text_size": "label.text_size",
        "dot_radius": "switch.dot_radius",
    }

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._switch = SwitchButtonGraphic(self)
        self._any_click = False
        self.stateChanged = self._switch.stateChanged

        self._label = TextGraphic(self)
        self._label.setTextColor(ThemeColor.fg)
        self._label.installEventFilter(self)
        self._text_rect = QtCore.QRectF()

        self._gap = 5.0
        self._row_height = 0.0

        self.setHasHeightForWidth(True)
        self.geometryChanged.connect(self._updateContents)

    @path_element(SwitchButtonGraphic)
    def switch(self) -> SwitchButtonGraphic:
        return self._switch

    @path_element(TextGraphic)
    def label(self) -> TextGraphic:
        return self._label

    def eventFilter(self, watched: TextGraphic, event: QtCore.QEvent) -> bool:
        if watched == self._label and event.type() == event.GraphicsSceneMousePress:
            pos = watched.mapToParent(event.pos())
            if self._any_click or self.labelRect().contains(pos):
                self.toggle(animated=True)
        return super().eventFilter(watched, event)

    def localEnv(self) -> dict[str, Any]:
        return self._switch.localEnv()

    @settable("on_state_change")
    def setOnStateChangeExpression(self, expr: config.Expr) -> None:
        self._switch.setOnStateChangeExpression(expr)

    def isClickAnywhere(self) -> bool:
        return self._any_click

    @settable(argtype=bool)
    def setClickAnywhere(self, anywhere: bool) -> None:
        self._any_click = anywhere

    def text(self) -> str:
        return self._label.html()

    @settable()
    def setText(self, html: str) -> None:
        self._label.setHtml(html)
        self.updateGeometry()
        self._updateContents()

    @settable()
    def setSpacing(self, space: float) -> None:
        self.layout().setSpacing(space)

    def checkState(self) -> Qt.CheckState:
        return self.switch().checkState()

    def setCheckState(self, state: Qt.CheckState) -> None:
        self.switch().setCheckState(state)

    def isChecked(self) -> bool:
        return self.switch().isChecked()

    @settable(argtype=bool)
    def setChecked(self, checked: bool, *, animated=False) -> None:
        self.switch().setChecked(checked, animated=animated)

    def toggle(self, *, animated=False) -> None:
        self.switch().toggle(animated=animated)

    def setFont(self, font: QtGui.QFont) -> None:
        self.prepareGeometryChange()
        super().setFont(font)
        self._label.setfont(font)
        self.updateGeometry()
        self._updateContents()

    def labelRect(self) -> QtCore.QRectF:
        return self._text_rect

    def _updateContents(self) -> None:
        r = self.rect().marginsRemoved(self._margins)
        switch = self._switch
        label = self._label
        fm = QtGui.QFontMetricsF(label.font())
        switch_sz = switch.implictSize()
        switch_w = switch_sz.width()
        switch_h = switch_sz.height()
        line_h = fm.height()
        row_h = max(switch_h, line_h)

        # sh = switch.implictSize().height()
        sy = r.y() + row_h / 2 - switch_h / 2
        lx = r.x() + switch_w + self._gap
        ly = r.y() + row_h / 2 - line_h / 2

        label_width = r.right() - lx
        self._text_rect = QtCore.QRectF(
            lx, r.y(), label_width, r.height()
        )

        sr = QtCore.QRectF(r.x(), sy, switch_w, switch_h)
        switch.setGeometry(sr)
        lr = QtCore.QRectF(lx, ly, r.right() - lx, r.bottom() - ly)
        label.setGeometry(lr)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        ms = self._margins
        constraint = constraint or QtCore.QSizeF(-1, -1)
        if which == Qt.PreferredSize:
            switch_size = self._switch.implictSize()
            if constraint.width() > 0:
                cw = constraint.width() - switch_size.width()
            else:
                cw = -1
            label_size = self._label.sizeHint(which, QtCore.QSizeF(cw, -1))
            width = switch_size.width() + self._gap + label_size.width()
            height = max(switch_size.height(), label_size.height())
            return QtCore.QSizeF(width + ms.left() + ms.right(),
                                 height + ms.top() + ms.bottom())
        return constraint

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.drawRect(self.labelRect())


@graphictype("controls.button")
class ButtonGraphic(core.ClickableGraphic):
    checkStateChanged = QtCore.Signal(bool)

    property_aliases = {
        "checkmark_glyph": "checkmark.glyph",
        "checkmark_color": "checkmark.text_color"
    }

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._click_expr: Optional[config.PythonExpr] = None
        self._change_expr: Optional[config.PythonExpr] = None
        self._colors_changed = False
        self._clickable = True
        self.setAcceptHoverEvents(True)
        self._label_align = Qt.AlignCenter
        self._rect = QtCore.QRectF()
        self._label_margins = QtCore.QMarginsF(16, 8, 16, 8)
        self._fills_space = True
        self._self_align = Qt.AlignCenter

        self._halo = core.RectangleGraphic(self)
        self._halo.setZValue(-5)
        self._halo.setPillShaped(True)
        self._halo.setFillColor(ThemeColor.primary)
        self._use_halo = True
        self._halo_offset = 0.0
        self._halo_opacity = 0.67
        self._halo_duration = 200

        self._bg = ColorChangeRectangle(self)
        self._bg.setZValue(-4)
        self._bg.setFillColor(ThemeColor.button)
        self._bg.setAltColor(ThemeColor.pressed)

        # Buttons have glint by default
        self.setFlat(False)

        self._checkable = False
        self._uncheckable = True
        self._checked = False
        self._check_blend = 0.0
        self._draw_check = True
        self._checkmark = makeCheckmark(self)
        self._spacing = 5.0

        self._draw_menu_glyph = True
        self._menu_glyph = StringGraphic(self)
        self._menu_glyph.setTextAlignment(Qt.AlignCenter)
        self._menu_glyph.setTextSize(10)
        self._menu_glyph.setGlyph(glyphs.FontAwesome.chevron_down)
        self._menu_glyph.setTextColor(ThemeColor.button_fg)
        self._menu_glyph_alignment = Qt.AlignLeft | Qt.AlignVCenter

        self._label = StringGraphic(self)
        self._label.setTextAlignment(Qt.AlignCenter)
        self._label.setTextColor(ThemeColor.button_fg)

        self._glow = self._bg.shadowEffect()
        self._glow.setBlurRadius(20.0)
        self._glow.setOffset(0, 0)
        self._glow.setEnabled(False)
        self._glow_color: converters.ColorSpec = ThemeColor.primary

        self._menu: Optional[QtWidgets.QMenu] = None

        # self.setText("Button")
        self.setMinimumSize(16, 16)

        # self._updateFonts()
        self._resetHalo()

        self.geometryChanged.connect(self._updateContents)
        # self._updateContents()
        # self._updateChecked()

        self.setCornerRadius(5.0)
        self.setPillShaped(True)

    _glow_color = DynamicColor()

    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == event.PaletteChange:
            self._colors_changed = True

    def _updateColors(self) -> None:
        self._glow.setColor(self._glow_color)
        self._colors_changed = False

    def localEnv(self) -> dict[str, Any]:
        return {
            "state": self.checkState(),
            "checked": self.isChecked()
        }

    @path_element(core.RectangleGraphic)
    def background(self) -> core.RectangleGraphic:
        return self._bg

    @path_element(StringGraphic)
    def label(self) -> StringGraphic:
        return self._label

    @path_element(StringGraphic)
    def checkmark(self) -> StringGraphic:
        return self._checkmark

    def checkState(self) -> Qt.CheckState:
        return Qt.Checked if self._checked else Qt.Unchecked

    @settable()
    def setCornerRadius(self, radius: float) -> None:
        self._bg.setCornerRadius(radius)
        self._halo.setCornerRadius(radius)

    @settable(argtype=bool)
    def setFlat(self, flat: bool) -> None:
        if flat:
            self._bg.setPen(Qt.NoPen)
        else:
            glint = QtGui.QLinearGradient(0, 0, 0, 1)
            glint.setColorAt(0.0, QtGui.QColor.fromRgbF(1, 1, 1, 0.3))
            glint.setColorAt(0.2, Qt.transparent)
            glint.setCoordinateMode(glint.ObjectMode)
            pen = QtGui.QPen(QtGui.QBrush(glint), 1.0)
            self._bg.setPen(pen)

    @settable(argtype=bool)
    def setPillShaped(self, is_pill: bool) -> None:
        self._bg.setPillShaped(is_pill)
        self._halo.setPillShaped(is_pill)

    @settable(argtype=QtGui.QColor)
    def setFillColor(self, color: converters.ColorSpec) -> None:
        self._bg.setFillColor(color)

    @settable(argtype=QtGui.QColor)
    def setPressedColor(self, color: converters.ColorSpec) -> None:
        self._bg.setAltColor(color)

    @settable(argtype=bool)
    def setIntersectWithParentShape(self, intersect: bool) -> None:
        super().setIntersectWithParentShape(intersect)
        self._bg.setIntersectWithParentShape(intersect)
        self._halo.setIntersectWithParentShape(intersect)

    def intersectionShape(self) -> QtGui.QPainterPath:
        if self._intersect_with_parent and (ps := self._parentShape()):
            return ps
        else:
            return self.shape()

    def isCheckable(self) -> bool:
        return self._checkable

    @settable(argtype=bool)
    def setCheckable(self, checkable: bool) -> None:
        self.prepareGeometryChange()
        self._checkable = checkable
        self.updateGeometry()
        self._updateContents()

    def setUncheckable(self, uncheckable: bool) -> None:
        self._uncheckable = uncheckable

    def isChecked(self) -> bool:
        return self._checked

    @settable(argtype=bool)
    def setChecked(self, checked: bool, *, animated=False) -> None:
        if checked != self._checked:
            self._checked = checked
            self._updateChecked(animated=animated)
            self.checkStateChanged.emit(checked)
            self._evaluateExpr(self._change_expr)

    def toggle(self, *, animated=False) -> None:
        if not self._uncheckable and self.isChecked():
            return
        self.setChecked(not self.isChecked(), animated=animated)

    @settable(argtype=bool)
    def setTransparent(self, tranparent: bool) -> None:
        self._bg.setVisible(not tranparent)

    def isDrawingCheckmark(self) -> bool:
        return self._draw_check

    @settable("on_click")
    def setOnClickExpression(self, expr: Union[str, dict, config.PythonExpr]
                             ) -> None:
        self._click_expr = config.PythonExpr.fromData(expr)

    @settable("on_state_change")
    def setOnStateChangeExpression(self,
                                   expr: Union[str, dict, config.PythonExpr]
                                   ) -> None:
        self._change_expr = config.PythonExpr.fromData(expr)

    @settable("checkmark_visible")
    def setDrawCheckmark(self, show_check: bool) -> None:
        self.prepareGeometryChange()
        self._draw_check = show_check
        self.updateGeometry()
        self._updateContents()
        self._updateChecked()

    def hasMenu(self) -> bool:
        return bool(self._menu)

    def setMenu(self, menu: QtWidgets.QMenu) -> None:
        self._menu = menu
        self._updateContents()

    @settable("menu")
    def setMenuItems(self, items: Sequence[str]) -> None:
        menu = QtWidgets.QMenu()
        for value in items:
            menu.addAction(value)
        self._menu = menu
        self._updateContents()

    def willDrawMenuGlyph(self) -> bool:
        return self._draw_menu_glyph

    def menuGlyphVisible(self) -> bool:
        return bool(self.willDrawMenuGlyph() and self.hasMenu())

    @settable(argtype=bool)
    def setDrawMenuGlyph(self, draw_menu_glyph: bool) -> None:
        self.prepareGeometryChange()
        self._draw_menu_glyph = draw_menu_glyph
        self._updateContents()

    @settable(argtype=Qt.Alignment)
    def setMenuGlyphAlignment(self, align: Qt.Alignment) -> None:
        self._menu_glyph_alignment = align
        self._updateContents()
        self.updateGeometry()

    def setLabelItem(self, graphic: Graphic) -> None:
        # if self._label:
        #     self._label.deleteLater()
        self._label = graphic
        self._label.setParentItem(self)
        self._label.setZValue(1)
        self._updateContents()
        self.update()

    @settable(argtype=QtGui.QColor)
    def setLabelColor(self, color: QtGui.QColor) -> None:
        label = self.label()
        if label:
            if isinstance(label, AbstractTextGraphic):
                label.setTextColor(color)

    def labelMargins(self) -> QtCore.QMarginsF:
        return self._label_margins

    @settable(argtype=QtCore.QMarginsF)
    def setLabelMargins(self, ms: QtCore.QMarginsF) -> None:
        self._label_margins = ms
        self._updateContents()

    def text(self) -> str:
        return self._label.text()

    @settable()
    def setText(self, text: str) -> None:
        self.prepareGeometryChange()
        if self._label and isinstance(self._label, AbstractTextGraphic):
            self._label.setText(text)
        else:
            self.setLabelItem(self._makeTextLabel(text))
        self.updateGeometry()
        self._updateContents()

    def setBorderColor(self, color: converters.ColorSpec) -> None:
        self.background().setBorderColor(color)

    def setBorderWidth(self, width: float) -> None:
        self.background().setBorderWidth(width)

    def setTextSize(self, size: int) -> None:
        self.label().setTextSize(size)

    def setTextColor(self, color: converters.ColorSpec) -> None:
        self.label().setTextColor(color)

    def setGlyph(self, glyph: glyphs.Glyph) -> None:
        self.prepareGeometryChange()
        self.setLabelMargins(QtCore.QMarginsF(4, 4, 4, 4))
        label = self.label()
        label.setGlyph(glyph)
        super().setFont(label.font())
        self.updateGeometry()

    @settable("glyph")
    def setGlyphName(self, name: str) -> None:
        glyph = glyphs.forName(name)
        if glyph:
            self.setGlyph(glyph)

    # @settable()
    # def setSvgGlyph(self, name: str) -> None:
    #     label = SvgGraphic(self)
    #     label.setGlyph(name)
    #     label.setMonochromeRole(self.labelRole())
    #     self.setLabelItem(label)

    def labelAlignment(self) -> Qt.Alignment:
        label = self._label
        if isinstance(label, AbstractTextGraphic):
            return label.textAlignment()
        else:
            return self._label_align

    @settable("label_align", argtype=Qt.Alignment)
    def setLabelAlignment(self, align: Qt.Alignment):
        self._label_align = align
        label = self._label
        if isinstance(label, AbstractTextGraphic):
            label.setTextAlignment(align)

    def setFont(self, font: QtGui.QFont) -> None:
        self.prepareGeometryChange()
        super().setFont(font)
        self._updateFonts()
        self.updateGeometry()

    @settable("text_size", converter=converters.textSizeConverter)
    def setFontSize(self, size: int) -> None:
        font = self.font()
        font.setPixelSize(size)
        self.setFont(font)
        self._updateFonts()

    def _updateFonts(self) -> None:
        font = self.font()
        if self._label:
            self._label.setFont(font)
        self._menu_glyph.setTextSize(int(font.pixelSize() * 0.8))
        self._updateContents()

    def fillsSpace(self) -> bool:
        return self._fills_space

    @settable("fill_space", argtype=bool)
    def setFillsSpace(self, fill: bool) -> None:
        self._fills_space = fill
        self._updateContents()

    def alignmentInSpace(self) -> Qt.Alignment:
        return self._self_align

    @settable("align", argtype=Qt.Alignment)
    def setAlignmentInSpace(self, align: Qt.Alignment) -> None:
        self._self_align = align
        self._updateContents()

    def click(self) -> None:
        self.clicked.emit()
        self.onClick()

    def checkBlendValue(self) -> float:
        return self._check_blend

    def setCheckBlendValue(self, blend: float) -> None:
        self._check_blend = blend
        self._updateLabelPositions()

    checkBlend = QtCore.Property(float, checkBlendValue, setCheckBlendValue)

    def _checkmarkSize(self) -> QtCore.QSizeF:
        check_extent = self.font().pixelSize() * 0.5
        return QtCore.QSizeF(check_extent, check_extent)

    def _menuGlyphRect(self) -> QtCore.QRectF:
        crect = self.rect().marginsRemoved(self.labelMargins())
        size = self._menu_glyph.implicitSize()
        rect = util.alignedRectF(
            self.layoutDirection(), self._menu_glyph_alignment, size, crect
        )
        return rect

    def _contentRect(self) -> QtCore.QRectF:
        rect = self.rect().marginsRemoved(self.labelMargins())

        if self.menuGlyphVisible():
            mgw = self._menu_glyph.implicitSize().width()
            align = self._menu_glyph_alignment
            gap = self._spacing
            if align & Qt.AlignLeft:
                rect.setLeft(rect.left() + mgw + gap)
            elif align & Qt.AlignRight:
                rect.setWidth(rect.width() - mgw - gap)

        return rect

    def _bodyRect(self) -> QtCore.QRectF:
        rect = self.rect()
        if self.fillsSpace():
            return rect
        else:
            return util.alignedRectF(self.layoutDirection(), self._self_align,
                                     self.implicitSize(), rect)

    def _labelRect(self) -> QtCore.QRectF:
        rect = self._bodyRect()
        label = self.label()
        label_rect = self._contentRect()
        check_size = self._checkmarkSize()

        if label_rect.width() <= 0:
            label_rect.setX(rect.x())
            label_rect.setWidth(rect.width())
        if label_rect.height() <= 0:
            label_rect.setY(rect.y())
            label_rect.setHeight(rect.height())

        if isinstance(label, StringGraphic):
            sz = label.implicitSize()
        else:
            sz = label.effectiveSizeHint(
                Qt.PreferredSize, QtCore.QSizeF(label_rect.width(), -1)
            )
        label_rect = util.alignedRectF(
            self.layoutDirection(), self._label_align, sz, label_rect
        )

        if self._draw_check and self.isChecked() and label_rect.width():
            gap = self._spacing
            blend = self._check_blend
            full_width = label_rect.width() + check_size.width() + gap
            offset = (full_width - label_rect.width()) / 2.0 * blend
            label_rect.moveLeft(label_rect.x() + offset)
        return label_rect

    def _checkmarkRect(self, label_rect: QtCore.QRectF = None
                       ) -> QtCore.QRectF:
        label_rect = label_rect or self._labelRect()
        check_size = self._checkmarkSize()
        check_rect = util.alignedRectF(
            self.layoutDirection(), self._label_align, check_size, self.rect()
        )
        check_rect.moveRight(label_rect.x() - self._spacing)
        return check_rect

    def _updateChecked(self, *, animated=True) -> None:
        animated = animated and not self.animationDisabled()
        checked = self.isChecked()
        # p = QtGui.QPalette
        # border_role = themes.ACCENT_ROLE if checked else p.NoRole
        text_role = (ThemeColor.primary if checked
                     else ThemeColor.button_fg)
        # border_width = 2.0 if checked else 0.0
        self._bg.stopBlendAnimation()
        self._bg.setBlendValue(float(checked))
        self._label.setTextColor(text_role)
        self._glow.setEnabled(checked)

        check_blend = float(checked)
        if animated:
            self.animateProperty(b"checkBlend", self._check_blend, check_blend)
        else:
            self._check_blend = check_blend
            self._updateLabelPositions()

    def _updateLabelPositions(self) -> None:
        label_rect = self._labelRect()
        check_rect = self._checkmarkRect(label_rect)
        checkmark = self._checkmark

        checkmark.setGeometry(check_rect)
        self._label.setGeometry(label_rect)

        check_blend = self._check_blend
        if self._draw_check and check_blend:
            checkmark.show()
            checkmark.setOpacity(check_blend)
        else:
            checkmark.hide()

    def _updateContents(self) -> None:
        center = self.rect().center()
        self.setTransformOriginPoint(center)

        body_rect = self._bodyRect()
        self._bg.setGeometry(body_rect)
        self._bg.setTransformOriginPoint(center)

        hoff = self._halo_offset
        self._halo.setGeometry(body_rect.adjusted(-hoff, -hoff, hoff, hoff))
        self._halo.setTransformOriginPoint(body_rect.center())

        self._updateLabelPositions()

        show_menu_glyph = self.menuGlyphVisible()
        if show_menu_glyph:
            self._menu_glyph.setGeometry(self._menuGlyphRect())
        self._menu_glyph.setVisible(show_menu_glyph)

    def hasImplicitSize(self) -> bool:
        return True

    def implicitSize(self) -> QtCore.QSizeF:
        ms = self.labelMargins()
        sz = self._contentSizeHint(Qt.PreferredSize, None)
        w = sz.width() + ms.left() + ms.right()
        # if self.drawingMenuGlyph():
        #     w += self._menu_glyph.implicitSize() + self._spacing
        h = sz.height() + ms.top() + ms.bottom()
        return QtCore.QSizeF(w, h)

    def sizeHint(self, which: Qt.SizeHintRole, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        if which == Qt.PreferredSize:
            return self.implicitSize()
        else:
            return constraint

    def _contentSizeHint(self, which: Qt.SizeHintRole,
                         constraint: QtCore.QSizeF = None) -> QtCore.QSizeF:
        sz = self._label.implicitSize()
        if self.isCheckable() and self.isDrawingCheckmark():
            w = sz.width() + self._checkmarkSize().width() + self._spacing
            sz.setWidth(w)
        return sz

    @settable(argtype=bool)
    def setHaloEnabled(self, enabled: bool) -> None:
        self._use_halo = enabled

    def haloOffsetValue(self) -> float:
        return self._halo_offset

    def setHaloOffsetValue(self, off: float) -> None:
        bg_rect = self._bodyRect()
        self._halo_offset = off
        self._halo.setGeometry(bg_rect.adjusted(-off, -off, off, off))

    haloOffset = QtCore.Property(float, haloOffsetValue, setHaloOffsetValue)

    def _animatePress(self) -> None:
        if not self.animationDisabled():
            self._bg.animateBlend(1.0)
            if self._use_halo:
                self._halo.show()
                self._halo.setOpacity(self._halo_opacity)
                self.animateProperty(
                    b"haloOffset", self.haloOffsetValue(), 4.0,
                    curve=QtCore.QEasingCurve.OutBack, duration=self._halo_duration
                )
        else:
            self._bg.setBlendValue(1.0)

    def _animateRelease(self) -> None:
        if not self.animationDisabled():
            self._bg.animateBlend(0.0)
            if self._use_halo:
                self.animateProperty(
                    b"haloOffset", self.haloOffsetValue(), 0.0,
                    duration=self._halo_duration
                )
        else:
            self._bg.setBlendValue(0.0)

    def _animateTrigger(self) -> None:
        blend = 1.0 if self.isChecked() else 0.0
        if not self.animationDisabled():
            self._bg.animateBlend(blend)
            if self._use_halo:
                self._halo.show()
                self._halo.setOpacity(self._halo_opacity)
                self.animateProperty(b"haloOffset", self.haloOffsetValue(), 8.0)
                self._halo.fadeOut(curve=QtCore.QEasingCurve.Linear,
                                   callback=self._resetHalo)
        else:
            self._bg.setBlendValue(blend)

    def _resetHalo(self) -> None:
        self.setHaloOffsetValue(0.0)
        self._halo.hide()

    def _animateHoverEnter(self) -> None:
        # self._bg.setHighlighted(True)
        pass

    def _animateHoverLeave(self) -> None:
        # self._bg.setHighlighted(False)
        pass

    def onMousePress(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        super().onMousePress(event)
        event.accept()
        if self._menu:
            pos = QtGui.QCursor.pos()
            self._mouse_pressed = False
            self._menu.popup(pos)
        else:
            self._animatePress()

    def onMouseRelease(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        event.accept()

    def onMouseEnter(self) -> None:
        if self._mouse_pressed:
            self._animatePress()
        else:
            self._animateHoverEnter()

    def onMouseLeave(self) -> None:
        if self._mouse_pressed:
            self._animateRelease()
        else:
            self._animateHoverLeave()

    def onClick(self) -> None:
        super().onClick()
        self._animateTrigger()
        if self.isCheckable():
            self.toggle(animated=True)
        # Evaluate click handler after checkable so it gets the new check state
        self._evaluateExpr(self._click_expr)

    def onCancel(self) -> None:
        super().onCancel()
        self._animateRelease()

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        if self._colors_changed:
            self._updateColors()
        super().paint(painter, option, widget)


@graphictype("controls.fancy_button")
class FancyButtonGraphic(ButtonGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._halo_opacity = 1.0
        self._gclrs = (QtGui.QColor("#ff0066"), QtGui.QColor("#ff00ff"),
                       QtGui.QColor("#0066ff"), QtGui.QColor("#00ffff"),
                       QtGui.QColor("#ff0066"))
        grad = QtGui.QConicalGradient(0.5, 0.5, 0.0)
        grad.setCoordinateMode(grad.ObjectMode)
        for i, clr in enumerate(self._gclrs):
            grad.setColorAt(1 / len(self._gclrs) * i, clr)
        self._halo.setBrush(QtGui.QBrush(grad))
        # self._halo.setBlurRadius(5.0)
        # self._halo.setZValue(5)
        self._resetHalo()

    def _resetHalo(self) -> None:
        self.setHaloOffsetValue(1.0)
        self._halo.show()
        self._halo.setOpacity(self._halo_opacity)


@graphictype("controls.simple_checkbox")
class SimpleCheckboxGraphic(core.AreaGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._check_blend = 0.0
        self._checkstate = Qt.Unchecked
        self._change_expr: Optional[config.Expr] = None
        self._click_expr: Optional[config.Expr] = None

        self._bg_off = ThemeColor.surface_lowest
        self._bg_on = ThemeColor.primary
        self._dot_off = ThemeColor.button_high
        self._dot_on = ThemeColor.pressed

        self._implicit_size = QtCore.QSizeF(16.0, 16.0)
        self._dot_size = 8.0
        self._dot_margin = 1.0

    _bg_off = DynamicColor()
    _bg_on = DynamicColor()
    _dot_off = DynamicColor()
    _dot_on = DynamicColor()

    @settable(argtype=QtCore.QSizeF)
    def setSize(self, size: QtCore.QSize) -> None:
        self.setFixedSize(size)
        self._implicit_size = size
        self.updateGeometry()

    @settable("off_bg_color", converter=converters.colorConverter)
    def setOffBackgroundColor(self, color: converters.ColorSpec) -> None:
        self._bg_off = color

    @settable("on_bg_color", converter=converters.colorConverter)
    def setOnBackgroundColor(self, color: converters.ColorSpec) -> None:
        self._bg_on = color

    @settable("off_dot_color", converter=converters.colorConverter)
    def setOffDotColor(self, color: converters.ColorSpec) -> None:
        self._dot_off = color

    @settable("on_dot_color", converter=converters.colorConverter)
    def setOnDotColor(self, color: converters.ColorSpec) -> None:
        self._dot_on = color

    @settable()
    def setDotSize(self, size: float) -> None:
        self._dot_size = size
        self.update()

    @settable()
    def setDotMargin(self, margin: float) -> None:
        self._dot_margin = margin
        self.update()

    def _checkBlend(self) -> float:
        return self._check_blend

    def _setCheckBlend(self, active: float) -> None:
        self._check_blend = active
        self.update()

    check_blend = QtCore.Property(float, _checkBlend, _setCheckBlend)

    def hasImplicitSize(self) -> bool:
        return True

    def implicitSize(self) -> QtCore.QSizeF:
        impsize = self._implicit_size
        if impsize:
            return QtCore.QSizeF(self._implicit_size)
        else:
            fxh = self._fixed_height
            height = 16.0 if fxh is None else fxh
            fxw = self._fixed_width
            width = height * 2 if fxw is None else fxw
        return QtCore.QSizeF(width, height)

    def localEnv(self) -> dict[str, Any]:
        return {
            "state": self.checkState(),
            "checked": self.isChecked()
        }

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        event.accept()
        mods = event.modifiers()
        extra_env = {
            "ctrl_key": bool(mods & Qt.ControlModifier or mods),
            "shift_key": bool(mods & Qt.ShiftModifier),
            "alt_key": bool(mods & Qt.AltModifier),
            "meta_key": bool(mods & Qt.MetaModifier),
        }
        self.toggle()
        self._evaluateExpr(self._click_expr, extra_env=extra_env)

    def checkState(self) -> Qt.CheckState:
        return self._checkstate

    def setCheckState(self, state: Qt.CheckState, *, animated=False) -> None:
        if state != self._checkstate:
            animated = animated and not self.animationDisabled()
            self._checkstate = state
            self._evaluateExpr(self._change_expr)

            active = float(self.isChecked())
            if animated:
                self.stopPropertyAnimation(b"check_blend")
                self.animateProperty(
                    b"check_blend", self._checkBlend(), active,
                    curve=QtCore.QEasingCurve.InOutBack
                )
            else:
                self._setCheckBlend(active)

    def isChecked(self) -> bool:
        return self._checkstate == Qt.Checked

    @settable()
    def setChecked(self, checked: bool, *, animated=False) -> None:
        self.setCheckState(Qt.Checked if checked else Qt.Unchecked,
                           animated=animated)

    def toggle(self, *, animated=True) -> None:
        self.setChecked(not self.isChecked(), animated=animated)
        self.update()

    @settable("on_click")
    def setOnClickExpression(self, expr: Union[str, dict, config.PythonExpr]
                             ) -> None:
        self._click_expr = config.PythonExpr.fromData(expr)

    @settable("on_state_change")
    def setOnStateChangeExpression(self, expr: Union[str, dict, config.PythonExpr]
                                   ) -> None:
        self._change_expr = config.PythonExpr.fromData(expr)

    def animateBlend(self, blend: float, **kwargs) -> None:
        self.animateProperty(b"blend", self.blendValue(), blend, **kwargs)

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        rect = self.rect()
        dsize = self._dot_size
        dm = self._dot_margin
        width = rect.width()
        height = dsize + dm * 2
        track_y = rect.center().y() - height / 2
        outer = QtCore.QRectF(rect.x(), track_y, width, height)
        inner = outer.adjusted(dm, dm, -dm, -dm)

        blend = self._checkBlend()
        bg_c = themes.blend(self._bg_off, self._bg_on, blend)
        dot_c = themes.blend(self._dot_off, self._dot_on, blend)

        x1 = inner.x()
        x2 = inner.right() - dsize
        x = x1 + (x2 - x1) * blend
        dot_rect = QtCore.QRectF(x, inner.y(), dsize, dsize)

        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_c)
        painter.drawRoundedRect(outer, height / 2, height / 2)

        painter.setBrush(dot_c)
        painter.drawRoundedRect(dot_rect, dsize / 2, dsize / 2)


@graphictype("controls.checkbox")
class CheckboxGraphic(ButtonGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        self._box_size = QtCore.QSizeF(16, 16)
        super().__init__(parent)
        self._gap = 5.0
        self.setCheckable(True)
        self.setLabelMargins(QtCore.QMarginsF(0, 0, 0, 0))
        self.label().setTextAlignment(Qt.AlignLeft)

    def boxSize(self) -> QtCore.QSizeF:
        return self._box_size

    def setBoxSize(self, size: QtCore.QSizeF) -> None:
        self.prepareGeometryChange()
        self._box_size = size
        self.updateGeometry()

    def spacing(self) -> float:
        return self._gap

    def setSpacing(self, gap: float) -> None:
        self._gap = gap
        self._updateLabelPositions()

    def _bodyRect(self) -> QtCore.QRectF:
        return util.alignedRectF(self.layoutDirection(), Qt.AlignLeft,
                                 self.boxSize(), self.rect())

    def _labelRect(self) -> QtCore.QRectF:
        rect = self.rect()
        bg_rect = self._bodyRect()
        rect.setLeft(bg_rect.right() + self.spacing())
        return rect

    def _checkmarkRect(self, label_rect: QtCore.QRectF = None
                       ) -> QtCore.QRectF:
        return self._bodyRect()


@graphictype("controls.tool_button")
class ToolButtonGraphic(ButtonGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        self._orientation = Qt.Horizontal
        self._icon: Optional[StringGraphic | PixmapGraphic] = None
        self._label_blend = 0.0
        # Track these separately from the actual .isVisible() of the items
        # because they might be fading out but still visible
        self._label_visible = False
        self._icon_visible = False

        super().__init__(parent)

        self._text_before_icon = False
        self._icon = StringGraphic(self)
        self._icon.setTextAlignment(Qt.AlignCenter)
        self._alt_icon: Optional[StringGraphic | PixmapGraphic] = None
        self.setLabelMargins(QtCore.QMarginsF(8, 8, 8, 8))

    @path_element(Graphic)
    def iconItem(self) -> Optional[Graphic]:
        return self._icon

    @path_element(StringGraphic)
    def glyphItem(self) -> StringGraphic:
        if not isinstance(self._icon, StringGraphic):
            self._icon = StringGraphic(self)
            self._icon.setTextAlignment(Qt.AlignCenter)
            self._icon.setVisible(self._icon_visible)
        return self._icon

    def setGlyph(self, glyph: glyphs.Glyph) -> None:
        self.glyphItem().setGlyph(glyph)
        if not self._icon_visible:
            self.setIconVisible(True, animated=False)

    @path_element(PixmapGraphic)
    def pixmapItem(self) -> PixmapGraphic:
        if not isinstance(self._icon, PixmapGraphic):
            self._icon = PixmapGraphic(self)
            self._icon.setVisible(self._icon_visible)
        return self._icon

    @settable("image")
    def setImagePath(self, path: pathlib.Path | str) -> None:
        self.pixmapItem().setPath(path)
        if not self._icon_visible:
            self.setIconVisible(True, animated=False)

    def setIcon(self, icon: QtGui.QIcon) -> None:
        self.pixmapItem().setIcon(icon)
        if not self._icon_visible:
            self.setIconVisible(True, animated=False)

    @settable()
    def setHoudiniIcon(self, name: str):
        self.pixmapItem().setHoudiniIcon(name)
        if not self._icon_visible:
            self.setIconVisible(True, animated=False)

    def orientation(self) -> Qt.Orientation:
        return self._orientation

    @settable(argtype=Qt.Orientation)
    def setOrientation(self, orient: Qt.Orientation) -> None:
        self._orientation = orient
        self._updateContents()

    def isTextBeforeIcon(self) -> bool:
        return self._text_before_icon

    @settable()
    def setTextBeforeIcon(self, reverse: bool) -> None:
        self._text_before_icon = reverse
        self._updateContents()

    def labelBlendValue(self) -> float:
        return self._label_blend

    def setLabelBlendValue(self, blend: float) -> None:
        self._label_blend = blend
        self.updateGeometry()

    labelBlend = QtCore.Property(float, labelBlendValue, setLabelBlendValue)

    @settable()
    def setText(self, text: str) -> None:
        super().setText(text)
        if not self._label_visible:
            self.setLabelVisible(True, animated=False)

    def isLabelVisible(self) -> bool:
        return self._label_visible

    @settable()
    def setLabelVisible(self, label_visible: bool, animated=True) -> None:
        label_visible = bool(label_visible)
        if self._label_visible == label_visible:
            return

        animated = animated and not self.animationDisabled()
        self.prepareGeometryChange()
        self._label_visible = label_visible
        blend = float(label_visible)
        if not animated:
            self._label_blend = blend
            self._label.setOpacity(blend)
            self.updateGeometry()
            self._updateContents()
        else:
            self._label.fadeTo(blend)
            self.animateProperty(b"labelBlend", self.labelBlend, blend,
                                 duration=200)

    def isIconVisible(self) -> bool:
        return self._icon_visible

    @settable()
    def setIconVisible(self, icon_visible: bool, animated=True) -> None:
        icon_visible = bool(icon_visible)
        if self._icon_visible == icon_visible:
            return

        animated = animated and not self.animationDisabled()
        self.prepareGeometryChange()
        self._icon_visible = icon_visible
        if not animated:
            self._icon.setVisible(icon_visible)
            self._updateContents()
        else:
            self._icon.fadeTo(float(icon_visible))
        self.updateGeometry()

    def _contentRect(self) -> QtCore.QRectF:
        crect = super()._contentRect()
        gap = self._spacing
        horiz = self._orientation == Qt.Horizontal
        icon_rect = self._iconRect()
        text_before = self._text_before_icon
        # inv_blend = 1.0 - self._label_blend

        if self._icon_visible and (self._label_visible or self._label_blend):
            if horiz:
                if text_before:
                    crect.setRight(icon_rect.x() - gap)
                else:
                    crect.setLeft(icon_rect.right() + gap)
            else:
                if text_before:
                    crect.setBottom(icon_rect.y() - gap)
                else:
                    crect.setTop(icon_rect.y() + gap)
        return crect

    def _iconRect(self) -> QtCore.QRectF:
        rect = super()._contentRect()
        horiz = self._orientation == Qt.Horizontal
        size = self._icon.implicitSize()
        icon_rect = QtCore.QRectF(rect)
        text_before = self._text_before_icon
        if self._label_visible or self._label_blend:
            if horiz:
                icon_rect.setWidth(size.width())
                if text_before:
                    icon_rect.moveRight(rect.right())
            else:
                icon_rect.setHeight(size.height())
                if text_before:
                    icon_rect.moveBottom(rect.bottom())
        return icon_rect

    def _contentSizeHint(self, which: Qt.SizeHintRole,
                         constraint: QtCore.QSizeF = None) -> QtCore.QSizeF:
        horiz = self._orientation == Qt.Horizontal
        icon_size = self._icon.implicitSize() if self._icon else QtCore.QSizeF()
        label_size = (self._label.implicitSize() if self._label else
                      QtCore.QSizeF())
        blend = self._label_blend
        gap = self._spacing
        w = h = 0.0
        if horiz:
            if self._icon_visible:
                w += icon_size.width()
            if self._label_visible or blend:
                w += label_size.width() * blend
            if self._icon_visible and self._label_visible:
                w += gap
            h = max(icon_size.height(), label_size.height())
        else:
            if self._icon_visible:
                h += icon_size.height()
            if self._label_visible or blend:
                w += label_size.height() * blend
            if self._icon_visible and self._label_visible:
                w += gap
            w = max(icon_size.width(), label_size.width())
        return QtCore.QSizeF(w, h)

    def _updateLabelPositions(self) -> None:
        super()._updateLabelPositions()
        self._icon.setGeometry(self._iconRect())

    def _updateChecked(self, animated=True) -> None:
        super()._updateChecked(animated=animated)
        if self._icon and isinstance(self._icon, StringGraphic):
            text_role = (ThemeColor.pressed_fg if self.isChecked()
                         else ThemeColor.button_fg)
            self._icon.setTextColor(text_role)


@graphictype("controls.slider")
class SliderGraphic(core.RectangleGraphic):
    valueChanged = QtCore.Signal(float)
    valueEdited = QtCore.Signal(float)

    property_aliases = {
        "handle_size": "handle.fixed_size"
    }

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._pressed = False
        self._orientation = Qt.Horizontal
        self._inverted = False
        self._min = 0.0
        self._max = 10.0
        self._value = 0.0
        self._snap_to_int = False
        self._snap_radius = 0.5

        self._track_width = 3.0
        self._show_ticks = False
        self._show_tick_text = False
        self._tick_text_decimal_places = 1
        self._tick_text_offset = 0.0
        self._tick_interval = 1.0
        self._tick_length = 4.0
        self._tick_width = 1.0
        self._tick_color = ThemeColor.secondary
        self._ticks_before = False
        self._track = core.RectangleGraphic(self)
        self._track.setPillShaped(True)
        self._track.setFillColor(ThemeColor.secondary_surface)

        self._handle = ButtonGraphic(self)
        self._handle.setClickable(False)
        self._handle.setPillShaped(True)
        self._handle.setFillColor(ThemeColor.button)
        self._handle.setPressedColor(ThemeColor.primary)
        self._handle.background().setBorderColor(ThemeColor.button_high)
        self._handle.background().setBorderWidth(2.0)
        self._handle.resize(16, 16)
        self._handle.setZValue(1)

        # TODO: update shadow when the palette changes
        shadow = QtWidgets.QGraphicsDropShadowEffect(self._handle)
        shadow.setBlurRadius(10.0)
        shadow.setColor(QtGui.QColor.fromRgbF(0.0, 0.0, 0.0, 0.75))
        shadow.setOffset(0, 1)
        self._handle.setGraphicsEffect(shadow)

        self.geometryChanged.connect(self._updateContents)
        self._updateContents()

    _tick_color = DynamicColor()

    def value(self) -> float:
        return self._value

    def setValue(self, value: float, interactive=False) -> None:
        animated = not (interactive or self.animationDisabled())
        value = max(self._min, min(self._max, value))
        if self._snap_to_int and not value.is_integer():
            rounded = round(value)
            if abs(value - rounded) <= self._snap_radius:
                value = rounded

        self._value = value
        self.valueChanged.emit(self._value)
        if interactive:
            self.valueEdited.emit(self._value)

        self._positionHandle(animated=animated)

    @path_element(ButtonGraphic)
    def handle(self) -> ButtonGraphic:
        return self._handle

    @path_element(core.RectangleGraphic)
    def track(self) -> core.RectangleGraphic:
        return self._track

    def handleSize(self) -> QtCore.QSizeF:
        return self._handle.size()

    def setHandleSize(self, size: QtCore.QSizeF) -> None:
        self.prepareGeometryChange()
        self._handle.resize(size)
        self.updateGeometry()

    def trackWidth(self) -> float:
        return self._track_width

    def setTrackWidth(self, width: float) -> None:
        self._track_width = width
        self._updateContents()

    def minimum(self) -> float:
        return self._min

    @settable()
    def setMinimum(self, minimum: float) -> None:
        self._min = minimum
        self._updateContents()

    def maximum(self) -> float:
        return self._max

    @settable()
    def setMaximum(self, maximum: float) -> None:
        self._max = maximum
        self._updateContents()

    def orientation(self) -> Qt.Orientation:
        return self._orientation

    @settable(argtype=Qt.Orientation)
    def setOrientation(self, orient: Qt.Orientation) -> None:
        self.prepareGeometryChange()
        self._orientation = orient
        self.updateGeometry()
        self._updateContents()

    def isInverted(self) -> bool:
        return self._inverted

    @settable(argtype=bool)
    def setInverted(self, inverted: bool) -> None:
        self._inverted = inverted
        self._updateContents()

    def isTicksBeforeSlider(self) -> bool:
        return self._ticks_before

    @settable(argtype=bool)
    def setTicksBeforeSlider(self, ticks_before: bool) -> None:
        self._ticks_before = ticks_before
        self._updateContents()

    def snapsToInts(self) -> bool:
        return self._snap_to_int

    @settable(argtype=bool)
    def setSnapToInts(self, snapping: bool) -> None:
        self._snap_to_int = snapping
        self.setValue(self._value)

    def fraction(self) -> float:
        return self.valueToFraction(self._value)

    def valueToFraction(self, value: float) -> float:
        fraction = (value - self._min) / (self._max - self._min)
        if self._inverted:
            fraction = 1.0 - fraction
        return fraction

    def fractionToValue(self, fraction: float) -> float:
        if self._inverted:
            fraction = 1.0 - fraction
        return (self._max - self._min) * fraction + self._min

    def valueToOffset(self, value: float) -> float:
        track_start, track_length = self._trackExtent()
        fraction = self.valueToFraction(value)
        return track_start + (track_length * fraction)

    def offsetToValue(self, offset: float) -> float:
        track_start, track_length = self._trackExtent()
        fraction = (offset - track_start) / track_length
        return self.fractionToValue(fraction)

    def currentOffset(self) -> float:
        return self.valueToOffset(self._value)

    def _handleRect(self) -> QtCore.QRectF:
        horiz = self._orientation == Qt.Horizontal
        rect = self.rect()
        ctr = rect.center()
        handle = self._handle
        handle_size = handle.size()
        handle_length = handle_size.width() if horiz else handle_size.height()
        offset = self.currentOffset() - handle_length / 2
        if horiz:
            x = rect.x() + offset
            y = ctr.y() - handle_size.height() / 2
        else:
            x = ctr.x() - handle_size.width() / 2
            y = rect.y() + offset
        return QtCore.QRectF(QtCore.QPointF(x, y), handle_size)

    def _trackExtent(self) -> tuple[float, float]:
        rect = self.rect()
        handle_size = self._handle.size()
        horiz = self._orientation == Qt.Horizontal
        length = rect.width() if horiz else rect.height()
        handle_length = handle_size.width() if horiz else handle_size.height()
        track_start = (handle_length / 2)
        track_length = length - handle_length
        return track_start, track_length

    # def _tickTranslation(self) -> QtCore.QPointF:
    #     tick_offset = 0.0
    #     if self._show_ticks and self._tick_length:
    #         tick_offset = -self._tick_length / 2.0
    #         if self._ticks_before:
    #             tick_offset *= -1
    #     if self._orientation == Qt.Horizontal:
    #         return QtCore.QPointF(0.0, tick_offset)
    #     else:
    #         return QtCore.QPointF(tick_offset, 0.0)

    def _trackRect(self) -> QtCore.QRectF:
        rect = self.rect()
        ctr = rect.center()
        horiz = self._orientation == Qt.Horizontal
        track_width = self._track_width
        track_start, track_length = self._trackExtent()

        # Add extra to start and end to account for "caps"
        track_start -= track_width
        track_length += track_width * 2

        if horiz:
            track_rect = QtCore.QRectF(
                rect.x() + track_start, ctr.y() - track_width / 2,
                track_length, track_width
            )
        else:
            track_rect = QtCore.QRectF(
                ctr.x() - track_width / 2, rect.y() + track_start,
                track_width, track_length
            )
        return track_rect

    def _positionHandle(self, animated=False) -> None:
        animated = animated and not self.animationDisabled()
        handle = self._handle
        handle_rect = self._handleRect()
        if animated:
            handle.animateGeometry(handle_rect)
        else:
            handle.setGeometry(handle_rect)

    def _updateContents(self) -> None:
        self._track.setGeometry(self._trackRect())
        self._positionHandle()
        self.update()

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        event.accept()
        self._pressed = True
        self._handle._animatePress()
        self._pressAt(event.pos())

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        event.accept()
        self._pressed = False
        self._handle._animateRelease()

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        event.accept()
        if self._pressed:
            self._pressAt(event.pos())

    def _pressAt(self, pos: QtCore.QPointF) -> None:
        horiz = self._orientation == Qt.Horizontal
        value = self.offsetToValue(pos.x() if horiz else pos.y())
        self.setValue(value, interactive=True)

    def _drawTicks(self, painter: QtGui.QPainter):
        painter.setPen(QtGui.QPen(self._tick_color, self._tick_width))
        track_rect = self._trackRect()
        horiz = self._orientation == Qt.Horizontal
        before = self._ticks_before
        show_text = self._show_tick_text
        text_offset = self._tick_text_offset
        if horiz:
            start = track_rect.y() if before else track_rect.bottom()
        else:
            start = track_rect.x() if before else track_rect.right()
        length = self._tick_length
        if before:
            length *= -1

        interval = self._tick_interval
        if interval == 0.0:
            return

        fm = QtGui.QFontMetricsF(self.font())
        text_height = fm.ascent()

        value = self._min
        count = 0  # Limit the total number of ticks
        while value <= self._max and count < 100:
            offset = self.valueToOffset(value)

            if horiz:
                p1 = QtCore.QPointF(offset, start)
                p2 = QtCore.QPointF(offset, start + length)
            else:
                p1 = QtCore.QPointF(start, offset)
                p2 = QtCore.QPointF(start + length, offset)
            painter.drawLine(p1, p2)

            if show_text:
                display_value = round(value, self._tick_text_decimal_places)
                if display_value.is_integer():
                    display_value = int(display_value)
                text = str(display_value)
                text_width = fm.horizontalAdvance(text)
                if horiz:
                    x = offset - text_width / 2
                    y = start + length
                    if before:
                        pt = QtCore.QPointF(x, y - text_offset)
                    else:
                        pt = QtCore.QPointF(x, y + text_offset + text_height)
                else:
                    x = start + length
                    y = offset - text_height / 2
                    if before:
                        pt = QtCore.QPointF(x - text_offset - text_width, y)
                    else:
                        pt = QtCore.QPointF(x + text_offset, y)
                painter.drawText(pt, str(display_value))

            value += interval
            count += 1

    def crossWidth(self) -> float:
        horiz = self._orientation == Qt.Horizontal
        handle_size = self._handle.size()
        ext = handle_size.height() if horiz else handle_size.width()
        # If the track is actually wider than the handle, use that
        ext = max(self._track_width, ext)
        if self._show_ticks:
            ext += self._tick_length * 2
        if self._show_tick_text:
            ext += self._tick_text_offset
            fm = QtGui.QFontMetricsF(self.font())
            if horiz:
                ext += fm.ascent()
            else:
                ext += fm.horizontalAdvance(str(self._max))
        return ext

    def sizeHint(self, which: Qt.SizeHintRole, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        handle_size = self._handle.size()
        if which == Qt.MinimumSize:
            return handle_size
        elif which == Qt.PreferredSize:
            ext = self.crossWidth()
            if self._orientation == Qt.Horizontal:
                return QtCore.QSizeF(constraint.width(), ext)
            else:
                return QtCore.QSizeF(ext, constraint.height())
        return constraint

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        super().paint(painter, option, widget)
        # painter.drawRect(self.rect())

        interval = self._tick_interval
        if self._show_ticks and interval != 0.0:
            self._drawTicks(painter)


@graphictype("controls.popup_menu")
class PopupMenuGraphic(ButtonGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._widget = TransparentComboBox()
        self._widget.setMinimumSize(QtCore.QSize(0, 0))
        self._item = core.makeProxyItem(self, self._widget)
        self._item.setZValue(-1)

        self.setLabelMargins(QtCore.QMarginsF(8, 8, 8, 8))
        self.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._menu_glyph.setGlyph(glyphs.MaterialIcons.unfold_more)
        self._menu_glyph.setTextSize(converters.LARGE_TEXT_SIZE)

        self.geometryChanged.connect(self._updateContents)
        self.setZValue(2)

        self._widget.currentTextChanged.connect(self._onTextChanged)

    @path_element(QtWidgets.QComboBox)
    def comboBox(self) -> QtWidgets.QComboBox:
        return self._widget

    def setFont(self, font: QtGui.QFont) -> None:
        super().setFont(font)
        self._item.setFont(font)

    def menuGlyphVisible(self) -> bool:
        return True

    @settable("menu")
    def setMenuItems(self, items: Sequence[str]) -> None:
        self._widget.clear()
        self._widget.addItems(items)

    def _updateContents(self) -> None:
        super()._updateContents()
        self._item.setGeometry(self.rect())

    def _onTextChanged(self) -> None:
        self.setText(self._widget.currentText())


@graphictype("controls.toolbar")
class ToolbarGraphic(core.RectangleGraphic):
    property_aliases = {
        "h_space": "arrangement.h_space",
        "v_space": "arrangement.v_space",
        "spacing": "arrangement.spacing",
        "orientation": "arrangement.orientation",
        "justify": "arrangement.justify",
        "align": "arrangement.align"
    }

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._items: list[ButtonGraphic] = []
        self._arrangement = layouts.LinearArrangement(Qt.Horizontal)
        self._arrangement.setSpacing(10.0)
        self._arrangement.setJustification(layouts.Justify.start)
        self._default_size = QtCore.QSizeF()
        self._text_size: Union[int, str] = "small"

        layout = layouts.ArrangementLayout(self._arrangement)
        self.setLayout(layout)

    @path_element(layouts.LinearArrangement)
    def arrangement(self) -> layouts.LinearArrangement:
        return self._arrangement

    # def setArrangement(self, arrangement: layouts.Arrangement) -> None:
    #     self._arrangement = arrangement
        # self._updateContents(animated=False)

    @settable(argtype=QtCore.QSizeF)
    def setDefaultSize(self, size: QtCore.QSizeF) -> None:
        self._default_size = size

    def itemAt(self, index: int) -> ButtonGraphic:
        return self._items[index]

    def setIndexVisibility(self, index: int, visible: bool, animated=True
                           ) -> None:
        item = self.itemAt(index)
        animated = animated and not self.animationDisabled()
        if animated:
            if visible:
                item.fadeIn()
            else:
                item.fadeOut()
        else:
            item.setVisible(visible)
        item.fadeIn()
        self._updateContents(animated=animated)

    @settable(converter=converters.textSizeConverter)
    def setTextSize(self, size: Union[int, str]) -> None:
        self._text_size = size

    def addChild(self, item: QtWidgets.QGraphicsItem, index: int = None
                 ) -> None:
        super().addChild(item)
        if index is None:
            self._items.append(item)
            self.layout().addItem(item)
        else:
            self._items.insert(index, item)
            self.layout().insertItem(index, item)

    def addButton(self, text: str = None, index: int = None, *,
                  glyph: glyphs.Glyph = None, icon: QtGui.QIcon = None,
                  font_size: int = None,
                  checkable=False, checked=False, draw_check=True,
                  width: float = None, height: float = None,
                  min_width=24.0, min_height=24.0,
                  size: QtCore.QSize = None, enabled=True, visible=True,
                  name: str = None) -> ButtonGraphic:
        button = ToolButtonGraphic(self)
        if name:
            button.setObjectName(name)
        if text:
            button.setText(text)
        if glyph:
            button.setGlyph(glyph)
        elif icon:
            button.setIcon(icon)

        button.setFontSize(font_size if font_size is not None
                           else self._text_size)

        size = size or self._default_size
        if size and size.isValid():
            button.setPreferredSize(size)
        if width is not None:
            button.setPreferredWidth(width)
        if height is not None:
            button.setPreferredHeight(height)

        if width is None or width >= min_width:
            button.setMinimumWidth(min_width)
        if height is None or height >= min_height:
            button.setMinimumHeight(min_height)

        button.setLabelMargins(QtCore.QMarginsF(4, 4, 4, 4))
        button.setCheckable(checkable)
        button.setChecked(checked)
        button.setEnabled(enabled)
        button.setVisible(visible)
        button.setDrawCheckmark(draw_check)

        self.addChild(button, index=index)
        return button

    def _visibleItems(self) -> Sequence[Graphic]:
        return [it for it in self._items
                if it.isVisible() and not it.isFadingOut()]

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        return self._arrangement.sizeHint(which, constraint,
                                          self._visibleItems())

    # def _updateContents(self, animated=False) -> None:
    #     if self._arranging:
    #         return
    #     self._arranging = True
    #     animated = animated and not self.animationDisabled()
    #     rect = self.rect()
    #     items = self._visibleItems()
    #     self._arrangement.layoutItems(rect, items, animated=animated)
    #     self._arranging = False


@graphictype("controls.button_strip")
class ButtonStrip(ToolbarGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self.setCornerRadius(8.0)
        self._arrangement.setSpacing(1)
        # self.setClipping(True)

        self.geometryChanged.connect(self._updateShape)
        self.setHasHeightForWidth(True)

    def count(self) -> int:
        return len(self._items)

    def setCount(self, count: int) -> None:
        cur_count = self.count()
        if count < cur_count:
            self._truncate(count)
        elif count > cur_count:
            for _ in range(count - cur_count):
                self.addButton()
        self.updateGeometry()

    def addButton(self, text: str = None, index: int = None, *,
                  glyph: glyphs.Glyph = None, icon: QtGui.QIcon = None,
                  font_size: int = None,
                  checkable=False, checked=False, draw_check=True,
                  width: float = None, height: float = None,
                  min_width=12.0, min_height=12.0,
                  size: QtCore.QSize = None, enabled=True, visible=True,
                  name: str = None, cls: type[ButtonGraphic] = ButtonGraphic
                  ) -> ButtonGraphic:
        button = super().addButton(
            text=text, index=index, glyph=glyph, icon=icon, font_size=font_size,
            checkable=checkable, checked=checked, draw_check=draw_check,
            width=width, height=height, min_width=min_width,
            min_height=min_height, size=size, enabled=enabled, visible=visible,
            name=name,
        )
        button.setCornerRadius(0.0)
        button.setFlat(True)
        button.setPillShaped(False)
        button.setHaloEnabled(False)
        button.setIntersectWithParentShape(True)
        button.setLabelMargins(QtCore.QMarginsF(12, 4, 12, 4))
        return button

    def _truncate(self, length=0) -> None:
        while self.layout().count() > length:
            self._deleteItemAt(self.count() - 1)

    def _deleteItemAt(self, index: int) -> None:
        layout = self.layout()
        layout.removeAt(index)
        item = self._items.pop(index)
        # item.setParentItem(None)
        item.hide()

    @settable()
    def setLabels(self, labels: Sequence[str]) -> None:
        self.setCount(len(labels))
        for i, label in enumerate(labels):
            button = self.itemAt(i)
            button.setText(label)
        self.updateGeometry()

    def _updateShape(self) -> None:
        rect = self.rect()
        arng = self._arrangement
        if not self._items:
            return

        item_rects = [r for _, r
                      in arng.rects(Qt.PreferredSize, rect, self._items)]
        r = util.containingRectF(item_rects)
        self._shape = self._shapeForRect(r)

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.setPen(Qt.magenta)
    #     painter.drawPath(self.shape())

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        hint = self._arrangement.sizeHint(which, constraint, self._items)
        return hint


@graphictype("controls.mx_button_strip")
class MxButtonStrip(ButtonStrip):
    currentIndexChanged = QtCore.Signal(int)

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._change_expr: Optional[config.PythonExpr] = None
        self._current_index = -1

    def localEnv(self) -> dict[str, Any]:
        env = super().localEnv()
        env["current_index"] = self._current_index
        return env

    def addChild(self, item: ButtonGraphic, index: int = None
                 ) -> None:
        item.setCheckable(True)
        item.setUncheckable(False)
        if self._current_index == -1:
            self._current_index = 0
        item.setChecked(not self._items)  # Check the first item by default

        def callback(checked: bool) -> None:
            if checked:
                self.setCurrentItem(item)

        item.checkStateChanged.connect(callback)
        super().addChild(item)

    def clear(self) -> None:
        while self._items:
            item = self._items.pop()
            item.checkStateChanged.disconnect()
            # item.setParentItem(None)
            item.hide()

    def currentIndex(self) -> int:
        return self._current_index

    def currentItem(self) -> Optional[ButtonGraphic]:
        if self._current_index < 0:
            raise ValueError("No buttons")
        return self._items[self._current_index]

    @settable()
    def setCurrentIndex(self, index: int, animated=False) -> None:
        if index < 0:
            raise ValueError(f"Invalid current index: {index}")
        self._current_index = index
        for i, it in enumerate(self._items):
            it.setChecked(i == index, animated=animated)
            it.setZValue(2 if i == index else 0)
        self.currentIndexChanged.emit(index)
        self._evaluateExpr(self._change_expr)

    def setCurrentItem(self, item: ButtonGraphic, animated=False) -> None:
        index = self._items.index(item)
        self.setCurrentIndex(index, animated=animated)

    @settable("on_current_change")
    def setOnCurrentChangeExpression(
            self, expr: Union[str, dict, config.PythonExpr]) -> None:
        self._change_expr = config.PythonExpr.fromData(expr)


@graphictype("controls.transient_message")
class TransientMessageGraphic(core.Graphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._message: Optional[Graphic] = None
        self._alignment = Qt.AlignCenter
        self._showing = False
        self._in_duration = core.ANIM_DURATION_MS
        self._scale_curve = QtCore.QEasingCurve.OutBack
        self._out_duration = core.ANIM_DURATION_MS * 2
        self._out_scale_curve = QtCore.QEasingCurve.InBack
        self._click_to_dismiss = True
        self._auto_dismiss = False
        self._animating = False
        self._height = 0.0

        self._timer = QtCore.QTimer()
        self._timer.setInterval(300)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hideMessage)

        self._anim_group = QtCore.QParallelAnimationGroup()
        self._fade_anim = core.makeAnim(self, b"opacity",
                                        curve=QtCore.QEasingCurve.Linear)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._anim_group.addAnimation(self._fade_anim)
        self._scale_anim = core.makeAnim(self, b"scale", curve=self._scale_curve)
        self._scale_anim.setStartValue(0.5)
        self._scale_anim.setEndValue(1.0)
        self._anim_group.addAnimation(self._scale_anim)
        self._anim_group.finished.connect(self._transitionDone)

        self.setZValue(100)

    def _makeTextItem(self) -> None:
        self._message = StringGraphic(self)
        self._message.setTextAlignment(Qt.AlignCenter)
        self._message.setPillShaped(True)
        self._message.setFillColor(ThemeColor.success)
        self._message.setTextColor(ThemeColor.success_fg)
        self._message.setMargins(10, 5, 10, 5)

    def resizeEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self._updateContents()

    @path_element(TextGraphic)
    def messageItem(self) -> TextGraphic:
        return self._message

    @settable(argtype=Graphic)
    def setMessageItem(self, item: Graphic) -> None:
        self.prepareGeometryChange()
        item.setParentItem(self)
        self._message = item
        self.updateGeometry()

    @settable("text")
    def setText(self, text: str) -> None:
        self.prepareGeometryChange()
        if not self._message:
            self._makeTextItem()
        if isinstance(self._message, AbstractTextGraphic):
            self._message.setText(text)
        else:
            raise ValueError(f"Can't set text on item {self._message!r}")
        self.updateGeometry()

    def isClickToDismiss(self) -> bool:
        return self._click_to_dismiss

    @settable(argtype=bool)
    def setClickToDismiss(self, wait: bool) -> None:
        self._click_to_dismiss = wait

    def isAutoDismiss(self) -> bool:
        return self._auto_dismiss

    def setAutoDismiss(self, auto: bool) -> None:
        self._auto_dismiss = auto

    def delay(self) -> int:
        return self._timer.interval()

    @settable()
    def setDelay(self, delay_ms: int) -> None:
        self._timer.setInterval(delay_ms)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None,
                 ) -> QtCore.QSizeF:
        message = self._message
        if message:
            return message.sizeHint(which, constraint)
        else:
            return constraint

    def _containerHeight(self) -> float:
        return self._height

    def _setContainerHeight(self, height: float) -> None:
        self._height = height
        self.resize(self.size().width(), height)
        self.updateGeometry()

    containerHeight = QtCore.Property(float, _containerHeight, _setContainerHeight)

    def messageSizeForWidth(self, width: float) -> QtCore.QSizeF:
        message = self.messageItem()
        constraint = QtCore.QSizeF(width, -1)
        # effectiveSizeHint() always seems to expand to the constrant, which we
        # don't want here
        size = message.sizeHint(Qt.PreferredSize, constraint)
        return size

    def isMessageVisible(self) -> bool:
        return self._showing

    @settable(argtype=bool)
    def setMessageVisible(self, visible: bool, *, animated=False) -> None:
        animated = animated and not self.animationDisabled(ignore_visible=True)
        # geom = self.geometry()
        if animated:
            was_showing = self._showing

            if visible and not was_showing:
                # h = self.messageSizeForWidth(geom.width()).height()
                # self.animateProperty(
                #     b"containerHeight", 0.0, h,
                #     duration=duration, curve=QtCore.QEasingCurve.Linear,
                #     callback=callback
                # )
                self._animateIn()
            elif was_showing and not visible:
                # self.animateProperty(
                #     b"containerHeight", self.size().height(), 0.0,
                #     curve=QtCore.QEasingCurve.Linear, duration=duration,
                #     callback=callback
                # )
                self._animateOut()
        else:
            self.setVisible(visible)
            if visible and self.isAutoDismiss():
                self._timer.start()

        self._showing = visible

    def _animateIn(self) -> None:
        self._animating = True
        self._anim_group.setDirection(self._anim_group.Forward)
        self._anim_group.start()

    def _animateOut(self) -> None:
        self._animating = True
        self._anim_group.setDirection(self._anim_group.Backward)
        self._anim_group.start()

    def _transitionDone(self) -> None:
        self._animating = False
        if self._showing and self.isAutoDismiss():
            self._timer.start()

    def hideMessage(self) -> None:
        self.setMessageVisible(False, animated=True)

    def display(self, targets: Sequence[QtWidgets.QGraphicsItem] = None,
                click_to_dismiss: bool = None, auto_dismiss: bool = None,
                delay: int = None, alignment=Qt.AlignCenter, margin=10,
                animated=True) -> None:
        if targets:
            self.positionInside(targets, alignment=alignment, margin=margin)
        else:
            self.positionInViewport(alignment=alignment, margin=margin)
        if delay is not None:
            self.setDelay(delay)
        if click_to_dismiss is not None:
            self.setClickToDismiss(click_to_dismiss)
        if auto_dismiss is not None:
            self.setAutoDismiss(auto_dismiss)
        self.setMessageVisible(True, animated=animated)

    def positionInside(self, items: Sequence[QtWidgets.QGraphicsItem],
                       alignment=Qt.AlignCenter, margin=10.0) -> None:
        if not items:
            return

        first = items[0]
        scene = first.scene()
        if not scene:
            raise Exception(f"{first!r} is not in a scene")
        if scene is not self.scene():
            raise Exception(f"Not in the same scene as {first!r}")

        rect = first.mapRectToScene(first.rect())
        for item in items[1:]:
            rect = rect.united(item.mapRectToScene(item.rect()))

        view_rect = core.sceneViewport(scene)
        overlap = rect.intersected(view_rect)
        if overlap.isValid():
            area = overlap
        else:
            area = view_rect

            # Change alignment to indicate which direction "offscreen" the
            # selection was
            if rect.bottom() <= area.top():
                alignment = Qt.AlignTop
            elif rect.top() >= area.bottom():
                alignment = Qt.AlignBottom
            else:
                alignment = Qt.AlignVCenter

            if rect.right() <= area.left():
                alignment |= Qt.AlignLeft
            elif rect.left() >= area.right():
                alignment |= Qt.AlignRight
            else:
                alignment |= Qt.AlignHCenter

        self.positionInSceneRect(area, alignment=alignment, margin=margin)

    def positionInViewport(self, alignment=Qt.AlignCenter, margin=10.0) -> None:
        scene = self.scene()
        if not scene:
            raise Exception(f"{self!r} is not in a scene")
        area = core.sceneViewport(scene)
        self.positionInSceneRect(area, alignment=alignment, margin=margin)

    def positionInSceneRect(self, scene_rect: QtCore.QRectF,
                            alignment=Qt.AlignCenter, margin=10.0) -> None:
        message = self._message
        inset_rect = scene_rect.adjusted(margin, margin, -margin, -margin)
        if inset_rect.isValid():
            scene_rect = inset_rect
        if message.hasImplicitSize():
            size = message.implicitSize()
        else:
            size = self._message.effectiveSizeHint(Qt.PreferredSize,
                                                   scene_rect.size())
        rect = util.alignedRectF(self.layoutDirection(), alignment, size,
                                 scene_rect)
        self.setGeometry(rect)

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent
                        ) -> None:
        if self.isClickToDismiss() and self.isMessageVisible():
            self.hideMessage()

    def _updateContents(self) -> None:
        rect = self.rect()
        message = self._message
        if message:
            message.setGeometry(rect)
        self._height = rect.height()
        self.setTransformOriginPoint(rect.center())

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.setPen(Qt.magenta)
    #     painter.drawRect(self.rect())


@graphictype("controls.tab_dots")
class TabDotsGraphic(core.ClickableGraphic):
    currentIndexChanged = QtCore.Signal(int)
    dotClicked = QtCore.Signal(int)

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._rounded = True
        self._orientation = Qt.Horizontal
        self._count = 0
        self._current = 0
        self._dot = core.RectangleGraphic(self)
        self._dot.setFillColor(ThemeColor.primary)
        self._dot.setPillShaped(self._rounded)
        self._dot_color = ThemeColor.button
        self._spacing = 10.0
        self._dot_size = QtCore.QSizeF(8, 8)
        self._alignment = Qt.AlignCenter
        self.geometryChanged.connect(self._positionDot)

    _dot_color = DynamicColor()

    @path_element(core.RectangleGraphic)
    def dot(self) -> core.RectangleGraphic:
        return self._dot

    def onMousePress(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        super().onMousePress(event)
        event.accept()
        if self._count:
            pos = event.pos()
            closest = -1
            min_dist = 99999.0
            for i, rect in enumerate(self._dotRects()):
                ctr = rect.center()
                dist = (pos.x() - ctr.x()) ** 2 + (pos.y() - ctr.y()) ** 2
                if dist < min_dist:
                    closest = i
                    min_dist = dist
            self.setCurrentIndex(closest)
            self.dotClicked.emit(closest)

    def count(self) -> int:
        return self._count

    @settable()
    def setCount(self, count: int) -> None:
        self.prepareGeometryChange()
        self._count = count
        self.updateGeometry()
        self.update()
        self._positionDot()

    def currentIndex(self) -> int:
        return self._current

    @settable("current")
    def setCurrentIndex(self, current: int) -> None:
        self._current = current
        self._positionDot(animated=True)
        self.currentIndexChanged.emit(current)

    def spacing(self) -> float:
        return self._spacing

    @settable()
    def setSpacing(self, space: float) -> None:
        self.prepareGeometryChange()
        self._spacing = space
        self.updateGeometry()
        self.update()

    def dotSize(self) -> QtCore.QSizeF:
        return QtCore.QSizeF(self._dot_size)

    @settable(argtype=QtCore.QSizeF)
    def setDotSize(self, size: QtCore.QSizeF) -> None:
        self.prepareGeometryChange()
        self._dot_size = size
        self.updateGeometry()
        self.update()

    @settable()
    def setDotWidth(self, width: float) -> None:
        self.prepareGeometryChange()
        self._dot_size.setWidth(width)
        self.updateGeometry()
        self.update()

    @settable()
    def setDotWidth(self, height: float) -> None:
        self.prepareGeometryChange()
        self._dot_size.setHeight(height)
        self.updateGeometry()
        self.update()

    def isRounded(self) -> bool:
        return self._rounded

    @settable()
    def setRounded(self, rounded: bool) -> None:
        self._rounded = rounded
        self._dot.setPillShaped(rounded)
        self.update()

    def hasImplicitSize(self) -> bool:
        return True

    def implicitSize(self) -> QtCore.QSizeF:
        count = self.count()
        space = self.spacing()
        size = QtCore.QSizeF(self._dot_size)
        if count >= 2:
            extra = space * (count - 1)
            if self._orientation == Qt.Horizontal:
                width = size.width() * count + extra
                size.setWidth(width)
            else:
                height = size.height() * count + extra
                size.setHeight(height)
        return size

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        if which in (Qt.MinimumSize, Qt.PreferredSize, Qt.MaximumSize):
            size = self.implicitSize()
            if constraint.width() >= 0:
                size.setWidth(constraint.width())
            if constraint.height() >= 0:
                size.setHeight(constraint.height())
        return constraint

    def _dotsArea(self) -> QtCore.QRectF:
        rect = self.rect()
        area_size = self.implicitSize()
        return util.alignedRectF(
            self.layoutDirection(), self._alignment, area_size, rect
        )

    def _positionDot(self, animated=False) -> None:
        animated = animated and not self.animationDisabled()
        dot = self._dot
        current = self._current
        if 0 <= current < self._count:
            dot.show()
            space = self._spacing
            pos = self._dotsArea().topLeft()
            size = self._dot_size
            if self._orientation == Qt.Horizontal:
                pos.setX(pos.x() + current * (size.width() + space))
            else:
                pos.setY(pos.y() + current * (size.height() + space))
            rect = QtCore.QRectF(pos, size)
            if animated:
                dot.animateGeometry(rect, curve=QtCore.QEasingCurve.InOutBack)
            else:
                dot.setGeometry(rect)
        else:
            dot.hide()

    def _dotRects(self) -> Iterable[QtCore.QRectF]:
        area = self._dotsArea()
        dot_size = self._dot_size
        space = self._spacing

        if self._orientation == Qt.Horizontal:
            t = QtCore.QPointF(dot_size.width() + space, 0)
        else:
            t = QtCore.QPointF(0, dot_size.height() + space)

        rect = QtCore.QRectF(area.topLeft(), dot_size)
        for i in range(self._count):
            yield rect
            rect.translate(t)

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        count = self.count()
        if not count:
            return

        dot_size = self._dot_size
        rounded = self._rounded
        radius = 0.0
        if rounded:
            radius = min(dot_size.width(), dot_size.height()) / 2

        painter.setBrush(self._dot_color)
        painter.setPen(Qt.NoPen)
        for rect in self._dotRects():
            if rounded:
                painter.drawRoundedRect(rect, radius, radius)
            else:
                painter.drawRect(rect)


@graphictype("controls.tones")
class TonePaletteGraphic(Graphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent=parent)

        # self._tone_palette = Tones(0.0, 0.0)
        self._hue = None
        self._chroma = None
        self._attribute = "primary"

    @settable()
    def setPalette(self, name: str) -> None:
        self._attribute = name

    @settable()
    def setHue(self, hue: float) -> None:
        self._hue = hue
        self.update()

    @settable()
    def setChroma(self, chroma: float) -> None:
        self._chroma = chroma
        self.update()

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        r = self.rect()

        if self._attribute:
            theme = self.effectiveTheme()
            tone_palette = getattr(theme, self._attribute)
        else:
            from ..colorutils import Tones
            tone_palette = Tones(0.0, 0.0)

        if self._hue is not None:
            tone_palette.hue = self._hue
        if self._chroma is not None:
            tone_palette.chroma = self._chroma

        tones = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
        w = r.width() / len(tones)
        for i, tone in enumerate(tones):
            color = tone_palette.tone(tone)
            rr = QtCore.QRectF(r.x() + i * w, r.y(), w, r.height())
            painter.fillRect(rr, color)





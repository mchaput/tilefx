from __future__ import annotations
import enum
import math
from typing import Iterable, Optional, Sequence, Tuple, TypeVar, Union

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .. import converters, models
from ..config import settable
from ..themes import ThemeColor
from .core import graphictype, DynamicColor, DataGraphic


DEFAULT_TRACK_ROLE = ThemeColor.value
DEFAULT_TRACK_ALPHA = 0.25

T = TypeVar("T")


def _unitScale(rect: QtCore.QRectF) -> float:
    w = rect.width()
    h = rect.height()
    scale = h if w > h else w
    return scale


def _positiveAngle(angle: float) -> float:
    while angle < 0:
        angle += 360.0
    return angle


class SegmentStyle(enum.Enum):
    rectangle = enum.auto()
    circle = enum.auto()
    box = enum.auto()


def makeChartModel() -> models.DataModel:
    model = models.DataModel()
    model.setColumnCount(2)
    return model


def segmentStyleConverter(style: Union[str, SegmentStyle]) -> SegmentStyle:
    if isinstance(style, str):
        style = style.lower()
        if style == "rectangle":
            return SegmentStyle.rectangle
        elif style == "circle":
            return SegmentStyle.circle
        elif style == "box":
            return SegmentStyle.box
        else:
            raise ValueError(style)
    elif isinstance(style, SegmentStyle):
        return style
    else:
        raise TypeError(style)


class ArcItem(QtWidgets.QGraphicsEllipseItem):
    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawArc(self.rect(), self.startAngle(), self.spanAngle())


class ChartGraphic(DataGraphic):
    _use_modelReset = True
    _use_dataChanged = True
    _use_rowsInserted = True
    _use_rowsRemoved = True

    rowHighlighted = QtCore.Signal(int)

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._model: Optional[QtCore.QAbstractItemModel] = makeChartModel()
        self._name_spec = "name"
        self._name_data_id = models.DataID(0, Qt.DisplayRole)
        self._value_spec = "value"
        self._value_data_id = models.DataID(1, Qt.DisplayRole)
        self._color_spec = "decoration"
        self._color_data_id = models.DataID(0, Qt.DecorationRole)
        self._is_mono = False
        self._color: Optional[QtGui.QColor] = None

        self._show_track = False
        self._track_color = ThemeColor.value
        self._track_alpha = DEFAULT_TRACK_ALPHA

        self._normalizer = models.SmartNormalization()
        self._hilite_row = -1
        self._interactive = False
        self._square = False

        self.setAcceptHoverEvents(True)

    _color = DynamicColor()
    _track_color = DynamicColor()

    def _rowDataChanged(self, first_row: int, last_row: int) -> None:
        self.update()

    def _rowsInserted(self, _: QtCore.QModelIndex, first: int, last: int
                      ) -> None:
        self.update()

    def _rowsRemoved(self, _: QtCore.QModelIndex, first: int, last: int
                     ) -> None:
        self.update()

    def normalization(self) -> models.Normalization:
        return self._normalizer

    def setModel(self, model: Optional[QtCore.QAbstractItemModel]) -> None:
        super().setModel(model)
        if model:
            self.setNameDataID(self._name_spec)
            self.setValueDataID(self._value_spec)
            self.setColorDataID(self._color_spec)
        self.update()

    def setNormalization(self, norm: models.Normalization):
        self._normalizer = norm
        self.update()

    def total(self) -> Optional[float]:
        norm = self.normalization()
        return norm.total()

    @settable()
    def setTotal(self, total: Optional[float]):
        self.setNormalization(models.FractionOfNumber(total))
        self.update()

    def nameDataID(self) -> models.DataID:
        return self._name_data_id

    @settable("name_id")
    def setNameDataID(self, spec: Union[str, tuple[int, str], models.DataID]
                      ) -> None:
        self._name_spec = spec
        model = self.model()
        if model:
            try:
                self._name_data_id = models.specToDataID(model, spec)
            except models.NoRoleError:
                pass

    def valueDataID(self) -> models.DataID:
        return self._value_data_id

    @settable("value_id")
    def setValueDataID(self, spec: Union[str, tuple[int, str], models.DataID]
                        ) -> None:
        self._value_spec = spec
        model = self.model()
        if model:
            try:
                self._value_data_id = models.specToDataID(model, spec)
            except models.NoRoleError:
                pass

    def colorColumn(self) -> int:
        return self._color_data_id.column

    def colorDataRole(self) -> Union[int, str]:
        return self._color_data_id.role

    def colorDataID(self) -> models.DataID:
        return self._color_data_id

    @settable("color_id")
    def setColorDataID(self, spec: Union[str, tuple[int, str], models.DataID]
                        ) -> None:
        self._color_spec = spec
        model = self.model()
        if model:
            try:
                self._color_data_id = models.specToDataID(model, spec)
            except models.NoRoleError:
                pass

    @settable(argtype=QtGui.QColor)
    def setColor(self, color: QtGui.QColor) -> None:
        self._color = color
        self.update()

    def isMonochrome(self) -> bool:
        return self._is_mono

    @settable(argtype=bool)
    def setMonochrome(self, is_mono: bool) -> None:
        self._is_mono = is_mono
        self.update()

    def isSquare(self) -> bool:
        return self._square

    @settable()
    def setSquare(self, square: bool) -> None:
        self._square = square
        self.update()

    def isTrackVisible(self) -> bool:
        return self._show_track

    @settable()
    def setTrackVisible(self, visible: bool) -> None:
        self._show_track = visible
        self.update()

    def trackColor(self) -> QtGui.QColor:
        return self._track_color

    @settable(argtype=QtGui.QColor)
    def setTrackColor(self, color: QtGui.QColor):
        self._track_color = color

    def trackAlpha(self) -> float:
        return self._track_alpha

    @settable()
    def setTrackAlpha(self, alpha: float):
        self._track_alpha = alpha

    def effectiveTrackColor(self) -> Optional[QtGui.QColor]:
        tcolor = self.trackColor()
        tcolor.setAlphaF(self.trackAlpha())
        return tcolor

    def isInteractive(self) -> bool:
        return self._interactive

    @settable()
    def setInteractive(self, interactive: bool):
        self._interactive = interactive
        self.update()

    def hoverMoveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        super().hoverMoveEvent(event)
        if self.isInteractive():
            row = self.rowAtPos(event.pos())
            self._hilite_row = row
            self.rowHighlighted.emit(row)
            self.update()

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        super().hoverLeaveEvent(event)
        self._hilite_row = -1
        if self.isInteractive():
            self.rowHighlighted.emit(-1)
        self.update()

    def event(self, event: QtCore.QEvent) -> bool:
        if event.type() == event.ToolTip:
            text = self.toolTipAtPos(event.pos())
            if text:
                QtWidgets.QToolTip.showText(event.globalPos(), text)
                return True
        return super().event(event)

    def rowAtPos(self, pos: QtCore.QPointF) -> int:
        return -1

    def toolTipAtPos(self, pos: QtCore.QPoint) -> Optional[str]:
        row = self.rowAtPos(pos)
        if row != -1:
            index = self._model.index(row, self._namecol)
            text = self._model.data(index, Qt.ToolTipRole)
            return text

    def highlightedRow(self) -> int:
        return self._hilite_row

    def setHighlightedRow(self, row: int) -> None:
        self._hilite_row = row
        self.update()

    def rowCount(self) -> int:
        model = self.model()
        if model:
            return model.rowCount()
        return 0

    def rowColor(self, row: int) -> QtGui.QColor:
        # If a color or role override is set on this chart, use that instead of
        # getting the color from the model
        color = self._color
        if color:
            return color

        if self._is_mono:
            row = 0

        model = self.model()
        if not isinstance(row, int):
            raise ValueError(f"Row index is not an int: {row}")
        if row >= model.rowCount():
            raise IndexError(row)
        index = model.index(row, self.colorColumn())
        color = index.data(self.colorDataRole())
        color = converters.toColor(color, self)
        return color

    def setRowColor(self, color: converters.ColorSpec, row=0) -> None:
        color_id = self.colorDataID()
        model = self.model()
        index = model.index(row, color_id.column)
        model.setData(index, color, color_id.role)

    def valueAt(self, row: int) -> float:
        value_id = self.valueDataID()
        model = self.model()
        index = model.index(row, value_id.column)
        value = index.data(value_id.role) or 0.0
        return float(value)

    @settable()
    def setValue(self, value: float, row=0) -> None:
        value_id = self.valueDataID()
        model = self.model()
        ix = model.index(row, value_id.column)
        model.setData(ix, value, value_id.role)
        self.update()

    def values(self) -> Sequence[float]:
        return [self.valueAt(row) for row in range(self.rowCount())]

    @settable()
    def setValues(self, values: Sequence[float], start_row=0) -> None:
        row_count = self.rowCount()
        end_row = len(values) + start_row
        if end_row > row_count:
            model = self.model()
            new_count = end_row - row_count
            model.insertRows(start_row, new_count)

        for i, value in enumerate(values):
            self.setValue(value, start_row + i)
        self.update()

    def normalizedValues(self) -> Sequence[float]:
        norm = self.normalization()
        return norm.normalized(self.values())

    def chartRect(self) -> QtCore.QRectF:
        rect = self.rect()
        if self.isSquare():
            ctr = rect.center()
            w = min(rect.width(), rect.height())
            return QtCore.QRectF(ctr.x() - w/2, ctr.y() - w/2, w, w)
        else:
            return rect

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        r = self.rect()
        painter.setPen(Qt.red)
        painter.drawRect(r)


class CircularChartGraphic(ChartGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._clockwise = True
        self._startangle = 90.0
        self._sweep = 360.0
        self._gapangle = 0.0
        self._penwidth = 5.0
        self._textsize = 0.5
        self._capstyle = Qt.RoundCap
        self._square = True

    def isClockwise(self) -> bool:
        return self._clockwise

    @settable()
    def setClockwise(self, clockwise: bool):
        self._clockwise = clockwise
        self.update()

    def penWidth(self) -> float:
        return self._penwidth

    def penWidthForRow(self, row: int) -> float:
        pw = self.penWidth()
        hilited_row = self.highlightedRow()
        if row == hilited_row:
            pw *= 1.5
        elif hilited_row >= 0:
            pw *= 0.5
        return pw

    def setPenWidth(self, width: float) -> None:
        self._penwidth = width
        self.update()

    def chartRect(self) -> QtCore.QRectF:
        hw = self.penWidth() / 2.0
        return super().chartRect().adjusted(hw, hw, -hw, -hw)

    def _arcScale(self) -> float:
        return -1.0 if self.isClockwise() else 1.0

    def penCapStyle(self) -> Qt.PenCapStyle:
        return self._capstyle

    @settable()
    def setRounded(self, round_pencap: bool):
        style = Qt.RoundCap if round_pencap else Qt.FlatCap
        self.setPenCapStyle(style)
        self.update()

    def angleAndDistance(self, x: float, y: float) -> Tuple[float, float]:
        rect = self.chartRect()
        ctr = rect.center()
        scale = _unitScale(rect)
        dx = x - ctr.x()
        dy = y - ctr.y()
        angle = math.degrees(math.atan2(-dy, dx))
        if angle < 0:
            angle = 360 + angle
        dist = math.sqrt(dx ** 2 + dy ** 2) / scale
        return angle, dist

    def setAngles(self, start_degrees: float, sweep: float, clockwise=None):
        if clockwise is not None:
            self._clockwise = clockwise
        self._startangle = start_degrees
        self._sweep = sweep
        self.update()

    def gapAngle(self) -> float:
        return self._gapangle

    @settable()
    def setGapAngle(self, degrees: float):
        self._gapangle = degrees
        self.update()

    def startAngle(self) -> float:
        return self._startangle

    @settable()
    def setStartAngle(self, degrees: float):
        self._startangle = degrees
        self.update()

    def sweep(self) -> float:
        return self._sweep

    @settable()
    def setSweep(self, degrees: float):
        self._sweep = degrees
        self.update()

    def endAngle(self) -> float:
        start = self.startAngle()
        return start + self._sweep * self._arcScale()

    def setAngleAndGap(self, degrees: float, gap_degrees=0.0,
                       clockwise: bool = None):
        if clockwise is not None:
            self._clockwise = clockwise
        self._startangle = degrees
        self._gapangle = gap_degrees
        self.update()


@graphictype("stacked_donut")
class StackedDonutChartGraphic(CircularChartGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._normalizer = models.FractionOfSum()
        self._arcspacing = 0.0
        self._pie = False

    def isPie(self) -> bool:
        return self._pie

    @settable()
    def setPie(self, pie: bool) -> None:
        self._pie = pie
        self.update()

    def arcSpacing(self) -> float:
        return self._arcspacing

    @settable("spacing")
    def setArcSpacing(self, degrees: float) -> None:
        self._arcspacing = degrees
        self.update()

    def effectiveStartAndSweepAngles(self) -> tuple[float, float]:
        space = self.arcSpacing()
        scale = self._arcScale()
        start = self.startAngle()
        sweep = self.sweep()
        gap_degrees = self.gapAngle()
        if gap_degrees:
            start = start + gap_degrees / 2.0 * scale
            sweep -= gap_degrees
        sweep -= space * self.rowCount()
        return start, sweep

    def rowAtPos(self, pos: QtCore.QPointF) -> int:
        angle, dist = self.angleAndDistance(pos.x(), pos.y())
        angle = _positiveAngle(angle)
        if (0.5 - self.penWidth() - 0.3) <= dist <= 0.8:
            for i, (arc_angle, arc_span) in enumerate(self._arcs()):
                arc_start = _positiveAngle(arc_angle)
                arc_end = arc_start + arc_span
                if arc_end < 0:
                    if angle < arc_start or angle > 360 + arc_end:
                        return i
                else:
                    if arc_end < arc_start:
                        arc_start, arc_end = arc_end, arc_start
                    if arc_start <= angle <= arc_end:
                        return i
        return -1

    def _arcs(self) -> Iterable[tuple[float, float]]:
        space = self.arcSpacing()
        scale = self._arcScale()
        values = self.normalizedValues()
        angle, sweep = self.effectiveStartAndSweepAngles()
        for i, value in enumerate(values):
            span = sweep * value * scale
            yield angle, span
            angle += span + space

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        rect = self.chartRect()

        painter.setBrush(Qt.NoBrush)

        pen = QtGui.QPen(Qt.black, self.penWidth())
        pen.setCapStyle(self.penCapStyle())

        if self.isTrackVisible():
            angle, sweep = self.effectiveStartAndSweepAngles()
            pen.setColor(self.effectiveTrackColor())
            painter.setPen(pen)
            painter.drawArc(rect, int(angle * 16), int(sweep * 16))

        for i, (angle, span) in enumerate(self._arcs()):
            color = self.rowColor(i)
            pen.setColor(color)
            pen.setWidthF(self.penWidthForRow(i))
            painter.setPen(pen)
            painter.drawArc(rect, int(angle * 16), int(span * 16))


@graphictype("concentric_donut")
class ConcentricDonutChartGraphic(CircularChartGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._spacing = 0.025

    def spacing(self) -> float:
        return self._spacing

    @settable()
    def setSpacing(self, spacing: float) -> None:
        self._spacing = spacing
        self.rebuild()

    def rowAtPos(self, pos: QtCore.QPointF) -> int:
        row = -1
        count = self.rowCount()
        rect = self.chartRect()
        inset = (self.penWidth() + self.spacing()) / rect.width()
        angle, dist = self.angleAndDistance(pos.x(), pos.y())
        # TODO: do this better
        outer_dist = 0.5 + inset
        inner_dist = outer_dist - inset * count
        if inner_dist <= dist <= outer_dist:
            ring = ((dist - inner_dist) / inset)
            row = (count - 1) - int(ring)
        return row

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        rect = self.chartRect()
        scale = self._arcScale()
        values = self.normalizedValues()
        start_angle = self.startAngle()
        start_ticks = int(start_angle * 16)
        sweep = self.sweep()
        inset = self.penWidth() + self.spacing()
        show_track = self.isTrackVisible()
        track_color = self.effectiveTrackColor()

        pen = QtGui.QPen(Qt.black, 1.0)
        painter.setBrush(Qt.NoBrush)
        for i, value in enumerate(values):
            pen.setWidthF(self.penWidthForRow(i))
            if show_track:
                pen.setColor(track_color)
                painter.setPen(pen)
                painter.drawArc(rect, start_ticks, int(sweep * 16))

            span = sweep * value * scale
            color = self.rowColor(i)
            pen.setColor(color)
            painter.setPen(pen)
            span_ticks = int(span * 16)
            painter.drawArc(rect, start_ticks, span_ticks)
            rect.adjust(inset, inset, -inset, -inset)


@graphictype("segmented_donut")
class SegmentedDonutChartGraphic(CircularChartGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._normalizer = models.FractionOfSum()
        self._segments = 5
        self._arcspacing = 5.0
        self._pie = False
        self._capstyle = Qt.FlatCap

    def isPie(self) -> bool:
        return self._pie

    @settable()
    def setPie(self, pie: bool) -> None:
        self._pie = pie
        self.rebuild()

    def arcSpacing(self) -> float:
        return self._arcspacing

    @settable("spacing")
    def setArcSpacing(self, degrees: float):
        self._arcspacing = degrees
        self.rebuild()

    def segmentCount(self) -> int:
        return self._segments

    @settable()
    def setSegmentCount(self, segments: int) -> None:
        self._segments = segments
        self.rebuild()

    def _partCount(self) -> int:
        return self.segmentCount()


@graphictype("stacked_bar")
class StackedBarChartGraphic(ChartGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._orientation = Qt.Horizontal
        self._spacing = 1.0
        self._rounded = False

    def orientation(self) -> Qt.Orientation:
        return self._orientation

    @settable(argtype=Qt.Orientation)
    def setOrientation(self, orient: Qt.Orientation) -> None:
        self._orientation = orient
        self.update()

    def spacing(self) -> float:
        return self._spacing

    @settable()
    def setSpacing(self, space: float) -> None:
        self._spacing = space
        self.update()

    def isRounded(self) -> bool:
        return self._rounded

    @settable(argtype=bool)
    def setRounded(self, rounded: bool) -> None:
        self._rounded = rounded
        self.update()

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        rect = self.chartRect()
        values = self.normalizedValues()
        space = self.spacing()
        horiz = self.orientation() == Qt.Horizontal
        rounded = self.isRounded()

        if rounded:
            radius = min(rect.width(), rect.height()) / 2.0
            clip_path = QtGui.QPainterPath()
            clip_path.addRoundedRect(rect, radius, radius)
            painter.setClipPath(clip_path)

        if horiz:
            length = rect.width()
            breadth = rect.height()
        else:
            length = rect.height()
            breadth = rect.width()

        if self.isTrackVisible():
            track_color = self.effectiveTrackColor()
            painter.fillRect(rect, track_color)

        wout_space = length - space * (len(values) - 1)
        pos = 0.0
        for i, value in enumerate(values):
            color = self.rowColor(i)
            bar_len = wout_space * value
            if horiz:
                r = QtCore.QRectF(rect.x() + pos, rect.y(),
                                  bar_len, breadth)
            else:
                r = QtCore.QRectF(rect.x(), rect.y() + pos,
                                  breadth, bar_len)
            painter.fillRect(r, color)
            pos += bar_len + space

        if rounded:
            painter.setClipping(False)


@graphictype("segmented_bar")
class SegmentedBarChartGraphic(ChartGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._orientation = Qt.Horizontal
        self._reversed = False
        self._segcount = 5
        self._spacing = 1
        self._analog = True
        self._multicolor = False

    def segmentCount(self) -> int:
        return self._segcount

    @settable()
    def setSegmentCount(self, segments: int) -> None:
        self._segcount = segments
        self.update()

    def isMulticolor(self) -> bool:
        return self._multicolor

    @settable()
    def setMulticolor(self, multi: bool):
        self._multicolor = multi

    def orientation(self) -> Qt.Orientation:
        return self._orientation

    @settable(argtype=Qt.Orientation)
    def setOrientation(self, orient: Qt.Orientation) -> None:
        self._orientation = orient
        self.update()

    def isReversed(self) -> bool:
        return self._reversed

    @settable()
    def setReversed(self, reverse: bool) -> None:
        self._reversed = reverse
        self.update()

    def isAnalog(self) -> bool:
        return self._analog

    @settable()
    def setAnalog(self, analog: bool) -> None:
        self._analog = analog
        self.update()

    def rebuild(self) -> None:
        self.update()

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        painter.save()
        rect = self.chartRect()
        values = self.values()
        orient = self.orientation()
        revd = self.isReversed()
        analog = self.isAnalog()
        multicolor = self.isMulticolor()

        if orient == Qt.Vertical:
            length = rect.height()
            breadth = rect.width()
            edgestart = rect.left()
            origin = rect.top() if revd else rect.bottom()
            deltasign = 1 if revd else -1
        else:
            length = rect.width()
            breadth = rect.height()
            edgestart = rect.top()
            origin = rect.right() if revd else rect.left()
            deltasign = -1 if revd else 1

        barsize = breadth / len(values)
        segcount = self.segmentCount()
        segsize = length / segcount
        barlength = segsize * segcount
        baredge = edgestart
        show_track = self.isTrackVisible()
        track_color = self.effectiveTrackColor()

        for i, value in enumerate(values):
            floorsegs = int(math.floor(value))
            ceilsegs = int(math.ceil(value))
            segedge = origin
            color = self.rowColor(i if multicolor else 0)
            for j in range(segcount):
                if not show_track and j >= ceilsegs:
                    break

                pt = QtCore.QPointF(baredge, segedge)
                sz = QtCore.QSizeF(barsize - 1, (segsize - 1) * deltasign)
                if orient == Qt.Horizontal:
                    pt = pt.transposed()  # QPoint does not have transpose()
                    sz.transpose()
                segrect = QtCore.QRectF(pt, sz)

                if show_track:
                    painter.fillRect(segrect, track_color)

                if j < ceilsegs:
                    alpha = 1.0
                    if analog and j == floorsegs and value < ceilsegs:
                        alpha = value - floorsegs

                    if alpha < 1.0:
                        opacity = painter.opacity()
                        painter.setOpacity(alpha)
                    painter.fillRect(segrect, color)
                    if alpha < 1.0:
                        painter.setOpacity(opacity)
                segedge += segsize * deltasign
            baredge += barsize
        painter.restore()


class Point2DChartGraphic(ChartGraphic):
    def _points(self) -> Sequence[QtCore.QPointF]:
        rect = self.chartRect()
        values = self.normalizedValues()
        dx = rect.width() / (len(values) - 1) if len(values) > 1 else 0
        points: list[QtCore.QPointF] = []
        for i, value in enumerate(values):
            x = rect.x() + i * dx
            y = rect.bottom() - rect.height() * value
            points.append(QtCore.QPointF(x, y))
        return points


@graphictype("line_chart")
class LineChartGraphic(Point2DChartGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._normalizer = models.FractionOfMax()
        self._penwidth = 1.0
        self._dotradius = 2.0
        # self._line = QtWidgets.QGraphicsPathItem(self)
        # self._dots: list[ArcItem] = []

    def dotRadius(self) -> float:
        return self._dotradius

    @settable()
    def setDotRadius(self, radius: float) -> None:
        self._dotradius = radius
        self.update()

    def penWidth(self) -> float:
        return self._penwidth

    @settable()
    def setPenWidth(self, width: float) -> None:
        self._penwidth = width
        self.update()

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        points = self._points()
        if not points:
            return

        color = self.rowColor(0)
        dot_radius = self.dotRadius()

        if dot_radius:
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            for i, p in enumerate(points):
                dr = QtCore.QRectF(p.x() - dot_radius, p.y() - dot_radius,
                                   dot_radius * 2, dot_radius * 2)
                painter.drawEllipse(dr)

        painter.setPen(color)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolyline(QtGui.QPolygonF(points))


@graphictype("area_chart")
class AreaChartGraphic(Point2DChartGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._normalizer = models.FractionOfMax()
        self._area = QtWidgets.QGraphicsPathItem(self)
        self._area.setPen(Qt.NoPen)

    def _points(self) -> Sequence[QtCore.QPointF]:
        r = self.chartRect()
        points = list(super()._points())
        points.insert(0, QtCore.QPointF(r.x(), r.bottom()))
        points.append(QtCore.QPointF(r.right(), r.bottom()))
        return points

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        points = self._points()
        if not points:
            return

        color = self.rowColor(0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        if len(points) == 1:
            rect = self.chartRect()
            p = points[0]
            r = QtCore.QRectF(p.x(), p.y(), rect.width(), rect.height() - p.y())
            painter.drawRect(r)
        else:
            painter.drawPolygon(QtGui.QPolygonF(points))


@graphictype("bar_chart")
class BarChartGraphic(ChartGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._normalizer = models.FractionOfMax()
        self._orientation = Qt.Vertical
        self._centered = False
        self._spacing = 1.0
        self._rounded = False
        # self._bars: list[QtWidgets.QGraphicsRectItem] = []

    def orientation(self) -> Qt.Orientation:
        return self._orientation

    @settable(argtype=Qt.Orientation)
    def setOrientation(self, orient: Qt.Orientation):
        self._orientation = orient
        self.update()

    def isCentered(self):
        return self._centered

    @settable()
    def setCentered(self, centered):
        self._centered = centered
        self.update()

    def spacing(self):
        return self._spacing

    @settable()
    def setSpacing(self, space):
        self._spacing = space
        self.update()

    def isRounded(self) -> bool:
        return self._rounded

    @settable()
    def setRounded(self, rounded: bool):
        self._rounded = rounded
        self.update()

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        values = self.normalizedValues()
        if not values:
            return

        rect = self.chartRect()
        space = self.spacing()
        centered = self.isCentered()
        is_vert = self.orientation() == Qt.Vertical
        full_length = rect.height() if is_vert else rect.width()
        if centered:
            full_length /= 2.0
        full_breadth = rect.width() if is_vert else rect.height()
        full_breadth -= space * len(values)
        bar_breadth = full_breadth / len(values)
        radius = bar_breadth / 2.0 if self.isRounded() else 0
        show_track = self.isTrackVisible()
        track_color = self.effectiveTrackColor()
        painter.setPen(Qt.NoPen)

        if is_vert:
            zero = rect.center().y() if centered else rect.bottom()
            start = rect.x()
        else:
            zero = rect.center().x() if centered else rect.x()
            start = rect.y()

        if show_track:
            painter.setBrush(track_color)
            x = start
            for i in range(len(values)):
                if is_vert:
                    r = QtCore.QRectF(x, zero, bar_breadth, -full_length)
                else:
                    r = QtCore.QRectF(zero, x, full_length, bar_breadth)
                if radius:
                    painter.drawRoundedRect(r, radius, radius)
                else:
                    painter.drawRect(r)
                x += bar_breadth + space

        for i, value in enumerate(values):
            color = self.rowColor(i)
            bar_length = full_length * value
            if is_vert:
                r = QtCore.QRectF(start, zero, bar_breadth, -bar_length)
            else:
                r = QtCore.QRectF(zero, start, bar_length, bar_breadth)

            painter.setBrush(color)
            if radius:
                painter.drawRoundedRect(r, radius, radius)
            else:
                painter.drawRect(r)

            start += bar_breadth + space


from __future__ import annotations
import enum
import math
from typing import Callable, Optional, Sequence, Tuple, TypeVar, Union

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from . import models, styling, themes
from .config import settable
from .graphics import graphictype, Graphic
from .themes import blend


DEFAULT_TRACK_ROLE = QtGui.QPalette.WindowText
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


def rebuildParts(parent: QtWidgets.QGraphicsItem, count: int, parts: list[T],
                 maker_fn: Callable[[QtWidgets.QGraphicsItem], T]) -> None:
    while len(parts) > count:
        part = parts.pop()
        part.hide()
        part.setParentItem(None)
        part.deleteLater()
    while len(parts) < count:
        part = maker_fn(parent)
        parts.append(part)


class ChartGraphic(Graphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._model: Optional[QtCore.QAbstractTableModel] = None
        self._namecol = 0
        self._namerole = Qt.DisplayRole
        self._valuecol = 1
        self._valuerole = Qt.DisplayRole

        self._showtrack = False
        self._trackcolor: Optional[QtGui.QColor] = None
        self._trackrole = DEFAULT_TRACK_ROLE
        self._trackalpha = DEFAULT_TRACK_ALPHA

        self._normalizer = models.SmartNormalization()
        self._hilite_row = -1
        self._square = False

    def normalization(self) -> models.Normalization:
        return self._normalizer

    def setNormalization(self, norm: models.Normalization):
        self._normalizer = norm
        self._recalc()

    def total(self) -> Optional[float]:
        return self.normalization().total()

    @settable()
    def setTotal(self, total: Optional[float]):
        self.setNormalization(models.FractionOfNumber(total))
        self.rebuild()

    @settable()
    def setNameColumn(self, column: int, role=Qt.DisplayRole) -> None:
        self._namecol = column
        self._namerole = role
        self.rebuild()

    @settable()
    def setValueColumn(self, column: int, role=Qt.DisplayRole) -> None:
        self._valuecol = column
        self._valuerole = role
        self.rebuild()

    def isSquare(self) -> bool:
        return self._square

    @settable()
    def setSquare(self, square: bool) -> None:
        self._square = square
        self.rebuild()

    def isTrackVisible(self) -> bool:
        return self._showtrack

    @settable()
    def setTrackVisible(self, visible: bool) -> None:
        self._showtrack = visible
        self.rebuild()

    def trackColor(self) -> QtGui.QColor:
        return self._trackcolor

    @settable(argtype=QtGui.QColor)
    def setTrackColor(self, color: QtGui.QColor):
        self._trackcolor = color

    def trackRole(self) -> QtGui.QPalette.ColorRole:
        return self._trackrole

    @settable(argtype=QtGui.QPalette.ColorRole)
    def setTrackRole(self, role: QtGui.QPalette.ColorRole):
        self._trackrole = role

    def trackAlpha(self) -> float:
        return self._trackalpha

    @settable()
    def setTrackAlpha(self, alpha: float):
        self._trackalpha = alpha

    def effectiveTrackColor(self) -> Optional[QtGui.QColor]:
        tcolor = self.trackColor()
        trole = self.trackRole()
        alpha = self.trackAlpha()
        if tcolor is None and trole is not None:
            tcolor = self.palette().color(trole)
            if alpha is not None:
                tcolor.setAlphaF(alpha)
        return tcolor

    def model(self) -> QtCore.QAbstractTableModel:
        return self._model

    def setModel(self, model: QtCore.QAbstractTableModel):
        if self._model:
            self._model.modelReset.disconnect(self._datachanged)
            self._model.dataChanged.disconnect(self._datachanged)
            self._model.layoutChanged.disconnect(self._datachanged)
        self._model = model
        self._model.modelReset.connect(self._datachanged)
        self._model.dataChanged.connect(self._datachanged)
        self._model.layoutChanged.connect(self._datachanged)
        self.update()

    def highlightedRow(self) -> int:
        return self._hilite_row

    def setHighlightedRow(self, row: int):
        self._hilite_row = row
        self.rebuild()

    def rowCount(self) -> int:
        model = self.model()
        if model:
            return model.rowCount()
        return 0

    def rowColor(self, row: int) -> QtGui.QColor:
        model = self.model()
        if not isinstance(row, int):
            raise ValueError(f"Row index is not an int: {row}")
        if row >= model.rowCount():
            raise IndexError(row)
        index = model.index(row, self._namecol)
        color = index.data(Qt.DecorationRole)
        if isinstance(color, int):
            # A ColorRole returned by .data() loses its"object-ness" and turns
            # into an int... turn it back into a ColorRole object
            crole = QtGui.QPalette.ColorRole(color)
            color = self.palette().color(crole)

        if not isinstance(color, QtGui.QColor):
            color = Qt.black
        return color

    def setRowColor(self, color: QtGui.QColor, row=0) -> None:
        model = self.model()
        index = model.index(row, self._valuecol)
        model.setData(index, color, Qt.DecorationRole)

    def setRowColorRole(self, role: QtGui.QPalette.ColorRole, row=0) -> None:
        model = self.model()
        index = model.index(row, self._valuecol)
        model.setData(index, role, Qt.DecorationRole)

    def valueAt(self, row: int) -> float:
        model = self.model()
        index = model.index(row, self._valuecol)
        value = index.data(Qt.EditRole)
        return float(value)

    @settable()
    def setValue(self, value: float, row=0) -> None:
        model = self.model()
        index = model.index(row, self._valuecol)
        model.setData(index, value, self._valuerole)
        self.rebuild()

    def values(self) -> Sequence[float]:
        return [self.valueAt(row) for row in range(self.rowCount())]

    @settable()
    def setValues(self, values: Sequence[float], start_row=0) -> None:
        for i, value in enumerate(values):
            self.setValue(value, start_row + i)
        self.rebuild()

    def normalizedValues(self) -> Sequence[float]:
        norm = self.noralization()
        return norm.normalized(self.values())

    def chartRect(self) -> QtCore.QRectF:
        rect = self.rect()
        if self.isSquare():
            ctr = rect.center()
            w = min(rect.width(), rect.height())
            return QtCore.QRectF(ctr.x() - w/2, ctr.y() - w/2, w, w)
        else:
            return rect

    def rebuild(self) -> None:
        self.update()


class CircularChartGraphic(ChartGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._clockwise = True
        self._startangle = 90.0
        self._sweep = 360.0
        self._gapangle = 0.0
        self._penwidth = 3.0
        self._textsize = 0.5
        self._capstyle = Qt.RoundCap
        self._square = True

        self._parts: list[QtWidgets.QGraphicsEllipseItem] = []

        self._track = QtWidgets.QGraphicsEllipseItem(self)

    def isClockwise(self) -> bool:
        return self._clockwise

    @settable()
    def setClockwise(self, clockwise: bool):
        self._clockwise = clockwise
        self.rebuild()

    def penWidth(self) -> float:
        return self._penwidth

    def setPenWidth(self, width: float) -> None:
        self._penwidth = width
        self.rebuild()

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
        self._rebuildArcs()

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

    def rowAtPos(self, pos: QtCore.QPointF) -> int:
        raise NotImplementedError

    def setAngles(self, start_degrees: float, sweep: float, clockwise=None):
        if clockwise is not None:
            self._clockwise = clockwise
        self._startangle = start_degrees
        self._sweep = sweep
        self.rebuild()

    def gapAngle(self) -> float:
        return self._gapangle

    @settable()
    def setGapAngle(self, degrees: float):
        self._gapangle = degrees
        self.rebuild()

    def startAngle(self) -> float:
        return self._startangle

    @settable()
    def setStartAngle(self, degrees: float):
        self._startangle = degrees
        self.rebuild()

    def sweep(self) -> float:
        return self._sweep

    @settable()
    def setSweep(self, degrees: float):
        self._sweep = degrees
        self.rebuild()

    def endAngle(self) -> float:
        start = self.startAngle()
        return start + self._sweep * self._arcScale()

    def setAngleAndGap(self, degrees: float, gap_degrees=0.0,
                       clockwise: bool = None):
        if clockwise is not None:
            self._clockwise = clockwise
        self._startangle = degrees
        self._gapangle = gap_degrees
        self.rebuild()

    def _partCount(self) -> int:
        return self.rowCount()

    def _rebuildTrack(self) -> None:
        track = self._track
        track.setRect(self.chartRect())
        track.setVisible(self.isTrackVisible())
        color = self.effectiveTrackColor()
        track.setPen(QtGui.QPen(color, self.penWidth()))

    def _rebuildArcs(self) -> None:
        rebuildParts(self, self._partCount(), self._parts,
                     QtWidgets.QGraphicsEllipseItem)
        penwidth = self.penWidth()
        capstyle = self.penCapStyle()
        for i, part in enumerate(self._parts):
            color = self.rowColor(i)
            pen = QtGui.QPen(color, penwidth)
            pen.setCapStyle(capstyle)
            part.setPen(pen)
            part.setBrush(Qt.NoBrush)


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
        self.rebuild()

    def arcSpacing(self) -> float:
        return self._arcspacing

    @settable("spacing")
    def setArcSpacing(self, degrees: float) -> None:
        self._arcspacing = degrees
        self.rebuild()

    def effectiveStartAndSweepAngles(self) -> tuple[float, float]:
        space = self.arcSpacing()
        scale = self._arcScale()
        start = self.startAngle()
        sweep = self.sweep()
        gap_degrees = self.gapAngle()
        if gap_degrees:
            start = start + gap_degrees / 2.0 * scale
            sweep -= gap_degrees
        sweep -= space * self.count()
        return start, sweep

    def rowAtPos(self, pos: QtCore.QPointF) -> int:
        ix = -1
        angle, dist = self.angleAndDistance(pos.x(), pos.y())
        angle = _positiveAngle(angle)
        if (0.5 - self.penWidth() - 0.3) <= dist <= 0.8:
            for i, (arc_angle, arc_span) in enumerate(self._arcs):
                arc_start = _positiveAngle(arc_angle)
                arc_end = arc_start + arc_span
                if arc_end < 0:
                    found = angle < arc_start or angle > 360 + arc_end
                else:
                    if arc_end < arc_start:
                        arc_start, arc_end = arc_end, arc_start
                    found = arc_start <= angle <= arc_end
                if found:
                    ix = i
                    break
        return ix

    def rebuild(self) -> None:
        self._rebuildTrack()
        self._rebuildArcs()
        parts = self._parts
        space = self.arcSpacing()
        scale = self._arcScale()
        normalized = self.normalizedValues()
        angle, sweep = self.effectiveStartAndSweepAngles()
        rect = self.chartRect()
        penwidth = self.penWidth()
        for i, part in enumerate(parts):
            value = normalized[i]
            span = sweep * value * scale
            part.setStartAngle(int(angle * 16))
            part.setSpanAngle(int(span * 16))

            color = self.rowColor(i)
            part.setPen(QtGui.QPen(color, penwidth))
            part.setRect(rect)
            angle += (span + space) * scale


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

    def rebuild(self) -> None:
        self._rebuildTrack()
        self._rebuildArcs()
        parts = self._parts
        scale = self._arcScale()
        normalized = self.normalizedValues()
        start_angle = self.startAngle()
        sweep = self.sweep()
        rect = self.chartRect()
        inset = self.penWidth() + self.spacing()
        for i, part in enumerate(parts):
            value = normalized[i]
            span = sweep * value * scale
            part.setRect(rect)
            part.setStartAngle(int(start_angle * 16))
            part.setSpanAngle(int(span * 16))

            rect.adjust(inset, inset, -inset, -inset)


@graphictype("segmented_donut_grpahic")
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

    def rebuild(self) -> None:
        self._rebuildArcs()
        parts = self._parts
        penwidth = self.penWidth()
        count = self.segmentCount()
        angle = self.startAngle()
        scale = self._arcScale()
        space = self.arcSpacing()
        totaldeg = self.sweep() - (space * (count - 1))
        segment_span = totaldeg / count

        track_color = self.effectiveTrackColor()
        value = self.valueAt(0)
        lit_color = self.rowColor(0)
        fully_lit = math.floor(value)
        for i in range(count):
            part = parts[i]
            if i <= fully_lit:
                color = lit_color
            elif i < value:
                color = blend(track_color, lit_color, value - i)
            else:
                color = track_color
            part.setPen(QtGui.QPen(color, penwidth))
            part.setStartAngle(int(angle * 16))
            part.setSpanAngle(int(segment_span * 16))
            angle += (segment_span + space) * scale


@graphictype("segmented_bar_chart_graphic")
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
        self.rebuild()

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
        self.rebuild()

    def isReversed(self) -> bool:
        return self._reversed

    @settable()
    def setReversed(self, reverse: bool) -> None:
        self._reversed = reverse
        self.rebuild()

    def isAnalog(self) -> bool:
        return self._analog

    @settable()
    def setAnalog(self, analog: bool) -> None:
        self._analog = analog
        self.rebuild()

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
            y = rect.y() - rect.height() * value
            points.append(QtCore.QPointF(x, y))
        return points


@graphictype("line_chart_graphic")
class LineChartGraphic(Point2DChartGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._normalizer = models.FractionOfMax()
        self._penwidth = 1.0
        self._dotradius = 2.0
        self._line = QtWidgets.QGraphicsPathItem(self)
        self._dots: list[QtWidgets.QGraphicsEllipseItem] = []

    def dotRadius(self) -> float:
        return self._dotradius

    @settable()
    def setDotRadius(self, radius: float) -> None:
        self._dotradius = radius
        self.rebuild()

    def penWidth(self) -> float:
        return self._penwidth

    @settable()
    def setPenWidth(self, width: float) -> None:
        self._penwidth = width
        self.rebuild()

    def rebuild(self) -> None:
        dots = self._dots
        rebuildParts(self, self.rowCount(), dots, QtWidgets.QGraphicsRectItem)
        points = self._points()
        if not points:
            return

        color = self.rowColor(0)
        path = QtGui.QPainterPath()
        dot_rad = self.dotRadius()
        for i, p in enumerate(points):
            dot = dots[i]
            if dot_rad:
                dot.setRect(p.x() - dot_rad, p.y() - dot_rad,
                            dot_rad * 2, dot_rad * 2)
                dot.setBrush(color)
                dot.setPen(Qt.NoPen)
                dot.show()
            else:
                dot.hide()

            if i:
                path.lineTo(p)
            else:
                path.moveTo(p)

        line = self._line
        line.setPath(path)
        line.setPen(QtGui.QPen(color, self.penWidth()))


@graphictype("area_chart_graphic")
class AreaChartGraphic(Point2DChartGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._normalizer = models.FractionOfMax()
        self._area = QtWidgets.QGraphicsPathItem(self)
        self._area.setPen(Qt.NoPen)

    def rebuild(self) -> None:
        points = self._points()
        if not points:
            return
        path = QtGui.QPainterPath()
        if len(points) == 1:
            p = points[0]
            rect = self.chartRect()
            path.addRect(p.x(), p.y(), rect.width(), rect.height() - p.y())
        else:
            path.addPolygon(QtGui.QPolygonF(points))
        self._area.setBrush(self.rowColor(0))
        self._area.setPath(path)


@graphictype("bar_chart_graphic")
class BarChartGraphic(ChartGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._normalizer = models.FractionOfMax()
        self._orientation = Qt.Vertical
        self._centered = False
        self._spacing = 1.0
        self._rounded = False
        self._bars: list[QtWidgets.QGraphicsRectItem] = []

    def orientation(self) -> Qt.Orientation:
        return self._orientation

    @settable(argtype=Qt.Orientation)
    def setOrientation(self, orient: Qt.Orientation):
        self._orientation = orient
        self.rebuild()

    def isCentered(self):
        return self._centered

    @settable()
    def setCentered(self, centered):
        self._centered = centered
        self.rebuild()

    def spacing(self):
        return self._spacing

    @settable()
    def setSpacing(self, space):
        self._spacing = space
        self.rebuild()

    def isRounded(self) -> bool:
        return self._rounded

    @settable()
    def setRounded(self, rounded: bool):
        self._rounded = rounded
        self.rebuild()

    def rebuild(self) -> None:
        rebuildParts(self, self.rowCount(), self._bars,
                     QtWidgets.QGraphicsRectItem)
        rect = self.chartRect()
        bars = self._bars
        space = self.spacing()
        centered = self.isCentered()
        vertical = self.orientation() == Qt.Vertical
        full_length = rect.height() if vertical else rect.width()
        if centered:
            full_length /= 2.0
        full_breadth = rect.width() if vertical else rect.height()
        full_breadth -= space * self.count()
        values = self.normalizedValues()
        bar_breadth = full_breadth / len(values)
        radius = bar_breadth / 2.0 if self.rounded() else 0

        if vertical:
            zero = rect.center().y() if centered else rect.bottom()
            start = rect.x()
        else:
            zero = rect.center().x() if centered else rect.x()
            start = rect.y()

        for i, value in enumerate(values):
            bar = bars[i]
            bar_length = full_length * value

            if vertical:
                r = QtCore.QRectF(start, zero, bar_breadth, -bar_length)
            else:
                r = QtCore.QRectF(zero, start, bar_length, bar_breadth)
            bar.setRect(r)
            bar.setBrush(self.rowColor(i))
            start += bar_breadth + space

from __future__ import annotations

import enum
import math
from typing import Any, Callable, Iterable, Optional, Sequence, TypeVar, Union

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .. import converters
from ..config import settable
from ..util import validSizeHint


DEFAULT_GRID_SPACING = 4.0
DEFAULT_GRID_COL_WIDTH = 90.0
DEFAULT_GRID_ROW_HEIGHT = 50.0
GOLDEN_RATIO = 1.61803399
PACKING_TOLERANCE = 0.1

DEFAULT_MIN_COL_WIDTH = 200.0
DEFAULT_ROW_HEIGHT = 24.0
DEFAULT_ITEM_SPACING = 10.0


class Justify(enum.Enum):
    start = enum.auto()
    end = enum.auto()
    center = enum.auto()
    space_between = enum.auto()
    space_around = enum.auto()
    space_evenly = enum.auto()
    stretch = enum.auto()
    even = enum.auto()


class Align(enum.Enum):
    start = enum.auto()
    end = enum.auto()
    center = enum.auto()
    stretch = enum.auto()


alignment_names: dict[str, Align] = {
    "start": Align.start,
    "end": Align.end,
    "center": Align.center,
    "stretch": Align.stretch,
}
justification_names: dict[str, Justify] = {
    "start" : Justify.start,
    "end": Justify.end,
    "center": Justify.center,
    "space_between": Justify.space_between,
    "space_around": Justify.space_around,
    "space_evenly": Justify.space_evenly,
    "stretch": Justify.stretch,
    "even": Justify.even,
}

T = TypeVar("T")
ItemRectPair = tuple[QtWidgets.QGraphicsWidget, QtCore.QRectF]


def chunks(items: Sequence[T], n: int) -> Iterable[Sequence[T]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


def horizontal_keyfn(r: QtCore.QRectF) -> tuple[float, float]:
    return r.y(), r.x()


def vertical_keyfn(r: QtCore.QRectF) -> tuple[float, float]:
    return r.x(), r.y()


def offsetAndSpacing(justificaiton: Justify, available: float, count: int
                     ) -> tuple[float, float]:
    if justificaiton == Justify.start:
        return 0, 0
    elif justificaiton == Justify.end:
        return available, 0
    elif justificaiton == Justify.center:
        return available / 2, 0
    elif justificaiton == Justify.space_between and count > 1:
        return 0, available / (count - 1)
    elif justificaiton == Justify.space_around:
        m = available / (count * 2)
        return m, m * 2
    elif justificaiton == Justify.space_evenly:
        return 0, available / (count + 1)


def stretchFactors(avail: float, total_width: float, widths: Sequence[float],
                   stretches: Sequence[int]) -> Sequence[float]:
    if not widths:
        return widths
    total_stretch = sum(stretches)
    if total_width > avail:
        shrink = avail / total_width
        factors = [shrink] * len(widths)
    elif total_width < avail:
        extra = avail - total_width
        factors = []
        for w, s in zip(widths, stretches):
            if w:
                s_frac = s / total_stretch
                stretched_width = w + extra * s_frac
                factor = stretched_width / w
            else:
                factor = 1.0
            factors.append(factor)
    else:
        factors = [1.0] * len(widths)
    return factors


def stretchRect(orient: Qt.Orientation, item: QtWidgets.QGraphicsWidget,
                rect: QtCore.QRectF, *, value: float = None, scale=1.0) -> None:
    w = rect.width()
    h = rect.height()
    if orient == Qt.Horizontal:
        w = value if value is not None else w * scale
        if item.sizePolicy().hasHeightForWidth():
            hint = validSizeHint(item, Qt.PreferredSize, QtCore.QSizeF(w, -1))
            h = hint.height()
    else:
        h = value if value is not None else h * scale
        if item.sizePolicy().hasWidthForHeight():
            hint = validSizeHint(item, Qt.PreferredSize, QtCore.QSizeF(-1, h))
            w = hint.width()
    rect.setSize(QtCore.QSizeF(w, h))


def justifyAndAlign(orient: Qt.Orientation, item_rects: Sequence[ItemRectPair],
                    pos: QtCore.QPointF, avail: float, across: float,
                    justify: Justify, align: Align, spacing: float,
                    stretches: Sequence[int]) -> float:
    if not item_rects:
        return 0.0
    if orient not in (Qt.Horizontal, Qt.Vertical):
        raise ValueError(f"{orient} not an orientation")

    horiz = orient == Qt.Horizontal
    # print("--")
    # print("items=", item_rects)
    # print("horiz=", horiz, "justify=", justify, "align=", align)

    if horiz:
        lengths = [r.width() for _, r in item_rects]
    else:
        lengths = [r.height() for _, r in item_rects]
    total_length = sum(lengths) + spacing * (len(item_rects) - 1)

    scale_factors = [1.0] * len(item_rects)
    extra = avail - total_length
    offset = 0.0
    if extra >= 1.0 and justify != Justify.even:
        if justify == Justify.stretch:
            scale_factors = stretchFactors(avail, total_length, lengths, stretches)
        elif justify == Justify.center:
            offset = extra / 2.0
        elif justify == Justify.end:
            offset = extra
        elif justify == Justify.space_between and len(item_rects) > 1:
            spacing += extra / (len(item_rects) - 1)
    # print("offset=", offset)

    if justify == Justify.even:
        eq_breadth = avail / len(item_rects)
        for item, rect in item_rects:
            stretchRect(orient, item, rect, value=eq_breadth)
    elif justify == Justify.stretch:
        for i, (item, rect) in enumerate(item_rects):
            stretchRect(orient, item, rect, scale=scale_factors[i])

    # When called from FlowArrangement, across = -1, and the cross width is
    # calculated from the items in the row.
    if across < 0:
        across = max((r.height() if horiz else r.width())
                     for _, r in item_rects)
    # print("across=", across)

    for _, rect in item_rects:
        # print("-off=", offset)
        if horiz:
            rect.moveLeft(pos.x() + offset)
            advance = rect.width()
        else:
            rect.moveTop(pos.y() + offset)
            advance = rect.height()
        offset += advance + spacing
        # print(" *advance=", advance, "*off=", offset)
        # print(" rect=", rect)

        cross_offset = 0.0
        if horiz:
            item_across = rect.height()
        else:
            item_across = rect.width()
        extra_across = across - item_across
        if extra_across >= 1.0:
            if align == Align.center:
                cross_offset = extra_across / 2.0
            elif align == Align.end:
                cross_offset = extra_across
        if horiz:
            rect.moveTop(pos.y() + cross_offset)
            if extra_across >= 1.0 and align == Align.stretch:
                rect.setHeight(across)
        else:
            rect.moveLeft(pos.x() + cross_offset)
            if extra_across >= 1.0 and align == Align.stretch:
                rect.setWidth(across)
        # print(" *rect=", rect)
    return across


# def stretchRects(avail_rect: QtCore.QRectF,
#                  item_rects: Sequence[QtCore.QRectF],
#                  halign: Justify, valign: Justify,
#                  h_offset=0.0, v_offset=0.0):
#     avail_w = avail_rect.width()
#     avail_h = avail_rect.height()
#     hscale = vscale = 1.0
#     total_width = max(r.right() for r in item_rects)
#     total_height = max(r.bottom() for r in item_rects)
#     if total_width < avail_w and halign == Justify.stretch:
#         hscale = avail_rect.width() / total_width
#     if total_height < avail_h and valign == Justify.stretch:
#         vscale = avail_rect.height() / total_height
#
#     for rect in item_rects:
#         x = rect.x()
#         y = rect.y()
#         w = rect.width()
#         h = rect.height()
#         rect.setRect(x * hscale + h_offset, y * vscale + v_offset,
#                      w * hscale, h * vscale)


class Packer:
    # More-or-less straight translation of Packery's bin-packing algorithm to
    # Python/Qt.

    def __init__(self, width: float, height: float,
                 key_fn: Callable = horizontal_keyfn):
        self._width = width
        self._height = height
        self._key_fn = key_fn
        self._spaces: list[QtCore.QRectF] = [QtCore.QRectF(0, 0, width, height)]

    def pack(self, rect: QtCore.QRectF) -> bool:
        for space in self._spaces:
            if (
                rect.width() <= space.width() + PACKING_TOLERANCE and
                rect.height() <= space.height() + PACKING_TOLERANCE
            ):
                self.placeInSpace(rect, space)
                return True
        return False

    def packAt(self, rect: QtCore.QRectF, x: float, y: float) -> bool:
        for space in self._spaces:
            if (
                x >= space.x() - PACKING_TOLERANCE and
                y >= space.y() - PACKING_TOLERANCE and
                rect.width() <= space.width() + PACKING_TOLERANCE and
                rect.height() <= space.height() + PACKING_TOLERANCE
            ):
                rect.moveTo(x - space.x(), y - space.y())
                self.placeInSpace(rect, space)
                return True
        return False

    def linePack(self, rect: QtCore.QRectF, orientation: Qt.Orientation
                 ) -> bool:
        for space in self._spaces:
            if orientation == Qt.Vertical:
                # Fits in column?
                fits = (space.x() < rect.x() and
                        space.right() >= rect.right() and
                        space.height() >= rect.height() - 0.01)
            else:
                # Fits in row?
                fits = (space.y() <= rect.y() and
                        space.bottom() >= rect.bottom() and
                        space.width() >= rect.width() - 0.01)
            if fits:
                self.placeInSpace(rect, space)
                return True
        return False

    def placeInSpace(self, rect: QtCore.QRectF, space: QtCore.QRectF):
        rect.moveTo(space.x() + rect.x(), space.y() + rect.y())
        self.placed(rect)

    def placed(self, rect: QtCore.QRectF):
        revised_spaces: list[QtCore.QRect] = []
        for space in self._spaces:
            if (
                abs(rect.x() - space.x()) < 0.1 and
                abs(rect.y() - space.y()) < 0.1 and
                abs(rect.width() - space.width()) < 0.1 and
                abs(rect.height() - space.height()) < 0.1
            ):
                continue

            new_spaces = self.maximalFreeRects(space, rect)
            if new_spaces:
                revised_spaces.extend(new_spaces)
            else:
                revised_spaces.append(space)
        self._spaces = revised_spaces
        self.mergeAndSortSpaces()

    def mergeAndSortSpaces(self):
        self.mergeRects(self._spaces)
        self._spaces.sort(key=self._key_fn)

    def addSpace(self, space: QtCore.QRect):
        self._spaces.append(space)
        self.mergeAndSortSpaces()

    @staticmethod
    def maximalFreeRects(this: QtCore.QRect, rect: QtCore.QRect
                         ) -> Sequence[QtCore.QRect]:
        free_rects: list[QtCore.QRect] = []
        if not this.intersects(rect):
            return free_rects
        # Top
        if this.y() < rect.y():
            free_rects.append(QtCore.QRectF(
                this.x(), this.y(),
                this.width(), rect.y() - this.y()
            ))
        # Right
        if this.right() > rect.right():
            free_rects.append(QtCore.QRectF(
                rect.right(), this.y(),
                this.right() - rect.right(), this.height()
            ))
        # Bottom
        if this.bottom() > rect.bottom():
            free_rects.append(QtCore.QRectF(
                this.x(), rect.bottom(),
                this.width(), this.bottom() - rect.bottom()
            ))
        # Left
        if this.x() < rect.x():
            free_rects.append(QtCore.QRectF(
                this.x(), this.y(), rect.x() - this.x(), this.height()
            ))

        return free_rects

    @staticmethod
    def mergeRects(rects: list[QtCore.QRectF]):
        # Modifies the list in-place to remove overlapping rects
        i = 0
        while i < len(rects):
            rect = rects[i]
            j = 0
            removed = False
            while (i + j) < len(rects):
                other = rects[i + j]
                if rect == other:
                    j += 1
                elif other.contains(rect):
                    # Remove rect
                    del rects[i]
                    removed = True
                    break
                elif rect.contains(other):
                    del rects[i + j]
                else:
                    j += 1
            if not removed:
                i += 1


class Arrangement(QtCore.QObject):
    invalidated = QtCore.Signal()

    _auto_margins = True

    def __init__(self, parent: QtCore.QObject = None):
        super().__init__(parent)
        self._metadata: dict[int, Any] = {}
        self._margins = QtCore.QMarginsF(0, 0, 0, 0)
        self._spacing = QtCore.QSizeF(0, 0)

    def clear(self) -> None:
        self._metadata.clear()

    def invalidate(self) -> None:
        self.invalidated.emit()

    def setMetadata(self, obj: QtWidgets.QGraphicsWidget, data: Any) -> None:
        self._metadata[id(obj)] = data
        self.invalidate()

    def metadata(self, obj: QtWidgets.QGraphicsWidget, default=None) -> Any:
        return self._metadata.get(id(obj), default)

    def horizontalSpacing(self) -> float:
        return self._spacing.width()

    @settable("h_space")
    def setHorizontalSpacing(self, hspace: float):
        self._spacing.setWidth(hspace)
        self.invalidate()

    def verticalSpacing(self) -> float:
        return self._spacing.height()

    @settable("v_space")
    def setVerticalSpacing(self, vspace: float):
        self._spacing.setHeight(vspace)
        self.invalidate()

    def spacing(self) -> QtCore.QSizeF:
        return QtCore.QSizeF(self._spacing)

    @settable("spacing")
    def setSpacing(self, spacing: Union[float, QtCore.QSizeF]):
        if isinstance(spacing, (int, float)):
            spacing = QtCore.QSizeF(spacing, spacing)
        else:
            spacing = QtCore.QSizeF(spacing)
        self._spacing = spacing
        self.invalidate()

    def margins(self) -> QtCore.QMarginsF:
        return QtCore.QMarginsF(self._margins)

    @settable(argtype=QtCore.QMarginsF)
    def setMargins(self, left: Union[QtCore.QMarginsF, float], top=0.0,
                   right=0.0, bottom=0.0) -> None:
        self._margins = converters.marginsArgs(left, top, right, bottom)
        self.invalidate()

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF,
                 items: Sequence[QtWidgets.QWidget]) -> QtCore.QSizeF:
        if not items:
            return QtCore.QSizeF(0, 0)

        size = QtCore.QSizeF(-1, -1)
        ms = self._margins
        cw = constraint.width()
        ch = constraint.height()
        if cw >= 0:
            if self._auto_margins:
                cw -= ms.left() + ms.right()
            c = QtCore.QSizeF(cw, ch)
            bottom = 0.0
            avail = QtCore.QRectF(QtCore.QPointF(0, 0), c)
            for _, rect in self.rects(which, avail, items):
                bottom = max(bottom, rect.bottom())
            if self._auto_margins:
                bottom += ms.top() + ms.bottom()
            size = QtCore.QSizeF(constraint.width(), bottom)
        elif constraint.height() >= 0:
            if self._auto_margins:
                ch -= ms.top() + ms.bottom()
            c = QtCore.QSizeF(cw, ch)
            right = 0.0
            avail = QtCore.QRectF(QtCore.QPointF(0, 0), c)
            for _, rect in self.rects(which, avail, items):
                right = max(right, rect.right())
            if self._auto_margins:
                right += ms.left() + ms.right()
            size = QtCore.QSizeF(right, constraint.height())
        elif which == Qt.PreferredSize:
            size = self._implicitSizeHint(items)
        return size

    def _implicitSizeHint(self, items: Sequence[QtWidgets.QWidget]
                          ) -> QtCore.QSizeF:
        return QtCore.QSizeF(-1, -1)

    def layoutItems(self, geom: QtCore.QRectF,
                    items: Sequence[QtWidgets.QGraphicsWidget], animated=False
                    ) -> None:
        from tilefx.graphics import Graphic

        for item, item_rect in self.rects(Qt.PreferredSize, geom, items):
            if animated and isinstance(item, Graphic):
                item.animateGeometry(item_rect)
            else:
                item.setGeometry(item_rect)

    @staticmethod
    def _itemRects(which: Qt.SizeHint, constraint: QtCore.QSizeF,
                   items: Sequence[QtWidgets.QGraphicsWidget],
                   ) -> list[ItemRectPair]:
        pairs: list[ItemRectPair] = []

        for item in items:
            if not item.isVisible():
                continue
            size = item.effectiveSizeHint(which, constraint)
            pairs.append((item, QtCore.QRectF(QtCore.QPointF(), size)))
        return pairs

    def rects(self, which: Qt.SizeHint, geom: QtCore.QRectF,
              items: Sequence[QtWidgets.QGraphicsWidget]
              ) -> Iterable[ItemRectPair]:
        if self._auto_margins and geom.size().isValid():
            geom = geom.marginsRemoved(self._margins)
        return self._rects(which, geom, items)

    def _rects(self, which: Qt.SizeHint, geom: QtCore.QRectF,
               items: Sequence[QtWidgets.QGraphicsWidget]
               ) -> Iterable[ItemRectPair]:
        raise NotImplementedError


class OrientedArrangement(Arrangement):
    def __init__(self, orientation=Qt.Vertical, parent: QtCore.QObject = None):
        super().__init__(parent)
        if orientation not in (Qt.Horizontal, Qt.Vertical):
            raise ValueError(f"{orientation} not an orientation")
        self._orientation = orientation

    @staticmethod
    def _constraint(orient: Qt.Orientation, size: QtCore.QSizeF
                    ) -> QtCore.QSizeF:
        constraint = QtCore.QSizeF(-1, -1)
        if orient == Qt.Horizontal:
            constraint.setHeight(size.height())
        else:
            constraint.setWidth(size.width())
        return constraint

    def orientation(self) -> Qt.Orientation:
        return self._orientation

    @settable(argtype=Qt.Orientation)
    def setOrientation(self, orientation: Qt.Orientation):
        self._orientation = orientation
        self.invalidate()

    def _itemSpacing(self, orient: Qt.Orientation) -> float:
        if orient == Qt.Horizontal:
            return self.horizontalSpacing()
        else:
            return self.verticalSpacing()


class LinearArrangement(OrientedArrangement):
    def __init__(self, orientation=Qt.Vertical, parent: QtCore.QObject = None):
        super().__init__(orientation=orientation, parent=parent)
        self._justify = Justify.stretch
        self._align_items = Align.stretch
        self._even = False

    def stretchFactor(self, item: QtWidgets.QGraphicsWidget) -> int:
        return self.metadata(item, 1)

    def setStretchFactor(self, item: QtWidgets.QGraphicsWidget, factor: int):
        self.setMetadata(item, factor)

    def crossAlignment(self) -> Align:
        return self._align_items

    @settable("item_align")
    def setCrossAlignment(self, align: Union[str, Align]) -> None:
        if isinstance(align, str):
            align = alignment_names[align]
        self._align_items = align
        self.invalidate()

    def justification(self) -> Justify:
        return self._justify

    @settable("justify")
    def setJustification(self, justify: Union[str, Justify]) -> None:
        if isinstance(justify, str):
            justify = justification_names[justify]
        self._justify = justify
        self.invalidate()

    @staticmethod
    def staticRects(
            which: Qt.SizeHint, geom: QtCore.QRectF,
            items: Sequence[QtWidgets.QGraphicsWidget],
            orient: Qt.Orientation, item_spacing: float,
            item_align: Union[str, Align], line_just: Union[str, Justify],
            stretches: Sequence[int] = None,
            ) -> Iterable[ItemRectPair]:
        constraint = OrientedArrangement._constraint(orient, geom.size())
        item_rects = Arrangement._itemRects(which, constraint, items)
        if item_rects:
            avail = geom.width() if orient == Qt.Horizontal else geom.height()
            across = geom.height() if orient == Qt.Horizontal else geom.width()
            justifyAndAlign(orient, item_rects, geom.topLeft(), avail, across,
                            line_just, item_align, item_spacing, stretches)
        return item_rects

    def _rects(self, which: Qt.SizeHint, geom: QtCore.QRectF,
               items: Sequence[QtWidgets.QGraphicsWidget]
               ) -> Iterable[ItemRectPair]:
        orient = self.orientation()
        item_spacing = self._itemSpacing(orient)
        line_just = self.justification()
        item_align = self.crossAlignment()

        stretches = [self.stretchFactor(item) for item in items]
        return self.staticRects(
            which, geom, items, orient, item_spacing, item_align, line_just,
            stretches=stretches
        )

    def _implicitSizeHint(self, items: Sequence[QtWidgets.QWidget]
                          ) -> QtCore.QSizeF:
        sizes = [validSizeHint(it, Qt.PreferredSize, QtCore.QSizeF(-1, -1))
                 for it in items]
        if self.orientation() == Qt.Horizontal:
            w_fn = sum
            h_fn = max
        else:
            w_fn = max
            h_fn = sum
        width = w_fn(sz.width() for sz in sizes)
        height = h_fn(sz.height() for sz in sizes)
        return QtCore.QSizeF(width, height)


class FlowArrangement(OrientedArrangement):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(Qt.Horizontal, parent=parent)
        self._dense = True
        self._justify = Justify.stretch
        self._content_justify = Justify.start
        self._align_items = Align.start
        self._min_item_length = 0.0

    # We repurpose spacing width/height as item space and line spacing

    def itemSpacing(self) -> float:
        return self._spacing.width()

    @settable()
    def setItemSpacing(self, spacing: float) -> None:
        self._spacing.setWidth(spacing)
        self.invalidate()

    def lineSpacing(self) -> float:
        return self._spacing.height()

    @settable()
    def setItemSpacing(self, spacing: float) -> None:
        self._spacing.setHeight(spacing)
        self.invalidate()

    def stretchFactor(self, item: QtWidgets.QGraphicsWidget) -> int:
        return self.metadata(item, 1)

    def setStretchFactor(self, item: QtWidgets.QGraphicsWidget, factor: int):
        self.setMetadata(item, factor)

    def crossAlignment(self) -> Align:
        return self._align_items

    @settable("item_align")
    def setCrossAlignment(self, align: Union[str, Align]) -> None:
        if isinstance(align, str):
            align = alignment_names[align]
        self._align_items = align
        self.invalidate()

    def justification(self) -> Justify:
        return self._justify

    @settable("justify")
    def setJustification(self, justify: Union[str, Justify]) -> None:
        if isinstance(justify, str):
            justify = justification_names[justify]
        self._justify = justify
        self.invalidate()

    def contentJustification(self) -> Justify:
        return self._content_justify

    @settable("content_justify")
    def setContentJustification(self, justify: Union[str, Justify]):
        if isinstance(justify, str):
            justify = justification_names[justify]
        self._content_justify = justify
        self.invalidate()

    def minimumItemLength(self) -> float:
        return self._min_item_length

    @settable("min_item_length")
    def setMinimumItemLength(self, length: float) -> None:
        self._min_item_length = length
        self.invalidate()

    def _implicitSizeHint(self, items: Sequence[QtWidgets.QWidget]
                          ) -> QtCore.QSizeF:
        if not items:
            return QtCore.QSizeF()

        horiz = self.orientation() == Qt.Horizontal
        sizes = [validSizeHint(it, Qt.PreferredSize, QtCore.QSizeF(-1, -1))
                 for it in items]
        length = sum((sz.width() if horiz else sz.height()) for sz in sizes)
        cross = max((sz.height() if horiz else sz.width()) for sz in sizes)
        space = self.horizontalSpacing() if horiz else self.verticalSpacing()
        length += ((len(items) - 1) * space)
        if horiz:
            size = QtCore.QSizeF(length, cross)
        else:
            size = QtCore.QSizeF(cross, length)
        return size

    @staticmethod
    def _wrapLines(orient: Qt.Orientation, item_rects: Sequence[ItemRectPair],
                   avail: float, space: float) -> Iterable[int]:
        x = 0.0
        brk = 0
        for i, (item, rect) in enumerate(item_rects):
            extent = rect.width() if orient == Qt.Horizontal else rect.height()
            if i and x + extent > avail:
                brk = i
                yield brk
                x = 0.0
            x += extent + space
        if brk < len(item_rects):
            yield len(item_rects)

    def _rects(self, which: Qt.SizeHint, geom: QtCore.QRectF,
               items: Sequence[QtWidgets.QGraphicsWidget]
               ) -> Iterable[ItemRectPair]:
        orient = self.orientation()
        line_just = self.justification()
        item_align = self.crossAlignment()
        content_just = self.contentJustification()
        line_spacing = self.lineSpacing()
        item_spacing = self.itemSpacing()
        horiz = orient == Qt.Horizontal
        min_item_len = self.minimumItemLength()

        # constraint = self._constraint(orient, geom.size())
        constraint = QtCore.QSizeF(-1, -1)
        item_rects = self._itemRects(Qt.PreferredSize, constraint, items)

        if horiz:
            avail = geom.width()
            avail_length = geom.height()
            if min_item_len:
                for _, r in item_rects:
                    r.setWidth(max(r.width(), min_item_len))
        else:
            avail = geom.height()
            avail_length = geom.width()
            if min_item_len:
                for _, r in item_rects:
                    r.setHeight(max(r.height(), min_item_len))

        # Break the full list into lines
        lines: list[Sequence[ItemRectPair]] = []
        line_sizes: list[float] = []
        break_start = 0
        offset = 0.0
        for line_break in self._wrapLines(orient, item_rects, avail,
                                          item_spacing):
            line = item_rects[break_start:line_break]
            break_start = line_break
            stretches = [self.stretchFactor(item) for item, _ in line]
            if horiz:
                pos = QtCore.QPointF(geom.x(), geom.y() + offset)
                avail = geom.width()
            else:
                pos = QtCore.QPointF(geom.x() + offset, geom.y())
                avail = geom.height()
            across = justifyAndAlign(orient, line, pos, avail, -1, line_just,
                                     item_align, item_spacing, stretches)
            offset += across + line_spacing

        #     lines.append(line)
        #     if horiz:
        #         line_breadth = max(r.height() for _, r in line)
        #     else:
        #         line_breadth = max(r.width() for _, r in line)
        #     line_sizes.append(line_breadth)
        #     i = line_break
        #
        # line_offset, line_spacing, line_scales = justify(
        #     line_sizes, avail_length, line_spacing, content_just
        # )
        # for line, line_breadth, line_scale in zip(lines, line_sizes, line_scales):
        #     arrangeLine(
        #         avail, line, orient, item_spacing, line_just, item_align,
        #         line_scale=line_scale, line_offset=line_offset
        #     )
        #     line_offset += line_breadth * line_scale + line_spacing

        return item_rects


class SwitchArrangement(Arrangement):
    def __init__(self, parent: QtCore.QObject = None):
        super().__init__(parent)
        self._break_width = 200.0

    def breakWidth(self) -> float:
        return self._break_width

    @settable()
    def setBreakWidth(self, width: float) -> None:
        self._break_width = width
        self.invalidate()

    def _rects(self, which: Qt.SizeHint, geom: QtCore.QRectF,
               items: Sequence[QtWidgets.QGraphicsWidget]
               ) -> Iterable[ItemRectPair]:
        if geom.width() > self._break_width:
            orient = Qt.Horizontal
        else:
            orient = Qt.Vertical
        spacing = self.spacing()
        item_spacing = (spacing.width() if orient == Qt.Horizontal
                        else spacing.height())
        return LinearArrangement.staticRects(
            which, geom, items, orient, item_spacing,
            Align.stretch, Justify.stretch,
        )


class Matrix(Arrangement):
    _auto_margins = False

    def __init__(self, parent: QtCore.QObject = None):
        super().__init__(parent)
        self._width = 0.0
        self._min_column_width = DEFAULT_MIN_COL_WIDTH
        self._max_column_width = 999999.0
        self._max_column_count = 999999
        self._row_height = DEFAULT_ROW_HEIGHT
        self._h_space = DEFAULT_ITEM_SPACING
        self._v_space = DEFAULT_ITEM_SPACING
        self._stretch = True

    def maximumColumnCount(self) -> int:
        return self._max_column_count

    @settable("max_columns")
    def setMaximumColumnCount(self, count: int) -> None:
        self._max_column_count = count

    def horizontalSpacing(self) -> float:
        return self._h_space

    @settable("h_space")
    def setHorizontalSpacing(self, space: float) -> None:
        self._h_space = space
        self.invalidate()

    def verticalSpacing(self) -> float:
        return self._v_space

    @settable("v_space")
    def setVerticalSpacing(self, space: float) -> None:
        self._v_space = space
        self.invalidate()

    @settable("spacing")
    def setSpacing(self, space: float):
        self._h_space = self._v_space = space
        self.invalidate()

    def minimumColumnWidth(self) -> float:
        return self._min_column_width

    @settable("min_column_width")
    def setMinimumColumnWidth(self, width: float) -> None:
        self._min_column_width = width
        self.invalidate()

    def maximumColumnWidth(self) -> float:
        return self._max_column_width

    @settable("max_column_width")
    def setMaximumColumnWidth(self, width: float) -> None:
        self._max_column_width = width
        self.invalidate()

    def rowHeight(self) -> float:
        return self._row_height

    @settable()
    def setRowHeight(self, height: float) -> None:
        self._row_height = height
        self.invalidate()

    def columnStretch(self) -> bool:
        return self._stretch

    @settable()
    def setColumnStretch(self, stretch: bool) -> None:
        self._stretch = stretch
        self.invalidate()

    def columnCount(self, width: float, item_count: int) -> int:
        if not item_count:
            return 0
        mcc = self._max_column_count
        if mcc == 1:
            return mcc

        ms = self._margins
        h_space = self.horizontalSpacing()
        min_col = self.minimumColumnWidth()
        avail = width - (ms.left() + ms.right())
        cols = int((avail + h_space) / (min_col + h_space)) or 1
        cols = min(item_count, cols)
        return min(cols, mcc)

    def colsAndRows(self, width: float, item_count: int) -> tuple[int, int]:
        if item_count and width:
            cols = self.columnCount(width, item_count)
            rows = math.ceil(item_count / cols)
            return cols, rows
        else:
            return 0, 0

    def rowCount(self, width: float, item_count: int) -> int:
        return self.colsAndRows(width, item_count)[1]

    def visualSize(self, width: float, item_count: int) -> QtCore.QSizeF:
        cols, rows = self.colsAndRows(width, item_count)
        if not cols:
            return QtCore.QSizeF()
        col_width = self.columnWidth(width, cols)
        vw = col_width * cols + self.horizontalSpacing() * (cols - 1)

        v_space = self.verticalSpacing()
        vh = rows * self.rowHeight() + (v_space * (rows - 1))

        ms = self._margins
        vw += ms.left() + ms.right()
        vh += ms.top() + ms.bottom()

        return QtCore.QSizeF(vw, vh)

    def visualHeight(self, width: float, item_count) -> float:
        return self.visualSize(width, item_count).height()

    def singleColumnHeight(self, item_count: int) -> float:
        v_space = self.verticalSpacing()
        return item_count * self.rowHeight() + (v_space * (item_count - 1))

    def columnWidth(self, width: float, col_count: int) -> float:
        if not col_count:
            col_width = 0
        elif self.columnStretch():
            hspace = self.horizontalSpacing()
            ms = self._margins
            avail = width - (ms.left() + ms.right()) + hspace
            col_width = avail / col_count - hspace
        else:
            col_width = self.minimumColumnWidth()
        return col_width

    def mapIndextoCell(self, width: float, item_count: int, ix: int
                       ) -> tuple[int, int]:
        if ix >= item_count:
            raise ValueError(f"Out of boounds item {ix} >= {item_count}")
        col_count = self.columnCount(width, item_count)
        if col_count:
            row = int(ix / col_count)
            col = ix - (row * col_count)
        else:
            row = col = 0
        return col, row

    def mapCellToIndex(self, width: float, item_count: int, col: int, row: int
                       ) -> int:
        col_count = self.columnCount(width, item_count)
        return min(row * col_count + col, item_count - 1)

    def mapCellsToIndexes(self, width: float, item_count: int,
                          coord_list: Iterable[tuple[int, int]]
                          ) -> Iterable[int]:
        cols, rows = self.colsAndRows(width, item_count)
        for col, row in coord_list:
            if 0 <= col < cols and 0 <= row < rows:
                ix = row * cols + col
                if 0 <= ix < item_count:
                    yield ix

    def mapPointToCell(self, width: float, col_count: int,
                       point: QtCore.QPointF) -> tuple[int, int]:
        col_adv = self.columnWidth(width, col_count) + self.horizontalSpacing()
        v_adv = self.rowHeight() + self.verticalSpacing()
        if not col_adv:
            return 0, 0
        row = int(point.y() / v_adv)
        col = int(point.x() / col_adv)
        return col, row

    def mapPointToIndex(self, width: float, item_count: int,
                        point: QtCore.QPointF) -> int:
        col_count = self.columnCount(width, item_count)
        col, row = self.mapPointToCell(width, col_count, point)
        return self.mapCellToIndex(width, item_count, col, row)

    def mapCellToVisualRect(self, width: float, item_count: int,
                            col: int, row: int) -> QtCore.QRectF:
        col_count = self.columnCount(width, item_count)
        x = self.visualLeft(width, col_count, col)
        y = self.visualTop(row)
        w = self.columnWidth(width, col_count)
        return QtCore.QRectF(x, y, w, self.rowHeight())

    def mapIndexToVisualRect(self, width: float, item_count: int, ix: int
                             ) -> QtCore.QRectF:
        col, row = self.mapIndextoCell(width, item_count, ix)
        return self.mapCellToVisualRect(width, item_count, col, row)

    def visualLeft(self, width: float, col_count: int, col: int) -> float:
        x = self._margins.left()
        col_adv = self.columnWidth(width, col_count) + self.horizontalSpacing()
        x += col * col_adv
        return x

    def visualTop(self, row: int) -> float:
        v_adv = self.rowHeight() + self.verticalSpacing()
        return row * v_adv + self._margins.top()

    def visualRight(self, width: float, col_count: int, col: int) -> float:
        return (self.visualLeft(width, col_count, col) +
                self.columnWidth(width, col_count))

    def visualBottom(self, row: int) -> float:
        return self.visualTop(row) + self.rowHeight()

    def mapVisualRectToCellRect(self, width: float, col_count: int,
                                rect: QtCore.QRectF) -> QtCore.QRect:
        col1, row1 = self.mapPointToCell(width, col_count, rect.topLeft())
        col2, row2 = self.mapPointToCell(width, col_count, rect.bottomRight())
        return QtCore.QRect(col1, row1, col2 - col1, row2 - row1)

    def mapVisualRecToCells(self, width: float, item_count: int,
                            rect: QtCore.QRectF) -> Iterable[tuple[int, int]]:
        col_count = self.columnCount(width, item_count)
        cell_rect = self.mapVisualRectToCellRect(width, col_count, rect)
        c = cell_rect.x()
        r = cell_rect.y()
        for i in range(cell_rect.width()):
            for j in range(cell_rect.height()):
                yield c + i, r + j

    def mapVisualRectToIndexes(self, width: float, item_count: int,
                               rect: QtCore) -> Iterable[int]:
        coords = self.mapVisualRecToCells(width, item_count, rect)
        return self.mapCellsToIndexes(width, item_count, coords)

    def mapCellRectToVisualRect(self, width: float, col_count: int,
                                cell_rect: QtCore.QRect) -> QtCore.QRectF:
        hspace = self.horizontalSpacing()
        vspace = self.verticalSpacing()
        v_adv = self.rowHeight() + self.verticalSpacing()
        x = self.visualLeft(width, col_count, cell_rect.left())
        y = self.visualTop(cell_rect.top())
        cw = self.columnWidth(width, col_count) + hspace
        w = cw * cell_rect.width() - hspace
        h = v_adv * cell_rect.height() - vspace
        return QtCore.QRectF(x, y, w, h)

    def _implicitSizeHint(self, items: Sequence[QtWidgets.QWidget]
                          ) -> QtCore.QSizeF:
        cols = math.ceil(math.sqrt(len(items)))
        ms = self.margins()
        width = self.minimumColumnWidth() * cols
        width += self.horizontalSpacing() * (cols - 1) + ms.left() + ms.right()
        return self.visualSize(width, len(items))

    def _rects(self, which: Qt.SizeHint, geom: QtCore.QRectF,
               items: Sequence[QtWidgets.QGraphicsWidget]
               ) -> Iterable[ItemRectPair]:
        width = geom.width()
        vis_items = [it for it in items if it.isVisible()]
        count = len(vis_items)

        i = 0
        for item in vis_items:
            rect = self.mapIndexToVisualRect(width, count, i)
            yield item, rect
            i += 1


class KeyValueArrangement(Arrangement):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._spacing = QtCore.QSizeF(10.0, 0.0)
        self._key_item_name = "key"
        self._value_item_name = "value"

    @settable()
    def setKeyItemName(self, name: str) -> None:
        self._key_item_name = name

    @settable()
    def setValueItemName(self, name: str) -> None:
        self._value_item_name = name

    def _rects(self, which: Qt.SizeHint, geom: QtCore.QRectF,
               items: Sequence[QtWidgets.QGraphicsWidget]
               ) -> Iterable[ItemRectPair]:
        from .core import Graphic
        from .controls import StringGraphic

        items = [item for item in items if isinstance(item, Graphic)]
        if not items:
            return

        hspace = self._spacing.width()
        vspace = self._spacing.height()
        rect = geom.marginsRemoved(self._margins)
        key_size = QtCore.QSizeF()
        constraint = QtCore.QSizeF(rect.width() / 2.0, -1)
        for item in items:
            key_item = item.findChildGraphic(self._key_item_name)
            if key_item:
                if isinstance(key_item, StringGraphic):
                    size = key_item.implicitSize()
                else:
                    size = key_item.sizeHint(Qt.PreferredSize, constraint)
                key_size = key_size.expandedTo(size)

        kw = key_size.width()
        vx = kw + hspace
        vw = rect.width() - kw - hspace
        constraint = QtCore.QSizeF(vw, -1)
        y = rect.y()
        for item in items:
            key_item = item.findChildGraphic(self._key_item_name)
            value_item = item.findChildGraphic(self._value_item_name)
            h = key_size.height()
            if key_item:
                key_rect = QtCore.QRectF(QtCore.QPointF(0, 0), key_size)
                key_item.setGeometry(key_rect)
            if value_item:
                val_size = value_item.sizeHint(Qt.PreferredSize, constraint)
                val_rect = QtCore.QRectF(QtCore.QPointF(vx, 0), val_size)
                value_item.setGeometry(val_rect)
                h = max(h, val_size.height())
            item_rect = QtCore.QRectF(rect.x(), y, rect.width(), h)
            yield item, item_rect
            y += item_rect.height() + vspace


class PackedArrangement(OrientedArrangement):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._dense = True

    def isDense(self) -> bool:
        return self._dense

    @settable()
    def setDense(self, dense: bool):
        self._dense = dense
        self.invalidate()

    def _rects(self, which: Qt.SizeHint, geom: QtCore.QRectF,
               items: Sequence[QtWidgets.QGraphicsWidget]
               ) -> Iterable[ItemRectPair]:
        orient = self.orientation()
        spacing = self.spacing()
        dense = self.isDense()

        constraint = self._constraint(orient, geom.size())
        item_rects = self._itemRects(which, constraint, items)
        if not item_rects:
            return

        if self.orientation() == Qt.Horizontal:
            width = geom.width()
            height = sum(rect.height() for _, rect in item_rects)
            key_fn = horizontal_keyfn
        else:
            height = geom.height()
            width = sum(rect.width() for _, rect in item_rects)
            key_fn = vertical_keyfn

        packer = Packer(width, height, key_fn=key_fn)
        bottom = 0.0
        for item, rect in item_rects:
            if dense:
                placed = packer.pack(rect)
            else:
                placed = packer.linePack(rect, orient)
            if not placed:
                rect.moveTo(0.0, bottom)
                packer.placed(rect)
            bottom = max(bottom, rect.bottom())

            hspace = spacing.width() / 2.0
            vspace = spacing.height() / 2.0
            rect.adjust(hspace, vspace, -hspace, -vspace)

            yield item, rect


class PackedGridArrangement(PackedArrangement):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._cellsize = QtCore.QSizeF(DEFAULT_GRID_COL_WIDTH,
                                       DEFAULT_GRID_ROW_HEIGHT)
        self._item_poses: dict[int, QtCore.QPoint] = {}
        self._item_spans: dict[int, QtCore.QSize] = {}
        self._stretch = True

    def cellSize(self) -> QtCore.QSizeF:
        return QtCore.QSizeF(self._cellsize)

    @settable(argtype=QtCore.QSizeF)
    def setCellSize(self, size: QtCore.QSizeF):
        self._cellsize = size
        self.invalidate()

    @settable()
    def setColumnWidth(self, width: float):
        self._cellsize.setWidth(width)
        self.invalidate()

    @settable()
    def setRowHeight(self, height: float):
        self._cellsize.setHeight(height)
        self.invalidate()

    @settable()
    def setStretch(self, stretch: bool):
        self._stretch = stretch
        self.invalidate()

    def setItemPos(self, item: QtWidgets.QLayoutItem, pos: QtCore.QPoint
                   ) -> None:
        self._item_poses[id(item)] = pos
        self.invalidate()

    def setItemSpans(self, item: QtWidgets.QLayoutItem, spans: QtCore.QSize):
        self._item_spans[id(item)] = spans
        self.invalidate()

    def setItemColumnSpan(self, item: QtWidgets.QLayoutItem, span: int):
        if id(item) in self._item_spans:
            self._item_spans[id(item)].setWidth(span)
        else:
            self._item_spans[id(item)] = QtCore.QSize(span, 1)
        self.invalidate()

    def setItemRowSpan(self, item: QtWidgets.QLayoutItem, span: int):
        if id(item) in self._item_spans:
            self._item_spans[id(item)].setHeight(span)
        else:
            self._item_spans[id(item)] = QtCore.QSize(1, span)
        self.invalidate()

    def cellPos(self, pos: QtCore.QPoint, cellsize: QtCore.QSizeF = None,
                maxcols=9999, maxrows=9999) -> QtCore.QPointF:
        if cellsize is None:
            cellsize = self._cellsize
        grid_x = pos.x()
        if grid_x < 0:
            grid_x = maxcols + grid_x
        grid_y = pos.y()
        if grid_y < 0:
            grid_y = maxrows + grid_y
        return QtCore.QPointF(
            grid_x * cellsize.width() + grid_x * self.horizontalSpacing(),
            grid_y * cellsize.height() + grid_y * self.verticalSpacing()
        )

    def spanSize(self, span: QtCore.QSize, cellsize: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        if cellsize is None:
            cellsize = self._cellsize
        cw = cellsize.width()
        ch = cellsize.height()
        cols = span.width()
        rows = span.height()
        hspace = self.horizontalSpacing()
        vspace = self.verticalSpacing()
        width = cols * (cw + hspace) - hspace
        height = rows * (ch + vspace) - vspace
        return QtCore.QSizeF(width, height)

    def _rects(self, which: Qt.SizeHint, geom: QtCore.QRectF,
               items: Sequence[QtWidgets.QGraphicsWidget]
               ) -> Iterable[ItemRectPair]:
        orient = self.orientation()
        horiz = orient == Qt.Horizontal
        hspace = self.horizontalSpacing()
        vspace = self.verticalSpacing()
        cellsize = self.cellSize()
        dense = self.isDense()

        maxcols = maxrows = 99999
        avail = geom.width()
        if avail > 0 and horiz:
            maxcols = int((avail + hspace) / (cellsize.width() + hspace)) or 1
            if self._stretch:
                # Make sure we don't accidentally shrink the cell when trying to
                # stretch it!
                width = max(cellsize.width(), avail / maxcols - hspace)
                cellsize = QtCore.QSizeF(width, cellsize.height())

        item_rects: list[ItemRectPair] = []
        for item in items:
            span = self._item_spans.get(id(item), QtCore.QSize(1, 1))
            if span.width() > maxcols or span.height() > maxrows:
                span = QtCore.QSize(min(maxcols, span.width()),
                                    min(maxrows, span.height()))
            size = self.spanSize(span, cellsize)
            rect = QtCore.QRectF(QtCore.QPointF(0, 0), size)
            rect.adjust(0, 0, hspace, vspace)
            item_rects.append((item, rect))
        if not item_rects:
            return

        if orient == Qt.Horizontal:
            width = geom.width()
            height = sum(rect.height() for _, rect in item_rects)
            key_fn = horizontal_keyfn
        else:
            height = geom.height()
            width = sum(rect.width() for _, rect in item_rects)
            key_fn = vertical_keyfn

        packer = Packer(width, height, key_fn=key_fn)
        bottom = 0.0
        # First pack any absolutely positioned items
        skip: set[int] = set()
        for item, rect in item_rects:
            grid_pos = self._item_poses.get(id(item))
            if grid_pos:
                pos = self.cellPos(grid_pos, cellsize, maxcols, maxrows)
                placed = packer.packAt(rect, pos.x(), pos.y())
                if placed:
                    skip.add(id(item))
        # Now loop over the items again, avoiding the ones we just placed
        for item, rect in item_rects:
            if id(item) not in skip:
                if dense:
                    placed = packer.pack(rect)
                else:
                    placed = packer.linePack(rect, orient)
                if not placed:
                    rect.moveTo(0.0, bottom)
                    packer.placed(rect)
            bottom = max(bottom, rect.bottom())
            rect.adjust(0, 0, -hspace, -vspace)
            yield item, rect


# Adapter to provide an Arrangement as a QGraphicsLayout

class ArrangementLayout(QtWidgets.QGraphicsLayout):
    def __init__(self, arrangement: Arrangement,
                 parent: QtWidgets.QGraphicsLayoutItem = None):
        super().__init__(parent)
        self.setInstantInvalidatePropagation(True)
        self._arrangement = arrangement
        self._arrangement.invalidated.connect(self.invalidate)
        self._items: list[QtWidgets.QGraphicsLayoutItem] = []
        self._debug: Optional[str] = None

        sp = self.sizePolicy()
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    @settable()
    def setDebug(self, debug: bool) -> None:
        self._debug = debug

    def arrangement(self) -> Arrangement:
        return self._arrangement

    def count(self) -> int:
        return len(self._items)

    def addItem(self, item: QtWidgets.QGraphicsLayoutItem):
        item.setParentLayoutItem(self)
        self.addChildLayoutItem(item)
        self._items.append(item)
        self.invalidate()

    def iterItems(self) -> Iterable[QtWidgets.QGraphicsLayoutItem]:
        return iter(self._items)

    def itemAt(self, i: int) -> Optional[QtWidgets.QGraphicsLayoutItem]:
        if i < len(self._items):
            return self._items[i]

    def removeAt(self, i: int) -> None:
        if i < 0 or i >= self.count():
            raise ValueError(f"Can't remove {i} only {self.count()} items")

        item = self.itemAt(i)
        self._items.remove(item)
        item.setParentLayoutItem(None)
        assert item.parentLayoutItem() != self
        if item.ownedByLayout():
            item.deleteLater()
        self.invalidate()

    def removeItem(self, to_remove: QtWidgets.QGraphicsItem) -> bool:
        for i, item in enumerate(self.iterItems()):
            if item == to_remove:
                self.removeAt(i)
                return True
        return False

    def moveItemAt(self, old_index: int, new_index: int) -> None:
        if old_index == new_index:
            return
        if old_index < 0 or old_index >= self.count():
            raise IndexError(old_index)
        if new_index < 0 or new_index >= self.count():
            raise IndexError(new_index)
        item = self._items.pop(old_index)
        self._items.insert(new_index, item)

    def setGeometry(self, geom: QtCore.QRectF) -> None:
        if self._debug:
            print("RELAYOUT", self._debug, geom)
        self._arrangement.layoutItems(geom, self._items)

    def sizeHint(self, which: Qt.SizeHint,
                 constraint: QtCore.QSizeF = None) -> QtCore.QSizeF:
        hint = self._arrangement.sizeHint(which, constraint, self._items)
        if self._debug:
            print("LSH", self._debug, which, constraint, "=", hint)
        return hint

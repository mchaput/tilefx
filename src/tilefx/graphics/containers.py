from __future__ import annotations
import math
from typing import cast, Iterable, Optional, Sequence, Union

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from ..config import settable
from ..util import validSizeHint
from . import core, effects, layouts
from .core import graphictype, path_element, makeAnim, Graphic


class ContainerGraphic(core.AreaGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._items: list[Graphic] = []

    # def setGeometry(self, rect: QtCore.QRectF) -> None:
    #     super().setGeometry(rect)
    #     self._repositionContents()

    def resizeEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        super().resizeEvent(event)
        self._repositionContents()

    def addChild(self, item: QtWidgets.QGraphicsItem):
        super().addChild(item)
        if isinstance(item, Graphic) and item not in self._items:
            self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Graphic:
        return self._items[index]

    def indexOf(self, item: QtWidgets.QGraphicsItem) -> int:
        return self._items.index(item)

    def visibleItems(self) -> Iterable[Graphic]:
        return (item for item in self._items if item.isVisible())

    def _repositionContents(self) -> None:
        raise NotImplementedError

    def _reset(self) -> None:
        # self._anim_group.stop()
        self._repositionContents()



class SwitchingContainerGraphic(ContainerGraphic):
    currentIndexChanged = QtCore.Signal(int)

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._index: int = 0

    def addChild(self, item: QtWidgets.QGraphicsItem):
        super().addChild(item)

    def currentIndex(self) -> int:
        return self._index

    def setCurrentByName(self, name: str) -> None:
        for i, item in enumerate(self._items):
            if item.objectName() == name:
                return self.setCurrentIndex(i)
        else:
            raise NameError(f"No child named {name!r} in {self!r}")

    def currentItem(self) -> QtWidgets.QGraphicsItem:
        return self.itemAt(self.currentIndex())

    @settable()
    def setCurrent(self, item: Union[Graphic, str, int]) -> None:
        if isinstance(item, int):
            self.setCurrentIndex(item)
        elif isinstance(item, str):
            self.setCurrentByName(item)
        elif isinstance(item, Graphic):
            self.switchTo(item)
        else:
            raise TypeError(f"Can't set current item to {item!r}")

    def setCurrentIndex(self, ix: int) -> None:
        if ix != self._index:
            prev = self._index
            self._index = ix
            self._transition(prev, ix)
            self.currentIndexChanged.emit(ix)

    def goToNext(self) -> None:
        if not self.count():
            return
        ix = self.currentIndex() + 1
        if ix >= self.count():
            ix = 0
        self.setCurrentIndex(ix)

    def goToPrevious(self) -> None:
        if not self.count():
            return
        ix = self.currentIndex() - 1
        if ix < 0:
            ix = self.count() - 1
        self.setCurrentIndex(ix)

    def _transition(self, previous: int, current: int) -> None:
        self._repositionContents()


@graphictype("containers.flip")
class FlipContainerGraphic(SwitchingContainerGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._duration = 400
        self._flipx = 0.0
        self._flipy = 90.0
        self._flipping = False
        self._stretch_contents = False

        self._anim_group = QtCore.QSequentialAnimationGroup(self)
        self._anim_group.finished.connect(self._reset)

    def isStretchingContents(self) -> bool:
        return self._stretch_contents

    @settable(argtype=bool)
    def setStretchContents(self, stretch: bool) -> None:
        self._stretch_contents = stretch
        self._repositionContents()

    def addChild(self, item: QtWidgets.QGraphicsItem) -> None:
        first = not self.count()
        super().addChild(item)
        if isinstance(item, Graphic):
            item.setVisible(first)
        self._repositionContents()

    def _repositionContents(self) -> None:
        rect = self.rect()
        ctr = rect.center()
        for item in self._items:
            item.setPos(ctr)
            if self.isStretchingContents():
                item.resize(rect.size())
            item.setXYRotation(QtCore.QPointF())

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        super().mousePressEvent(event)
        if self._flipping:
            return
        self.goToNext()

    def _reset(self):
        self._anim_group.stop()
        self._flipping = False
        current = self.currentItem()
        for gr in self._items:
            gr.setVisible(gr is current)
            gr.setXYRotation(QtCore.QPointF())

    def _switch(self, from_graphic: Graphic, to_graphic: Graphic) -> None:
        from_graphic.hide()
        to_graphic.show()

    def _transition(self, previous: int, current: int) -> None:
        self._flipping = True
        from_graphic = self.itemAt(previous)
        to_graphic = self.itemAt(current)

        duration = self._duration // 2
        group = self._anim_group
        group.stop()
        from_graphic.setXYRotation(QtCore.QPointF())
        for g in self._items:
            g.setVisible(g is from_graphic)

        group.clear()

        anim1 = makeAnim(from_graphic, b"xyrot", duration=duration,
                         curve=QtCore.QEasingCurve.Linear)
        anim1.setStartValue(from_graphic.xyRotation())
        anim1.setEndValue(QtCore.QPointF(self._flipx, self._flipy))
        anim1.finished.connect(lambda: self._switch(from_graphic, to_graphic))
        group.addAnimation(anim1)

        anim2 = makeAnim(to_graphic, b"xyrot", duration=duration,
                         curve=QtCore.QEasingCurve.Linear)
        anim2.setStartValue(QtCore.QPointF(-self._flipx, -self._flipy))
        anim2.setEndValue(QtCore.QPointF(0.0, 0.0))
        group.addAnimation(anim2)

        group.start()

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     r = self.rect()
    #     painter.fillRect(r, QtGui.QColor("#405060"))


@graphictype("containers.shuffle")
class ShuffleContainerGraphic(SwitchingContainerGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._before_count = 2
        self._after_count = 2
        self._duration = 300
        self._delta = QtCore.QPointF(0, 10)
        self._resize_to_max = False
        self._current_value = 0.0

    def addChild(self, item: QtWidgets.QGraphicsItem):
        super().addChild(item)
        # effect = QtWidgets.QGraphicsBlurEffect()
        effect = effects.ColorBlendEffect()
        effect.setColor(QtGui.QColor("#000000"))
        effect.setStrength(0.0)
        item.setGraphicsEffect(effect)

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneEvent):
        if not self.count():
            return
        self.goToNext()

    @settable()
    def setResizeToMax(self, resize_to_max: bool) -> None:
        self._resize_to_max = resize_to_max
        self._repositionContents()

    def beforeCount(self) -> int:
        return self._before_count

    @settable()
    def setBeforeCount(self, count: int):
        self._before_count = count
        self._repositionContents()

    def afterCount(self) -> int:
        return self._after_count

    @settable()
    def setAfterCount(self, count: int):
        self._after_count = count
        self._repositionContents()

    def currentValue(self) -> float:
        return self._current_value

    def setCurrentValue(self, value: float) -> None:
        self._current_value = value
        self._repositionContents()

    value = QtCore.Property(float, currentValue, setCurrentValue)

    def startIndex(self) -> int:
        cur_ix = round(self._current_value)
        return max(0, cur_ix - self.beforeCount())

    def endIndex(self) -> int:
        cur_ix = round(self._current_value)
        return min(self.count(), cur_ix + self.afterCount() + 1)

    def visibleCount(self) -> int:
        return self.endIndex() - self.startIndex()

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        if which in (Qt.MinimumSize, Qt.PreferredSize, Qt.MaximumSize):
            delta = self._delta
            shown = self.visibleCount()
            tdx = delta.x() * (shown + 1)
            tdy = delta.y() * (shown + 1)
            cw = constraint.width()
            ch = constraint.height()
            if cw >= 0:
                cw -= tdx
            if ch >= 0:
                ch -= tdy
            c = QtCore.QSizeF(cw, ch)
            size = QtCore.QSizeF()
            for item in self.visibleItems():
                isize = item.effectiveSizeHint(which, c)
                size = size.expandedTo(isize)
            return size + QtCore.QSizeF(tdx, tdy)
        else:
            return constraint

    def _repositionContents(self) -> None:
        rect = self.rect()
        count = self.count()
        before = self.beforeCount()
        after = self.afterCount()

        cur_val = self._current_value
        cur_ix = round(cur_val)
        start = max(0, cur_ix - before)
        end = min(count, cur_ix + after + 1)
        shown = end - start

        delta = self._delta
        dx = delta.x()
        dy = delta.y()
        tdx = dx * (shown - 1)
        tdy = dy * (shown - 1)
        color_step = 0.5 / (shown + 1)

        iw = rect.width() - tdx
        ih = rect.height() - tdy
        max_size = QtCore.QSizeF(iw, ih)
        constraint = QtCore.QSizeF(iw, -1)
        ctr = rect.center()
        scale_step = 0.02
        for i in range(count):
            item = self._items[i]
            if start <= i < end:
                item.show()
                dist = cur_val - i

                z = count - abs(cur_ix - i)
                item.setZValue(z)
                if self._resize_to_max:
                    isize = max_size
                else:
                    isize = item.sizeHint(Qt.PreferredSize, constraint)


                effect = item.graphicsEffect()
                # if effect and isinstance(effect, QtWidgets.QGraphicsBlurEffect):
                #     effect.setBlurRadius(abs(x_dist) * 2.0)
                if effect and isinstance(effect, effects.ColorBlendEffect):
                    colorize = abs(dist) * color_step
                    effect.setStrength(colorize)

                pos = QtCore.QPointF(
                    ctr.x() - dist * dx - isize.width() / 2,
                    ctr.y() - dist * dy - isize.height() / 2
                )
                irect = QtCore.QRectF(pos, isize)
                item.setGeometry(irect)

                item.setTransformOriginPoint(item.rect().center())
                item.setScale(1.0 - abs(dist) * scale_step)
            else:
                item.hide()
                item.setScale(1.0)
                # item.setXYRotation(QtCore.QPointF(0, 0))

    def _transition(self, previous: int, current: int) -> None:
        self.animateProperty(b"value", float(previous), float(current),
                             duration=self._duration,
                             curve=QtCore.QEasingCurve.InOutSine)


@graphictype("containers.reveal_stack")
class ExpandingStackGraphic(ContainerGraphic):
    openStateChanged = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._open = False
        self._expansion = 0.0
        self._arrangement = layouts.LinearArrangement()
        self._arrangement.setSpacing(10.0)
        self._closed_count = 4
        self._closed_offset = 5.0
        self._closed_scale = 0.9
        self._duration = 400
        self._animating = False

        self.setClipping(True)

        self.setHasHeightForWidth(True)

    def addChild(self, item: QtWidgets.QGraphicsItem):
        z = -self.count()
        super().addChild(item)
        item.setZValue(z)
        effect = effects.ColorBlendEffect()
        effect.setColor(QtGui.QColor("#000000"))
        effect.setStrength(0.0)
        item.setGraphicsEffect(effect)
        # item.installEventFilter(self)

    # def eventFilter(self, watched: QtWidgets.QGraphicsWidget,
    #                 event: QtCore.QEvent) -> bool:
    #     # if watched not in self._items:
    #     #     watched.uninstallEventFilter(self)
    #     if event.type() in (event.Show, event.Hide):
    #         print("watched=", watched, "type=", event.type())
    #         self._repositionContents()
    #         self.updateGeometry()
    #     return super().eventFilter(watched, event)


    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneEvent):
        if not self.count():
            return
        first = self.itemAt(0)
        if first.geometry().contains(event.pos()):
            self.toggle()

    @path_element(layouts.LinearArrangement, "layout")
    def arrangement(self) -> layouts.LinearArrangement:
        return self._arrangement

    def count(self) -> int:
        return len(self._items)

    def closedCount(self) -> int:
        return self._closed_count

    @settable()
    def setClosedCount(self, count: int):
        self._closed_count = count
        self._repositionContents()

    @settable()
    def setClosedOffset(self, offset: float) -> None:
        self._closed_offset = offset
        self._repositionContents()

    @settable()
    def setDuration(self, duration: int) -> None:
        self._duration = duration

    def expansionValue(self) -> float:
        return self._expansion

    def setExpansion(self, expansion: float) -> None:
        self._expansion = expansion
        self.updateGeometry()

    expansion = QtCore.Property(float, expansionValue, setExpansion)

    def isOpen(self) -> bool:
        return self._open

    @settable(argtype=bool)
    def setOpen(self, open: bool, animated=True):
        if open != self._open:
            self._open = open
            self._transition(open, animated=animated)
            self.openStateChanged.emit()

    def toggle(self, animated=True) -> None:
        self.setOpen(not self.isOpen(), animated=animated)

    def _closedRects(self, item_rects: Iterable[tuple[Graphic, QtCore.QRectF]]
                     ) -> Iterable[tuple[Graphic, QtCore.QRectF, float]]:
        arrangement = self._arrangement
        shown = self._closed_count
        y = arrangement.margins().top()
        y_off = self._closed_offset
        bottom = 0.0

        for i, (item, rect) in enumerate(item_rects):
            h = rect.height()
            if 0 < i < shown:
                h *= 1.0 - i * 0.02
                y = bottom - h
            yield item, rect, y
            bottom = y + h + y_off

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        arng = self._arrangement
        ms = arng.margins()
        expansion = self._expansion

        if not self._items:
            return QtCore.QSizeF(0, 0)

        if expansion == 1.0 or not self._items:
            return arng.sizeHint(which, constraint, self._items)
        else:
            geom = QtCore.QRectF(QtCore.QPointF(), constraint)
            item_rects = list(arng.rects(which, geom, self._items))
            if not item_rects:
                return QtCore.QSizeF(0, 0)

            closed_rects = list(self._closedRects(item_rects))
            if constraint.width() >= 0:
                w = constraint.width()
            else:
                w = max(r.right() for _, r in item_rects) + ms.right()

            open_h = max(r.bottom() for _, r in item_rects) + ms.bottom()
            closed_h = (max(y + r.height() for _, r, y in closed_rects) +
                        ms.bottom())

            diff = open_h - closed_h
            h = closed_h + diff * expansion
            size = QtCore.QSizeF(w, h)
            return size

    def _transition(self, open: bool, animated=True) -> None:
        self.prepareGeometryChange()
        animated = animated and not self.animationDisabled()
        expanded = float(open)
        if animated:
            self.animateProperty(b"expansion", self.expansionValue(),
                                 expanded, duration=self._duration)
        else:
            self.setExpansion(expanded)
            self._repositionContents()
        self.updateGeometry()

    def _repositionContents(self) -> None:
        rect = self.rect()
        expansion = self.expansionValue()
        arng = self._arrangement
        item_rects = arng.rects(Qt.PreferredSize, rect, self._items)
        if expansion == 1.0:
            for i, (item, rect) in enumerate(item_rects):
                item.setGeometry(rect)
                item.setOpacity(1.0)
        else:
            shown = self._closed_count
            color_step = 0.5 / (shown + 1)
            scale_step = 0.02
            for i, (item, rect, y) in enumerate(self._closedRects(item_rects)):
                rect.moveTop(y + (rect.y() - y) * expansion)
                item.setGeometry(rect)

                item.setTransformOriginPoint(item.rect().center())
                if i < shown:
                    colorize = i * color_step
                    alpha = 1.0
                    size_scale = 1.0 - i * scale_step
                else:
                    colorize = 0.5
                    alpha = 0.0
                    size_scale = 1.0 - shown * scale_step
                item.setOpacity(alpha + (1.0 - alpha) * expansion)
                item.setScale(size_scale + (1.0 - size_scale) * expansion)
                effect = item.graphicsEffect()
                if effect and isinstance(effect, effects.ColorBlendEffect):
                    effect.setStrength(colorize * (1.0 - expansion))

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.setPen(Qt.blue)
    #     painter.drawRect(self.rect())

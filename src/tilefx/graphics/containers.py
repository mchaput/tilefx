from __future__ import annotations
from typing import cast, Iterable, Optional, Sequence, Union

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from ..config import settable
from . import controls, core, effects, layouts
from .core import graphictype, path_element, makeAnim, Graphic


@graphictype("containers.scroll")
class ScrollGraphic(core.RectangleGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._last_content_size = QtCore.QSizeF(-1, -1)
        self._updating_contents = False
        self._content: Optional[Graphic] = None
        self._scroll_pos = QtCore.QPointF(0, 0)
        self._vsb_item = controls.ScrollBarItem(Qt.Vertical, self)
        self._vsb_item.setZValue(20)
        self._title_item: Optional[Graphic] = None
        self._title_target_name: Optional[str] = None
        self._title_target_item: Optional[Graphic] = None
        self._title_min_y = 0.0
        self._title_shown = False
        self._footer_item: Optional[Graphic] = None

        self._match_width = True
        self.setClipping(True)

        self.verticalScrollBar().valueChanged.connect(self._onVScroll)
        self.verticalScrollBar().setSingleStep(16)

        self._updateContents()

    # def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange,
    #                value: Any) -> Any:
    #     if change == self.ItemSceneChange:
    #         old_scene = self.scene()
    #         if old_scene:
    #             old_scene.sceneRectChanged.disconnect(self.updateGeometry)
    #         new_scene = cast(QtWidgets.QGraphicsScene, value)
    #         new_scene.sceneRectChanged.connect(self.updateGeometry)
    #
    #     return super().itemChange(change, value)

    def setGeometry(self, rect: QtCore.QRectF) -> None:
        super().setGeometry(rect)
        self._updateContents()

    def resizeEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        super().resizeEvent(event)
        self._updateContents()

    def addChild(self, item: QtWidgets.QGraphicsItem) -> None:
        self.setContentItem(item)

    @path_element(Graphic, "contents")
    def contentsItem(self) -> Graphic:
        return self._content

    @settable("content_item", value_object_type=Graphic)
    def setContentItem(self, item: Graphic) -> None:
        if self._content:
            # self._content.removeEventFilter(self)
            self._content.geometryChanged.disconnect(self._onContentSizeChanged)

        self._content = item
        item.setParentItem(self)
        item.setZValue(0)

        self._content.geometryChanged.connect(self._onContentSizeChanged)
        self._content.installEventFilter(self)
        self._updateContents()

    def _onContentSizeChanged(self) -> None:
        content = self._content
        if content:
            size = content.size()
            if size.isEmpty():
                return
            if size != self._last_content_size:
                if self._updating_contents:
                    # print("already", self.objectName(), size)
                    pass
                else:
                    self.updateGeometry()
                    self._updateContents()
                    self._last_content_size = size

    def contentsSizeHint(self, which: Qt.SizeHint,
                        constraint: QtCore.QSizeF = None) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        return self.contentsItem().sizeHint(which, constraint)

    def eventFilter(self, watched: QtWidgets.QGraphicsWidget,
                    event: QtCore.QEvent) -> bool:
        if watched == self._content and event.type() == event.LayoutRequest:
            self.prepareGeometryChange()
            self.updateGeometry()
            self._updateContents()
        return super().eventFilter(watched, event)

    def titleItem(self) -> Optional[Graphic]:
        return self._title_item

    @settable("title_item", value_object_type=Graphic)
    def setTitleItem(self, item: Graphic) -> None:
        self._title_item = item
        item.setParentItem(self)
        item.setZValue(10)
        self._updateTitleAndFooterVisibility(animated=False)

    def titleTargetItem(self) -> Optional[QtWidgets.QGraphicsWidget]:
        name = self._title_target_name
        item = self._title_target_item
        if name and not item:
            item = self.findChildGraphic(name, recursive=True)
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

    def footerItem(self) -> Optional[Graphic]:
        return self._footer_item

    @settable("footer_item", value_object_type=Graphic)
    def setFooterItem(self, item: Graphic) -> None:
        self._footer_item = item
        item.setParentItem(self)
        item.setZValue(9)
        self._updateContents()

    def dataProxy(self) -> Optional[Graphic]:
        return self.contentsItem()

    def localEnv(self) -> dict[str, Any]:
        return self.contentsItem().localEnv()

    @path_element(Graphic, "title")
    def titleItem(self) -> Graphic:
        return self._title_item

    @path_element(Graphic, "footer")
    def footerItem(self) -> Graphic:
        return self._footer_item

    def verticalScrollBar(self) -> QtWidgets.QScrollBar:
        return self._vsb_item.widget()

    @settable("scroll_y")
    def setScrollY(self, y: int) -> None:
        self.verticalScrollBar().setValue(y)

    def scrollToTop(self) -> None:
        self.setScrollY(0)

    def scrollbarNeeded(self) -> bool:
        if self._content:
            return self._content.size().height() > self.size().height()
        else:
            return False

    def viewportRect(self) -> QtCore.QRectF:
        # This must return the visible rect in SCENE coordinates
        scene_r = self.parentViewportRect()
        safe_r = self.mapRectToScene(self.safeArea())
        return scene_r.intersected(safe_r)

    def safeArea(self) -> QtCore.QRectF:
        rect = self.rect()
        if self.scrollbarNeeded():
            vsb = self.verticalScrollBar()
            rect.setRight(rect.right() - vsb.width())
        if self.shouldShowTitle():
            title = self._title_item
            rect.setTop(rect.top() + title.size().height())
        if self.shouldShowFooter():
            footer = self._footer_item
            rect.setBottom(rect.bottom() - footer.size().height())
        return rect

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        contents = self.contentsItem()
        if contents:
            vsb_width = self.verticalScrollBar().width()
            cw = constraint.width()
            if cw >= 0:
                constraint.setWidth(cw - vsb_width)
            size = contents.sizeHint(which, constraint)
            return size
        return constraint

    def _onVScroll(self) -> None:
        v = self.verticalScrollBar().value()
        self._scroll_pos.setY(max(0, v))
        self._updateScrollPosition()
        self._updateTitleAndFooterVisibility()
        self._vsb_item.update()

    def _updateScrollPosition(self) -> None:
        contents = self.contentsItem()
        if not contents:
            return
        contents.setPos(-self._scroll_pos)

    def _updateContents(self) -> None:
        if self._updating_contents:
            raise Exception(f"Already updating {self.objectName()}")
        rect = self.rect()
        width = rect.width()
        page_height = rect.height()
        contents = self.contentsItem()
        if not contents:
            return
        self._updating_contents = True

        vsb = self.verticalScrollBar()
        vsb_width = vsb.width()
        vsb_x = rect.right() - vsb_width
        vsb_rect = QtCore.QRectF(vsb_x, rect.y(), vsb_width, rect.height())
        # if self.objectName() == "root":
        #     print("rect=", rect, "x=", vsb_x, "vsb=", vsb_rect)
        self._vsb_item.setGeometry(vsb_rect)
        self._vsb_item.update()
        vsb.setPageStep(int(page_height))

        if self._match_width:
            vp_width = width - vsb_width - 1
            constraint = QtCore.QSizeF(vp_width, -1)
            csize = contents.sizeHint(Qt.PreferredSize, constraint)
            # if csize.height() <= page_height:
            #     vp_width = width
            csize.setWidth(vp_width)
            crect = QtCore.QRectF(-self._scroll_pos, csize)
            contents.setGeometry(crect)
        else:
            csize = contents.size()

        can_scroll = rect.height() < csize.height()
        self._vsb_item.setVisible(can_scroll)
        if can_scroll:
            vscroll_max = csize.height() - page_height
            vsb.setRange(0, int(vscroll_max))
        else:
            vsb.setRange(0, 0)
        self._updateScrollPosition()
        self._vsb_item.update()

        constraint = QtCore.QSizeF(csize.width(), -1)
        title = self._title_item
        if title:
            hsize = title.effectiveSizeHint(Qt.PreferredSize, constraint)
            title.setGeometry(0, 0, csize.width(), hsize.height())
        footer = self._footer_item
        if footer:
            fsize = footer.effectiveSizeHint(Qt.PreferredSize, constraint)
            footer.setGeometry(0, rect.bottom() - fsize.height(),
                               csize.width(), fsize.height())

        self._updateTitleAndFooterVisibility()
        self._updating_contents = False

    # def update(self, *args, **kwargs):
    #     self._updateContents()
    #     super().update(*args, **kwargs)

    def shouldShowTitle(self) -> bool:
        header = self._title_item
        if not header:
            return False
        if self._scroll_pos.y() < self._title_min_y:
            return False
        if target := self.titleTargetItem():
            scroll_y = self._scroll_pos.y()
            target_bottom = target.geometry().bottom() - scroll_y
            header_bottom = header.geometry().bottom()
            return target_bottom < header_bottom
        return True

    def shouldShowFooter(self) -> bool:
        footer = self._footer_item
        return bool(footer)

    def _updateTitleAndFooterVisibility(self, animated=True):
        animated = animated and not self.animationDisabled()
        title = self._title_item
        if title:
            # Keep track of _title_shown instead of just checking if the title
            # is currently visible, because it could be visible but already
            # fading out
            show_title = self.shouldShowTitle()
            if animated and show_title and not self._title_shown:
                title.fadeIn()
            elif animated and self._title_shown and not show_title:
                title.fadeOut()
            else:
                title.setVisible(show_title)
            self._title_shown = show_title
        footer = self._footer_item
        if footer:
            footer.setVisible(self.shouldShowFooter())

    def wheelEvent(self, event: QtWidgets.QGraphicsSceneWheelEvent) -> None:
        if self.scrollbarNeeded():
            self.scene().sendEvent(self._vsb_item, event)
            event.accept()
        else:
            parent = self.parentItem()
            if parent:
                parent.wheelEvent(event)

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     r = self.rect()
    #     painter.setPen(Qt.red)
    #     painter.drawRect(r)
    #     painter.setPen(Qt.green)
    #     painter.drawRect(self.mapRectFromScene(self.viewportRect()))


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

from __future__ import annotations
import time
from collections import defaultdict
from typing import cast, Any, Collection, Iterable, Optional, Sequence, Union

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .. import models
from ..config import settable
from . import core, controls, layouts, themes
from .core import graphictype, path_element, Graphic, DataGraphic


# Keys for QGraphicsItem.data()
ITEM_KEY_VALUE = 21
ITEM_ROW_NUM = 22
ITEM_SECTION_VALUE = 134


@graphictype("views.scroll")
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


@graphictype("views.data_layout")
class DataLayoutGraphic(DataGraphic):
    contentSizeChanged = QtCore.Signal()
    rowHighlighted = QtCore.Signal(int)

    _use_modelReset = True
    _use_dataChanged = True
    _use_rowsInserted = True
    _use_rowsRemoved = True
    _use_rowsMoved = True
    _use_layoutChanged = True

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._prev_size = QtCore.QSizeF(-1, -1)
        self._scene_rect_changed = False
        self._hide_when_empty = False
        self._visible = True
        self._interactive = False
        self._hilite_row = -1

        self._hilite = core.RectangleGraphic(self)
        self._hilite.setCornerRadius(4)
        self._hilite.setFillColor(themes.ThemeColor.highlight)
        self._hilite.setOpacity(0.25)
        self._hilite.hide()

        self._item_template: dict[str, Any] = {}
        self._arrangement: Optional[layouts.Arrangement] = None
        self._laying_out = False
        self._animate_resizing = False

        # Child items, by the item's unique key
        self._items: dict[int | str, Graphic] = {}

        # self.geometryChanged.connect(self._resized)

    # def _rowDataChanged(self, first_row: int, last_row: int) -> None:
    #     model = self.model()
    #     controller = self.controller()
    #     if controller:
    #         for row in range(first_row, last_row + 1):
    #             index = model.index(row, 0)
    #             graphic = self.itemForRow(row)
    #             controller.updateObjectFromModel(index, graphic)

    def setGeometry(self, rect: QtCore.QRectF) -> None:
        super().setGeometry(rect)
        size = rect.size()
        if self._scene_rect_changed or size != self._prev_size:
            self._scene_rect_changed = False
            self._prev_size = size
            self._updateContents()

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange,
                   value: Any) -> Any:
        if change == self.ItemScenePositionHasChanged:
            self._updateContents()
        elif change == self.ItemSceneChange:
            old_scene = self.scene()
            if old_scene:
                old_scene.sceneRectChanged.disconnect(self._onSceneRectChanged)
            new_scene = cast(QtWidgets.QGraphicsScene, value)
            new_scene.sceneRectChanged.connect(self._onSceneRectChanged)
        return super().itemChange(change, value)

    def _onSceneRectChanged(self) -> None:
        self._scene_rect_changed = True
        self.updateGeometry()
        # self._updateContents()

    def resizeEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        super().resizeEvent(event)
        self.contentSizeChanged.emit()

    def _rowsInserted(self, _: QtCore.QModelIndex, first: int, last: int
                      ) -> None:
        if self._hide_when_empty:
            self._updateVisibility()
        self.updateGeometry()
        self._updateContents()

    def _rowsRemoved(self, _: QtCore.QModelIndex, first: int, last: int
                     ) -> None:
        if self._hide_when_empty:
            self._updateVisibility()
        self.updateGeometry()
        self._updateContents()

    def _modelReset(self) -> None:
        if self._hide_when_empty:
            self._updateVisibility()
        self.updateGeometry()
        self._updateContents()

    def _rowDataChanged(self, start_row: int, end_row: int) -> None:
        model = self.model()
        controller = self.controller()
        if not controller:
            return

        for row in range(start_row, end_row + 1):
            graphic = self.itemForRow(row)
            if not graphic:
                raise Exception(f"Update for nonexistant row {row}")
            controller.updateItemFromModel(model, row, self, graphic)

    @classmethod
    def templateKeys(cls) -> Sequence[str]:
        return ("item_template",)

    def setObjectName(self, name: str) -> None:
        super().setObjectName(name)
        self._updateLayoutName()

    def _updateLayoutName(self):
        if self._arrangement and not self._arrangement.objectName():
            self._arrangement.setObjectName(f"{self.objectName()}__layout")

    def itemTemplates(self) -> dict[str, dict[str, Any]]:
        return {
            "item_template": self._item_template
        }

    @settable("item_template")
    def setItemTemplate(self, template_data: dict[str, Any]):
        self._item_template = template_data
        self._updateLayoutName()
        self._modelReset()

    def setModel(self, model: Optional[QtCore.QAbstractItemModel]) -> None:
        super().setModel(model)
        self._updateContents()

    @path_element(layouts.Arrangement, "layout")
    def arrangement(self) -> Optional[layouts.Arrangement]:
        return self._arrangement

    def setArrangement(self, layout: layouts.Arrangement) -> None:
        if self._arrangement:
            self._arrangement.invalidated.disconnect(self._updateContents)
        self._arrangement = layout
        self._arrangement.invalidated.connect(self._updateContents)

    def _rowsMoved(self, _: QtCore.QModelIndex, src_start: int, src_end: int,
                   __: QtCore.QModelIndex, dest_start: int) -> None:
        print("Rows moved", src_start, src_end, "-", dest_start)
        self._updateContents(anim_arrange=True)

    def _layoutChanged(self) -> None:
        print("Layout changed")
        self._updateContents(anim_arrange=True, anim_repop=True)

    # def setGeometry(self, rect: QtCore.QRectF) -> None:
    #     super().setGeometry(rect)
    #     self._updateContents(anim_arrange=self._animate_resizing)

    def resizeEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        super().resizeEvent(event)
        self._updateContents(anim_arrange=self._animate_resizing)

    def _updateContents(self, *, anim_arrange=False, anim_repop=False,
                        ) -> None:
        # t = perf_counter()
        # self.prepareGeometryChange()
        if self._laying_out:
            return
        self._laying_out = True
        animated = not self.animationDisabled()
        anim_arrange = anim_arrange and animated
        # anim_repop = anim_repop and animated
        anim_repop = False

        self._updateDataContents(anim_arrange=anim_arrange,
                                 anim_repop=anim_repop)
        self._laying_out = False
        # print(perf_counter() - t)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        model = self.model()
        if model and which == Qt.PreferredSize:
            arng = self.arrangement()
            hint = arng.sizeHint(which, constraint, list(self._items.values()))
            return hint
        return constraint

    def _updateChildren(self, *, anim_arrange=False):
        self.arrangement().layoutItems(self.rect(),
                                       list(self.childGraphics()),
                                       animated=anim_arrange)

    def _updateDataContents(self, *, anim_arrange=False, anim_repop=False):
        all_keys = set(self._items)
        live_keys: set[str] = set()
        old_items = self._items
        new_items: dict[int|str, Graphic] = {}
        for row_num in range(self.rowCount()):
            key = self._keyForRow(row_num)
            live_keys.add(key)
            item = old_items.get(key)
            if item:
                item.setOpacity(1.0)
                item.show()
                self._updateItemFromModel(item, row_num)
            else:
                item = self._makeItem(key, row_num)
                item.show()
                if anim_repop:
                    item.fadeIn()
                else:
                    item.setOpacity(1.0)
            new_items[key] = item

        self._recycleKeys(all_keys - live_keys, anim_repop=anim_repop)
        self._items = new_items
        self._rearrange()

    def _rearrange(self) -> None:
        arng = self.arrangement()
        if arng:
            arng.layoutItems(self.rect(), list(self._items.values()))

    def _collectItems(self, animated=True) -> None:
        anim_repop = animated and not self.animationDisabled()
        all_keys = set(self._items)
        live_keys = set(self._keyForRow(row) for row in range(self.rowCount()))
        self._recycleKeys(all_keys - live_keys, anim_repop=anim_repop)

    def _recycleKeys(self, unused_keys: Collection[str], *, anim_repop=False
                     ) -> None:
        # Recycle items that are no longer visible
        for unused_key in unused_keys:
            try:
                unused_item = self._items.pop(unused_key)
            except KeyError:
                raise KeyError(f"Unused key {unused_key} missing "
                               f"from {list(self._items)} "
                               f"in {self.objectName()}")
            self._recycle(unused_item, anim_repop=anim_repop)

    def _recycle(self, graphic: Graphic, anim_repop=False) -> None:
        if anim_repop:
            graphic.fadeOut()
        else:
            graphic.hide()
            graphic.setOpacity(1.0)

    def _keyForRow(self, row_num: int) -> int|float|str:
        model = self.model()
        key_value = model.index(row_num, 0).data(
            models.DataModel.UniqueIDRole
        )
        if key_value is models.DataModel.NoUniqueID:
            key_value = row_num
        return key_value

    def itemForRow(self, row_num: int, create=False) -> Optional[Graphic]:
        key = self._keyForRow(row_num)
        item = self._items.get(key)
        if create and not item:
            item = self._makeItem(key, row_num)
        return item

    def liveItems(self) -> Iterable[Graphic]:
        return self._items.values()

    def _makeItemFromScratch(self, key: Union[int, str], row: int) -> Graphic:
        tmpl = self._item_template
        if tmpl:
            controller = self.controller()
            graphic = core.graphicFromData(tmpl, parent=self,
                                           controller=controller)
        else:
            graphic = controls.PlaceholderGraphic(self)
        graphic.setZValue(1)
        return graphic

    def _updateItemFromModel(self, graphic: Graphic, row: int):
        model = self.model()
        self.controller().updateItemFromModel(model, row, self, graphic)
        key_value = self._keyForRow(row)
        graphic.setData(ITEM_KEY_VALUE, key_value)
        graphic.setData(ITEM_ROW_NUM, row)
        graphic.setLocalVariable("row_num", row)
        graphic.setLocalVariable("unique_id", key_value)
        graphic.setObjectName(f"{model.objectName()}_{row}")

    def _makeItem(self, key: Union[int, str], row: int) -> Graphic:
        graphic = self._makeItemFromScratch(key, row)
        self._updateItemFromModel(graphic, row)
        self._items[key] = graphic
        return graphic

    def showEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self._updateContents()

    def isInteractive(self) -> bool:
        return self._interactive

    @settable()
    def setInteractive(self, interactive: bool) -> None:
        self._interactive = interactive
        self.setAcceptHoverEvents(interactive)

    def setHighlightedRow(self, row: int) -> None:
        if row != self._hilite_row:
            if self._hilite_row >= 0:
                self._setRowHighlight(self._hilite_row, False)
            self._hilite_row = row
            self.rowHighlighted.emit(row)
            if row >= 0:
                self._setRowHighlight(row, True)

    def _setRowHighlight(self, row_num: int, on: bool) -> None:
        key = self._keyForRow(row_num)
        item = self._items.get(key)
        if item and isinstance(item, core.AreaGraphic):
            duration = 200 if on else 400
            item.setHighlighted(on, animated=True, duration=duration)

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self.setHighlightedRow(-1)

    def hoverMoveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        super().hoverMoveEvent(event)
        if self._interactive:
            pos = event.pos()
            model = self.model()
            if model:
                for item in self._items.values():
                    if item.geometry().contains(pos):
                        row_num = item.data(ITEM_ROW_NUM)
                        if row_num is not None:
                            self.setHighlightedRow(row_num)
                            return
            self.setHighlightedRow(-1)

    @settable()
    def setHideWhenEmpty(self, hide_when_empty: bool):
        self._hide_when_empty = hide_when_empty
        self._updateVisibility()

    @settable()
    def setVisible(self, visible: bool) -> None:
        self._visible = visible
        self._updateVisibility()

    def shouldBeVisible(self) -> bool:
        visible = self._visible
        if self._hide_when_empty and not self.model().rowCount():
            visible = False
        return visible

    def _updateVisibility(self) -> None:
        visible = self.shouldBeVisible()
        cur_vis = self.isVisible()
        if visible != cur_vis:
            super().setVisible(visible)
            self.visibleChanged.emit()


@graphictype("views.list")
class DataListGraphic(DataLayoutGraphic):
    rowHighlighted = QtCore.Signal(int)

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        self._section_data_id: Optional[models.DataID] = None
        super().__init__(parent)
        self._visible = True
        self._heading_template: dict[str, Any] = {}
        self._section_rows: defaultdict[str, list[int]] = defaultdict(list)
        self._headings: dict[str, Graphic] = {}
        self._section_gap = 10.0
        self._sections_sticky = True
        self._use_sections = True

        matrix = layouts.Matrix()
        matrix.setMinimumColumnWidth(100)
        matrix.setColumnStretch(True)
        matrix.setMargins(QtCore.QMarginsF(10, 10, 10, 10))
        self.setArrangement(matrix)

        self._reuse_items = True
        # Items that have scrolled offscreen, ready to be reused
        # (if _reuse_items is on)
        self._pool: list[Graphic] = []
        self._populated = False
        self._display_margin = 40.0

        self.setHasHeightForWidth(True)
        self.setFlag(self.ItemSendsScenePositionChanges, True)

    @classmethod
    def templateKeys(cls) -> Sequence[str]:
        return "item_template", "heading_template"

    def itemTemplates(self) -> dict[str, Optional[dict[str, Any]]]:
        return {
            "item_template": self._item_template,
            "heading_template": self._heading_template
        }

    def _rowDataChanged(self, start_row: int, end_row: int) -> None:
        has_sections = self.hasSections()
        # sect_col = self.sectionDataID()
        model = self.model()
        if not model:
            return

        sections_dirty = False
        for row in range(start_row, end_row + 1):
            graphic = self.itemForRow(row)
            if not graphic:
                # The item not existing yet indicates the shape of the data has
                # changed, so we should do a full update
                sections_dirty = True
                continue

            self.controller().updateItemFromModel(model, row, self, graphic)

            # The row data changing might have changed which section it's in
            if has_sections and not sections_dirty:
                old_sect = graphic.data(ITEM_SECTION_VALUE)
                new_sect = self._sectionForRow(row)
                sections_dirty = old_sect != new_sect

        if has_sections and sections_dirty:
            # TODO: just move the changed rows, instead of recomputing all
            self._updateSections(update_contents=True)

    def _modelReset(self) -> None:
        self.prepareGeometryChange()
        self._populated = False
        self._updateSections(update_contents=True)
        self.updateGeometry()

    def _rowsInserted(self, _: QtCore.QModelIndex, first: int, last: int
                      ) -> None:
        self.prepareGeometryChange()
        self._updateSections(repopulating=self._populated, update_contents=True)
        self._populated = True
        self.updateGeometry()

    def _rowsRemoved(self, _: QtCore.QModelIndex, first: int, last: int
                     ) -> None:
        self.prepareGeometryChange()
        self._updateSections(repopulating=True, update_contents=True)
        self.updateGeometry()

    # def setPos(self, pos: QtCore.QPointF) -> None:
    #     super().setPos(pos)
    #     self._updateContents()

    @settable(argtype=bool)
    def setUseSections(self, use_sections: bool) -> None:
        self._use_sections = use_sections
        self._updateContents()

    def sectionDataID(self) -> models.DataID:
        return self._section_data_id

    @settable("section_key")
    def setSectionKeyDataID(self, spec: Union[str, tuple[int, str], models.DataID]
                            ) -> None:
        model = self.model()
        self._section_data_id = models.specToDataID(model, spec)
        if self.hasSections():
            self._updateSections(update_contents=True)
        else:
            self._headings.clear()
            self._section_rows.clear()
            self._updateContents()

    def hasSections(self) -> bool:
        return self._use_sections and bool(self.sectionDataID())

    def isReusingItems(self) -> bool:
        return self._reuse_items

    @settable()
    def setReuseItems(self, reuse: bool) -> None:
        self._reuse_items = reuse
        if not reuse:
            self._pool.clear()

    def headingTemplate(self) -> dict[str, Any]:
        return self._heading_template

    @settable("heading_template")
    def setHeadingTemplate(self, template_data: dict[str, Any]) -> None:
        self._heading_template = template_data
        if self.hasSections():
            self._modelReset()

    @settable("h_space")
    def setHorizontalSpacing(self, hspace: float):
        self.matrix().setHorizontalSpacing(hspace)
        self._updateContents()

    @settable("v_space")
    def setVerticalSpacing(self, vspace: float):
        self.matrix().setVerticalSpacing(vspace)
        self._updateContents()

    @settable()
    def setSpacing(self, space: float):
        self.matrix().setSpacing(space)
        self._updateContents()

    def matrix(self) -> layouts.Matrix:
        return self.arrangement()

    def setVisibleRect(self, rect: QtCore.QRectF) -> None:
        pass

    def margins(self) -> QtCore.QMarginsF:
        return self.matrix().margins()

    @settable(argtype=QtCore.QMarginsF)
    def setMargins(self, ms: QtCore.QMarginsF) -> None:
        self.matrix().setMargins(ms)
        self._updateContents()

    def heightForWidth(self, width: float) -> float:
        count = self.rowCount()
        return self.matrix().visualHeight(width, count)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = None
                 ) -> QtCore.QSizeF:
        constraint = constraint or QtCore.QSizeF(-1, -1)
        if which == Qt.PreferredSize:
            matrix = self.matrix()
            cw = constraint.width()
            if cw < 0:
                cw = matrix.minimumColumnWidth()

            h = 0.0
            if self.hasSections():
                for sect_value in self.sectionKeyValues():
                    heading = self.sectionHeading(sect_value)
                    if not heading:
                        continue
                    sz = heading.effectiveSizeHint(which, QtCore.QSizeF(cw, -1))
                    h += sz.height() + self._section_gap

                    row_count = self.sectionRowCount(sect_value)
                    h += matrix.visualHeight(cw, row_count)
            else:
                h = matrix.visualHeight(cw, self.rowCount())
            return QtCore.QSizeF(cw, h)
        return constraint

    def mapRowToVisualRect(self, row: int, count: int) -> QtCore.QRectF:
        width = self.size().width()
        return self.matrix().mapIndexToVisualRect(width, count, row)

    def _sectionForRow(self, row_num: int) -> int|float|str:
        model = self.model()
        data_id = self.sectionDataID()
        index = model.index(row_num, data_id.column)
        sect_val = index.data(data_id.role)
        return sect_val

    def clearItems(self) -> None:
        # for item in self._items.values():
        #     self._deleteGraphic(item)
        self._items.clear()
        self._collectItems()

    def _makeItem(self, key: Union[int, str], row: int) -> Graphic:
        graphic: Optional[Graphic] = None
        if self._reuse_items:
            # Try re-using an item from the cache, otherwise create a new one
            try:
                # Possibly paranoid, but for increased thread safety, pop and
                # catch an exception instead of checking if the cache has an
                # item and then taking it as two separate ops
                graphic = self._pool.pop()
            except IndexError:
                pass

        if graphic is None:
            graphic = self._makeItemFromScratch(key, row)

        graphic.setHighlighted(False)
        self._updateItemFromModel(graphic, row)
        self._items[key] = graphic
        return graphic

    def _makeHeading(self, section_value: int|str) -> Graphic:
        tmpl = self._heading_template
        if tmpl:
            item = core.graphicFromData(tmpl, parent=self)
        else:
            item = controls.PlaceholderGraphic(self)
        item.setZValue(2)
        return item

    def displayMargin(self) -> float:
        return self._display_margin

    def setDisplayMargin(self, margin: float) -> None:
        self._display_margin = margin
        self._updateContents()

    def extraRect(self, rect: QtCore.QRectF) -> QtCore.QRectF:
        rect = QtCore.QRectF(rect)
        dm = self._display_margin
        if dm:
            rect.adjust(0, -dm, 0, dm)
            if rect.y() < 0:
                rect.setY(0)
        return rect

    def _updateSections(self, *, repopulating=False, update_contents=True):
        self._updateVisibility()
        if self.hasSections():
            old_headings = self._headings
            sections = self._section_rows
            sections.clear()
            for row_num in range(self.rowCount()):
                sect_val = self._sectionForRow(row_num)
                assert sect_val is not None
                sections[sect_val].append(row_num)

            new_headings: dict[str, Graphic] = {}
            for sect_value in sections:
                if sect_value in old_headings:
                    item = old_headings.pop(sect_value)
                else:
                    item = self._makeHeading(sect_value)
                new_headings[sect_value] = item
                item.setData(ITEM_SECTION_VALUE, sect_value)

                # Set heading data
                env = {
                    "section": sect_value,
                    "count": self.sectionRowCount(sect_value)
                }
                self.controller().updateTemplateItemFromEnv(
                    self, "heading_template", item, env
                )

            self._headings = new_headings

            for item in old_headings.values():
                item.hide()
                item.setParentItem(None)

        if update_contents:
            self._updateContents(anim_repop=repopulating)

    def sectionKeyValues(self) -> Sequence[int|str]:
        return tuple(self._section_rows.keys())

    def sectionRows(self, section_value: int|str) -> Sequence[int]:
        return tuple(self._section_rows.get(section_value, ()))

    def sectionRowCount(self, section_value: int|str) -> int:
        return len(self._section_rows[section_value])

    def sectionHeading(self, section_value: int|str) -> Optional[Graphic]:
        return self._headings.get(section_value)

    def _updateDataContents(self, *, anim_arrange=False, anim_repop=False
                            ) -> None:
        # t = time.perf_counter()
        if self.scene() is None:
            return
        rect = self.rect()
        vp_rect = self.viewportRect()
        if not vp_rect.isValid():
            return
        vis_rect = self.mapRectFromScene(vp_rect)
        ex_vis_rect = self.extraRect(vis_rect)

        has_sections = self.hasSections()
        if has_sections and not self._headings:
            self._updateSections(update_contents=False)

        existing_keys = set(self._items)
        # print("  existing_keys=", len(existing_keys))
        live_keys: set[int|str] = set()
        matrix = self.matrix()

        if has_sections:
            self._updateSectionContents(vis_rect, live_keys,
                                        anim_arrange=anim_arrange)
        else:
            visible_row_nums = matrix.mapVisualRectToIndexes(
                rect.width(), self.rowCount(), ex_vis_rect
            )
            self._updateItems(visible_row_nums, self.rowCount(),
                              vis_rect, live_keys, QtCore.QPointF(),
                              anim_arrange=anim_arrange, anim_repop=anim_repop)
        # print("  live_keys=", len(live_keys))
        self._recycleKeys(existing_keys - live_keys, anim_repop=anim_repop)
        # print(f"_uDC= {self.objectName()} {time.perf_counter() - t:0.04f}")

    def _updateSectionContents(self, vis_rect: QtCore.QRectF,
                               live_keys: set[int|str], *, anim_arrange=False,
                               anim_repop=False) -> None:
        matrix = self.matrix()
        width = self.size().width()

        y = 0.0
        for sect_value in self.sectionKeyValues():
            heading = self.sectionHeading(sect_value)
            height = heading.effectiveSizeHint(
                Qt.PreferredSize, QtCore.QSizeF(width, -1)
            ).height()
            heading.setPos(0, y)
            heading.resize(width, height)
            # heading.setData(self.data_natural_y, y)
            y += height

            row_numbers = self.sectionRows(sect_value)
            row_count = len(row_numbers)
            matrix_height = matrix.visualHeight(width, len(row_numbers))
            matrix_rect = QtCore.QRectF(0.0, y, width, matrix_height)
            sect_vis_rect = vis_rect.intersected(matrix_rect)
            if sect_vis_rect.isValid():
                offset = QtCore.QPointF(0, y)
                ex_rect = self.extraRect(sect_vis_rect).translated(-offset)
                visible_indices = matrix.mapVisualRectToIndexes(
                    width, row_count, ex_rect
                )
                self._updateItems(
                    visible_indices, row_count, sect_vis_rect, live_keys,
                    offset, row_number_lookup=row_numbers,
                    section_value=sect_value, anim_arrange=anim_arrange,
                    anim_repop=anim_repop
                )
            y += matrix_height + self._section_gap

        vis_top = vis_rect.top()
        if self._sections_sticky and vis_top:
            prev_y = y
            for sect_value in reversed(self.sectionKeyValues()):
                heading = self.sectionHeading(sect_value)
                hy = heading.y()
                hh = heading.size().height()
                if hy < vis_top:
                    sticky_y = min(vis_top, prev_y - hh)
                    heading.setPos(0, sticky_y)
                    break
                prev_y = hy

    def _updateItems(self, visible_indices: Iterable[int], count: int,
                     vis_rect: QtCore.QRectF, live_keys: set[int|str],
                     offset: QtCore.QPointF, *,
                     row_number_lookup: Sequence[int] = None,
                     section_value: int|str = None,
                     anim_arrange=False, anim_repop=False) -> None:
        matrix = self.matrix()
        width = self.size().width()

        for i in visible_indices:
            if row_number_lookup:
                row_number = row_number_lookup[i]
            else:
                row_number = i

            key = self._keyForRow(row_number)
            live_keys.add(key)

            rect = matrix.mapIndexToVisualRect(width, count, i)
            rect.translate(offset)
            item = self._items.get(key)
            if item:
                item.show()
                item.setOpacity(1.0)
                if anim_arrange:
                    item.animateGeometry(rect, view_rect=vis_rect)
                else:
                    item.setGeometry(rect)
            else:
                item = self._makeItem(key, row_number)
                item.setGeometry(rect)
                item.show()
                item.setOpacity(1.0)
                if anim_repop:
                    item.fadeIn()
            item.setData(ITEM_SECTION_VALUE, section_value)

    def _recycle(self, graphic: Graphic, anim_repop=False) -> None:
        if self._reuse_items:
            self._pool.append(graphic)
        super()._recycle(graphic, anim_repop=anim_repop)

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     r = self.rect()
    #     painter.setPen(Qt.blue)
    #     painter.drawRect(r)


@graphictype("views.scrolling_list")
class ListView(ScrollGraphic):
    contentSizeChanged = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._visible = True
        self.setContentItem(DataListGraphic(self))
        self.setClipping(True)

        self.rowHighlighted = self._content.rowHighlighted
        self._content.contentSizeChanged.connect(self._onContentSizeChanged)
        self._content.visibleChanged.connect(self._updateVisibility)

    def setObjectName(self, name: str) -> None:
        super().setObjectName(name)
        self._content.setObjectName(f"{name}_list")

    @path_element(layouts.Matrix)
    def matrix(self) -> layouts.Matrix:
        return self._content.matrix()

    @settable("section_key")
    def setSectionKeyDataID(self, col_id: str|int) -> None:
        self._content.setSectionKeyDataID(col_id)

    def isHoverHighlighting(self) -> bool:
        return self._content.isInteractive()

    @settable()
    def setHoverHighlighting(self, hover_highlight: bool) -> None:
        self._content.setInteractive(hover_highlight)

    def updateGeometry(self) -> None:
        super().updateGeometry()
        self.contentSizeChanged.emit()

    @settable(argtype=bool)
    def setHideWhenEmpty(self, hide_when_empty: bool) -> None:
        self._content.setHideWhenEmpty(hide_when_empty)

    @settable()
    def setVisible(self, visible: bool) -> None:
        self._visible = visible
        self._updateVisibility()

    def shouldBeVisible(self) -> bool:
        return self._visible and self._content.shouldBeVisible()

    def _updateVisibility(self) -> None:
        visible = self.shouldBeVisible()
        cur_vis = self.isVisible()
        if visible != cur_vis:
            super().setVisible(visible)
            self.visibleChanged.emit()

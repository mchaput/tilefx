from __future__ import annotations
from collections import defaultdict
from typing import cast, Any, Collection, Iterable, Optional, Sequence, Union

from PySide2 import QtCore, QtGui, QtWidgets, QtSvg
from PySide2.QtCore import Qt

from . import config, converters, graphics, layouts, models, styling
from .config import settable
from .graphics import graphictype, Graphic


class DataGraphic(Graphic):
    dataChanged = QtCore.Signal(int, int)

    _use_modelReset = False
    _use_dataChanged = False
    _use_rowsInserted = False
    _use_rowsRemoved = False
    _use_rowsMoved = False
    _use_layoutChanged = False

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._model: Optional[QtCore.QAbstractTableModel] = None

    def _disconnectModel(self):
        if self._use_dataChanged:
            self._model.dataChanged.disconnect(self._dataChanged)
        if self._use_modelReset:
            self._model.modelReset.disconnect(self._resetContents)
        if self._use_rowsInserted:
            self._model.rowsInserted.disconnect(self._rowsInserted)
        if self._use_rowsRemoved:
            self._model.rowsRemoved.disconnect(self._rowsRemoved)
        if self._use_rowsMoved:
            self._model.rowsMoved.disconnect(self._rowsMoved)
        if self._use_layoutChanged:
            self._model.layoutChanged.disconnect(self._layoutChanged)

    def _connectModel(self):
        if self._use_dataChanged:
            self._model.dataChanged.connect(self._dataChanged)
        if self._use_modelReset:
            self._model.modelReset.connect(self._resetContents)
        if self._use_rowsInserted:
            self._model.rowsInserted.connect(self._rowsInserted)
        if self._use_rowsRemoved:
            self._model.rowsRemoved.connect(self._rowsRemoved)
        if self._use_rowsMoved:
            self._model.rowsMoved.connect(self._rowsMoved)
        if self._use_layoutChanged:
            self._model.layoutChanged.connect(self._layoutChanged)

    def __del__(self):
        if self._model:
            self._disconnectModel()

    def _dataChanged(self, index1: QtCore.QModelIndex,
                     index2: QtCore.QModelIndex, roles=()) -> None:
        model = self.dataModel()
        if not model:
            raise Exception(f"{self} does not have a data model")

        controller = self.controller()
        for row in range(index1.row(), index2.row() + 1):
            index = model.index(row, 0)
            graphic = self.itemForRow(row)
            controller.updateObjectFromModel(index, graphic)

        self._rowDataChanged(index1.row(), index2.row())

    def dataModel(self) -> QtCore.QAbstractItemModel:
        return self._model

    def setDataModel(self, model: Optional[QtCore.QAbstractItemModel]) -> None:
        if self._model:
            self._disconnectModel()
        self._model = model
        if self._model:
            self._connectModel()

    def clearDataModel(self) -> None:
        self.setDataModel(None)

    def _rowDataChanged(self, start_row: int, end_row: int) -> None:
        pass

    def _resetContents(self) -> None:
        pass

    def _rowsInserted(self, _: QtCore.QModelIndex, first: int, last: int
                      ) -> None:
        pass

    def _rowsRemoved(self, _: QtCore.QModelIndex, first: int, last: int
                     ) -> None:
        pass

    def _rowsMoved(self, _: QtCore.QModelIndex, src_start: int, src_end: int,
                   __: QtCore.QModelIndex, dest_start: int) -> None:
        pass

    def _layoutChanged(self) -> None:
        pass

    def extraVariables(self) -> dict[str, Any]:
        return {"model": self.dataModel()}

    def controller(self) -> Optional[config.DataController]:
        scene = self.scene()
        if not isinstance(scene, graphics.GraphicScene):
            raise TypeError(f"DataGraphic not in GraphicScene: {scene!r}")
        controller = scene.controller()
        if not controller:
            raise ValueError("DataGraphic in scene without controller")
        return controller

    def rowCount(self) -> int:
        model = self.dataModel()
        if model:
            return model.rowCount()
        else:
            return 0


@graphictype("scroll_graphic")
class ScrollGraphic(Graphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._contents: Optional[Graphic] = None
        self._scroll_pos = QtCore.QPointF(0, 0)
        self._vsb_item = graphics.makeProxyItem(
            self, QtWidgets.QScrollBar(Qt.Vertical)
        )
        self._vsb_item.setZValue(100)
        self._match_width = True
        self.geometryChanged.connect(self._updateContents)
        self.verticalScrollBar().valueChanged.connect(self._onVScroll)
        self.setClipping(True)

        self.verticalScrollBar().setSingleStep(16)
        self._updateContents()

    def addChild(self, item: QtWidgets.QGraphicsItem) -> None:
        self.setContentsItem(item)

    def contentsItem(self) -> Graphic:
        return self._contents

    def setContentsItem(self, contents: Graphic) -> None:
        self._contents = contents
        contents.setParentItem(self)

    def dataProxy(self) -> Optional[Graphic]:
        return self.contentsItem()

    def extraVariables(self) -> dict[str, Any]:
        return self.contentsItem().extraVariables()

    def pathElement(self, name: str) -> Optional[QtCore.QObject]:
        if name == "contents":
            return self.contentsItem()

    def verticalScrollBar(self) -> QtWidgets.QScrollBar:
        return self._vsb_item.widget()

    def scrollbarNeeded(self) -> bool:
        return self._contents.size().height() > self.size().height()

    def viewportRect(self) -> QtCore.QRectF:
        # This must return the visible rect in SCENE coordinates
        if self.scrollbarNeeded():
            return self.mapRectToScene(self.rect())
        else:
            return self.parentViewportRect()
        # return self.rect().translated(self._scroll_pos)

    def _updateScrollPosition(self) -> None:
        contents = self.contentsItem()
        if not contents:
            return
        contents.setPos(-self._scroll_pos)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = ...
                 ) -> QtCore.QSizeF:
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

    def _updateContents(self) -> None:
        rect = self.rect()
        width = rect.width()
        page_height = rect.height()
        contents = self.contentsItem()
        if not (self.isVisible() and contents):
            return

        vsb = self.verticalScrollBar()
        vsb_width = vsb.width()
        self._vsb_item.setGeometry(
            QtCore.QRectF(rect.right() - vsb_width, rect.y(),
                          vsb_width, rect.height())
        )
        vsb.setPageStep(int(page_height))

        if self._match_width:
            vp_width = width - vsb_width
            constraint = QtCore.QSizeF(vp_width, -1)
            csize = contents.effectiveSizeHint(Qt.PreferredSize, constraint)
            if csize.height() <= page_height:
                csize.setWidth(width)
            contents.resize(csize)
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

    def wheelEvent(self, event: QtWidgets.QGraphicsSceneWheelEvent) -> None:
        self.scene().sendEvent(self._vsb_item, event)

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     r = self.rect()
    #     painter.setPen(Qt.red)
    #     painter.drawRect(r)


@graphictype("data_layout_graphic")
class DataLayoutGraphic(DataGraphic):
    contentSizeChanged = QtCore.Signal()

    _use_modelReset = True
    _use_dataChanged = True
    _use_rowsInserted = True
    _use_rowsRemoved = True
    _use_rowsMoved = True
    _use_layoutChanged = True

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._item_template: dict[str, Any] = {}
        self._arrangement: Optional[layouts.Arrangement] = None
        self._laying_out = False
        self._animate_resizing = False

        # Child items, by the item's unique key
        self._items: dict[int | str, Graphic] = {}

        self.geometryChanged.connect(self._resized)

    def setObjectName(self, name: str) -> None:
        super().setObjectName(name)
        self._updateLayoutName()

    def _updateLayoutName(self):
        if self._arrangement and not self._arrangement.objectName():
            self._arrangement.setObjectName(f"{self.objectName()}__layout")

    def itemTemplate(self) -> dict[str, Any]:
        return self._item_template

    @settable()
    def setItemTemplate(self, template_data: dict[str, Any]):
        self._item_template = template_data
        self._updateLayoutName()
        self._resetContents()

    def setDataModel(self, model: Optional[QtCore.QAbstractItemModel]) -> None:
        super().setDataModel(model)
        self._updateContents()

    def arrangement(self) -> Optional[layouts.Arrangement]:
        return self._arrangement

    def setArrangement(self, layout: layouts.Arrangement) -> None:
        if self._arrangement:
            self._arrangement.invalidated.disconnect(self._updateContents)
        self._arrangement = layout
        self._arrangement.invalidated.connect(self._updateContents)

    def _rowDataChanged(self, start_row: int, end_row: int) -> None:
        model = self.dataModel()
        for row in range(start_row, end_row + 1):
            graphic = self.itemForRow(row)
            if not graphic:
                raise Exception(f"Received update for nonexistant row {row}")
            self.controller().updateItemFromModel(model, row, self, graphic)

    def _rowsMoved(self, _: QtCore.QModelIndex, src_start: int, src_end: int,
                   __: QtCore.QModelIndex, dest_start: int) -> None:
        print("Rows moved", src_start, src_end, "-", dest_start)
        self._updateContents(anim_arrange=True)

    def _layoutChanged(self) -> None:
        print("Layout changed")
        self._updateContents(anim_arrange=True, anim_repop=True)

    def _resized(self) -> None:
        self._updateContents(anim_arrange=self._animate_resizing)

    def _updateContents(self, *, anim_arrange=False, anim_repop=False,
                        ) -> None:
        if not self.isVisible() or self._laying_out:
            return
        rect = self.rect()
        if not rect.isValid():
            return
        self._laying_out = True
        animated = not self.animationDisabled()
        anim_arrange = anim_arrange and animated
        anim_repop = anim_repop and animated

        self._updateDataContents(anim_arrange=anim_arrange,
                                 anim_repop=anim_repop)
        self._laying_out = False

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = ...
                 ) -> QtCore.QSizeF:
        model = self.dataModel()
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
        self.prepareGeometryChange()
        all_keys = set(self._items)
        live_keys: set[str] = set()
        new_items = {}
        for row_num in range(self.rowCount()):
            key = self._keyForRow(row_num)
            live_keys.add(key)
            item = self._items.get(key)
            if item:
                item.show()
                item.setOpacity(1.0)
            else:
                item = self._makeItem(key, row_num)
                item.show()
                if anim_repop:
                    item.fadeIn()
                else:
                    item.setOpacity(1.0)
            new_items[key] = item

        self.arrangement().layoutItems(self.rect(), list(new_items.values()))
        self._items = new_items
        self._recycleKeys(all_keys - live_keys, anim_repop=anim_repop)
        self.updateGeometry()

    def _collectItems(self, animated=True) -> None:
        anim_repop = animated and not self.animationDisabled()
        all_keys = set(self._items)
        live_keys = set(self._keyForRow(row) for row in range(self.rowCount()))
        self._recycleKeys(all_keys - live_keys, anim_repop=anim_repop)

    def _recycleKeys(self, unused_keys: Collection[str], *, anim_repop=False
                     ) -> None:
        # Recycle items that are no longer visible
        for unused_key in unused_keys:
            unused_item = self._items.pop(unused_key)
            if anim_repop:
                unused_item.fadeOut(
                    callback=lambda g=unused_item: self._recycle(g)
                )
            else:
                self._recycle(unused_item)

    def _recycle(self, graphic: Graphic, anim_repop=False) -> None:
        if anim_repop:
            graphic.fadeOut()
        else:
            graphic.hide()
            graphic.setOpacity(1.0)

    def _keyForRow(self, row_num: int) -> int|float|str:
        model = self.dataModel()
        key_value = model.index(row_num, 0).data(
            models.DataModel.UniqueKeyRole
        )
        if key_value is models.DataModel.NoUniqueKey:
            key_value = row_num
        return key_value

    def itemForRow(self, row_num: int, create=False) -> Optional[Graphic]:
        key = self._keyForRow(row_num)
        item = self._items.get(key)
        if create and not item:
            item = self._makeItem(key, row_num)
        return item

    def pathElement(self, name: str) -> Optional[QtCore.QObject]:
        if name == "layout":
            return self.arrangement()
        return super().pathElement(name)

    def _makeItemFromScratch(self, key: Union[int, str], row: int) -> Graphic:
        tmpl = self._item_template
        if tmpl:
            graphic = graphics.graphicFromData(tmpl, parent=self)
        else:
            graphic = graphics.PlaceholderGraphic(self)
        graphic.setZValue(1)
        return graphic

    def _updateItemFromModel(self, graphic: Graphic, row: int):
        model = self.dataModel()
        self.controller().updateItemFromModel(model, row, self, graphic)

    def _makeItem(self, key: Union[int, str], row: int) -> Graphic:
        graphic = self._makeItemFromScratch(key, row)
        self._updateItemFromModel(graphic, row)
        self._items[key] = graphic
        return graphic

    def showEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self._updateContents()


@graphictype("list_graphic")
class ListGraphic(DataLayoutGraphic):
    # Keys for QGraphicsItem.data()
    data_section_value = 0
    data_natural_y = 1

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        self._section_data_id: Optional[models.DataID] = None
        super().__init__(parent)
        self._heading_template: dict[str, Any] = {}

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

        self._last_width = 0.0

        self._section_rows: defaultdict[str, list[int]] = defaultdict(list)
        self._headings: dict[str, Graphic] = {}
        self._section_gap = 10.0
        self._sections_sticky = True

        self.setHasHeightForWidth(True)

        self.setFlag(self.ItemSendsScenePositionChanges, True)

    def _rowDataChanged(self, start_row: int, end_row: int) -> None:
        has_sections = self.hasSections()
        sect_col = self.sectionDataID()
        model = self.dataModel()
        if not model:
            return

        sections_dirty = False
        for row in range(start_row, end_row + 1):
            graphic = self.itemForRow(row)
            if not graphic:
                raise Exception(f"Received update for nonexistant row {row}")
            self.controller().updateItemFromModel(model, row, self, graphic)

            # The row data changing might have changed which section it's in
            if has_sections and not sections_dirty:
                old_sect = graphic.data(self.data_section_value)
                new_sect = self.sectionForRow(row)
                sections_dirty = old_sect != new_sect

        if has_sections and sections_dirty:
            # TODO: just move the changed rows, instead of recomputing all
            self._updateSections()

    def _resetContents(self) -> None:
        print("Reset contents")
        self.prepareGeometryChange()
        self.clearItems()
        self._populated = False
        self._updateSections()
        self.updateGeometry()
        self.contentSizeChanged.emit()

    def _rowsInserted(self, _: QtCore.QModelIndex, first: int, last: int
                      ) -> None:
        self.prepareGeometryChange()
        self._updateSections(repopulating=self._populated)
        self._populated = True
        self.contentSizeChanged.emit()

    def _rowsRemoved(self, _: QtCore.QModelIndex, first: int, last: int
                     ) -> None:
        self.prepareGeometryChange()
        self._updateSections(repopulating=True)
        self.updateGeometry()
        self.contentSizeChanged.emit()

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange,
                   value: Any) -> Any:
        if change == self.ItemScenePositionHasChanged:
            self._updateContents()
        return super().itemChange(change, value)

    # def setPos(self, pos: QtCore.QPointF) -> None:
    #     super().setPos(pos)
    #     self._updateContents()

    def sectionDataID(self) -> models.DataID:
        return self._section_data_id

    @settable()
    def setSectionDataID(self, spec: Union[str, tuple[int, str], models.DataID]
                         ) -> None:
        model = self.dataModel()
        self._section_data_id = models.specToDataID(model, spec)
        if self.hasSections():
            self._updateSections()
        else:
            self._headings.clear()
            self._section_rows.clear()
            self._updateContents()

    def hasSections(self) -> bool:
        return bool(self.sectionDataID())

    def isReusingItems(self) -> bool:
        return self._reuse_items

    @settable()
    def setReuseItems(self, reuse: bool) -> None:
        self._reuse_items = reuse
        if not reuse:
            self._pool.clear()

    def headingTemplate(self) -> dict[str, Any]:
        return self._heading_template

    @settable()
    def setHeadingTemplate(self, template_data: dict[str, Any]) -> None:
        self._heading_template = template_data
        if self.hasSections():
            self._resetContents()

    @settable("h_spacing")
    def setHorizontalSpacing(self, hspace: float):
        self.matrix().setHorizontalSpacing(hspace)
        self._updateContents(anim_repop=True)

    @settable("v_spacing")
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

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = ...
                 ) -> QtCore.QSizeF:
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
                    h += sz.height()

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
        model = self.dataModel()
        data_id = self.sectionDataID()
        return model.index(row_num, data_id.column).data(data_id.role)

    def clearItems(self) -> None:
        # for item in self._items.values():
        #     self._deleteGraphic(item)
        self._items.clear()

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

        self._updateItemFromModel(graphic, row)
        self._items[key] = graphic
        return graphic

    def _makeHeading(self, section_value: int|str) -> Graphic:
        tmpl = self._heading_template
        if tmpl:
            item = graphics.graphicFromData(tmpl, parent=self)
        else:
            item = graphics.PlaceholderGraphic(self)
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
        if not self.hasSections():
            return

        old_headings = self._headings
        sections = self._section_rows
        sections.clear()
        for row_num in range(self.rowCount()):
            sect_val = self._sectionForRow(row_num)
            sections[sect_val].append(row_num)

        new_headings: dict[str, Graphic] = {}
        for sect_value in sections:
            if sect_value in old_headings:
                item = old_headings[sect_value]
            else:
                item = self._makeHeading(sect_value)
            new_headings[sect_value] = item
            item.setData(self.data_section_value, sect_value)
            # Set heading data
            env = {
                "section": sect_value,
                "count": self.sectionRowCount(sect_value)
            }
            self.controller().updateTemplateItemFromEnv(
                "heading_template", env, self, item
            )

        self._headings = new_headings

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
        rect = self.rect()
        vis_rect = self.mapRectFromScene(self.viewportRect())
        ex_vis_rect = self.extraRect(vis_rect)

        has_sections = self.hasSections()
        if has_sections and not self._headings:
            self._updateSections(update_contents=False)

        existing_keys = set(self._items)
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

        # print("live_keys=", len(live_keys))
        self._recycleKeys(existing_keys - live_keys, anim_repop=anim_repop)

    def _updateSectionContents(self, vis_rect: QtCore.QRectF,
                               live_keys: set[int|str], *, anim_arrange=False,
                               anim_repop=False) -> None:
        matrix = self.matrix()
        width = self.size().width()

        y = 0.0
        for sect_value in self.sectionKeyValues():
            heading = self.sectionHeading(sect_value)
            if width != self._last_width:
                height = heading.effectiveSizeHint(
                    Qt.PreferredSize, QtCore.QSizeF(width, -1)
                ).height()
            else:
                height = heading.size().height()
            heading.setPos(0, y)
            heading.resize(width, height)
            heading.setData(self.data_natural_y, y)
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

        self._last_width = width

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
            item.setData(self.data_section_value, section_value)

    def _recycle(self, graphic: Graphic, anim_repop=False) -> None:
        if self._reuse_items:
            self._pool.append(graphic)
        super()._recycle(graphic, anim_repop=anim_repop)

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     r = self.rect()
    #     painter.setPen(Qt.red)
    #     painter.drawRect(r)


@graphictype("list_view")
class ListView(ScrollGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._contents = ListGraphic(self)
        self.contentSizeChanged = self._contents.contentSizeChanged
        self.setClipping(True)

    def pathElement(self, name: str) -> Optional[QtCore.QObject]:
        if name == "matrix":
            return self._contents.matrix()
        return super().pathElement(name)

    def setSectionKey(self, col_id: str|int) -> None:
        self._contents.setSectionDataID(col_id)

from __future__ import annotations
import enum
import time
from collections import defaultdict
from typing import cast, Any, Collection, Iterable, Optional, Sequence, Union

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .. import config, models, util
from ..config import settable
from . import core, containers, converters, controls, layouts, themes
from .core import graphictype, path_element, Graphic, DataGraphic


# Keys for QGraphicsItem.data()
ITEM_KEY_VALUE = 21
ITEM_ROW_NUM = 22
ITEM_SECTION_VALUE = 134


class UpdateReason(enum.Enum):
    no_update = enum.auto()
    scene_rect = enum.auto()
    viewport = enum.auto()
    resize = enum.auto()
    model_change = enum.auto()
    show = enum.auto()
    settings = enum.auto()
    remeasure = enum.auto()
    wake = enum.auto()


class DataItemPool:
    def __init__(self, name: str = None):
        self.name = name
        self._pool: list[core.Graphic] = []
        self._item_template: dict[str, Any] | core.GraphicTemplate = {}
        self._prewarm_count = 0
        self._prewarm_batch_size = 50
        self._prewarm_batch_delay = 250
        self._batch_timer: Optional[QtCore.QTimer] = None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name} {id(self):x}>"

    def __len__(self) -> int:
        return len(self._pool)

    def pop(self, parent: QtWidgets.QGraphicsItem,
            controller: config.DataController) -> core.Graphic:
        # Doing this is more thread-safe than checking the length and then
        # popping
        try:
            item = self._pool.pop()
        except IndexError:
            item = self._makeItemFromScratch(parent, controller)

        item.setData(ITEM_KEY_VALUE, None)
        item.setData(ITEM_ROW_NUM, None)
        if parent:
            item.setParentItem(parent)
        item.setHighlighted(False)
        item.show()
        item.setOpacity(1.0)
        return item

    def _makeItemFromScratch(self, parent: QtWidgets.QGraphicsItem,
                             controller: config.DataController) -> core.Graphic:
        tmpl = self._item_template
        if tmpl:
            graphic = core.graphicFromData(tmpl, parent=parent,
                                           controller=controller)
        else:
            graphic = controls.PlaceholderGraphic()
        graphic.setZValue(1)
        # graphic.setData(ITEM_KEY_VALUE, unique_value)
        # graphic.setData(ITEM_ROW_NUM, row)
        # graphic.setLocalVariable("row_num", row)
        # graphic.setLocalVariable("unique_id", unique_value)
        return graphic

    def push(self, item: core.Graphic) -> None:
        item.setParentItem(None)
        self._pool.append(item)

    def setItemTemplate(self, template_data: dict[str, Any]):
        self._item_template = template_data
        self._pool.clear()
        self._prewarmPool()

    def setPrewarmPoolSize(self, count: int) -> None:
        self._prewarm_count = count
        self._prewarmPool()

    def _prewarmBatchTimer(self) -> QtCore.QTimer:
        if self._batch_timer is None:
            self._batch_timer = QtCore.QTimer()
            self._batch_timer.timeout.connect(self._prewarmPool)
            self._batch_timer.setInterval(self._prewarm_batch_delay)
            self._batch_timer.setSingleShot(True)
        return self._batch_timer

    def _prewarmPool(self) -> None:
        target = self._prewarm_count
        if not (self._item_template and target):
            return

        current = len(self._pool)
        batch_target = min(target, current + self._prewarm_batch_size)
        # t = time.perf_counter()
        for _ in range(current, batch_target):
            self._pool.append(self._makeItemFromScratch(None, None))
        # print("Prewarm", self.name, batch_target, target,
        #       time.perf_counter() - t)
        if batch_target < target:
            self._prewarmBatchTimer().start()


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
        self._prev_scene_rect = QtCore.QRectF()
        self._prev_viewport = QtCore.QRectF()
        # self._prev_size = QtCore.QSizeF(-1, -1)
        # self._scene_rect_changed = False
        self._reuse_items = True
        self._hide_when_empty = False
        self._visible = True
        self._interactive = False
        self._hilite_row = -1
        self._measure_data_ids: Sequence[models.DataID] = ()
        self._measurements: dict[models.DataID, float] = {}
        self._dynamic_item_width_expr: Optional[config.Expr] = None
        self._value_font_map: dict[models.DataID, QtGui.QFont] = {}

        self._hilite = core.RectangleGraphic(self)
        self._hilite.setCornerRadius(4)
        self._hilite.setFillColor(themes.ThemeColor.highlight)
        self._hilite.setOpacity(0.25)
        self._hilite.hide()

        self._arrangement: Optional[layouts.Arrangement] = None
        self._laying_out = False
        self._animate_resizing = False

        self._item_pool = DataItemPool()
        # Live items, by the item's unique key
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

    # def setGeometry(self, rect: QtCore.QRectF) -> None:
    #     super().setGeometry(rect)
    #     size = rect.size()
    #     if self._scene_rect_changed or size != self._prev_size:
    #         self._scene_rect_changed = False
    #         self._prev_size = size
    #         self._updateContents()

    def setObjectName(self, name: str) -> None:
        super().setObjectName(name)
        if self._item_pool.name is None:
            self._item_pool.name = name

    @settable("measure_values")
    def setMeasureDataIDs(self, data_ids: Sequence[str | models.DataID]
                          ) -> None:
        model = self.model()
        self._measure_data_ids = tuple(
            models.specToDataID(model, spec) for spec in data_ids
        )
        self._remeasure()

    @settable("dynamic_item_width")
    def setDynamicItemWidthExpr(self, expr: str | dict | config.Expr) -> None:
        if isinstance(expr, (str, dict)):
            expr = config.PythonExpr.fromData(expr)
        self._dynamic_item_width_expr = expr

    @settable()
    def setValueFontMap(self, value_font_map: dict[str, QtGui.QFont]) -> None:
        self._value_font_map = value_font_map
        self._remeasure()

    def _remeasure(self) -> None:
        if not self._measure_data_ids:
            return

        model = self.model()
        font = self.font()
        _toDataID = models.specToDataID
        vfonts = {
            _toDataID(model, spec): converters.fontConverter(font_data, font)
            for spec, font_data in self._value_font_map.items()
        }

        if not model:
            return
        count = model.rowCount()
        if not count:
            return

        # print("measuring", self.objectName())
        # t = time.perf_counter()
        for data_id in self._measure_data_ids:
            vfont = vfonts[data_id]
            fm = QtGui.QFontMetricsF(vfont)
            max_w = 0.0
            for row in range(count):
                index = model.index(row, data_id.column)
                text = index.data(data_id.role)
                w = fm.horizontalAdvance(text)
                max_w = max(max_w, w)
            self._measurements[data_id] = max_w
        # print(f"Measure {self.objectName()}: {time.perf_counter() - t:0.04f}")

    def localEnv(self) -> dict[str, Any]:
        env = super().localEnv()
        env.update(
            measured=self.valueMeasurement,
        )
        return env

    def valueMeasurement(self, spec: str | models.DataID) -> float:
        model = self.model()
        if not model:
            raise Exception(f"No model in {self}")
        data_id = models.specToDataID(model, spec)
        return self._measurements.get(data_id, 0.0)

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange,
                   value: Any) -> Any:
        if change == self.ItemScenePositionHasChanged:
            self._updateView(UpdateReason.scene_rect)
        elif change == self.ItemSceneChange:
            self.sceneChanged(self.scene(), value)
        return super().itemChange(change, value)

    def sceneChanged(self, old_scene: QtWidgets.QGraphicsScene,
                     new_scene: QtWidgets.QGraphicsScene) -> None:
        self._invalidateCaches()
        if old_scene and isinstance(old_scene, core.GraphicScene):
            old_scene.viewportChanged.disconnect(self.viewportChanged)
        if isinstance(new_scene, core.GraphicScene):
            new_scene.viewportChanged.connect(self.viewportChanged)

    def resizeEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        super().resizeEvent(event)
        self.contentSizeChanged.emit()
        self._updateView(UpdateReason.resize,
                         anim_arrange=self._animate_resizing)

    def _rowsInserted(self, _: QtCore.QModelIndex, first: int, last: int
                      ) -> None:
        if self._hide_when_empty:
            self._updateVisibility()
        self._remeasure()
        self.updateGeometry()
        self._updateView(UpdateReason.model_change)

    def _rowsRemoved(self, _: QtCore.QModelIndex, first: int, last: int
                     ) -> None:
        if self._hide_when_empty:
            self._updateVisibility()
        self._remeasure()
        self.updateGeometry()
        self._updateView(UpdateReason.model_change)

    def _modelReset(self) -> None:
        if self._hide_when_empty:
            self._updateVisibility()
        self._invalidateCaches()
        self._remeasure()
        self.updateGeometry()
        self._updateView(UpdateReason.model_change)

    def _rowDataChanged(self, start_row: int, end_row: int) -> None:
        model = self.model()
        controller = self.controller()
        if not controller:
            return

        local_env = self.localEnv()
        for row in range(start_row, end_row + 1):
            graphic = self.itemForRow(row)
            if not graphic:
                raise Exception(f"Update for nonexistant row {row}")
            self._updateItemFromModel(graphic, row, model=model,
                                      controller=controller,
                                      local_env=local_env)

        self._remeasure()

    def _invalidateCaches(self):
        self._prev_viewport = self._prev_scene_rect = QtCore.QRectF()

    def _onLayoutChanged(self):
        self._updateView(UpdateReason.model_change)

    def _rowsMoved(self, _: QtCore.QModelIndex, src_start: int, src_end: int,
                   __: QtCore.QModelIndex, dest_start: int) -> None:
        print("Rows moved", src_start, src_end, "-", dest_start)
        self._updateView(UpdateReason.model_change, anim_arrange=True)

    def _layoutChanged(self) -> None:
        print("Layout changed")
        self._updateView(UpdateReason.model_change, anim_arrange=True, anim_repop=True)

    @classmethod
    def templateKeys(cls) -> Sequence[str]:
        return ("item_template",)

    def setObjectName(self, name: str) -> None:
        super().setObjectName(name)
        self._updateLayoutName()

    def textToCopy(self) -> str:
        items = self._items.values()
        return "; ".join(item.textToCopy() for item in items)

    def _updateLayoutName(self):
        if self._arrangement and not self._arrangement.objectName():
            self._arrangement.setObjectName(f"{self.objectName()}__layout")

    @settable("item_template")
    def setItemTemplate(self, template_data: dict[str, Any]):
        self._item_pool.setItemTemplate(template_data)
        self._updateLayoutName()
        self._modelReset()

    @path_element(layouts.Arrangement)
    def arrangement(self) -> Optional[layouts.Arrangement]:
        return self._arrangement

    def setArrangement(self, layout: layouts.Arrangement) -> None:
        if self._arrangement:
            self._arrangement.invalidated.disconnect(lambda: self._onLayoutChanged)
        self._arrangement = layout
        self._arrangement.invalidated.connect(self._onLayoutChanged)

    def countForSize(self, size: QtCore.QSizeF) -> int:
        total = self.rowCount()
        arng = self.arrangement()
        if isinstance(arng, layouts.Matrix):
            count = min(total, arng.countForSize(size))
        else:
            rect = self.rect()
            rect.setSize(size)
            count = sum(int(rect.contains(item.geometry()))
                        for item in self._items.values())
        return count

    def snappedHeight(self, y: float) -> float:
        # Given a y value, returns the y value snapped to the bottom of the
        # corresponding row. Since DataLayout supports arbitrary layouts, it
        # can't snap and just returns the input. Subclasses that enforce a
        # regular layout can override this to do snapping.
        return y

    def setItemPool(self, pool: DataItemPool) -> None:
        self._item_pool = pool

    # def setGeometry(self, rect: QtCore.QRectF) -> None:
    #     super().setGeometry(rect)
    #     self._updateContents(anim_arrange=self._animate_resizing)

    def awaken(self) -> None:
        super().awaken()
        self._updateView(UpdateReason.wake)

    def _updateView(self, reason: UpdateReason, *, anim_arrange=False,
                    anim_repop=False) -> None:
        scene = self.scene()

        # Before checking visibility, update it
        if reason == UpdateReason.model_change and self._hide_when_empty:
            self._updateVisibility()

        if reason not in (UpdateReason.resize, UpdateReason.wake) and \
                not (scene and self.isVisible()):
            return
        if self._laying_out:
            return

        sr = self.mapRectToScene(self.rect())
        vp = self.viewportRect()
        if reason == UpdateReason.scene_rect and sr == self._prev_scene_rect:
            return
        if reason == UpdateReason.viewport and vp == self._prev_viewport:
            return
        self._prev_scene_rect = sr
        self._prev_viewport = vp

        # t = perf_counter()
        # self.prepareGeometryChange()
        # print("update", self.objectName(), reason, self.viewportRect())
        self._laying_out = True
        animated = not self.animationDisabled()
        anim_arrange = anim_arrange and animated
        # anim_repop = anim_repop and animated
        anim_repop = False

        update_data = reason == UpdateReason.model_change
        self._updateDataContents(anim_arrange=anim_arrange,
                                 anim_repop=anim_repop, update_data=update_data)
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

    # def _updateChildren(self, *, anim_arrange=False):
    #     self.arrangement().layoutItems(self.rect(),
    #                                    list(self.childGraphics()),
    #                                    animated=anim_arrange)

    def _updateDataContents(self, *, anim_arrange=False, anim_repop=False,
                            update_data=True):
        all_keys = set(self._items)
        live_keys: set[str] = set()
        old_items = self._items
        new_items: dict[int|str, Graphic] = {}
        local_env = self.localEnv()
        for row_num in range(self.rowCount()):
            key = self._keyForRow(row_num)
            live_keys.add(key)
            item = old_items.get(key)
            if item:
                item.setOpacity(1.0)
                item.show()
            else:
                item = self._makeItem(key)
                item.show()
                if anim_repop:
                    item.fadeIn()
                else:
                    item.setOpacity(1.0)

            if update_data or item.data(ITEM_KEY_VALUE) != key:
                # print("-self=", self.objectName(), "updating", key)
                self._updateItemFromModel(item, row_num, local_env=local_env)
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
        graphic.hide()
        graphic.setOpacity(1.0)
        graphic.setParentItem(None)
        if self._reuse_items:
            self._item_pool.push(graphic)

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
            item = self._makeItem(key)
            self._updateItemFromModel(item, row_num, local_env=self.localEnv())
        return item

    def liveItems(self) -> Iterable[Graphic]:
        return self._items.values()

    def _updateItemFromModel(self, graphic: Graphic, row: int,
                             local_env: dict[str, Any] = None,
                             model: QtCore.QAbstractItemModel = None,
                             controller: config.DataController = None) -> None:
        model = model or self.model()
        controller = controller or self.controller()
        controller.updateItemFromModel(model, row, self, graphic,
                                       extra_env=local_env)
        unique_value = self._keyForRow(row)
        graphic.setData(ITEM_KEY_VALUE, unique_value)
        graphic.setData(ITEM_ROW_NUM, row)
        graphic.setLocalVariable("row_num", row)
        graphic.setLocalVariable("unique_id", unique_value)
        graphic.setObjectName(f"{model.objectName()}_{row}")

    def _makeItem(self, key: Union[int, str]) -> Graphic:
        controller = self.controller()
        graphic = self._item_pool.pop(self, controller)
        self._items[key] = graphic
        return graphic

    def showEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self._updateView(UpdateReason.show)

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
        if self._hide_when_empty and not self.model().rowCount():
            return False
        return self._visible

    def _updateVisibility(self) -> None:
        visible = self.shouldBeVisible()
        cur_vis = self.isVisible()
        if visible != cur_vis:
            super().setVisible(visible)
            self.visibleChanged.emit()


@graphictype("views.list")
class DataListGraphic(DataLayoutGraphic):
    rowHighlighted = QtCore.Signal(int)

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

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        self._section_data_id: Optional[models.DataID] = None
        super().__init__(parent)
        self._visible = True

        self._sel_start = self._sel_end = -1
        self._selecting = False
        self._selection_corner_radius = 4.0
        self._selecting = False

        self._heading_template: dict[str, Any] = {}
        self._section_rows: defaultdict[str, list[int]] = defaultdict(list)
        self._headings: dict[str, Graphic] = {}
        self._section_gap = 10.0
        self._sections_sticky = True
        self._use_sections = True
        self._copyable_item_text_expr: Optional[config.PythonExpr] = None

        matrix = layouts.Matrix()
        matrix.setMinimumColumnWidth(100)
        matrix.setColumnStretch(True)
        matrix.setMargins(QtCore.QMarginsF(10, 10, 10, 10))
        self.setArrangement(matrix)

        self._populated = False
        self._display_margin = 0.0

        self.setHasHeightForWidth(True)
        self.setFlag(self.ItemSendsScenePositionChanges, True)
        self.setSelectable(True)

    def viewportChanged(self) -> None:
        self._updateSections(UpdateReason.viewport)

    @classmethod
    def templateKeys(cls) -> Sequence[str]:
        return "item_template", "heading_template"

    def _rowDataChanged(self, start_row: int, end_row: int) -> None:
        has_sections = self.hasSections()
        # sect_col = self.sectionDataID()
        model = self.model()
        if not model:
            return

        controller = self.controller()
        sections_dirty = False
        for row in range(start_row, end_row + 1):
            graphic = self.itemForRow(row)
            if not graphic:
                # The item not existing yet indicates the shape of the data has
                # changed, so we should do a full update
                sections_dirty = True
                continue

            self._updateItemFromModel(graphic, row, model=model,
                                      controller=controller)

            # The row data changing might have changed which section it's in
            if has_sections and not sections_dirty:
                old_sect = graphic.data(ITEM_SECTION_VALUE)
                new_sect = self._sectionForRow(row)
                sections_dirty = old_sect != new_sect

        self._remeasure()
        if has_sections and sections_dirty:
            # TODO: just move the changed rows, instead of recomputing all
            self._updateSections(UpdateReason.model_change,
                                 update_contents=True)

    def _modelReset(self) -> None:
        self.prepareGeometryChange()
        self._populated = False
        self._remeasure()
        self._invalidateCaches()
        self._updateSections(UpdateReason.model_change, update_contents=True)
        self.updateGeometry()

    def _rowsInserted(self, _: QtCore.QModelIndex, first: int, last: int
                      ) -> None:
        self.prepareGeometryChange()
        self._remeasure()
        self._updateSections(UpdateReason.model_change,
                             repopulating=self._populated, update_contents=True)
        self._populated = True
        self.updateGeometry()

    def _rowsRemoved(self, _: QtCore.QModelIndex, first: int, last: int
                     ) -> None:
        self.prepareGeometryChange()
        self._remeasure()
        self._updateSections(UpdateReason.model_change, repopulating=True,
                             update_contents=True)
        self.updateGeometry()

    def _posToRowAndRect(self, pos: QtCore.QPointF
                         ) -> tuple[int, QtCore.QRectF]:
        width = self.rect().width()
        count = self.rowCount()
        matrix = self.matrix()
        row_num = matrix.mapPointToIndex(width, count, pos)
        row_num = max(0, min(row_num, self.rowCount()))
        item_rect = matrix.mapIndexToVisualRect(width, count, row_num)
        return row_num, item_rect

    def setItemSelectionEnd(self, end: int) -> None:
        self._sel_end = end
        self.update()

    def setItemSelectionRange(self, start: int, end: int) -> None:
        self._sel_start = start
        self._sel_end = end
        self.update()

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent
                        ) -> None:
        event.accept()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)
        shift = bool(mods & Qt.ShiftModifier)
        # alt = bool(mods & Qt.AltModifier)
        pos = event.pos()
        row_num, item_rect = self._posToRowAndRect(pos)

        if self._sel_start >= 0 and shift:
            self.setItemSelectionEnd(row_num)
        else:
            self.setItemSelectionRange(row_num, row_num)
        self._selecting = True
        self.scene().clearSelection()
        self.setSelected(True)
        self.update()

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent
                       ) -> None:
        if self._selecting:
            pos = event.pos()
            row_num, _ = self._posToRowAndRect(pos)
            self.setItemSelectionEnd(row_num)
            self.update()

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent
                          ) -> None:
        event.accept()
        self._selecting = False

    # def setPos(self, pos: QtCore.QPointF) -> None:
    #     super().setPos(pos)
    #     self._updateContents()

    def localEnv(self) -> dict[str, Any]:
        env = super().localEnv()
        env.update(
            row_height=self._arrangement.rowHeight(),
        )
        return env

    @settable(argtype=bool)
    def setUseSections(self, use_sections: bool) -> None:
        self._use_sections = use_sections
        self._updateView(UpdateReason.settings)

    def sectionDataID(self) -> models.DataID:
        return self._section_data_id

    @settable("section_key")
    def setSectionKeyDataID(self, spec: Union[str, tuple[int, str], models.DataID]
                            ) -> None:
        model = self.model()
        self._section_data_id = models.specToDataID(model, spec)
        if self.hasSections():
            self._updateSections(UpdateReason.settings, update_contents=True)
        else:
            self._headings.clear()
            self._section_rows.clear()
            self._updateView(UpdateReason.settings)

    @settable("on_copy_item_text")
    def setCopyableItemTextExpression(self, expr: config.PythonExpr) -> None:
        if isinstance(expr, (str, dict)):
            expr = config.PythonExpr.fromData(expr)
        self._copyable_item_text_expr = expr

    def textToCopy(self) -> str:
        return "; ".join(self.itemTexts())

    def _rangeToCopy(self) -> Iterable[int]:
        if self.isSelected() and self._sel_start >= 0:
            rng = range(self._sel_start, self._sel_end + 1)
        else:
            rng = range(self.rowCount())
        return rng

    def itemTexts(self) -> Iterable[str]:
        model = self.model()
        if not model or not model.rowCount():
            return
        expr = self._copyable_item_text_expr
        if not expr:
            return

        controller = self.controller()
        env = controller.globalEnv().copy() if controller else {}
        env.update(self.localEnv())
        mra = models.ModelRowAdapter(model, 0)
        env.update({
            "model": model,
            "row_num": 0,
            "item": mra
        })

        for row_num in self._rangeToCopy():
            env["row_num"] = row_num
            mra.row = row_num
            text = expr.evaluate(None, env)
            yield text

    def snappedHeight(self, y: float) -> float:
        return self.matrix().snappedHeight(y)

    def hasSections(self) -> bool:
        return self._use_sections and bool(self.sectionDataID())

    def isReusingItems(self) -> bool:
        return self._reuse_items

    @settable()
    def setReuseItems(self, reuse: bool) -> None:
        self._reuse_items = reuse

    @settable("item_template")
    def setItemTemplate(self, template_data: dict[str, Any] | core.GraphicTemplate):
        self._item_pool.setItemTemplate(template_data)
        self._modelReset()

    def headingTemplate(self) -> dict[str, Any] | core.GraphicTemplate:
        return self._heading_template

    @settable("heading_template")
    def setHeadingTemplate(self, template_data: dict[str, Any] | core.GraphicTemplate) -> None:
        self._heading_template = template_data
        if self.hasSections():
            self._modelReset()

    @settable("h_space")
    def setHorizontalSpacing(self, hspace: float):
        self.matrix().setHorizontalSpacing(hspace)
        self._updateView(UpdateReason.settings)

    @settable("v_space")
    def setVerticalSpacing(self, vspace: float):
        self.matrix().setVerticalSpacing(vspace)
        self._updateView(UpdateReason.settings)

    @settable()
    def setSpacing(self, space: float):
        self.matrix().setSpacing(space)
        self._updateView(UpdateReason.settings)

    def _remeasure(self) -> None:
        super()._remeasure()
        self._updateDynamicWidth()

    def _updateDynamicWidth(self) -> None:
        if self._dynamic_item_width_expr:
            value = self._evaluateExpr(self._dynamic_item_width_expr)
            matrix = self.matrix()
            if value and value != matrix.minimumColumnWidth():
                matrix.setMinimumColumnWidth(value)
                self._updateView(UpdateReason.remeasure)

    # def dataModel(self) -> models.DataModel:
    #     model = self.model()
    #     if isinstance(model, QtCore.QSortFilterProxyModel):
    #         model = model.sourceModel()
    #     if not isinstance(model, models.DataModel):
    #         raise TypeError(f"Can't set measure columns on {model}")
    #     return model

    @path_element(layouts.Matrix)
    def matrix(self) -> layouts.Matrix:
        return self.arrangement()

    def setVisibleRect(self, rect: QtCore.QRectF) -> None:
        pass

    def margins(self) -> QtCore.QMarginsF:
        return self.matrix().margins()

    @settable(argtype=QtCore.QMarginsF)
    def setMargins(self, ms: QtCore.QMarginsF) -> None:
        self.matrix().setMargins(ms)
        self._updateView(UpdateReason.settings)

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
        self._updateView(UpdateReason.settings)

    def extraRect(self, rect: QtCore.QRectF) -> QtCore.QRectF:
        rect = QtCore.QRectF(rect)
        dm = self._display_margin
        if dm:
            rect.adjust(0, -dm, 0, dm)
            if rect.y() < 0:
                rect.setY(0)
        return rect

    def _updateSections(self, reason: UpdateReason, *, repopulating=False,
                        update_contents=True) -> None:
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
            self._updateView(reason, anim_repop=repopulating)

    def sectionKeyValues(self) -> Sequence[int|str]:
        return tuple(self._section_rows.keys())

    def sectionRows(self, section_value: int|str) -> Sequence[int]:
        return tuple(self._section_rows.get(section_value, ()))

    def sectionRowCount(self, section_value: int|str) -> int:
        return len(self._section_rows[section_value])

    def sectionHeading(self, section_value: int|str) -> Optional[Graphic]:
        return self._headings.get(section_value)

    def _visibleRowNums(self, width: float) -> Iterable[int]:
        vp_rect = self.viewportRect()  # In scene coordinates
        # print("  ", self.objectName(), "vp=", vp_rect)
        if not vp_rect.isValid():
            return ()
        vis_rect = self.mapRectFromScene(vp_rect)
        ex_vis_rect = self.extraRect(vis_rect)
        matrix = self.matrix()
        return matrix.mapVisualRectToIndexes(
            width, self.rowCount(), ex_vis_rect
        )

    def _updateDataContents(self, *, anim_arrange=False, anim_repop=False,
                            update_data=True) -> None:
        if self.scene() is None:
            return
        rect = self.rect()
        vp_rect = self.viewportRect()  # In scene coordinates
        if not vp_rect.isValid():
            return
        vis_rect = self.mapRectFromScene(vp_rect)

        has_sections = self.hasSections()
        if has_sections and not self._headings:
            self._updateSections(UpdateReason.no_update, update_contents=False)

        existing_keys = set(self._items)
        live_keys: set[int|str] = set()
        if has_sections:
            self._updateSectionItems(
                vis_rect, live_keys, anim_arrange=anim_arrange,
                update_data=update_data
            )
        else:
            visible_row_nums = self._visibleRowNums(rect.width())
            self._updateItems(visible_row_nums, self.rowCount(),
                              vis_rect, live_keys, QtCore.QPointF(),
                              anim_arrange=anim_arrange, anim_repop=anim_repop,
                              update_data=update_data)
        self._recycleKeys(existing_keys - live_keys, anim_repop=anim_repop)

    def _updateSectionItems(self, vis_rect: QtCore.QRectF,
                            live_keys: set[int|str], *, anim_arrange=False,
                            anim_repop=False, update_data=True) -> None:
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
                    anim_repop=anim_repop, update_data=update_data
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
                     anim_arrange=False, anim_repop=False,
                     update_data=True) -> None:
        matrix = self.matrix()
        width = self.size().width()
        local_env = self.localEnv()

        # t = time.perf_counter()
        updated = 0
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
                item = self._makeItem(key)
                item.setGeometry(rect)
                item.show()
                item.setOpacity(1.0)
                if anim_repop:
                    item.fadeIn()

            if update_data or item.data(ITEM_KEY_VALUE) != key:
                # print("self=", self.objectName(), "updating", key)
                self._updateItemFromModel(item, row_number, local_env=local_env)
                updated += 1

            item.setData(ITEM_SECTION_VALUE, section_value)
        # print(f"ITEMS {self.objectName()} {time.perf_counter() - t:0.04f} {updated}")

    def _selectionPath(self, sel_start: int, sel_end: int
                       ) -> QtGui.QPainterPath:
        matrix = self.matrix()
        width = self.rect().width()
        count = self.rowCount()
        sel_rad = self._selection_corner_radius

        sel_path = QtGui.QPainterPath()
        start_col, start_row = matrix.mapIndextoCell(width, count, sel_start)
        start_rect = matrix.mapIndexToVisualRect(width, count, sel_start)
        end_col, end_row = matrix.mapIndextoCell(width, count, sel_end)
        end_rect = matrix.mapIndexToVisualRect(width, count, sel_end)

        if start_row == end_row:
            sel_rect = QtCore.QRectF(start_rect.topLeft(),
                                     end_rect.bottomRight())
            sel_path.addRoundedRect(sel_rect, sel_rad, sel_rad)
        else:
            has_middle = end_row > start_row + 1
            no_mid = not has_middle
            top_rect = QtCore.QRectF(
                start_rect.x(), start_rect.y(),
                width - start_rect.x(), start_rect.height() + 2
            )
            bl_rad = (
                sel_rad if no_mid and start_rect.right() > end_rect.right()
                else 0
            )
            br_rad = (
                sel_rad if no_mid and start_rect.left() > end_rect.left()
                else 0
            )
            top_path = util.roundedRectPath(
                top_rect, tl_radius=sel_rad, tr_radius=sel_rad,
                bl_radius=bl_rad, br_radius=br_rad
            )
            sel_path.addPath(top_path)
            # top_path = util.roundedRectPath()

            if has_middle:
                middle_rect = QtCore.QRectF(
                    0, start_rect.bottom(),
                    width, end_rect.top() - start_rect.bottom()
                )
                tl_rad = sel_rad if start_rect.x() > 0 else 0
                br_rad = sel_rad if end_rect.right() < width else 0
                middle_path = util.roundedRectPath(
                    middle_rect, tl_radius=tl_rad, br_radius=br_rad
                )
                sel_path = sel_path.united(middle_path)

            bottom_rect = QtCore.QRectF(
                0, end_rect.y() - 2, end_rect.right(), end_rect.height() + 2
            )

            tl_rad = sel_rad if no_mid and start_rect.left() > 0 else 0
            tr_rad = (sel_rad if no_mid and end_rect.right() < start_rect.left()
                      else 0)
            bottom_path = util.roundedRectPath(
                bottom_rect, bl_radius=sel_rad, br_radius=sel_rad,
                tl_radius=tl_rad, tr_radius=tr_rad,
            )
            sel_path = sel_path.united(bottom_path)

        return sel_path

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        super().paint(painter, option, widget)
        if not (self.isSelected() and self._sel_start >= 0):
            return

        sel_start = self._sel_start
        sel_end = self._sel_end
        if sel_end < sel_start:
            sel_start, sel_end = sel_end, sel_start

        sel_path = self._selectionPath(sel_start, sel_end)
        sel_pen, sel_brush = self._selectionPenAndBrush()
        painter.setPen(sel_pen)
        painter.setBrush(sel_brush)
        painter.drawPath(sel_path)

# @graphictype("views.scrolling_list")
# class ListView(containers.ScrollGraphic):
#     contentSizeChanged = QtCore.Signal()
#
#     def __init__(self, parent: QtWidgets.QGraphicsItem = None):
#         super().__init__(parent)
#         self._visible = True
#         self.setContentItem(DataListGraphic(self))
#         self.setClipping(True)
#
#         self.rowHighlighted = self._content.rowHighlighted
#         self._content.contentSizeChanged.connect(self._onContentSizeChanged)
#         self._content.visibleChanged.connect(self._updateVisibility)
#
#     def setObjectName(self, name: str) -> None:
#         super().setObjectName(name)
#         self._content.setObjectName(f"{name}_list")
#
#     @path_element(layouts.Matrix)
#     def matrix(self) -> layouts.Matrix:
#         return self._content.matrix()
#
#     @settable("section_key")
#     def setSectionKeyDataID(self, col_id: str|int) -> None:
#         self._content.setSectionKeyDataID(col_id)
#
#     def isHoverHighlighting(self) -> bool:
#         return self._content.isInteractive()
#
#     @settable()
#     def setHoverHighlighting(self, hover_highlight: bool) -> None:
#         self._content.setInteractive(hover_highlight)
#
#     def updateGeometry(self) -> None:
#         super().updateGeometry()
#         self.contentSizeChanged.emit()
#
#     @settable(argtype=bool)
#     def setHideWhenEmpty(self, hide_when_empty: bool) -> None:
#         self._content.setHideWhenEmpty(hide_when_empty)
#
#     @settable()
#     def setVisible(self, visible: bool) -> None:
#         self._visible = visible
#         self._updateVisibility()
#
#     def shouldBeVisible(self) -> bool:
#         return self._visible and self._content.shouldBeVisible()
#
#     def _updateVisibility(self) -> None:
#         visible = self.shouldBeVisible()
#         cur_vis = self.isVisible()
#         if visible != cur_vis:
#             super().setVisible(visible)
#             self.visibleChanged.emit()

from __future__ import annotations
import enum
import time
from collections import defaultdict
from typing import cast, Any, Collection, Iterable, Optional, Sequence, Union

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .. import config, models
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

    # def setGeometry(self, rect: QtCore.QRectF) -> None:
    #     super().setGeometry(rect)
    #     size = rect.size()
    #     if self._scene_rect_changed or size != self._prev_size:
    #         self._scene_rect_changed = False
    #         self._prev_size = size
    #         self._updateContents()

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

    def _remeasure(self) -> None:
        if not self._measure_data_ids:
            return

        model = self.model()
        font = self.font()
        vfonts = {
            models.specToDataID(model, spec):
                converters.fontConverter(fd, font)
            for spec, fd in self._value_font_map.items()
        }

        if not model:
            return
        count = model.rowCount()
        if not count:
            return

        # print("measuring", self.objectName())
        t = time.perf_counter()
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
            self._invalidateCaches()
            old = self.scene()
            if old and isinstance(old, core.GraphicScene):
                # old_scene.sceneRectChanged.disconnect(self._onSceneRectChanged)
                old.viewportChanged.disconnect(self.viewportChanged)
            if isinstance(value, core.GraphicScene):
                # value.sceneRectChanged.connect(self._onSceneRectChanged)
                value.viewportChanged.connect(self.viewportChanged)
        return super().itemChange(change, value)

    # def _onSceneRectChanged(self) -> None:
    #     self._scene_rect_changed = True
    #     self.updateGeometry()
    #     # self._updateContents()

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

        for row in range(start_row, end_row + 1):
            graphic = self.itemForRow(row)
            if not graphic:
                raise Exception(f"Update for nonexistant row {row}")
            controller.updateItemFromModel(model, row, self, graphic)

        self._remeasure()

    def _invalidateCaches(self):
        self._prev_viewport = self._prev_scene_rect = QtCore.QRectF()

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
        return {"item_template": self._item_template}

    @settable("item_template")
    def setItemTemplate(self, template_data: dict[str, Any]):
        self._item_template = template_data
        self._updateLayoutName()
        self._modelReset()

    def setModel(self, model: Optional[QtCore.QAbstractItemModel]) -> None:
        super().setModel(model)

    @path_element(layouts.Arrangement, "layout")
    def arrangement(self) -> Optional[layouts.Arrangement]:
        return self._arrangement

    def setArrangement(self, layout: layouts.Arrangement) -> None:
        if self._arrangement:
            self._arrangement.invalidated.disconnect(lambda: self._onLayoutChanged)
        self._arrangement = layout
        self._arrangement.invalidated.connect(self._onLayoutChanged)

    def _onLayoutChanged(self):
        self._updateView(UpdateReason.model_change)

    def _rowsMoved(self, _: QtCore.QModelIndex, src_start: int, src_end: int,
                   __: QtCore.QModelIndex, dest_start: int) -> None:
        print("Rows moved", src_start, src_end, "-", dest_start)
        self._updateView(UpdateReason.model_change, anim_arrange=True)

    def _layoutChanged(self) -> None:
        print("Layout changed")
        self._updateView(UpdateReason.model_change, anim_arrange=True, anim_repop=True)

    # def setGeometry(self, rect: QtCore.QRectF) -> None:
    #     super().setGeometry(rect)
    #     self._updateContents(anim_arrange=self._animate_resizing)

    def awaken(self) -> None:
        super().awaken()
        self._updateView(UpdateReason.wake)

    def _updateView(self, reason: UpdateReason, *, anim_arrange=False,
                    anim_repop=False) -> None:
        scene = self.scene()
        if reason not in (UpdateReason.resize, UpdateReason.wake) and \
                not (scene and scene.isActive() and self.isVisible()):
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

    # def _updateChildren(self, *, anim_arrange=False):
    #     self.arrangement().layoutItems(self.rect(),
    #                                    list(self.childGraphics()),
    #                                    animated=anim_arrange)

    def _updateDataContents(self, *, anim_arrange=False, anim_repop=False):
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
                self._updateItemFromModel(item, row_num, local_env=local_env)
            else:
                item = self._makeItem(key, row_num, local_env=local_env)
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
            item = self._makeItem(key, row_num, local_env=self.localEnv())
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

    def _updateItemFromModel(self, graphic: Graphic, row: int,
                             local_env: dict[str, Any]):
        model = self.model()
        self.controller().updateItemFromModel(model, row, self, graphic,
                                              extra_env=local_env)
        key_value = self._keyForRow(row)
        graphic.setData(ITEM_KEY_VALUE, key_value)
        graphic.setData(ITEM_ROW_NUM, row)
        graphic.setLocalVariable("row_num", row)
        graphic.setLocalVariable("unique_id", key_value)
        graphic.setObjectName(f"{model.objectName()}_{row}")

    def _makeItem(self, key: Union[int, str], row: int,
                  local_env: dict[str, Any]) -> Graphic:
        graphic = self._makeItemFromScratch(key, row)
        self._updateItemFromModel(graphic, row, local_env=local_env)
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
        self._prewarm_count = 0
        self._prewarm_batch_size = 25
        self._prewarm_batch_delay = 250
        self._batch_timer: Optional[QtCore.QTimer] = None

        self.setHasHeightForWidth(True)
        self.setFlag(self.ItemSendsScenePositionChanges, True)

    def viewportChanged(self) -> None:
        self._updateSections(UpdateReason.viewport)

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

    # def setPos(self, pos: QtCore.QPointF) -> None:
    #     super().setPos(pos)
    #     self._updateContents()

    def localEnv(self) -> dict[str, Any]:
        env = super().localEnv()
        env.update(
            col_width=self._col_width,
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

    def hasSections(self) -> bool:
        return self._use_sections and bool(self.sectionDataID())

    def isReusingItems(self) -> bool:
        return self._reuse_items

    @settable()
    def setReuseItems(self, reuse: bool) -> None:
        self._reuse_items = reuse
        if reuse:
            self._prewarmPool()
        else:
            self._pool.clear()

    @settable("item_template")
    def setItemTemplate(self, template_data: dict[str, Any]):
        super().setItemTemplate(template_data)
        self._pool.clear()
        self._prewarmPool()

    @settable("prewarm")
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

    def _availableItems(self) -> int:
        return len(self._items) + len(self._pool)

    def _prewarmPool(self) -> None:
        if not self._item_template or not self._reuse_items:
            return
        target = self._prewarm_count
        avail = self._availableItems()
        if target > avail:
            batch_target = min(target, avail + self._prewarm_batch_size)
            # t = time.perf_counter()
            for _ in range(avail, batch_target):
                item = self._makeItemFromScratch(0, 0)
                self._pool.append(item)
            # print("Prewarm", self.objectName(), batch_target, target,
            #       time.perf_counter() - t)
            if self._availableItems() < target:
                self._prewarmBatchTimer().start()

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

    def _makeItem(self, key: Union[int, str], row: int,
                  local_env: dict[str, Any]) -> Graphic:
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
        self._updateItemFromModel(graphic, row, local_env=local_env)
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

    def _updateDataContents(self, *, anim_arrange=False, anim_repop=False
                            ) -> None:
        # t = time.perf_counter()
        if self.scene() is None:
            return
        rect = self.rect()
        vp_rect = self.viewportRect()  # In scene coordinates
        # print("  ", self.objectName(), "vp=", vp_rect)
        if not vp_rect.isValid():
            return
        vis_rect = self.mapRectFromScene(vp_rect)
        ex_vis_rect = self.extraRect(vis_rect)

        has_sections = self.hasSections()
        if has_sections and not self._headings:
            self._updateSections(UpdateReason.no_update, update_contents=False)

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
        # print(self.objectName(), "live_keys=", len(live_keys))
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
        local_env = self.localEnv()

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
                item = self._makeItem(key, row_number, local_env=local_env)
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
class ListView(containers.ScrollGraphic):
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

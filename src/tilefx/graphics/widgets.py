from __future__ import annotations
import pathlib
import time
from typing import Any, Optional, Union

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .. import config, themes
from . import core


class ZoomingView(QtWidgets.QGraphicsView):
    zoomChanged = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setTransformationAnchor(self.NoAnchor)
        self.setFrameStyle(self.NoFrame)

        self._zoomlevels = [0.75, 0.8, 0.9, 1.0, 1.2, 1.4, 1.7, 2.0]
        self._global_scale = 1.0
        self._zoom_scale = 1.0

        self.zoomOutAction = QtWidgets.QAction("Zoom Out", self)
        self.zoomOutAction.setShortcut(QtGui.QKeySequence("Ctrl+-"))
        self.zoomOutAction.triggered.connect(self.zoomOut)
        self.addAction(self.zoomOutAction)

        self.zoomInAction = QtWidgets.QAction("Zoom In", self)
        self.zoomInAction.setShortcuts([
            QtGui.QKeySequence("Ctrl+="),
            QtGui.QKeySequence("Ctrl++")
        ])
        self.zoomInAction.triggered.connect(self.zoomIn)
        self.addAction(self.zoomInAction)

        self.unzoomAction = QtWidgets.QAction("Actual Size", self)
        self.unzoomAction.setShortcut(QtGui.QKeySequence("Ctrl+0"))
        self.unzoomAction.triggered.connect(self.unzoom)
        self.addAction(self.unzoomAction)

        self.toggleAnimationAction = QtWidgets.QAction("Reduce Motion", self)
        self.toggleAnimationAction.setCheckable(True)
        self.toggleAnimationAction.setChecked(False)
        self.toggleAnimationAction.toggled.connect(self.setAnimationDisabled)

    def setAnimationDisabled(self, disabled: bool) -> None:
        scene = self.scene()
        if isinstance(scene, core.GraphicScene):
            scene.setAnimationDisabled(disabled)

    def globalScale(self) -> float:
        return self._global_scale

    def setGlobalScale(self, scale: float) -> None:
        self._global_scale = scale
        # Re-set zoom level to the current value to apply new global scale
        self.setZoomLevel(self._zoom_scale)

    def zoomLevel(self) -> float:
        return self._zoom_scale

    def setZoomLevel(self, scale: float):
        self._zoom_scale = scale
        scale = scale * self._global_scale
        self.setTransform(QtGui.QTransform.fromScale(scale, scale))
        self.fitToContents()
        self.zoomChanged.emit()

    def zoomOut(self):
        self.setZoomLevel(self.nextLowerZoomLevel())
        self.fitToContents()

    def zoomIn(self):
        self.setZoomLevel(self.nextHigherZoomLevel())
        self.fitToContents()

    def unzoom(self):
        self.setZoomLevel(1.0)
        self.fitToContents()

    def nextLowerZoomLevel(self) -> float:
        z = self.zoomLevel()
        for level in reversed(self._zoomlevels):
            if z > level:
                return level
        return self._zoomlevels[0]

    def nextHigherZoomLevel(self) -> float:
        z = self.zoomLevel()
        for level in self._zoomlevels:
            if z < level:
                return level
        return self._zoomlevels[-1]

    def fitToContents(self) -> None:
        pass


class GraphicView(ZoomingView):
    SizeSceneRectToContent = 0
    SizeSceneRectToView = 1

    viewportChanged = QtCore.Signal()
    contentSizeChanged = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self._use_own_vsb = True
        self._template_path: Optional[pathlib.Path] = None
        self._scene_rect_mode = self.SizeSceneRectToContent

        self.setBackgroundRole(QtGui.QPalette.Window)
        self.setContentsMargins(0, 0, 0, 0)
        # self.setDragMode(self.ScrollHandDrag)
        self.setInteractive(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.setRenderHint(QtGui.QPainter.TextAntialiasing, True)

        vsb = ScrollBar(Qt.Vertical, self)
        vsb.setAutoFillBackground(False)
        self.setVerticalScrollBar(vsb)
        vsb.valueChanged.connect(self.notifyViewportChanged)

    def setScene(self, scene: core.GraphicScene) -> None:
        old_scene = self.scene()
        if isinstance(old_scene, core.GraphicScene):
            old_scene.rootChanged.disconnect(self.fitToContents)
            old_scene.rootGeometryChanged.disconnect(self._onContentSizeChanged)
        super().setScene(scene)
        if isinstance(scene, core.GraphicScene):
            scene.rootChanged.connect(self.fitToContents)
            scene.contentSizeChanged.connect(self._onContentSizeChanged)
            palette = scene.themePalette().qtPalette()
            self.setPalette(palette)
            self.verticalScrollBar().setPalette(palette)

    def _onContentSizeChanged(self) -> None:
        self.fitToContents()
        self.contentSizeChanged.emit()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.fitToContents()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self.fitToContents()

    def sceneRectMode(self) -> int:
        return self._scene_rect_mode

    def setSceneRectMode(self, mode: int) -> None:
        self._scene_rect_mode = mode

    def setUseOwnVerticalScrollBar(self, use_own_vsb: bool) -> None:
        self._use_own_vsb = use_own_vsb
        policy = Qt.ScrollBarAlwaysOn if use_own_vsb else Qt.ScrollBarAlwaysOff
        self.setVerticalScrollBarPolicy(policy)
        self.fitToContents()

    def viewRect(self) -> QtCore.QRectF:
        rect = self.rect()
        vsb = self.verticalScrollBar()
        if vsb.isVisible():
            rect.setWidth(rect.width() - vsb.width())

        rect = QtCore.QRectF(rect)
        factor = self._zoom_scale * self._global_scale
        vw = rect.width() / factor
        vh = rect.height() / factor
        rect.setSize(QtCore.QSizeF(vw, vh))
        return rect

    def scrollY(self) -> float:
        y = self.verticalScrollBar().value()
        factor = self._zoom_scale * self._global_scale
        return y / factor

    def viewportRect(self) -> QtCore.QRectF:
        view_rect = self.viewRect()
        view_rect.moveTop(self.scrollY())
        return view_rect

    def fitToContents(self):
        root = self.rootGraphic()
        view_rect = self.viewRect()
        scene_rect = view_rect
        if root:
            if self.sceneRectMode() == self.SizeSceneRectToContent:
                constraint = QtCore.QSizeF(view_rect.width(), -1)
                csize = root.effectiveSizeHint(Qt.PreferredSize, constraint)
                scene_rect = QtCore.QRectF(QtCore.QPointF(), csize)
            if scene_rect != root.geometry():
                # t = time.perf_counter()
                root.setGeometry(scene_rect)
                # print("  ", time.perf_counter() - t)
        self.setSceneRect(scene_rect)
        self.notifyViewportChanged()

    def notifyViewportChanged(self) -> None:
        from .core import GraphicScene
        self.viewportChanged.emit()
        scene = self.scene()
        if isinstance(scene, GraphicScene):
            scene.notifyViewportChanged()

    def scrollToTop(self) -> None:
        self.verticalScrollBar().setValue(0)

        from .containers import ScrollGraphic
        root = self.rootGraphic()
        if isinstance(root, ScrollGraphic):
            root.scrollToTop()

    def widgetHeightHint(self) -> float:
        from .containers import ScrollGraphic
        scene = self.scene()
        if not scene:
            return 0.0
        if not isinstance(scene, core.GraphicScene):
            return self.sceneRect().height()

        root = scene.rootGraphic()
        view_rect = self.viewRect()
        constraint = QtCore.QSizeF(view_rect.width(), -1)
        if isinstance(root, ScrollGraphic):
            size = root.contentsSizeHint(Qt.PreferredSize, constraint)
        else:
            root.updateGeometry()
            # I don't know why, but calling this twice in a row gives two
            # different results, and the second one is more correct. Until I
            # figure out why, I have to leave this here like this :(
            size = root.sizeHint(Qt.PreferredSize, constraint)
            size = root.sizeHint(Qt.PreferredSize, constraint)

        # Decompensate for the scaling factor
        factor = self._zoom_scale * self._global_scale
        return size.height() * factor

    def rootGraphic(self) -> Optional[core.Graphic]:
        scene = self.scene()
        if scene and isinstance(scene, core.GraphicScene):
            return scene.rootGraphic()

    def controller(self) -> Optional[config.DataController]:
        scene = self.scene()
        if scene and isinstance(scene, core.GraphicScene):
            return scene.controller()

    def setController(self, controller: config.DataController) -> None:
        scene = self.scene()
        if scene and isinstance(scene, core.GraphicScene):
            scene.setController(controller)
        else:
            raise TypeError(f"Can't set controller on scene: {scene}")

    def loadTemplate(self, path: Union[str, pathlib.Path], force=False) -> None:
        path = pathlib.Path(path)
        if path and (force or path != self._template_path):
            scene = self.scene()
            if isinstance(scene, core.GraphicScene):
                scene.loadTemplate(path)

    def setTemplate(self, template_data: dict[str, Any]) -> None:
        scene = self.scene()
        if isinstance(scene, core.GraphicScene):
            scene.setTemplate(template_data)

    def setColorTheme(self, theme: themes.ColorTheme) -> None:
        scene = self.scene()
        if isinstance(scene, core.GraphicScene):
            scene.setColorTheme(theme)
            self.setPalette(scene.themePalette().qtPalette())

    def setThemeColor(self, color: QtGui.QColor) -> None:
        scene = self.scene()
        if isinstance(scene, core.GraphicScene):
            scene.setThemeColor(color)
            self.setPalette(scene.themePalette().qtPalette())


class ScrollBar(QtWidgets.QScrollBar):
    def __init__(self, orientation: Qt.Orientation,
                 parent: QtWidgets.QWidget = None):
        super().__init__(orientation, parent)
        self._track_width = 4.0
        self._style = QtWidgets.QCommonStyle()

    def trackAndHandleRects(self, track_width: float
                            ) -> tuple[QtCore.QRectF, QtCore.QRectF]:
        option = QtWidgets.QStyleOptionSlider()
        option.initFrom(self)
        option.minimum = self.minimum()
        option.maximum = self.maximum()
        option.orientation = self.orientation()
        option.singleStep = self.singleStep()
        option.pageStep = self.pageStep()
        option.sliderPosition = self.sliderPosition()
        option.sliderValue = self.sliderPosition()
        option.upsideDown = self.invertedAppearance()

        style = self._style
        track_rect = QtCore.QRectF(style.subControlRect(
            style.CC_ScrollBar, option, style.SC_ScrollBarGroove, self
        ).normalized())
        handle_rect = QtCore.QRectF(style.subControlRect(
            style.CC_ScrollBar, option, style.SC_ScrollBarSlider, self
        ).normalized())

        hw = track_width / 2.0
        ctr = track_rect.center()
        if option.orientation == Qt.Vertical:
            cx = ctr.x() - hw
            tr = QtCore.QRectF(cx, track_rect.y(),
                               track_width, track_rect.height())
            hr = QtCore.QRectF(cx, handle_rect.y(),
                               track_width, handle_rect.height())
        else:
            cy = ctr.y() - hw
            tr = QtCore.QRectF(track_rect.x(), cy,
                               track_rect.width(), track_width)
            hr = QtCore.QRectF(handle_rect.x(), cy,
                               handle_rect.width(), track_width)

        return tr, hr

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        palette = self.palette()
        color = palette.window().color()
        painter.fillRect(self.rect(), color)

        # This widget doesn't seem to get the right palette from the parent
        # view when in a Python pnael, so we can't reply on the correct colors.
        # Just base the track and handle colors off the background color.
        if color.lightnessF() < 0.6:
            handle_color = color.lighter(200)
        else:
            handle_color = color.darker(200)
        track_color = QtGui.QColor(handle_color)
        track_color.setAlphaF(0.5)

        track_rect, handle_rect = self.trackAndHandleRects(self._track_width)
        half_width = self._track_width / 2.0
        painter.setPen(Qt.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, half_width, half_width)
        painter.setBrush(handle_color)
        painter.drawRoundedRect(handle_rect, half_width, half_width)

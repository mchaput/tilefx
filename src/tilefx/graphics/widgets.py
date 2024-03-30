from __future__ import annotations
import pathlib
from typing import Any, Optional, Union

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .. import config
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
        self.zoomInAction.setShortcut(QtGui.QKeySequence("Ctrl+="))
        self.zoomInAction.triggered.connect(self.zoomIn)
        self.addAction(self.zoomInAction)

        self.unzoomAction = QtWidgets.QAction("Actual Size", self)
        self.unzoomAction.setShortcut(QtGui.QKeySequence("Ctrl+0"))
        self.unzoomAction.triggered.connect(self.unzoom)
        self.addAction(self.unzoomAction)

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
    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self._template_path: Optional[pathlib.Path] = None

        self.setBackgroundRole(QtGui.QPalette.Window)
        self.setContentsMargins(0, 0, 0, 0)
        # self.setDragMode(self.ScrollHandDrag)
        self.setInteractive(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        self.setAlignment(Qt.AlignCenter)

    def setScene(self, scene: core.GraphicScene) -> None:
        old_scene = self.scene()
        if old_scene and isinstance(old_scene, core.GraphicScene):
            old_scene.rootChanged.disconnect(self.fitToContents)
        super().setScene(scene)
        if scene and isinstance(scene, core.GraphicScene):
            scene.rootChanged.connect(self.fitToContents)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.fitToContents()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self.fitToContents()

    def viewRect(self) -> QtCore.QRectF:
        rect = QtCore.QRectF(self.rect())
        factor = self._zoom_scale * self._global_scale
        vw = rect.width() / factor
        vh = rect.height() / factor
        rect.setSize(QtCore.QSizeF(vw, vh))
        return rect

    def fitToContents(self):
        scene = self.scene()
        if not scene:
            return

        view_rect = self.viewRect()
        if isinstance(scene, core.GraphicScene):
            root = scene.rootGraphic()
            if root and root.isVisible():
                # constraint = QtCore.QSizeF(vw, -1)
                # size = root.effectiveSizeHint(Qt.PreferredSize, constraint)
                root.setGeometry(view_rect)

        self.scene().setSceneRect(view_rect)

    def scrollToTop(self) -> None:
        from .views import ScrollGraphic
        root = self.rootGraphic()
        if isinstance(root, ScrollGraphic):
            root.scrollToTop()

    def contentHeightForWidth(self, width: float) -> float:
        from .views import ScrollGraphic
        scene = self.scene()
        if not scene:
            return 0.0
        if not isinstance(scene, core.GraphicScene):
            return scene.sceneRect().height()

        root = scene.rootGraphic()
        constraint = QtCore.QSizeF(width, -1)
        if isinstance(root, ScrollGraphic):
            size = root.contentsSizeHint(Qt.PreferredSize, constraint)
        else:
            size = root.sizeHint(Qt.PreferredSize, constraint)

        # Compensate for the scaling factor
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

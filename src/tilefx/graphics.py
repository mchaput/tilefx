from __future__ import annotations
import enum
import math
import pathlib
from collections import defaultdict
from types import CodeType
from typing import (cast, Any, Callable, Iterable, Mapping, Optional, Sequence,
                    Union)

from PySide2 import QtCore, QtGui, QtWidgets, QtSvg
from PySide2.QtCore import Qt

import tilefx.themes
from . import config, converters, layouts, styling, themes
from .config import settable, findSettable, settableNames
from .layouts import Matrix

ANCHOR_PREFIX = "anchor:"

ANIM_DURATION_MS = 250
DEFAULT_EASING_CURVE = QtCore.QEasingCurve.OutCubic
FONT_FAMILY = "Lato"
NUMBER_FAMILY = "Lato"
MONOSPACE_FAMILY = "Source Code Pro"


graphic_class_registry: dict[str, type[Graphic]] = {}
graphictype = config.registrar(graphic_class_registry)

outback = QtCore.QEasingCurve(QtCore.QEasingCurve.BezierSpline)
outback.addCubicBezierSegment(QtCore.QPointF(.17,.67), QtCore.QPointF(.43,1.3),
                              QtCore.QPointF(1.0, 1.0))


def makeProxyItem(parent: QtWidgets.QGraphicsItem, widget: QtWidgets.QWidget
                  ) -> QtWidgets.QGraphicsProxyWidget:
    widget.setAttribute(Qt.WA_TranslucentBackground, True)
    gi = QtWidgets.QGraphicsProxyWidget(parent)
    gi.setWidget(widget)
    return gi


def drawTextDocument(painter: QtGui.QPainter, rect: QtCore.QRectF,
                     doc: QtGui.QTextDocument, palette: QtGui.QPalette,
                     color: QtGui.QColor = None,
                     role: QtGui.QPalette.ColorRole = QtGui.QPalette.WindowText
                     ) -> None:
    tx = rect.x()
    ty = rect.y()
    height = doc.size().height()
    align = doc.defaultTextOption().alignment()
    if align & Qt.AlignVCenter:
        ty += rect.height() / 2 - height / 2
    elif align & Qt.AlignBottom:
        ty = rect.bottom() - height

    painter.translate(tx, ty)
    text_rect = rect.translated(-tx, -ty)
    # painter.setClipRect(rect, Qt.IntersectClip)

    # QAbstractTextDocumentLayout is hardcoded to draw the text using
    # the Text role, but we want to use WindowText for values (and also
    # for it to be configurable), so I have to munge the palette and
    # pass that to the draw() method
    if color:
        palette.setColor(palette.Text, color)
    elif role != palette.Text:
        palette.setBrush(palette.Text, palette.brush(role))

    context = QtGui.QAbstractTextDocumentLayout.PaintContext()
    context.palette = palette
    context.cursorPosition = -1
    context.clip = text_rect
    doc.documentLayout().draw(painter, context)


def drawChasingArc(painter: QtGui.QPainter, rect: QtCore.QRect,
                   timestep: int, color: QtGui.QColor = None) -> None:
    color = color or QtGui.QColor.fromRgbF(1.0, 1.0, 1.0)
    pen = QtGui.QPen(color, 1.0)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    sweep = abs(math.sin((timestep % 500) / 500 * math.pi)) * 140 + 10
    degrees = -(timestep % 360)
    start_ticks = int((degrees - sweep / 2) * 16)
    sweep_ticks = int(sweep * 16)
    painter.drawArc(rect, start_ticks, sweep_ticks)


def drawFadingRings(painter: QtGui.QPainter, rect: QtCore.QRectF,
                    timestep: int, color: QtGui.QColor = None, ring_count=3
                    ) -> None:
    color = color or QtGui.QColor.fromRgbF(1.0, 1.0, 1.0)
    half = rect.width() / 2
    ctr = rect.center()
    interval = (half * 1.5) / ring_count
    pct = (timestep % 100) / 100
    for i in range(ring_count + 1):
        r = i * interval + (interval * pct)
        color.setAlphaF(1.0 - max(0.0, r / half))
        painter.setPen(QtGui.QPen(color, 1.5))
        painter.drawEllipse(ctr, r, r)


def makeAnim(item: QtWidgets.QGraphicsItem, prop: bytes, *,
             duration=ANIM_DURATION_MS, curve=DEFAULT_EASING_CURVE
             ) -> QtCore.QPropertyAnimation:
    anim = QtCore.QPropertyAnimation(item, prop)
    anim.setDuration(duration)
    anim.setEasingCurve(curve)
    return anim


def startAnim(item: QtWidgets.QGraphicsItem, prop: bytes, start: Any, end: Any,
              *, duration=ANIM_DURATION_MS, curve=DEFAULT_EASING_CURVE,
              policy=QtCore.QAbstractAnimation.DeleteWhenStopped) -> None:
    anim = makeAnim(item, prop, duration=duration, curve=curve)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.start(policy)


def scaleAndFadeOut(item: QtWidgets.QGraphicsItem, duration=ANIM_DURATION_MS,
                    curve=DEFAULT_EASING_CURVE,
                    parent: QtWidgets.QGraphicsItem = None) -> None:
    scale_anim = makeAnim(item, b"scale", duration=duration, curve=curve)
    scale_anim.setStartValue(1.0)
    scale_anim.setEndValue(2.0)

    fade_anim = makeAnim(item, b"opaciy", duration=duration, curve=curve)
    fade_anim.setStartValue(item.opacity())
    fade_anim.setEndValue(0.0)

    anim_group = QtCore.QParallelAnimationGroup(parent or item)
    anim_group.addAnimation(scale_anim)
    anim_group.addAnimation(fade_anim)
    anim_group.start(anim_group.DeleteWhenStopped)


def recolorPixmap(pixmap: QtGui.QPixmap, color: QtGui.QColor) -> None:
    if pixmap.isNull():
        return
    p = QtGui.QPainter(pixmap)
    p.setCompositionMode(p.CompositionMode_SourceAtop)
    p.fillRect(pixmap.rect(), color)
    p.end()


class ZoomingView(QtWidgets.QGraphicsView):
    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self._zoomlevels = [0.75, 0.8, 0.9, 1.0, 1.2, 1.4, 1.7, 2.0]
        self._global_scale = 1.0
        self._zoomscale = 1.0

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
        self.setZoomLevel(self._zoomscale)

    def zoomLevel(self) -> float:
        return self._zoomscale

    def setZoomLevel(self, scale: float):
        self._zoomscale = scale
        scale = scale * self._global_scale
        self.setTransform(QtGui.QTransform.fromScale(scale, scale))
        self.fitToContents()

    def zoomOut(self):
        self.setZoomLevel(self.nextLowerZoomLevel())

    def zoomIn(self):
        self.setZoomLevel(self.nextHigherZoomLevel())

    def unzoom(self):
        self.setZoomLevel(1.0)

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


class GraphicViewWidget(ZoomingView):
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
        self.setAlignment(Qt.AlignCenter)

    def setScene(self, scene: GraphicScene) -> None:
        old_scene = self.scene()
        if old_scene and isinstance(old_scene, GraphicScene):
            old_scene.rootChanged.disconnect(self.fitToContents)
        super().setScene(scene)
        if scene and isinstance(scene, GraphicScene):
            scene.rootChanged.connect(self.fitToContents)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.fitToContents()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self.fitToContents()

    def viewRect(self) -> QtCore.QRectF:
        rect = self.rect()
        vsb = self.verticalScrollBar()
        if vsb.isVisible():
            sbw = self.verticalScrollBar().width()
        else:
            sbw = 0
        vw = (rect.width() - sbw) / (self.zoomLevel() * self.globalScale())
        return QtCore.QRectF(0, 0, vw, rect.height())

    def fitToContents(self):
        scene = self.scene()
        if not scene:
            return

        view_rect = self.viewRect()
        if isinstance(scene, GraphicScene):
            root = scene.rootGraphic()
        else:
            root = None

        self.scene().setSceneRect(view_rect)
        if root and root.isVisible():
            constraint = QtCore.QSizeF(view_rect.width(), -1)
            size = root.effectiveSizeHint(Qt.PreferredSize, constraint)
            # size = size.boundedTo(view_rect.size())
            root_rect = QtCore.QRectF(QtCore.QPointF(0, 0), view_rect.size())
            root.setGeometry(root_rect)

            layout = root.layout()
            if layout:
                layout.activate()

    def rootGraphic(self) -> Optional[Graphic]:
        scene = self.scene()
        if scene and isinstance(scene, GraphicScene):
            return scene.rootGraphic()

    def controller(self) -> Optional[config.DataController]:
        scene = self.scene()
        if scene and isinstance(scene, GraphicScene):
            return scene.controller()

    def setController(self, controller: config.DataController) -> None:
        scene = self.scene()
        if scene and isinstance(scene, GraphicScene):
            scene.setController(controller)
        else:
            raise TypeError(f"Can't set controller on scene: {scene}")

    def loadTemplate(self, path: Union[str, pathlib.Path], force=False) -> None:
        path = pathlib.Path(path)
        if path and (force or path != self._template_path):
            scene = self.scene()
            if isinstance(scene, GraphicScene):
                scene.loadTemplate(path)

    def setTemplate(self, template_data: dict[str, Any]) -> None:
        scene = self.scene()
        if isinstance(scene, GraphicScene):
            scene.setTemplate(template_data)


class GraphicScene(QtWidgets.QGraphicsScene):
    rootChanged = QtCore.Signal()
    linkActivated = QtCore.Signal(str)

    def __init__(self, parent: QtCore.QObject = None):
        super().__init__(parent)
        self.setPalette(themes.darkPalette(self.palette()))
        self._template_path: Optional[pathlib.Path] = None
        self._template_data: dict[str, Any] = {}
        self._root: Optional[Graphic] = None
        self._controller: Optional[config.DataController] = None

    def linkClicked(self, url: str) -> None:
        self.linkActivated.emit(url)

    def rootGraphic(self) -> Optional[Graphic]:
        return self._root

    def setRootGraphic(self, root: Graphic) -> None:
        if root is self._root:
            return

        old_root = self._root
        if old_root:
            self.removeItem(old_root)
            # old_root.deleteLater()

        self._root = root
        self.addItem(root)
        self.rootChanged.emit()

    def controller(self) -> Optional[config.DataController]:
        return self._controller

    def setController(self, controller: Optional[config.DataController]) -> None:
        self._controller = controller

    def loadTemplate(self, path: Union[str, pathlib.Path], force=False) -> None:
        import json

        path = pathlib.Path(path)
        if path and (force or path != self._template_path):
            with path.open() as f:
                template_data = json.load(f)
            self.setTemplate(template_data)
            self._template_path = path

    def reloadTemplate(self) -> None:
        self.loadTemplate(self._template_path, force=True)

    def setTemplate(self, template_data: dict[str, Any]) -> None:
        root = rootFromTemplate(template_data, self.controller())
        self.setRootGraphic(root)

    def drawBackground(self, painter: QtGui.QPainter,
                       rect: QtCore.QRectF) -> None:
        painter.fillRect(rect, self.palette().window())


class Graphic(QtWidgets.QGraphicsWidget):
    property_aliases = {}

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._local_env: dict[str, Any] = {}
        self._anims: dict[bytes, QtCore.QPropertyAnimation] = {}
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._model: Optional[QtCore.QAbstractItemModel] = None
        self._animation_disabled = False
        self._xrot = 0.0
        self._yrot = 0.0
        self._zdist = 180.0

    @classmethod
    def propertyAliases(cls) -> dict[str, str]:
        aliases = {}
        for c in cls.__mro__:
            if issubclass(c, Graphic):
                aliases.update(c.property_aliases)
        return aliases

    @classmethod
    def fromData(cls, data: dict[str, Any], parent: Graphic = None,
                 controller: config.DataController = None) -> Graphic:
        graphic: Graphic = cls(parent=parent)
        if parent:
            parent.prepChild(graphic, data)
        graphic.configureFromData(data, controller)
        return graphic

    # def __del__(self):
    #     for k in list(self._anims):
    #         anim = self._anims.pop(k)
    #         anim.finished.disconnect(self._animFinished)
    #         anim.deleteLater()

    def configureFromData(self, data: dict[str, Any],
                          controller: config.DataController = None) -> None:
        # We want to set the object's own properties first, then instantiate its
        # children (because the properties might influence how prepChild()
        # works), so we pop the child data out and process it after setting up
        # the tile
        child_tile_data: Sequence[dict[str, Any]] = data.pop("items", ())

        if "name" in data:
            self.setObjectName(data.pop("name"))
        if controller:
            controller.prepObject(self, data)
        config.updateSettables(self, data)

        # Create child tiles
        for sub_data in child_tile_data:
            child = graphicFromData(sub_data, parent=self,
                                    controller=controller)
            self.addChild(child)

    def setHasHeightForWidth(self, hfw: bool) -> None:
        sp = self.sizePolicy()
        sp.setHeightForWidth(hfw)
        self.setSizePolicy(sp)

    def setHasWidthForHeight(self, wfh: bool) -> None:
        sp = self.sizePolicy()
        sp.setHeightForWidth(wfh)
        self.setSizePolicy(sp)

    def pathElement(self, name: str) -> Optional[QtCore.QObject]:
        return None

    def addChild(self, item: QtWidgets.QGraphicsItem) -> None:
        item.setParentItem(self)

    def prepChild(self, child: Graphic, data: dict[str, Any]) -> None:
        for prop_name in list(data):
            if ":" in prop_name:
                setter = findSettable(self, prop_name)
                if setter:
                    value = data.pop(prop_name)
                    setter(self, child, value)
                else:
                    raise NameError(f"No property {prop_name} on {self!r}: " +
                                    ", ".join(settableNames(self)))

    def namedLayoutItem(self, name: str
                        ) -> Optional[QtWidgets.QGraphicsLayoutItem]:
        if name == "parent":
            return self.layout()

        obj: Optional[QtWidgets.QGraphicsItem] = None
        for child in self.childItems():
            if child.objectName() == name:
                if not isinstance(child, QtWidgets.QGraphicsLayoutItem):
                    raise TypeError(f"{obj!r} is not layout-able")
                return child

    def childNames(self) -> Sequence[str]:
        return [c.objectName() for c in self.childItems() if c.objectName()]

    def parentViewportRect(self) -> QtCore.QRectF:
        # This must return the visible rect in SCENE coordinates
        parent = self.parentGraphic()
        if parent:
            return parent.viewportRect()
        else:
            scene = self.scene()
            if scene:
                srect = scene.sceneRect()
                return srect
        return QtCore.QRectF()

    def viewportRect(self) -> QtCore.QRectF:
        # This must return the visible rect in SCENE coordinates
        return self.parentViewportRect()

    def anchorLayout(self) -> QtWidgets.QGraphicsAnchorLayout:
        layout = self.layout()
        if layout:
            if not isinstance(layout, QtWidgets.QGraphicsAnchorLayout):
                raise Exception(f"Can't get anchor layout of {self!r}, "
                                f"it aready has layout {layout!r}")
        else:
            layout = QtWidgets.QGraphicsAnchorLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self.setLayout(layout)
        return layout

    @settable()
    def setSelectable(self, on: bool) -> None:
        self.setFlag(self.ItemIsSelectable, on)

    def extraVariables(self) -> dict[str, Any]:
        return {}

    def dataProxy(self) -> Optional[Graphic]:
        return None

    def parentGraphic(self) -> Optional[Graphic]:
        parent = self.parentItem()
        while parent and not isinstance(parent, Graphic):
            parent = parent.parentItem()
        return parent

    def childGraphics(self) -> Iterable[Graphic]:
        return (child for child in self.childItems()
                if isinstance(child, Graphic))

    def updateableChildren(self) -> Iterable[Graphic]:
        return self.childGraphics()

    def animationDisabled(self) -> bool:
        return self._animation_disabled

    def clipping(self) -> bool:
        return self.flags() & self.ItemClipsChildrenToShape

    @settable("clip")
    def setClipping(self, clip: bool) -> None:
        self.setFlag(self.ItemClipsChildrenToShape, clip)

    def blurEffect(self) -> Optional[QtWidgets.QGraphicsBlurEffect]:
        effect = self.graphicsEffect()
        if isinstance(effect, QtWidgets.QGraphicsBlurEffect):
            return effect

    @settable()
    def setBlurRadius(self, radius: float) -> None:
        blur = self.blurEffect()
        if blur:
            blur.setBlurRadius(radius)

    @settable("fixed_width")
    def setFixedWidth(self, width: float):
        self.prepareGeometryChange()
        super().setPreferredWidth(width)
        super().setMinimumWidth(width)
        super().setMaximumWidth(width)
        self.updateGeometry()

    @settable("fixed_height")
    def setFixedHeight(self, height: float):
        self.prepareGeometryChange()
        super().setPreferredHeight(height)
        super().setMinimumHeight(height)
        super().setMaximumHeight(height)
        self.updateGeometry()

    @settable("fixed_size", argtype=QtCore.QSizeF)
    def setFixedSize(self, size: QtCore.QSizeF) -> None:
        self.prepareGeometryChange()
        super().setPreferredSize(size)
        super().setMinimumSize(size)
        super().setMaximumSize(size)
        self.updateGeometry()

    def xRotation(self) -> float:
        return self._xrot

    @settable("x_rotation")
    def setXRotation(self, angle: float) -> None:
        self.show()
        self._xrot = angle
        self._updateTransform()

    xrot = QtCore.Property(float, xRotation, setXRotation)

    def yRotation(self) -> float:
        return self._yrot

    @settable("y_rotation")
    def setYRotation(self, angle: float) -> None:
        self.show()
        self._yrot = angle
        self._updateTransform()

    yrot = QtCore.Property(float, yRotation, setYRotation)

    def xyRotation(self) -> QtCore.QPointF:
        return QtCore.QPointF(self._xrot, self._yrot)

    def setXYRotation(self, p: QtCore.QPointF) -> None:
        self._xrot = p.x()
        self._yrot = p.y()
        self._updateTransform()

    xyrot = QtCore.Property(QtCore.QPointF, xyRotation, setXYRotation)

    @settable("projection_distance")
    def setProjectionDistance(self, dist: float) -> None:
        self._zdist = dist

    def _updateTransform(self):
        size = self.size()
        dx = size.width() / 2
        dy = size.height() / 2
        self.setTransformOriginPoint(-dx, -dy)
        # rot = QtWidgets.QGraphicsRotation(self)
        # rot.setOrigin(QtGui.QVector3D(size.width() / 2, size.height() / 2, 0.0))
        # rot.setAxis(QtGui.QVector3D(0.0, 1.0, 0.0))
        # rot.setAngle(72)
        # self.setTransformations([rot, scale])
        m4 = QtGui.QMatrix4x4()
        m4.rotate(self._xrot, 1.0, 0.0, 0.0)
        m4.rotate(self._yrot, 0.0, 1.0, 0.0)
        m4.translate(-dx, -dy)
        self.setTransform(m4.toTransform(self._zdist))

    def localEnv(self) -> dict[str, Any]:
        parent = self.parentGraphic()
        env = parent.localEnv() if parent else {}
        env.update(self._local_env)
        env["self"] = self
        return env

    def setLocalEnv(self, env: dict[str, Any]) -> None:
        self._local_env = env

    def _anim(self, prop: bytes, *, duration=ANIM_DURATION_MS,
              curve=DEFAULT_EASING_CURVE) -> QtCore.QPropertyAnimation:
        try:
            anim = self._anims[prop]
        except KeyError:
            anim = makeAnim(self, prop, duration=duration, curve=curve)
            anim.finished.connect(self._animFinished)
            self._anims[prop] = anim
        return anim

    def animateProperty(self, prop: bytes, start: Any, end: Any, *,
                        duration=ANIM_DURATION_MS,
                        curve=DEFAULT_EASING_CURVE,
                        callback: Callable[[], None] = None) -> None:
        anim = self._anim(prop)
        anim.stop()
        anim.setDuration(duration)
        anim.setEasingCurve(curve)
        anim.setStartValue(start)
        anim.setEndValue(end)
        if callback:
            self._callbacks[id(anim)] = callback
        anim.start()

    def _animFinished(self) -> None:
        anim = self.sender()
        callback = self._callbacks.pop(id(anim), None)
        if callback:
            callback()

    def animateGeometry(self, rect: QtCore.QRectF,
                        view_rect: QtCore.QRectF = None, **kwargs) -> None:
        if view_rect:
            # Don't animate if both the start and end rects are not visible
            on_screen = (self.geometry().intersects(view_rect) or
                         rect.intersects(view_rect))
            if not on_screen:
                self.setGeometry(rect)
                return
        self.animateProperty(b"geometry", self.geometry(), rect, **kwargs)

    def animateScale(self, scale: float, **kwargs) -> None:
        self.animateProperty(b"scale", self.scale(), scale, **kwargs)

    def animateRotation(self, degrees: float, duration=ANIM_DURATION_MS
                        ) -> None:
        self.animateProperty(b"rotation", self.rotation(), degrees,
                             duration=duration)

    def fadeTo(self, opacity: float, **kwargs) -> None:
        self.animateProperty(b"opacity", self.opacity(), opacity, **kwargs)

    def fadeIn(self, **kwargs) -> None:
        self.show()
        self.fadeTo(1.0, **kwargs)

    def fadeOut(self, hide=True, **kwargs) -> None:
        if hide and "callback" not in kwargs:
            kwargs["callback"] = (lambda: self.hide())
        self.fadeTo(0.0, **kwargs)

    def scaleAndFadeOut(self, **kwargs) -> None:
        scaleAndFadeOut(self)

    def flipTo(self, h_angle: float, v_angle: float) -> None:
        if v_angle != self._xrot:
            self.animateProperty(b"xrot", self.xRotation(), v_angle)
        if h_angle != self._yrot:
            self.animateProperty(b"yrot", self.yRotation(), h_angle)

    # def resizeEvent(self, event):
    #     super().resizeEvent(event)
    #     self.setTransformOriginPoint(self.rect().center())


settable("min_width")(Graphic.setMinimumWidth)
settable("min_height")(Graphic.setMinimumHeight)
settable("max_width")(Graphic.setMaximumWidth)
settable("max_height")(Graphic.setMaximumHeight)
settable("width")(Graphic.setPreferredWidth)
settable("height")(Graphic.setPreferredHeight)
settable("size", argtype=QtCore.QSizeF)(Graphic.setPreferredSize)
settable("min_size", argtype=QtCore.QSizeF)(Graphic.setMinimumSize)
settable("max_size", argtype=QtCore.QSizeF)(Graphic.setMaximumSize)


@graphictype("layout_graphic")
class LayoutGraphic(Graphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._margins = QtCore.QMarginsF(0, 0, 0, 0)

    def addChild(self, item: QtWidgets.QGraphicsWidget):
        super().addChild(item)
        layout = self.layout()
        if layout:
            layout.addItem(item)

    # def contentLayout(self) -> Optional[layouts.Arrangement]:
    #     return self._layout
    #
    # def setContentLayout(self, layout: layouts.Arrangement) -> None:
    #     if self._layout:
    #         self._layout.invalidated.disconnect(self._updateContents)
    #     self._layout = layout
    #     self._layout.setMargins(self._margins)
    #     self._layout.invalidated.connect(self._updateContents)
    #
    # def _updateContents(self, animated=True) -> None:
    #     animated = animated and not self.animationDisabled()
    #     self.contentLayout().layoutItems(self.rect(),
    #                                      list(self.childGraphics()),
    #                                      animated=animated)

    @settable("margins", argtype=QtCore.QMarginsF)
    def setMargins(self, left: Union[QtCore.QMarginsF, float], top=0.0,
                   right=0.0, bottom=0.0) -> None:
        # We just copy the margins onto the layout, but we also have to remember
        # them in case the layout hasn't been set yet or if it changes
        self._margins = converters.marginsArgs(left, top, right, bottom)
        layout = self.layout()
        if layout:
            layout.setMargins(left, top, right, bottom)


@graphictype("anchors")
class AnchorsGraphic(Graphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._layout_ops: defaultdict[str, list[tuple]] = defaultdict(list)

    def _try(self, method: Callable, child: QtWidgets.QGraphicsItem,
             name: str, *args, **kwargs):
        if not isinstance(child, QtWidgets.QGraphicsItem):
            raise TypeError(f"Not a QGraphicsItem: {child!r}")
        if not isinstance(name, str):
            raise TypeError(f"Not a name string: {name!r}")
        obj = self.namedLayoutItem(name)
        if obj:
            method(child, obj, *args, **kwargs)
        else:
            self._layout_ops[name].append((method, child, args, kwargs))

    def drainLayoutOperations(self) -> None:
        ops = self._layout_ops
        for name, oplist in ops.items():
            obj = self.namedLayoutItem(name)
            if not obj:
                names = ", ".join(self.childNames())
                raise NameError(
                    f"Can't find layout object named {name!r} in {names}"
                )
            for method, child, args, kwargs in oplist:
                method(child, obj, *args, **kwargs)
        self._layout_ops.clear()

    def configureFromData(self, data: dict[str, Any],
                          controller: config.DataController = None) -> None:
        super().configureFromData(data, controller)
        self.drainLayoutOperations()

    @settable("spacing")
    def setLayoutSpacing(self, spacing: float) -> None:
        layout = self.anchorLayout()
        layout.setSpacing(spacing)

    @settable("v_spacing")
    def setVerticalSpacing(self, spacing: float) -> None:
        layout = self.anchorLayout()
        layout.setVerticalSpacing(spacing)

    @settable("h_spacing")
    def setHorizontalSpacing(self, spacing: float) -> None:
        layout = self.anchorLayout()
        layout.setHorizontalSpacing(spacing)

    def addSideAnchorsByName(self, child: Graphic, obj: Graphic,
                             orient: Qt.Orientations) -> None:
        layout = self.anchorLayout()
        layout.addAnchors(obj, child, orient)

    def addCornerAnchorByName(self, child: Graphic, obj: Graphic,
                              corner1: Qt.Corner, corner2: Qt.Corner) -> None:
        layout = self.anchorLayout()
        layout.addCornerAnchors(obj, corner2, child, corner1)

    def addEdgeAnchorByName(self, child: Graphic, obj: Graphic,
                            edge1: Qt.AnchorPoint, edge2: Qt.AnchorPoint
                            ) -> None:
        layout = self.anchorLayout()
        layout.addAnchor(obj, edge2, child, edge1)

    def _parseSideRel(self, rel: str) -> tuple[str, Qt.AnchorPoint]:
        if "." not in rel:
            raise ValueError(f"Can't use anchor point: {rel}")
        name, apoint = rel.rsplit(".", 1)
        return name, converters.anchorPointConverter(apoint)

    def _parseCornerRel(self, rel: str) -> tuple[str, Qt.Corner]:
        if "." not in rel:
            raise ValueError(f"Can't use anchor point: {rel}")
        name, corner = rel.rsplit(".", 1)
        return name, converters.cornerConverter(corner)

    @settable("anchors:fill")
    def setChildFillAnchors(self, child: Graphic, name: str) -> None:
        self._try(self.addSideAnchorsByName, child, name,
                  Qt.Horizontal | Qt.Vertical)

    @settable("anchors:h_fill")
    def setChildHorizontalFillAnchors(self, child: Graphic, name: str) -> None:
        self._try(self.addSideAnchorsByName, child, name, Qt.Horizontal)

    @settable("anchors:v_fill")
    def setChildVerticalFillAnchors(self, child: Graphic, name: str) -> None:
        self._try(self.addSideAnchorsByName, child, name, Qt.Vertical)

    @settable("anchor:top_left")
    def setChildTopLeftAnchor(self, child: Graphic, rel: str) -> None:
        name, corner = self._parseCornerRel(rel)
        self._try(self.addCornerAnchorByName, child, name,
                  Qt.TopLeftCorner, corner)

    @settable("anchor:top_right")
    def setChildTopRightAnchor(self, child: Graphic, rel: str) -> None:
        name, corner = self._parseCornerRel(rel)
        self._try(self.addCornerAnchorByName, child, name,
                  Qt.TopRightCorner, corner)

    @settable("anchor:bottom_left")
    def setChildBottomLeftAnchor(self, child: Graphic, rel: str) -> None:
        name, corner = self._parseCornerRel(rel)
        self._try(self.addCornerAnchorByName, child, name,
                  Qt.BottomLeftCorner, corner)

    @settable("anchor:bottom_right")
    def setChildBottomRightAnchor(self, child: Graphic, rel: str) -> None:
        name, corner = self._parseCornerRel(rel)
        self._try(self.addCornerAnchorByName, child, name,
                  Qt.BottomRightCorner, corner)

    @settable("anchor:left")
    def setChildLeftAnchor(self, child: Graphic, rel: str) -> None:
        name, edge = self._parseSideRel(rel)
        self._try(self.addEdgeAnchorByName, child, name, Qt.AnchorLeft, edge)

    @settable("anchor:top")
    def setChildTopAnchor(self, child: Graphic, rel: str) -> None:
        name, edge = self._parseSideRel(rel)
        self._try(self.addEdgeAnchorByName, child, name, Qt.AnchorTop, edge)

    @settable("anchor:right")
    def setChildRightAnchor(self, child: Graphic, rel: str) -> None:
        name, edge = self._parseSideRel(rel)
        self._try(self.addEdgeAnchorByName, child, name, Qt.AnchorRight, edge)

    @settable("anchor:bottom")
    def setChildBottomAnchor(self, child: Graphic, rel: str) -> None:
        name, edge = self._parseSideRel(rel)
        self._try(self.addEdgeAnchorByName, child, name, Qt.AnchorBottom, edge)

    @settable("anchor:h_center")
    def setChildHorizontalCenterAnchor(self, child: Graphic, rel: str) -> None:
        name, edge = self._parseSideRel(rel)
        self._try(self.addEdgeAnchorByName, child, name,
                  Qt.AnchorHorizontalCenter, edge)

    @settable("anchor:v_center")
    def setChildVerticalCenterAnchor(self, child: Graphic, rel: str) -> None:
        name, edge = self._parseSideRel(rel)
        self._try(self.addEdgeAnchorByName, child, name,
                  Qt.AnchorVerticalCenter, edge)


@graphictype("placeholder_graphic")
class PlaceholderGraphic(Graphic):
    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        r = self.rect()
        painter.setPen(Qt.red)
        painter.drawRect(r)
        # painter.drawLine(r.topLeft(), r.bottomRight())
        # painter.drawLine(r.bottomLeft(), r.topRight())


@graphictype("busy_graphic")
class BusyGraphic(Graphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._timestep = 0
        self._speed = 1
        self._color = QtGui.QColor.fromRgbF(1.0, 1.0, 1.0)
        self._timer = QtCore.QTimer()
        self._timer.setInterval(100)
        self._timer.timeout.connect(self.frameAdvance)

    def color(self) -> QtGui.QColor:
        return self._color

    def setColor(self, color: QtGui.QColor) -> None:
        self._color = color
        self.update()

    def speed(self) -> int:
        return self._speed

    def setSpeed(self, speed: int) -> None:
        self._speed = speed
        if not speed:
            self._timer.stop()
        elif not self._timer.isActive():
            self._timer.start()

    def interval(self) -> int:
        return self._timer.interval()

    def setInterval(self, interval_ms: int) -> None:
        self._timer.setInterval(interval_ms)

    def isActive(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def frameAdvance(self):
        self._timestep += 1
        self.update()

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        drawFadingRings(painter, self.rect(), timestep=self._timestep,
                        color=self._color)


@graphictype("svg")
class SvgGraphic(Graphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._renderer: Optional[QtSvg.QSvgRenderer] = None
        self._alignment = Qt.AlignCenter
        self.setCacheMode(self.ItemCoordinateCache)
        self._color: Optional[QtGui.QColor] = None
        self._role: Optional[QtGui.QPalette.ColorRole] = None

    def monochromeColor(self) -> Optional[QtGui.QColor]:
        return self._color

    @settable("color", argtype=QtGui.QColor)
    def setMonochromeColor(self, color: QtGui.QColor) -> None:
        self._color = color
        self.update()

    def monochromeRole(self) -> Optional[QtGui.QPalette.ColorRole]:
        return self._role

    @settable("color_role", argtype=QtGui.QPalette.ColorRole)
    def setMonochromeRole(self, role: QtGui.QPalette.ColorRole) -> None:
        self._role = role
        self.update()

    def svgRenderer(self) -> Optional[QtSvg.QSvgRenderer]:
        return self._renderer

    def alignment(self) -> Qt.Alignment:
        return self._alignment

    @settable(argtype=Qt.Alignment)
    def setAlignment(self, align: Qt.Alignment) -> None:
        self._alignment = align
        self.update()

    @settable()
    def setGlyph(self, name: str) -> None:
        from .glyphs import glyphs
        self._renderer = glyphs().renderer(name)
        self.update()

    def effectiveSizeHint(self, which: Qt.SizeHintRole, constraint=None):
        if which == Qt.PreferredSize:
            svg = self.svgRenderer()
            if svg:
                return svg.defaultSize()
        return constraint

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        svg = self.svgRenderer()
        if not svg:
            return

        rect = self.rect()
        src_size = svg.defaultSize()
        dest_size = rect.size()
        scale = min(dest_size.width() / src_size.width(),
                    dest_size.height() / src_size.height())
        size = src_size * scale
        svg_rect = styling.alignedRectF(
            self.layoutDirection(), self.alignment(), size, rect
        )
        svg.render(painter, svg_rect)

        color = self.monochromeColor()
        role = self.monochromeRole()
        if color or role:
            if not color:
                color = self.palette().color(role)
            painter.setCompositionMode(painter.CompositionMode_SourceAtop)
            painter.fillRect(svg_rect, color)


@graphictype("icon_graphic")
class IconGraphic(Graphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._icon: Optional[QtGui.QIcon] = None
        self._alignment: Qt.Alignment = Qt.AlignCenter

    @settable()
    def setGlyph(self, name: str) -> None:
        from .glyphs import glyphs
        self._icon = glyphs.icon(name)

    @settable()
    def setHoudiniIcon(self, name: str) -> None:
        import hou
        self._icon = hou.qt.Icon(name)

    @settable()
    def setIconPath(self, path: Union[str, pathlib.Path]):
        self._icon = QtGui.QIcon(str(path))

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        rect = self.rect()
        self._icon.paint(painter, rect.toAlignedRect(),
                         alignment=self._alignment)


@graphictype("marquee_graphic")
class MarqueeGraphic(Graphic):
    class State(enum.Enum):
        stopped = enum.auto()
        at_start = enum.auto()
        rolling_forward = enum.auto()
        at_end = enum.auto()
        rolling_backward = enum.auto()

    class ReturnMode(enum.Enum):
        reverse = enum.auto()
        instant = enum.auto()
        fade = enum.auto()
        rollover = enum.auto()

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self.setClipping(True)
        self._group = Graphic(self)
        self._text1 = StringGraphic(self._group)
        self._text2 = StringGraphic(self._group)
        self._content = self._text1

        self._pretimer = QtCore.QTimer(self)
        self._pretimer.setInterval(2000)
        self._pretimer.setSingleShot(True)
        self._pretimer.timeout.connect(self._prerollFinished)
        self._posttimer = QtCore.QTimer(self)
        self._posttimer.setInterval(1000)
        self._posttimer.setSingleShot(True)
        self._posttimer.timeout.connect(self._postrollFinished)

        self._msec_per_pixel = 20
        self._roller = QtCore.QPropertyAnimation(self)
        self._roller.setPropertyName(b"pos")
        self._roller.finished.connect(self._rollFinished)
        self._roller.setEasingCurve(QtCore.QEasingCurve.Linear)
        self._roller.setTargetObject(self._group)
        self._state = self.State.stopped
        self._rollover_gap = 20.0
        self._return_mode = self.ReturnMode.rollover

        self.geometryChanged.connect(self.restart)
        self.resetContent()

    def text(self) -> str:
        return self._text1.text()

    @settable()
    def setText(self, text: str) -> None:
        self._text1.setText(text)
        self._text2.setText(text)
        self.resetContent()

    def foregroundRole(self) -> QtGui.QPalette.ColorRole:
        return self._text1.foregroundRole()

    @settable()
    def setForegroundRole(self, role: QtGui.QPalette.ColorRole) -> None:
        self._text1.setForegroundRole(role)
        self._text2.setForegroundRole(role)

    def foregroundColor(self) -> QtGui.QColor:
        return self._text1.foregroundColor()

    def setForegroundColor(self, color: QtGui.QColor) -> None:
        self._text1.setForegroundColor(color)
        self._text2.setForegroundColor(color)

    def returnMode(self) -> MarqueeGraphic.ReturnMode:
        return self._return_mode

    def setReturnMode(self, mode: MarqueeGraphic.ReturnMode) -> None:
        self._return_mode = mode
        self.restart()

    def rolloverGap(self) -> float:
        return self._rollover_gap

    @settable()
    def setRolloverGap(self, gap: float) -> None:
        self._rollover_gap = gap
        self.restart()

    def shouldAnimate(self) -> bool:
        size = self.size()
        csize = self._text1.effectiveSizeHint(
            Qt.PreferredSize, QtCore.QSizeF(-1, size.height())
        )
        return csize.width() > self.size().width()

    def resetContent(self) -> None:
        size = self.size()
        csize = self._text1.effectiveSizeHint(
            Qt.PreferredSize, QtCore.QSizeF(-1, size.height())
        )
        r1 = QtCore.QRectF(QtCore.QPointF(0, 0), csize)
        r2 = QtCore.QRectF(r1).translated(r1.width() + self._rollover_gap, 0)
        self._group.setPos(0, 0)
        self._text1.setGeometry(r1)
        self._text2.setGeometry(r2)

        is_rollover = self._return_mode == self.ReturnMode.rollover
        self._text2.setVisible(is_rollover and self.shouldAnimate())

    def delayAtStart(self) -> int:
        return self._pretimer.interval()

    @settable()
    def setDelayAtStart(self, msecs: int) -> None:
        self._pretimer.setInterval(msecs)

    def delayAtEnd(self) -> int:
        return self._posttimer.interval()

    @settable()
    def setDelayAtEnd(self, msecs: int) -> None:
        self._posttimer.setInterval(msecs)

    def delayPerPixel(self) -> int:
        return self._msec_per_pixel

    @settable()
    def setDelayPerPixel(self, msecs: int) -> None:
        self._msec_per_pixel = msecs

    def easingCurve(self) -> QtCore.QEasingCurve:
        return self._roller.easingCurve()

    def setEasingCurve(self, curve: QtCore.QEasingCurve) -> None:
        self._roller.setEasingCurve(curve)

    def restart(self):
        self._pretimer.stop()
        self._posttimer.stop()
        self._roller.stop()

        self.resetContent()

        if not self._group.isVisible() or not self._group.opacity():
            self._group.fadeIn()
        self._state = self.State.at_start

        if self.shouldAnimate():
            self._pretimer.start()

    def stop(self) -> None:
        self._pretimer.stop()
        self._posttimer.stop()
        self._roller.stop()
        self._state = self.State.stopped
        self._text1.setPos(0, 0)

    def resizeEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self.restart()

    def showEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self.restart()

    def hideEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self.stop()

    def _animateRoll(self, backwards=False) -> None:
        is_rollver = self._return_mode == self.ReturnMode.rollover
        content = self._group if is_rollver else self._text1
        mode = self._return_mode
        delta_width = self.size().width() - self._text1.size().width()
        if mode == self.ReturnMode.rollover:
            delta_width = self._text1.size().width() + self._rollover_gap
            target_pos = QtCore.QPointF(-delta_width, 0)
        elif backwards:
            target_pos = QtCore.QPointF(0, 0)
        else:
            target_pos = QtCore.QPointF(-delta_width, 0)

        self._roller.setStartValue(content.pos())
        self._roller.setEndValue(target_pos)

        if backwards:
            duration = self._return_msec
        else:
            duration = int(delta_width * self._msec_per_pixel)
        self._roller.setDuration(duration)

        self._state = (self.State.rolling_backward if backwards
                       else self.State.rolling_forward)
        self._roller.start()

    def _prerollFinished(self) -> None:
        self._animateRoll()

    def _rollFinished(self) -> None:
        self._state = self.State.at_end
        if self._return_mode == self.ReturnMode.rollover:
            self.restart()
        elif self._state == self.State.rolling_forward:
            self._posttimer.start()
        elif self._state == self.State.rolling_backward:
            self.restart()

    def _postrollFinished(self) -> None:
        mode = self._return_mode
        if mode == self.ReturnMode.reverse:
            self._animateRoll(backwards=True)
        elif mode == self.ReturnMode.instant:
            self.restart()
        elif mode == self.ReturnMode.fade:
            self._group.fadeOut(callback=self.restart)


@graphictype("clickable")
class ClickableGraphic(Graphic):
    clicked = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._handlers: dict[QtCore.QEvent.Type, config.PythonValue] = {}
        self._button_down = False
        self._pressed = False

    def isDown(self) -> bool:
        return self._button_down

    @settable()
    def setOnClick(self, code: Union[str, CodeType]) -> None:
        expr = config.PythonValue(code)
        self._handlers[QtCore.QEvent.GraphicsSceneMouseRelease] = expr

    def sceneEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> bool:
        expr = self._handlers.get(event.type())
        if expr:
            expr.evaluate(None, self.localEnv())
        return super().sceneEvent(event)

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        super().mousePressEvent(event)
        event.accept()
        self._button_down = True
        self._pressed = True
        self._down()

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        super().mouseReleaseEvent(event)
        self._button_down = False
        self._pressed = False
        self._up()
        if self.rect().contains(event.pos()):
            self._clicked()

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        pos = event.pos()
        inside = self.rect().contains(pos)
        if self._pressed and not inside:
            self._pressed = False
            self._outside(pos)
        elif inside and not self._pressed:
            self._pressed = True
            self._inside(pos)

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self._body.setHighlighted(True)
        self.update()

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self._body.setHighlighted(False)
        self.update()

    def _down(self) -> None:
        return

    def _up(self):
        return

    def _clicked(self) -> None:
        self.clicked.emit()

    def _inside(self, pos: QtCore.QPointF) -> None:
        return

    def _outside(self, pos: QtCore.QPointF) -> None:
        return


@graphictype("area")
class AreaGraphic(Graphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._pen: Optional[QtGui.QPen] = None
        self._border_color: Optional[QtGui.QColor] = None
        self._border_role: QtGui.QPalette.ColorRole = QtGui.QPalette.NoRole
        self._border_width = 1.0
        self._brush: Optional[QtGui.QBrush] = None
        self._fill_tint: Optional[QtGui.QColor] = None
        self._fill_tint_amount = 0.5
        self._fill_role = QtGui.QPalette.NoRole
        self._hilited = False

    def pen(self) -> Optional[QtGui.QPen]:
        return self._pen

    def setPen(self, pen: QtGui.QPen) -> None:
        self._pen = pen
        self.update()

    def borderColor(self) -> Optional[QtGui.QColor]:
        return self._border_color

    @settable(argtype=QtGui.QColor)
    def setBorderColor(self, color: QtGui.QColor):
        pen = self.pen()
        if not pen or pen is Qt.NoPen:
            pen = QtGui.QPen(color)
        else:
            pen.setColor(color)
        self._pen = pen
        self.update()

    def borderRole(self) -> QtGui.QPalette.ColorRole:
        return self._border_role

    @settable(argtype=QtGui.QPalette.ColorRole)
    def setBorderRole(self, role: QtGui.QPalette.ColorRole) -> None:
        self._border_role = role
        self.update()

    def borderWidth(self) -> float:
        return self._border_width

    @settable()
    def setBorderWidth(self, width: float) -> None:
        self._border_width = width
        self.update()

    def effectiveBorderPen(self) -> QtGui.QPen:
        if self._pen:
            return QtGui.QPen(self._pen)

        color = self._border_color
        if not color:
            role = self._border_role
            if role == QtGui.QPalette.NoRole:
                return Qt.NoPen
            color = self.palette().color(role)

        width = self._border_width
        return QtGui.QPen(color, width)

    def brush(self) -> QtGui.QBrush:
        return self._brush

    def setBrush(self, brush: QtGui.QBrush):
        self._brush = QtGui.QBrush(brush)

    def fillColor(self) -> Optional[QtGui.QColor]:
        if self._brush:
            return self._brush.color()

    @settable("bg_color", argtype=QtGui.QColor)
    def setFillColor(self, color: QtGui.QColor) -> None:
        self._brush = QtGui.QBrush(color)
        self.update()

    fill = QtCore.Property(QtGui.QColor, fillColor, setFillColor)

    def fillRole(self) -> QtGui.QPalette.ColorRole:
        return self._fill_role

    @settable("bg_role", argtype=QtGui.QPalette.ColorRole)
    def setFillRole(self, role: QtGui.QPalette.ColorRole) -> None:
        self._fill_role = role
        self.update()

    def setHighlighted(self, hilited: bool) -> None:
        self._hilited = hilited
        self.update()

    def highlightColor(self) -> QtGui.QColor:
        return self.effectiveFillColor().lighter(120)

    @settable("bg_tint", argtype=QtGui.QColor)
    def setFillTintColor(self, color: QtGui.QColor) -> None:
        self._fill_tint = color
        self.update()

    @settable("bg_tint_amount")
    def setFillTintAmount(self, amount: float) -> None:
        self._fill_tint_amount = amount
        self.update()

    def effectiveFillColor(self) -> Optional[QtGui.QColor]:
        if self._brush:
            color = self._brush.color()
        elif self._fill_role != QtGui.QPalette.NoRole:
            color = self.palette().color(self._fill_role)
        else:
            return None
        if self._fill_tint and self._fill_tint_amount:
            color = themes.blend(color, self._fill_tint, self._fill_tint_amount)
        return color

    def effectiveBrush(self) -> QtGui.QBrush:
        brush = self._brush
        if not brush:
            color = self.effectiveFillColor()
            if color:
                brush = QtGui.QBrush(color)
            else:
                brush = Qt.NoBrush
        return brush

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     r = self.rect()
    #     if self.isSelected():
    #         painter.fillRect(r, Qt.yellow)

        # painter.setPen(Qt.green)
        # painter.drawRect(r)


@graphictype("flip_container")
class FlipContainerGraphic(AreaGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._flippables: list[Graphic] = []
        self._current: Optional[Graphic] = None
        self._anim_group = QtCore.QSequentialAnimationGroup(self)
        self._anim_group.finished.connect(self._reset)
        self._duration = 400
        self._flipx = 0.0
        self._flipy = 90.0
        self._flipping = False

        self.geometryChanged.connect(self._repositionContents)
        self._repositionContents()

    def _repositionContents(self) -> None:
        rect = self.rect()
        ctr = rect.center()
        for item in self._flippables:
            item.setPos(ctr)
            item.setXYRotation(QtCore.QPointF())

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        super().mousePressEvent(event)
        if self._flipping:
            return
        self.goToNext()

    def addChild(self, item: QtWidgets.QGraphicsItem):
        super().addChild(item)
        if isinstance(item, Graphic):
            first = not self._flippables
            item.setVisible(first)
            self._flippables.append(item)
            if first:
                self._current = item
        self._repositionContents()

    def count(self) -> int:
        return len(self._flippables)

    @settable()
    def setCurrent(self, item: Union[Graphic, str, int]) -> None:
        if isinstance(item, int):
            graphic = self._flippables[item]
        elif isinstance(item, Graphic):
            if item not in self._flippables:
                raise ValueError(f"{item!r} is not a child of {self!r}")
            graphic = item
        elif isinstance(item, str):
            for i, graphic in enumerate(self._flippables):
                if graphic.objectName() == item:
                    break
            else:
                raise NameError(f"No child named {item!r} in {self!r}")
        else:
            raise TypeError(f"Can't set current item to {item!r}")

        previous = self._current
        self._current = graphic
        if previous:
            self._transition(previous, graphic)
        else:
            self._reset()

    def _reset(self):
        self._anim_group.stop()
        self._flipping = False
        current = self._current
        for gr in self._flippables:
            gr.setVisible(gr is current)
            gr.setXYRotation(QtCore.QPointF())

    def goToNext(self) -> None:
        if not self._flippables:
            return
        current = self._current
        ix = self._flippables.index(current) + 1
        if ix >= self.count():
            ix = 0
        self.setCurrent(ix)

    def goToPrevious(self) -> None:
        if not self._flippables:
            return
        current = self._current
        ix = self._flippables.index(current) - 1
        if ix < 0:
            ix = self.count() - 1
        self.setCurrent(ix)

    def _switch(self, from_graphic: Graphic, to_graphic: Graphic) -> None:
        from_graphic.hide()
        to_graphic.show()

    def _transition(self, from_graphic: Graphic, to_graphic: Graphic
                    ) -> None:
        self._flipping = True
        duration = self._duration // 2
        group = self._anim_group
        group.stop()
        from_graphic.setXYRotation(QtCore.QPointF())
        for g in self._flippables:
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

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        r = self.rect()
        painter.fillRect(r, QtGui.QColor("#405060"))


@graphictype("shuffle_container")
class ShuffleContainerGraphic(AreaGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._deck: list[Graphic] = []
        self._current_index: int = 0
        self._current: Optional[Graphic] = None
        self._anim_group = QtCore.QParallelAnimationGroup(self)
        self._anim_group.finished.connect(self._reset)
        self._show_before = 1
        self._show_after = 1
        self._duration = 400
        self._delta_x = 20.0
        self._delta_y = 10.0
        self._delta_blur = 10.0
        self._delta_transparency = 0.33
        self._flipping = False

        self.geometryChanged.connect(self._repositionContents)
        self._repositionContents()

    def addChild(self, item: QtWidgets.QGraphicsItem):
        super().addChild(item)
        if isinstance(item, Graphic) and not item in self._deck:
            self._deck.append(item)

    def count(self) -> int:
        return len(self._deck)

    def _repositionContents(self) -> None:
        cur_ix = self._current_index
        for i, item in enumerate(self._deck):
            delta = i - cur_ix
            visible = ((delta < 0 and abs(delta) <= self._show_before) or
                       (0 <= delta <= self._show_after))
            item.setVisible(visible)
            blur = item.blurEffect()
            if visible:
                item.setPos(self._delta_x * delta, self._delta_y * delta)
                blur.setBlurRadius(self._delta_blur * abs(delta))
                blur.setEnabled(True)
                item.setOpacity(self._delta_transparency ** abs(delta))
            else:
                item.hide()
                blur.setEnabled(False)
                item.setOpacity(1.0)
                item.setBlurRadius(0.0)

    def goToNext(self) -> None:
        if not self._deck:
            return
        ix = self._current_index + 1
        if ix >= self.count():
            ix = 0
        self.setCurrent(ix)

    def goToPrevious(self) -> None:
        if not self._deck:
            return
        ix = self._current_index - 1
        if ix < 0:
            ix = self.count() - 1
        self.setCurrent(ix)


@graphictype("dot_graphic")
class DotGraphic(AreaGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._radius = 4.0

    def radius(self) -> float:
        return self._radius

    @settable()
    def setRadius(self, radius: float) -> None:
        self._radius = radius
        self.update()

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        rect = self.rect()
        radius = self._radius
        if not radius:
            radius = min(rect.width(), rect.height()) / 2.0
        painter.setBrush(self.effectiveBrush())
        painter.setPen(self.effectiveBorderPen())
        painter.drawEllipse(rect.center(), radius, radius)


@graphictype("rectangle")
class RectangleGraphic(AreaGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._corner_radius = 0.0

    @settable()
    def setCornerRadius(self, radius: float) -> None:
        self._corner_radius = radius
        self.update()

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        rect = self.rect()
        radius = self._corner_radius
        painter.setBrush(self.effectiveBrush())
        painter.setPen(self.effectiveBorderPen())
        if radius > 0.0:
            painter.drawRoundedRect(rect, radius, radius)
        else:
            painter.drawRect(rect)


class AbstractTextGraphic(RectangleGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._fg_role = styling.VALUE_ROLE
        self._color: Optional[QtGui.QColor] = None
        self._margins = QtCore.QMarginsF(0, 0, 0, 0)
        self._text_tint: Optional[QtGui.QColor] = None
        self._text_tint_amount = 0.5

    def font(self) -> QtGui.QFont:
        return self._item.font()

    def setFont(self, font: QtGui.QFont):
        super().setFont(font)
        self.prepareGeometryChange()
        self._item.setFont(font)
        self._updateContents()
        self.updateGeometry()

    @settable()
    def setBold(self, bold: bool) -> None:
        font = self.font()
        font.setBold(bold)
        self.setFont(font)

    @settable()
    def setItalic(self, italic: bool) -> None:
        font = self.font()
        font.setItalic(italic)
        self.setFont(font)

    def changeEvent(self, event: QtCore.QEvent):
        if event.type() == event.PaletteChange:
            self._updateTextColor()

    def margins(self) -> QtCore.QMarginsF:
        return self._margins

    @settable("margins", argtype=QtCore.QMarginsF)
    def setMargins(self, left: Union[QtCore.QMarginsF, float], top=0.0,
                   right=0.0, bottom=0.0) -> None:
        self._margins = converters.marginsArgs(left, top, right, bottom)
        self._updateContents()

    def fontSize(self) -> int:
        return self.font().pixelSize()

    def setFontSize(self, size: int) -> None:
        font = self.font()
        font.setPixelSize(size)
        self.setFont(font)
        self.update()

    textSize = QtCore.Property(int, fontSize, setFontSize)

    @settable("text_tint", argtype=QtGui.QColor)
    def setTextTintColor(self, color: QtGui.QColor) -> None:
        self._text_tint = color
        self._updateTextColor()

    @settable("text_tint_amount")
    def setTextTintAmount(self, amount: float) -> None:
        self._text_tint_amount = amount
        self._updateTextColor()

    def textAlignment(self) -> Qt.Alignment:
        raise NotImplementedError

    @settable("text_align", argtype=Qt.Alignment)
    def setTextAlignment(self, align: Qt.Alignment) -> None:
        raise NotImplementedError

    def foregroundRole(self) -> QtGui.QPalette.ColorRole:
        return self._fg_role

    @settable("text_role", argtype=QtGui.QPalette.ColorRole)
    def setForegroundRole(self, role: QtGui.QPalette.ColorRole):
        self._fg_role = role
        self._updateTextColor()

    def foregroundColor(self) -> Optional[QtGui.QColor]:
        return self._color

    @settable("text_color", argtype=QtGui.QColor)
    def setForegroundColor(self, color: QtGui.QColor) -> None:
        self._color = color
        self._updateTextColor()

    def effectiveTextColor(self) -> QtGui.QColor:
        color = self._color
        if not color:
            color = self.palette().color(self._fg_role)
        if self._text_tint and self._text_tint_amount:
            color = themes.blend(color, self._text_tint, self._text_tint_amount)
        return color

    def _updateTextColor(self) -> None:
        raise NotImplementedError


@graphictype("string_graphic")
class StringGraphic(AbstractTextGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._text = ""
        self._text_width = 0.0
        self._text_height = 0.0
        self._item = QtWidgets.QGraphicsSimpleTextItem(self)
        self._alignment = Qt.AlignLeft
        self._elide_mode: Qt.TextElideMode = Qt.ElideNone

        self.geometryChanged.connect(self._updateContents)
        self._updateTextWidth()
        self._updateContents()

    def text(self) -> str:
        return self._text

    @settable()
    def setText(self, text: str) -> None:
        self.prepareGeometryChange()
        self._text = text
        self._updateTextWidth()
        self._updateContents()
        self.updateGeometry()

    def textAlignment(self) -> Qt.Alignment:
        return self._alignment

    @settable("align", argtype=Qt.Alignment)
    def setTextAlignment(self, align: Qt.Alignment) -> None:
        self._alignment = align
        self._updateContents()

    def font(self) -> QtGui.QFont:
        return self._item.font()

    def textHeight(self) -> float:
        return self._item.boundingRect().height() - 4.0

    def elideMode(self) -> Qt.TextElideMode:
        return self._elide_mode

    @settable(argtype=Qt.TextElideMode)
    def setElideMode(self, elide: Qt.TextElideMode) -> None:
        self.prepareGeometryChange()
        self._elide_mode = elide
        self._updateContents()
        self.updateGeometry()

    def _updateTextWidth(self) -> None:
        fm = QtGui.QFontMetricsF(self._item.font())
        self._text_width = fm.horizontalAdvance(self._text)

    def _updateContents(self):
        rect = self.rect().marginsRemoved(self.margins())
        width = rect.width()
        text_width = self._text_width
        elide = self._elide_mode
        text = self._text
        if text_width > width and elide != Qt.ElideNone:
            fm = QtGui.QFontMetricsF(self._item.font())
            text = fm.elidedText(text, elide, width)
            text_width = width
        self._item.setText(text)

        text_size = QtCore.QSizeF(text_width, self.textHeight())
        text_rect = styling.alignedRectF(
            self.layoutDirection(), self._alignment, text_size, rect
        )
        self._item.setPos(text_rect.x(), text_rect.y() - 2.0)
        self._updateTextColor()

    def _updateTextColor(self) -> None:
        color = self.effectiveTextColor()
        self._item.setBrush(color)

    def implicitSize(self) -> QtCore.QSizeF:
        text = self.text()
        if not text:
            return QtCore.QSizeF()

        ms = self.margins()
        fm = QtGui.QFontMetricsF(self.font())
        width = fm.horizontalAdvance(text) + ms.left() + ms.right()
        height = self.textHeight() + ms.top() + ms.bottom()
        return QtCore.QSizeF(width, height)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = ...
                 ) -> QtCore.QSizeF:
        if which in (Qt.PreferredSize, Qt.MinimumSize):
            size = self.implicitSize()
            if constraint.width() > size.width():
                size.setWidth(constraint.width())
            return size
        return constraint

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     super().paint(painter, option, widget)
    #     rect = self.rect().marginsRemoved(self._margins)
    #     # painter.setPen(Qt.blue)
    #     # painter.drawRect(rect)
    #     if not rect.isValid():
    #         return
    #
    #     color = self.effectiveTextColor()
    #     font = self.font()
    #     text = self._text
    #     width = self._text_width
    #     if width > rect.width() and self._elide_mode != Qt.ElideNone:
    #         fm = QtGui.QFontMetricsF(font)
    #         text = fm.elidedText(text, self._elide_mode, rect.width())
    #
    #     painter.setFont(font)
    #     painter.setPen(color)
    #     painter.drawText(rect, self._alignment, text)


@graphictype("text_graphic")
class TextGraphic(AbstractTextGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._alignment = Qt.AlignLeft | Qt.AlignVCenter
        self._text_selectable = True
        self._links_clickable = True
        self._item = QtWidgets.QGraphicsTextItem(self)
        self._item.linkActivated.connect(self.linkClicked)
        self._updateInteractionFlags()

        doc = self._item.document()
        doc.setDefaultFont(self.font())
        doc.setUndoRedoEnabled(False)
        doc.setDocumentMargin(0)

        self.setHasHeightForWidth(True)

        self.geometryChanged.connect(self._updateContents)
        self._updateContents()

    def document(self) -> QtGui.QTextDocument:
        return self._item.document()

    def setDocument(self, doc: QtGui.QTextDocument) -> None:
        self._item.setDocument(doc)
        self._updateContents()

    @settable("align", argtype=Qt.Alignment)
    def setTextAlignment(self, align: Qt.Alignment):
        self._alignment = align
        self._updateContents()

    def plainText(self) -> str:
        return self._item.toPlainText()

    @settable("text")
    def setPlainText(self, text: str):
        self.prepareGeometryChange()
        self._item.setPlainText(str(text))
        self.updateGeometry()

    def html(self) -> str:
        return self._item.toHtml()

    @settable("html")
    def setHtml(self, html: str):
        self.prepareGeometryChange()
        self._item.setHtml(str(html))
        self.updateGeometry()

    def _updateContents(self):
        self.document().setDefaultTextOption(QtGui.QTextOption(self._alignment))
        rect = self.rect().marginsRemoved(self.margins())
        height = rect.height()
        self._item.setTextWidth(rect.width())
        text_height = self.document().size().height()
        y = 0.0
        if text_height < height:
            diff = height - text_height
            if self._alignment & Qt.AlignVCenter:
                y = diff / 2.0
            elif self._alignment & Qt.AlignBottom:
                y = diff
        self._item.setPos(0, y)
        self._updateTextColor()

    def _updateTextColor(self) -> None:
        color = self.effectiveTextColor()
        self._item.setDefaultTextColor(color)

    def sizeHint(self, which: Qt.SizeHint,
                 constraint: QtCore.QSizeF = ...) -> QtCore.QSizeF:
        # fm = QtGui.QFontMetricsF(self.font())
        ms = self.margins()
        size = QtCore.QSizeF(constraint)
        if which == Qt.PreferredSize:
            doc = QtGui.QTextDocument()
            doc.setDocumentMargin(0)
            doc.setHtml(self.document().toHtml())
            # saved_width = doc.textWidth()
            if constraint.width() >= 0:
                w = max(0.0, constraint.width() - ms.left() - ms.right())
                doc.setTextWidth(w)
                size = QtCore.QSizeF(constraint.width(), doc.size().height())
            else:
                size = doc.size()
            # doc.setTextWidth(saved_width)
        return size

    @settable()
    def setTextSelectable(self, selectable: bool) -> None:
        self._text_selectable = selectable
        self._updateInteractionFlags()

    @settable()
    def setLinksClickable(self, clickable: bool) -> None:
        self._links_clickable = clickable
        self._updateInteractionFlags()

    def _updateInteractionFlags(self) -> None:
        flags = Qt.NoTextInteraction
        if self._text_selectable:
            flags |= Qt.TextSelectableByMouse
        if self._links_clickable:
            flags |= Qt.LinksAccessibleByMouse
        self._item.setTextInteractionFlags(flags)

    def linkClicked(self, url: str) -> None:
        scene = self.scene()
        if isinstance(scene, GraphicScene):
            scene.linkClicked(url)

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.setPen(Qt.red)
    #     painter.drawRect(self.rect())
    #     painter.setPen(Qt.yellow)
    #     painter.drawRect(self._item.boundingRect())

    #     super().paint(painter, option, widget)
    #     rect = self.rect().marginsRemoved(self._margins)
    #     doc = self._doc
    #     if not rect.isValid():
    #         return
    #
    #     if self._elided:
    #         text = self.plainText()
    #         fm = painter.fontMetrics()
    #         line_space = fm.lineSpacing()
    #         width = int(rect.width())
    #         height = rect.height()
    #         layout = QtGui.QTextLayout(text, painter.font())
    #         layout.beginLayout()
    #         y = 0
    #         while True:
    #             line = layout.createLine()
    #             if not line.isValid():
    #                 break
    #
    #             line.setLineWidth(width)
    #             nextY = y + line_space
    #
    #             if height >= nextY + line_space:
    #                 line.draw(painter, QtCore.QPoint(0, y))
    #                 y = nextY
    #             else:
    #                 last_line = text[line.textStart():]
    #                 elided = fm.elidedText(last_line, Qt.ElideRight, width)
    #                 painter.drawText(QtCore.QPoint(0, y + fm.ascent()), elided)
    #                 layout.createLine()
    #                 break
    #         layout.endLayout()
    #     else:
    #         drawTextDocument(painter, rect, doc, self.palette(),
    #                          color=self.foregroundColor(),
    #                          role=self.foregroundRole())


@graphictype("checkmark_graphic")
class CheckmarkGraphic(Graphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._rect = QtCore.QRectF()
        self._width = 2.0
        self._color: Optional[QtGui.QColor] = None
        self._role = QtGui.QPalette.ButtonText
        self._points: Sequence[QtCore.QPointF] = ()

    @settable(argtype=QtGui.QColor)
    def setLineColor(self, color: QtGui.QColor) -> None:
        self._color = color
        self.update()

    @settable(argtype=QtGui.QPalette.ColorRole)
    def setLineRole(self, role: QtGui.QPalette.ColorRole):
        self._role = role
        self.update()

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        rect = self.rect()
        color = self._color
        if not color:
            color = self.palette().color(self._role)
        painter.setPen(QtGui.QPen(color, self._width))
        if not rect.isValid():
            return
        if rect != self._rect:
            self._points = styling.checkmarkPoints(rect)
            self._rect = rect
        painter.drawPolyline(self._points)


@graphictype("switch_rectangle")
class SwitchRectangleGraphic(RectangleGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._alt_color: Optional[QtGui.QColor] = None
        self._alt_role = QtGui.QPalette.Link
        self._blend = 0.0

    @settable(argtype=QtGui.QColor)
    def setAltColor(self, color: QtGui.QColor) -> None:
        self._alt_color = color
        self.update()

    @settable(argtype=QtGui.QPalette.ColorRole)
    def setAltRole(self, role: QtGui.QPalette.ColorRole) -> None:
        self._alt_role = role
        self.update()

    def blendValue(self) -> float:
        return self._blend

    def setBlendValue(self, blend: float) -> None:
        self._blend = blend
        self.update()

    blend = QtCore.Property(float, blendValue, setBlendValue)

    def animateBlend(self, blend: float, **kwargs) -> None:
        self.animateProperty(b"blend", self.blendValue(), blend, **kwargs)

    def effectiveFillColor(self) -> QtGui.QColor:
        c1 = super().effectiveFillColor()
        if self._alt_color:
            c2 = self._alt_color
        else:
            c2 = self.palette().color(self._alt_role)
        return themes.blend(c1, c2, self._blend)


@graphictype("switch_button")
class SwitchButtonGraphic(ClickableGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._reversed = False
        self._radius = 6.0
        self._inner_margin = 3.0
        self._gap = 2.0
        self._duration = 250
        self._curve = QtCore.QEasingCurve.InOutBack
        self._checkstate = Qt.Unchecked

        self._bg = SwitchRectangleGraphic(self)
        self._bg.setFillRole(QtGui.QPalette.Button)
        self._bg.setAltRole(QtGui.QPalette.Link)

        self._dot = DotGraphic(self)
        self._dot.setRadius(0.0)
        self._dot.setGeometry(0, 0, 16, 16)
        self._dot.setFillRole(QtGui.QPalette.Light)

        self._check = CheckmarkGraphic(self._dot)
        self._check.setLineColor(QtGui.QColor.fromRgbF(0.0, 0.0, 0.0, 0.5))

        shadow = QtWidgets.QGraphicsDropShadowEffect(self._dot)
        shadow.setBlurRadius(10.0)
        shadow.setColor(QtGui.QColor.fromRgbF(0.0, 0.0, 0.0, 0.75))
        shadow.setOffset(0, 2)
        self._dot.setGraphicsEffect(shadow)

        self.geometryChanged.connect(self._updateContents)
        self._updateContents()

    @settable(argtype=QtGui.QColor)
    def setFillColor(self, color: QtGui.QColor) -> None:
        self._bg.setFillColor(color)

    @settable(argtype=QtGui.QPalette.ColorRole)
    def setFillRole(self, role: QtGui.QPalette.ColorRole) -> None:
        self._bg.setFillRole(role)

    @settable(argtype=QtGui.QColor)
    def setAltColor(self, color: QtGui.QColor) -> None:
        self._bg.setAltColor(color)

    @settable(argtype=QtGui.QPalette.ColorRole)
    def setAltRole(self, role: QtGui.QPalette.ColorRole) -> None:
        self._bg.setAltRole(role)

    def checkState(self) -> Qt.CheckState:
        return self._checkstate

    def setCheckState(self, state: Qt.CheckState) -> None:
        animated = not self.animationDisabled()
        old_state = self._checkstate
        if state != old_state:
            self._checkstate = state
            if state == Qt.PartiallyChecked:
                if animated:
                    self._dot.fadeOut()
                else:
                    self._dot.hide()
            else:
                checked = state == Qt.Checked
                if old_state == Qt.PartiallyChecked:
                    self._dot.fadeIn()

                if animated:
                    self._bg.animateBlend(float(checked),
                                          duration=self._duration,
                                          curve=self._curve)
                    self._dot.animateGeometry(self._dotRect(checked),
                                              duration=self._duration,
                                              curve=self._curve)
                else:
                    self._updateContents()

                self._dot.setHighlighted(checked)
                self._check.setVisible(checked)

    def isChecked(self) -> bool:
        return self._checkstate == Qt.Checked

    @settable()
    def setChecked(self, checked: bool) -> None:
        self.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def _down(self) -> None:
        self.setChecked(not self.isChecked())

    def _tick(self) -> None:
        self._activation = self._bg_anim.currentValue()
        self._updateContents()

    def _dotRect(self, checked: bool) -> QtCore.QRectF:
        r = self._subRect()
        im = self._inner_margin
        diam = self._radius * 2
        y = r.y() + im
        x1 = r.x() + im
        x2 = r.right() - im - self._radius * 2
        if self._reversed:
            x = x1 if checked else x2
        else:
            x = x2 if checked else x1
        return QtCore.QRectF(x, y, diam, diam)

    def _updateContents(self) -> None:
        r = self._subRect()
        diam = self._radius * 2
        checked = self.isChecked()
        self._bg.setGeometry(r)
        self._bg.setCornerRadius(r.height() / 2)
        self._bg.setBlendValue(int(checked))

        self._dot.setHighlighted(checked)
        self._dot.setGeometry(self._dotRect(checked))

        cdiam = max(4.0, diam * 0.5)
        inset = diam / 2.0 - cdiam / 2
        check_rect = QtCore.QRectF(inset, inset, cdiam, cdiam)
        self._check.setGeometry(check_rect)
        self._check.setVisible(self.isChecked())

    @settable()
    def setDotRadius(self, radius: float) -> None:
        self.prepareGeometryChange()
        self._radius = radius
        self._updateContents()
        self.updateGeometry()

    def implictSize(self) -> QtCore.QSizeF:
        im = self._inner_margin
        w = self._radius * 4 + im * 2 + self._gap
        h = self._radius * 2 + im * 2
        return QtCore.QSizeF(w, h)

    def _subRect(self) -> QtCore.QRectF:
        rect = self.rect()
        size = self.implictSize()
        return styling.alignedRectF(self.layoutDirection(), Qt.AlignCenter,
                                    size, rect)

    def sizeHint(self, which: Qt.SizeHint, constraint: QtCore.QSizeF = ...
                 ) -> QtCore.QSizeF:
        if which in (Qt.MinimumSize, Qt.PreferredSize, Qt.MaximumSize):
            return self.implictSize()
        return constraint


@graphictype("button")
class ButtonGraphic(ClickableGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._rect = QtCore.QRectF()
        self._body = RectangleGraphic(self)
        self._body.setZValue(2)
        self._body.setFillRole(QtGui.QPalette.Button)
        self._body.setBorderRole(QtGui.QPalette.Link)
        self._body.setBorderWidth(2.0)

        # self._halo = RectangleGraphic(self)
        # self._halo.setZValue(1)

        self._label = StringGraphic(self)
        self._label.setTextAlignment(Qt.AlignCenter)
        self._label.setZValue(3)
        self._label_margins = QtCore.QMarginsF(16, 8, 16, 8)

        self.setAcceptHoverEvents(True)

        self.setText("Button")
        self.setMinimumSize(16, 16)

        # self._body_rect_anim = makeAnim(self._body, b"geometry",
        #                                 curve=outback, duration=300)
        # self._halo_rect_anim = makeAnim(self._halo, b"geometry",
        #                                 curve=outback, duration=300)
        # self._halo_fade_anim = makeAnim(self._halo, b"opacity",
        #                                 curve=QtCore.QEasingCurve.Linear,
        #                                 duration=400)

        self.geometryChanged.connect(self._updateSize)
        self._updateSize()

    def pathElement(self, name: str) -> Optional[QtCore.QObject]:
        if name == "button":
            return self._body
        elif name == "label":
            return self._label
        return super().pathElement(name)

    def buttonRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(self._rect)

    def labelItem(self) -> Graphic:
        return self._label

    def setLabelItem(self, graphic: Graphic) -> None:
        if self._label:
            self._label.deleteLater()
        self._label = graphic
        self._label.setParentItem(self)
        self._label.setZValue(3)
        self._updateSize()
        self.update()

    def labelColor(self) -> Optional[QtGui.QColor]:
        return self._label_color

    @settable(argtype=QtGui.QColor)
    def setLabelColor(self, color: QtGui.QColor) -> None:
        self._label_color = color
        label = self.labelItem()
        if label:
            if isinstance(label, AbstractTextGraphic):
                label.setForegroundColor(color)
            elif isinstance(label, SvgGraphic):
                label.setMonochromeColor(color)

    def labelRole(self) -> QtGui.QPalette.ColorRole:
        return self._label_role

    @settable(argtype=QtGui.QPalette.ColorRole)
    def setLabelRole(self, role: QtGui.QPalette.ColorRole) -> None:
        self._label_role = role
        label = self.labelItem()
        if label:
            if isinstance(label, AbstractTextGraphic):
                label.setForegroundRole(role)
            elif isinstance(label, SvgGraphic):
                label.setMonochromeRole(role)

    @settable(argtype=QtCore.QSizeF)
    def setLabelSize(self, size: QtCore.QSizeF):
        self._label_size = size
        label = self.labelItem()
        if label:
            label.setPreferredSize(size)

    def labelMargins(self) -> QtCore.QMarginsF:
        return self._label_margins

    @settable(argtype=QtCore.QMarginsF)
    def setLabelMargins(self, ms: QtCore.QMarginsF) -> None:
        self._label_margins = ms
        self._updateSize()

    def text(self) -> str:
        return self._label.text()

    @settable()
    def setText(self, text: str) -> None:
        if self._label and isinstance(self._label, StringGraphic):
            self._label.setText(text)
        else:
            self.setLabelItem(self._makeTextLabel(text))

    def labelAlignment(self) -> Qt.Alignment:
        label = self._label
        if isinstance(label, AbstractTextGraphic):
            return label.textAlignment()
        else:
            return self._alignment

    @settable(argtype=Qt.Alignment)
    def setLabelAlignment(self, align: Qt.Alignment):
        self._alignment = align
        label = self._label
        if isinstance(label, AbstractTextGraphic):
            label.setTextAlignment(align)

    def fontSize(self) -> int:
        label = self._label
        if isinstance(label, AbstractTextGraphic):
            return label.fontSize()
        else:
            return self._font_size

    @settable("text_size")
    def setFontSize(self, size: int) -> None:
        self._font_size = size
        label = self._label
        if isinstance(label, AbstractTextGraphic):
            label.setFontSize(size)

    @settable()
    def setGlyph(self, name: str) -> None:
        label = SvgGraphic(self)
        label.setGlyph(name)
        label.setMonochromeRole(self.labelRole())
        self.setLabelItem(label)

    def _updateSize(self) -> None:
        rect = self.rect()
        self._body.setGeometry(rect)
        radius = min(rect.width() / 2, rect.height() / 2, 32.0)
        self._body.setCornerRadius(radius)

        label = self.labelItem()
        if label:
            label_rect = rect.marginsRemoved(self.labelMargins())
            if not isinstance(label, AbstractTextGraphic):
                sz = label.preferredSize()
                label_rect = styling.alignedRectF(
                    self.layoutDirection(), self._alignment, sz, rect
                )
            label.setGeometry(label_rect)
            label.setTransformOriginPoint(label.rect().center())

    # def haloItem(self) -> QtWidgets.QGraphicsRectItem:
    #     return self._halo
    #
    # def _resize(self):
    #     rect = self.rect()
    #     self._body.setGeometry(rect)
    #     label = self.labelItem()
    #
    #
    # def _readyHalo(self) -> QtWidgets.QGraphicsRectItem:
    #     rect_anim = self._halo_rect_anim
    #     if rect_anim.state() == self._halo_rect_anim.Running:
    #         rect_anim.stop()
    #     fade_anim = self._halo_fade_anim
    #     if fade_anim.state() == self._halo_rect_anim.Running:
    #         fade_anim.stop()
    #     halo = self.haloItem()
    #     halo.setOpacity(0.5)
    #     return halo
    #
    # def _animateHaloAdjustment(self, direction: int):
    #     self._readyHalo()
    #     body_anim = self._body_rect_anim
    #     halo_anim = self._halo_rect_anim
    #     in_rad = self.in_radius
    #     out_rad = self.out_radius
    #
    #     r = self.rect()
    #     in_rect = r.adjusted(in_rad, in_rad, -in_rad, -in_rad)
    #     out_rect = r.adjusted(-out_rad, -out_rad, out_rad, out_rad)
    #     if direction > 0:
    #         body_anim.setStartValue(r)
    #         body_anim.setEndValue(in_rect)
    #         halo_anim.setStartValue(r)
    #         halo_anim.setEndValue(out_rect)
    #     else:
    #         body_anim.setStartValue(in_rect)
    #         body_anim.setEndValue(r)
    #         halo_anim.setStartValue(out_rect)
    #         halo_anim.setEndValue(r)
    #
    #     body_anim.start()
    #     halo_anim.start()
    #
    # def _animateClick(self) -> None:
    #     self._label.animateScale(1.0, curve=QtCore.QEasingCurve.OutBack)
    #     body_anim = self._body_rect_anim
    #     body_anim.setStartValue(self._body.geometry())
    #     body_anim.setEndValue(self.rect())
    #     body_anim.start()
    #
    #     cr = self.click_radius
    #     halo = self._readyHalo()
    #     rect_anim = self._halo_rect_anim
    #     rect_anim.setStartValue(halo.geometry())
    #     rect_anim.setEndValue(self.rect().adjusted(-cr, -cr, cr, cr))
    #
    #     fade_anim = self._halo_fade_anim
    #     fade_anim.setStartValue(0.5)
    #     fade_anim.setEndValue(0.0)
    #
    #     rect_anim.start()
    #     fade_anim.start()
    #
    # def _animatePress(self) -> None:
    #     self._label.animateScale(2.0, curve=QtCore.QEasingCurve.OutBack)
    #     self._animateHaloAdjustment(1)
    #
    # def _animateRelease(self) -> None:
    #     self._label.animateScale(1.0, curve=QtCore.QEasingCurve.OutBack)
    #     self._animateHaloAdjustment(-1)

    def sizeHint(self, which: Qt.SizeHintRole, constraint: QtCore.QSizeF = ...
                 ) -> QtCore.QSizeF:
        label = self._label
        if which == Qt.PreferredSize:
            if label:
                ms = self.labelMargins()
                sz = label.effectiveSizeHint(which, constraint)
                w = sz.width() + ms.left() + ms.right()
                h = sz.height() + ms.top() + ms.bottom()
                return QtCore.QSizeF(w, h)
            else:
                return QtCore.QSizeF(200, 30)
        else:
            return constraint


def graphicFromData(data: dict[str, Any], parent: Graphic = None,
                    controller: config.DataController = None) -> Graphic:
    # Make a copy of the data dict so we can pop keys off and not affect
    # the caller
    data = data.copy()
    typename = data.pop("type", "text")
    try:
        graphic_class = graphic_class_registry[typename]
    except KeyError:
        raise Exception(f"Unknown tile type: {typename!r}")
    if not issubclass(graphic_class, Graphic):
        raise TypeError(f"Class {graphic_class} is not a subclass of Graphic")

    graphic = graphic_class.fromData(data, parent=parent, controller=controller)

    size = graphic.effectiveSizeHint(Qt.PreferredSize, QtCore.QSizeF())
    if size.isValid():
        graphic.resize(size)

    return graphic


def rootFromTemplate(data: dict[str, Any], controller: config.DataController
                     ) -> Graphic:
    if not controller:
        raise Exception("No controller")
    controller.clear()
    graphic = graphicFromData(data, controller=controller)
    controller.setRoot(graphic)
    return graphic

from __future__ import annotations
import dataclasses
import pathlib
import time
from collections import defaultdict
from typing import (TYPE_CHECKING, Any, Callable, Collection, Iterable,
                    Optional, Sequence, TypeVar, Union)

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .. import colorutils, config, converters, models, themes, util
from ..config import settable

if TYPE_CHECKING:
    from . import controls


ANIM_DURATION_MS = 250
DEFAULT_EASING_CURVE = QtCore.QEasingCurve.OutCubic
FONT_FAMILY = "Lato"
NUMBER_FAMILY = "Lato"
MONOSPACE_FAMILY = "Source Code Pro"

POOF_ANIM_DURATION = 300
POOF_ANIM_CURVE = QtCore.QEasingCurve.Linear
POOF_OPACITY_CURVE = QtCore.QEasingCurve.InCurve
POOF_SCALE_END = 1.2
POOF_BLUR_END = 30.0

# Type aliases
T = TypeVar("T")
AT = TypeVar("AT")


# Maps Graphic type names (as specified in the JSON) to classes
graphic_class_registry: dict[str, type[Graphic]] = {}


# def dump(obj: QtWidgets.QGraphicsItem, tab=0) -> None:
#     print("  " * tab, type(obj), obj.objectName())
#     for sub in obj.childItems():
#         dump(sub, tab + 1)


def graphictype(*names):
    def fn(cls: T) -> T:
        for name in names:
            if name in graphic_class_registry:
                raise Exception(f"Duplicate graphic type name: {name}")
            graphic_class_registry[name] = cls
        cls.graphic_type_names = names
        config.compileSettables(cls)
        return cls
    return fn


def path_element(argtype: type[Graphic]):
    def fn(method: T) -> T:
        method._element_type = argtype
        return method
    return fn


def makeProxyItem(parent: QtWidgets.QGraphicsItem, widget: QtWidgets.QWidget
                  ) -> QtWidgets.QGraphicsProxyWidget:
    widget.setAttribute(Qt.WA_TranslucentBackground, True)
    gi = QtWidgets.QGraphicsProxyWidget(parent)
    gi.setWidget(widget)
    return gi


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


def scaleAndFadeAnim(item: QtWidgets.QGraphicsItem,
                     scale_to: float, fade_to: float,
                     start_opacity=1.0, end_opacity=0.0, *,
                     duration=ANIM_DURATION_MS,
                     curve=QtCore.QEasingCurve.Linear,
                     parent: QtWidgets.QGraphicsItem = None
                     ) -> QtCore.QParallelAnimationGroup:
    anim_group = QtCore.QParallelAnimationGroup(parent or item)

    scale_anim = makeAnim(item, b"scale", duration=duration, curve=curve)
    scale_anim.setStartValue(item.scale())
    scale_anim.setEndValue(scale_to)
    anim_group.addAnimation(scale_anim)

    fade_anim = makeAnim(item, b"opacity", duration=duration, curve=curve)
    fade_anim.setStartValue(item.opacity())
    fade_anim.setEndValue(fade_to)
    anim_group.addAnimation(fade_anim)

    return anim_group


def poofAnim(item: QtWidgets.QGraphicsItem,
             scale_to: float, fade_to: float, blur_to: float, *,
             duration=POOF_ANIM_DURATION, curve=POOF_ANIM_CURVE,
             parent: QtWidgets.QGraphicsItem = None
             ) -> QtCore.QParallelAnimationGroup:
    anim_group = QtCore.QParallelAnimationGroup(parent or item)

    scale_anim = makeAnim(item, b"scale", duration=duration, curve=curve)
    scale_anim.setStartValue(item.scale())
    scale_anim.setEndValue(scale_to)
    anim_group.addAnimation(scale_anim)

    fade_anim = makeAnim(item, b"opacity", duration=duration,
                         curve=POOF_OPACITY_CURVE)
    fade_anim.setStartValue(item.opacity())
    fade_anim.setEndValue(fade_to)
    anim_group.addAnimation(fade_anim)

    effect = item.graphicsEffect()
    if not effect:
        effect = QtWidgets.QGraphicsBlurEffect()
        effect.setBlurRadius(0.0)
        item.setGraphicsEffect(effect)

    if isinstance(effect, QtWidgets.QGraphicsBlurEffect):
        blur_anim = makeAnim(effect, b"blurRadius", duration=duration,
                             curve=curve)
        blur_anim.setStartValue(effect.blurRadius())
        blur_anim.setEndValue(blur_to)
        anim_group.addAnimation(blur_anim)

    return anim_group


def dataProxyFor(obj: QtCore.QObject) -> QtCore.QObject:
    checked: list[QtWidgets.QGraphicsItem] = [obj]
    while isinstance(checked[-1], Graphic):
        dp = checked[-1].dataProxy()
        if not dp:
            break
        if dp in checked:
            dp_refs = ', '.join(repr(o) for o in checked)
            raise Exception(f"Circular dataProxy refs: {dp_refs}: {dp!r}")
        checked.append(dp)
    return checked[-1]


def copyTextToClipboard(text: str) -> None:
    if text:
        clipboard = QtGui.QGuiApplication.clipboard()
        clipboard.setText(text)


def sceneViewport(scene: QtWidgets.QGraphicsScene) -> QtCore.QRectF:
    from .widgets import GraphicView

    for view in scene.views():
        if isinstance(view, GraphicView):
            return view.viewportRect()

    return scene.sceneRect()


def copyItemContentsToClipboard(items: Sequence[Graphic], text: str = None,
                                scene: QtWidgets.QGraphicsScene = None,
                                deselect=True) -> None:
    if items:
        scene = scene or items[0].scene()
        if text is None:
            text = "; ".join(item.textToCopy() for item in items)
    if not text:
        return

    if deselect:
        for item in items:
            item.setSelected(False)

    if scene and isinstance(scene, GraphicScene):
        scene.displayMessage(
            "Copied to Clipboard", targets=items, click_to_dismiss=False,
            auto_dismiss=True, delay=600, animated=True,
        )

    copyTextToClipboard(text)


@dataclasses.dataclass
class GraphicTemplate:
    create: Callable[[Optional[Graphic]], Graphic]
    update: Callable[[Graphic, Any, dict[str, Any]], None]


class GraphicScene(QtWidgets.QGraphicsScene):
    viewportChanged = QtCore.Signal()
    rootChanged = QtCore.Signal()
    linkActivated = QtCore.Signal(str)
    contentSizeChanged = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject = None):
        super().__init__(parent)
        self._animation_disabled = False
        self._template_path: Optional[pathlib.Path] = None
        self._template_data: dict[str, Any] = {}
        self._root: Optional[Graphic] = None
        self._controller: Optional[config.DataController] = None
        self._message: Optional[controls.TransientMessageGraphic] = None

        # c = QtGui.QColor("#63D0DF")  # "#63D0DF" #D0BCFF
        theme_hct = colorutils.Color("hct", [282, 48, 25])
        highlight_hct = themes.qcolor_to_hct(QtGui.QColor("#C7FF00"))
        self._color_theme = themes.ColorTheme.fromHct(theme_hct)
        self._theme_palette = self._color_theme.themePalette()
        self.setPalette(self._theme_palette.qtPalette())

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.matches(QtGui.QKeySequence.Copy):
            focus_item = self.focusItem()
            selected = self.selectedItems()

            if focus_item and isinstance(focus_item, QtWidgets.QGraphicsTextItem):
                # A QGraphicsTextItem can take care of copying its own selection
                # to the clipboard, we should just fall through to the super()
                # call below
                pass
            elif selected:
                event.accept()
                copyItemContentsToClipboard(selected, scene=self)
                return

        super().keyPressEvent(event)

    def contextMenuEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        # Implement scene-level context menu here someday.
        # (We must accept this event because if it propagates down to Qt code
        # it will crash trying to open a standard context menu.)
        event.accept()

    def linkClicked(self, url: str) -> None:
        # print("link clicked=", url)
        self.linkActivated.emit(url)

    def rootGraphic(self) -> Optional[Graphic]:
        return self._root

    def setRootGraphic(self, root: Graphic) -> None:
        if root is self._root:
            return

        old_root = self._root
        if old_root:
            old_root.contentSizeChanged.disconnect(self.contentSizeChanged)
            self.removeItem(old_root)
            # old_root.deleteLater()

        root.contentSizeChanged.connect(self.contentSizeChanged)
        self._root = root
        self.addItem(root)
        self.rootChanged.emit()

    def notifyViewportChanged(self) -> None:
        self.viewportChanged.emit()

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
        root = rootFromTemplate(template_data, self.controller(), self)
        self.setRootGraphic(root)

    def colorTheme(self) -> themes.ColorTheme:
        return self._color_theme

    def setColorTheme(self, theme: themes.ColorTheme) -> None:
        self._color_theme = theme
        self._theme_palette = theme.themePalette()
        self.setPalette(self._theme_palette.qtPalette())
        self.update()

    def themeColor(self) -> QtGui.QColor:
        return self.colorTheme().theme_qcolor

    def setThemeColor(self, color: QtGui.QColor) -> None:
        theme = themes.ColorTheme.fromColor(color)
        self.setColorTheme(theme)

    def themePalette(self) -> themes.ThemePalette:
        return self._theme_palette

    def drawBackground(self, painter: QtGui.QPainter,
                       rect: QtCore.QRectF) -> None:
        painter.fillRect(rect, self.palette().window())

    def animationDisabled(self) -> bool:
        return self._animation_disabled

    def setAnimationDisabled(self, disabled: bool) -> None:
        self._animation_disabled = disabled

    def viewportRect(self) -> QtCore.QRectF:
        return sceneViewport(self)

    def _makeMessage(self) -> None:
        from .controls import TransientMessageGraphic
        self._message = TransientMessageGraphic()
        self.addItem(self._message)
        self._message.setGeometry(10, 10, 128, 128)
        self._message.setText("Hello there I am a message")

    def messageItem(self) -> controls.TransientMessageGraphic:
        if not self._message:
            self._makeMessage()
        return self._message

    def displayMessage(self, text: str,
                       targets: Sequence[QtWidgets.QGraphicsItem] = None,
                       click_to_dismiss=False, auto_dismiss=True, delay=500,
                       alignment=Qt.AlignCenter, margin=10, animated=True
                       ) -> None:
        message = self.messageItem()
        message.setText(text)
        message.display(targets=targets, click_to_dismiss=click_to_dismiss,
                        auto_dismiss=auto_dismiss, delay=delay,
                        alignment=alignment, margin=margin, animated=animated)


class DynamicColor:
    # Descriptor that calculates a color on-demand based on the current theme.
    # Caches the color until the palette changes.
    def __init__(self):
        self.spec_attr = ""
        self.color_attr = ""
        self.cache_key_attr = ""

    def __set_name__(self, owner: type[Graphic], name: str) -> None:
        self.spec_attr = f"_{name}_spec"
        self.color_attr = f"_{name}_color"
        self.cache_key_attr = f"_{name}_cache_key"

    def __get__(self, obj: Graphic, objtype=None) -> Optional[QtGui.QColor]:
        if obj is None:
            # This can happen if the descriptor is accessed on the class
            return None

        spec: converters.ColorSpec = getattr(obj, self.spec_attr, None)
        color: QtGui.QColor = getattr(obj, self.color_attr, None)
        cached_key = getattr(obj, self.cache_key_attr, None)
        if spec is None:
            return None
        palette = obj.themePalette()
        # palette = obj.palette()
        if palette:
            if color is None or palette.cache_key != cached_key:
            # if color is None or palette.cacheKey() != cached_key:
                color = palette.resolve(spec)
            #     color = themes.themeColor(spec, palette)
                setattr(obj, self.color_attr, color)
                setattr(obj, self.cache_key_attr, palette.cache_key)
                # setattr(obj, self.cache_key_attr, palette.cacheKey())
            return color
        else:
            return QtGui.QColor("#ff00ff")

    def __set__(self, obj: Graphic, spec: converters.ColorSpec):
        setattr(obj, self.spec_attr, spec)
        setattr(obj, self.color_attr, None)


def sceneAnimationDisabled(scene: Optional[QtWidgets.QGraphicsScene]) -> bool:
    if scene and isinstance(scene, GraphicScene):
        return scene.animationDisabled()
    else:
        return False


class Graphic(QtWidgets.QGraphicsWidget):
    # This gets replaced by the class decorator
    graphic_type_names: tuple[str] = ()
    property_aliases = {}

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._children: dict[Union[int, str], Graphic] = {}
        self._styles: Optional[dict[str, Any]] = None
        self._implicit_size: Optional[QtCore.QSizeF] = None
        self._fixed_width: Optional[float] = None
        self._fixed_height: Optional[float] = None
        self._color_theme: Optional[themes.ColorTheme] = None
        self._theme_palette: Optional[themes.ThemePalette] = None
        self._local_env: Optional[dict[str, Any]] = None
        self._anims: dict[bytes, QtCore.QPropertyAnimation] = {}
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._model: Optional[QtCore.QAbstractItemModel] = None
        self._fading_out = False
        self._fading_in = False
        self._xrot = 0.0
        self._yrot = 0.0
        self._zdist = 180.0
        self._hilited = False
        self._hilite_value = 0.0
        self._poof_anim: Optional[QtCore.QAbstractAnimation] = None

        # If you don't explicitly set a text size, it gets huge for some reason
        # when the view is scaled
        font = QtGui.QFont()
        font.setPixelSize(12)
        super().setFont(font)

    # def contextMenuEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
    #     print("Graphic context menu=", event)
    #     event.accept()

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
        if "name" in data:
            graphic.setObjectName(data.pop("name"))
        if parent:
            parent.prepChild(graphic, data)
        graphic.configureFromData(data, controller)
        return graphic

    @classmethod
    def templateKeys(cls) -> Sequence[str]:
        return ()

    @classmethod
    def objectValueKeysAndTypes(cls) -> Sequence[tuple[str, type[QtCore.QObject]]]:
        return [(info.name, info.value_object_type)
                for _, info in config.settersAndInfos(cls)
                if info.value_object_type]

    @classmethod
    def parentMethodKeys(cls) -> Collection[str]:
        return [info.name for _, info in config.settersAndInfos(cls)
                if info.is_parent_method]

    def configureFromData(self, data: dict[str, Any],
                          controller: config.DataController = None) -> None:
        # We want to set the object's own properties first, then instantiate its
        # children (because the properties might influence how prepChild()
        # works), so we pop the child data out and process it after setting up
        # the tile
        child_datas: Sequence[dict[str, Any]] = data.pop("items", ())
        # Pull out properties that are graphic items, so we can instantiate them
        # separately and make the controller aware of them
        key_type_data_list: \
            list[tuple[str, type[QtCore.QObject], dict[str, Any]]] = []
        for k, ktype in self.objectValueKeysAndTypes():
            if k in data:
                key_type_data_list.append((k, ktype, data.pop(k)))

        name = data.pop("name", None)
        if name:
            self.setObjectName(name)

        # For each property that takes an item type (such as a model or a
        # Graphic), instantiate the object from the JSON value and then pass it
        # to the setter
        for key, obj_type, sub_data in key_type_data_list:
            if issubclass(obj_type, Graphic):
                c = graphicFromData(sub_data, parent=self,
                                    controller=controller)
            elif issubclass(obj_type, QtCore.QAbstractItemModel):
                c = models.modelFromData(sub_data, parent=self,
                                         controller=controller)
            elif obj_type in converters.converter_registry:
                conveter = converters.converter_registry[obj_type]
                c = conveter(sub_data)
            else:
                raise TypeError(f"Can't make value of type {obj_type}")
            config.setSettable(self, key, c)

        if controller:
            controller.prepObject(self, data, name)
        config.updateSettables(self, data)

        # Create child items
        for sub_data in child_datas:
            c = graphicFromData(sub_data, parent=self, controller=controller)
            self.addChild(c)

    def model(self) -> QtCore.QAbstractItemModel:
        return self._model

    def textToCopy(self) -> str:
        return ""

    def sceneChanged(self, old_scene: QtWidgets.QGraphicsScene,
                     new_scene: QtWidgets.QGraphicsScene) -> None:
        pass

    def viewportChanged(self) -> None:
        pass

    def awaken(self) -> None:
        for child in self.childGraphics():
            child.awaken()

    def setHasHeightForWidth(self, hfw: bool) -> None:
        sp = self.sizePolicy()
        sp.setHeightForWidth(hfw)
        self.setSizePolicy(sp)

    def setHasWidthForHeight(self, wfh: bool) -> None:
        sp = self.sizePolicy()
        sp.setHeightForWidth(wfh)
        self.setSizePolicy(sp)

    def controller(self) -> Optional[config.DataController]:
        scene = self.scene()
        if scene is None:
            return
        if not isinstance(scene, GraphicScene):
            raise Exception(f"Not a GraphicScene: {scene!r}")
        controller = scene.controller()
        if not controller:
            raise Exception("Graphic in scene without controller")
        return controller

    def colorTheme(self) -> themes.ColorTheme:
        return self._color_theme

    def effectiveTheme(self) -> themes.ColorTheme:
        if self._color_theme:
            return self._color_theme
        parent = self.parentItem()
        if parent and isinstance(parent, Graphic):
            return parent.effectiveTheme()
        scene = self.scene()
        if isinstance(scene, GraphicScene):
            return scene.colorTheme()

    def themePalette(self) -> Optional[themes.ThemePalette]:
        if self._theme_palette:
            return self._theme_palette
        parent = self.parentItem()
        if parent and isinstance(parent, Graphic):
            return parent.themePalette()
        scene = self.scene()
        if isinstance(scene, GraphicScene):
            return scene.themePalette()

    def setColorTheme(self, theme: themes.ColorTheme) -> None:
        self._color_theme = theme
        self._theme_palette = theme.themePalette()
        self.setPalette(self._theme_palette.qtPalette())

    def pathElement(self, name: str) -> Optional[QtCore.QObject]:
        return getattr(self, name)()

    def addChild(self, item: QtWidgets.QGraphicsItem) -> None:
        item.setParentItem(self)
        name = item.objectName()
        key = name if name else id(item)
        self._children[key] = item

    def prepChild(self, child: Graphic, data: dict[str, Any]) -> None:
        # Child items can have settings that are meant to be interpreted by the
        # parent item (usually layout options); grab those settings out of the
        # data and apply them on the parent
        parent_keys = self.parentMethodKeys()

        if self.graphic_type_names:
            for prop_name in parent_keys:
                if prop_name in data:
                    if setter := config.findParentSettable(self, prop_name):
                        value = data.pop(prop_name)
                        setter(self, child, value)
                    else:
                        raise NameError(f"No property {prop_name} on {self!r}")

    def findElement(self, name: str, recursive=False,
                    ) -> Optional[QtWidgets.QGraphicsWidget]:
        try:
            return self._children[name]
        except KeyError:
            pass

        try:
            return self.pathElement(name)
        except AttributeError:
            pass

        if recursive:
            for child in self.childGraphics():
                obj = child.findElement(name, recursive)
                if obj:
                    return obj

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
                return sceneViewport(scene)
            else:
                return QtCore.QRectF()

    def viewportRect(self) -> QtCore.QRectF:
        # This must return the visible rect in SCENE coordinates
        return self.parentViewportRect()

    def hasImplicitSize(self) -> bool:
        return self._implicit_size is not None

    def implicitSize(self) -> QtCore.QSizeF:
        if self._implicit_size:
            return QtCore.QSizeF(self._implicit_size)
        else:
            raise AttributeError(f"{self} has no implicit size")

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

    def namedStyle(self, name: str) -> dict[str, Any]:
        name = name or "*"
        style = self._styles.get(name, {}) if self._styles else {}
        if parent := self.parentGraphic():
            style = parent.namedStyle(name) | style
        return style

    @settable("style")
    def setStyleName(self, stylename: str) -> None:
        style = self.namedStyle(stylename)
        if style:
            config.updateSettables(self, style)

    @settable()
    def setStyles(self, styles: dict[str, dict[str, Any]]) -> None:
        self._styles = styles

    def canShrink(self) -> Optional[bool]:
        return None

    def findShrinkables(self) -> Iterable[Graphic]:
        shrinkable = self.canShrink()
        if shrinkable is None:
            for child in self.childGraphics():
                yield from child.findShrinkables()
        elif shrinkable:
            yield self

    def shrinkHeightTo(self, height: float) -> None:
        raise NotImplementedError(type(self))

    def shrinkFactor(self) -> float:
        return 1.0

    def shrunkenMinimumHeight(self) -> float:
        return self.minimumHeight()

    def unshrink(self) -> None:
        for tile in self.childGraphics():
            tile.unshrink()

    @settable()
    def setSelectable(self, on: bool) -> None:
        self.setFlag(self.ItemIsSelectable, on)

    def setLocalVariable(self, name: str, value: Any) -> None:
        if self._local_env is None:
            self._local_env = {}
        self._local_env[name] = value

    def localEnv(self) -> dict[str, Any]:
        if self._local_env:
            return self._local_env
        else:
            return {}

    def scopedVariables(self) -> dict[str, Any]:
        parent = self.parentGraphic()
        extra = self.localEnv()
        if parent:
            env = parent.scopedVariables()
            env.update(extra)
        else:
            env= extra
        return env

    def _evaluateExpr(self, expr: Optional[config.Expr],
                      extra_env: dict[str, Any] = None) -> Any:
        if not expr:
            return

        controller = self.controller()
        if controller:
            env = controller.globalEnv()
        else:
            env = {}
        env.update(self.scopedVariables())
        env["self"] = self
        env["controller"] = controller
        if extra_env:
            env.update(extra_env)
        return expr.evaluate(None, env)

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

    def animationDisabled(self, ignore_visible=False) -> bool:
        if not (self.isVisible() or ignore_visible):
            return True
        return sceneAnimationDisabled(self.scene())

    def clipping(self) -> bool:
        return self.flags() & self.ItemClipsChildrenToShape

    @settable("clip")
    def setClipping(self, clip: bool) -> None:
        self.setFlag(self.ItemClipsChildrenToShape, clip)

    def _getOrMakeEffect(self, cls: type[QtWidgets.QGraphicsEffect]
                         ) -> Optional[QtWidgets.QGraphicsEffect]:
        effect = self.graphicsEffect()
        if effect is None:
            effect = cls()
            self.setGraphicsEffect(effect)
            return effect
        elif isinstance(effect, cls):
            return effect

    def shadowEffect(self) -> Optional[QtWidgets.QGraphicsDropShadowEffect]:
        return self._getOrMakeEffect(QtWidgets.QGraphicsDropShadowEffect)

    def blurEffect(self) -> Optional[QtWidgets.QGraphicsBlurEffect]:
        return self._getOrMakeEffect(QtWidgets.QGraphicsBlurEffect)

    @settable("blur")
    def setBlurRadius(self, radius: float) -> None:
        blur = self.blurEffect()
        if blur:
            blur.setBlurRadius(radius)

    @settable("shadow_visible", argtype=bool)
    def setShadowEnabled(self, shadow: bool):
        self.shadowEffect().setEnabled(shadow)

    @settable(argtype=QtGui.QColor)
    def setShadowColor(self, color: QtGui.QColor):
        self.shadowEffect().setColor(color)

    @settable()
    def setShadowBlur(self, radius: float):
        self.shadowEffect().setBlurRadius(radius)

    @settable()
    def setShadowOffsetX(self, dx: float):
        self.shadowEffect().setXOffset(dx)

    @settable(argtype=QtCore.QPointF)
    def setShadowOffset(self, delta: QtCore.QPointF) -> None:
        self.shadowEffect().setOffset(delta)

    @settable()
    def setShadowOffsetY(self, dy: float):
        self._shadowEffect().setYOffset(dy)

    @settable("fixed_width")
    def setFixedWidth(self, width: float):
        self._fixed_width = width
        if self._fixed_height is not None:
            self._implicit_size = QtCore.QSizeF(width, self._fixed_height)
        self.prepareGeometryChange()
        super().setPreferredWidth(width)
        super().setMinimumWidth(width)
        super().setMaximumWidth(width)
        self.updateGeometry()

    @settable("fixed_height")
    def setFixedHeight(self, height: float):
        self._fixed_height = height
        if self._fixed_width is not None:
            self._implicit_size = QtCore.QSizeF(self._fixed_width, height)
        self.prepareGeometryChange()
        super().setPreferredHeight(height)
        super().setMinimumHeight(height)
        super().setMaximumHeight(height)
        self.updateGeometry()

    @settable("fixed_size", argtype=QtCore.QSizeF)
    def setFixedSize(self, size: QtCore.QSizeF) -> None:
        self._implicit_size = QtCore.QSizeF(size)
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
        m4 = QtGui.QMatrix4x4()
        m4.rotate(self._xrot, 1.0, 0.0, 0.0)
        m4.rotate(self._yrot, 0.0, 1.0, 0.0)
        m4.translate(-dx, -dy)
        self.setTransform(m4.toTransform(self._zdist))

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

    def stopPropertyAnimation(self, prop: bytes) -> None:
        anim = self._anim(prop)
        anim.stop()

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
        self.stopPropertyAnimation(b"opacity")
        self.animateProperty(b"opacity", self.opacity(), opacity, **kwargs)

    def isFadingIn(self) -> bool:
        return self._fading_in

    def fadeIn(self, **kwargs) -> None:
        if self.isFadingIn():
            return

        self.show()
        callback = kwargs.pop("callback", None)
        kwargs["callback"] = lambda: self._afterFade(False, callback)
        self._fading_in = True
        self.fadeTo(1.0, **kwargs)

    def _afterFade(self, hide: bool, callback: Optional[Callable]):
        self._fading_out = self._fading_in = False
        if hide:
            self.hide()
        if callback:
            callback()

    def isFadingOut(self) -> bool:
        return self._fading_out

    def fadeOut(self, hide=True, **kwargs) -> None:
        if self.isFadingOut():
            return

        self.show()
        callback = kwargs.pop("callback", None)
        kwargs["callback"] = lambda: self._afterFade(hide, callback)
        self._fading_out = True
        self.fadeTo(0.0, **kwargs)

    def poofIn(self, **kwargs):
        self.show()
        blur = self.blurEffect()
        blur.setBlurRadius(POOF_BLUR_END)
        self.setScale(POOF_SCALE_END)
        self.setOpacity(0.0)
        self._poof_anim = poofAnim(self, scale_to=1.0, fade_to=1.0, blur_to=0.0)
        self._poof_anim.start()

    def poofOut(self, hide=True, **kwargs):
        if hide and "callback" not in kwargs:
            kwargs["callback"] = lambda: self.hide()
        blur = self.blurEffect()
        self.show()
        self.setScale(1.0)
        self.setOpacity(1.0)
        blur.setBlurRadius(0.0)
        self._poof_anim = poofAnim(self, scale_to=POOF_SCALE_END,
                                   fade_to=0.0, blur_to=POOF_BLUR_END)
        self._poof_anim.start()

    def flipTo(self, h_angle: float, v_angle: float) -> None:
        if v_angle != self._xrot:
            self.animateProperty(b"xrot", self.xRotation(), v_angle)
        if h_angle != self._yrot:
            self.animateProperty(b"yrot", self.yRotation(), h_angle)

    def _hiliteVal(self) -> float:
        return self._hilite_value

    def _setHiliteVal(self, value: float) -> None:
        self._hilite_value = value
        self.update()

    _hiliteValue = QtCore.Property(float, _hiliteVal, _setHiliteVal)

    def isHighlighted(self) -> bool:
        return self._hilited

    def setHighlighted(self, highlighted: bool, animated=False,
                       duration=100) -> None:
        self._hilited = highlighted
        value = float(highlighted)
        if animated and not self.animationDisabled():
            self.animateProperty(b"_hiliteValue", self._hilite_value, value,
                                 duration=duration)
        else:
            self._setHiliteVal(value)

    def _selectionPenAndBrush(self) -> tuple[QtGui.QPen, QtGui.QBrush]:
        palette = self.themePalette()
        outline = palette.resolve(themes.ThemeColor.highlight)
        outline.setAlphaF(0.5)
        fill = palette.resolve(themes.ThemeColor.highlight_surface)
        fill.setAlphaF(0.25)
        pen = QtGui.QPen(outline, 1.0)
        brush = QtGui.QBrush(fill)
        return pen, brush


settable()(Graphic.setToolTip)


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

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.setPen(Qt.green)
    #     painter.drawRect(self.rect())


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
            try:
                self._model.dataChanged.disconnect(self._dataChanged)
            except RuntimeError:
                pass
        if self._use_modelReset:
            try:
                self._model.modelReset.disconnect(self._modelReset)
            except RuntimeError:
                pass
        if self._use_rowsInserted:
            try:
                self._model.rowsInserted.disconnect(self._rowsInserted)
            except RuntimeError:
                pass
        if self._use_rowsRemoved:
            try:
                self._model.rowsRemoved.disconnect(self._rowsRemoved)
            except RuntimeError:
                pass
        if self._use_rowsMoved:
            try:
                self._model.rowsMoved.disconnect(self._rowsMoved)
            except RuntimeError:
                pass
        if self._use_layoutChanged:
            try:
                self._model.layoutChanged.disconnect(self._layoutChanged)
            except RuntimeError:
                pass

    def _connectModel(self):
        if self._use_dataChanged:
            self._model.dataChanged.connect(self._dataChanged)
        if self._use_modelReset:
            self._model.modelReset.connect(self._modelReset)
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

    def setModel(self, model: Optional[QtCore.QAbstractItemModel]) -> None:
        if self._model:
            self._disconnectModel()
        self._model = model
        self.setLocalVariable("model", model)
        if self._model:
            self._connectModel()

    def _dataChanged(self, index1: QtCore.QModelIndex,
                     index2: QtCore.QModelIndex, roles=()) -> None:
        model = self.model()
        if not model:
            raise Exception(f"{self} does not have a data model")
        self._rowDataChanged(index1.row(), index2.row())

    def _rowDataChanged(self, first_row: int, last_row: int) -> None:
        pass

    def _rowDataChanged(self, start_row: int, end_row: int) -> None:
        pass

    def _modelReset(self) -> None:
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

    def localEnv(self) -> dict[str, Any]:
        return {"model": self.model()}

    def rowCount(self) -> int:
        model = self.model()
        if model:
            return model.rowCount()
        else:
            return 0


settable("visible")(Graphic.setVisible)
settable("min_width")(Graphic.setMinimumWidth)
settable("min_height")(Graphic.setMinimumHeight)
settable("max_width")(Graphic.setMaximumWidth)
settable("max_height")(Graphic.setMaximumHeight)
settable("preferred_width")(Graphic.setPreferredWidth)
settable("preferred_height")(Graphic.setPreferredHeight)
settable("preferred_size", argtype=QtCore.QSizeF)(Graphic.setPreferredSize)
settable("min_size", argtype=QtCore.QSizeF)(Graphic.setMinimumSize)
settable("max_size", argtype=QtCore.QSizeF)(Graphic.setMaximumSize)
settable("size", argtype=QtCore.QSizeF)(Graphic.resize)


def graphicFromData(data: dict[str, Any], parent: Graphic = None,
                    controller: config.DataController = None,
                    scene: GraphicScene = None) -> Graphic:
    if isinstance(data, GraphicTemplate):
        graphic = data.create(parent)
    elif isinstance(data, dict):
        # Make a copy of the data dict so we can pop keys off and not affect
        # the caller
        data = data.copy()
        typename = data.pop("type", "text")
        try:
            cls = graphic_class_registry[typename]
        except KeyError:
            raise Exception(f"Unknown tile type: {typename!r}")
        if not issubclass(cls, Graphic):
            raise TypeError(f"Class {cls} is not a subclass of Graphic")
        graphic = cls.fromData(data, parent=parent,
                                         controller=controller)
    else:
        raise TypeError(f"Can't create graphic from {data!r}")

    if scene:
        scene.addItem(graphic)

    size = graphic.effectiveSizeHint(Qt.PreferredSize, QtCore.QSizeF(-1, -1))
    if size.isValid():
        graphic.resize(size)

    return graphic


def rootFromTemplate(data: dict[str, Any], controller: config.DataController,
                     scene: GraphicScene) -> Graphic:
    if not controller:
        raise Exception("No controller")
    controller.clear()
    graphic = graphicFromData(data, controller=controller, scene=scene)
    controller.setRoot(graphic)
    return graphic


class AreaGraphic(Graphic):
    highlight_alpha = 0.5

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._clip_to_parent_shape = False
        # You can set an explicit QPen, or else set separate color/role and
        # width, and the pen will be constructed in effectiveBorderPen()
        self._pen: Optional[QtGui.QPen] = None
        self._border_color: Optional[QtGui.QColor] = None
        self._border_width = 1.0
        self._brush: Optional[QtGui.QBrush] = None
        self._fill_color: Optional[QtGui.QColor] = None
        self._fill_tint: Optional[QtGui.QColor] = None
        self._fill_tint_amount = 0.5
        self._striped = False
        self._stripe_color: Optional[QtGui.QColor] = None
        # If _stripe_spacing is not set explicitly, use _strip_width
        self._stripe_spacing: Optional[float] = None
        self._stripe_width = 10.0

    _border_color = DynamicColor()
    _fill_color = DynamicColor()
    _fill_tint = DynamicColor()
    _stripe_color = DynamicColor()

    def clipsToParentShape(self) -> bool:
        return self._clip_to_parent_shape

    def setClipsToParentShape(self, clip: bool):
        self._clip_to_parent_shape = clip
        self.update()

    def pen(self) -> Optional[QtGui.QPen]:
        return self._pen

    def setPen(self, pen: QtGui.QPen) -> None:
        self._pen = pen
        self.update()

    def borderColor(self) -> Optional[QtGui.QColor]:
        return self._border_color

    @settable(argtype=QtGui.QColor)
    def setBorderColor(self, color: converters.ColorSpec):
        self._border_color = color
        self.update()

    def borderWidthValue(self) -> float:
        return self._border_width

    @settable()
    def setBorderWidth(self, width: float) -> None:
        self._border_width = width
        self.update()

    borderWidth = QtCore.Property(float, borderWidthValue, setBorderWidth)

    def effectiveBorderPen(self) -> QtGui.QPen:
        width = self._border_width
        if self._pen:
            return QtGui.QPen(self._pen)

        color = self._border_color
        if not color or not width:
            return Qt.NoPen

        return QtGui.QPen(color, width)

    def brush(self) -> QtGui.QBrush:
        return self._brush

    def setBrush(self, brush: QtGui.QBrush):
        self._brush = QtGui.QBrush(brush)
        self.update()

    def isStriped(self) -> bool:
        return self._striped

    @settable(argtype=bool)
    def setStriped(self, striped: bool) -> None:
        self._striped = striped

    @settable(argtype=QtGui.QColor)
    def setStripeColor(self, color: converters.ColorSpec) -> None:
        self._stripe_color = color

    @settable()
    def setStripeSpacing(self, space: float) -> None:
        self._stripe_space = space

    @settable()
    def setStripeWidth(self, width: float) -> None:
        self._stripe_width = width

    def fillColor(self) -> Optional[QtGui.QColor]:
        return self._fill_color

    @settable("fill_color", argtype=QtGui.QColor)
    def setFillColor(self, color: converters.ColorSpec) -> None:
        self._fill_color = color
        self.update()

    fill = QtCore.Property(QtGui.QColor, fillColor, setFillColor)

    @settable("fill_tint", argtype=QtGui.QColor)
    def setFillTintColor(self, color: QtGui.QColor) -> None:
        self._fill_tint = color
        self.update()

    @settable("fill_tint_amount")
    def setFillTintAmount(self, amount: float) -> None:
        self._fill_tint_amount = amount
        self.update()

    def effectiveFillColor(self) -> Optional[QtGui.QColor]:
        color = self._fill_color
        if not color:
            return None
        if self._fill_tint and self._fill_tint_amount:
            color = themes.blend(color, self._fill_tint, self._fill_tint_amount)
        return color

    def effectiveBrush(self) -> QtGui.QBrush:
        if self._brush:
            return self._brush

        color = self.effectiveFillColor()
        stripe_color = self._stripe_color
        if self._striped and stripe_color:
            color = color or Qt.transparent
            width = self._stripe_width
            space = self._stripe_spacing
            space = space if space is not None else width
            brush = themes.stripes(color, stripe_color, space, width)
        elif color:
            brush = QtGui.QBrush(color)
        else:
            brush = Qt.NoBrush
        return brush


@graphictype("rectangle")
class RectangleGraphic(AreaGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._corner_radius = 0.0
        # self._round_corners = [True, True, True, True]
        self._is_pill = False
        self._intersect_with_parent = False
        self._shape: Optional[QtGui.QPainterPath] = None

    @settable(argtype=bool)
    def setIntersectWithParentShape(self, intersect: bool) -> None:
        self._intersect_with_parent = intersect

    def intersectionShape(self) -> QtGui.QPainterPath:
        return self.shape()

    def isPillShaped(self) -> bool:
        return self._is_pill

    @settable()
    def setPillShaped(self, is_pill: bool) -> None:
        self._is_pill = is_pill
        self.update()

    def cornerRadius(self) -> float:
        if self._is_pill:
            rect = self.rect()
            return min(rect.width() / 2, rect.height() / 2, 64.0)
        else:
            return self._corner_radius

    # def setRoundedCorners(self, top_left: bool, top_right: bool,
    #                       bottom_left: bool, bottom_right: bool) -> None:
    #     self._round_corners = [top_left, top_right, bottom_left, bottom_right]
    #     self.update()

    @settable()
    def setCornerRadius(self, radius: float) -> None:
        self._corner_radius = radius
        self.update()

    def _parentShape(self) -> Optional[QtGui.QPainterPath]:
        parent_item = self.parentItem()
        if parent_item:
            if isinstance(parent_item, RectangleGraphic):
                parent_shape = parent_item.intersectionShape()
            else:
                parent_shape = parent_item.shape()
            return self.mapFromParent(parent_shape)

    def shape(self) -> QtGui.QPainterPath:
        if self._shape or self._intersect_with_parent or self._corner_radius:
            if self._shape:
                return self._shape
            else:
                return self._shapeForRect(self.rect())
        else:
            return super().shape()

    def _shapeForRect(self, rect: QtCore.QRectF) -> QtGui.QPainterPath:
        shape = QtGui.QPainterPath()
        cr = self.cornerRadius()
        if cr:
            shape.addRoundedRect(rect, cr, cr)
        else:
            shape.addRect(rect)

        if self._intersect_with_parent:
            if parent_shape := self._parentShape():
                shape = shape.intersected(parent_shape)
        return shape

    def setShape(self, shape: QtGui.QPainterPath) -> None:
        self._shape = shape
        self.update()

    def _paintRectangle(self, painter: QtGui.QPainter) -> None:
        rect = self.rect()
        if self._hilite_value:
            hi_val = self._hiliteVal()
            color = self.palette().color(QtGui.QPalette.Highlight)
            color.setAlphaF(hi_val * self.highlight_alpha)
            painter.fillRect(rect, color)

        brush = self.effectiveBrush()
        pen = self.effectiveBorderPen()
        if (brush is Qt.NoBrush or not brush) and (pen is Qt.NoPen or not pen):
            return

        if self._clip_to_parent_shape:
            parent = self.parentItem()
            if parent:
                shape = self.mapFromParent(parent.shape())
                painter.setClipPath(shape)

        painter.setBrush(brush)
        painter.setPen(pen)
        if self._shape or self._intersect_with_parent:
            shape = self.shape()
            painter.drawPath(shape)
        else:
            radius = self.cornerRadius()
            if radius > 0.0:
                painter.drawRoundedRect(rect, radius, radius)
            else:
                painter.drawRect(rect)

    def _paintSelection(self, painter: QtGui.QPainter) -> None:
        pen, brush = self._selectionPenAndBrush()
        painter.setPen(pen)
        painter.setBrush(brush)
        painter.drawPath(self.shape())

    def paint(self, painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: Optional[QtWidgets.QWidget] = None) -> None:
        self._paintRectangle(painter)
        if self.isSelected():
            self._paintSelection(painter)


class ClickableGraphic(RectangleGraphic):
    pressed = QtCore.Signal()
    clicked = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._clickable = True
        # This item is "down" (the mouse button is pressed while the mouse
        # pointer is over it
        self._is_down = False
        # Records whether the mouse button is currently pressed
        self._mouse_pressed = False
        # We have to track this manually because we don't get hover events while
        # the mouse button is down
        self._inside = False

    def isDown(self) -> bool:
        return self._is_down

    def isClickable(self) -> bool:
        return self._clickable

    def setClickable(self, clickable: bool) -> None:
        self._clickable = clickable

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        super().mousePressEvent(event)
        # Because of QGraphicsWidget's "mouse grabber" system, a "press" might
        # not actually be on this item
        pos = event.pos()
        if self._clickable and self.rect().contains(pos):
            self._inside = True
            self._is_down = True
            self._mouse_pressed = True
            self.pressed.emit()
            self.onMousePress(event)
            self.onMouseDrag(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._clickable:
            self._is_down = False
            self._mouse_pressed = False
            inside = self.rect().contains(event.pos())
            self.onMouseRelease(event)
            if inside:
                self.clicked.emit()
                self.onClick()
            else:
                self.onCancel()

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        # We don't get hover events while the mouse is down, so we have to track
        # in/out ourselves
        if self._clickable:
            was_inside = self._inside
            inside = self._inside = self.rect().contains(event.pos())
            if self._mouse_pressed:
                self._is_down = inside
                if was_inside and not inside:
                    self._is_down = False
                    self.onMouseLeave()
                elif inside and not was_inside:
                    self._is_down = True
                    self.onMouseEnter()
                if inside:
                    self.onMouseDrag(event)

    # def hoverMoveEvent(self, event):
    #     pass

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self._inside = True
        self.onMouseEnter()

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        self._inside = False
        self.onMouseLeave()

    def onMousePress(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        pass

    def onMouseRelease(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        pass

    def onClick(self) -> None:
        pass

    def onCancel(self) -> None:
        pass

    def onMouseEnter(self) -> None:
        pass

    def onMouseDrag(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        pass

    def onMouseLeave(self) -> None:
        pass

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     painter.setPen(Qt.green)
    #     painter.drawRect(self.rect())


FieldValue = Union[config.Expr, str, int, float]


class UnresolvedAnchor(Exception):
    pass


class FieldAdapter:
    attr_names = ("left", "top", "right", "bottom", "h_center", "v_center",
                  "width", "height")

    def __init__(self, item: Optional[Graphic],
                 resolved: dict[Qt.AnchorPoint, float] = None):
        self._item = item
        self._resolved: dict[Qt.AnchorPoint, float] = {}
        if resolved:
            self._resolved.update(resolved)

        self._size: Optional[QtCore.QSizeF] = None
        self._width: Optional[float] = None
        self._height: Optional[float] = None
        if item and item.hasImplicitSize():
            self._size = item.implicitSize()
            self._width = self._size.width()
            self._height = self._size.height()

    @classmethod
    def fromRect(cls, rect: QtCore.QRectF) -> FieldAdapter:
        return FieldAdapter(None, {
            Qt.AnchorLeft: rect.left(),
            Qt.AnchorTop: rect.top(),
            Qt.AnchorRight: rect.right(),
            Qt.AnchorBottom: rect.bottom(),
            Qt.AnchorHorizontalCenter: rect.center().x(),
            Qt.AnchorVerticalCenter: rect.center().y(),
        })

    @property
    def width(self) -> float:
        if self._size:
            return self._width
        resolved = self._resolved
        if Qt.AnchorLeft in resolved and Qt.AnchorRight in resolved:
            return resolved[Qt.AnchorRight] - resolved[Qt.AnchorLeft]
        else:
            raise UnresolvedAnchor(f"{self._item.objectName()}.width")

    @property
    def height(self) -> float:
        if self._size:
            return self._height
        resolved = self._resolved
        if Qt.AnchorTop in resolved and Qt.AnchorBottom in resolved:
            return resolved[Qt.AnchorBottom] - resolved[Qt.AnchorTop]
        else:
            raise UnresolvedAnchor(f"{self._item.objectName()}.height")

    def __getattr__(self, name: str) -> float:
        anchor = converters.anchorPointConverter(name)
        size = self._size
        resolved = self._resolved

        if anchor in resolved:
            return resolved[anchor]

        # if we don't have explicit center points set, we can infer them if
        # we know the edges
        if anchor == Qt.AnchorHorizontalCenter and anchor not in resolved:
            if Qt.AnchorTop in resolved and Qt.AnchorBottom in resolved:
                top = resolved[Qt.AnchorTop]
                bot = resolved[Qt.AnchorBottom]
                return top + bot / 2
        elif anchor == Qt.AnchorHorizontalCenter and anchor not in resolved:
            if Qt.AnchorLeft in resolved and Qt.AnchorRight in resolved:
                left = resolved[Qt.AnchorLeft]
                right = resolved[Qt.AnchorRight]
                return left + right / 2

        # If the item has a known size, we can resolve edges opposite from the
        # size and a parallel edge
        if size:
            if anchor == Qt.AnchorRight:
                if Qt.AnchorLeft in resolved:
                    return resolved[Qt.AnchorLeft] + self._width
                elif Qt.AnchorHorizontalCenter in resolved:
                    return resolved[Qt.AnchorHorizontalCenter] + size.width() / 2
            elif anchor == Qt.AnchorLeft:
                if Qt.AnchorRight in resolved:
                    return resolved[Qt.AnchorRight] - self._width
                elif Qt.AnchorHorizontalCenter in resolved:
                    return resolved[Qt.AnchorHorizontalCenter] - size.width() / 2
            elif anchor == Qt.AnchorBottom:
                if Qt.AnchorTop in resolved:
                    return resolved[Qt.AnchorTop] + self._height
                elif Qt.AnchorVerticalCenter in resolved:
                    return resolved[Qt.AnchorVerticalCenter] + size.height() / 2
            elif anchor == Qt.AnchorTop:
                if Qt.AnchorBottom in resolved:
                    return resolved[Qt.AnchorBottom] - self._height
                elif Qt.AnchorVerticalCenter in resolved:
                    return resolved[Qt.AnchorVerticalCenter] - size.height() / 2
            elif anchor == Qt.AnchorHorizontalCenter:
                if Qt.AnchorLeft in resolved:
                    return resolved[Qt.AnchorLeft] + self._width / 2
                elif Qt.AnchorRight in resolved:
                    return resolved[Qt.AnchorRight] - self._width / 2
            elif anchor == Qt.AnchorVerticalCenter:
                if Qt.AnchorTop in resolved:
                    return resolved[Qt.AnchorTop] + self._height / 2
                elif Qt.AnchorBottom in resolved:
                    return resolved[Qt.AnchorBottom] - self._height / 2

        raise UnresolvedAnchor(f"{self._item.objectName()}.{name}")

    def set(self, anchor: str | Qt.AnchorPoint, value: float) -> None:
        if isinstance(anchor, str):
            anchor = converters.anchor_points[anchor]
        self._resolved[anchor] = value

    def toRect(self) -> QtCore.QRectF:
        if Qt.AnchorLeft not in self._resolved:
            self._resolved[Qt.AnchorLeft] = 0.0
        if Qt.AnchorTop not in self._resolved:
            self._resolved[Qt.AnchorTop] = 0.0

        left = self.left
        top = self.top
        right = max(left, self.right)
        bottom = max(top, self.bottom)
        r = QtCore.QRectF(left, top, right - left, bottom - top)
        if not r.size().isValid():
            # print("resolved=", self._resolved)
            # print("x=", left, "y=", top, "r=", right, "b=", bottom,
            #       "w=", r.width(), "h=", r.height())
            raise Exception(f"Invalid rectangle {r} "
                            f"for {self._item.objectName()!r}")
        return r


class ItemGraphic(RectangleGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._copyable_text_expr: Optional[config.PythonExpr] = None

    @settable("copyable_text")
    def setCopyableTextExpression(self, expr: config.PythonExpr) -> None:
        if isinstance(expr, (str, dict)):
            expr = config.PythonExpr.fromData(expr)
        self._copyable_text_expr = expr

    def textToCopy(self) -> str:
        if self._copyable_text_expr:
            text = self._evaluateExpr(self._copyable_text_expr)
            print("copy=", repr(text))
            return text
        else:
            return ""


@graphictype("field")
class FieldGraphic(ItemGraphic):
    _anchor_to_name = util.invertedDict(converters.anchor_points)

    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._exprs: dict[tuple[str, Qt.AnchorPoint], config.PythonExpr] = {}
        self._knowns: dict[str, dict[Qt.AnchorPoint, float]] = {}
        self._manual_order: Optional[Sequence[tuple[str, Qt.AnchorPoint]]] = None
        self._order: Optional[Sequence[tuple[str, Qt.AnchorPoint]]] = None

    # def _computeResolutionOrder(self) -> Sequence[tuple[str, str]]:
    #     dg: util.DependencyGraph[tuple[str, str]] = util.DependencyGraph()
    #
    #     prev_mo: Optional[tuple[str, str]] = None
    #     for mo in self._manual_order:
    #         if isinstance(mo, str):
    #             mo = tuple(mo.split(".", 1))
    #         elif not isinstance(mo, tuple):
    #             raise TypeError(f"Can't use {mo} in resolution order")
    #         dg.add(mo)
    #         if prev_mo:
    #             dg.depends_on(prev_mo, mo)
    #         prev_mo = mo
    #
    #     obj_names = set(obj.objectName() for obj in self.childGraphics()
    #                     if obj.objectName())
    #     for obj_name in obj_names:
    #         exprs = self._exprs[obj_name]
    #         for anchor, expr in exprs.items():
    #             if not isinstance(expr, config.PythonExpr):
    #                 continue
    #             anchor_name = self._anchor_to_name[anchor]
    #             from_attr = (obj_name, anchor_name)
    #             dg.add(from_attr)
    #             parsed = ast.parse(expr.source)
    #             for node in ast.walk(parsed):
    #                 if isinstance(node, ast.Attribute) and node.ctx == ast.Load:
    #                     lhs = node.value
    #                     if not isinstance(lhs, ast.Name):
    #                         continue
    #                     if lhs.id not in obj_names:
    #                         continue
    #                     if node.attr not in FieldAdapter.attr_names:
    #                         continue
    #                     if node.attr == "width":
    #                         to_add = [(lhs.id, "left"), (lhs.id, "right")]
    #                     elif node.attr == "height":
    #                         to_add = [(lhs.id, "top"), (lhs.id, "bottom")]
    #                     else:
    #                         to_add = [(lhs.id, node.attr)]
    #                     for to_attr in to_add:
    #                         dg.add(to_attr)
    #                         dg.depends_on(from_attr, to_attr)
    #     return tuple(dg.resolve())
    #
    # def _resolutionOrder(self) -> Sequence[tuple[str, str]]:
    #     if self._order is None:
    #         self._order = self._computeResolutionOrder()
    #     return self._order

    def _setExpr(self, child: Graphic, anchor: Qt.AnchorPoint,
                 value: str | config.PythonExpr) -> None:
        name = child.objectName()
        if not name:
            raise ValueError(f"Child item {child} needs a name")
        if isinstance(value, str):
            value = config.PythonExpr(value)
        if isinstance(value, (int, float)):
            kns = self._knowns.setdefault(name, {})
            kns[anchor] = value
        elif isinstance(value, config.Expr):
            self._exprs[name, anchor] = value
            self._order = None

    def resizeEvent(self, event: QtWidgets.QGraphicsSceneEvent) -> None:
        super().resizeEvent(event)
        self._updateContents()

    @settable()
    def setManualOrder(self, order: Sequence[Union[str, tuple[str, str]]]
                       ) -> None:
        self._manual_order = order

    @settable("field:left", is_parent_method=True)
    def setChildLeftExpr(self, child: Graphic, expr: FieldValue) -> None:
        self._setExpr(child, Qt.AnchorLeft, expr)

    @settable("field:top", is_parent_method=True)
    def setChildTopExpr(self, child: Graphic, expr: FieldValue) -> None:
        self._setExpr(child, Qt.AnchorTop, expr)

    @settable("field:right", is_parent_method=True)
    def setChildRightExpr(self, child: Graphic, expr: FieldValue) -> None:
        self._setExpr(child, Qt.AnchorRight, expr)

    @settable("field:bottom", is_parent_method=True)
    def setChildBottomExpr(self, child: Graphic, expr: FieldValue) -> None:
        self._setExpr(child, Qt.AnchorBottom, expr)

    @settable("field:h_center", is_parent_method=True)
    def setChildHCenterExpr(self, child: Graphic, expr: FieldValue) -> None:
        self._setExpr(child, Qt.AnchorHorizontalCenter, expr)

    @settable("field:v_center", is_parent_method=True)
    def setChildVCenterExpr(self, child: Graphic, expr: FieldValue) -> None:
        self._setExpr(child, Qt.AnchorVerticalCenter, expr)

    def _updateContents(self) -> None:
        rect = self.rect()
        # print("parent_rect=", rect)
        knowns = self._knowns
        exprs = self._exprs
        objs: dict[str, Graphic] = {
            obj.objectName(): obj for obj in self.childGraphics()
            if obj.objectName()
        }
        env: dict[str, FieldAdapter] = {
            "parent": FieldAdapter.fromRect(rect)
        }
        for obj_name, obj in objs.items():
            env[obj_name] = FieldAdapter(obj, resolved=knowns.get(obj_name))

        if self._manual_order is not None or self._order is not None:
            order = self._manual_order or self._order
            for key in order:
                obj_name, anchor = key
                expr = exprs[key]
                value = self._evaluateExpr(expr, extra_env=env)
                env[obj_name].set(anchor, value)
        else:
            # We can't really use a straightforward dependency resolution
            # algorithm to figure out the order in which to evaluate expressions
            # because various attributes can be derived from others. So at least
            # for now we just loop over ones we can't resolve until we can't
            # loop anymore :(
            # t = time.perf_counter()
            order: list[tuple[str, Qt.AnchorPoint]] = []
            to_do = list(exprs.items())
            while to_do:
                resolved_at_least_one = False
                for i, (key, expr) in enumerate(to_do):
                    obj_name, anchor = key
                    try:
                        value = self._evaluateExpr(expr, extra_env=env)
                    except UnresolvedAnchor:
                        continue
                    else:
                        to_do.pop(i)
                        resolved_at_least_one = True
                        env[obj_name].set(anchor, value)
                        order.append((obj_name, anchor))
                if not resolved_at_least_one:
                    ues = [expr.source for _, expr in to_do]
                    raise Exception(f"Undecidable expressions: {ues!r}")

            # Remember this order for subsequent items
            self._order = order
            # print(f"Resolve order: {time.perf_counter() - t:0.04f}")

        for obj_name, obj in objs.items():
            adapter = env[obj_name]
            rect = adapter.toRect()
            obj.setGeometry(rect)


@graphictype("anchors")
class AnchorsGraphic(ItemGraphic):
    def __init__(self, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        self._layout_ops: defaultdict[str, list[tuple]] = defaultdict(list)

    def addChild(self, item: QtWidgets.QGraphicsItem) -> None:
        super().addChild(item)

    def _try(self, method: Callable, child: QtWidgets.QGraphicsItem,
             name: str, *args, **kwargs):
        if not isinstance(child, QtWidgets.QGraphicsItem):
            raise TypeError(f"Not a QGraphicsItem: {child!r}")
        obj = self.namedLayoutItem(name)
        if obj:
            method(child, obj, *args, **kwargs)
        else:
            self._layout_ops[name].append((method, child, args, kwargs))

    def configureFromData(self, data: dict[str, Any],
                          controller: config.DataController = None) -> None:
        super().configureFromData(data, controller)
        self.drainLayoutOperations()

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

    def namedLayoutItem(self, name: str
                        ) -> Optional[QtWidgets.QGraphicsLayoutItem]:
        if name == "parent":
            return self.layout()
        return self.findElement(name)

    @settable("spacing")
    def setLayoutSpacing(self, spacing: float) -> None:
        layout = self.anchorLayout()
        layout.setSpacing(spacing)

    @settable("v_space")
    def setVerticalSpacing(self, spacing: float) -> None:
        layout = self.anchorLayout()
        layout.setVerticalSpacing(spacing)

    @settable("h_space")
    def setHorizontalSpacing(self, spacing: float) -> None:
        layout = self.anchorLayout()
        layout.setHorizontalSpacing(spacing)

    @settable("margins", argtype=QtCore.QMarginsF)
    def setMargins(self, ms: QtCore.QMarginsF):
        layout = self.anchorLayout()
        layout.setContentsMargins(ms.left(), ms.top(), ms.right(), ms.bottom())

    def addSideAnchors(self, child: Graphic, obj: Graphic,
                       horizontal: bool, vertical: bool,
                       h_space: float = None, v_space: float = None) -> None:
        layout = self.anchorLayout()
        # We don't use addAnchors() because we want to set the anchor spacing
        if horizontal:
            left = layout.addAnchor(obj, Qt.AnchorLeft, child, Qt.AnchorLeft)
            right = layout.addAnchor(obj, Qt.AnchorRight, child, Qt.AnchorRight)
            if h_space is not None:
                left.setSpacing(h_space)
                right.setSpacing(h_space)

        if vertical:
            top = layout.addAnchor(obj, Qt.AnchorTop, child, Qt.AnchorTop)
            bot = layout.addAnchor(obj, Qt.AnchorBottom, child, Qt.AnchorBottom)
            if v_space is not None:
                top.setSpacing(v_space)
                bot.setSpacing(v_space)

    def addCornerAnchors(self, child: Graphic, obj: Graphic,
                         corner1: Qt.Corner, corner2: Qt.Corner,
                         h_space: float = None, v_space: float = None) -> None:
        layout = self.anchorLayout()
        # We don't use addCornerAnchors() because we want to set the anchor
        # spacing
        if corner1 in (Qt.TopLeftCorner, Qt.BottomLeftCorner):
            h_edge1 = Qt.AnchorLeft
        else:
            h_edge1 = Qt.AnchorRight
        if corner1 in (Qt.TopLeftCorner, Qt.TopRightCorner):
            v_edge1 = Qt.AnchorTop
        else:
            v_edge1 = Qt.AnchorBottom

        if corner2 in (Qt.TopLeftCorner, Qt.BottomLeftCorner):
            h_edge2 = Qt.AnchorLeft
        else:
            h_edge2 = Qt.AnchorRight
        if corner2 in (Qt.TopLeftCorner, Qt.TopRightCorner):
            v_edge2 = Qt.AnchorTop
        else:
            v_edge2 = Qt.AnchorBottom

        h = layout.addAnchor(obj, h_edge2, child, h_edge1)
        if h_space is not None:
            h.setSpacing(h_space)
        v = layout.addAnchor(obj, v_edge2, child, v_edge1)
        if v_space is not None:
            v.setSpacing(v_space)

    def addEdgeAnchor(self, child: Graphic, obj: Graphic,
                      edge1: Qt.AnchorPoint, edge2: Qt.AnchorPoint,
                      spacing: float = None) -> None:
        layout = self.anchorLayout()
        anchor = layout.addAnchor(obj, edge2, child, edge1)
        if spacing is not None:
            anchor.setSpacing(spacing)

    @staticmethod
    def _parseAnchorSpec(spec: Union[str, dict[str, Any]]
                         ) -> tuple[str, Optional[float], Optional[float]]:
        h_space = v_space = None
        if isinstance(spec, str):
            name = spec
        elif isinstance(spec, dict):
            if "to" not in spec:
                raise KeyError(f"Anchor dict {spec} mssing 'to' key")
            name = spec["to"]
            if not isinstance(name, str):
                raise TypeError(f"Anchor 'to' value {name!r} is not a string")
            if "spacing" in spec:
                h_space = v_space = spec["spacing"]
            else:
                h_space = spec.get("h_space")
                v_space = spec.get("v_space")
        else:
            raise TypeError(f"Anchor {spec!r} not a string or dict")
        return name, h_space, v_space

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

    @settable("anchor:fill", is_parent_method=True)
    def setChildFillAnchors(self, child: Graphic, spec: str | dict) -> None:
        name, h_space, v_space= self._parseAnchorSpec(spec)
        self._try(self.addSideAnchors, child, name,
                  horizontal=True, vertical=True,
                  h_space=h_space, v_space=v_space)

    @settable("anchor:h_fill", is_parent_method=True)
    def setChildHorizontalFillAnchors(self, child: Graphic, spec: str | dict
                                      ) -> None:
        name, h_space, v_space = self._parseAnchorSpec(spec)
        self._try(self.addSideAnchors, child, name,
                  horizontal=True, vertical=False,
                  h_space=h_space, v_space=v_space)

    @settable("anchor:v_fill", is_parent_method=True)
    def setChildVerticalFillAnchors(self, child: Graphic, spec: str | dict
                                    ) -> None:
        name, h_space, v_space = self._parseAnchorSpec(spec)
        self._try(self.addSideAnchors, child, name,
                  horizontal=False, vertical=True,
                  h_space=h_space, v_space=v_space)

    @settable("anchor:top_left", is_parent_method=True)
    def setChildTopLeftAnchor(self, child: Graphic, spec: str | dict) -> None:
        rel, h_space, v_space = self._parseAnchorSpec(spec)
        name, corner = self._parseCornerRel(rel)
        self._try(self.addCornerAnchors, child, name,
                  Qt.TopLeftCorner, corner,
                  h_space=h_space, v_space=v_space)

    @settable("anchor:top_right", is_parent_method=True)
    def setChildTopRightAnchor(self, child: Graphic, spec: str | dict) -> None:
        rel, h_space, v_space = self._parseAnchorSpec(spec)
        name, corner = self._parseCornerRel(rel)
        self._try(self.addCornerAnchors, child, name,
                  Qt.TopRightCorner, corner,
                  h_space=h_space, v_space=v_space)

    @settable("anchor:bottom_left", is_parent_method=True)
    def setChildBottomLeftAnchor(self, child: Graphic, spec: str | dict
                                 ) -> None:
        rel, h_space, v_space = self._parseAnchorSpec(spec)
        name, corner = self._parseCornerRel(rel)
        self._try(self.addCornerAnchors, child, name,
                  Qt.BottomLeftCorner, corner,
                  h_space=h_space, v_space=v_space)

    @settable("anchor:bottom_right", is_parent_method=True)
    def setChildBottomRightAnchor(self, child: Graphic, spec: str | dict
                                  ) -> None:
        rel, h_space, v_space = self._parseAnchorSpec(spec)
        name, corner = self._parseCornerRel(rel)
        self._try(self.addCornerAnchors, child, name,
                  Qt.BottomRightCorner, corner,
                  h_space=h_space, v_space=v_space)

    @settable("anchor:left", is_parent_method=True)
    def setChildLeftAnchor(self, child: Graphic, spec: str | dict) -> None:
        rel, h_space, v_space = self._parseAnchorSpec(spec)
        name, edge = self._parseSideRel(rel)
        self._try(self.addEdgeAnchor, child, name, Qt.AnchorLeft, edge,
                 spacing=h_space)

    @settable("anchor:top", is_parent_method=True)
    def setChildTopAnchor(self, child: Graphic, spec: str | dict) -> None:
        rel, h_space, v_space = self._parseAnchorSpec(spec)
        name, edge = self._parseSideRel(rel)
        self._try(self.addEdgeAnchor, child, name, Qt.AnchorTop, edge,
                  spacing=v_space)

    @settable("anchor:right", is_parent_method=True)
    def setChildRightAnchor(self, child: Graphic, spec: str | dict) -> None:
        rel, h_space, v_space = self._parseAnchorSpec(spec)
        name, edge = self._parseSideRel(rel)
        self._try(self.addEdgeAnchor, child, name, Qt.AnchorRight, edge,
                  spacing=h_space)

    @settable("anchor:bottom", is_parent_method=True)
    def setChildBottomAnchor(self, child: Graphic, spec: str | dict) -> None:
        rel, h_space, v_space = self._parseAnchorSpec(spec)
        name, edge = self._parseSideRel(rel)
        self._try(self.addEdgeAnchor, child, name, Qt.AnchorBottom, edge,
                  spacing=v_space)

    @settable("anchor:h_center", is_parent_method=True)
    def setChildHorizontalCenterAnchor(self, child: Graphic, spec: str | dict
                                       ) -> None:
        rel, h_space, v_space = self._parseAnchorSpec(spec)
        name, edge = self._parseSideRel(rel)
        self._try(self.addEdgeAnchor, child, name,
                  Qt.AnchorHorizontalCenter, edge,
                  spacing=h_space)

    @settable("anchor:v_center", is_parent_method=True)
    def setChildVerticalCenterAnchor(self, child: Graphic, spec: str | dict
                                     ) -> None:
        rel, h_space, v_space = self._parseAnchorSpec(spec)
        name, edge = self._parseSideRel(rel)
        self._try(self.addEdgeAnchor, child, name,
                  Qt.AnchorVerticalCenter, edge,
                  spacing=v_space)

    # def paint(self, painter: QtGui.QPainter,
    #           option: QtWidgets.QStyleOptionGraphicsItem,
    #           widget: Optional[QtWidgets.QWidget] = None) -> None:
    #     r = self.rect()
    #     painter.setPen(Qt.red)
    #     painter.drawRect(r)

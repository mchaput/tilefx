from __future__ import annotations
from datetime import datetime
from typing import (TYPE_CHECKING, cast, Any, Callable, Iterable, Optional,
                    Sequence, TypeVar, Union)

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

if TYPE_CHECKING:
    from . import formatting, styling, themes
    from .graphics import core, charts

    ColorSpec = Union[
        str, QtGui.QPalette.ColorRole, QtGui.QColor, themes.ThemeColor,
        Sequence[float]
    ]

T = TypeVar("T")
WidgetType = Union[QtWidgets.QWidget, QtWidgets.QGraphicsWidget]


converter_registry: dict[type, Callable] = {}
takes_styled_object: set[Callable] = set()


SMALL_LABEL_SIZE = 10
LABEL_SIZE = 12
TINY_TEXT_SIZE = 9
XSMALL_TEXT_SIZE = 10
SMALL_TEXT_SIZE = 12
MEDIUM_TEXT_SIZE = 13
LARGE_TEXT_SIZE = 16
XLARGE_TEXT_SIZE = 20
HUGE_TEXT_SIZE = 28
text_sizes: dict[str, int] = {
    "smalllabel": SMALL_LABEL_SIZE,
    "label": LABEL_SIZE,
    "tiny": TINY_TEXT_SIZE,
    "xsmall": XSMALL_TEXT_SIZE,
    "small": SMALL_TEXT_SIZE,
    "medium": MEDIUM_TEXT_SIZE,
    "large": LARGE_TEXT_SIZE,
    "xlarge": XLARGE_TEXT_SIZE,
    "huge": HUGE_TEXT_SIZE,
}
data_roles: dict[str, Qt.ItemDataRole] = {
    "display": Qt.DisplayRole,
    "decoration": Qt.DecorationRole,
    "edit": Qt.EditRole,
    "tooltip": Qt.ToolTipRole,
    "size": Qt.SizeHintRole,
    "font": Qt.FontRole,
    "align": Qt.TextAlignmentRole,
    "bg": Qt.BackgroundRole,
    "fg": Qt.ForegroundRole,
}
role_types: dict[Qt.ItemDataRole, type] = {
    Qt.DisplayRole: str,
    Qt.DecorationRole: QtGui.QIcon,
    Qt.EditRole: str,
    Qt.ToolTipRole: str,
    Qt.SizeHintRole: QtCore.QSize,
    Qt.FontRole: QtGui.QFont,
    Qt.TextAlignmentRole: Qt.Alignment,
    Qt.BackgroundRole: QtGui.QBrush,
    Qt.ForegroundRole: QtGui.QBrush,
}
alignment_names: dict[str, Qt.Alignment] = {
    "topleft": Qt.AlignTop | Qt.AlignLeft,
    "nw": Qt.AlignTop | Qt.AlignLeft,
    "top": Qt.AlignTop | Qt.AlignHCenter,
    "n": Qt.AlignTop | Qt.AlignHCenter,
    "topright": Qt.AlignTop | Qt.AlignRight,
    "ne": Qt.AlignTop | Qt.AlignRight,
    "left": Qt.AlignVCenter | Qt.AlignLeft,
    "w": Qt.AlignVCenter | Qt.AlignLeft,
    "center": Qt.AlignCenter,
    "right": Qt.AlignVCenter | Qt.AlignRight,
    "e": Qt.AlignVCenter | Qt.AlignRight,
    "bottomleft": Qt.AlignBottom | Qt.AlignLeft,
    "sw": Qt.AlignBottom | Qt.AlignLeft,
    "bottom": Qt.AlignBottom | Qt.AlignHCenter,
    "s": Qt.AlignBottom | Qt.AlignHCenter,
    "bottomright": Qt.AlignBottom | Qt.AlignRight,
    "se": Qt.AlignBottom | Qt.AlignRight,
}
anchor_points: dict[str, Qt.AnchorPoint] = {
    "left": Qt.AnchorLeft,
    "top": Qt.AnchorTop,
    "right": Qt.AnchorRight,
    "bottom": Qt.AnchorBottom,
    "v_center": Qt.AnchorVerticalCenter,
    "h_center": Qt.AnchorHorizontalCenter,
    "vcenter": Qt.AnchorVerticalCenter,
    "hcenter": Qt.AnchorHorizontalCenter
}
edge_names: dict[str, Qt.Edge] = {
    "top": Qt.TopEdge,
    "left": Qt.LeftEdge,
    "right": Qt.RightEdge,
    "bottom": Qt.BottomEdge
}
corner_names: dict[str, Qt.Corner] = {
    "top_left": Qt.TopLeftCorner,
    "top_right": Qt.TopRightCorner,
    "bottom_left": Qt.BottomLeftCorner,
    "bottom_right": Qt.BottomRightCorner,
}


def marginsArgs(left: Union[QtCore.QMarginsF, float], top=0.0,
                right=0.0, bottom=0.0) -> QtCore.QMarginsF:
    if isinstance(left, QtCore.QMarginsF):
        ms = QtCore.QMarginsF(left)
    elif isinstance(left, (int, float)):
        ms = QtCore.QMarginsF(left, top, right, bottom)
    else:
        raise TypeError(f"Not valid margins argument: {left}")
    return ms


def converter(to_type: type, pass_styled=False):
    def wrapper(f: Callable):
        converter_registry[to_type] = f
        if pass_styled:
            takes_styled_object.add(f)
        return f
    return wrapper


@converter(bool)
def boolConverter(value: Union[bool, str]) -> bool:
    if isinstance(value, str):
        t = value.lower()
        if t in ("on", "true", "yes"):
            return True
        elif t in ("off", "false", "no"):
            return False
        else:
            raise ValueError(value)
    else:
        return bool(value)


@converter(int)
def intConverter(value: Union[int, str]) -> int:
    if isinstance(value, str):
        value = int(value)
    return value


@converter(float)
def floatConverter(value: Union[float, str]) -> float:
    if isinstance(value, str):
        value = float(value)
    return value


@converter(Qt.Orientation)
def orientationConverter(orient: Union[str, Qt.Orientation]) -> Qt.Orientation:
    if isinstance(orient, str):
        orient = orient.lower()
        if orient in ("h", "horiz", "horizontal"):
            orient = Qt.Horizontal
        elif orient in ("v", "vert", "vertical"):
            orient = Qt.Vertical
        else:
            raise ValueError(f"Not an orientation: {orient!r}")
    return orient


@converter(QtGui.QBrush)
def brushConverter(brush: Union[str, QtGui.QBrush], *,
                   styled_object: WidgetType = None) -> Optional[QtGui.QBrush]:
    if isinstance(brush, str) and brush == "warning":
        from .themes import stripes
        brush = stripes(QtGui.QColor(255, 128, 0), QtGui.QColor(0, 0, 0))
    else:
        color = colorConverter(brush, styled_object=styled_object)
        brush = QtGui.QBrush(color)
    return brush


@converter(QtGui.QColor)
def colorConverter(color: ColorSpec) -> ColorSpec:
    from . import themes

    if isinstance(color, QtGui.QColor):
        return color
    elif isinstance(color, (list, tuple)):
        color = cast(Sequence[float], color)
        if len(color) >= 4:
            color = QtGui.QColor.fromRgbF(color[0], color[1], color[2], color[3])
        elif len(color) == 3:
            color = QtGui.QColor.fromRgbF(color[0], color[1], color[2])
        elif len(color) == 2:
            color = QtGui.QColor.fromRgbF(color[0], color[0], color[0], color[1])
        elif len(color) == 1:
            color = QtGui.QColor.fromRgbF(color[0], color[0], color[0])
        else:
            color = QtGui.QColor("#000000")
    elif isinstance(color, str) and color.startswith("#"):
        return QtGui.QColor(color)
    elif color in ("black", "white"):
        return QtGui.QColor(color)
    elif color == "transparent":
        color = Qt.transparent
    elif color in themes.ThemeColor.__members__:
        color = themes.ThemeColor.__members__[color]
    elif isinstance(color, (QtGui.QPalette.ColorRole, themes.ThemeColor)):
        pass
    else:
        raise TypeError(f"Not a color: {color!r}")
    return color


def toColor(color: ColorSpec, obj: core.Graphic) -> QtGui.QColor:
    from . import themes
    from .graphics import core

    if isinstance(color, QtGui.QColor):
        return color
    elif not isinstance(color, (str, QtGui.QPalette.ColorRole, themes.ThemeColor)):
        raise TypeError(f"Can't convert {color!r} to color")

    if isinstance(obj, core.Graphic) and not isinstance(color, QtGui.QColor):
        palette = obj.themePalette()
        if not palette:
            raise Exception(f"No theme palette on {obj}: {obj.parentItem()} / {obj.scene()}")

        color = palette.resolve(color)

    return color


def vectorConverter(vec: Union[str, Iterable]) -> Sequence[float]:
    if vec is None or vec == "":
        values = []
    elif isinstance(vec, str):
        # In the Houdini info tree, vectors are strings with square brackets
        # around comma separated values :/
        vec = vec.lstrip("[").rstrip("]")
        values = [float(v) for v in vec.split(",")]
    else:
        # Don't want to import hou here to check for hou.Vector3/hou.Vector4,
        # just try to iterate on all other value types, that will work with
        # Houdini vector objects
        values = tuple(vec)
    return values


def textSizeConverter(size: Union[int, str]) -> int:
    if isinstance(size, str):
        size = size.lower().replace("-", "")
        if size in text_sizes:
            size = text_sizes[size]
        else:
            raise ValueError(f"Unknown size: {size}")
    if not isinstance(size, int):
        raise TypeError(size)
    return size


@converter(QtCore.QSize)
def sizeFConverter(size: Union[QtCore.QSize, tuple[int, int]]
                   ) -> QtCore.QSizeF:
    if isinstance(size, (list, tuple)):
        size = QtCore.QSize(int(size[0]), int(size[1]))
    return size


@converter(QtCore.QSizeF)
def sizeFConverter(size: Union[QtCore.QSizeF, tuple[float, float]]
                   ) -> QtCore.QSizeF:
    if isinstance(size, (list, tuple)):
        size = QtCore.QSizeF(size[0], size[1])
    return size


@converter(QtCore.QPointF)
def pointFConverter(point: Union[QtCore.QPointF, tuple[float, float]]
                    ) -> QtCore.QPointF:
    if isinstance(point, (list, tuple)):
        point = QtCore.QPointF(point[0], point[1])
    return point


@converter(QtCore.QPoint)
def pointConverter(point: Union[QtCore.QPoint, tuple[int, int]]
                    ) -> QtCore.QPointF:
    if isinstance(point, (list, tuple)):
        point = QtCore.QPoint(point[0], point[1])
    return point


@converter(Qt.TextElideMode)
def elideModeConverter(mode: Union[str, bool, Qt.TextElideMode]
                       ) -> Qt.TextElideMode:
    if isinstance(mode, str):
        mode = mode.lower()
        if mode == "left":
            mode = Qt.ElideLeft
        elif mode == "right":
            mode = Qt.ElideRight
        elif mode == "middle" or mode == "center":
            mode = Qt.ElideMiddle
        elif mode == "none":
            mode = Qt.ElideNone
    elif mode is True:
        mode = Qt.ElideLeft
    elif mode is False:
        mode = Qt.ElideNone
    return mode


# @converter(QtGui.QPalette.ColorRole)
# def colorRoleConverter(role: Union[QtGui.QPalette.ColorRole, str]
#                        ) -> QtGui.QPalette.ColorRole:
#     raise Exception
#     if isinstance(role, str):
#         role = color_roles[role.lower()]
#     return role


@converter(QtGui.QIcon)
def iconConverter(icon: Union[QtGui.QIcon, str]) -> QtGui.QIcon:
    if isinstance(icon, str):
        import hou
        icon = hou.qt.Icon(icon)
    if not isinstance(icon, QtGui.QIcon):
        raise TypeError(icon)
    return icon


@converter(Qt.ItemDataRole)
def dataRoleConverter(role: Union[Qt.ItemDataRole, str]) -> Qt.ItemDataRole:
    if isinstance(role, str):
        role = data_roles[role]
    if not isinstance(role, (Qt.ItemDataRole, int)):
        raise TypeError(role)
    return role


def convertItemData(role: Union[Qt.ItemDataRole, str], value: Any) -> Any:
    role = dataRoleConverter(role)
    t = role_types.get(role)
    if t:
        converter_fn = converter_registry[t]
        value = converter_fn(value)
    return value


@converter(datetime)
def datetimeConverter(dt: Union[str, int, float, datetime]) -> datetime:
    if isinstance(dt, str):
        dt = datetime.strptime(dt, "%d-%b-%y %H:%M:%S")
    elif isinstance(dt, (int, float)):
        dt = datetime.fromtimestamp(dt)
    return dt


def numberTierConverter(tiers: Union[str, Sequence[tuple[int, str]]]
                        ) -> Sequence[tuple[int, str]]:
    if tiers == "memory":
        tiers = formatting.MEMORY_TIERS
    elif tiers == "disk":
        tiers = formatting.DISK_TIERS
    elif tiers is None:
        tiers = formatting.NUMBER_TIERS
    return tiers


# Can't register this for the charts.Chart type because importing charts would
# be a circular import
def chartConverter(chart: Union[str, dict, charts.ChartGraphic]
                   ) -> charts.ChartGraphic:
    from tilefx.graphics.charts import ChartGraphic

    if isinstance(chart, str):
        chart = {"type": chart}
    if isinstance(chart, dict):
        chart = ChartGraphic.fromData(chart)
    return chart


@converter(Qt.Edge)
def edgeConverter(edge: Union[Qt.Edge, str]) -> Qt.Edge:
    if isinstance(edge, str):
        name = edge.lower()
        if name in edge_names:
            edge = edge_names[name]
    if not isinstance(edge, Qt.Edge):
        raise ValueError(f"Not an edge: {edge!r}")
    return edge


@converter(Qt.AnchorPoint)
def anchorPointConverter(anchor: Union[Qt.AnchorPoint, str]) -> Qt.AnchorPoint:
    if isinstance(anchor, str):
        name = anchor.lower()
        if anchor in anchor_points:
            anchor = anchor_points[name]
    if not isinstance(anchor, Qt.AnchorPoint):
        raise ValueError(f"Not an anchor point: {anchor!r}")
    return anchor


@converter(Qt.Corner)
def cornerConverter(corner: Union[Qt.Corner, str]) -> Qt.Corner:
    if isinstance(corner, str):
        name = corner.lower()
        if corner in corner_names:
            corner = corner_names[name]
    if not isinstance(corner, Qt.Corner):
        raise ValueError(f"Not an anchor point: {corner!r}")
    return corner


@converter(Qt.Alignment)
def alignmentConverter(align: Union[Qt.Alignment, str]) -> Qt.Alignment:
    if isinstance(align, str):
        if align in alignment_names:
            return alignment_names[align]
        else:
            kws = set(align.split())
            # Horizontal
            if "right" in kws:
                align = Qt.AlignRight
            elif "center" in kws:
                align = Qt.AlignHCenter
            else:
                align = Qt.AlignLeft
            # Vertical
            if "top" in kws:
                align |= Qt.AlignTop
            elif "bottom" in kws:
                align |= Qt.AlignBottom
            else:
                align |= Qt.AlignVCenter
    return align


@converter(QtWidgets.QBoxLayout.Direction)
def directionConverter(direction: Union[str, QtWidgets.QBoxLayout.Direction]
                       ) -> QtWidgets.QBoxLayout.Direction:
    if isinstance(direction, QtWidgets.QBoxLayout.Direction):
        return direction
    elif direction in ("left", "left_to_right", "horizontal"):
        return QtWidgets.QBoxLayout.LeftToRight
    elif direction in ("right", "right_to_left"):
        return QtWidgets.QBoxLayout.RightToLeft
    elif direction in ("top", "top_to_bottom", "vertical"):
        return QtWidgets.QBoxLayout.TopToBottom
    elif direction in ("bottom", "bottom_to_top"):
        return QtWidgets.QBoxLayout.BottomToTop
    else:
        raise ValueError(direction)


@converter(QtCore.QMargins)
def marginsConverter(m: Union[int, Sequence[int]]) -> QtCore.QMargins:
    if not m:
        m = QtCore.QMargins(0, 0, 0, 0)
    elif isinstance(m, int):
        m = QtCore.QMargins(m, m, m, m)
    elif isinstance(m, (list, tuple)):
        if len(m) == 1:
            m = QtCore.QMargins(m[0], m[0], m[0], m[0])
        elif len(m) < 4:
            m = QtCore.QMargins(m[0], m[1], m[0], m[1])
        elif len(m) >= 4:
            m = QtCore.QMargins(*m[:4])
    return m


@converter(QtCore.QMarginsF)
def marginsFConverter(m: Union[float, Sequence[float]]) -> QtCore.QMarginsF:
    if not m:
        m = QtCore.QMarginsF(0, 0, 0, 0)
    elif isinstance(m, (int, float)):
        m = QtCore.QMarginsF(m, m, m, m)
    elif isinstance(m, (list, tuple)):
        if len(m) == 1:
            m = QtCore.QMarginsF(m[0], m[0], m[0], m[0])
        elif len(m) < 4:
            m = QtCore.QMarginsF(m[0], m[1], m[0], m[1])
        elif len(m) >= 4:
            m = QtCore.QMarginsF(*m[:4])
    return m


# Can't register this for the formatting.NumberFormatter type because importing
# formatting would cause a circular import
def formatConverter(fmt: Union[str, dict[str, Any], formatting.NumberFormatter]
                    ) -> formatting.NumberFormatter:
    from . import formatting

    if isinstance(fmt, str):
        fmt = {"type": fmt}
    if isinstance(fmt, dict):
        fmt = formatting.formatterFromData(fmt)
    return fmt


@converter(QtGui.QFont.Weight)
def fontWeightConverter(weight: Union[str, int, QtGui.QFont.Weight]
                        ) -> QtGui.QFont.Weight:
    # In Qt prior to v6, the values of the Weight enum are random ints, rather
    # than the typographically standard hundreds
    if isinstance(weight, str):
        weight = weight.lower().replace("_", "")
    if weight == "thin" or weight == 100:
        return QtGui.QFont.Thin
    elif weight == "extralight" or weight == 200:
        return QtGui.QFont.ExtraLight
    elif weight == "light" or weight == 300:
        return QtGui.QFont.Light
    elif weight == "normal" or weight == "regular" or weight == 400:
        return QtGui.QFont.Normal
    elif weight == "medium" or weight == 500:
        return QtGui.QFont.Medium
    elif weight == "demibold" or weight == 600:
        return QtGui.QFont.DemiBold
    elif weight == "bold" or weight == 700:
        return QtGui.QFont.Bold
    elif weight == "extrabold" or weight == 800:
        return QtGui.QFont.ExtraBold
    elif weight == "black" or weight == 900:
        return QtGui.QFont.Black
    return QtGui.QFont.Normal


@converter(QtGui.QFont)
def fontConverter(data: dict[str, Any] | QtGui.QFont,
                  base_font: QtGui.QFont = None) -> QtGui.QFont:
    if isinstance(data, QtGui.QFont):
        return data
    if not isinstance(data, dict):
        raise TypeError(f"Can't convert {data!r} to font")
    font = QtGui.QFont(base_font) if base_font else QtGui.QFont()
    family = data.get("family")
    if family is not None:
        font.setFamily(family)
    size = data.get("size")
    if size is not None:
        font.setPixelSize(textSizeConverter(size))
    bold = data.get("bold")
    if bold is not None:
        font.setBold(bool(bold))
    italic = data.get("italic")
    if italic is not None:
        font.setItalic(bool(italic))
    weight = data.get("weight")
    if weight:
        font.setWeight(fontWeightConverter(weight))
    return font


@converter(QtWidgets.QGraphicsLayout)
def graphicsLayoutConverter(layout: Union[str, dict, QtWidgets.QGraphicsLayout]
                            ) -> QtWidgets.QGraphicsLayout:
    # from hutil.qt.data.layouts import layout_registry

    if isinstance(layout, QtWidgets.QGraphicsLayout):
        return layout
    if isinstance(layout, str):
        layout = {"type": layout}
    if not isinstance(layout, dict):
        raise TypeError(layout)


def colorPolicyConverter(
        policy: Union[styling.ColorPolicy, Sequence[ColorSpec]]
                         ) -> styling.ColorPolicy:
    from .styling import ColorPolicy, MonochromeColorPolicy, ColorLookupPolicy
    from .themes import default_chart_colors

    if isinstance(policy, ColorPolicy):
        return policy
    # if isinstance(policy, str) and policy in NAMED_COLOR_POLICIES:
    #     return NAMED_COLOR_POLICIES[policy]
    elif isinstance(policy, str):
        color = colorConverter(policy)
        return MonochromeColorPolicy(color)
    elif isinstance(policy, (list, tuple)):
        if policy and all(isinstance(x, float) for x in policy):
            color = colorConverter(policy)
            return MonochromeColorPolicy(color)
        else:
            colors = [colorConverter(c) for c in policy]
            return ColorLookupPolicy(colors)
    return ColorLookupPolicy(default_chart_colors)

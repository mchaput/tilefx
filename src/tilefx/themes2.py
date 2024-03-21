from __future__ import annotations
import enum
from typing import Union

from PySide2 import QtCore, QtGui


class Clr(enum.Enum):
    blue = enum.auto()
    green = enum.auto()
    indigo = enum.auto()
    orange = enum.auto()
    magenta = enum.auto()
    purple = enum.auto()
    plum = enum.auto()
    red = enum.auto()
    cyan = enum.auto()
    yellow = enum.auto()
    kiwi = enum.auto()
    peach = enum.auto()
    pink = enum.auto()
    steel = enum.auto()
    tan = enum.auto()
    mint = enum.auto()
    gray = enum.auto()


color_names: dict[str, Clr] = {
    "blue": Clr.blue,
    "indigo": Clr.indigo,
    "orange": Clr.orange,
    "magenta": Clr.magenta,
    "purple": Clr.purple,
    "plum": Clr.plum,
    "red": Clr.red,
    "cyan": Clr.cyan,
    "yellow": Clr.yellow,
    "peach": Clr.peach,
    "pink": Clr.pink,
    "steel": Clr.steel,
    "tan": Clr.tan,
    "mint": Clr.mint,
    "gray": Clr.gray,
}


DARK_COLORS: dict[Clr, QtGui.QColor] = {
    Clr.blue: QtGui.QColor("#3399ff"),
    Clr.green: QtGui.QColor("#30d158"),
    Clr.indigo: QtGui.QColor("#6e6cff"),
    Clr.orange: QtGui.QColor("#ff9f0a"),
    Clr.magenta: QtGui.QColor("#ee5c93"),
    Clr.purple: QtGui.QColor("#bf5af2"),
    Clr.plum: QtGui.QColor("#891f91"),
    Clr.red: QtGui.QColor("#ff5151"),
    Clr.cyan: QtGui.QColor("#64d2ff"),
    Clr.yellow: QtGui.QColor("#ffd60a"),
    Clr.kiwi: QtGui.QColor("#96d130"),
    Clr.peach: QtGui.QColor("#e2af8e"),
    Clr.pink: QtGui.QColor("#ffa9a9"),
    Clr.steel: QtGui.QColor("#a9c6e7"),
    Clr.tan: QtGui.QColor("#ceb4a4"),
    Clr.mint: QtGui.QColor("#8dcaa9"),
    Clr.gray: QtGui.QColor("#919191"),
}
LIGHT_COLORS: dict[Clr, QtGui.QColor] = {
    Clr.blue: QtGui.QColor(0, 110, 229),
    Clr.green: QtGui.QColor(36, 161, 68),
    Clr.indigo: QtGui.QColor(88, 86, 214),
    Clr.orange: QtGui.QColor(255, 102, 0),
    Clr.magenta: QtGui.QColor(255, 104, 133),
    Clr.purple: QtGui.QColor(175, 82, 222),
    Clr.red: QtGui.QColor(207, 0, 0),
    Clr.cyan: QtGui.QColor(17, 153, 215),
    Clr.yellow: QtGui.QColor(246, 190, 0),
    Clr.kiwi: QtGui.QColor(99, 144, 19),
    Clr.peach: QtGui.QColor(192, 123, 79),
    Clr.pink: QtGui.QColor(210, 137, 137),
    Clr.steel: QtGui.QColor(104, 121, 140),
    Clr.tan: QtGui.QColor(147, 134, 127),
    Clr.mint: QtGui.QColor(93, 146, 117),
    Clr.gray: QtGui.QColor(179, 179, 179),
}


DEFAULT_CHART_COLORS = (Clr.red, Clr.blue, Clr.yellow, Clr.green, Clr.pink,
                        Clr.cyan, Clr.purple, Clr.peach, Clr.tan, Clr.plum,
                        Clr.mint, Clr.gray)


def themeColor(c: Union[str, Clr, QtGui.QColor], palette: QtGui.QPalette = None
               ) -> QtGui.QColor:
    if isinstance(c, str):
        c = color_names[c]
    if isinstance(c, Clr):
        if palette:
            bg = palette.color(palette.Window)
            isdark = bg.lightnessF() < 0.5
            colorset = DARK_COLORS if isdark else LIGHT_COLORS
        else:
            colorset = DARK_COLORS
        return colorset[c]
    elif isinstance(c, QtGui.QColor):
        return c
    else:
        raise TypeError(f"Can't use {c} as a color")

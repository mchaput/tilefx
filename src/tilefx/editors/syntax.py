from __future__ import annotations
import enum
import re
from typing import Callable, Iterable, Optional, Pattern, Union

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt


ws_expr = re.compile(r"\s+")
unichar_expr = re.compile(r"\\u[A-Fa-f-0-9]{4}")
number_expr = re.compile(r"""
\b  # only match after a break
[-+]?  # Optionally start with a sign
\d(\d|_\d)*  # Underscores are allowed but not at start or end
(
    [.]
    \d(\d|_\d)*  # Fractional part
    ([eE]\d(\d|_\d)*)?  # Scientific notation
)?
\b # only match before a break
""", re.VERBOSE)


class Style(enum.Enum):
    plain = enum.auto()
    string = enum.auto()
    var = enum.auto()
    func = enum.auto()
    keyword = enum.auto()
    quote = enum.auto()
    number = enum.auto()
    ref = enum.auto()
    comment = enum.auto()
    error = enum.auto()
    type = enum.auto()
    extra = enum.auto()


StyleLookup = Callable[[Style], QtGui.QColor]

style_to_hcs_name: dict[Style, str] = {
    Style.plain: "ParmSyntaxPlainColor",
    Style.string: "ParmSyntaxStringColor",
    Style.var: "ParmSyntaxVarColor",
    Style.func: "ParmSyntaxFuncColor",
    Style.keyword: "ParmSyntaxKeywordColor",
    Style.quote: "ParmSyntaxQuoteColor",
    Style.number: "ParmSyntaxNumberColor",
    Style.ref: "ParmSyntaxRefColor",
    Style.comment: "ParmSyntaxCommentColor",
    Style.error: "ParmSyntaxErrorColor",
    Style.type: "ParmSyntaxTypeColor",
    Style.extra: "ParmSyntaxExtraColor",
}

default_colors: dict[Style, QtGui.QColor] = {
    Style.plain: QtGui.QColor("#E0E2E4"),
    Style.string: QtGui.QColor("#B6DBDB"),
    Style.var: QtGui.QColor("#C892CA"),
    Style.func: QtGui.QColor("#608EBE"),
    Style.keyword: QtGui.QColor("#93C663"),
    Style.quote: QtGui.QColor("#FFD6ED"),
    Style.number: QtGui.QColor("#FCCA22"),
    Style.ref: QtGui.QColor("#E8E2B8"),
    Style.comment: QtGui.QColor("#A7A8A7"),
    Style.error: QtGui.QColor("#E14640"),
    Style.type: QtGui.QColor("#93A7BB"),
    Style.extra: QtGui.QColor("#E36DD6"),
}


def nullStyleColor(style: Style) -> QtGui.QColor:
    return QtGui.QColor(0, 0, 0)


def defaultStyleColor(style: Style) -> QtGui.QColor:
    return default_colors.get(style)


def houdiniStyleColor(style: Style) -> QtGui.QColor:
    import hou

    colorname = style_to_hcs_name[style]
    return hou.qt.toQColor(hou.ui.colorFromName(colorname))


def alts(names: Iterable[str]) -> str:
    return "|".join(re.escape(t) for t in names)


def keywordExpr(names: Iterable[str]) -> Pattern:
    return re.compile("(" + alts(names) + r")\b")


# QSyntaxHighlighter only allows passing a single int of "state" between lines.
# For languages that need a stack (e.g. trying to color object keys differently
# from other strings in JSON), we can hack it by packing a few bits for each
# level of the stack into the "state" int.
def bitstackPush(stackbits: int, bits: int, size=2) -> int:
    return (stackbits << size) | bits


def bitstackPop(stackbits: int, size: int) -> tuple[int, int]:
    return stackbits >> size, stackbits | (2**size-1)


def bitstackTrim(stackbits: int, size: int) -> int:
    return stackbits >> size


def bitstackReplace(stackbits: int, bits: int, size: int) -> int:
    return ((stackbits >> size) << size) | bits


def bitstackPeek(stackbits: int, size: int) -> int:
    return stackbits & (2**size-1)


def syntaxHighlighterConverter(
        hiliter: Union[str, QtGui.QSyntaxHighlighter]
        ) -> Union[QtGui.QSyntaxHighlighter, type[QtGui.QSyntaxHighlighter]]:
    if hiliter == "json":
        from .json import JsonHighlighter
        return JsonHighlighter
    elif hiliter == "python":
        from .python import PythonHighlighter
        return PythonHighlighter
    elif hiliter == "expression":
        from .houdini import ExpressionHighlighter
        return ExpressionHighlighter
    elif hiliter == "vex":
        from .houdini import VexHighlighter
        return VexHighlighter
    elif hiliter == "regex":
        from .regex import RegexHighlighter
        return RegexHighlighter
    elif hiliter == "asset_name":
        from assettools import AssetNameHighlighter
        return AssetNameHighlighter
    elif hiliter == "jsonpathfx":
        from .json import JsonpathHighlighter
        return JsonpathHighlighter
    elif isinstance(hiliter, str):
        raise ValueError(f"Unknown syntax highlighter: {hiliter}")
    if not isinstance(hiliter, QtGui.QSyntaxHighlighter):
        raise TypeError(hiliter)
    return hiliter


class HighlighterBase(QtGui.QSyntaxHighlighter):
    def __init__(self, parent: QtCore.QObject = None):
        super().__init__(parent)
        self.styleColor: StyleLookup = houdiniStyleColor

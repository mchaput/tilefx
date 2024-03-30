from __future__ import annotations
import enum

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .syntax import HighlighterBase, Style


class RegexState(enum.Enum):
    normal = enum.auto()
    char_set_start = enum.auto()
    char_set = enum.auto()


class RegexHighlighter(HighlighterBase):
    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self._active = True

    def setActive(self, active: bool) -> None:
        self._active = active
        self.rehighlight()

    def highlightBlock(self, line: str) -> None:
        if not self._active:
            return
        pos = 0
        state = RegexState.normal
        while pos < len(line):
            char = line[pos]
            style = Style.plain
            inc = 1
            if char == "\\":
                if pos < len(line) + 1:
                    style = Style.quote
                    inc = 2
                else:
                    style = Style.error
            elif state in (RegexState.char_set, RegexState.char_set_start):
                if char == "]":
                    state = RegexState.normal
                elif char == "-" and state == RegexState.char_set:
                    style = Style.keyword
                else:
                    state = RegexState.char_set
                    style = Style.string

            elif char == "[":
                state = RegexState.char_set_start

            elif char in "().+?*^$":
                style = Style.func

            self.setFormat(pos, pos + inc, self.styleColor(style))
            pos += inc

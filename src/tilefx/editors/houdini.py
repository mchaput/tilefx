from __future__ import annotations
import enum
import re
from typing import Iterable, Optional, Pattern, Union

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .syntax import HighlighterBase, keywordExpr, ws_expr, Style


class ExpressionHighlighter(HighlighterBase):
    func_expr = re.compile(r"(^|(?<=\W))[A-Za-z_][A-Za-z_0-9]*(?=[(])")
    var_expr = re.compile("[@$]([A-Za-z_][A-Za-z_0-9]*)?")

    def highlightBlock(self, line: str) -> None:
        pos = 0
        in_string: Optional[str] = None
        while pos < len(line):
            char = line[pos]
            prev = pos
            style = Style.plain
            if char == "\\":
                if pos < len(line) + 1:
                    style = Style.quote
                    pos += 2
                else:
                    style = Style.error
                    pos += 1
            elif in_string:
                style = Style.string
                if char == in_string:
                    in_string = None
                pos += 1
            elif char in "'\"":
                style = Style.string
                in_string = char
                pos += 1
            elif m := number_expr.match(line, pos):
                style = Style.number
                pos = m.end()
            elif m := self.func_expr.match(line, pos):
                style = Style.func
                pos = m.end()
            elif m := self.var_expr.match(line, pos):
                style = Style.var
                pos = m.end()
            else:
                pos += 1

            self.setFormat(prev, pos, self.styleColor(style))


VEX_KEYWORDS = ("if", "else", "for", "while", "break", "continue",
                "illuminance", "forpoints", "foreach", "gather", "do", "return",
                "export", "const", "_Pragma")
VEX_TYPES = ("int", "float", "vector4", "vector", "vector2", "matrix2",
             "matrix3", "matrix", "dict", "bsdf", "string", "void",
             )

kw_expr = keywordExpr(VEX_KEYWORDS)
type_expr = keywordExpr(VEX_TYPES)
attr_expr = re.compile(r"[fuvpi234sd]?@[A-Za-z_][A-Za-z0-9_]*")
call_expr = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?=\s*[(])")
identifier_expr = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# In VEX, "1." and ".0" are valid numbers
number_expr = re.compile(r"""
[-+]?  # optional sign at start
(  # Either...
([0-9]+([.][0-9]*)?)  # whole number with optional decimal
|  # or...
([.][0-9]+)  # only a decimal
)
(e[0-9]+)?  # optional exponent
""", re.VERBOSE)


class VexState(enum.IntEnum):
    normal = enum.auto()
    double_quoted = enum.auto()
    single_quoted = enum.auto()
    line_comment = enum.auto()
    block_comment = enum.auto()
    preproc_comment = enum.auto()
    attribute = enum.auto()


def vex_token(state: VexState, line: str, pos=0) -> tuple[Style, int, VexState]:
    # Returns tuple of style, end position, next state
    if state == VexState.block_comment:
        if pos < len(line) - 1 and line.startswith("*/", pos):
            return Style.comment, pos + 2, VexState.normal
        else:
            while pos < len(line) and not line.startswith("*/", pos):
                pos += 1
            return Style.comment, pos, VexState.block_comment

    elif state == VexState.line_comment:
        return Style.comment, len(line), VexState.normal

    elif state == VexState.preproc_comment:
        style = Style.extra
        if pos < len(line) and line[pos] == "\\":
            style = Style.quote
            pos += 2
        else:
            while pos < len(line) and line[pos] != "\\":
                pos += 1
        if pos == len(line):
            state = VexState.normal
        return style, pos, state

    elif state == VexState.double_quoted or state == VexState.single_quoted:
        if state == VexState.double_quoted:
            endchar = '"'
        else:
            endchar = "'"
        style = Style.string
        if pos < len(line):
            char = line[pos]
            if char == "\\":
                style = Style.quote
                pos += 2
            elif char == endchar:
                state = VexState.normal
                pos += 1
            else:
                while pos < len(line) and char != "\\" and char != endchar:
                    pos += 1
                    if pos == len(line):
                        break
                    char = line[pos]
        return style, pos, state

    elif state == VexState.single_quoted:
        style = Style.string
        if pos < len(line):
            char = line[pos]
            if char == "\\":
                style = Style.quote
                pos += 2
            elif char == '"':
                state = VexState.normal
                pos += 1
            else:
                while pos < len(line) and line[pos] not in '\\"':
                    pos += 1
        return style, pos, state

    elif state == VexState.normal:
        has2 = pos < len(line) - 1
        if m := ws_expr.match(line, pos):
            return Style.plain, m.end(), VexState.normal
        elif m := kw_expr.match(line, pos):
            return Style.keyword, m.end(), VexState.normal
        elif m := type_expr.match(line, pos):
            return Style.type, m.end(), VexState.normal
        elif m := attr_expr.match(line, pos):
            return Style.ref, m.end(), VexState.normal
        # check number after attr because attr can start with a digit (3@foo)
        elif m := number_expr.match(line, pos):
            return Style.number, m.end(), VexState.normal
        elif m := call_expr.match(line, pos):
            return Style.func, m.end(1), VexState.normal
        elif m := identifier_expr.match(line, pos):
            # Var?
            return Style.plain, m.end(), VexState.normal
        elif has2 and line.startswith("//", pos):
            return Style.comment, len(line), VexState.normal
        elif has2 and line.startswith("/*", pos):
            return Style.comment, pos + 2, VexState.block_comment
        else:
            char = line[pos]
            if char == "#" and (pos == 0 or line[:pos].isspace()):
                return Style.extra, pos + 1, VexState.preproc_comment
            if char == "'":
                return Style.string, pos + 1, VexState.single_quoted
            elif char == '"':
                return Style.string, pos + 1, VexState.double_quoted

    return Style.plain, pos + 1, state


class VexHighlighter(HighlighterBase):
    def highlightBlock(self, text: str) -> None:
        stateint = self.previousBlockState()
        state: VexState = (VexState(stateint) if stateint > -1
                           else VexState.normal)
        pos = 0
        while pos < len(text):
            style, endpos, state = vex_token(state, text, pos)
            if endpos <= pos:
                raise Exception("VEX lexer did not move forward")
            color = self.styleColor(style)
            self.setFormat(pos, endpos, color)
            pos = endpos

        self.setCurrentBlockState(state.value)

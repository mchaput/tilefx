from __future__ import annotations
import enum
import re
from typing import NamedTuple

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .syntax import HighlighterBase, Style, number_expr


c_escape = re.compile(r"\\[\\nrtbf'\"]")
x_escape = re.compile(r"\\x[A-Fa-f0-9]{2}")
u_escape = re.compile(r"\\u[A-Fa-f0-9]{4}")
line_cont = re.compile(r"\\\s*$")
kw_expr = re.compile(r"""
\b
(and|as|assert|async|await|break|class|continue|def|del|elif|else|except|
finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|
return|try|while|with|yield)
\b
""", re.VERBOSE)
return_anno = re.compile(r"(?<=->)[^:]+($|(?=:))")
soft_kw_expr = re.compile(r"\s*(match|case|type)\s+")
func_expr = re.compile(r"(^|\s|[.])[A-Za-z_][A-Za-z_0-9]*(?=[(])")
class_expr = re.compile(r"\bclass\b")
def_expr = re.compile(r"\bdef\b")
arrow_expr = re.compile(r"\s*->\s*")
colon_expr = re.compile(r":\s*$")
special_expr = re.compile(r"\b(self|True|False|None)\b")
decorator_expr = re.compile(r"^\s*@[A-Za-z_][A-Za-z_0-9.]*($|(?=[(]))")


class State(enum.IntEnum):
    normal = enum.auto()
    in_class = enum.auto()
    in_def = enum.auto()
    sq_string = enum.auto()
    dq_string = enum.auto()
    tri_sq_string = enum.auto()
    tri_dq_string = enum.auto()


class Token(NamedTuple):
    style: Style
    end_pos: int
    new_state: State | int
    continues: bool = False


def token(state_int: int, line: str, pos=0) -> Token:
    if state_int < 0:
        state_int = 1
    state: State = State(state_int & 15)
    type_level = state_int >> 4

    char = line[pos]

    if type_level == 1 and char in ",=():":
        type_level = 0
        state_int = state

    if state in (State.sq_string, State.dq_string, State.tri_sq_string,
                 State.tri_dq_string):
        style = Style.string
        is_triple = state in (State.tri_sq_string, State.tri_dq_string)
        if m := c_escape.match(line, pos):
            style = Style.quote
            pos = m.end()
        elif m := x_escape.match(line, pos):
            style = Style.quote
            pos = m.end()
        elif m := u_escape.match(line, pos):
            style = Style.quote
            pos = m.end()
        elif m := line_cont.match(line, pos):
            return Token(Style.quote, m.end(), state_int, continues=True)
        elif char == "\\":
            style = Style.error
            pos += 1
        elif (
            (state == State.tri_sq_string and line.startswith("'''", pos)) or
            (state == State.tri_dq_string and line.startswith('"""', pos))
        ):
            return Token(Style.string, pos + 3, State.normal)
        elif (
            (state == State.sq_string and line.startswith("'", pos)) or
            (state == State.dq_string and line.startswith('"', pos))
        ):
            return Token(Style.string, pos + 1, State.normal)
        else:
            pos += 1
            # Fast-forward to the next interesting char
            while pos < len(line) and line[pos] not in "'\"\\":
                pos += 1

        if pos == len(line) and not is_triple:
            state = State.normal
        return Token(style, pos, state, continues=is_triple)

    elif char == "#":
        return Token(Style.comment, len(line), state)

    elif m := line_cont.match(line, pos):
        return Token(Style.quote, m.end(), state_int, continues=True)

    elif type_level:
        if (state == State.in_class or state == State.in_def) and type_level == 2 and char == "]":
            return Token(Style.plain, pos + 1, state)
        elif type_level > 1 and char == "]":
            return Token(Style.plain, pos + 1,
                         ((type_level - 1) << 4) | state.value)
        elif char == "[":
            return Token(Style.plain, pos + 1,
                         ((type_level + 1) << 4) | state.value)
        else:
            return Token(Style.type, pos + 1, state_int)

    elif line.startswith('"""', pos):
        return Token(Style.string, pos + 3, State.tri_dq_string, continues=True)

    elif line.startswith("'''", pos):
        return Token(Style.string, pos + 3, State.tri_sq_string, continues=True)

    elif line.startswith('"', pos):
        state = State.dq_string if pos + 1 < len(line) else State.normal
        return Token(Style.string, pos + 1, state)

    elif line.startswith("'", pos):
        state = State.sq_string if pos + 1 < len(line) else State.normal
        return Token(Style.string, pos + 1, state)

    elif m := class_expr.match(line, pos):
        return Token(Style.keyword, m.end(), State.in_class)

    elif state == State.in_class or state == State.in_def:
        if char == "[":
            return Token(Style.plain, pos + 1, (2 << 4) | state.value)
        elif char in "(:":
            return Token(Style.plain, pos + 1, State.normal)
        else:
            style = Style.type if state == State.in_class else Style.func
            return Token(style, pos + 1, state)

    elif m := arrow_expr.match(line, pos):
        return Token(Style.plain, m.end(), (1 << 4) | state.value)

    elif m := colon_expr.match(line, pos):
        return Token(Style.plain, m.end(), State.normal)

    elif char == ":":
        return Token(Style.plain, pos + 1, (1 << 4) | state.value)

    elif m := def_expr.match(line, pos):
        return Token(Style.keyword, m.end(), State.in_def)

    elif m := decorator_expr.match(line, pos):
        return Token(Style.extra, m.end(), state)

    elif m := special_expr.match(line, pos):
        return Token(Style.extra, m.end(), state)

    elif m := func_expr.match(line, pos):
        return Token(Style.func, m.end(), state)

    elif m := kw_expr.match(line, pos):
        return Token(Style.keyword, m.end(), state)

    elif m := soft_kw_expr.match(line, pos):
        return Token(Style.keyword, m.end(), state)

    elif m := return_anno.match(line, pos):
        return Token(Style.type, m.end(), state)

    elif m := number_expr.match(line, pos):
        return Token(Style.number, m.end(), state)
    else:
        return Token(Style.plain, pos + 1, state_int)


class PythonHighlighter(HighlighterBase):
    def highlightBlock(self, text: str) -> None:
        state_int = self.previousBlockState()
        pos = 0
        continues = False
        while pos < len(text):
            style, endpos, state_int, continues = token(state_int, text, pos)
            # print("pos=", endpos, "style=", style, "state=",
            #       State(state_int & 15), state_int >> 4)
            if endpos <= pos:
                raise Exception(
                    f"Lexer stalled in state {state_int} @{pos} in {text!r}"
                )
            color = self.styleColor(style)
            self.setFormat(pos, endpos, color)
            pos = endpos

        type_level = state_int >> 4
        if state_int <= 0:
            state_int = State.normal
        # print("->", pos, state_int, State(state_int & 15),
        #       state_int >> 4, save_state)
        if not (continues or type_level > 1):
            state_int = State.normal
        self.setCurrentBlockState(state_int)

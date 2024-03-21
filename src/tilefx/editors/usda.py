from __future__ import annotations
import enum
import re
from typing import Iterable, Optional, Tuple

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .syntax import Style, keywordExpr, styleColor, number_expr


USDA_KEYWORDS = ("prepend", "add", "append", "delete", "def", "over", "class",
                 "uniform", "custom")
SPEC_KEYWORDS = ("def", "over", "class")
MOD_KEYWORDS = ("prepend", "add", "append", "delete")
PROPSPEC_KEYWORDS = ("uniform", "custom") + MOD_KEYWORDS

newline_expr = re.compile(r"\n|\r\n|\r|\u2028|\u2029")
ws_expr = re.compile(r"\s+")
kw_expr = keywordExpr(USDA_KEYWORDS)
singleton_expr = re.compile("true|false|None")
unicode_id_pattern = r"(?:((?!\d)\w+(?:\.(?!\d)\w+)*)\.)?((?!\d)\w+)"
ascii_id_pattern = r"[a-zA-Z_]+[a-zA-Z_0-9]*"
id_pattern = ascii_id_pattern
id_expr = re.compile(id_pattern)

format_expr = re.compile(r"#(usda|sdf)\s\d+[.]\d+")
stage_ref_expr = re.compile(rf"<({id_pattern}|/|[.]|:)*>")
external_expr = re.compile(r"@[^@]*@")

prim_spec_expr = re.compile(rf"""
(?P<kw>def|over|class)
\s+
(?P<type>{id_pattern}\s*)?
"(?P<name>{id_pattern})"
""", re.VERBOSE)

prop_expr = re.compile(rf"""
(?P<kws>((uniform|custom|prepend|add|append|delete)\s+)*)
(?P<type>{id_pattern}(\[])?)
\s+
(?P<name>({id_pattern}:)*{id_pattern}([.]{id_pattern})?)
""", re.VERBOSE)

variantset_expr = re.compile(rf"""
(?P<kw>variantSet)
\s*
"(?P<name>{id_pattern})"
""", re.VERBOSE)

metadata_expr = re.compile(rf"""
(?P<kws>((prepend|add|append|delete)\s+)*)
(?P<name>{id_pattern})
""")

# spec_expr = re.compile(r"\s*" + alts(SPEC_KEYWORDS))
# listmod_expr = re.compile(r"\s*" + alts(MOD_KEYWORDS))
# prop_spec_expr = re.compile(r"\s*" + alts(PROPSPEC_KEYWORDS))
# variantset_expr = re.compile(r"\s*variantSet\b")
# prim_name_expr = re.compile('"' + id_pattern + '"')
# prop_name_expr = re.compile("(" + id_pattern + ":)*" + id_pattern +
#                             "([.]" + id_pattern + ")?")


class State(enum.IntEnum):
    normal = enum.auto()
    array = enum.auto()
    double_quoted = enum.auto()
    single_quoted = enum.auto()
    triple_single_quoted = enum.auto()
    triple_double_quoted = enum.auto()


# class Style(enum.Enum):
#     plain = enum.auto()
#     string = enum.auto()
#     var = enum.auto()
#     func = enum.auto()
#     keyword = enum.auto()
#     quote = enum.auto()
#     number = enum.auto()
#     ref = enum.auto()
#     comment = enum.auto()
#     error = enum.auto()
#     type = enum.auto()
#     extra = enum.auto()


def tokens(state: State, line: str, pos: int
           ) -> Iterable[tuple[Style, int, State]]:
    style = Style.plain

    if state == State.array:
        # Arrays can be very long, so we special case to try to get through them
        # quickly
        while pos < len(line) and not line.startswith("]", pos):
            pos += 1
        if pos < len(line):
            yield style, pos + 1, State.normal
        else:
            yield style, pos, state

    elif m := ws_expr.match(line, pos):
        yield style, m.end(), state

    elif state in (State.single_quoted, State.double_quoted,
                   State.triple_single_quoted, State.triple_double_quoted):
        if state == State.single_quoted:
            ending = "'"
        elif state == State.double_quoted:
            ending = '"'
        elif state == State.triple_single_quoted:
            ending = "'''"
        else:
            ending = '"""'

        style = Style.string
        if pos <= len(line) - 2 and line.startswith("\\", pos):
            style = Style.quote
            pos += 2
        elif line.startswith(ending, pos):
            state = State.normal
            pos += len(ending)
        else:
            while pos < len(line) and not line.startswith(ending, pos):
                pos += 1
            # For single line strings, end the style if we get to the end of the
            # line and it's not closed
            if pos == len(line) and state in (State.single_quoted,
                                              State.double_quoted):
                state = State.normal
        yield style, pos, state

    elif m := format_expr.match(line, pos):
        yield Style.extra, m.end(), state

    elif m := number_expr.match(line, pos):
        yield Style.number, m.end(), state

    elif m := singleton_expr.match(line, pos):
        yield Style.type, m.end(), state

    elif m := stage_ref_expr.match(line, pos):
        yield Style.ref, m.end(), state

    elif m := external_expr.match(line, pos):
        yield Style.ref, m.end(), state

    elif m := prim_spec_expr.match(line, pos):
        yield Style.keyword, m.end("kw"), state
        if m.group("type"):
            yield Style.type, m.end("type"), state
        yield Style.var, m.end(), state

    elif m := prop_expr.match(line, pos):
        if m.group("kws"):
            yield Style.keyword, m.end("kws"), state
        yield Style.type, m.end("type"), state
        yield Style.var, m.end(), state

    elif m := variantset_expr.match(line, pos):
        yield Style.keyword, m.end("kw"), state
        yield Style.var, m.end(), state

    # elif m := metadata_expr.match(line, pos):
    #     if m.group("kws"):
    #         yield Style.keyword, m.end("kws"), state
    #     yield Style.var, m.end(), state

    elif line.startswith("'''", pos):
        yield Style.string, pos + 3, State.triple_single_quoted

    elif line.startswith('"""', pos):
        yield Style.string, pos + 3, State.triple_double_quoted

    elif m := kw_expr.match(line, pos):
        yield Style.keyword, m.end(), state

    else:
        char = line[pos]
        pos += 1
        if char == "#":
            yield Style.comment, len(line), state
        elif char == "[":
            yield Style.plain, pos, State.array
        elif char == "'":
            yield Style.string, pos, State.single_quoted
        elif char == '"':
            yield Style.string, pos, State.double_quoted
        else:
            yield Style.plain, pos, state


class UsdaHighlighter(QtGui.QSyntaxHighlighter):
    def highlightBlock(self, text: str) -> None:
        stateint = self.previousBlockState()
        state: State = State(stateint) if stateint > -1 else State.normal
        pos = 0
        while pos < len(text):
            for style, endpos, state in tokens(state, text, pos):
                if endpos <= pos:
                    raise Exception(
                        f"USDA lexer stuck at {state} {pos} {style}: {text!r}"
                    )
                self.setFormat(pos, endpos, styleColor(style))
                pos = endpos

        self.setCurrentBlockState(state.value)

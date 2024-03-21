from __future__ import annotations
import enum
from typing import TYPE_CHECKING, Optional, Union

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .syntax import (bitstackPeek, bitstackPush, bitstackReplace, bitstackTrim,
                     number_expr, unichar_expr, ws_expr, styleColor, Style)

if TYPE_CHECKING:
    from jsonpathfx import Kind


class JsonState(enum.IntEnum):
    object = 0
    object_key = 1
    array = 2


# Each level of state requires 2 bits
JSON_STATE_SIZE = 2


def json_token(stackbits: int, line: str, pos: int, in_string=False,
               ) -> tuple[Style, int, Union[JsonState, int], bool]:
    # We want to color object keys differently from value strings, so we have
    # to maintain a stack, which we hack by packing the "state" at each level
    # into the bits of the 32 bit int
    state = JsonState(bitstackPeek(stackbits, JSON_STATE_SIZE))
    char = line[pos]

    if in_string and unichar_expr.match(line, pos):
        # Matches \u followed by 4 hex digits
        return Style.quote, pos + 6, state, in_string

    elif char == "\\":
        # According to the JSON spec, only certain characters can follow a
        # backslash
        if pos <= len(line) - 2 and line[pos + 1] in '"\\/bfnrt':
            return Style.quote, pos + 2, state, in_string
        else:
            return Style.error, pos + 1, state, in_string

    elif in_string and char == '"':
        # JSON only allows double-quoted strings
        if state == JsonState.object_key:
            style = Style.keyword
        else:
            style = Style.string
        return style, pos + 1, stackbits, False

    elif in_string:
        if state == JsonState.object_key:
            style = Style.keyword
        else:
            style = Style.string

        # Seek along quickly until we find a backslash or end quotes
        while pos < len(line) and line[pos] not in '"\\':
            pos += 1

        return style, pos, stackbits, in_string

    elif char == '"':
        if state == JsonState.object_key:
            style = Style.keyword
        else:
            style = Style.string
        return style, pos + 1, stackbits, True

    elif char in "{[":
        style = Style.plain
        ns = state
        if char == "{":
            ns = JsonState.object_key
        elif char == "[":
            ns = JsonState.array
        newstack = bitstackPush(stackbits, ns, JSON_STATE_SIZE)
        # Qt only saves state as a 32-bit int. Since we use 2 bits per level,
        # we can only store up to 15 levels of stack. After that we just ignore
        # pushes!
        if newstack > 2**31:
            # Don't change the stack, otherwise Qt will throw an overflow error
            return style, pos + 1, stackbits, False
        else:
            return style, pos + 1, newstack, False

    elif char == "}":
        if state in (JsonState.object_key, JsonState.object):
            style = Style.plain
        else:
            style = Style.error
        return style, pos + 1, bitstackTrim(stackbits, JSON_STATE_SIZE), False

    elif char == "]":
        if state == JsonState.array:
            style = Style.plain
        else:
            style = Style.error
        return style, pos + 1, bitstackTrim(stackbits, JSON_STATE_SIZE), False

    elif char == ":":
        if state == JsonState.object_key:
            style = Style.plain
            newstack = bitstackReplace(stackbits, JsonState.object,
                                       JSON_STATE_SIZE)
        else:
            style = Style.error
            newstack = stackbits
        return style, pos + 1, newstack, False

    elif char == ",":
        style = Style.plain
        newstack = stackbits
        if state == JsonState.object:
            newstack = bitstackReplace(stackbits, JsonState.object_key,
                                       JSON_STATE_SIZE)
        elif state != JsonState.array:
            style = Style.error
        return style, pos + 1, newstack, False

    elif line.startswith("true", pos):
        return Style.type, pos + 4, stackbits, False

    elif line.startswith("false", pos):
        return Style.type, pos + 5, stackbits, False

    elif line.startswith("null", pos):
        return Style.type, pos + 4, stackbits, False

    elif m := ws_expr.match(line, pos):
        return Style.plain, m.end(), stackbits, False

    elif m := number_expr.match(line, pos):
        return Style.number, m.end(), stackbits, False

    else:
        # Technically this could be "error", but it's a bad experience if
        # everything the user types is colored as "error" until they finish
        return Style.plain, pos + 1, stackbits, False


class JsonHighlighter(QtGui.QSyntaxHighlighter):
    def highlightBlock(self, text: str) -> None:
        stackbits = self.previousBlockState()
        if stackbits == -1:
            stackbits = 0
        pos = 0
        # We don't care about multi-line strings, so we don't need to record if
        # we're in a string into the state, we just maintain it for the current
        # line
        in_string = False
        while pos < len(text):
            style, endpos, stackbits, in_string = \
                json_token(stackbits, text, pos, in_string)
            if endpos <= pos:
                raise Exception(f"JSON lexer stuck at {pos}: {text!r}")
            self.setFormat(pos, endpos, styleColor(style))
            pos = endpos

        self.setCurrentBlockState(int(stackbits))


class JsonpathHighlighter(QtGui.QSyntaxHighlighter):
    """
    Highlighter for jsonpathfx syntax.
    """

    @staticmethod
    def _kind_map() -> dict[Kind, Style]:
        from jsonpathfx import Kind

        return {
            Kind.root: Style.keyword,
            Kind.this: Style.keyword,
            Kind.desc: Style.keyword,
            Kind.child: Style.keyword,
            Kind.star: Style.keyword,
            Kind.or_: Style.keyword,
            Kind.and_: Style.keyword,
            Kind.merge: Style.keyword,
            Kind.intersect: Style.keyword,
            Kind.open_brace: Style.extra,
            Kind.close_brace: Style.extra,
            Kind.true: Style.number,
            Kind.false: Style.number,
            Kind.call: Style.func,
            Kind.number: Style.number,
            Kind.bind: Style.var,
            Kind.name: Style.string,
            Kind.string: Style.string,
            Kind.plus: Style.keyword,
            Kind.minus: Style.keyword,
            Kind.divide: Style.keyword,
            Kind.less_than_eq: Style.keyword,
            Kind.less_than: Style.keyword,
            Kind.equals: Style.keyword,
            Kind.greater_than_eq: Style.keyword,
            Kind.greater_than: Style.keyword,
            Kind.not_eq: Style.keyword,
            Kind.regex: Style.keyword,
            Kind.bang: Style.keyword,
            Kind.comment: Style.comment,
        }

    def highlightBlock(self, text: str) -> None:
        from jsonpathfx import lex

        kind_map = self._kind_map()
        tokens = lex(text)
        prev_pos = -1
        prev_style: Optional[Style] = None
        for token in tokens:
            pos = token.pos
            if prev_style:
                self.setFormat(prev_pos, pos, styleColor(prev_style))
            prev_pos = pos
            prev_style = kind_map.get(token.kind)
        if prev_style is not None:
            self.setFormat(prev_pos, len(text), styleColor(prev_style))

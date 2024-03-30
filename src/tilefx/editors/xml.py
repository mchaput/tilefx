from __future__ import annotations
import enum
import re
from typing import Iterable, Optional, Tuple

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt

from .syntax import HighlighterBase, Style, number_expr


class XmlState(enum.Enum):
    text = enum.auto()
    cdata = enum.auto()
    start_tag = enum.auto()
    end_tag = enum.auto()
    attr = enum.auto()
    attr_value = enum.auto()
    decl = enum.auto()
    sq_attr = enum.auto()
    dq_attr = enum.auto()


identifier_expr = re.compile(r"\w(\w|-)*", re.UNICODE)
tag_open_expr = re.compile(r"<[/?]?\w(\w|-)*", re.UNICODE)
entity_expr = re.compile(r"&([^;]+);")


def _badCloseTag(line: str, pos: int, state: XmlState, in_pi: bool) -> bool:
    if line.startswith("/>", pos) or line[pos] == ">":
        return in_pi or state in (XmlState.attr, XmlState.attr_value)
    return False


class XmlHighlighter(HighlighterBase):
    def highlightBlock(self, line: str) -> None:
        if not line:
            return

        state_int = self.previousBlockState()
        in_pi = bool(state_int & 0b10000)
        if state_int <= 0:
            state = XmlState.text
        else:
            state = XmlState(state_int & 0b1111)
        pos = 0
        while pos < len(line):
            start = pos
            char = line[pos]
            pos += 1
            style = Style.plain
            if _badCloseTag(line, start, state, in_pi):
                style = Style.error if in_pi else Style.type
                state = XmlState.text
                in_pi = False
                if char == "/":
                    pos += 1
            elif state == XmlState.text:
                if line.startswith("<![CDATA[", start):
                    style = Style.type
                    state = XmlState.cdata
                    pos = start + 9
                elif line.startswith("<!"):
                    style = Style.type
                    state = XmlState.decl
                    pos = start + 2
                elif m := tag_open_expr.match(line, start):
                    style = Style.type
                    if line.startswith("</", start):
                        state = XmlState.end_tag
                    else:
                        state = XmlState.start_tag
                        in_pi = line.startswith("<?", start)
                    pos = m.end()
                elif line.startswith("</"):
                    style = Style.type
                    state = XmlState.end_tag
                    pos = start + 2
                elif m := entity_expr.match(line, start):
                    style = Style.quote
                    pos = m.end()
                elif char in "&<":
                    style = Style.error
                else:
                    while pos < len(line) and line[pos] not in "&<":
                        pos += 1
            elif state == XmlState.cdata:
                if line.startswith("]]>", start):
                    style = Style.type
                    state = XmlState.text
                    pos = start + 3
                else:
                    while pos < len(line) and not line.startswith("]]>", pos):
                        pos +=1
            elif state == XmlState.start_tag:
                if line.startswith("?>", start):
                    if in_pi:
                        style = Style.type
                    else:
                        style = Style.error
                    state = XmlState.text
                    pos = start + 2
                elif char == ">":
                    style = Style.type
                    state = XmlState.text
                elif m := identifier_expr.match(line, start):
                    style = Style.keyword
                    state = XmlState.attr
                    pos = m.end()
            elif state == XmlState.attr:
                if char.isspace() or char == ">":
                    style = Style.error if in_pi else Style.type
                    state = XmlState.text
                elif char == "=":
                    style = Style.extra
                    state = XmlState.attr_value
                else:
                    style = Style.error
                    state = XmlState.start_tag
            elif state == XmlState.attr_value:
                if char == "'":
                    style = Style.string
                    state = XmlState.sq_attr
                elif char == '"':
                    style = Style.string
                    state = XmlState.dq_attr
                elif char.isspace():
                    pass
                elif char == ">":
                    style = Style.error
                    state = XmlState.text
                else:
                    if m := identifier_expr.match(line, start):
                        style = Style.var
                        pos = m.end()
                    else:
                        style = Style.error
                        pos += 1
                    state = XmlState.start_tag
            elif state == XmlState.end_tag:
                if char.isspace():
                    pass
                else:
                    style = Style.type if char == ">" else Style.error
                    state = XmlState.text
            elif state == XmlState.decl:
                if char == ">":
                    style = Style.type
                    state = XmlState.text
                else:
                    while pos < len(line) and line[pos] != ">":
                        pos += 1
            elif state == XmlState.sq_attr or state == XmlState.dq_attr:
                ec = "'" if state == XmlState.sq_attr else '"'
                cs = ec + "&"
                style = Style.string
                if char == ec:
                    state = XmlState.start_tag
                elif m := entity_expr.match(line, start):
                    style = Style.quote
                    pos = m.end()
                else:
                    while pos < len(line) and line[pos] not in cs:
                        pos += 1

            self.setFormat(start, pos, self.styleColor(style))
            if in_pi and state != XmlState.start_tag:
                in_pi = False

        state_int = state.value
        if in_pi:
            state_int |= 0b10000

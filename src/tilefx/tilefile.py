from __future__ import annotations
import ast
import enum
import re
from types import CodeType
from typing import Any, Collection, NamedTuple, Optional, Union

import jsonpathfx


class ParserError(Exception):
    def __init__(self, msg: str, text: str, pos: int):
        at = coords(text, pos)
        near = text[pos:pos + 5]
        super().__init__(f"{msg} at {at}: {near!r}")


def coords(text: str, pos: int) -> str:
    line = 1
    col = pos
    nl = text.rfind("\n", 0, pos)
    while nl >= 0:
        start = nl
        if line == 1:
            col = pos - nl
        line += 1
        nl = text.rfind("\n", 0, nl)
        if not nl < start:
            raise Exception("coords did not move backward at", nl)
    return f"line {line} col {col + 1}"


bare_name_expr = re.compile(r"\s*([^\\'\"{}\[\],]+)")
line_comment_expr = re.compile(r"#[^\r\n]*")
# block_comment_expr = re.compile(r"/[*].*[*]/", re.DOTALL)
number_expr = re.compile(r"(-?\d+([.]\d*(e\d+)?)?)|([.]\d+([eE]\d*)?)")
sep_expr = re.compile(r"[ \t]*,?[ \t]*(\r\n|\r|\n)")
bs_x_expr = re.compile(r"\\x([a-fA-F0-9]{2})")
bs_u_expr = re.compile(r"\\u([a-fA-F0-9]{4})")
eq_expr = re.compile("[ \t]*=[ \t]*")
to_line_end_expr = re.compile(r"([^\r\n]+)(\r\n|\r|\n)")

symbols: dict[str, Any] = {
    "true": True,
    "false": False,
    "null": None
}
symbol_expr = re.compile(rf"\s*({'|'.join(symbols)})\s*")

escapable_chars: dict[str, str] = {
    '"': '"',
    "'": "'",
    "\\": "\\",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t"
}
brackets = {"(": ")", "[": "]", "{": "}"}
endbrackets = frozenset(brackets.values())


class Entity:
    pass


class GraphicItem(Entity):
    def __init__(self, type_name: str, params: dict[str, Any]):
        self.type_name = type_name
        self.params = params

    @classmethod
    def parse(cls, text: str, pos: int) -> tuple[GraphicItem, int]:
        name, pos = lex_bare_name(text, pos)
        params, pos = parse_dict(text, pos)
        return GraphicItem(name, params), pos


class PythonExpression(Entity):
    def __init__(self, source: str):
        self.source = source

    @classmethod
    def parse(cls, text: str, pos: int) -> tuple[PythonExpression, int]:
        source, pos = parse_expression(text, pos)
        try:
            code = compile(source, source, "eval")
        except Exception as e:
            raise ParserError(f"Error compiling expression {e}", text, pos)
        return PythonExpression(source), pos


class JsonPathExpression(Entity):
    def __init__(self, source: str, path: jsonpathfx.JsonPath = None):
        self.source = source
        if path is None:
            path = jsonpathfx.parse(source)
        self.path = path

    @classmethod
    def parse(cls, text: str, pos: int) -> tuple[JsonPathExpression, int]:
        source, pos = parse_expression(text, pos)
        path = jsonpathfx.parse(source)
        return JsonPathExpression(source), pos


class VariableAssignment(Entity):
    def __init__(self, name: str, source: str):
        self.name = name
        self.source = source

    @classmethod
    def parse(cls, text: str, pos: int) -> tuple[VariableAssignment, int]:
        name, pos = lex_bare_name(text, pos)
        if m := eq_expr.match(text, pos):
            pos = m.end()
        else:
            raise ParserError("Expected =", text, pos)
        source, pos = parse_expression(text, pos)
        try:
            code = compile(source, source, "eval")
        except Exception as e:
            raise ParserError(f"Error compiling expression {e}", text, pos)
        return VariableAssignment(name, source), pos


entity_parsers = {
    "let": VariableAssignment.parse,
    "path": JsonPathExpression.parse,
    "expr": PythonExpression.parse,
    "item": GraphicItem.parse,
    "template": GraphicItem.parse,
}
item_expr = re.compile("(\w+)\s*(?=[{])")
entity_names_pattern = '|'.join(entity_parsers)
entity_keyword_expr = re.compile(rf"\s*({entity_names_pattern})\s+")


def lex_string_literal(text: str, pos: int, allow_multiline_strings=True
                       ) -> tuple[str, int]:
    multiline = False
    if text.startswith('"""', pos):
        multiline = True
        close = '"""'
        pos += 3
    elif text.startswith("'''", pos):
        multiline = True
        close = "'''"
        pos += 3
    elif text[pos] == '"':
        close = '"'
        pos += 1
    elif text[pos] == "'":
        close = "'"
        pos += 1
    else:
        raise Exception(f"No quote at {pos}")

    if multiline and not allow_multiline_strings:
        raise ParserError(f"Unexprected {close}", text, pos)

    prev = pos
    chunks: list[str] = []
    while pos < len(text):
        char = text[pos]
        if char in "\r\n" and not multiline:
            raise ParserError(f"Unclosed string", text, pos)

        if text.startswith(close, pos):
            if prev < pos:
                chunks.append(text[prev:pos])
            return "".join(chunks), pos + 1
        elif m := (bs_x_expr.match(text, pos) or bs_u_expr.match(text, pos)):
            if prev < pos:
                chunks.append(text[prev:pos])
            code = int(m.group(1), 16)
            chunks.append(chr(code))
            pos = m.end()
            prev = pos
        elif char == "\\" and pos < len(text) - 1:
            if prev < pos:
                chunks.append(text[prev:pos])
            escaped = text[pos + 1]
            if escaped in escapable_chars:
                chunks.append(escapable_chars[escaped])
                pos += 2
                prev = pos
            else:
                raise ParserError(f"Unknown escape char {escaped}", text, pos)
        else:
            pos += 1

    raise ParserError(f"Unclosed string", text, pos)


def lex_bare_name(text: str, pos: int) -> tuple[str, int]:
    if m := bare_name_expr.match(text, pos):
        name = m.group(1)
        pos = m.end()
    else:
        raise ParserError("Expected name", text, pos)
    return name, pos


def lex_quoteless_string(text: str, pos: int) -> tuple[str, int]:
    if m := to_line_end_expr.match(text, pos):
        return m.group(1), m.end()
    else:
        raise ParserError(f"Expected string", text, pos)


def parse_expression(text: str, pos: int, ends: Collection[str] = "\r\n",
                     allow_multiline_strings=True) -> tuple[str, int]:
    start = pos
    stack: list[tuple[str, pos]] = []
    length = len(text)
    while pos < length:
        char = text[pos]
        if char in ends and not stack:
            break

        if char in brackets:
            # If the char is an open bracket, add it to the stack
            stack.append((brackets[char], pos))
            pos += 1
        elif stack and char == stack[-1][0]:
            # If it's the close bracket we're looking for, pop the stack
            stack.pop()
            pos += 1
        elif char in endbrackets:
            # If it's a close bracket we're NOT looking for
            raise ParserError(f"Unexpected {char}", text, pos)
        elif m := line_comment_expr.match(text, pos):
            pos = m.end()
        elif char in "\"'":
            # If we're starting a string, loop through chars until we find
            # the end quote
            _, pos = lex_string_literal(
                text, pos, allow_multiline_strings=allow_multiline_strings
            )
        else:
            # Move to the next char
            pos += 1

    source = text[start:pos].strip()
    if stack:
        ochar, opos = stack[-1]
        raise ParserError(f"Unmatched {ochar}", text, opos)
    if not source:
        raise ParserError("Empty Python expression", text, start)

    return source, pos


def skip_ws(text: str, pos: int, err="Unexpected EOF", allow_eof=False,
            skip_newlines=True) -> int:
    while pos < len(text):
        char = text[pos]
        if char in "\r\n" and not skip_newlines:
            return pos

        if char.isspace():
            pos += 1
        elif m := line_comment_expr.match(text, pos):
            pos = m.end()
        # elif m := block_comment_expr.match(text, pos):
        #     pos = m.end()
        else:
            return pos

    if allow_eof:
        return pos
    else:
        raise ParserError(err, text, pos)


def parse_sep(text, pos, end_before: str, allow_eof=False) -> int:
    if m := sep_expr.match(text, pos):
        return m.end()
    else:
        pos = skip_ws(text, pos, err=f"Expected , but found EOF at {pos}")
        char = text[pos]
        if char == ",":
            return pos + 1
        elif char == end_before:
            return pos
        else:
            raise ParserError(f"Expected comma", text, pos)


def parse_dict(text: str, pos: int
               ) -> tuple[dict[str, jsonpathfx.JsonValue], int]:
    if not text.startswith("{", pos):
        raise ParserError(f"Expected open brace", text, pos)
    pos = skip_ws(text, pos + 1)

    result: dict[str, jsonpathfx.JsonValue] = {}
    while pos < len(text):
        start = pos
        pos = skip_ws(text, pos)

        char = text[pos]
        if char == "}":
            return result, pos + 1
        elif char in "'\"":
            key, pos = lex_string_literal(text, pos)
        elif m := bare_name_expr.match(text, pos):
            key = m.group(1)
            pos = m.end()
        else:
            raise ParserError("Expected key", text, pos)

        pos = skip_ws(text, pos, err="Expected : but found EOF")
        char = text[pos]
        if char == ":":
            pos = skip_ws(text, pos + 1,
                          err=f"Expected value but found EOF")
        else:
            raise ParserError(f"Expected : but found {char!r}", text, pos)

        value, pos = parse_value(text, pos)
        result[key] = value

        print("key=", repr(key), "value=", repr(value), "pos=", pos)
        pos = parse_sep(text, pos, "}")

        if pos <= start:
            raise Exception("Dict parser did not move forward", text, pos)

    raise ParserError(f"Expected close brace", text, pos)


def parse_array(text: str, pos: int
                ) -> tuple[list[jsonpathfx.JsonValue], int]:
    if not text.startswith("[", pos):
        raise ParserError(f"Expected [", text, pos)
    pos = skip_ws(text, pos + 1)

    result: list[jsonpathfx.JsonValue] = []
    while pos < len(text):
        start = pos
        char = text[pos]
        if char == "]":
            return result, skip_ws(text, pos + 1)

        value, pos = parse_value(text, pos)
        result.append(value)

        pos = parse_sep(text, pos, "]")

        if pos <= start:
            raise Exception("Array parser did not move forward")

    raise ParserError(f"Expected ]", text, pos)


def parse_entity(text: str, pos: int
                 ) -> tuple[Union[Entity, jsonpathfx.JsonValue], int]:
    pos = skip_ws(text, pos)
    if m := entity_keyword_expr.match(text, pos):
        keyword = m.group(1)
        parser = entity_parsers[keyword]
        return parser(text, pos)
    elif m := item_expr.match(text, pos):
        name = m.group(1)
        params, pos = parse_dict(text, m.end())
        return GraphicItem(name, params), pos
    else:
        return parse_value(text, pos)


def parse_value(text: str, pos: int) -> tuple[jsonpathfx.JsonValue, int]:
    pos = skip_ws(text, pos)
    if text[pos] == "{":
        return parse_dict(text, pos)
    elif text[pos] in "'\"":
        return lex_string_literal(text, pos)
    elif m := symbol_expr.match(text, pos):
        return symbols[m.group(1)], m.end()
    elif m := number_expr.match(text, pos):
        return ast.literal_eval(m.group(0)), m.end()
    else:
        raise ParserError(f"Excpected JSON value", text, pos)


def parse(text: str, pos=0) -> Union[Entity, jsonpathfx.JsonValue]:
    entity, pos = parse_entity(text, pos)
    if pos < len(text):
        pos = skip_ws(text, pos, allow_eof=True)
    if pos < len(text):
        char = text[pos]
        raise ParserError(f"Unexpected {char!r}", text, pos)
    return entity

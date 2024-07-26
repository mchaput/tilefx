from __future__ import annotations

import ast
import dataclasses
import enum
import re
import textwrap
from types import CodeType
from typing import Any, Collection, Iterable, NamedTuple, NewType, Optional

import jsonpathfx


BLOCK_EXPR_START = "```"
BLOCK_EXPR_END = "```"
LINE_EXPR_START = "`"
LINE_EXPR_END = "`"
ASSIGN_KEYWORD = "let"
OBJECT_KEYWORD = "obj"
TEMPLATE_KEYWORD = "template"
MODEL_KEYWORD = "model"


class ErrType(enum.Enum):
    syntax = enum.auto()
    bracket = enum.auto()
    string = enum.auto()
    expr = enum.auto()
    dict_key = enum.auto()
    type_name = enum.auto()
    obj_name = enum.auto()
    obj_open_brace = enum.auto()


class ParserError(Exception):
    def __init__(self, err_type: ErrType, msg: str, text: str, start=-1, end=-1,
                 fragment: str = None, token: Token = None):
        if not isinstance(err_type, ErrType):
            raise TypeError(err_type)
        if token is not None:
            start = token.start
            end = token.end
            fragment = text[max(0, start - 5):min(len(text), end + 10)]

        err_msg = f"{msg} at {coords(text, start)}"
        if fragment:
            err_msg = f"{err_msg}: {fragment!r}"
        super().__init__(err_msg)
        self.err_type = err_type
        self.start = start
        self.end = end


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


comment_expr = re.compile(r"#([^\r\n]+)(\r\n|\r|\n)")
name_expr = re.compile(r"(\w|[.])+")
line_comment_expr = re.compile(r"#[^\r\n]*")
number_expr = re.compile(r"(-?\d+([.]\d*(e\d+)?)?)|([.]\d+([eE]\d*)?)")
sep_expr = re.compile(r"[ \t]*,?[ \t]*(\r\n|\r|\n)")
bs_x_expr = re.compile(r"\\x([a-fA-F0-9]{2})")
bs_u_expr = re.compile(r"\\u([a-fA-F0-9]{4})")
eq_expr = re.compile("[ \t]*=[ \t]*")
newline_expr = re.compile(r"[\r\n]+")
h_space_expr = re.compile(r"[ \t]+")
to_line_end_expr = re.compile(r"([^\r\n]+)(\r\n|\r|\n)")
env_var_expr = re.compile(
    r"[$]([A-Za-z_][A-Za-z0-9_]+)"
)

literals: dict[str, Any] = {
    "true": True,
    "True": True,
    "false": False,
    "False": False,
    "null": None,
    "None": None,
}
literal_expr = re.compile('|'.join(literals))

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

ComputedKey = NewType("ComputedKey", str)


class AstNode:
    start = -1
    end = -1

    def dynamic(self) -> bool:
        return False


@dataclasses.dataclass
class ModuleNode(AstNode):
    value: list[AstNode]

    @property
    def start(self) -> int:
        return self.value[0].start if self.value else -1

    @property
    def end(self) -> int:
        return self.value[-1].end if self.value else -1


@dataclasses.dataclass
class PythonExpr(AstNode):
    source: str
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)

    def dynamic(self) -> bool:
        return True


@dataclasses.dataclass
class PythonBlock(AstNode):
    source: str
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)

    def dynamic(self) -> bool:
        return True


@dataclasses.dataclass
class StaticPythonExpr(AstNode):
    source: str
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)


@dataclasses.dataclass
class JsonpathNode(AstNode):
    source: str
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)

    def dynamic(self) -> bool:
        return True


@dataclasses.dataclass
class Literal(AstNode):
    value: int|float|str|dict|list|tuple|None
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)


@dataclasses.dataclass
class DictNode(AstNode):
    value: dict[str | ComputedKey, AstNode]
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)


@dataclasses.dataclass
class ListNode(AstNode):
    value: list[AstNode]
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)


@dataclasses.dataclass
class ObjectNode(AstNode):
    type_name: str
    name: Optional[str]
    params: dict[str, AstNode]
    items: list = dataclasses.field(default_factory=list)
    is_template: bool = False
    on_update: Optional[PythonBlock] = None
    type_name_start: int = dataclasses.field(default=-1, compare=False)
    obj_name_start: int = dataclasses.field(default=-1, compare=False)
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)


@dataclasses.dataclass
class ModelNode(AstNode):
    name: Optional[str]
    params: dict[str, AstNode]
    on_update: Optional[PythonBlock] = None
    obj_name_start: int = dataclasses.field(default=-1, compare=False)
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)


@dataclasses.dataclass
class EnvVarNode(AstNode):
    value: str
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)


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
        raise ParserError(ErrType.bracket, f"Unexprected {close}",
                          text, pos)

    prev = pos
    chunks: list[str] = []
    while pos < len(text):
        char = text[pos]
        if char in "\r\n" and not multiline:
            raise ParserError(ErrType.string, f"Unclosed string",
                              text, pos)

        if text.startswith(close, pos):
            if prev < pos:
                chunks.append(text[prev:pos])
            return "".join(chunks), pos + len(close)
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
                raise ParserError(ErrType.string,
                                  f"Unknown escape char {escaped}", text, pos)
        else:
            pos += 1

    raise ParserError(ErrType.string, f"Unclosed string", text, pos)


# def lex_quoteless_string(text: str, pos: int) -> tuple[str, int]:
#     if m := to_line_end_expr.match(text, pos):
#         return m.group(1), m.end()
#     else:
#         raise ParserError(f"Expected string", text, pos)


def parse_expression(text: str, pos: int,
                     end_chars: Collection[str] = "\r\n",
                     newline_is_error=False, allow_multiline_strings=True
                     ) -> tuple[str, int]:
    start = pos
    stack: list[tuple[str, pos]] = []
    length = len(text)
    while pos < length:
        char = text[pos]
        if char in end_chars and not stack:
            break
        if char in "\r\n" and not stack and newline_is_error:
            raise ParserError(ErrType.expr,"Unexpected line end", text, pos)

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
            raise ParserError(ErrType.expr, f"Unexpected {char}", text, pos)
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
        raise ParserError(ErrType.bracket, f"Unmatched {ochar}", text, opos)
    if not source:
        raise ParserError(ErrType.expr, "Empty Python expression", text, start)

    return source, pos


def parse_line_expr(text: str, pos: int) -> tuple[str, int]:
    expr_str, end_pos = parse_expression(text, pos, end_chars="\r\n`",
                                         newline_is_error=True,
                                         allow_multiline_strings=False)
    if end_pos < len(text) and text[end_pos] == "`":
        return expr_str, end_pos + 1
    else:
        raise ParserError(ErrType.bracket, "Unclosed expr", text, pos)


def lex_to_end_string(text: str, pos: int, end_str: str) -> tuple[str, int]:
    end_pos = text.find(end_str, pos)
    if end_pos <= pos:
        raise ParserError(ErrType.bracket, "Unclosed expr", text, pos)
    return text[pos:end_pos], end_pos + len(end_str)


# Pratt parser based on this extremely helpful and easy-to-read article:
# https://journal.stuffwithstuff.com/2011/03/19/pratt-parsers-expression-parsing-made-easy/
#
# In the class names below "prefix" means "prefix or standalone" and
# "infix" means "not prefix" (includes postfix and "mixfix" (e.g. ?:))

class Kind(enum.Enum):
    eof = enum.auto()
    newline = enum.auto()
    string = enum.auto()
    number = enum.auto()
    literal = enum.auto()
    line_expr = enum.auto()
    block_expr = enum.auto()
    value_expr = enum.auto()
    env_var = enum.auto()
    comma = enum.auto()
    colon = enum.auto()
    open_brace = enum.auto()
    close_brace = enum.auto()
    open_paren = enum.auto()
    close_paren = enum.auto()
    open_square = enum.auto()
    close_square = enum.auto()
    jsonpath = enum.auto()
    keyword = enum.auto()
    name = enum.auto()

    object = enum.auto()
    template = enum.auto()
    model = enum.auto()
    assign = enum.auto()


class Token(NamedTuple):
    kind: Kind
    payload: Any
    start: int
    end: int


kw_to_obj_kind: dict[str, Kind] = {
    OBJECT_KEYWORD: Kind.object,
    TEMPLATE_KEYWORD: Kind.template,
    MODEL_KEYWORD: Kind.model,
    ASSIGN_KEYWORD: Kind.assign,
}
kw_expr = re.compile(rf"({'|'.join(kw_to_obj_kind)})\s+")


def lex(text: str, pos=0) -> Iterable[Token]:
    dict_depth = 0
    prev_kind: Optional[Kind] = None
    while pos < len(text):
        start = pos
        char = text[pos]
        if m := h_space_expr.match(text, pos):
            pos = m.end()
            continue
        elif m := comment_expr.match(text, pos):
            pos = m.end()
            continue
        elif m := newline_expr.match(text, pos):
            out = Token(Kind.newline, "\n", pos, m.end())
            pos = m.end()
        elif text.startswith(BLOCK_EXPR_START, pos):
            block, end_pos = lex_to_end_string(text, pos + len(BLOCK_EXPR_START),
                                               BLOCK_EXPR_END)
            out = Token(Kind.block_expr, block, pos, end_pos)
            pos = end_pos
        elif text.startswith(LINE_EXPR_START, pos):
            line, end_pos = parse_line_expr(text, pos + len(LINE_EXPR_START))
            out = Token(Kind.line_expr, line, pos, end_pos)
            pos = end_pos
        elif char in "'\"":
            string, end_pos = lex_string_literal(text, pos)
            out = Token(Kind.string, string, pos, end_pos)
            pos = end_pos
        elif m := number_expr.match(text, pos):
            num_str = m.group(0)
            if "." in num_str:
                value = float(num_str)
            else:
                value = int(num_str)
            out = Token(Kind.literal, value, pos, m.end())
            pos = m.end()
        elif m := literal_expr.match(text, pos):
            out = Token(Kind.literal, literals[m.group(0)], pos, m.end())
            pos = m.end()
        elif m := kw_expr.match(text, pos):
            out = Token(kw_to_obj_kind[m.group(1)], m.group(1), pos, m.end())
            pos = m.end()
        elif char == ",":
            out = Token(Kind.comma, ",", pos, pos + 1)
            pos += 1
        elif char == ":":
            out = Token(Kind.colon, ":", pos, pos + 1)
            pos += 1
        elif m := env_var_expr.match(text, pos):
            out = Token(Kind.env_var, m.group(1), pos, m.end())
            pos = m.end()
        elif char in "$@":
            path, end_pos = parse_expression(text, pos)
            out = Token(Kind.jsonpath, path, pos, pos + 1)
            pos = end_pos
        elif char == "{":
            out = Token(Kind.open_brace, "{", pos, pos + 1)
            dict_depth += 1
            pos += 1
        elif char == "}":
            out = Token(Kind.close_brace, "}", pos, pos + 1)
            dict_depth -= 1
            pos += 1
        elif char == "[":
            out = Token(Kind.open_square, "[", pos, pos + 1)
            pos += 1
        elif char == "]":
            out = Token(Kind.close_square, "]", pos, pos + 1)
            pos += 1
        elif char == "(":
            expr, end_pos = parse_expression(
                text, pos + 1, end_chars=")", newline_is_error=False
            )
            out = Token(Kind.value_expr, expr, pos + 1, end_pos)
            pos = end_pos + 1
        elif dict_depth and prev_kind == Kind.colon:
            expr, end_pos = parse_expression(text, pos, end_chars="\r\n,")
            out = Token(Kind.value_expr, expr, pos, end_pos)
            pos = end_pos
        elif m := name_expr.match(text, pos):
            out = Token(Kind.name, m.group(0), pos, m.end())
            pos = m.end()
        else:
            raise ParserError(ErrType.syntax, "Syntax error: {char}",
                              text, pos)

        yield out
        prev_kind = out.kind

        if pos <= start:
            raise Exception(f"Pos error {start} -> {pos}")


class Parselet:
    def parse_prefix(self, parser: Parser, token: Token) -> AstNode:
        raise NotImplementedError

    def parse_infix(self, parser: Parser, left: AstNode, token: Token
                    ) -> AstNode:
        raise NotImplementedError

    def precedence(self) -> int:
        raise NotImplementedError


class DictParselet(Parselet):
    def parse_prefix(self, parser: Parser, open_token: Token) -> AstNode:
        d: dict[str, AstNode] = {}
        parser.skip_any(Kind.newline)
        token = parser.consume()
        first = True
        while token.kind != Kind.eof:
            if token.kind == Kind.close_brace:
                return DictNode(d, start=open_token.end, end=token.start)

            if not first:
                if token.kind == Kind.comma or token.kind == Kind.newline:
                    parser.skip_any(Kind.newline)
                    token = parser.consume()
                else:
                    raise parser.expected(ErrType.syntax, "comma or newline",
                                          token)
            first = False

            if token.kind == Kind.close_brace:
                return DictNode(d, start=open_token.end, end=token.start)
            elif token.kind in (Kind.name, Kind.string):
                key = token.payload
            elif token.kind == Kind.value_expr:
                key = ComputedKey(token.payload)
            else:
                raise parser.expected(ErrType.dict_key, "dictionary key", token)

            parser.consume(Kind.colon, ErrType.dict_key)
            parser.skip_any(Kind.newline)
            value = parser.expression()
            d[key] = value
            token = parser.consume()

        raise parser.err(ErrType.bracket, "Unclosed brace", open_token)


class ListParselet(Parselet):
    def parse_prefix(self, parser: Parser, open_token: Token) -> AstNode:

        ls: list[AstNode] = []
        first = True
        while parser.current().kind != Kind.eof:
            if close_token := parser.optional(Kind.close_square):
                return ListNode(ls, start=open_token.end, end=close_token.start)

            if not first:
                token = parser.consume()
                if token.kind == Kind.comma:
                    parser.skip_any(Kind.newline)
                else:
                    raise parser.err(ErrType.syntax, "Expected comma after list item",
                                     token)
            first = False

            if close_token := parser.optional(Kind.close_square):
                return ListNode(ls, start=open_token.end, end=close_token.start)
            else:
                ls.append(parser.expression())

        raise parser.err(ErrType.bracket, "Unclosed square bracket", open_token)


class ObjectParselet(Parselet):
    def parse_prefix(self, parser: Parser, kw_token: Token) -> ObjectNode:
        obj_kind = kw_token.kind
        params: dict[str, AstNode] = {}
        items: Optional[list[ObjectNode]] = []
        if obj_kind in (Kind.object, Kind.template):
            type_token = parser.consume(Kind.name, ErrType.type_name)
            type_name = type_token.payload
            out = ObjectNode(type_name, None, params, items,
                             is_template=obj_kind == Kind.template,
                             type_name_start=type_token.start)
        elif obj_kind == Kind.model:
            out = ModelNode(None, params)
        else:
            raise Exception(f"Unknown keyword {obj_kind} {kw_token.payload}")

        out.start = kw_token.start
        name_token = parser.optional(Kind.string)
        out.name = name_token.payload if name_token else None
        out.obj_name_start = name_token.start if name_token else -1

        parser.skip_any(Kind.newline)
        open_token = parser.consume(Kind.open_brace, ErrType.obj_open_brace)
        parser.skip_any(Kind.newline)
        token = parser.consume()
        first = True
        finished = False
        while token.kind != Kind.eof:
            if token.kind == Kind.close_brace:
                finished = True
                break

            if first and token.kind == Kind.block_expr:
                out.on_update = PythonBlock(
                    textwrap.dedent(token.payload).strip(),
                    start=token.start, end=token.end
                )
                parser.skip_any(Kind.newline)
                token = parser.consume()
                continue

            if not first:
                if token.kind == Kind.comma or token.kind == Kind.newline:
                    parser.skip_any(Kind.newline)
                else:
                    raise parser.expected(ErrType.syntax, "comma or newline",
                                          token)
                token = parser.consume()
            first = False

            if token.kind == Kind.close_brace:
                finished = True
                break

            elif token.kind in (Kind.object, Kind.template, Kind.model):
                items.append(self.parse_prefix(parser, token))
                token = parser.consume()
                continue

            elif token.kind in (Kind.name, Kind.string):
                key = token.payload
            else:
                raise parser.expected(ErrType.dict_key, "dictionary key", token)

            parser.consume(Kind.colon, ErrType.dict_key)
            val_node = parser.expression()
            if key == "items" and isinstance(val_node, ListNode):
                items.extend(v for v in val_node.value
                             if isinstance(v, (ObjectNode, ModelNode)))
            else:
                params[key] = val_node

            # Get the next token and loop
            token = parser.consume()

        if finished:
            out.end = token.start
            return out
        else:
            raise parser.err(ErrType.bracket, "Unclosed brace", open_token)


class LiteralParselet(Parselet):
    def parse_prefix(self, parser: Parser, token: Token) -> AstNode:
        return Literal(token.payload)


class ExprParselet(Parselet):
    def parse_prefix(self, parser: Parser, token: Token) -> AstNode:
        if token.kind == Kind.value_expr or token.kind == Kind.name:
            return StaticPythonExpr(token.payload)
        elif token.kind == Kind.env_var:
            return EnvVarNode(token.payload)
        else:
            source = textwrap.dedent(token.payload).strip()
            if token.kind == Kind.line_expr:
                return PythonExpr(source)
            else:
                return PythonBlock(source)


class JsonPathParselet(Parselet):
    def parse_prefix(self, parser: Parser, token: Token) -> AstNode:
        return JsonpathNode(token.payload)


prefixes: dict[Kind, Parselet] = {
    Kind.open_brace: DictParselet(),
    Kind.open_square: ListParselet(),
    Kind.object: ObjectParselet(),
    Kind.template: ObjectParselet(),
    Kind.model: ObjectParselet(),
    Kind.string: LiteralParselet(),
    Kind.number: LiteralParselet(),
    Kind.literal: LiteralParselet(),
    Kind.line_expr: ExprParselet(),
    Kind.block_expr: ExprParselet(),
    Kind.value_expr: ExprParselet(),
    Kind.env_var: ExprParselet(),
    Kind.jsonpath: JsonPathParselet(),
    Kind.name: ExprParselet(),
}
infixes: dict[Kind, Parselet] = {
    # No infix or suffix syntax currently
}


class Parser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = list(lex(text))
        # self.depth = 0

    def expected(self, err_type: ErrType, expectation: str, found: Token
                 ) -> Exception:
        return self.err(err_type, f"Expected {expectation}, "
                        f"found {found.kind.name} {found.payload!r}",
                        found)

    def err(self, err_type: ErrType, message: str, token: Token = None
            ) -> Exception:
        if token is None:
            token = self.current()
        return ParserError(err_type, message, self.text, token=token)

    def optional(self, kind: Kind) -> Optional[Token]:
        if not self.tokens:
            return None
        if self.tokens[0].kind == kind:
            return self.consume()

    def skip_any(self, kind: Kind) -> bool:
        skipped = False
        while self.tokens and self.tokens[0].kind == kind:
            self.tokens.pop(0)
            skipped = True
        return skipped

    def _eof_token(self) -> Token:
        return Token(Kind.eof, "<EOF>", len(self.text), len(self.text))

    def consume(self, kind: Kind = None, err_type=ErrType.syntax) -> Token:
        if self.tokens:
            token = self.tokens.pop(0)
        else:
            token = self._eof_token()

        if kind and token.kind != kind:
            raise self.expected(err_type, str(kind.name), token)
        return token

    def current(self) -> Token:
        return self.lookahead(0)

    def lookahead(self, distance: int) -> Optional[Token]:
        if distance >= len(self.tokens):
            return self._eof_token()
        return self.tokens[distance]

    def current_infix(self) -> Optional[Parselet]:
        return infixes.get(self.current().kind)

    def infix_precedence(self) -> int:
        infix = infixes.get(self.current().kind)
        if infix:
            return infix.precedence()
        return 0

    def expression(self, precedence=0, skip_newlines=True) -> AstNode:
        if skip_newlines:
            self.skip_any(Kind.newline)
        token = self.consume()
        prefix_parselet = prefixes.get(token.kind)
        if not prefix_parselet:
            raise self.err(ErrType.syntax,
                           f"Can't parse {token.kind.name} {token.payload!r}",
                           token)

        # self.depth += 1
        expr = prefix_parselet.parse_prefix(self, token)
        # self.depth -= 1

        while precedence < self.infix_precedence():
            token = self.consume()
            infix_parselet = infixes[token.kind]
            # self.depth += 1
            expr = infix_parselet.parse_infix(self, expr, token)
            # self.depth -= 1

        return expr

    def parse_module(self) -> ModuleNode:
        nodes: list[AstNode] = []
        while self.current().kind != Kind.eof:
            if self.skip_any(Kind.newline):
                continue
            nodes.append(self.expression())
        return ModuleNode(nodes)

    def parse(self) -> AstNode:
        node = self.parse_module()
        if isinstance(node, ModuleNode) and len(node.value) == 1:
            node = node.value[0]
        if self.tokens:
            tk = self.tokens[0]
            raise self.err(ErrType.syntax, f"Syntax error: {tk.payload}", tk)
        return node


def parse(text: str) -> AstNode:
    return Parser(text).parse()




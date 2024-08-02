from __future__ import annotations

import dataclasses
import enum
import re
import textwrap
from typing import (Any, Collection, Iterable, NamedTuple, NewType, Optional,
                    Sequence, TypeVar)


ASSIGN_EQ_OP = "="
DICT_ITEM_OP = ":"
BLOCK_EXPR_START = "```"
BLOCK_EXPR_END = "```"
LINE_EXPR_START = "`"
LINE_EXPR_END = "`"
LET_KEYWORD = "let"
VAR_KEYWORD = "var"
DYN_KEYWORD = "dyn"
OBJECT_KEYWORD = "def"
OVER_KEYWORD = "over"
STYLE_KEYWORD = "style"
TEMPLATE_KEYWORD = "template"
MODEL_KEYWORD = "model"
REF_KEYWORD = "reference"
FUNC_KEYWORD = "fn"
BEFORE_KEYWORD = "before"
AFTER_KEYWORD = "after"
INSERT_KEYWORD = "insert"


class ErrType(enum.Enum):
    system = enum.auto()
    syntax = enum.auto()
    bracket = enum.auto()
    string = enum.auto()
    expr = enum.auto()
    item = enum.auto()
    type_name = enum.auto()
    obj_name = enum.auto()
    obj_open_brace = enum.auto()
    obj_member = enum.auto()


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
number_expr = re.compile(r"""
(  # Hex integer
    0[xX][0-9a-fA-F]*
)  
|
(
    [+-]?  # Sign
    (
        (  # Digits -> decimal -> digits
            [0-9]+
            ([.][0-9]*)?
        )
        |  # or...
        (  # Decimal -> digitsl
            [.][0-9]+
        )
    )
    (  # ...optinally followed by exponent
        [eE][-+]?[0-9]+
    )?
)
    """,re.VERBOSE)
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


class Kind(enum.Enum):
    eof = enum.auto()
    newline = enum.auto()
    string = enum.auto()
    number = enum.auto()
    literal = enum.auto()
    line_expr = enum.auto()
    block_expr = enum.auto()
    env_var = enum.auto()
    comma = enum.auto()
    colon = enum.auto()
    assign_eq = enum.auto()
    open_brace = enum.auto()
    close_brace = enum.auto()
    open_paren = enum.auto()
    close_paren = enum.auto()
    open_square = enum.auto()
    close_square = enum.auto()
    jsonpath = enum.auto()
    keyword = enum.auto()
    name = enum.auto()
    value_expr = enum.auto()

    object = enum.auto()
    over = enum.auto()
    style = enum.auto()
    template = enum.auto()
    model = enum.auto()
    let = enum.auto()
    var = enum.auto()
    dyn = enum.auto()
    reference = enum.auto()
    func = enum.auto()

    before = enum.auto()
    after = enum.auto()
    insert = enum.auto()

class Namespace(dict):
    def __repr__(self):
        return f"<Namespace {super().__repr__()}>"

    def __getattr__(self, name: str) -> Any:
        return self[name]

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __or__(self, other):
        return Namespace(super().__or__(other))

    def copy(self) -> Namespace:
        return Namespace(super().copy())


class AstNode:
    start = -1
    end = -1

    def dynamic(self) -> bool:
        return False

    def assumes_name(self) -> bool:
        return False


@dataclasses.dataclass
class ModuleNode(AstNode):
    items: list[AstNode]
    name: Optional[str] = None
    styles: Namespace = dataclasses.field(default_factory=Namespace)

    @property
    def start(self) -> int:
        return self.items[0].start if self.items else -1

    @property
    def end(self) -> int:
        return self.items[-1].end if self.items else -1


@dataclasses.dataclass
class PythonAstNode(AstNode):
    source: str
    name: Optional[str] = dataclasses.field(default=None, compare=False)
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)

    def assumes_name(self) -> bool:
        return True


@dataclasses.dataclass
class PythonExpr(PythonAstNode):
    def dynamic(self) -> bool:
        return True


@dataclasses.dataclass
class PythonBlock(PythonAstNode):
    def dynamic(self) -> bool:
        return True


@dataclasses.dataclass
class JsonpathNode(PythonAstNode):
    source: str
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)

    def dynamic(self) -> bool:
        return True

    def assumes_name(self) -> bool:
        return True


@dataclasses.dataclass
class Literal(AstNode):
    value: int|float|str|dict|list|tuple|None
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)


@dataclasses.dataclass
class FuncNode(AstNode):
    expr: PythonAstNode
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)

    def dynamic(self) -> bool:
        return True


@dataclasses.dataclass
class RefNode(AstNode):
    ref: str
    items: list[AstNode] = dataclasses.field(default_factory=list)
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)


@dataclasses.dataclass
class DictNode(AstNode):
    values: dict[str | ComputedKey, AstNode]
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)


@dataclasses.dataclass
class ListNode(AstNode):
    values: list[AstNode]
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)


@dataclasses.dataclass
class ObjectNode(AstNode):
    type_name: str
    name: Optional[str]
    items: list[AstNode] = dataclasses.field(default_factory=list)
    is_template: bool = False
    options: dict[str, AstNode] = dataclasses.field(default_factory=dict)
    type_start: int = dataclasses.field(default=-1, compare=False)
    name_start: int = dataclasses.field(default=-1, compare=False)
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)

    def dynamic(self) -> bool:
        return any(it.dynamic() for it in self.items)


@dataclasses.dataclass
class InsertionNode(AstNode):
    kind: Kind
    arg: str | int
    obj: ObjectNode
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)


@dataclasses.dataclass
class SimpleObjectNode(AstNode):
    name: Optional[str]
    items: list[AstNode] = dataclasses.field(default_factory=list)
    options: dict[str, AstNode] = dataclasses.field(default_factory=dict)
    name_start: int = dataclasses.field(default=-1, compare=False)
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)


class OverNode(SimpleObjectNode):
    pass


class StyleNode(SimpleObjectNode):
    pass


class ModelNode(SimpleObjectNode):
    def dynamic(self) -> bool:
        return True


@dataclasses.dataclass
class EnvVarNode(AstNode):
    value: str
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)

    def dynamic(self) -> bool:
        return True


@dataclasses.dataclass
class Assign(AstNode):
    name: str
    value: PythonAstNode | Literal | DictNode | ListNode
    dyn: bool = True
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)

    def dynamic(self) -> bool:
        return self.dyn


@dataclasses.dataclass
class Prop(AstNode):
    name: str | ComputedKey
    value: AstNode
    dyn: bool = False
    start: int = dataclasses.field(default=-1, compare=False)
    end: int = dataclasses.field(default=-1, compare=False)

    def dynamic(self) -> bool:
        return self.dyn


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


def lex_expression(text: str, pos: int,
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
    expr_str, end_pos = lex_expression(text, pos, end_chars="\r\n`",
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

class Token(NamedTuple):
    kind: Kind
    payload: Any
    start: int
    end: int


kw_to_kind: dict[str, Kind] = {
    OBJECT_KEYWORD: Kind.object,
    OVER_KEYWORD: Kind.over,
    STYLE_KEYWORD: Kind.style,
    TEMPLATE_KEYWORD: Kind.template,
    MODEL_KEYWORD: Kind.model,
    LET_KEYWORD: Kind.let,
    VAR_KEYWORD: Kind.var,
    DYN_KEYWORD: Kind.dyn,
    REF_KEYWORD: Kind.reference,
    FUNC_KEYWORD: Kind.func,
    BEFORE_KEYWORD: Kind.before,
    AFTER_KEYWORD: Kind.after,
    INSERT_KEYWORD: Kind.insert,
}
kw_expr = re.compile(rf"({'|'.join(kw_to_kind)})\s+(?![:=])")

char_to_kind: dict[str, Kind] = {
    ",": Kind.comma,
    ASSIGN_EQ_OP: Kind.assign_eq,
}


def lex(text: str, pos=0) -> Iterable[Token]:
    bracket_stack: list[Token] = []
    allow_expr = False
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
            yield Token(Kind.newline, "\n", pos, m.end())
            pos = m.end()
        elif text.startswith(BLOCK_EXPR_START, pos):
            block, end_pos = lex_to_end_string(
                text, pos + len(BLOCK_EXPR_START), BLOCK_EXPR_END
            )
            yield Token(Kind.block_expr, block, pos, end_pos)
            pos = end_pos
        elif text.startswith(LINE_EXPR_START, pos):
            line, end_pos = parse_line_expr(text, pos + len(LINE_EXPR_START))
            yield Token(Kind.line_expr, line, pos, end_pos)
            pos = end_pos
        elif char in "'\"":
            string, end_pos = lex_string_literal(text, pos)
            yield Token(Kind.string, string, pos, end_pos)
            pos = end_pos
        elif m := number_expr.match(text, pos):
            num_str = m.group(0)
            if "." in num_str:
                value = float(num_str)
            else:
                value = int(num_str)
            yield Token(Kind.number, value, pos, m.end())
            pos = m.end()
        elif m := literal_expr.match(text, pos):
            yield Token(Kind.literal, literals[m.group(0)], pos, m.end())
            pos = m.end()
        elif m := kw_expr.match(text, pos):
            yield Token(kw_to_kind[m.group(1)], m.group(1), pos, m.end())
            pos = m.end()
        elif m := env_var_expr.match(text, pos):
            yield Token(Kind.env_var, m.group(1), pos, m.end())
            pos = m.end()
        elif char == DICT_ITEM_OP:
            yield Token(Kind.colon, char, pos, pos + 1)
            pos += 1
            if bracket_stack and bracket_stack[-1].kind == Kind.open_brace:
                allow_expr = True
                continue
        elif char in char_to_kind:
            yield Token(char_to_kind[char], char, pos, pos + 1)
            pos += 1
        elif char in "$@":
            path, end_pos = lex_expression(text, pos)
            yield Token(Kind.jsonpath, path, pos, pos + 1)
            pos = end_pos
        elif char == "{":
            out = Token(Kind.open_brace, char, pos, pos + 1)
            yield out
            bracket_stack.append(out)
            pos += 1
        elif char == "}":
            out = Token(Kind.close_brace, char, pos, pos + 1)
            yield out
            if bracket_stack and bracket_stack[-1].kind == Kind.open_brace:
                bracket_stack.pop()
            else:
                raise ParserError(ErrType.bracket, "Unmatched }", text,
                                  token=out)
            pos += 1
        elif char == "[":
            out = Token(Kind.open_square, char, pos, pos + 1)
            yield out
            bracket_stack.append(out)
            pos += 1
        elif char == "]":
            out = Token(Kind.close_square, char, pos, pos + 1)
            yield out
            if bracket_stack and bracket_stack[-1].kind == Kind.open_square:
                bracket_stack.pop()
            else:
                raise ParserError(ErrType.bracket, "Unmatched ]", text,
                                  token=out)
            pos += 1
        elif allow_expr:
            expr, end_pos = lex_expression(text, pos, end_chars="\r\n,}")
            yield Token(Kind.value_expr, expr, pos, end_pos)
            pos = end_pos
        elif char == "(":
            out = Token(Kind.open_paren, char, pos, pos + 1)
            yield out
            bracket_stack.append(out)
            pos += 1
        elif char == ")":
            out = Token(Kind.close_paren, char, pos, pos + 1)
            yield out
            if bracket_stack and bracket_stack[-1].kind == Kind.open_paren:
                bracket_stack.pop()
            else:
                raise ParserError(ErrType.bracket, "Unmatched )", text,
                                  token=out)
            pos += 1
        elif m := name_expr.match(text, pos):
            yield Token(Kind.name, m.group(0), pos, m.end())
            pos = m.end()
        else:
            raise ParserError(ErrType.syntax, f"Syntax error: {char}",
                              text, pos)
        allow_expr = False

        if pos <= start:
            raise Exception(f"Pos error {start} -> {pos}")

    if bracket_stack:
        token = bracket_stack[-1]
        raise ParserError(ErrType.bracket, f"Unclosed {token.payload}",
                          text, token=token)


class Parselet:
    def parse_prefix(self, parser: Parser, token: Token) -> AstNode:
        raise NotImplementedError

    def parse_infix(self, parser: Parser, left: AstNode, token: Token
                    ) -> AstNode:
        raise NotImplementedError

    def precedence(self) -> int:
        raise NotImplementedError


class ListParselet(Parselet):
    @classmethod
    def parse_prefix(cls, parser: Parser, open_token: Token) -> AstNode:

        ls: list[AstNode] = []
        first = True
        while parser.current().kind != Kind.eof:
            parser.skip_any(Kind.newline)
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


def skip_sep(parser: Parser, close_kind: Kind) -> None:
    cur_kind = parser.current().kind
    if cur_kind == close_kind:
        return

    if cur_kind == Kind.comma or cur_kind == Kind.newline:
        parser.optional(Kind.comma)
        parser.skip_any(Kind.newline)
    else:
        raise parser.expected(ErrType.syntax, "comma or newline",
                              parser.current())


def take_key(parser: Parser, op=Kind.colon) -> tuple[str | ComputedKey, int]:
    key_token = parser.consume()
    if key_token.kind in (Kind.name, Kind.string):
        key = key_token.payload
    elif key_token.kind == Kind.value_expr:
        key = ComputedKey(key_token.payload)
    else:
        raise parser.expected(ErrType.item, "dictionary key", key_token)
    parser.consume(op, ErrType.item)
    parser.skip_any(Kind.newline)
    return key, key_token.start


def take_object_options(parser: Parser) -> tuple[dict[str, AstNode], int]:
    parser.skip_any(Kind.newline)
    open_token = parser.consume(Kind.open_paren, ErrType.bracket)
    parser.skip_any(Kind.newline)
    options: dict[str, AstNode] = {}
    first = True
    while parser.current().kind != Kind.eof:
        if not first:
            skip_sep(parser, Kind.close_paren)
        first = False
        cur_kind = parser.current().kind
        if cur_kind == Kind.close_paren:
            close_token = parser.consume()
            return options, close_token.end
        elif cur_kind == Kind.name:
            key, key_start = take_key(parser, Kind.assign_eq)
            expr_token = parser.current()
            expr_node = parser.expression()
            if not isinstance(expr_node, (Literal, PythonExpr, JsonpathNode)):
                raise parser.err(ErrType.syntax, "Invalid option value",
                                 expr_token)
            options[key] = expr_node

    raise parser.err(ErrType.bracket, "Unclosed option list", open_token)


def take_object_params(parser: Parser, allowed_types: Sequence[type[AstNode]]
                       ) -> tuple[list[AstNode], int]:
    parser.skip_any(Kind.newline)
    open_token = parser.consume(Kind.open_brace, ErrType.obj_open_brace)
    parser.skip_any(Kind.newline)
    items: list[AstNode] = []
    first = True
    while parser.current().kind != Kind.eof:
        # if first:
        #     parser.skip_any(Kind.newline)
        #     if docstring_token := parser.optional(Kind.string):
        #         items.append(Prop("doc", Literal(docstring_token.payload)))
        #         parser.skip_any(Kind.newline)

        if not first:
            skip_sep(parser, Kind.close_brace)
        first = False

        cur_kind = parser.current().kind
        if cur_kind == Kind.close_brace:
            close_token = parser.consume()
            return items, close_token.end
        elif cur_kind == Kind.name or cur_kind == Kind.string:
            key, key_start = take_key(parser)
            expr_node = parser.expression()
            if expr_node.assumes_name():
                expr_node.name = key
            items.append(Prop(key, expr_node, start=key_start))
        else:
            start_token = parser.current()
            obj_node = parser.expression()
            if isinstance(obj_node, Prop) or type(obj_node) in allowed_types:
                items.append(obj_node)
            else:
                raise parser.err(ErrType.obj_member,
                                 f"Can't use {start_token.payload} here",
                                 start_token)

    raise parser.err(ErrType.bracket, "Unclosed parameters", open_token)


class DictParselet(Parselet):
    @classmethod
    def parse_prefix(cls, parser: Parser, open_token: Token) -> DictNode:
        values: dict[str | ComputedKey, AstNode] = {}
        parser.skip_any(Kind.newline)
        first = True
        while parser.current().kind != Kind.eof:
            if not first:
                skip_sep(parser, Kind.close_brace)
            first = False
            if close_token := parser.optional(Kind.close_brace):
                return DictNode(values, start=open_token.start,
                                end=close_token.end)

            key, _ = take_key(parser)
            values[key] = parser.expression()

        raise parser.err(ErrType.bracket, "Unclosed brace", open_token)


class ObjectParselet(DictParselet):
    @classmethod
    def parse_prefix(cls, parser: Parser, kw_token: Token
                     ) -> ObjectNode:
        is_template = kw_token.kind == Kind.template
        type_token = parser.consume(Kind.name, ErrType.type_name)
        obj = ObjectNode(type_token.payload, None, is_template=is_template,
                         type_start=type_token.start,
                         start=kw_token.start)
        if name_token := parser.optional(Kind.string):
            obj.name = name_token.payload
            obj.name_start = name_token.start

        if parser.current().kind == Kind.open_paren:
            obj.options, _ = take_object_options(parser)

        obj.items, obj.end = take_object_params(parser, (
            ObjectNode, ModelNode, StyleNode, Assign
        ))
        return obj


class OverParselet(Parselet):
    @classmethod
    def parse_prefix(cls, parser: Parser, kw_token: Token) -> OverNode:
        name_token = parser.consume(Kind.string)
        obj = OverNode(name_token.payload, name_start=name_token.start)

        if parser.current().kind == Kind.open_paren:
            obj.options, _ = take_object_options(parser)

        obj.items, obj.end = take_object_params(parser, (
            InsertionNode, ObjectNode, ModelNode, StyleNode, Assign
        ))
        return obj


class InsertionParselet(Parselet):
    @classmethod
    def parse_prefix(cls, parser: Parser, kw_token: Token) -> InsertionNode:
        kind = kw_token.kind
        if kind == Kind.before or kind == Kind.after:
            arg = parser.consume(Kind.string)
        elif kind == Kind.insert:
            arg = parser.consume(Kind.number)
        else:
            raise Exception("Unknown insertion kind")
        next_token = parser.current()
        obj = parser.expression()
        if not isinstance(obj, ObjectNode):
            raise parser.expected(ErrType.syntax, OBJECT_KEYWORD, next_token)
        return InsertionNode(kind, arg.payload, obj, start=kw_token.start,
                             end=obj.end)


class SimpleObjectParselet(Parselet):
    def __init__(self, cls: type[SimpleObjectNode], name_required=False):
        assert issubclass(cls, SimpleObjectNode)
        self._cls = cls
        self._name_required = name_required

    def parse_prefix(self, parser: Parser, kw_token: Token) -> AstNode:
        if self._name_required:
            name_token = parser.consume(Kind.string)
            name = name_token.payload
            name_start = name_token.start
        elif name_token := parser.optional(Kind.string):
            name = name_token.payload
            name_start = name_token.start
        else:
            name = None
            name_start = -1
        obj = self._cls(name, name_start=name_start, start=kw_token.start)

        if parser.current().kind == Kind.open_paren:
            obj.options, _ = take_object_options(parser)

        obj.items, obj.end = take_object_params(parser, (
            Assign,
        ))
        return obj


class LiteralParselet(Parselet):
    @classmethod
    def parse_prefix(cls, parser: Parser, token: Token) -> AstNode:
        return Literal(token.payload)


class EnvVarParselet(Parselet):
    @classmethod
    def parse_prefix(cls, parser: Parser, token: Token) -> EnvVarNode:
        return EnvVarNode(token.payload, start=token.start, end=token.end)


class ExprParselet(Parselet):
    @classmethod
    def parse_prefix(cls, parser: Parser, token: Token) -> PythonAstNode:
        if token.kind == Kind.name:
            return PythonExpr(token.payload)
        else:
            if token.kind == Kind.block_expr:
                source = textwrap.dedent(token.payload).strip()
                return PythonBlock(source)
            else:
                source = re.sub("\s+", " ", token.payload).strip()
                return PythonExpr(source)


class JsonPathParselet(Parselet):
    @classmethod
    def parse_prefix(cls, parser: Parser, token: Token) -> AstNode:
        return JsonpathNode(token.payload)


class AssignParselet(Parselet):
    @classmethod
    def parse_prefix(cls, parser: Parser, kw_token: Token) -> Assign:
        name_token = parser.consume(Kind.name)
        name = name_token.payload
        parser.consume(Kind.assign_eq, ErrType.item)
        parser.skip_any(Kind.newline)

        first_expr_token = parser.current()
        expr_node = parser.expression()
        if expr_node.assumes_name():
            expr_node.name = name
        if isinstance(expr_node, (PythonAstNode, Literal, DictNode, ListNode)):
            dynamic = kw_token.kind == Kind.var
            return Assign(name, expr_node, dyn=dynamic,
                          start=kw_token.start, end=expr_node.end)
        else:
            raise parser.expected(ErrType.syntax, "assignment value",
                                  first_expr_token)


class DynParselet(Parselet):
    @classmethod
    def parse_prefix(cls, parser: Parser, kw_token: Token) -> Prop:
        name_token = parser.consume(Kind.name)
        name = name_token.payload
        parser.consume(Kind.colon, ErrType.item)
        parser.skip_any(Kind.newline)

        first_expr_token = parser.current()
        expr_node = parser.expression()
        if expr_node.assumes_name():
            expr_node.name = name
        if isinstance(expr_node, PythonAstNode):
            return Prop(name, expr_node, dyn=True, start=kw_token.start,
                        end=expr_node.end)
        else:
            raise parser.expected(ErrType.syntax, "property expression",
                                  first_expr_token)


class FuncParselet(Parselet):
    @classmethod
    def parse_prefix(cls, parser: Parser, kw_token: Token) -> FuncNode:
        ex_token = parser.consume()
        if ex_token.kind in (Kind.line_expr, Kind.block_expr, Kind.value_expr):
            ex_node = ExprParselet.parse_prefix(parser, ex_token)
            return FuncNode(ex_node, start=kw_token.start, end=ex_node.end)
        else:
            raise parser.expected(ErrType.syntax, "Python block",
                                  ex_token)


class RefParselet(Parselet):
    @classmethod
    def parse_prefix(cls, parser: Parser, kw_token: Token) -> RefNode:
        ref_token = parser.consume(Kind.string)
        obj = RefNode(ref_token.payload)
        obj.items, obj.end = take_object_params(parser, (
            Assign, ObjectNode,
        ))
        return obj


prefixes: dict[Kind, Parselet] = {
    Kind.open_brace: DictParselet,
    Kind.open_square: ListParselet,
    Kind.object: ObjectParselet,
    Kind.template: ObjectParselet,
    Kind.over: OverParselet,
    Kind.model: SimpleObjectParselet(ModelNode),
    Kind.style: SimpleObjectParselet(StyleNode),
    Kind.string: LiteralParselet,
    Kind.number: LiteralParselet,
    Kind.literal: LiteralParselet,
    Kind.line_expr: ExprParselet,
    Kind.block_expr: ExprParselet,
    Kind.value_expr: ExprParselet,
    Kind.let: AssignParselet,
    Kind.var: AssignParselet,
    Kind.dyn: DynParselet,
    Kind.func: FuncParselet,
    Kind.env_var: EnvVarParselet,
    Kind.jsonpath: JsonPathParselet,
    Kind.name: ExprParselet,
    Kind.before: InsertionParselet,
    Kind.after: InsertionParselet,
    Kind.insert: InsertionParselet,
}
infixes: dict[Kind, Parselet] = {
    # No infix or suffix syntax currently
}


class Parser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = list(lex(text))
        # self.depth = 0

    def expected(self, err_type: ErrType, expected: str, found: Token
                 ) -> Exception:
        return self.err(err_type, f"Expected {expected}, "
                        f"found {found.kind}({found.payload!r})",
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
            raise Exception(f"No parser for {token.kind}")

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
        items: list[AstNode] = []
        while self.current().kind != Kind.eof:
            if self.skip_any(Kind.newline):
                continue
            items.append(self.expression())
        return ModuleNode(items)

    def parse(self) -> AstNode:
        node = self.parse_module()
        if self.tokens:
            tk = self.tokens[0]
            raise self.err(ErrType.syntax, f"Syntax error: {tk.payload}", tk)

        if len(node.items) == 1:
            return node.items[0]
        else:
            return node


def parse(text: str) -> AstNode:
    return Parser(text).parse()

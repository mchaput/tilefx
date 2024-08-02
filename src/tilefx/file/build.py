from __future__ import annotations
import dataclasses
import textwrap
import time
import struct
from base64 import b32encode
from typing import Any, Callable, Optional

import jsonpathfx

from tilefx.file import tilefile as tf


def source_lines(source: str, level=1) -> list[str]:
    source = textwrap.dedent(source)
    lines = tf.newline_expr.split(source)
    if level:
        lines = indentLines(lines, level)
    return lines


def indentLines(lines: list[str], level=1):
    if level:
        tab = "    " * level
        lines = [f"{tab}{line}" for line in lines]
    else:
        lines = list(lines)
    return lines


@dataclasses.dataclass
class BuildContext:
    path: tuple[tf.AstNode, ...] = ()
    warns: list[tuple[str, tf.AstNode]] = \
        dataclasses.field(default_factory=list)
    setup_names: dict[int, str] = dataclasses.field(default_factory=dict)
    update_names: dict[int, str] = dataclasses.field(default_factory=dict)
    value_names: dict[int, str] = dataclasses.field(default_factory=dict)

    def warn(self, msg: str, node: tf.AstNode) -> None:
        self.warns.append((msg, node))

    def push(self, node: tf.AstNode) -> BuildContext:
        return BuildContext(self.path + (node,), self.warns, self.setup_names,
                            self.update_names, self.value_names)


b32digits = "0123456789abcdefghijklmnopqrstuv"


def num32(n: int) -> str:
    if n == 0:
        return "_"
    digits = []
    while n:
        digits.append(int(n % 32))
        n //= 32
    return "".join(b32digits[x] for x in reversed(digits))


def idstr(o: object) -> str:
    return num32(id(o))


def objName(node: tf.AstNode, ctx: BuildContext) -> str:
    if node is None:
        return "None"
    if isinstance(node, tf.JsonpathNode):
        prefix = f"_{node.name}" if node.name else ""
        name = f"{prefix}_path_{idstr(node)}"
    elif hasattr(node, "name") and node.name:
        name = node.name
    else:
        if isinstance(node, tf.ObjectNode):
            prefix = node.type_name.replace(".", "_")
        else:
            prefix = type(node).__name__
        name = f"_{prefix}_{idstr(node)}"
    return name


def _fnSuffix(node: tf.AstNode, ctx: BuildContext) -> str:
    suffix = f"_{objName(node, ctx)}"
    # id_suffix = f"_{idstr(node)}"
    # if not suffix.endswith(id_suffix):
    #     suffix += id_suffix
    return suffix


def setupName(node: tf.AstNode, ctx: BuildContext) -> str:
    suffix = _fnSuffix(node, ctx)
    if isinstance(node, tf.PythonBlock):
        return suffix
    return f"_setup{suffix}"


def updateName(node: tf.AstNode, ctx: BuildContext) -> str:
    return f"_update{_fnSuffix(node, ctx)}"


def hasSetup(node: tf.AstNode) -> bool:
    return type(node) in setup_functions


def setupFor(node: tf.AstNode, ctx: BuildContext) -> list[str]:
    f =  setup_functions[type(node)]
    lines = f(node, ctx.push(node))
    if not lines:
        raise Exception(f"Function {f} returned {lines}")
    return lines


def updateFor(node: tf.AstNode, ctx: BuildContext) -> list[str]:
    return update_functions[type(node)](node, ctx.push(node))


def valueFor(node: tf.AstNode, ctx: BuildContext) -> str:
    t = type(node)
    if t in value_functions:
        f = value_functions[t]
    else:
        f = objName
    return f(node, ctx)


def moduleSetup(node: tf.ModuleNode, ctx: BuildContext) -> list[str]:
    # Sort models first so objects can refer to them
    items = list(node.items)
    items.sort(key=lambda sub: int(not isinstance(sub, tf.ModelNode)))

    lines = [
        "import jsonpathfx",
        "from tilefx.file import tilefile as _tf",
        "from tilefx.file.tilefile import Namespace as _NS",
        "from tilefx.graphics.core import GraphicTemplate as _GT",
        "from tilefx.models import DataModel as _DM",
        "from tilefx.graphics.styling import TextSize, ThemeColor",
        "_styles = _NS()",
        "",
    ]

    for it in items:
        if isinstance(it, tf.PythonBlock):
            lines.append("# Code block")
            lines.extend(source_lines(it.source, level=0))

    lines.extend([
        "def setup(scene, data, env):",
        "    _root_obj = None"
    ])
    for it in items:
        if isinstance(it, tf.PythonBlock):
            continue
        elif isinstance(it, (tf.StyleNode, tf.ModelNode, tf.ObjectNode)) and it.name:
            lines.extend(indentLines(setupFor(it, ctx)))
            if isinstance(it, tf.ObjectNode):
                lines.append(f"    _root_obj = {objName(it, ctx)}")
        else:
            ctx.warn("Module property has no effect", it)

    lines.extend(indentLines(moduleUpdate(node, ctx)))
    lines.append("    return _root_obj, update_module")
    return lines


def moduleUpdate(node: tf.ModuleNode, ctx: BuildContext) -> list[str]:
    lines: list[str] = [
        "# Module update",
        f"def update_module(_data, env):"
    ]
    for it in node.items:
        if type(it) in update_functions:
            lines.append(f"    {updateName(it, ctx)}(None, _data, env)")
    return lines


def styleSetup(node: tf.StyleNode, ctx: BuildContext) -> list[str]:
    setup_fn_name = setupName(node, ctx)
    lines = [
        f"# style: {node.name}",
        f"def {setup_fn_name}(_, _data, env, this: _NS = None) -> _tf.Namspace:",
        "    obj = _tf.Namespace()"
    ]
    for it in node.items:
        if isinstance(it, (tf.Prop, tf.Assign)) and hasSetup(it.value):
            lines.extend(indentLines(setupFor(it.value, ctx)))

        if isinstance(it, tf.Assign) and it.dynamic():
            lines.append(f"    {it.name} = {valueFor(it.value, ctx)}")
        elif isinstance(it, tf.Prop):
            lines.append(f"    obj.{it.name} = {valueFor(it.value, ctx)}")
    lines.append("    return obj")
    lines.append(f"_styles.{node.name} = {setup_fn_name}(None, _data, env, this)")
    return lines


def pythonBlockSetup(node: tf.PythonBlock, ctx: BuildContext) -> list[str]:
    fn_name = setupName(node, ctx)
    assert fn_name
    return [
        f"def {fn_name}(obj, _data, env, this: _NS = None) -> Any:",
        "    _this = _data",
    ] + source_lines(node.source)


def pythonBlockValue(node: tf.PythonBlock, ctx: BuildContext) -> str:
    return f"{setupName(node, ctx)}(obj, _data, env, this)"


def pythonExprValue(node: tf.PythonExpr, ctx: BuildContext) -> str:
    return node.source


def pythonExprUpdate(node: tf.PythonExpr, ctx: BuildContext) -> str:
    return node.source


def jsonpathSetup(node: tf.JsonpathNode, ctx: BuildContext) -> list[str]:
    return [
        f"{objName(node, ctx)} = jsonpathfx.parse({node.source!r})"
    ]


def jsonpathValue(node: tf.JsonpathNode, ctx: BuildContext) -> str:
    return f"{objName(node, ctx)}.values(_here, this)"


def literalValue(node: tf.Literal, ctx: BuildContext) -> str:
    return repr(node.value)


def dictValue(node: tf.DictNode, ctx: BuildContext) -> str:
    its: list[str] = []
    for k, v in node.values.items():
        if type(k) is tf.ComputedKey:
            k_str = str(k)
        elif isinstance(k, str):
            k_str = repr(k)
        else:
            raise TypeError(f"Can't serialize key {k!r}")
        its.append(f"{k_str}: {valueFor(v, ctx)}")
    return "{" + ", ".join(its) + "}"


def listValue(self, ctx: BuildContext) -> str:
    return (
        "[" +
        ", ".join(valueFor(v, ctx) for v in self.values) +
        "]"
    )


def objectValue(node: tf.ObjectNode, ctx: BuildContext) -> str:
    if node.is_template:
        return (f"_GT({setupName(node, ctx)}, "
                f"{updateName(node, ctx)})")
    elif node.name:
        return objName(node, ctx)
    else:
        return f"{setupName(node, ctx)}(obj, _data, env, this)"


def objectSetup(node: tf.ObjectNode, ctx: BuildContext) -> list[str]:
    lines = []
    setup_name = setupName(node, ctx)
    update_name = updateName(node, ctx)

    type_name = "template" if node.is_template else "object"
    # cls_name = graphic_class_registry[node.type_name]

    if node.name:
        lines.append(f"# {type_name} setup: {node.name}")

    lines.extend([
        f"def {setup_name}(obj, _data, env, this: _NS = None):",
        "    parent = obj",
        "    if not this: this = _NS()",
        f"    obj = {node.type_name}()",
    ])
    if node.name:
        lines.append(f"    obj.setObjectName({node.name!r})")

    if any(isinstance(it, tf.StyleNode) for it in node.items):
        lines.append("    _styles = _styles.copy()")

    # has_model = False
    for it in node.items:
        if isinstance(it, (tf.Prop, tf.Assign)) and hasSetup(it.value):
            lines.extend(indentLines(setupFor(it.value, ctx)))

        if isinstance(it, tf.Assign):
            if not it.dynamic():
                lines.append(f"    {it.name} = {valueFor(it.value, ctx)}")
        elif isinstance(it, tf.Prop):
            # has_model = has_model or it.name == "model"
            lines.append(f"    obj.set_{it.name}({valueFor(it.value, ctx)})")
        elif isinstance(it, tf.ObjectNode):
            lines.extend(indentLines(setupFor(it, ctx)))
            if it.is_template:
                lines.append(f"    {it.name} = {valueFor(it, ctx)}")
            else:
                lines.append(f"    obj.addItem({valueFor(it, ctx)})")
        elif hasSetup(it):
            lines.extend(indentLines(setupFor(it, ctx)))

    # for it in node.items:
    #     if type(it) in update_functions:
    #         lines.extend(indentLines(updateFor(it, ctx)))

    lines.extend(indentLines(updateFor(node, ctx)))

    lines.append(f"    return obj, {update_name}")
    if node.name and not node.is_template:
        lines.append("# path: " + ",".join(objName(p, ctx) for p in ctx.path))
        if len(ctx.path) > 1:
            args = "obj, _data, env, this"
        else:
            args = "None, {}, _NS(), None"
        lines.append(f"{node.name}, {update_name} = {setup_name}({args})")

    return lines


def objectUpdate(node: tf.ObjectNode, ctx: BuildContext) -> list[str]:
    type_name = "template" if node.is_template else "object"
    fn_name = updateName(node, ctx)
    dynamics = [it for it in node.items if it.dynamic()]
    lines = []
    if node.name:
        lines.append(f"# {type_name} update: {node.name}")

    # for it in dynamics:
    #     if isinstance(it, (tf.Assign, tf.Prop)):
    #         it = it.value
    #     if type(it) in update_functions:
    #         lines.extend(updateFor(it, ctx))

    lines.extend([
        f"def {fn_name}(obj, _data, env, this: _NS = None) -> None:",
        "    _here = _data",
        "    if hasattr(obj, 'localEnv'):",
        "       this |= obj.localEnv()"
    ])
    # if has_model:
    #     lines.append("        model = obj.dataModel()")
    for it in dynamics:
        if isinstance(it, tf.Assign):
            if not it.dynamic():
                lines.append(f"    {it.name} = {valueFor(it.value, ctx)}")
        if isinstance(it, tf.Prop):
            ctx.property_name = it.name
            lines.append(
                f"    obj.set_{it.name}({valueFor(it.value, ctx)})"
            )
        elif type(it) in update_functions:
            lines.append(f"    {updateName(it, ctx)}({it.name}, _data, env, this)")

    return lines


MODEL_SETTING_NAMES = ("sorted_by", "dynamic_sort", "dynamic_filter",
                       "unique_id", "color_id", "key_order")


def modelSetup(node: tf.ModelNode, ctx: BuildContext) -> list[str]:
    name = objName(node, ctx)
    setup_name = setupName(node, ctx)
    update_name = updateName(node,ctx)
    lines = [f"# setup model: {name}"]

    has_jsonpath = False
    for it in node.items:
        if isinstance(it, (tf.Prop, tf.Assign)) and hasSetup(it.value):
            if isinstance(it.value, tf.JsonpathNode):
                has_jsonpath = True
            lines.extend(setupFor(it.value, ctx))

    lines.extend([
        f"def {setup_name}(_, _data, env, this: _NS = None) -> _DM:",
        "    model = _DM()",
    ])
    if node.name:
        lines.append(f"    obj.setObjectName({node.name!r})")

    has_id = False
    rows_val: Optional[str] = None
    for it in node.items:
        if isinstance(it, tf.Assign):
            lines.append(f"    {it.name} = {valueFor(it.value, ctx)}")
        elif isinstance(it, tf.Prop):
            key = it.name
            val = valueFor(it.value, ctx)
            if key == "rows":
                rows_val = val
                # lines.append(f"    model.setRows({val})")
            elif key == "sorted_by":
                lines.append(f"    model.setSortSpec({val})")
            elif key == "unique_id":
                has_id = True
                lines.append(f"    model.setUniqueDataID({val})")
            elif key == "color_id":
                lines.append(f"    model.setColorDataID({val})")
            elif key == "key_order":
                lines.append(f"    model.setKeyOrder({val})")
            else:
                has_id = has_id or key == "id"
                lines.append(f"    model.addDataIDSpec({key!r})")

    if not has_id:
        ctx.warn("Model does not specify a unique row ID", node)

    lines.extend(indentLines(updateFor(node, ctx)))
    lines.append(f"    return model, {update_name}")
    lines.append(f"{objName(node, ctx)}, {update_name} = {setup_name}(None, _data, env, this)")
    return lines


def modelUpdate(node: tf.ModelNode, ctx: BuildContext) -> list[str]:
    update_fn_name = updateName(node, ctx)
    lines = [
        f"def {update_fn_name}(model, _data, env, this: _NS = None) -> None:",
        "    _rows = []",
    ]
    rows_val: Optional[str] = None
    for it in node.items:
        if isinstance(it, tf.Prop) and it.name == "rows":
            rows_val = valueFor(it, ctx)

    if rows_val:
        lines.append(f"    for obj in {rows_val}:")
        lines.append("        _ro = {}")
        # if has_jsonpath:
        #     lines.append("        _here = obj")
        for it in node.items:
            if not isinstance(it, (tf.Assign, tf.Prop)):
                continue
            val = valueFor(it.value, ctx)
            if isinstance(it, tf.Assign):
                lines.append(f"        {it.name} = {val}")
            elif isinstance(it, tf.Prop):
                key = it.name
                if key != "rows" and key not in MODEL_SETTING_NAMES:
                    lines.append(f"        _ro[{it.name!r}] = {val}")
        lines.append("        _rows.append(_ro)")
    else:
        ctx.warn("Model does not have a rows expression", node)
    lines.append("    model.setRows(_rows)")
    return lines


def funcSetup(node: tf.FuncNode, ctx: BuildContext) -> list[str]:
    return [
        f"def {objName(node, ctx)}():"
    ] + source_lines(node.expr.source)


value_functions = {
    tf.PythonExpr: pythonExprValue,
    tf.PythonBlock: pythonBlockValue,
    tf.JsonpathNode: jsonpathValue,
    tf.Literal: literalValue,
    tf.DictNode: dictValue,
    tf.ListNode: listValue,
    tf.ObjectNode: objectValue,
}
setup_functions = {
    tf.ModuleNode: moduleSetup,
    tf.StyleNode: styleSetup,
    tf.PythonBlock: pythonBlockSetup,
    tf.JsonpathNode: jsonpathSetup,
    tf.ObjectNode: objectSetup,
    tf.ModelNode: modelSetup,
    tf.FuncNode: funcSetup,
}
update_functions = {
   tf.ModuleNode: moduleUpdate,
   tf.ObjectNode: objectUpdate,
   tf.ModelNode: modelUpdate,
}


def main() -> None:
    import pathlib
    from time import perf_counter

    t = perf_counter()
    in_path = pathlib.Path("/Users/matt/dev/src/houdini/support/config/Root/node_info.tilefile")
    # in_path = pathlib.Path("/Users/matt/Downloads/test.tilefile")
    out_path = pathlib.Path("/Users/matt/Downloads/" + in_path.stem + ".py")
    print("out=", out_path)
    text = in_path.read_text()
    p = tf.parse(text)
    assert isinstance(p, tf.ModuleNode)
    ctx = BuildContext()
    lines = moduleSetup(p, ctx)
    # lines.extend(moduleUpdate(p, ctx))
    lines.append("")
    source = "\n".join(lines)
    out_path.write_text(source)

    code = compile(source, out_path, "exec")
    print(time.perf_counter() - t)
    for warn in ctx.warns:
        print("WARN:", warn)


if __name__ == "__main__":
    main()

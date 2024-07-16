from __future__ import annotations
import dataclasses
import textwrap
from typing import Any, Callable, Optional

import jsonpathfx

from .tilefile import (newline_expr, AstNode, ModuleNode, PythonNode,
                       PythonValueNode, JsonpathNode, LiteralValueNode,
                       DictNode, ListNode, ObjectNode, ModelNode, EnvVarNode)


def source_lines(source: str, level=1) -> list[str]:
    source = textwrap.dedent(source)
    lines = newline_expr.split(source)
    if level:
        lines = indent_lines(lines, level)
    return lines


def indent_lines(lines: list[str], level=1):
    if level:
        tab = "    " * level
        lines = [f"{tab}{line}" for line in lines]
    else:
        lines = list(lines)
    return lines


@dataclasses.dataclass
class BuildContext:
    obj: Any
    obj_name: str
    class_name: str
    parent_name: Optional[str]
    property_name: Optional[str]
    memo: dict[int, Any] = dataclasses.field(default_factory=dict)
    warns: list[tuple[str, AstNode]] = dataclasses.field(default_factory=list)


SetupFunction = Callable[[AstNode, BuildContext], list[str]]
ValueFunction = Callable[[AstNode, BuildContext], str]
UpdateFunction = Callable[[AstNode, BuildContext], str]


def objName(node: ObjectNode) -> str:
    if node.obj_name:
        return node.obj_name
    else:
        return f"obj_{id(node):x}"


def modelName(node: ModelNode) -> str:
    if node.obj_name:
        return node.obj_name
    else:
        return f"model_{id(node):x}"


def setupFor(node: AstNode, ctx: BuildContext) -> list[str]:
    return setup_functions[type(node)](node, ctx)


def valueFor(node: AstNode, ctx: BuildContext) -> str:
    return value_functions[type(node)](node, ctx)


def updateFor(node: AstNode, ctx: BuildContext) -> str:
    return update_functions[type(node)](node, ctx)


def moduleSetup(node: ModuleNode, ctx: BuildContext) -> list[str]:
    lines: list[str] = [
        "def setupModule():"
    ]
    for subnode in node.value:
        ctx.parent_name = None
        if type(subnode) in setup_functions:
            lines.extend(indent_lines(setupFor(subnode, ctx), 1))

        if isinstance(subnode, PythonNode) and subnode.mode == "exec":
            lines.extend(indent_lines(setupFor(subnode, ctx), 1))
        elif isinstance(subnode, ObjectNode):
            pass
        elif isinstance(subnode, ModelNode) and subnode.obj_name:
            pass
        else:
            ctx.warns.append(("Module property has no effect", subnode))

    dynamic = [sub for sub in node.value if type(sub) in update_functions]
    if dynamic:
        lines.append("def updateModuleFromData(data, env):")
        for subnode in dynamic:
            lines.append(f"    {updateFor(subnode, ctx)}")

    return lines


def moduleUpdate(node: ModelNode, ctx: BuildContext) -> str:
    return "updateModuleFromData(data, env)"


def python_fn_name(ctx: BuildContext) -> str:
    return f"update_{ctx.obj_name}_{ctx.property_name}"


def pythonSetup(node: PythonNode, ctx: BuildContext) -> list[str]:
    fn_name = python_fn_name(ctx)
    return [
        f"def {fn_name}(self: {ctx.class_name}) -> Any:"
    ] + source_lines(node.source)


def pythonValue(node: PythonNode, ctx: BuildContext) -> str:
    fn_name = python_fn_name(ctx)
    return f"{fn_name}(self)"


def pythonUpdate(node: PythonNode, ctx: BuildContext) -> str:
    if node.mode == "exec":
        return f"{python_fn_name(ctx)}(self)"
    else:
        return node.source


def pyValueValue(node: PythonValueNode, ctx: BuildContext) -> str:
    return node.source


def jsonpath_var_name(ctx: BuildContext) -> str:
    return f"{ctx.obj_name}_{ctx.property_name}_path"


def jsonpathSetup(node: JsonpathNode, ctx: BuildContext) -> list[str]:
    path_var = jsonpath_var_name(ctx)
    return [
        f"{path_var} = jsonpathfx.parse({node.source!r})"
    ]


def jsonpathValue(node: JsonpathNode, ctx: BuildContext) -> str:
    path_var = jsonpath_var_name(ctx)
    return f"{path_var}.values(data, env)"


def literalValue(node: LiteralValueNode, ctx: BuildContext) -> str:
    return repr(node.value)


def dictValue(node: DictNode, ctx: BuildContext) -> str:
    return (
        "{" +
        ", ".join(f"{k!r}: {valueFor(v, ctx)}"
                  for k, v in node.value.items()) +
        "}"
    )


def listValue(self, ctx: BuildContext) -> str:
    return (
        "[" +
        ", ".join(valueFor(v, ctx) for v in self.value) +
        "]"
    )


def object_setup_fn_name(ctx: BuildContext) -> str:
    return f"make_{ctx.obj_name}"


def object_update_fn_name(ctx: BuildContext) -> str:
    return f"update_{ctx.obj_name}"


def objectValue(node: ObjectNode, ctx: BuildContext) -> str:
    if node.is_template:
        ctx.obj_name = objName(node)
        return object_setup_fn_name(ctx)
    else:
        return objName(node)


def objectSetup(node: ObjectNode, ctx: BuildContext) -> list[str]:
    ctx.obj_name = name = objName(node)
    setup_fn_name = object_setup_fn_name(ctx)
    update_fn_name = object_update_fn_name(ctx)
    statics = [x for x in node.params if type(x[1]) not in update_functions]
    dynamics = [x for x in node.params if type(x[1]) in update_functions]

    lines = []
    for n, p in dynamics:
        ctx.property_name = name
        if type(p) in setup_functions:
            lines.extend(setupFor(p, ctx))

    lines.extend([
        f"def {setup_fn_name}(parent: Any) -> {ctx.class_name}:",
        f"    __obj = {ctx.class_name}()",
        f"    __obj.setObjectName({name!r})"
    ])

    for n, p in statics:
        ctx.property_name = name
        lines.append(f"    setProperty({name}, {n}, {valueFor(p, ctx)})")
    lines.append("    return __obj")

    if dynamics:
        lines.append(f"def {update_fn_name}(self, data, env) -> None:")
        for n, p in dynamics:
            ctx.property_name = n
            lines.append(f"    setProperty({name}, {n}, {updateFor(p, ctx)})")

    if not node.is_template:
        lines.append(f"{ctx.obj_name} = {setup_fn_name}({ctx.parent_name}")
        if ctx.parent_name:
            lines.append(f"{ctx.parent_name}.addItem({ctx.obj_name}")

    ctx.parent_name = name
    for child in node.items:
        lines.extend(setupFor(child, ctx))

    return lines


def objectUpdate(node: ObjectNode, ctx: BuildContext) -> str:
    ctx.obj_name = name = objName(node)
    return f"{object_update_fn_name(ctx)}({name}, data, env)"


def model_setup_fn_name(ctx: BuildContext) -> str:
    return f"make_model_{ctx.obj_name}"


def model_update_fn_name(ctx: BuildContext) -> str:
    return f"update_model_{ctx.obj_name}"


def modelValue(node: ModelNode, ctx: BuildContext) -> str:
    return modelName(node)


MODEL_SETTING_NAMES = ("rows", "sorted_by", "dynamic_sort", "dynamic_filter",
                       "unique_id", "color_id", )


def modelSetup(node: ModelNode, ctx: BuildContext) -> list[str]:
    ctx.obj_name = name = modelName(node)
    setup_fn_name = model_setup_fn_name(ctx)
    update_fn_name = model_update_fn_name(ctx)
    lines = []

    cols = [x for x in node.params.items() if x[0] not in MODEL_SETTING_NAMES]
    for n, p in cols:
        if type(p) not in update_functions:
            ctx.warns.append((f"Model property {n} is not dynamic", p))

    rows_node = node.params.get("rows")
    if not rows_node:
        ctx.warns.append((f"Model does not have a 'rows' expression", node))

    for setting_name in MODEL_SETTING_NAMES:
        setting_node = node.params.get(setting_name)
        ctx.property_name = setting_name
        if type(setting_node) in setup_functions:
            lines.extend(setupFor(rows_node, ctx))

    lines.extend([
        f"def {setup_fn_name}() -> DataModel:",
        f"    __model = DataModel()",
    ])
    for n, _ in cols:
        lines.append(f"    __model.addDataIDSpec({n!r})")

    if uid_node := node.params.get("unique_id"):
        ctx.property_name = "unique_id"
        lines.append(f"    __model.setUniqueDataID({valueFor(uid_node, ctx)}")

    if rows_node:
        if type(rows_node) in update_functions:
            lines.extend([
                f"def {update_fn_name}(self: DataModel, data, env) -> None:"
                "    row_objs = []"
            ])
            for n, p in cols:
                lines.append(f"    _{n} = self.dataToID({n!r})")
            lines.extend([
                f"    for row in {valueFor(rows_node, ctx)}:"
                "        row_objs.append({"
            ])
            for n, p in cols:
                ctx.property_name = n
                lines.append(f"            _{n}: {valueFor(p, ctx)}")
            lines.append("        }")
            lines.append(f"    {name}.setRows(row_objs)")
        elif isinstance(rows_node, ListNode):
            ctx.property_name = "rows"
            lines.append(f"    __model.setRows({valueFor(rows_node, ctx)}")
        else:
            ctx.warns.append(("Rows property must be an expression or list",
                              rows_node))

    return lines


def modelUpdate(node: ModelNode, ctx: BuildContext) -> str:
    ctx.obj_name = name = modelName(node)
    return f"{model_update_fn_name(ctx)}({name}, data, env)"


value_functions = {
    PythonNode: pythonValue,
    PythonValueNode: pyValueValue,
    JsonpathNode: jsonpathValue,
    LiteralValueNode: literalValue,
    DictNode: dictValue,
    ListNode: listValue,
    ObjectNode: objectValue,
    ModelNode: modelValue,
}
setup_functions = {
    ModuleNode: moduleSetup,
    PythonNode: pythonSetup,
    JsonpathNode: jsonpathSetup,
}
update_functions = {
    ModuleNode: moduleUpdate,
    PythonNode: pythonUpdate,
    JsonpathNode: jsonpathUpdate,
    ObjectNode: objectSetup,
    ModelNode: modelUpdate
}

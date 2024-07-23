from __future__ import annotations
import dataclasses
import textwrap
from typing import Any, Callable, Optional

import jsonpathfx

from .tilefile import (newline_expr, AstNode, ModuleNode,
                       PythonExpr, PythonBlock, StaticPythonExpr, JsonpathNode,
                       Literal, DictNode, ListNode, ObjectNode, ModelNode,
                       ComputedKey)


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
    type_name: str
    memo: dict[int, Any] = dataclasses.field(default_factory=dict)
    warns: list[tuple[str, AstNode]] = dataclasses.field(default_factory=list)
    parent_name: Optional[str] = None
    parent_type_name: Optional[str] = None
    property_name: Optional[str] = None


SetupFunction = Callable[[AstNode, BuildContext], list[str]]
ValueFunction = Callable[[AstNode, BuildContext], str]
UpdateFunction = Callable[[AstNode, BuildContext], str]


def objName(node: ObjectNode) -> str:
    if node.name:
        return node.name
    else:
        return f"obj_{id(node):x}"


def modelName(node: ModelNode) -> str:
    if node.name:
        return node.name
    else:
        return f"model_{id(node):x}"


def setupFor(node: AstNode, ctx: BuildContext) -> list[str]:
    if type(node) not in setup_functions:
        raise TypeError(f"No setup function for {type(node)}")
    return setup_functions[type(node)](node, ctx)


def valueFor(node: AstNode, ctx: BuildContext) -> str:
    return value_functions[type(node)](node, ctx)


def updateFor(node: AstNode, ctx: BuildContext) -> str:
    return update_functions[type(node)](node, ctx)


def moduleSetup(node: ModuleNode, ctx: BuildContext) -> list[str]:
    # Sort models first so objects can refer to them
    items = list(node.value)
    items.sort(key=lambda sub: int(not isinstance(sub, ModelNode)))

    lines: list[str] = []
    for sub in items:
        ctx.parent_name = None
        if type(sub) in setup_functions:
            lines.extend(setupFor(sub, ctx))

        if isinstance(sub, PythonBlock):
            lines.extend(setupFor(sub, ctx))
        elif isinstance(sub, ObjectNode):
            pass
        elif isinstance(sub, ModelNode) and sub.name:
            pass
        else:
            ctx.warns.append(("Module property has no effect", sub))

    dynamic = [sub for sub in items if type(sub) in update_functions]
    if dynamic:
        lines.append("def _updateModuleFromData(_data, _env):")
        for sub in dynamic:
            lines.append(f"    {updateFor(sub, ctx)}")

    return lines


def moduleUpdate(node: ModelNode, ctx: BuildContext) -> str:
    return "updateModuleFromData(_data, _env)"


def python_block_update_fn_name(ctx: BuildContext) -> str:
    return f"update_{ctx.obj_name}_{ctx.property_name}"


def pythonBlockSetup(node: PythonBlock, ctx: BuildContext) -> list[str]:
    fn_name = python_block_update_fn_name(ctx)
    return [
        f"def {fn_name}(obj, _data, _env) -> Any:"
    ] + source_lines(node.source)


def pythonBlockValue(node: PythonBlock, ctx: BuildContext) -> str:
    fn_name = python_block_update_fn_name(ctx)
    return f"{fn_name}(obj, _data, _env)"


def pythonExprValue(node: PythonExpr, ctx: BuildContext) -> str:
    return node.source


def pythonExprUpdate(node: PythonExpr, ctx: BuildContext) -> str:
    return node.source


def pythonStaticValue(node: StaticPythonExpr, ctx: BuildContext) -> str:
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
    return f"{path_var}.values(_data, _env)"


def literalValue(node: Literal, ctx: BuildContext) -> str:
    return repr(node.value)


def dictValue(node: DictNode, ctx: BuildContext) -> str:
    its: list[str] = []
    for k, v in node.value.items():
        if type(k) is ComputedKey:
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
        ", ".join(valueFor(v, ctx) for v in self.value) +
        "]"
    )


def object_setup_fn_name(ctx: BuildContext) -> str:
    return f"_make_{ctx.obj_name}"


def object_update_fn_name(ctx: BuildContext) -> str:
    return f"_update_{ctx.obj_name}"


def objectValue(node: ObjectNode, ctx: BuildContext) -> str:
    if node.is_template:
        ctx.obj_name = objName(node)
        return object_setup_fn_name(ctx)
    else:
        return objName(node)


def objectSetup(node: ObjectNode, ctx: BuildContext) -> list[str]:
    lines = []
    ctx.obj_name = name = objName(node)
    setup_fn_name = object_setup_fn_name(ctx)
    update_fn_name = object_update_fn_name(ctx)
    parent_name = ctx.parent_name
    parent_type_name = ctx.parent_type_name
    # cls_name = graphic_class_registry[node.type_name]

    on_setup = node.params.pop("on_setup", None)
    on_update = node.params.pop("on_update", None)

    for k, p in node.params.items():
        ctx.parent_name = node.name
        ctx.parent_typ_name = node.type_name
        ctx.property_name = k
        if type(p) in setup_functions:
            lines.extend(setupFor(p, ctx))

    lines.extend([
        f"def {setup_fn_name}() -> {ctx.type_name}:",
        f"    _obj = {node.type_name}()",
        f"    _obj.setObjectName({name!r})"
    ])
    if on_setup and isinstance(on_setup, PythonBlock):
        lines.extend(source_lines(on_setup.source))

    dyns = [k for k, p in node.params.items() if p.dynamic()]
    statics = [k for k in node.params if k not in dyns]
    for k in statics:
        p = node.params[k]
        ctx.property_name = name
        lines.append(f"    _obj.{k} = {valueFor(p, ctx)}")

    lines.append("    return _obj")

    if not node.is_template:
        lines.append(f"{ctx.obj_name} = {setup_fn_name}()")

    for child in node.items:
        ctx.parent_name = name
        ctx.parent_typ_name = node.type_name
        lines.extend(setupFor(child, ctx))

    for child in node.items:
        lines.append(f"{name}.addItem({objName(child)})")

    if dyns or node.items:
        lines.extend([
            f"def {update_fn_name}(obj, _data, _env) -> None:",
            "    _env |= obj.localEnv()"
        ])
        if on_update and isinstance(on_update, PythonBlock):
            lines.append("    # on_update")
            lines.extend(source_lines(on_update.source))

        for k in dyns:
            p = node.params[k]
            ctx.obj_name = name
            ctx.property_name = k
            value_expr = valueFor(p, ctx)
            assert isinstance(value_expr, str)
            lines.append(f"    obj.{k} = {value_expr}")
        for k, p in node.params.items():
            if type(p) in update_functions:
                ctx.obj_name = name
                ctx.property_name = k
                lines.append(f"    {updateFor(p, ctx)}")

        for child in node.items:
            ctx.parent_name = name
            ctx.parent_typ_name = node.type_name
            lines.append(f"    {updateFor(child, ctx)}")

    return lines


def objectUpdate(node: ObjectNode, ctx: BuildContext) -> str:
    ctx.obj_name = name = objName(node)
    return f"{object_update_fn_name(ctx)}({name}, _data, _env)"


def model_setup_fn_name(ctx: BuildContext) -> str:
    return f"_make_model_{ctx.obj_name}"


def model_update_fn_name(ctx: BuildContext) -> str:
    return f"_update_model_{ctx.obj_name}"


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
        if rows_node.dynamic():
            print("YYYY")
            lines.extend([
                f"def {update_fn_name}(model: DataModel, _data, _env) -> None:",
                "    _row_objs = []"
            ])
            for n, p in cols:
                lines.append(f"    _{n} = model.dataToID({n!r})")
            lines.extend([
                f"    for row in {valueFor(rows_node, ctx)}:",
                "        _row_objs.append({"
            ])
            for n, p in cols:
                ctx.property_name = n
                lines.append(f"            _{n}: {valueFor(p, ctx)}")
            lines.append("        }")
            lines.append(f"    {name}.setRows(_row_objs)")
        elif isinstance(rows_node, ListNode):
            ctx.property_name = "rows"
            lines.append(f"    model.setRows({valueFor(rows_node, ctx)}")
        else:
            ctx.warns.append(("Rows property must be an expression or list",
                              rows_node))



    return lines


def modelUpdate(node: ModelNode, ctx: BuildContext) -> str:
    ctx.obj_name = name = modelName(node)
    return f"{model_update_fn_name(ctx)}({name}, _data, _env)"


value_functions = {
    PythonExpr: pythonExprValue,
    PythonBlock: pythonBlockValue,
    StaticPythonExpr: pythonStaticValue,
    JsonpathNode: jsonpathValue,
    Literal: literalValue,
    DictNode: dictValue,
    ListNode: listValue,
    ObjectNode: objectValue,
    ModelNode: modelValue,
}
setup_functions = {
    ModuleNode: moduleSetup,
    PythonBlock: pythonBlockSetup,
    JsonpathNode: jsonpathSetup,
    ObjectNode: objectSetup,
    ModelNode: modelSetup,
}
update_functions = {
    ModuleNode: moduleUpdate,
    ObjectNode: objectUpdate,
    ModelNode: modelUpdate,
}

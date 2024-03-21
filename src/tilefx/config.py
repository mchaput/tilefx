from __future__ import annotations
import ast
import re
import time
from collections import defaultdict
from types import CodeType
from typing import (TYPE_CHECKING, cast, Any, Callable, Collection, Iterable,
                    NamedTuple, Optional, Sequence, TypeVar, Union)

from PySide2 import QtCore, QtWidgets
from PySide2.QtCore import Qt

import jsonpathfx as jsonpath
from jsonpathfx import JsonValue

from . import styling

if TYPE_CHECKING:
    import hou
    from . import models
    from .graphics import core


# Type aliases
Scalar = Union[int, float, str]
SetterType = Callable[[QtCore.QObject, Any], None]
ParentSetterType = Callable[[QtCore.QObject, QtCore.QObject, Any], None]
QObjType = type[QtCore.QObject]
DependsMap = dict[str, Collection[str]]
T = TypeVar("T")


settables_lookup: dict[int, SetterInfo] = {}
setter_cache: dict[tuple[QObjType, str], SetterType] = {}
propety_alias_cache: dict[int, dict[str, str]] = {}


class SetterInfo(NamedTuple):
    name: Optional[str]
    converter: Optional[Callable[..., Any]]
    pass_styled: bool
    value_object_type: Optional[type[QtCore.QObject]]
    is_parent_method: bool


def registrar(registry_dict: dict):
    def class_wrapper(*names):
        def fn(cls):
            for name in names:
                registry_dict[name] = cls
            return cls

        return fn
    return class_wrapper


def camelToSnake(camel: str, drop_set=False):
    words = re.split('(?=[A-Z])', camel)
    if words[0] == "set" and drop_set:
        words = words[1:]
    return "_".join(w.lower() for w in words)


def snakeToCamel(snake: str, initial=False) -> str:
    return "".join((s.title() if (i > 0 or initial) else s) for i, s
                   in enumerate(snake.split("_")))


def settable(name: str = None, *, argtype: type = None,
             converter: Callable = None, convert_each=False,
             pass_styled=False, value_object_type: type[QtCore.QObject] = None,
             is_parent_method=False) -> Callable[[T], T]:
    if name is not None and not isinstance(name, str):
        raise TypeError(f"{name!r} is not a string")
    if argtype is not None and not converter:
        from .converters import converter_registry, takes_styled_object
        try:
            converter = converter_registry[argtype]
        except KeyError:
            raise TypeError(f"No converter for argument type {argtype!r}")

        pass_styled = pass_styled or converter in takes_styled_object

        if convert_each:
            conv = converter

            def converter(seq: Sequence[Any]) -> Sequence[Any]:
                return [conv(item) for item in seq]

    def decorator(m: T) -> T:
        method_name = m.__name__
        if is_parent_method and not method_name.startswith("setChild"):
            raise NameError(
                f"Parent setter method {method_name} name must start "
                "with 'setChild'"
            )
        elif not method_name.startswith("set"):
            raise NameError(
                f"Setter method {method_name} name must start with 'set'"
            )

        key = name or camelToSnake(method_name, drop_set=True)
        settables_lookup[id(m)] = SetterInfo(
            key, converter, pass_styled, value_object_type, is_parent_method,
        )
        return m

    return decorator


def _findSettable(obj: QtCore.QObject, key: str, attr_prefix: str,
                  is_parent_method: bool) -> Callable:
    obj_type = type(obj)
    cache_key = (obj_type, key)
    setter: Optional[SetterType] = setter_cache.get(cache_key)
    if not setter:
        for attr_name in dir(obj_type):
            if not attr_name.startswith("set"):
                continue
            method = getattr(obj_type, attr_name)
            if info := settables_lookup.get(id(method)):
                if key == info.name and info.is_parent_method == is_parent_method:
                    setter = makeSettableCaller(method, info)
                    setter_cache[cache_key] = setter
                    break
    return setter


def findSettable(obj: QtCore.QObject, key: str) -> Optional[SetterType]:
    return _findSettable(obj, key, "set", is_parent_method=False)


def findParentSettable(obj: QtCore.QObject, key: str
                       ) -> Optional[ParentSetterType]:
    return _findSettable(obj, key, "setChild", is_parent_method=True)


def setterInfos(obj_type: type[QtCore.QObject]) -> dict[str, SetterInfo]:
    name_info_map: dict[str, SetterInfo] = {}
    for attr_name in dir(obj_type):
        if not attr_name.startswith("set"):
            continue
        method = getattr(obj_type, attr_name)
        if info := settables_lookup.get(id(method)):
            name_info_map[info.name] = info
    return name_info_map


def settableNames(obj: QtCore.QObject) -> Sequence[str]:
    return list(setterInfos(type(obj)))


def makeSettableCaller(fn: Callable[[QtCore.QObject, Any], None],
                       info: SetterInfo = None) -> SetterType:
    if info and info.converter:
        if info.pass_styled:
            def styled_conv_setter(obj: QtCore.QObject, value: Any) -> None:
                fn(obj, info.converter(value, styled_object=obj))
            setter = styled_conv_setter
        else:
            def conv_setter(obj: QtCore.QObject, value: Any) -> None:
                fn(obj, info.converter(value))
            setter = conv_setter
    else:
        setter = fn
    return setter


def findQtProperty(obj: QtCore.QObject, key: str
                   ) -> Optional[Callable[[Any, Any], None]]:
    try:
        meta = obj.metaObject()
    except AttributeError:
        return None

    setter: Optional[Callable[[Any], None]] = None
    camel_name = snakeToCamel(key, initial=False)
    for i in range(meta.propertyCount()):
        metaprop = meta.property(i)
        propname = metaprop.name()
        if propname == camel_name and metaprop.isWritable():
            def setter(o: QtCore.QObject, value: Any) -> None:
                o.setProperty(propname, value)
            break

    return setter


def _findElement(obj: QtCore.QObject, part: str) -> Optional[QtCore.QObject]:
    # For a regular QObject (but not a QGraphicsItem), use findChild() to find
    # a child by name
    found = obj.findChild(QtCore.QObject, part)
    if found:
        return cast(QtCore.QObject, found)

    # For QGraphicsItem, findChild() does not work, so we have to manually
    # iter through the childItems() and check for a name match
    if isinstance(obj, QtWidgets.QGraphicsItem):
        for child in obj.childItems():
            if isinstance(child, QtWidgets.QGraphicsObject) and \
                    child.objectName() == part:
                return child

    # For Graphic items, we have a pathElement() method that lets the item
    # "export" names without them being actual child items
    from .graphics import core
    if isinstance(obj, core.Graphic):
        element = obj.pathElement(part)
        if element:
            return element

    # camel_part = snakeToCamel(part)
    # if hasattr(obj, camel_part):
    #     return getattr(obj, camel_part)()


def setSettable(obj: QtCore.QObject, key: str, value: Any) -> None:
    from .graphics import core

    orig_key = key
    if isinstance(obj, core.Graphic):
        cls = type(obj)
        cls_id = id(cls)
        if cls_id in propety_alias_cache:
            aliases = propety_alias_cache[cls_id]
        else:
            aliases = propety_alias_cache[cls_id] = cls.propertyAliases()
        key = aliases.get(key, key)

    if "." in key:
        parts = key.split(".")
        key = parts[-1]
        for part in parts[:-1]:
            next_obj = _findElement(obj, part)
            if not next_obj:
                raise KeyError(
                    f"Could not find {part!r} of {obj!r} ({orig_key}")
            obj = next_obj

    if set_method := findSettable(obj, key):
        pass
    elif set_method := findQtProperty(obj, key):
        pass
    else:
        known = settableNames(obj)
        raise KeyError(f"Property {key!r} not found on {obj!r} ({orig_key}): "
                       f"{known}")
    set_method(obj, value)


# Controller

def _toJsonPath(path: Union[str, jsonpath.JsonPath],
                cache: dict[str, jsonpath.JsonPath] = None
                ) -> jsonpath.JsonPath:
    if isinstance(path, str):
        if cache and path in cache:
            return cache[path]
        else:
            parsed = jsonpath.parse(path)
            if cache is not None:
                cache[path] = parsed
            return parsed
    elif isinstance(path, jsonpath.JsonPath):
        return path
    raise TypeError(f"Not a jsonpath: {path}")


class Expr:
    no_default = object()

    def __init__(self, *, value_map: dict[JsonValue, JsonValue] = None,
                 default=no_default, text_transform: str = None,
                 depends: Collection[str] = ()):
        self.value_map = value_map
        self.default = default
        self.text_transform: Optional[Callable[[str], str]] = None
        self.depends = depends

        if callable(text_transform):
            self.text_transform = text_transform
        elif text_transform == "upper":
            self.text_transform = lambda s: s.upper()
        elif text_transform == "lower":
            self.text_transform = lambda s: s.lower()
        elif text_transform == "capitalize":
            self.text_transform = lambda s: s.capitalize()
        elif text_transform:
            raise ValueError(f"Unknown text transform {text_transform!r}")

    def readOnly(self) -> bool:
        return True

    def evaluate(self, data: Any, env: dict[str, Any]) -> Any:
        raise NotImplementedError

    def findRowDatas(self, data: Any, env: dict[str, Any]
                     ) -> Iterable[models.RowData]:
        from .models import RowData
        for value in self.evaluate(data, env):
            yield RowData(value, env)

    def set(self, value: Any) -> None:
        raise NotImplementedError

    def _map(self, value: JsonValue) -> JsonValue:
        if self.value_map and value in self.value_map:
            value = self.value_map[value]
        elif self.default is not self.no_default:
            value = cast(JsonValue, self.default)

        if isinstance(value, str) and self.text_transform:
            value = self.text_transform(value)

        return value


# class StaticFinder(Finder):
#     def __init__(self, rows: Sequence[dict[str, JsonValue]]):
#         self._rows: list[dict[DataId, JsonValue]] = []
#         if not isinstance(rows, (list, tuple)):
#             raise TypeError(f"{rows!r} is not a sequence")
#
#         for row in rows:
#             if not isinstance(row, dict):
#                 raise TypeError(f"Static row {row!r} is not dict")
#             self._rows.append({specToDataId(k): v
#                                for k, v in row.items()})
#
#     def findRows(self, data: dict[str, Any], env: dict[str, Any]
#                  ) -> Sequence[tuple[JsonValue, dict[str, Any]]]:
#         return self._rows


class JsonPathExpr(Expr):
    def __init__(self, path: Union[str, jsonpath.JsonPath],
                 cache: dict[str, jsonpath.JsonPath], *, all_values=False,
                 **kwargs):
        super().__init__(**kwargs)
        self.path = _toJsonPath(path, cache)
        self.all_values = all_values

    def __repr__(self):
        return (f"<{type(self).__name__} {self.path!r} all={self.all_values} "
                f"default={self.default}>")

    @classmethod
    def fromData(cls, data: Union[str, dict[str, Any]],
                 cache: Optional[dict[str, jsonpath.JsonPath]]
                 ) -> JsonPathExpr:
        if isinstance(data, str):
            return JsonPathExpr(data, cache)
        elif isinstance(data, dict):
            if "path" not in data:
                raise KeyError(f"No 'path' key in JsonPath config: {data!r}")
            all_values = data.get("all", False)
            value_map = data.get("value_map")
            default = data.get("default", Expr.no_default)
            depends = data.get("depends", ())
            return JsonPathExpr(
                data["path"], cache, all_values=all_values, depends=depends,
                value_map=value_map, default=default
            )
        else:
            raise TypeError(data)

    def evaluate(self, data: dict[str, Any], env: dict[str, Any]) -> Any:
        try:
            values = self.path.values(data)
        except Exception as e:
            raise Exception(f"Error while evaluating {self.path}: {e}")
        if self.all_values:
            return values
        elif values:
            return self._map(values[0])
        elif self.default is not Expr.no_default:
            return self.default

    def findRowDatas(self, data: dict[str, Any], env: dict[str, Any]
                     ) -> Iterable[models.RowData]:
        from .models import RowData
        try:
            for match in self.path.find(data, env):
                bindings = match.bindings()
                if bindings:
                    row_env = env.copy()
                    row_env.update(bindings)
                else:
                    row_env = env
                yield RowData(match.value, row_env)
        except Exception as e:
            raise Exception(f"Error while finding with {self.path}: {e}")


class PythonExpr(Expr):
    def __init__(self, expression: Union[str, CodeType], **kwargs):
        super().__init__(**kwargs)
        self.source = ""
        if isinstance(expression, str):
            self.source = expression
            tree = ast.parse(expression, mode="eval")
            for n in ast.walk(tree):
                if isinstance(n, ast.Name) and n.id == "__import__" or \
                        isinstance(n, (ast.Import, ast.ImportFrom)):
                    raise SyntaxError("Import not allowed in expressions")
            expression = compile(tree, expression, "eval")
        elif not isinstance(expression, CodeType):
            raise TypeError(expression)
        self.code = expression

    def __repr__(self):
        return f"<{type(self).__name__} {self.source!r}>"

    @classmethod
    def fromData(cls, data: Union[str, dict[str, Any], PythonExpr]
                 ) -> PythonExpr:
        if isinstance(data, PythonExpr):
            return data
        if isinstance(data, str):
            return PythonExpr(data)
        elif isinstance(data, dict):
            if "expression" not in data:
                raise KeyError(
                    f"No 'expression' key in PythonExpr config: {data!r}")
            return PythonExpr(**data)
        else:
            raise TypeError(f"Can't create a Python expression from {data!r}")

    def evaluate(self, data: Any, env: dict[str, Any]) -> Any:
        value = eval(self.code, {}, env)
        value = self._map(value)
        return value


class ExternalExpr(Expr):
    def __init__(self, read: Callable, write: Callable = None, **kwargs):
        self._read = read
        self._write = write

    def readOnly(self) -> bool:
        return self._write is not None

    def evaluate(self, data: Any, env: dict[str, Any]) -> Any:
        return self._read(data, env)

    def set(self, value: Any) -> None:
        self._write(value)


# class InfoTreeValue(Expr):
#     info_expr = re.compile(
#         "(?P<branches>[^#]*)(#(?P<col>.*))?"
#     )
#     info_type_prefix = "type:"
#
#     def __init__(self, branches: Union[str, Sequence[str]],
#                  row_id: Union[str, int], column_id: Union[str, int]):
#         if isinstance(branches, str):
#             branches = branches.split("/")
#         if isinstance(row_id, str) and row_id.isdigit():
#             row_id = int(row_id)
#         if isinstance(column_id, str) and column_id.isdigit():
#             column_id = int(column_id)
#         self.branches = tuple(branches)
#         self.row_id = row_id
#         self.column_id = column_id
#
#     def __repr__(self):
#         return (f"<{type(self).__name__} {self.branches} "
#                 f"{self.row_id!r} {self.column_id!r}>")
#
#     @classmethod
#     def fromString(cls, spec: str) -> InfoTreeValue:
#         m = cls.info_expr.match(spec)
#         if not m:
#             raise ValueError(f"Could not parse info tree spec: {spec!r}")
#
#         branches = m.group("branches").split("/")
#         if branches:
#             row_id = branches[-1]
#             branches = branches[:-1]
#         else:
#             raise ValueError(f"No row specifiedc: {spec!r}")
#         col_id = m.group("col") or 1
#         obj = cls(branches, row_id, col_id)
#         return obj
#
#     @classmethod
#     def tree(cls, tree: hou.NodeInfoTree, branches: tuple[str, ...]
#              ) -> Optional[hou.NodeInfoTree]:
#         for branch_id in branches:
#             branches: dict[str, hou.NodeInfoTree] = tree.branches()
#             if branch_id.startswith(cls.info_type_prefix):
#                 type_name = branch_id.removeprefix(cls.info_type_prefix)
#                 for tree in branches.values():
#                     if tree.infoType() == type_name:
#                         break
#                 else:
#                     return
#             else:
#                 tree = tree.branches().get(branch_id)
#             if not tree:
#                 return
#         return tree
#
#     @staticmethod
#     def row(tree: hou.NodeInfoTree, branches: tuple[str, ...],
#             row_id: Union[str, int]) -> Optional[Sequence[str]]:
#         tree = InfoTreeValue.tree(tree, branches)
#         rows = tree.rows()
#         if isinstance(row_id, int):
#             if 0 <= row_id < len(rows):
#                 return rows[row_id]
#         else:
#             for row in rows:
#                 if row[0] == row_id:
#                     return row
#
#     @staticmethod
#     def value(tree: hou.NodeInfoTree, branches: tuple[str, ...],
#               row_id: Union[str, int], col_id: Union[str, int]
#               ) -> Optional[str]:
#         row = InfoTreeValue.row(tree, branches, row_id)
#         if not row:
#             return
#
#         if not isinstance(col_id, int):
#             try:
#                 col_id = tree.headings().index(col_id)
#             except ValueError:
#                 return
#         if 0 <= col_id < len(row):
#             return row[col_id]
#
#     def evaluate(self, tree: hou.NodeInfoTree, env: dict[str, Any]) -> Any:
#         return self.value(tree, self.branches, self.row_id, self.column_id)


def exprFromData(data: dict[str, Any], controller: DataController,
                 allow_literals=False) -> Expr:
    if isinstance(data, str):
        data = PythonExpr.fromData(data)
    elif isinstance(data, dict) and "path" in data:
        data = JsonPathExpr.fromData(data, None)
    elif isinstance(data, dict) and "expression" in data:
        data = PythonExpr.fromData(data)
    elif isinstance(data, dict) and "external" in data:
        data = controller.externalExpression(data["external"])
    elif isinstance(data, Expr):
        pass
    elif isinstance(data, (int, float)) and allow_literals:
        pass
    else:
        raise TypeError(f"{data} is not a valid expression")
    return data


def exprMap(source_dict: dict[str, Union[str, dict, Expr, int, float]],
            controller: DataController, allow_literals=False
            ) -> dict[str, Union[Expr, Scalar]]:
    if not isinstance(source_dict, dict):
        raise TypeError(f"Not a row dict: {source_dict!r}")
    expr_map: dict[str, Expr] = {}
    for key, value in source_dict.items():
        expr_map[key] = exprFromData(value, controller)
    return expr_map


def pythonExpressionMap(m: dict[str, Union[str, dict]]
                        ) -> dict[str, PythonExpr]:
    cm: dict[str, PythonExpr] = {}
    for k, v in m.items():
        if k.endswith(".py"):
            k = k.removesuffix(".py")
        cm[k] = PythonExpr.fromData(v)
    return cm


class Updater:
    def __init__(self, var_map: dict[str, Expr] = None,
                 prop_map: dict[str, Expr] = None):
        self.var_map = var_map or {}
        self.var_depends: DependsMap = {}
        self.prop_map = prop_map or {}
        self.prop_depends: DependsMap = {}

    @staticmethod
    def _dependsMap(m: dict[str, Expr]) -> DependsMap:
        deps: dict[str, set[str]] = {}
        for name, expr in m.items():
            for dep_name in expr.depends:
                if dep_name not in deps:
                    deps[dep_name] = set()
                deps[dep_name].add(name)
        return deps

    def updateDependencies(self, obj: QtCore.QObject, env: dict[str, Any],
                           name: str) -> None:
        env = env.copy()
        for var_name in self.var_depends.get(name, ()):
            expr = self.var_map[var_name]
            env[var_name] = expr.evaluate(None, env)

        for prop_name in self.prop_depends.get(name, ()):
            expr = self.prop_map[prop_name]
            value = expr.evaluate(None, env)
            setSettable(obj, prop_name, value)

    def setVariableData(self, var_dict: dict[str, Any],
                        controller: DataController) -> None:
        self.var_map = exprMap(var_dict, controller)
        self.var_depends = self._dependsMap(self.var_map)

    def setPropertyData(self, prop_dict: dict[str, Any],
                        controller: DataController, as_template=False) -> None:
        if as_template:
            pm = pythonExpressionMap(prop_dict)
        else:
            pm = exprMap(prop_dict, controller=controller)
        self.prop_map = pm
        self.prop_depends = self._dependsMap(self.prop_map)

    def addComputedProperty(self, name: str, value: Expr) -> None:
        self.prop_map[name] = value

    def updateObject(self, obj: QtCore.QObject, data: Optional[dict[str, Any]],
                     env: dict[str, Any], extra_env: dict[str, Any] = None
                     ) -> dict[str, JsonValue]:
        from .graphics import core

        var_map = self.var_map
        prop_map = self.prop_map

        if var_map or extra_env:
            env = env.copy()

            if extra_env:
                env.update(extra_env)

            for varname, compvalue in var_map.items():
                env[varname] = compvalue.evaluate(data, env)

            if isinstance(obj, core.Graphic):
                env.update(obj.localEnv())

        if prop_map:
            for propname, compvalue in prop_map.items():
                value = compvalue.evaluate(data, env)
                setSettable(obj, propname, value)

        return env

    def hasValues(self) -> bool:
        return self.hasVariables() or self.hasProperties()

    def hasVariables(self) -> bool:
        return bool(self.var_map)

    def hasProperties(self) -> bool:
        return bool(self.prop_map)


class Models(dict):
    def __getattr__(self, name: str) -> QtCore.QAbstractItemModel:
        return self[name]


class AbstractController(QtCore.QObject):
    def __init__(self, parent: QtCore.QObject = None):
        super().__init__(parent)
        self._root: Optional[core.Graphic] = None
        self._global_env: dict[str, Any] = {}

    def setRoot(self, graphic: core.Graphic) -> None:
        self._root = graphic

    def clear(self) -> None:
        pass

    def prepObject(self, obj: QtCore.QObject, data: dict[str, Any]) -> None:
        raise NotImplementedError

    def globalEnv(self) -> dict[str, Any]:
        return self._global_env.copy()

    def setGlobalEnv(self, env: dict[str, Any]) -> None:
        self._global_env = env

    def updateGlobalEnv(self, env: dict[str, Any]) -> None:
        self._global_env.update(env)


class DataController(AbstractController):
    value_key = ""
    row_key = ""

    def __init__(self):
        super().__init__()
        self.persistent_models = Models()
        self.models = Models()
        self._updaters: dict[int, Updater] = {}
        self._template_updaters: dict[tuple[int, str], Updater] = {}
        self._externals: dict[str, ExternalExpr] = {}
        self._color_policies: dict[str, styling.ColorPolicy] = {}
        self._depends: defaultdict[str, list[tuple[QtCore.QObject, Updater]]] \
            = defaultdict(list)

    def globalEnv(self) -> dict[str, Any]:
        env = super().globalEnv()
        env["models"] = self.models
        return env

    def clear(self) -> None:
        self._updaters.clear()
        self._template_updaters.clear()
        self._depends.clear()
        self.models.clear()
        self.models.update(self.persistent_models)

    def makeExpr(self, name: str, data: Any) -> Expr:
        raise NotImplementedError

    def addExternal(self, name: str, read: Callable, write: Callable = None
                    ) -> None:
        self._externals[name] = ExternalExpr(read, write)

    def externalExpression(self, name: str) -> ExternalExpr:
        return self._externals[name]

    def _makeModel(self, model_data: dict[str, Any], name: str
                   ) -> QtCore.QAbstractTableModel:
        from .models import modelFromData

        if "colors" in model_data:
            color_policy_data = model_data.pop("colors")
            # color_policy = styling.ColorPolicy.fromData(color_policy_data)

        model = modelFromData(model_data, self)
        name = model.objectName() or name
        model.setObjectName(name)

        if name in self.models:
            raise KeyError(f"Duplicate model name {name}")
        self.models[name] = model
        return model

    def _dataProxyFor(self, obj: QtCore.QObject) -> QtCore.QObject:
        from .graphics import core

        checked: list[QtWidgets.QGraphicsItem] = [obj]
        while isinstance(checked[-1], core.Graphic):
            dp = checked[-1].dataProxy()
            if not dp:
                break
            if dp in checked:
                dp_refs = ', '.join(repr(o) for o in checked)
                raise Exception(f"Circular dataProxy refs: {dp_refs}: {dp!r}")
            checked.append(dp)
        return checked[-1]

    def _setObjectModelData(self, data_obj: QtCore.QObject, model_data: Any
                            ) -> None:
        if isinstance(model_data, dict):
            name = f"obj_{data_obj.objectName()}_{id(data_obj)}"
            obj_model = self._makeModel(model_data, name)
        elif isinstance(model_data, str):
            # the value of "model" is the name of a common model
            obj_model = self.models[model_data]
        else:
            raise TypeError(f"Can't use {model_data} as a model")
        data_obj.setModel(obj_model)

    def _setupTemplate(self, obj_id: int, key: str,
                       template_data: dict[str, Any]) -> None:
        updater = Updater()
        updater.setVariableData(template_data.pop("variables", {}), self)
        updater.setPropertyData(template_data.pop("properties", {}), self,
                                as_template=True)
        if updater.hasValues():
            self._template_updaters[obj_id, key] = updater

    def prepObject(self, obj: QtCore.QObject, data: dict[str, Any]) -> None:
        from .graphics.core import Graphic

        # models: dict mapping model names to data models, for shared models
        model_dict = data.pop("models", {})
        if isinstance(model_dict, dict):
            for name, model_data in model_dict.items():
                self._makeModel(model_data, name)
        else:
            raise TypeError("Models key is not a dict")

        # Allow object to provide a "data proxy" that should be used for data
        # related matters. Note that a proxy may have a proxy, so we have to
        # keep chasing the method until it returns None, and also check for
        # reference loops
        orig_obj_id = id(obj)
        data_obj = self._dataProxyFor(obj)
        data_obj_id = id(data_obj)

        # model: a key containing either a string (the name of a shared model),
        # or a data model for local use
        obj_model: Optional[QtCore.QAbstractItemModel] = None
        if "model" in data:
            self._setObjectModelData(data_obj, data.pop("model"))

        updater = Updater()
        updater.setVariableData(data.pop("variables", {}), self)
        updater.setPropertyData(data.pop("properties", {}), self)
        if self.value_key and self.value_key in data:
            jp = data.pop(self.value_key)
            updater.addComputedProperty("value",
                                        self.makeExpr(self.value_key, jp))

        if updater.hasValues():
            self._updaters[orig_obj_id] = updater
            # TODO: for now we just update the entire object when any dependency
            #   changes
            for name in set(updater.var_depends) | set(updater.prop_depends):
                self._depends[name].append((obj, updater))

        # Look for templates
        obj_type = type(data_obj)
        if isinstance(data_obj, Graphic):
            template_keys = obj_type.templateKeys()
            for key in template_keys:
                if key in data:
                    template_data = data.pop(key)
                    setSettable(data_obj, key, template_data)
                    self._setupTemplate(data_obj_id, key, template_data)

        # listen_to = data.pop("listen", None)
        # if isinstance(listen_to, str):
        #     self._subscribers[listen_to].append(obj)
        # elif isinstance(listen_to, (list, tuple)):
        #     for lt in listen_to:
        #         self._subscribers[lt].append(obj)

    def updateDependencies(self, name: str, env: dict[str, JsonValue] = None
                           ) -> None:
        env = env if env is not None else self.globalEnv()
        for obj, updater in self._depends[name]:
            updater.updateDependencies(obj, env, name)

            if isinstance(obj, QtWidgets.QGraphicsItem):
                obj.updateGeometry()
                obj.update()

    def updateFromData(self, data: dict[str, Any], env: dict[str, Any] = None
                       ) -> None:
        from . import models

        root = self._root
        if not root:
            raise Exception("No root item set")

        env = env if env is not None else self.globalEnv()
        for model_name, model in self.models.items():
            # TODO: update the model using the model API?
            if isinstance(model, QtCore.QSortFilterProxyModel):
                model = model.sourceModel()
            if not isinstance(model, models.BaseDataModel):
                raise TypeError(f"Can't update {model} directly")
            model.updateFromData(data, env)

        self.updateObjectFromData(root, data, env)

    def updateObjectFromData(self, obj: QtCore.QObject, data: dict[str, Any],
                             env: dict[str, JsonValue] = None) -> None:
        from .graphics import core

        env = env if env is not None else self.globalEnv()
        updater = self._updaters.get(id(obj))
        if updater:
            extra_env = {}
            if isinstance(obj, core.Graphic):
                data_obj = self._dataProxyFor(obj)
                extra_env["model"] = data_obj.model()
            env = updater.updateObject(obj, data, env, extra_env)

        for child in obj.updateableChildren():
            self.updateObjectFromData(child, data, env)

        if isinstance(obj, QtWidgets.QGraphicsItem):
            obj.updateGeometry()
            obj.update()

    def updateTemplateItemFromEnv(self, key: str, extra_env: dict[str, Any],
                                  obj: QtCore.QObject, item: QtCore.QObject
                                  ) -> None:
        if not obj:
            raise ValueError("No object")
        if not item:
            raise ValueError("No item")

        updater = self._template_updaters.get((id(obj), key))
        if updater:
            updater.updateObject(item, data=None, env=self.globalEnv(),
                                 extra_env=extra_env)

        if isinstance(item, QtWidgets.QGraphicsItem):
            item.updateGeometry()
            item.update()

    def updateItemFromModel(self, model: QtCore.QAbstractItemModel, row: int,
                            obj: QtCore.QObject, item: QtCore.QObject,
                            key="item_template") -> None:
        from .models import ModelRowAdapter
        env = {
            "model": model,
            "row_num": row,
            "item":  ModelRowAdapter(model, row)
        }
        self.updateTemplateItemFromEnv(key, env, obj, item)


def updateSettables(obj: QtCore.QObject, updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        setSettable(obj, key, value)


class JsonPathController(DataController):
    """
    Controller object for updating tile properties based on jsonpaths matched
    against JSON data.
    """

    value_key = "json_path"

    def __init__(self):
        super().__init__()
        self._cache: dict[str, jsonpath.JsonPath] = {}

    def makeExpr(self, name: str, data: Any) -> JsonPathExpr:
        return JsonPathExpr.fromData(data, self._cache)


# class InfoTreeController(DataController):
#     path_key = "info_path"
#
#     def _makeValue(self, data: Any) -> config.ComputedValue:
#         return InfoTreeValue.fromString(data)

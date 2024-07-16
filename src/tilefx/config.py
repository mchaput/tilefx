from __future__ import annotations
import ast
import re
import time
import weakref
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
    from .graphics import core, views


# Type aliases
Scalar = Union[int, float, str]
SetterType = Callable[[QtCore.QObject, Any], None]
ParentSetterType = Callable[[QtCore.QObject, QtCore.QObject, Any], None]
QObjType = type[QtCore.QObject]
DependsMap = dict[str, Collection[str]]
T = TypeVar("T")
Q = TypeVar("Q", bound=type[QtCore.QObject])


def registrar(registry_dict: dict, compile_setters=False):
    def class_wrapper(*names):
        def fn(cls):
            for name in names:
                registry_dict[name] = cls
            if compile_setters:
                compileSettables(cls)
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


class SetterInfo(NamedTuple):
    name: Optional[str]
    converter: Callable
    value_object_type: Optional[type[QtCore.QObject]]
    is_parent_method: bool


setter_lookup: dict[tuple[QObjType, str], SetterType] = {}
# Setter metadata, keyed by the id() of the method
setter_infos: dict[int, SetterInfo] = {}


def settable(name: str = None, *, argtype: type = None,
             converter: Callable = None, convert_each=False,
             is_parent_method=False) -> Callable[[T], T]:
    if name is not None and not isinstance(name, str):
        raise TypeError(f"{name!r} is not a string")
    if argtype is not None and not converter:
        from .converters import converter_registry
        converter = converter_registry.get(argtype)

        if convert_each:
            conv = converter

            def converter(seq: Sequence[Any]) -> Sequence[Any]:
                return [conv(item) for item in seq]

    value_object_type = (
        argtype if argtype and issubclass(argtype, QtCore.QObject) else None
    )

    def decorator(m: T) -> T:
        method_name = m.__name__
        if is_parent_method and not method_name.startswith("setChild"):
            raise NameError(
                f"Parent setter method {method_name} name must start "
                "with 'setChild'"
            )

        key = name or camelToSnake(method_name, drop_set=True)
        # Some "methods" are objects we can't put custom attributes on (ie
        # descriptors), so we have to store the metadata in an indirect lookup
        info = SetterInfo(key, converter, value_object_type, is_parent_method)
        setter_infos[id(m)] = info
        return m

    return decorator


def settersAndInfos(cls: type[QtCore.QObject]
                    ) -> Iterable[tuple[SetterType, SetterInfo]]:
    for name in dir(cls):
        m = getattr(cls, name)
        if info := setter_infos.get(id(m)):
            yield m, info


def findParentSettable(obj: QtCore.QObject, key: str) -> Optional[SetterType]:
    method = setter_lookup[type(obj), key]
    if info := setter_infos.get(id(method)):
        if info.is_parent_method:
            return method


def _findElement(obj: QtCore.QObject, part: str) -> Optional[QtCore.QObject]:
    # For Graphic items, we have a pathElement() method that lets the item
    # "export" names without them being actual child items
    from .graphics import core
    if isinstance(obj, core.Graphic):
        if element := obj.findElement(part):
            return element

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

    # camel_part = snakeToCamel(part)
    # if hasattr(obj, camel_part):
    #     return getattr(obj, camel_part)()


def getSettable(obj_type: type[QtCore.QObject], name: str) -> SetterType:
    key = obj_type, name
    if key in setter_lookup:
        setter = setter_lookup[key]
    elif "." in name:
        # The template can set arbitrary dotted paths that may not be cached yet
        setter = _makePathSetter(name)
        setter_lookup[key] = setter
    else:
        raise KeyError(f"No property {name} on {obj_type}")
    return setter


def setSettable(obj: QtCore.QObject, name: str, value: Any) -> None:
    getSettable(type(obj), name)(obj, value)


def _makePathSetter(path: str) -> SetterType:
    parts = path.split(".")
    elements = parts[:-1]
    key = parts[-1]

    def setter(obj: core.Graphic, value: Any) -> None:
        for name in elements:
            obj = obj.findElement(name)
        m = setter_lookup[type(obj), key]
        m(obj, value)

    return setter


def _makeSetter(fn: SetterType, info: SetterInfo) -> SetterType:
    if info.converter:
        def conv_setter(obj: QtCore.QObject, value: Any) -> None:
            fn(obj, info.converter(value))
        setter = conv_setter
    else:
        setter = fn
    return setter


def _makeQtPropertySetter(prop_name: str) -> SetterType:
    # name_bytes = prop_name.encode("ascii")

    def _qtPropSetter(obj: QtCore.QObject, value: Any) -> None:
        obj.setProperty(prop_name, value)

    return _qtPropSetter


def compileSettables(cls: Q) -> Q:
    from .graphics.core import Graphic

    # Make setters for Qt properties
    if issubclass(cls, QtCore.QObject):
        meta = cls.staticMetaObject
        for i in range(meta.propertyCount()):
            prop = meta.property(i)
            if prop.isWritable():
                prop_name = prop.name()
                snake_name = camelToSnake(prop_name)
                setter_lookup[cls, snake_name] = \
                    _makeQtPropertySetter(prop_name)

    for attr_name in dir(cls):
        m = getattr(cls, attr_name)
        if info := setter_infos.get(id(m)):
            setter_lookup[cls, info.name] = _makeSetter(m, info)

    if issubclass(cls, Graphic):
        aliases = cls.propertyAliases()
        for alias, path in aliases.items():
            if "." in path:
                setter = _makePathSetter(path)
            else:
                setter = setter_lookup[cls, path]
            setter_lookup[cls, alias] = setter

    return cls


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
        if isinstance(depends, str):
            depends = (depends,)
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
            env = env.copy()
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
                row_env = env.copy()
                if bindings:
                    row_env.update(bindings)
                yield RowData(match.value, row_env)
        except Exception as e:
            raise Exception(f"Error while finding with {self.path}: {e}")


class PythonExpr(Expr):
    def __init__(self, expression: Union[str, CodeType], **kwargs):
        super().__init__(**kwargs)
        self.source = ""
        if isinstance(expression, str):
            if not expression:
                raise SyntaxError("Expression cannot be an empty string")
            self.source = expression
            try:
                tree = ast.parse(expression, mode="eval")
            except SyntaxError as e:
                raise SyntaxError(f"{expression!r}: {e}")
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
    def __init__(self, controller: DataController, var_data: dict,
                 prop_data: dict, obj: QtCore.QObject = None,
                 as_template=False):
        var_map = exprMap(var_data, controller) if var_data else {}
        if as_template:
            prop_map = pythonExpressionMap(prop_data)
        else:
            prop_map = exprMap(prop_data, controller=controller)

        # self.visibility_expr = None
        self.visibility_expr: Optional[Expr] = prop_map.pop("visible", None)

        self._object: Optional[weakref.ref[QtCore.QObject]] = \
            weakref.ref(obj) if obj else None
        self.controller = weakref.ref(controller)
        self.var_map: dict[str, Expr] = var_map or {}
        self.prop_map: dict[str, Expr] = prop_map or {}
        self.as_template = as_template

        self.setters: Optional[list[tuple[Expr, SetterType]]] = None
        if obj:
            self._cacheSetters(type(obj))

        self.var_depends = self._dependsMap(self.var_map)
        self.prop_depends = self._dependsMap(self.prop_map)

    def _cacheSetters(self, obj_type: type[QtCore.QObject]) -> None:
        setters = self.setters = []
        for prop_name, expr in self.prop_map.items():
            setter = getSettable(obj_type, prop_name)
            setters.append((expr, setter))

    @staticmethod
    def _dependsMap(m: dict[str, Expr]) -> DependsMap:
        deps: dict[str, set[str]] = {}
        for name, expr in m.items():
            for dep_name in expr.depends:
                if dep_name not in deps:
                    deps[dep_name] = set()
                deps[dep_name].add(name)
        return deps

    def dependsOn(self, name: str) -> bool:
        return name in self.var_depends or name in self.prop_depends

    def updateDependencies(self, data: dict[str, Any], env: dict[str, Any],
                           name: str, obj: QtCore.QObject = None) -> None:
        if not obj:
            if self._object:
                obj = self._object()
            else:
                raise Exception("No object to update dependencies")

        var_depends = self.var_depends.get(name, ())
        if var_depends:
            env = env.copy()
            for var_name in var_depends:
                env[var_name] = self.var_map[var_name].evaluate(data, env)

        for expr, setter in self.setters:
            if name in expr.depends:
                setter(obj, expr.evaluate(data, env))

    def updateObject(self, data: Optional[dict[str, Any]],
                     env: dict[str, Any], extra_env: dict[str, Any] = None,
                     obj: QtCore.QObject = None) -> dict[str, JsonValue]:
        from .graphics import core

        if not obj:
            if self._object:
                obj = self._object()
            else:
                raise Exception("No object to update")

        if self.var_map or extra_env or isinstance(obj, core.Graphic):
            env = env.copy()
            if extra_env:
                env.update(extra_env)

            for varname, compvalue in self.var_map.items():
                env[varname] = compvalue.evaluate(data, env)

            if isinstance(obj, core.Graphic):
                env.update(obj.localEnv())

        if isinstance(obj, core.Graphic) and self.visibility_expr:
            visible = self.visibility_expr.evaluate(data, env)
            obj.setVisible(visible)
            if not visible:
                return {}

        if self.setters is None:
            self._cacheSetters(type(obj))
        for expr, setter in self.setters:
            setter(obj, expr.evaluate(data, env))

        # if prop_map:
        #     for propname, compvalue in prop_map.items():
        #         value = compvalue.evaluate(data, env)
        #         setSettable(obj, propname, value)

        return env


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

    def clearEnv(self) -> None:
        self._global_env.clear()

    def prepObject(self, obj: QtCore.QObject, data: dict[str, Any],
                   name: str = None) -> None:
        raise NotImplementedError

    def globalEnv(self) -> dict[str, Any]:
        return self._global_env.copy()

    def setGlobalEnv(self, env: dict[str, Any]) -> None:
        self._global_env = env.copy()

    def updateGlobalEnv(self, env: dict[str, Any]) -> None:
        self._global_env.update(env)


class DataController(AbstractController):
    value_key = ""
    row_key = ""

    def __init__(self):
        super().__init__()
        self.persistent_models = Models()
        self.shared_item_pools: dict[str, views.DataItemPool] = {}
        self.models = Models()
        self._obj_id_to_pool_name: dict[int, str] = {}
        self._updaters: dict[int, Updater] = {}
        self._template_updaters: dict[tuple[int, str], Updater] = {}
        self._externals: dict[str, ExternalExpr] = {}
        self._color_policies: dict[str, styling.ColorPolicy] = {}

    def globalEnv(self) -> dict[str, Any]:
        env = super().globalEnv()
        env["models"] = self.models
        return env

    def clear(self) -> None:
        super().clear()
        self._updaters.clear()
        self._template_updaters.clear()
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

    @staticmethod
    def _dataProxyFor(obj: QtCore.QObject) -> QtCore.QObject:
        from .graphics.core import dataProxyFor
        return dataProxyFor(obj)

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
        var_data = template_data.pop("variables", None)
        prop_data = template_data.pop("properties", None)
        if prop_data:
            updater = Updater(self, var_data, prop_data, as_template=True)
            self._template_updaters[obj_id, key] = updater

    def prepObject(self, obj: QtCore.QObject, data: dict[str, Any],
                   name: str = None) -> None:
        from .graphics.core import Graphic
        from .graphics.views import DataItemPool

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
        if "model" in data:
            self._setObjectModelData(data_obj, data.pop("model"))

        shared_pool_data = data.pop("shared_item_templates", None)
        if shared_pool_data:
            if isinstance(shared_pool_data, dict):
                for tmpl_name, template_data in shared_pool_data.items():
                    if tmpl_name in self.shared_item_pools:
                        raise Exception(
                            f"Duplicate shared template name: {tmpl_name}"
                        )
                    pool = DataItemPool(tmpl_name)
                    pool.setItemTemplate(template_data)
                    self.shared_item_pools[tmpl_name] = pool
                    self._setupTemplate(-1, tmpl_name, template_data)
            else:
                raise ValueError("shared_item_templates must be a dict")

        var_data = data.pop("variables", None)
        prop_data = data.pop("properties", None)
        if self.value_key and self.value_key in data:
            prop_data["value"] = self.makeExpr(self.value_key,
                                               data.pop(self.value_key))
        if prop_data:
            updater = Updater(self, var_data, prop_data, obj=obj)
            self._updaters[orig_obj_id] = updater

        # Look for templates
        obj_type = type(data_obj)
        if isinstance(data_obj, Graphic):
            template_keys = obj_type.templateKeys()
            for key in template_keys:
                if key in data:
                    template_data = data.pop(key)
                    if isinstance(template_data, str):
                        tmpl_name = template_data
                        if tmpl_name in self.shared_item_pools:
                            pool = self.shared_item_pools[tmpl_name]
                            data_obj.setItemPool(pool)
                            self._obj_id_to_pool_name[data_obj_id] = tmpl_name
                        else:
                            raise KeyError(
                                f"Unkown shared template: {tmpl_name}"
                            )
                    else:
                        setSettable(data_obj, key, template_data)
                        self._setupTemplate(data_obj_id, key, template_data)

        # listen_to = data.pop("listen", None)
        # if isinstance(listen_to, str):
        #     self._subscribers[listen_to].append(obj)
        # elif isinstance(listen_to, (list, tuple)):
        #     for lt in listen_to:
        #         self._subscribers[lt].append(obj)

    def updateDependencies(self, name: str, data: dict[str, Any],
                           env: dict[str, JsonValue] = None) -> None:
        env = env if env is not None else self.globalEnv()
        for updater in self._updaters.values():
            if updater.dependsOn(name):
                updater.updateDependencies(data, env, name)

    def updateModels(self, data: dict[str, Any], env: dict[str, Any] = None,
                     clear_models=False) -> None:
        from . import models
        # t = time.perf_counter()
        for model_name, model in self.models.items():
            # tt = time.perf_counter()
            # TODO: update the model using the model API?
            if isinstance(model, QtCore.QSortFilterProxyModel):
                model = model.sourceModel()
            if not isinstance(model, models.BaseDataModel):
                raise TypeError(f"Can't update {model} directly")
            if clear_models:
                model.clear()
            model.updateFromData(data, env)
            env[model_name] = model
            # print(f"Update model {model.objectName()}: {model.rowCount()} "
            #       f"{time.perf_counter() - tt:0.04f}")
            # if isinstance(model, models.DataModel):
            #     print("rows=", model._rows)
        # print(f"Update models: {time.perf_counter() - t:0.04f}")

    def updateFromData(self, data: dict[str, Any], env: dict[str, Any] = None,
                       clear_models=False) -> None:
        root = self._root
        if not root:
            raise Exception("No root item set")

        env = env if env is not None else self.globalEnv()
        self.updateModels(data, env, clear_models=clear_models)

        for updater in self._updaters.values():
            updater.updateObject(data, env)

    def updateTemplateItemFromEnv(self, obj: QtCore.QObject, template_name: str,
                                  item: QtCore.QObject,
                                  extra_env: dict[str, Any]) -> None:
        if not obj:
            raise ValueError("No object")
        if not item:
            raise ValueError("No item")

        obj_id = id(obj)
        shared_pool_name = self._obj_id_to_pool_name.get(obj_id)
        if shared_pool_name is None:
            tmpl_key = (obj_id, template_name)
        else:
            tmpl_key = (-1, shared_pool_name)

        updater = self._template_updaters.get(tmpl_key)
        if updater:
            updater.updateObject(None, env=self.globalEnv(),
                                 extra_env=extra_env, obj=item)

        if isinstance(item, QtWidgets.QGraphicsItem):
            item.updateGeometry()
            item.update()

    def updateItemFromModel(self, model: QtCore.QAbstractItemModel, row: int,
                            obj: QtCore.QObject, item: QtCore.QObject,
                            template_name="item_template",
                            extra_env: dict[str, Any] = None) -> None:
        from .models import ModelRowAdapter
        env = {
            "model": model,
            "row_num": row,
            "item":  ModelRowAdapter(model, row)
        }
        if extra_env:
            env.update(extra_env)
        self.updateTemplateItemFromEnv(obj, template_name, item, env)


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

from __future__ import annotations
import enum
from typing import (TYPE_CHECKING, cast, Any, Callable, Collection, Iterable,
                    NamedTuple, Optional, Sequence, Union)

from PySide2 import QtCore
from PySide2.QtCore import Qt

from . import config, converters, themes, util
from .config import Expr


# Type aliases
Scalar = Union[int, float, str]


class DataError(Exception):
    pass


class NoRoleError(DataError):
    pass


class Hilite(enum.Enum):
    none = enum.auto()
    on = enum.auto()
    off = enum.auto()


def _fractions(values: Sequence[float], total: float = None,
               fn: Callable[[Iterable[float]], float] = sum) -> Sequence[float]:
    if values:
        if total is None:
            total = fn(values)
        if total:
            return [v / total for v in values]
    return values


class Normalization:
    def __init__(self, total: float = 1.0):
        self._total = total

    def __repr__(self):
        return f"<{type(self).__name__}>"

    def normalized(self, values: Sequence[float]) -> Sequence[float]:
        raise NotImplementedError

    def total(self) -> float:
        return self._total

    def setTotal(self, total: float):
        self._total = total


class FractionOfNumber(Normalization):
    def __repr__(self):
        return f"<{type(self).__name__} {self._total}>"

    def normalized(self, values: Sequence[float]) -> Sequence[float]:
        return _fractions(values, self._total)


class FractionOfSum(Normalization):
    def normalized(self, values: Sequence[float]) -> Sequence[float]:
        return _fractions(values)


class FractionOfMax(Normalization):
    def normalized(self, values: Sequence[float]) -> Sequence[float]:
        return _fractions(values, fn=max)


class Percentages(Normalization):
    def normalized(self, values: Sequence[float]) -> Sequence[float]:
        return [v / 100.0 for v in values]


class SmartNormalization(Normalization):
    def __repr__(self):
        return f"<{type(self).__name__} {self._total}>"

    def normalized(self, values: Sequence[float]) -> Sequence[float]:
        if self._total > 1.0:
            return [v / self._total for v in values]
        elif all(v <= 1.0 for v in values):
            return values
        else:
            return _fractions(values)


class DataID(NamedTuple):
    column: int
    role: int


class RowData(NamedTuple):
    data: int|float|str|dict
    env: dict[str, Any]


class RowFactory:
    def __init__(self):
        self._column_count = 0
        self._var_map: dict[str, Expr] = {}
        self._expr_map: dict[DataID, Expr] = {}
        self._unique_data_id: Optional[DataID] = None

    def columnCount(self) -> int:
        return self._column_count

    def setColumnCount(self, count: int) -> None:
        self._column_count = count

    def variableMap(self) -> dict[str, Expr]:
        return self._var_map

    def setVariableMap(self, var_map: dict[str, Expr]) -> None:
        self._var_map = var_map

    def exprMap(self) -> dict[DataID, Expr]:
        return self._expr_map

    def setExprMap(self, expr_map: dict[DataID, Expr]) -> None:
        self._expr_map = expr_map
        max_col = max(dataid.column for dataid in expr_map) if expr_map else -1
        if max_col + 1 > self.columnCount():
            self.setColumnCount(max_col + 1)

    def uniqueDataID(self) -> Optional[DataID]:
        return self._unique_data_id

    def setUniqueDataID(self, unique_id: DataID) -> None:
        self._unique_data_id = unique_id

    def findRowDatas(self, data: dict[str, Any], env: dict[str, Any]
                     ) -> Iterable[RowData]:
        raise NotImplementedError

    def _addVariables(self, data: dict[str, Any], env: dict[str, Any]
                      ) -> None:
        for var_name, expr in self._var_map.items():
            env[var_name] = expr.evaluate(data, env)

    def generateRows(self, data: dict[str, Any], env: dict[str, Any],
                     unique_id: Optional[DataID]
                     ) -> Iterable[dict[DataID, Scalar]]:
        unique_id = self.uniqueDataID()
        expr_map = self.exprMap()
        unique_val_set: set[Scalar] = set()

        for row_data, row_env in self.findRowDatas(data, env):
            row: dict[DataID, Scalar] = {}
            if isinstance(row_data, dict):
                row_env.update(row_data)
            row_env["obj"] = row_data

            self._addVariables(data, row_env)

            # Compute the key value first, and use it to compute the row color,
            # check for uniqueness, etc.
            if unique_id and unique_id in expr_map:
                unique_val = expr_map[unique_id].evaluate(row_data.data,
                                                          row_data.env)
                if not isinstance(unique_val, (int, float, str)):
                    raise ValueError(f"Can't use {unique_val!r} as key value")
                if unique_val in unique_val_set:
                    raise ValueError(f"Key value is not unique: {unique_val!r}")
                unique_val_set.add(unique_val)
                # Add any variables to the env that depend on the key value
                row_data.env["unique_id"] = unique_val

            for value_id, computed in expr_map.items():
                if unique_id and value_id == unique_id:
                    # If this is the unique value, we already did it above
                    continue
                value = computed.evaluate(row_data, row_env)
                row[value_id] = value

            yield row


class NullRowFactory(RowFactory):
    def columnCount(self) -> int:
        return 0

    def setColumnCount(self, count: int) -> None:
        raise Exception("Operation on null row factory")

    def setExprMap(self, expr_map: dict[DataID, Expr]) -> None:
        raise Exception("Operation on null row factory")

    def setUniqueDataID(self, unique_id: DataID) -> None:
        raise Exception("Operation on null row factory")

    def generateRows(self, data: dict[str, Any], env: dict[str, Any],
                     unique_id: Optional[DataID]
                     ) -> Iterable[dict[DataID, Scalar]]:
        return ()


class ExprRowFactory(RowFactory):
    def __init__(self, expr: config.Expr):
        super().__init__()
        if isinstance(expr, config.JsonPathExpr):
            expr.all_values = True
        self.expr = expr

    def __repr__(self):
        return f"<{type(self).__name__} {self.expr!r}>"

    def findRowDatas(self, data: dict[str, Any], env: dict[str, Any]
                     ) -> Iterable[RowData]:
        return self.expr.findRowDatas(data, env)


class LiteralRowFactory(RowFactory):
    def __init__(self,):
        super().__init__()
        self.row_list: list[dict[DataID, Union[Expr, Scalar]]] = []

    def addRows(self, rows: Sequence[dict[DataID, Union[Expr, Scalar]]]
                ) -> None:
        cc = self.columnCount()
        for row in rows:
            max_col = max(dataid.column for dataid in row)
            if max_col + 1 > cc:
                cc = max_col + 1
            self.row_list.append(row)
        self.setColumnCount(cc)

    def generateRows(self, data: dict[str, Any], env: dict[str, Any],
                     unique_id: Optional[DataID]
                     ) -> Iterable[tuple[dict[DataID, Scalar]]]:
        env = env.copy()
        self._addVariables(data, env)
        for row_dict in self.row_list:
            row: dict[DataID, Scalar] = {}
            for data_id, v in row_dict.items():
                if isinstance(v, Expr):
                    value = v.evaluate(data, env)
                else:
                    value = v
                row[data_id] = value
            yield row


class ConcatenatedRowFactory(RowFactory):
    def __init__(self, factory1: RowFactory, factory2: RowFactory):
        super().__init__()
        self.factory1 = factory1
        self.factory2 = factory2

    def generateRows(self, data: dict[str, Any], env: dict[str, Any],
                     unique_id: Optional[DataID]
                     ) -> Iterable[tuple[dict[DataID, Scalar]]]:
        if unique_id:
            # Eliminate rows with duplicate values for the unique key
            seen_keys = set()
            for row in self.factory1.generateRows(data, env, unique_id):
                seen_keys.add(row[unique_id])
                yield row
            for row in self.factory2.generateRows(data, env, unique_id):
                if row[unique_id] in seen_keys:
                    continue
                yield row
        else:
            yield from self.factory1.generateRows(data, env, unique_id)
            yield from self.factory2.generateRows(data, env, unique_id)


def _roleItems(model: QtCore.QAbstractItemModel) -> Iterable[tuple[int, str]]:
    for role_num, role_qbytes in model.roleNames().items():
        role_str = bytes(role_qbytes).decode("utf-8")
        yield role_num, role_str


def _getRoleNumber(model: QtCore.QAbstractItemModel, role: Union[int, str],
                   create=False) -> int:
    if isinstance(role, (int, Qt.ItemDataRole)):
        return role
    if not isinstance(role, str):
        raise TypeError(f"Can't convert {role!r} to role")
    if role.isdigit():
        return int(role)

    if isinstance(model, DataModel):
        try:
            return model.roleNumber(role)
        except NoRoleError:
            # Fall through to below in where we either handle create=True or
            # re-raise the error
            pass
    else:
        for role_num, role_name in _roleItems(model):
            if role == role_name:
                return role_num

    if create:
        if isinstance(model, DataModel):
            return model.addCustomRole(role)
        else:
            raise TypeError(f"Can't create new role on {model!r}")

    role_names = ", ".join(name for _, name in _roleItems(model))
    raise NoRoleError(f"No role {role!r} in {model!r} ({role_names})")


def specToDataID(model: QtCore.QAbstractItemModel,
                 spec: Union[str, tuple[int, str], DataID],
                 create=False) -> DataID:
    # A DataID is just a tuple of column number and role, to index into a row
    # in a QAbstractItemModel. The user can specify a DataID as a string like
    # "<column_int>.<role>" where role can be a role name or int, or just
    # "<role>" (where the column is assumed to be 0).
    if isinstance(spec, DataID):
        return spec
    if isinstance(spec, tuple):
        column = int(spec[0])
        role = _getRoleNumber(model, spec[1], create=create)
    elif isinstance(spec, str):
        if "." in spec:
            col_str, role_str = spec.split(".", 1)
            column = int(col_str) if col_str else 0
            role = _getRoleNumber(model, role_str, create=create)
        elif spec.isdigit():
            column = int(spec)
            role = Qt.DisplayRole
        else:
            # If there's no dot in the string, assume it's just a role name
            column = 0
            role = _getRoleNumber(model, spec, create=create)
    else:
        raise TypeError(f"Can't convert {spec!r} to DataID")

    return DataID(column, role)


def dataIDToSpec(model: QtCore.QAbstractItemModel, data_id: DataID) -> str:
    # Only use this for debugging
    spec = "?"
    for role_num, name_qbytes in model.roleNames().items():
        if role_num == data_id.role:
            spec = bytes(name_qbytes).decode("utf-8")
            break
        else:
            raise Exception(f"No name for role {role_num} in {model}")
    col = data_id.column
    if col != 0:
        spec = f"{col}.{spec}"
    return spec


class ColorMap:
    def __init__(self):
        self._colors = tuple(themes.default_chart_colors)
        self._overrides: dict[Union[str, int, float], converters.ColorSpec] = {}
        self._map: dict[Union[str, int, float], converters.ColorSpec] = {}
        self._prev_map: dict[Union[str, int, float], converters.ColorSpec] = {}
        self._i = 0

    def reset(self) -> None:
        self._prev_map = self._map
        self._map = {}
        self._i = 0

    def setOverrides(self, mapping: dict[Union[str, int], converters.ColorSpec]
                     ) -> None:
        self._overrides = mapping.copy()

    def setColors(self, colors: Sequence[converters.ColorSpec]) -> None:
        self._colors = tuple(colors)

    def addKey(self, key: Scalar) -> converters.ColorSpec:
        if key in self._overrides:
            color = self._overrides[key]
        elif key in self._prev_map:
            color = self._prev_map[key]
        else:
            color = self._colors[self._i]
            self._i += 1
            if self._i >= len(self._colors):
                self._i = 0
        self._map[key] = color
        return color

    def colorForKey(self, key: Union[str, int, float]) -> converters.ColorSpec:
        if key not in self._map:
            self.addKey(key)
        return self._map.get(key, "black")


def modelFromData(data: dict[str, Any], controller: config.DataController,
                  parent: QtCore.QObject = None) -> QtCore.QAbstractItemModel:
    type_name = data.pop("type", None)
    sorted_by = data.pop("sorted_by", None)
    sort_order = data.pop("sort_order", None)

    # Other model types?
    model = DataModel.fromData(data, parent=parent, controller=controller)

    if sorted_by:
        sort_key = model.toDataID(sorted_by)
        proxy = QtCore.QSortFilterProxyModel(parent=parent)
        proxy.setSortRole(sort_key.role)
        proxy.sort(sort_key.column)
        proxy.setDynamicSortFilter(True)
        proxy.setSourceModel(model)
        model = proxy

    return model


class BaseDataModel(QtCore.QAbstractTableModel):
    NoUniqueID = object()
    UniqueIDRole = Qt.UserRole
    MeasurementRole = Qt.UserRole + 1
    CustomRoleBase = Qt.UserRole + 2

    def __init__(self, parent: QtCore.QObject = None):
        super().__init__(parent)
        self._rows: list[dict[DataID, Any]] = []
        self._role_lookup: dict[str, int] = {}
        self._next_custom_role = self.CustomRoleBase
        self._spec_cache: dict[int | str, DataID] = {}
        self._column_count = 0
        self._unique_data_id: Optional[DataID] = None

        for role_num, name_qbytes in super().roleNames().items():
            self._role_lookup[bytes(name_qbytes).decode("utf-8")] = role_num

    def rowCount(self, parent=None) -> int:
        return len(self._rows)

    def rowObject(self, row_num: int) -> dict[DataID, Any]:
        return self._rows[row_num]

    def allRowObjects(self) -> Iterable[dict[DataID, Any]]:
        return iter(self._rows)

    def addCustomRole(self, name: str, role_number: int = None) -> int:
        if role_number is None:
            role_number = self.CustomRoleBase + self._next_custom_role
            self._next_custom_role += 1
        self._role_lookup[name] = role_number
        return role_number

    def setValue(self, row: int, spec: str | DataID, value: Any) -> None:
        data_id = self.toDataID(spec)
        index = self.index(row, data_id.column)
        self.setData(index, value, role=data_id.role)

    def roleNumber(self, role_name: str) -> int:
        try:
            return self._role_lookup[role_name]
        except KeyError:
            raise NoRoleError(f"No role {role_name!r} in {self!r}")

    def roleNames(self) -> dict[int, bytes]:
        name_map = super().roleNames().copy()
        for name, role_num in self._role_lookup.items():
            name_map[role_num] = QtCore.QByteArray(name.encode("ascii"))
        return name_map

    def roleNumberToName(self, role_num: int) -> str:
        num_to_name = util.invertedDict(self._role_lookup)
        return num_to_name[role_num]

    def dataIDtoSpec(self, data_id: DataID) -> str:
        role_name = self.roleNumberToName(data_id.role)
        return f"{data_id.column}.{role_name}"

    def toDataID(self, spec: str | DataID) -> DataID:
        if spec in self._spec_cache:
            return self._spec_cache[spec]
        else:
            data_id = specToDataID(self, spec)
            if data_id is not None:
                self._spec_cache[spec] = data_id
            return data_id

    def uniqueDataID(self) -> Optional[DataID]:
        return self._unique_data_id

    def setUniqueDataID(self, spec: str | DataID) -> None:
        unique_id = self.toDataID(spec)
        self._unique_data_id = unique_id

    def clear(self) -> None:
        self.beginResetModel()
        self._rows.clear()
        self.endResetModel()
    def updateFromData(self, data: dict[str, Any], env: dict[str, Any]) -> None:
        raise NotImplementedError


def orderingFromList(values: Sequence[Any], unique_id: DataID
                     ) -> Callable[[dict[DataID, Any]], int]:
    def _ordering(row: dict[DataID, Any]) -> int:
        if unique_id in row:
            try:
                return values.index(row[unique_id])
            except ValueError:
                pass
        return len(values)
    return _ordering


class DataModel(BaseDataModel):
    def __init__(self, parent: QtCore.QObject = None):
        super().__init__(parent)
        self._debug_rows = False
        self._row_factory: RowFactory = NullRowFactory()
        self._color_data_id = DataID(0, Qt.DecorationRole)
        self._color_map = ColorMap()
        self._ordering_fn: Optional[Callable] = None
        self._sort_by: Optional[DataID] = None
        self._ignored_keys: Collection[int | str] = ()

    @classmethod
    def fromData(cls, data: dict[str, Any], controller: config.DataController,
                 parent: QtCore.QObject = None) -> DataModel:
        model = cls(parent=parent)
        model.configureFromData(data, controller)
        return model

    def colorMap(self) -> ColorMap:
        return self._color_map

    def columnCount(self, parent=None) -> int:
        if self._column_count:
            return self._column_count
        else:
            return self._row_factory.columnCount()

    def setColumnCount(self, count: int) -> None:
        self._column_count = count

    def computedForDataID(self, spec: str | DataID) -> Expr:
        data_id = self.toDataID(spec)
        return self._data_map[data_id]

    def colorDataID(self) -> Optional[DataID]:
        return self._color_data_id

    def setColorDataID(self, spec: str | DataID) -> None:
        color_data_id = self.toDataID(spec)
        self._color_data_id = color_data_id

    def uniqueIDForRow(self, row_num: int) -> Scalar:
        row = self._rows[row_num]
        if self._unique_data_id:
            return row[self._unique_data_id]
        else:
            return row_num

    def rowNumberForUniqueID(self, key: Any) -> int:
        unique_id = self._unique_data_id
        # Just does a linear search because I don't want to pay the cost of
        # updating a key->row lookup dict. Don't call this in a tight loop!
        for i, row in enumerate(self._rows):
            if row.get(unique_id) == key:
                return i

        return -1

    def _configureFromRowData(self, data: dict[str, Any]) -> None:
        row_datas = data.pop("rows")
        if not isinstance(row_datas, (list, tuple)):
            raise TypeError(f"Can't use {row_datas!r} as a list of row data")
        for row_data in row_datas:
            if not isinstance(row_data, dict):
                raise TypeError(f"Can't use {row_data!r} as a row dict")
            row: dict[DataID, Scalar] = {}
            for k, v in row_data.items():
                data_id = specToDataID(self, k, create=True)
                row[data_id] = v
            self._rows.append(row)

    def _configureColorMap(self, data: dict[str, Any]) -> None:
        color_map = self.colorMap()
        row_colors = data.pop("row_colors", None)
        if row_colors:
            if isinstance(row_colors, (list, tuple)):
                color_map.setColors(row_colors)
            else:
                raise TypeError(f"Not a list: {row_colors!r}")

        key_color_map = data.pop("key_color_map", None)
        if key_color_map:
            if isinstance(key_color_map, dict):
                color_map.setOverrides(key_color_map)
            else:
                raise TypeError(f"Not a map: {key_color_map!r}")

    def _exprMap(self, value_map: dict[str, Union[dict, Expr, Scalar]],
                 controller: config.DataController,
                 allow_literals=False) -> dict[DataID, Union[Expr, Scalar]]:
        # value_map is a user-set dict mapping specs (e.g. "name") to
        # expression configs. config.valueMap() turns that into a dict
        # mapping spec strings to Expr instances.
        spec_map = config.exprMap(value_map, controller,
                                  allow_literals=allow_literals)
        # The we use specToDataID() to turn the spec string keys
        # (e.g. "name") into DataIDs (tuples of column and role numbers)
        # for use with the QAbstractItemModel API. Note that
        # specToDataID() with create=True also registers the column/role
        # corresponding to each spec with this model
        expr_map = {specToDataID(self, k, create=True): v
                    for k, v in spec_map.items()}
        return expr_map

    def setKeyOrdering(self, ordered_keys: Sequence[str | int]) -> None:
        self._ordering_fn = orderingFromList(ordered_keys, self.uniqueDataID())

    def setSortByDataID(self, data_id: DataID) -> None:
        self._sort_by = data_id

    def setIgnoredKeys(self, ignored_keys: Collection) -> None:
        self._ignored_keys = ignored_keys

    def configureFromData(self, data: dict[str, Any],
                          controller: config.DataController) -> None:
        original = data
        data = data.copy()
        self.beginResetModel()
        try:
            self._rows.clear()
            self._debug_rows = data.pop("debug_rows", False)
            expr_map: Optional[dict[DataID, Expr]] = None

            model_name = data.pop("name", None)
            if isinstance(model_name, str):
                self.setObjectName(model_name)

            # The value_map is a dict mapping value specs (e.g. "name") to
            # expressions to compute those values for each row
            value_map = data.pop("value_map", None)
            if isinstance(value_map, dict):
                expr_map = self._exprMap(value_map, controller)
            elif value_map is not None:
                raise TypeError(f"Value map {value_map} is not a dict")

            if "rows" not in data:
                raise KeyError(f"No 'rows' key found in model config: {data}")
            rows = data.pop("rows")
            if isinstance(rows, (str, dict)):
                expr = config.exprFromData(rows, controller)
                factory = ExprRowFactory(expr)
            elif isinstance(rows, (list, tuple)):
                factory = LiteralRowFactory()
                factory.addRows([
                    self._exprMap(row_dict, controller, allow_literals=True)
                    for row_dict in rows
                ])
            else:
                raise TypeError(f"Not a valid row factory: {rows}")

            var_data = data.pop("variables", None)
            if isinstance(var_data, dict):
                var_map = config.exprMap(var_data, controller)
                factory.setVariableMap(var_map)

            if expr_map:
                factory.setExprMap(expr_map)
            self._row_factory = factory

            # Spec for the row value that should be considered the row's unique
            # key
            unique_id: Optional[str] = data.pop("unique_id", None)
            if unique_id is not None:
                self.setUniqueDataID(unique_id)

            # If the user specifies a color data ID, the model will fill in that
            # value with a row color from the color map
            color_id: Optional[str] = data.pop("color_id", None)
            if color_id is not None:
                self.setColorDataID(color_id)

            # Use various keys in the data to configure the row color map
            self._configureColorMap(data)

            key_order = data.pop("key_order", None)
            if isinstance(key_order, (list, tuple)):
                self.setKeyOrdering(key_order)
            elif key_order is not None:
                raise TypeError(f"Can't use {key_order} as key order")

            ignore_keys = data.pop("ignore_keys", ())
            if isinstance(ignore_keys, (list, tuple, set, dict, frozenset)):
                self.setIgnoredKeys(set(ignore_keys))
            elif ignore_keys is not None:
                raise TypeError(f"Can't use {ignore_keys} as ignore key set")

            # The previous steps should have popped known keys out of the dict,
            # so if there are any left they are errors
            if data:
                unknown_keys = ", ".join(data)
                raise KeyError(f"Unknown model properties: {unknown_keys} in {original}")
        finally:
            self.endResetModel()

    def updateFromData(self, data: dict[str, Any], env: dict[str, Any]) -> None:
        color_map = self.colorMap()
        color_map.reset()
        unique_id = self.uniqueDataID()
        color_id = self.colorDataID()
        ignored_keys = self._ignored_keys

        new_rows: list[dict[DataID, Scalar]] = []
        for row in self._row_factory.generateRows(data, env, unique_id):
            if unique_id and row.get(unique_id) in ignored_keys:
                continue

            # If we have a unique DataID and a color DataID, and this row has
            # the key value but not a color value already, supply a color
            # from the color map
            if (unique_id and color_id and
                    unique_id in row and color_id not in row):
                row[color_id] = color_map.colorForKey(row[unique_id])
            new_rows.append(row)

        if self._ordering_fn:
            new_rows.sort(key=self._ordering_fn)

        if unique_id:
            self._updateUsingUniqueID(new_rows)
        else:
            self._resetRows(new_rows)

    def _makeUniqueIDMap(self, rows: list[dict[DataID, Any]]
                         ) -> Optional[dict[int|float|str, int]]:
        unique_id = self.uniqueDataID()
        new_map: dict[int|float|str, int] = {}
        for i, row in enumerate(rows):
            v = row[unique_id]
            if v in new_map:
                spec = self.dataIDtoSpec(unique_id)
                raise Exception(f"Unique values {spec} not unique "
                                f"in {self.objectName()}: {v!r}")
            new_map[v] = i
        return new_map

    def _updateUsingUniqueID(self, new_rows: list[dict[DataID, Any]]) -> bool:
        old_row_count = len(self._rows)
        old_map = self._makeUniqueIDMap(self._rows)
        new_map = self._makeUniqueIDMap(new_rows)
        old_unique_set = set(old_map)
        new_unique_set = set(new_map)
        # stable_keys = new_keyset & old_keyset
        # if len(stable_keys) < self.rowCount() * 0.1:
        #     return False

        removed_unqiues = old_unique_set - new_unique_set
        if removed_unqiues:
            self._removeRowsByUniqueID(removed_unqiues, old_map)

        inserted_uniques = new_unique_set - old_unique_set
        if inserted_uniques:
            self._insertRowsByUniqueID(inserted_uniques, new_rows, new_map)

        if self.rowCount() != len(new_rows):
            raise Exception(f"Row count mismatch init={old_row_count} "
                            f"inserted={len(inserted_uniques)} "
                            f"removed={len(removed_unqiues)} "
                            f"current={self.rowCount()} new={len(new_rows)}")
        self._updateRowData(new_rows)
        self._rows = new_rows
        return True

    def _removeRowsByUniqueID(self, removed: Collection[int | float | str],
                              old_map: dict[int | float | str, int]) -> None:
        # Remove rows in reverse order so the indexes don't change
        removed_rows = sorted((old_map[k] for k in removed),
                              reverse=True)
        i = 0
        while i < len(removed_rows):
            first = last = removed_rows[i]
            i += 1
            while i < len(removed_rows) and removed_rows[i] == first - 1:
                first -= 1
                del removed_rows[i]
            self.beginRemoveRows(QtCore.QModelIndex(), first, last)
            del self._rows[first:last + 1]
            self.endRemoveRows()

    def _insertRowsByUniqueID(self, inserted: Collection[int | float | str],
                              new_rows: list[dict[DataID, Any]],
                              new_map: dict[int | float | str, int]) -> None:
        # Insert rows in reverse order so the indexes don't change
        inserted_rows = sorted((new_map[k] for k in inserted),
                               reverse=True)
        i = 0
        while i < len(inserted_rows):
            first = last = inserted_rows[i]
            i += 1
            while i < len(inserted_rows) and inserted_rows[i] == first - 1:
                first -= 1
                del inserted_rows[i]
            self.beginInsertRows(QtCore.QModelIndex(), first, last)
            self._rows[first:first] = new_rows[first:last + 1]
            self.endInsertRows()

    def _resetRows(self, new_rows: list[dict[DataID, Any]]) -> None:
        self.beginResetModel()
        self._rows = new_rows
        self.endResetModel()

    def _emitRowsChanged(self, first: int, last: int) -> None:
        assert last >= 0
        index1 = self.index(first, 0)
        index2 = self.index(last, self.columnCount() - 1)
        self.dataChanged.emit(index1, index2)

    def _updateRowData(self, new_rows: list[dict[DataID, Any]],
                       start=0, end=None) -> None:
        current_rows = self._rows
        end = len(new_rows) if end is None else end

        dc_first = dc_last = None
        for row in range(start, end):
            values = new_rows[row]
            if values != current_rows[row]:
                current_rows[row] = values
                if dc_last is None:
                    dc_first = dc_last = row
                elif row == dc_last + 1:
                    dc_last += 1
                else:
                    self._emitRowsChanged(dc_first, dc_last)
                    dc_first = dc_last = row

        if dc_last is not None:
            self._emitRowsChanged(dc_first, dc_last)

    def insertRows(self, row: int, count: int, parent: QtCore.QModelIndex = None
                   ) -> None:
        if parent and parent.isValid():
            raise ValueError("Model does not support hierarchy")
        self.beginInsertRows(QtCore.QModelIndex(), row, row + count)
        to_insert = [{} for _ in range(count)]
        self._rows[row:row] = to_insert
        self.endInsertRows()

    def insertRow(self, row: int, parent: QtCore.QModelIndex = ...) -> None:
        self.insertRows(row, 1)

    def data(self, index: QtCore.QModelIndex, role=Qt.DisplayRole) -> Any:
        row_number = index.row()
        col_number = index.column()
        if row_number < 0 or row_number >= self.rowCount():
            return
        data_id = DataID(col_number, role)
        row = self._rows[row_number]

        if role == self.UniqueIDRole:
            unqiue_id = self.uniqueDataID()
            if not unqiue_id:
                return self.NoUniqueID
            return row[unqiue_id]

        elif data_id == self._color_data_id and data_id not in row:
            color_map = self._color_map
            unique_value = self.uniqueIDForRow(row_number)
            return color_map.colorForKey(unique_value)

        return row.get(data_id)

    def setData(self, index: QtCore.QModelIndex, value: Any, role=0) -> None:
        row_number = index.row()
        if row_number >= self.rowCount() or row_number < 0:
            return
        row = self._rows[row_number]
        data_id = DataID(index.column(), role)
        row[data_id] = value
        self.dataChanged.emit(index, index, (role,))


class ModelRowAdapter:
    def __init__(self, model: DataModel, row=0):
        self.row = row
        self.model = model

    def __len__(self) -> int:
        return self.model.rowCount()

    def __getitem__(self, spec: Union[str, tuple[int, str]]) -> Any:
        col, role = specToDataID(self.model, spec)
        model = self.model
        return model.index(self.row, col).data(role)

    def __getattr__(self, name: str) -> Any:
        col, role = specToDataID(self.model, name)
        model = self.model
        return model.index(self.row, col).data(role)

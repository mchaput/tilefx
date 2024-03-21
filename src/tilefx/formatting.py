# coding=utf-8
from __future__ import annotations

import dataclasses
import enum
import math
import pathlib
import re
from datetime import datetime, timedelta
from typing import (cast, Any, Callable, Dict, Literal, Sequence, Tuple,
                    Type, Union)

from .config import registrar, setSettable, settable


alnum_expr = re.compile(r"\d+([.]\d+)?|\w+")

TierList = Sequence[Tuple[int, str]]

formatter_class_registery: Dict[str, Type[NumberFormatter]] = {}
formattertype = registrar(formatter_class_registery)

LIGHT_WEIGHT = 400
NORMAL_WEIGHT = 600
BOLD_WEIGHT = 700


class NumberType(enum.Enum):
    normal = enum.auto()
    empty = enum.auto()
    integer = enum.auto()
    weird = enum.auto()
    oversized = enum.auto()
    error = enum.auto()


class BriefMode(enum.Enum):
    never = enum.auto()
    always = enum.auto()
    auto = enum.auto()


class FormattedValue:
    def __str__(self):
        return self.plainText()

    def plainText(self) -> str:
        raise NotImplementedError

    def html(self) -> str:
        raise NotImplementedError


@dataclasses.dataclass
class FormattedNumber(FormattedValue):
    original: Union[int, float]
    text: str
    fraction: str = ""
    type: NumberType = NumberType.normal
    prefix: str = ""
    suffix: str = ""
    brief: bool = False
    whole_weight: int | str = BOLD_WEIGHT
    fraction_weight: int | str = LIGHT_WEIGHT

    def plainText(self) -> str:
        return "".join((self.prefix, self.text, self.fraction, self.suffix))

    def html(self) -> str:
        ww = self.whole_weight
        fw = self.fraction_weight
        if "e" in self.text:
            return markup_sci(self.text)

        html = f"<span style='font-weight: {ww}'>{self.text}</span>"
        if self.prefix:
            html = f"<span>{self.prefix}</span>{html}"
        if self.fraction:
            html = f"{html}<span style='font-weight: {fw}'>{self.fraction}"
        if self.suffix:
            html = f"{html}{abbr(self.suffix)}"
        return html

    def main(self) -> str:
        return "".join((self.text, self.fraction))


@dataclasses.dataclass
class FormattedDuration(FormattedNumber):
    whole_weight: int = BOLD_WEIGHT
    fraction_weight: int = LIGHT_WEIGHT
    decimal_places: int = 1
    auto_decimal: int = 1
    long: bool = False

    def __str__(self) -> str:
        return self.plainText()

    def plainText(self) -> str:
        return format_duration(self.original, markup=False,
                               decimal_places=self.decimal_places,
                               auto_decimal=self.auto_decimal,
                               long=self.long)

    def html(self) -> str:
        return format_duration(self.original, markup=True,
                               decimal_places=self.decimal_places,
                               auto_decimal=self.auto_decimal,
                               whole_weight=self.whole_weight,
                               fraction_weight=self.fraction_weight,
                               long=self.long)


# These must be in reverse order of magnitude
NUMBER_TIERS: TierList = (
    (1000 ** 3, "B"),
    (1000 ** 2, "M"),
    (1000 ** 1, "K")
)
MEMORY_TIERS: TierList = (
    (1024 ** 4, "TiB"),
    (1024 ** 3, "GiB"),
    (1024 ** 2, "MiB"),
    (1024 ** 1, "KiB")
)
DISK_TIERS: TierList = (
    (1000 ** 4, "TB"),
    (1000 ** 3, "GB"),
    (1000 ** 2, "MB"),
    (1000 ** 1, "KB")
)


def formatterFromData(data: Dict[str, Any]) -> NumberFormatter:
    if isinstance(data, str):
        data = {"type": data}
    if not isinstance(data, dict):
        raise TypeError(data)

    # Make a copy of the data dict so we can pop keys off and not affect
    # the caller's object
    data = data.copy()
    typename = data.pop("type", "number")
    cls = formatter_class_registery[typename]
    return cls.fromData(typename, data)


def briefModeConverter(value: Union[bool, Literal["always", "never", "auto"]]
                       ) -> BriefMode:
    if value == "always":
        return BriefMode.always
    elif value == "never":
        return BriefMode.never
    elif value == "auto":
        return BriefMode.auto
    elif isinstance(value, BriefMode):
        return value
    elif value:
        return BriefMode.always
    else:
        return BriefMode.never


@formattertype("number", "brief", "memory", "bytes", "disk")
class NumberFormatter:
    def __init__(self, digits=-1, decimal_places=2, auto_decimal=1,
                 brief_mode=BriefMode.never, tiers=NUMBER_TIERS):
        self._digits = digits
        self._places = decimal_places
        self._auto_decimal = auto_decimal
        self._briefmode = brief_mode
        self._briefcut = 10000
        self._tiers = tiers
        self._whole_weight = BOLD_WEIGHT
        self._fraction_weight = LIGHT_WEIGHT

    @classmethod
    def fromData(cls, typename: str, data: Dict[str, Any]) -> NumberFormatter:
        obj: NumberFormatter = cls()

        briefmode = BriefMode.never
        tiers = NUMBER_TIERS
        if typename == "brief":
            briefmode = BriefMode.always
        elif typename == "memory":
            briefmode = BriefMode.auto
            tiers = MEMORY_TIERS
        elif typename == "bytes" or typename == "disk":
            briefmode = BriefMode.auto
            tiers = DISK_TIERS
        obj.setBriefMode(briefmode)
        obj.setTiers(tiers)

        for key, value in data.items():
            setSettable(obj, key, value)
        return obj

    def availableDigits(self) -> int:
        return self._digits

    # @settable("digits", argtype=int)
    def setAvailableDigits(self, digits: int):
        self._digits = digits

    def decimalPlaces(self) -> int:
        return self._places

    @settable("decimal_places", argtype=int)
    def setDecimalPlaces(self, places: int):
        self._places = places

    def autoDecimalPlaces(self) -> int:
        return self._auto_decimal

    @settable()
    def setAutoDecimalPlaces(self, places: int):
        self._auto_decimal = places

    def briefMode(self) -> BriefMode:
        return self._briefmode

    @settable("brief", converter=briefModeConverter)
    def setBriefMode(self, brief: BriefMode):
        self._briefmode = brief

    def tiers(self) -> TierList:
        return self._tiers

    def setTiers(self, tiers: TierList):
        self._tiers = tiers

    def wholeWeight(self) -> int:
        return self._whole_weight

    def setWholeWeight(self, weight: int | str):
        self._whole_weight = weight

    def fractionWeight(self) -> int:
        return self._fraction_weight

    def setFractionWeight(self, weight: int | str):
        self._fraction_weight = weight

    def formatInt(self, value: Union[int, float], is_brief=False
                  ) -> FormattedNumber:
        # After formatting replace hyphen with actual unicode minus sign
        text = f"{value:,d}".replace("-", "\u2212")
        return FormattedNumber(value, text, type=NumberType.integer,
                               brief=is_brief, whole_weight=self._whole_weight)

    def formatFloat(self, value: float, avail_digits: int, places: int,
                    is_brief=False) -> FormattedNumber:
        if places >= 0:
            value = round(value, places)
        ww = self._whole_weight
        fw = self._fraction_weight

        # Just use str() instead of format() because the "f" format type imposes
        # a fixed number of decimal places, and we only want to display the
        # needed decimal places (without extra 0s on the end)
        text = str(value)
        if "e" in text:
            return self.formatScientific(value)

        dot = text.find(".")
        if dot >= 0:
            whole = text[:dot]
            frac = text[dot + 1:]
            # Reconvert the whole part of the number to give it commas
            whole = f"{int(whole):,d}"

            digit_count = len(whole) + len(frac)
            if avail_digits > 0 and digit_count > avail_digits:
                places = max(0, avail_digits - len(whole))
                rounded = round(value, places)
                frac = str(rounded)[dot + 1:]

            return FormattedNumber(value, whole, "." + frac, brief=is_brief,
                                   whole_weight=ww, fraction_weight=fw)
        else:
            return FormattedNumber(value, text, whole_weight=ww,
                                   fraction_weight=fw)

    def formatScientific(self, value: Union[int, float]) -> FormattedNumber:
        # After formatting replace hyphen with actual unicode minus sign
        text = f"{value:e}".replace("-", "\u2212")
        return FormattedNumber(value, text, type=NumberType.oversized,
                               whole_weight=self._whole_weight,
                               fraction_weight=self._fraction_weight)

    def formatNumber(self, value: Union[int, float], avail_digits: int = None,
                     places: int = None, is_brief=False) -> FormattedNumber:
        avail_digits = avail_digits if avail_digits is not None else self.availableDigits()
        places = places if places is not None else self.decimalPlaces()
        if avail_digits > 0:
            maxv = 10 ** avail_digits - 1
            minv = -10 ** avail_digits + 1
        else:
            maxv = minv = None
        suffix = ""
        bfm = self.briefMode()

        if not is_brief and (bfm == BriefMode.always or
                             (bfm == BriefMode.auto and
                              value >= self._briefcut)):
            for divisor, unit in self.tiers():
                if value >= divisor:
                    break
            else:
                divisor = 1
                unit = ""

            value = value / divisor
            is_brief = True
            suffix = unit

        if (maxv and value > maxv) or (minv and value < minv):
            # This object has a maximum number of available digits, and the
            # number is too big or too small to fit, so use scientific notation
            fn = self.formatScientific(value)

        elif (isinstance(value, int) or
              (isinstance(value, float) and value.is_integer())):
            fn = self.formatInt(int(value), is_brief=is_brief)

        elif isinstance(value, float):
            if math.isnan(value):
                return FormattedNumber(value, "NaN", type=NumberType.weird,
                                       whole_weight=self._whole_weight)
            elif math.isinf(value):
                if value < 0:
                    text = "\u2212\u221e"  # minus-sign infinity
                else:
                    text = "\u221e"  # infinity
                fn = FormattedNumber(value, text, type=NumberType.weird,
                                     whole_weight=self._whole_weight)
            else:
                fn = self.formatFloat(value, avail_digits=avail_digits,
                                      places=places, is_brief=is_brief)
        else:
            raise TypeError(f"Can't format value {value!r}")

        fn.suffix = suffix
        return fn

    def format(self, value: [Union[str, int, float]]) -> FormattedValue:
        if isinstance(value, str):
            if value:
                try:
                    value = float(value)
                except ValueError as e:
                    return FormattedNumber(value, str(e), type=NumberType.error,
                                           whole_weight=self._whole_weight)
            else:
                return FormattedNumber(0.0, "", type=NumberType.empty)
        return self.formatNumber(value)

    def toPlainText(self, value: [Union[str, int, float]]) -> str:
        return self.toString(value, markup=False)

    def toString(self, value: Union[str, int, float], markup=True) -> str:
        fv = self.format(value)
        if markup:
            return fv.html()
        else:
            return fv.plainText()

    def __call__(self, value: Union[str, int, float], markup=True) -> str:
        return self.toString(value, markup=markup)


@formattertype("percent")
class PercentFormatter(NumberFormatter):
    def __init__(self, digits=3, decimal_places=1):
        super().__init__(digits, decimal_places)

    def formatNumber(self, value: Union[int, float], avail_digits: int = None,
                     places: int = None, is_brief=False) -> FormattedNumber:
        value = value * 100.0
        fn = super().formatNumber(value, avail_digits=avail_digits,
                                  places=places, is_brief=is_brief)
        assert isinstance(fn, FormattedNumber)
        fn.suffix = "%"
        return fn


@formattertype("duration")
class DurationFormatter(NumberFormatter):
    def __init__(self, decimal_places=1, auto_decimal=1, long=False):
        super().__init__(decimal_places=decimal_places,
                         auto_decimal=auto_decimal)
        self._long = long

    @settable("long")
    def setUseLongFormat(self, long: bool):
        self._long = long

    def usingLongFormat(self) -> bool:
        return self._long

    def formatNumber(self, value: Union[int, float], avail_digits: int = None,
                     places: int = None, is_brief=False) -> FormattedNumber:
        return FormattedDuration(value, "",
                                 decimal_places=self.decimalPlaces(),
                                 auto_decimal=self.autoDecimalPlaces(),
                                 long=self._long,
                                 whole_weight=self._whole_weight,
                                 fraction_weight=self._fraction_weight)


def formatted_number(value: [Union[str, int, float]], brief=False,
                     digits=8, decimal_places=2, tiers: TierList = NUMBER_TIERS
                     ) -> FormattedNumber:
    form = NumberFormatter(digits=digits, decimal_places=decimal_places,
                           tiers=tiers)
    form.setBriefMode(BriefMode.always if brief else BriefMode.never)
    return form.formatNumber(value)


def format_number(value: [Union[int, float]], brief=False, markup=False) -> str:
    fmt = formatted_number(value, brief=brief)
    if markup:
        return fmt.html()
    else:
        return fmt.plainText()


def format_duration(secs: float, markup=True, decimal_places=1, long=False,
                    auto_decimal=1, whole_weight=BOLD_WEIGHT,
                    fraction_weight=NORMAL_WEIGHT) -> str:
    if decimal_places == 0 and auto_decimal and 0 < secs < 1.0:
        decimal_places = auto_decimal
    secs = round(secs, decimal_places)

    hours, mins, secs = divide_seconds(secs)
    if isinstance(secs, float) and secs.is_integer():
        secs = int(secs)

    # If decimal_places is 0, then the format would be :03.0f which doesn't work
    # (it will give you e.g. "006"), so I just special case it
    if decimal_places:
        secstr = "{secs:0{digits}.{places}f}".format(
            secs=secs, digits=decimal_places + 3, places=decimal_places
        )
    else:
        secstr = f"{secs:02d}"
    if secstr.startswith("0") and not secstr.startswith("0.") and \
            not (long or hours or mins):
        secstr = secstr[1:]

    if markup:
        html = ""
        if hours or long:
            html = \
                f"<span style='font-weight: {whole_weight}'>{hours:02d}</span>:"
        if mins or hours or long:
            html += \
                f"<span style='font-weight: {whole_weight}'>{mins:02d}</span>:"
        if decimal_places:
            html += markup_float(secstr, whole_weight=whole_weight,
                                 fraction_weight=fraction_weight)
        else:
            html += \
                f"<span style='font-weight: {whole_weight}'>{secstr}</span>"
        if not (long or hours or mins):
            html += abbr("s")
        return html
    else:
        text = ""
        if hours or long:
            text = f"{hours:02d}:"
        if mins or hours or long:
            text += f"{mins:02d}:"
        text += secstr
        if not (long or hours or mins):
            text += "s"

        return text


def split_vector(string: str) -> Sequence[float]:
    string = string.strip().lstrip("[").rstrip("]")
    return [float(x) for x in string.split(",")]


def whole_digit_count(n: float) -> int:
    if math.isinf(n) or math.isnan(n):
        return 3
    if n == 0:
        return 1
    return int(math.log(math.trunc(n), 10)) + 1


def markup_sci(string: str) -> str:
    before, after = string.split("e")
    before = before.rstrip("0")
    if after[1] == "0":
        after = after[0] + after[2:]
    return f"<b>{before}</b>e{after}"


def span(string: str, weight=NORMAL_WEIGHT) -> str:
    return f"<span style='font-weight: {weight}'>{string}</span>"


def abbr(string: str, size="0.8em", weight=LIGHT_WEIGHT) -> str:
    return f"<span style='font-weight: {weight}'>{string}</span>"


def markup_float(string: Union[float, str], show_fraction=True,
                 whole_weight=BOLD_WEIGHT, fraction_weight=LIGHT_WEIGHT) -> str:
    string = str(string)
    dot = string.find(".")
    if dot >= 0:
        out = span(string[:dot], weight=whole_weight)
        if show_fraction:
            out += span(string[dot:], weight=fraction_weight)
        return out
    else:
        return span(string, weight=whole_weight)


def markup_path(text: str, filename_weight=BOLD_WEIGHT) -> str:
    lastslash = max(text.rfind("/"), text.rfind("\\"))
    if lastslash > -1:
        prefix = text[:lastslash + 1]
        stem = text[lastslash + 1:]
        text = f"{prefix}<b style='font-weight: {filename_weight}'>{stem}</b>"
    return text


def format_percent(pct: float, markup=False) -> str:
    s = format_number(pct, markup=markup)
    s += abbr("%") if markup else "%"
    return s


def format_dimensions(*dims: float, markup=False) -> str:
    if markup:
        joiner = f"<span style='font-weight: {LIGHT_WEIGHT}'> \xd7 </span>"
        return joiner.join(span(str(d), BOLD_WEIGHT) for d in dims)
    else:
        return " \xd7 ".join(str(d) for d in dims)


def divide_seconds(secs: float) -> Tuple[int, int, float]:
    # days, secs = divmod(secs, 86_400)
    hours, secs = divmod(secs, 3600)
    mins, secs = divmod(secs, 60)
    return int(hours), int(mins), secs


def format_date(dt: datetime, relative_to: datetime = None, markup=False
                ) -> str:
    if relative_to and dt.date() == relative_to.date():
        datetext = "Today"
    elif relative_to and dt.date() == (relative_to - timedelta(days=1)).date():
        datetext = "Yesterday"
    elif relative_to and dt.date() > (relative_to - timedelta(days=7)).date():
        datetext = dt.strftime("%A")
    else:
        date_template = "%d %b %Y"
        datetext = dt.strftime(date_template)
    return datetext


def format_time(dt: datetime, relative_to: datetime = None, markup=False
                ) -> str:
    if markup:
        time_template = "<b>%H</b>:<b>%M</b>:<b>%S</b>"
    else:
        time_template = "%H:%M:%S"
    timetext = dt.strftime(time_template)
    return timetext


def format_date_and_time(dt: datetime, relative_to: datetime = None,
                         markup=False) -> Tuple[str, str]:
    datetext = format_date(dt, relative_to=relative_to, markup=markup)
    timetext = format_time(dt, relative_to=relative_to, markup=markup)
    return timetext, datetext


def format_datetime(dt: datetime, relative_to: datetime = None,
                    markup=False, sep=" ") -> str:
    return sep.join(format_date_and_time(dt, relative_to=relative_to,
                                         markup=markup))


def format_relative_datetime(dt: datetime, now: datetime,
                             max_relative_seconds: int = 21600
                             ) -> Tuple[str, str]:
    # Negative time deltas are really weird, so immediately convert the
    # delta to total_seconds()
    totalsecs = abs(int((now - dt).total_seconds()))

    if totalsecs < max_relative_seconds:
        text = format_duration(totalsecs)
        desc = "ago" if dt <= now else "from now"
    else:
        text, desc = format_datetime(dt, relative_to=now)
    return text, desc


def format_brief(number: float, markup=False, decimal_places=1) -> str:
    bf = NumberFormatter(brief_mode=BriefMode.auto,
                         decimal_places=decimal_places)
    fmt = bf.formatNumber(number)
    if markup:
        return fmt.html()
    else:
        return fmt.plainText()


def format_memory(bytecount: int, markup=False, decimal_places=1) -> str:
    bf = NumberFormatter(brief_mode=BriefMode.auto, tiers=DISK_TIERS,
                         decimal_places=decimal_places)
    fmt = bf.formatNumber(bytecount)
    if markup:
        return fmt.html()
    else:
        return fmt.plainText()


def format_bytes(bytecount: int, markup=False, decimal_places=1) -> str:
    bf = NumberFormatter(brief_mode=BriefMode.auto, tiers=DISK_TIERS,
                         decimal_places=decimal_places)
    fmt = bf.formatNumber(bytecount)
    if markup:
        return fmt.html()
    else:
        return fmt.plainText()


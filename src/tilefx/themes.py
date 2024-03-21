from __future__ import annotations

import dataclasses
import enum
from typing import NamedTuple, Optional, Union

from PySide2 import QtCore, QtGui
from PySide2.QtCore import Qt

from . import colorutils
from .colorutils import Color
from .util import invertedDict


def blend(c1: QtGui.QColor, c2: QtGui.QColor, pct=0.5) -> QtGui.QColor:
    inv = 1.0 - pct
    return QtGui.QColor.fromRgbF(
        c1.redF() * inv + c2.redF() * pct,
        c1.greenF() * inv + c2.greenF() * pct,
        c1.blueF() * inv + c2.blueF() * pct,
        c1.alphaF() * inv + c2.alphaF() * pct,
    )


def complement(c: QtGui.QColor, angle=180.0) -> QtGui.QColor:
    deg = c.hueF() * 360.0
    deg = (deg + angle) % 360.0
    hue = deg / 360.0
    compl = QtGui.QColor.fromHslF(hue, c.saturationF(), c.lightnessF())
    return compl


def tint(c1: QtGui.QColor, c2: QtGui.QColor, pct=1.0) -> QtGui.QColor:
    return QtGui.QColor.fromRgbF(
        c1.redF() * c2.redF(),
        c1.greenF() * c2.greenF(),
        c1.blueF() * c2.blueF(),
        c1.alphaF() * c2.alphaF(),
    )


def transp(c: QtGui.QColor, pct=0.5) -> QtGui.QColor:
    c = QtGui.QColor(c)
    c.setAlphaF(pct)
    return c


def replaceHsl(c: QtGui.QColor, *, hue: float = None, saturation: float = None,
               lightness: float = None, alpha: float = None) -> QtGui.QColor:
    h = max(0.0, min(1.0, hue if hue is not None else c.hueF()))
    s = max(0.0, min(1.0, saturation if saturation is not None else c.saturationF()))
    l = max(0.0, min(1.0, lightness if lightness is not None else c.lightnessF()))
    a = max(0.0, min(1.0, alpha if alpha is not None else c.alphaF()))
    return QtGui.QColor.fromHslF(h, s, l, a)


def stripes(color1: QtGui.QColor, color2=Qt.transparent, width=2.5, width2=None
            ) -> QtGui.QColor:
    if width2 is None:
        width2 = width
    total = width + width2
    prop = width / total
    grad = QtGui.QLinearGradient(0.0, 0.0, total, total)
    grad.setColorAt(0.0, color1)
    grad.setColorAt(prop - 0.001, color1)
    grad.setColorAt(prop, color2)
    grad.setColorAt(1.0, color2)
    grad.setSpread(grad.RepeatSpread)
    return grad


def success_brush(color1=QtGui.QColor(0, 255, 64),
                  color2=QtGui.QColor(0, 0, 0, 0)):
    grad = stripes(color1, color2, width=1.0, width2=1.5)
    return QtGui.QBrush(grad)


def warning_brush(color1=QtGui.QColor(210, 177, 16),
                  color2=QtGui.QColor(103, 72, 0)):
    grad = stripes(color1, color2)
    return QtGui.QBrush(grad)


def error_brush(color1=QtGui.QColor(255, 84, 84),
                color2=QtGui.QColor(128, 0, 0)):
    grad = stripes(color1, color2)
    return QtGui.QBrush(grad)


def _hct(c: QtGui.QColor) -> Color:
    rgb = Color("srgb", [c.redF(), c.greenF(), c.blueF()])
    return rgb.convert("hct")


class ThemeColor(enum.Enum):
    bg = enum.auto()
    fg = enum.auto()
    alt_fg = enum.auto()
    dim_fg = enum.auto()
    value = enum.auto()

    primary = enum.auto()
    primary_fg = enum.auto()
    primary_surface = enum.auto()
    primary_surface_fg = enum.auto()

    secondary = enum.auto()
    secondary_fg = enum.auto()
    secondary_surface = enum.auto()
    secondary_surface_fg = enum.auto()

    highlight = enum.auto()
    highlight_fg = enum.auto()
    highlight_surface = enum.auto()
    highlight_surface_fg = enum.auto()

    button = enum.auto()
    button_high = enum.auto()
    button_low = enum.auto()
    button_fg = enum.auto()
    pressed = enum.auto()
    pressed_fg = enum.auto()

    field = enum.auto()
    field_alt = enum.auto()

    surface = enum.auto()
    surface_fg = enum.auto()
    surface_outline = enum.auto()
    surface_alt_fg = enum.auto()
    surface_highest = enum.auto()
    surface_high = enum.auto()
    surface_low = enum.auto()
    surface_lowest = enum.auto()

    success = enum.auto()
    success_fg = enum.auto()
    success_surface = enum.auto()
    success_surface_fg = enum.auto()

    warning = enum.auto()
    warning_fg = enum.auto()
    warning_surface = enum.auto()
    warning_surface_fg = enum.auto()

    error = enum.auto()
    error_fg = enum.auto()
    error_surface = enum.auto()
    error_surface_fg = enum.auto()

    blue = enum.auto()
    green = enum.auto()
    indigo = enum.auto()
    orange = enum.auto()
    magenta = enum.auto()
    purple = enum.auto()
    plum = enum.auto()
    red = enum.auto()
    cyan = enum.auto()
    yellow = enum.auto()
    kiwi = enum.auto()
    peach = enum.auto()
    pink = enum.auto()
    steel = enum.auto()
    tan = enum.auto()
    mint = enum.auto()
    gray = enum.auto()


@dataclasses.dataclass(frozen=True)
class ColorTheme:
    theme_qcolor: QtGui.QColor
    theme_hct: Color

    primary: colorutils.Tones
    primary_fg: colorutils.Tones

    secondary: colorutils.Tones
    secondary_fg: colorutils.Tones

    highlight: colorutils.Tones
    highlight_fg: colorutils.Tones

    neutral: colorutils.Tones
    neutral_fg: colorutils.Tones
    neutral_alt: colorutils.Tones

    error: colorutils.Tones
    warning: colorutils.Tones
    success: colorutils.Tones

    contrast: float
    is_dark: bool

    @classmethod
    def fromColor(cls, theme_color: QtGui.QColor, secondary: QtGui.QColor = None,
                  highlight: QtGui.QColor = None, contrast=7.0,
                  secondary_chroma=16, highlight_hue_rotation=-60.0,
                  highlight_min_chroma=32.0,
                  is_dark: bool = None) -> ColorTheme:
        theme_hct = _hct(theme_color)
        secondary_hct = _hct(secondary) if secondary else None
        highlight_hct = _hct(highlight) if highlight else None
        return cls.fromHct(
            theme_hct,
            secondary_hct=secondary_hct,
            highlight_hct=highlight_hct,
            contrast=contrast,
            secondary_chroma=secondary_chroma,
            highlight_hue_rotation=highlight_hue_rotation,
            is_dark=is_dark,
            theme_color=theme_color,
        )

    @classmethod
    def fromHct(cls, theme_hct: Color, secondary_hct: Color = None,
                highlight_hct: Color = None, contrast=7.0, secondary_chroma=16,
                neutral_chroma=8.0, highlight_hue_rotation=-60.0,
                highlight_min_chroma=16.0, is_dark: bool = None,
                theme_color: QtGui.QColor = None) -> ColorTheme:
        theme_hue = theme_hct["hue"]
        theme_chroma = theme_hct["chroma"]

        if is_dark is None:
            # Choose light/dark based on example color tone
            is_dark = theme_hct["tone"] <= 50.0

        if theme_color is None:
            theme_color = colorutils.hct_to_qcolor(theme_hct)

        if secondary_hct:
            secondary_hue = secondary_hct["hue"]
            secondary_chroma = secondary_hct["chroma"]
        else:
            secondary_hue = theme_hct["hue"]
            secondary_chroma = min(theme_chroma, secondary_chroma)

        if highlight_hct:
            highlight_hue = highlight_hct["hue"]
            highlight_chroma = highlight_hct["chroma"]
        else:
            highlight_hue = theme_hct["hue"] + highlight_hue_rotation
            highlight_chroma = max(highlight_min_chroma, theme_chroma)

        # print("theme hue=", theme_hue, "chroma=", theme_chroma)
        # print("neutral_chroma=", neutral_chroma,
        #       min(theme_chroma / 12, neutral_chroma),
        #       min(theme_chroma / 6, neutral_chroma * 2))

        # if theme_chroma > 10:
        #     primary_chroma = max(30.0, theme_chroma)
        # else:
        #     primary_chroma = theme_chroma

        theme = cls(
            theme_qcolor=theme_color,
            theme_hct=theme_hct,
            primary=colorutils.Tones(theme_hue, theme_chroma),
            primary_fg=colorutils.Tones(theme_hue, theme_chroma),
            secondary=colorutils.Tones(secondary_hue, secondary_chroma),
            secondary_fg=colorutils.Tones(secondary_hue, secondary_chroma/3.0),
            highlight=colorutils.Tones(highlight_hue, highlight_chroma),
            highlight_fg=colorutils.Tones(highlight_hue, theme_chroma / 2.0),
            neutral=colorutils.Tones(theme_hue, neutral_chroma),
            neutral_fg=colorutils.Tones(
                theme_hue, min(theme_chroma / 12, neutral_chroma)),
            neutral_alt=colorutils.Tones(
                theme_hue, min(theme_chroma / 6, neutral_chroma * 2)),
            error=colorutils.Tones(25, 84),
            warning=colorutils.Tones(90, 84),
            success=colorutils.Tones(140, 50),
            contrast=contrast,
            is_dark=is_dark
        )
        return theme

    def themePalette(self) -> ThemePalette:
        if self.is_dark:
            return self.darkPalette()
        else:
            return self.lightPalette()

    def lightPalette(self) -> ThemePalette:
        colors = {
            ThemeColor.bg: self.neutral.tone(87),
            ThemeColor.fg: self.neutral.tone(30),
            ThemeColor.alt_fg: self.neutral_alt.tone(10),
            ThemeColor.dim_fg: self.neutral_alt.tone(40),
            ThemeColor.value: self.secondary_fg.tone(10),

            ThemeColor.primary: self.primary.tone(40),
            ThemeColor.primary_fg: self.primary_fg.tone(90),
            ThemeColor.primary_surface: self.primary.tone(90),
            ThemeColor.primary_surface_fg: self.primary_fg.tone(10),

            ThemeColor.secondary: self.secondary.tone(40),
            ThemeColor.secondary_fg: self.secondary_fg.tone(90),
            ThemeColor.secondary_surface: self.secondary.tone(90),
            ThemeColor.secondary_surface_fg: self.secondary_fg.tone(10),

            ThemeColor.highlight: self.highlight.tone(40),
            ThemeColor.highlight_fg: self.highlight_fg.tone(90),
            ThemeColor.highlight_surface: self.highlight.tone(90),
            ThemeColor.highlight_surface_fg: self.highlight_fg.tone(10),

            ThemeColor.button: self.secondary.tone(70),
            ThemeColor.button_high: self.secondary.tone(60),
            ThemeColor.button_low: self.secondary.tone(90),
            ThemeColor.button_fg: self.secondary_fg.tone(30),
            ThemeColor.pressed: self.primary.tone(100),
            ThemeColor.pressed_fg: self.primary.tone(20),

            ThemeColor.field: self.neutral.tone(99),
            ThemeColor.field_alt: self.neutral.tone(94),

            ThemeColor.surface_lowest: self.neutral.tone(80),
            ThemeColor.surface_low: self.neutral.tone(84),
            ThemeColor.surface: self.neutral.tone(93),
            ThemeColor.surface_high: self.neutral.tone(96),
            ThemeColor.surface_highest: self.neutral.tone(99),

            ThemeColor.error: self.error.tone(40),
            ThemeColor.error_fg: self.error.tone(90),
            ThemeColor.error_surface: self.error.tone(90),
            ThemeColor.error_surface_fg: self.error.tone(10),

            ThemeColor.warning: self.warning.tone(40),
            ThemeColor.warning_fg: self.warning.tone(90),
            ThemeColor.warning_surface: self.warning.tone(90),
            ThemeColor.warning_surface_fg: self.warning.tone(10),

            ThemeColor.success: self.success.tone(40),
            ThemeColor.success_fg: self.success.tone(90),
            ThemeColor.success_surface: self.success.tone(90),
            ThemeColor.success_surface_fg: self.success.tone(10),
        }
        colors.update(basic_colors_light)
        return ThemePalette(colors)

    def darkPalette(self) -> ThemePalette:
        colors = {
            ThemeColor.bg: self.neutral.tone(12),
            ThemeColor.fg: self.neutral.tone(80),
            ThemeColor.alt_fg: self.neutral_alt.tone(90),
            ThemeColor.dim_fg: self.neutral_alt.tone(60),
            ThemeColor.value: self.secondary_fg.tone(90),

            ThemeColor.primary: self.primary.tone(80),
            ThemeColor.primary_fg: self.primary_fg.tone(20),
            ThemeColor.primary_surface: self.primary.tone(30),
            ThemeColor.primary_surface_fg: self.primary_fg.tone(90),

            ThemeColor.secondary: self.secondary.tone(80),
            ThemeColor.secondary_fg: self.secondary_fg.tone(20),
            ThemeColor.secondary_surface: self.secondary.tone(30),
            ThemeColor.secondary_surface_fg: self.secondary_fg.tone(90),

            ThemeColor.highlight: self.highlight.tone(60),
            ThemeColor.highlight_fg: self.highlight_fg.tone(20),
            ThemeColor.highlight_surface: self.highlight.tone(30),
            ThemeColor.highlight_surface_fg: self.highlight_fg.tone(90),

            ThemeColor.button: self.secondary.tone(30),
            ThemeColor.button_high: self.secondary.tone(50),
            ThemeColor.button_low: self.secondary.tone(10),
            ThemeColor.button_fg: self.secondary_fg.tone(90),
            ThemeColor.pressed: self.primary.tone(0),
            ThemeColor.pressed_fg: self.primary_fg.tone(80),

            ThemeColor.field: self.neutral.tone(5),
            ThemeColor.field_alt: self.neutral.tone(10),

            ThemeColor.surface_lowest: self.neutral.tone(15),
            ThemeColor.surface_low: self.neutral.tone(18),
            ThemeColor.surface: self.neutral.tone(20),
            ThemeColor.surface_high: self.neutral.tone(25),
            ThemeColor.surface_highest: self.neutral.tone(30),
            ThemeColor.surface_outline: self.neutral.tone(40),

            ThemeColor.error: self.error.tone(80),
            ThemeColor.error_fg: self.error.tone(20),
            ThemeColor.error_surface: self.error.tone(30),
            ThemeColor.error_surface_fg: self.error.tone(80),

            ThemeColor.warning: self.warning.tone(80),
            ThemeColor.warning_fg: self.warning.tone(20),
            ThemeColor.warning_surface: self.warning.tone(30),
            ThemeColor.warning_surface_fg: self.warning.tone(80),

            ThemeColor.success: self.success.tone(80),
            ThemeColor.success_fg: self.success.tone(20),
            ThemeColor.success_surface: self.success.tone(30),
            ThemeColor.success_surface_fg: self.success.tone(80),
        }
        colors.update(basic_colors_dark)
        return ThemePalette(colors)


class ThemePalette:
    def __init__(self, colors: dict[ThemeColor, QtGui.QColor]):
        self.colors = colors
        self.cache_key = hash(type(self))
        for nc in ThemeColor:
            if nc in colors:
                self.cache_key ^= hash(colors[nc].name())

    def resolve(self, color: Union[str, ThemeColor, QtGui.QColor]
                ) -> QtGui.QColor:
        if isinstance(color, QtGui.QColor):
            return QtGui.QColor(color)
        elif isinstance(color, str):
            color = ThemeColor.__members__[color]
        return QtGui.QColor(self.colors[color])

    def qtPalette(self) -> QtGui.QPalette:
        palette = QtGui.QPalette()
        colors = self.colors
        for role, theme_color in role_mapping.items():
            palette.setColor(role, colors[theme_color])
        return palette


role_mapping: dict[QtGui.QPalette.ColorRole, ThemeColor] = {
    QtGui.QPalette.Window: ThemeColor.bg,
    QtGui.QPalette.WindowText: ThemeColor.fg,
    QtGui.QPalette.Base: ThemeColor.field,
    QtGui.QPalette.AlternateBase: ThemeColor.field_alt,
    QtGui.QPalette.ToolTipBase: ThemeColor.secondary,
    QtGui.QPalette.ToolTipText: ThemeColor.secondary_fg,
    QtGui.QPalette.PlaceholderText: ThemeColor.dim_fg,
    QtGui.QPalette.Text: ThemeColor.value,
    QtGui.QPalette.Button: ThemeColor.button,
    QtGui.QPalette.ButtonText: ThemeColor.button_fg,
    QtGui.QPalette.BrightText: ThemeColor.pressed_fg,
    QtGui.QPalette.Light: ThemeColor.surface_highest,
    QtGui.QPalette.Midlight: ThemeColor.surface_high,
    QtGui.QPalette.Mid: ThemeColor.surface,
    QtGui.QPalette.Dark: ThemeColor.surface_low,
    QtGui.QPalette.Shadow: ThemeColor.pressed,
    QtGui.QPalette.Highlight: ThemeColor.highlight,
    QtGui.QPalette.HighlightedText: ThemeColor.highlight_fg,
    QtGui.QPalette.Link: ThemeColor.primary,
    QtGui.QPalette.LinkVisited: ThemeColor.error,
}

basic_colors_dark: dict[ThemeColor, QtGui.QColor] = {
    ThemeColor.error: QtGui.QColor("#f2b8b5"),
    # NamedColor.error_contrast: QtGui.QColor("#601410"),
    # NamedColor.error_surface: QtGui.QColor("#8c1d18"),
    # NamedColor.error_surface_contrast: QtGui.QColor("#f9dedc"),

    ThemeColor.blue: QtGui.QColor("#3399ff"),
    ThemeColor.green: QtGui.QColor("#30d158"),
    ThemeColor.indigo: QtGui.QColor("#6e6cff"),
    ThemeColor.orange: QtGui.QColor("#ff9f0a"),
    ThemeColor.magenta: QtGui.QColor("#ee5c93"),
    ThemeColor.purple: QtGui.QColor("#bf5af2"),
    ThemeColor.plum: QtGui.QColor("#891f91"),
    ThemeColor.red: QtGui.QColor("#ff5151"),
    ThemeColor.cyan: QtGui.QColor("#64d2ff"),
    ThemeColor.yellow: QtGui.QColor("#ffd60a"),
    ThemeColor.kiwi: QtGui.QColor("#96d130"),
    ThemeColor.peach: QtGui.QColor("#e2af8e"),
    ThemeColor.pink: QtGui.QColor("#ffa9a9"),
    ThemeColor.steel: QtGui.QColor("#a9c6e7"),
    ThemeColor.tan: QtGui.QColor("#ceb4a4"),
    ThemeColor.mint: QtGui.QColor("#8dcaa9"),
    ThemeColor.gray: QtGui.QColor("#919191"),
}
basic_colors_light: dict[ThemeColor, QtGui.QColor] = {
    ThemeColor.blue: QtGui.QColor("#0066CC"),
    ThemeColor.green: QtGui.QColor(36, 161, 68),
    ThemeColor.indigo: QtGui.QColor(88, 86, 214),
    ThemeColor.orange: QtGui.QColor(255, 102, 0),
    ThemeColor.magenta: QtGui.QColor(255, 104, 133),
    ThemeColor.purple: QtGui.QColor(175, 82, 222),
    ThemeColor.plum: QtGui.QColor("#891f91"),
    ThemeColor.red: QtGui.QColor(207, 0, 0),
    ThemeColor.cyan: QtGui.QColor(17, 153, 215),
    ThemeColor.yellow: QtGui.QColor(246, 190, 0),
    ThemeColor.kiwi: QtGui.QColor(99, 144, 19),
    ThemeColor.peach: QtGui.QColor(192, 123, 79),
    ThemeColor.pink: QtGui.QColor(210, 137, 137),
    ThemeColor.steel: QtGui.QColor(104, 121, 140),
    ThemeColor.tan: QtGui.QColor(147, 134, 127),
    ThemeColor.mint: QtGui.QColor(93, 146, 117),
    ThemeColor.gray: QtGui.QColor(179, 179, 179),
}

default_chart_colors = (
    ThemeColor.red, ThemeColor.blue, ThemeColor.yellow, ThemeColor.green,
    ThemeColor.purple, ThemeColor.cyan, ThemeColor.peach, ThemeColor.tan,
    ThemeColor.plum, ThemeColor.pink, ThemeColor.mint, ThemeColor.gray
)


# # Nord theme
# # Polar night
# nord00 = QColor("2E3440")
# nord01 = QColor("3B4252")
# nord02 = QColor("434C5E")
# nord03 = QColor("4C566A")
#
# # Snow storm
# nord04 = QColor("D8DEE9")
# nord05 = QColor("E5E9F0")
# nord06 = QColor("ECEFF4")
#
# # Frost
# nord07 = QColor("8FBCBB")
# nord08 = QColor("88C0D0")
# nord09 = QColor("81A1C1")
# nord10 = QColor("5E81AC")
#
# # Aurora
# nord11 = nord_red = QColor("BF616A")
# nord12 = nord_orange = QColor("D08770")
# nord13 = nord_yellow = QColor("EBCB8B")
# nord14 = nord_green = QColor("A3BE8C")
# nord15 = nord_purple = QColor("B48EAD")
#
# # Dracula
# dracula_window = QColor("282a36")
# dracula_lighter = QColor("44475a")
# dracula_windowtext = QColor("f8f8f2")
# dracula_placeholder = QColor("6272a4")
# dracula_cyan = QColor("8be9fd")
# dracula_green = QColor("50fa7b")
# dracula_orange = QColor("ffb86c")
# dracula_pink = QColor("ff79c6")
# dracula_purple = QColor("bd93f9")
# dracula_red = QColor("ff5555")
# dracula_yellow = QColor("f1fa8c")

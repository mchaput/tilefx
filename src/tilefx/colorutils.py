from __future__ import annotations
import dataclasses

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt
from coloraide import Color as BaseColor
from coloraide.spaces.hct import HCT, y_to_lstar, lstar_to_y
from coloraide.gamut.fit_hct_chroma import HCTChroma
from coloraide.distance.delta_e_hct import DEHCT


class Color(BaseColor):
    pass


Color.register([HCT(), DEHCT(), HCTChroma()])


E = 216.0 / 24389.0
KAPPA = 24389.0 / 27.0
tone_values = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]


def hct_to_hex(hct: Color) -> str:
    rgb = hct.convert("srgb")
    return rgb.to_string(hex=True, fit={'method': 'hct-chroma', 'jnd': 0.0})


def hct_to_qcolor(hct: Color) -> QtGui.QColor:
    return QtGui.QColor(hct_to_hex(hct))


class Tones:
    def __init__(self, hue: float, chroma: float) -> None:
        self.hue = hue
        self.chroma = chroma
        self._tones: dict[float, QtGui.QColor] = {}

    @classmethod
    def fromHct(cls, hct: Color) -> Tones:
        return Tones(hct["hue"], hct["chroma"])

    def tone(self, tone: float) -> QtGui.QColor:
        tone = round(tone, 1)
        if tone in self._tones:
            return self._tones[tone]

        hct = Color("hct", [self.hue, self.chroma, tone])
        qcolor = hct_to_qcolor(hct)
        self._tones[tone] = qcolor
        return qcolor

    # @classmethod
    # def forHueAndChrome(cls, hue: float, chroma: float) -> Tones:
    #     c = coloraide.Color("hct", [hue, chroma, 50])
    #     hct_colors = [
    #         c.clone().set("tone", tone).fit('srgb', method='hct-chroma',
    #                                         jnd=0.0)
    #         for tone in tone_values
    #     ]
    #     qt_colors = [
    #         QtGui.QColor(hct.to_string(hex=True)) for hct in hct_colors
    #     ]
    #     return Tones(hue, chroma, qt_colors)


def ratioOfYs(y1: float, y2: float) -> float:
    lighter = y1 if y1 > y2 else y2
    darker = y1 if lighter == y2 else y1
    return (lighter + 5.0) / (darker + 5.0)


def ratioOfTones(t1: float, t2: float) -> float:
    return ratioOfYs(lstar_to_y(t1), lstar_to_y(t2))



def deltaTone(reference_y: float, modified_y: float, ratio: float) -> float:
    contrast = ratioOfYs(reference_y, modified_y)
    diff = abs(contrast - ratio)
    if contrast < ratio and diff > 0.04:
        return -1

    value = y_to_lstar(modified_y)
    if not 0 <= value <= 100:
        return -1
    return value


def lighterTone(tone: float, ratio: float) -> float:
    dark_y = lstar_to_y(tone)
    light_y = ratio * (dark_y + 5.0) - 5.0
    return deltaTone(dark_y, light_y, ratio)


def darkerTone(tone: float, ratio: float) -> float:
    light_y = lstar_to_y(tone)
    dark_y = ((light_y + 5.0) / ratio) - 5.0
    return deltaTone(light_y, dark_y, ratio)


def tonePrefersLightForeground(tone: float) -> bool:
    return round(tone) < 60.0


def toneAllowsLightForeground(tone: float) -> bool:
    return round(tone) <= 49.0


def enableLightForeground(tone: float) -> float:
    if tonePrefersLightForeground(tone) and not toneAllowsLightForeground(tone):
        tone = 49.0
    return tone


def foregroundTone(bg_tone: float, ratio: float) -> float:
    lighter = lighterTone(bg_tone, ratio)
    darker = darkerTone(bg_tone, ratio)
    lighter_ratio = ratioOfTones(lighter, bg_tone)
    darker_ratio = ratioOfTones(darker, bg_tone)
    prefer_lighter = tonePrefersLightForeground(bg_tone)

    if prefer_lighter:
        nodiff = (abs(lighter_ratio - darker_ratio) < 0.1 and
                  lighter_ratio < ratio and
                  darker_ratio < ratio)
        if lighter_ratio >= ratio or lighter_ratio >= darker_ratio or nodiff:
            return lighter
        else:
            return darker
    else:
        if darker_ratio >= ratio or darker_ratio >= lighter_ratio:
            return darker
        else:
            return lighter

import uharfbuzz as hb
import base64

from io import BytesIO
from itertools import chain
from typing import Dict, Tuple
from fontTools.ttLib import TTFont
from ufo2ft import compileOTF, compileTTF
from ufoLib2.objects.font import Font

from extractor.formats.opentype import (
    extractGlyphOrder,
    extractOpenTypeGlyphs,
    extractOpenTypeInfo,
    extractOpenTypeKerning,
    extractUnicodeVariationSequences,
)


MAX_ERR = 0.2

FAMILY_RELATED_IDS = dict(
    LEGACY_FAMILY=1,
    TRUETYPE_UNIQUE_ID=3,
    FULL_NAME=4,
    POSTSCRIPT_NAME=6,
    PREFERRED_FAMILY=16,
    WWS_FAMILY=21,
)

WINDOWS_ENGLISH_IDS = 3, 1, 0x409
MAC_ROMAN_IDS = 1, 0, 0


def insert_suffix(string, family_name, suffix):
    # check whether family_name is a substring
    start = string.find(family_name)
    if start != -1:
        # insert suffix after the family_name substring
        end = start + len(family_name)
        new_string = string[:end] + suffix + string[end:]
    else:
        # it's not, we just append the suffix at the end
        new_string = string + suffix
    return new_string


def get_current_family_name(table):
    family_name_rec = None
    for plat_id, enc_id, lang_id in (WINDOWS_ENGLISH_IDS, MAC_ROMAN_IDS):
        for name_id in (
            FAMILY_RELATED_IDS["PREFERRED_FAMILY"],
            FAMILY_RELATED_IDS["LEGACY_FAMILY"],
        ):
            family_name_rec = table.getName(
                nameID=name_id,
                platformID=plat_id,
                platEncID=enc_id,
                langID=lang_id,
            )
            if family_name_rec is not None:
                break
        if family_name_rec is not None:
            break
    if not family_name_rec:
        raise ValueError("family name not found; can't add suffix")
    return family_name_rec.toUnicode()


def rename_record(name_record, family_name, suffix):
    string = name_record.toUnicode()
    new_string = insert_suffix(string, family_name, suffix)
    name_record.string = new_string
    return string, new_string


def add_family_suffix(font, suffix):
    table = font["name"]

    family_name = get_current_family_name(table)

    # postcript name can't contain spaces
    ps_family_name = family_name.replace(" ", "")
    ps_suffix = suffix.replace(" ", "")
    for rec in table.names:
        name_id = rec.nameID
        if name_id not in FAMILY_RELATED_IDS.values():
            continue
        if name_id == FAMILY_RELATED_IDS["POSTSCRIPT_NAME"]:
            old, new = rename_record(rec, ps_family_name, ps_suffix)
        elif name_id == FAMILY_RELATED_IDS["TRUETYPE_UNIQUE_ID"]:
            # The Truetype Unique ID rec may contain either the PostScript
            # Name or the Full Name string, so we try both
            if ps_family_name in rec.toUnicode():
                old, new = rename_record(rec, ps_family_name, ps_suffix)
            else:
                old, new = rename_record(rec, family_name, suffix)
        else:
            old, new = rename_record(rec, family_name, suffix)

    return family_name

def extractFontFromOpenType(
    tt_font,
    destination,
    extract_glyphs=True,
):
    extractGlyphOrder(tt_font, destination)
    try:
        extractOpenTypeInfo(tt_font, destination)
    except Exception as e:
        print(e)
        pass
    if extract_glyphs:
        extractOpenTypeGlyphs(tt_font, destination)
    else:
        for glyph_name in destination.glyphOrder:
            destination.newGlyph(glyph_name)
    extractUnicodeVariationSequences(tt_font, destination)
    kerning, groups = extractOpenTypeKerning(tt_font, destination)
    destination.groups.update(groups)
    destination.kerning.update(kerning)

def rename_name_ttfont(font, suffix) -> None:
    try:
        add_family_suffix(font, f" {suffix}")
    except Exception as e:
        print(e)
        pass


def rename_name_ufo(font, suffix) -> None:
    old_name = font.info.familyName
    new_name = f"{old_name} {suffix}"
    try:
        font.info.openTypeNameRecords.clear()
    except Exception as e:
        print("font info already cleared", e)
        pass

    font.info.familyName = new_name
    font.info.styleMapFamilyName = new_name

    font.info.openTypeNamePreferredFamilyName = new_name
    font.info.openTypeNameCompatibleFullName = new_name


def export_font(font, flavour="ttf"):
    if isinstance(font, Font):
        if flavour == "ttf":
            font = compileTTF(font, removeOverlaps=False, flattenComponents=False)
        elif flavour == "otf":
            font = compileOTF(font, removeOverlaps=True)
        else:
            raise Exception("flavour not matched")
    if isinstance(font, TTFont):
        font_bytes = BytesIO()
        font.save(font_bytes)
        return font_bytes
    else:
        raise Exception("not good instance")


def export_fonts(fonts, flavour="ttf"):
    fonts_ = []
    for font in fonts:
        fonts_.append(export_font(font))
    return fonts_


def fonts_to_base64(fonts):
    fonts_ = export_fonts(fonts)
    return [base64.b64encode(font.getvalue()).decode("ascii") for font in fonts_]


def get_components_in_subsetted_text(tt_font, glyph_names):
    if "glyf" in tt_font:
        def get_component_names(glyf, glyph_names, collector=[]):
            components = list(
                chain(
                    *[
                        glyf[glyph_name].getComponentNames(glyf)
                        for glyph_name in glyph_names
                    ]
                )
            )
            if components:
                collector += components
                return get_component_names(glyf, components, collector)
            else:
                return collector

        glyf = tt_font["glyf"]
        keep_glyphs = filter(
            lambda glyph_name: False if glyph_name is None else True, glyph_names
        )
        return get_component_names(glyf, list(keep_glyphs))
    else:
        return []

def extract_kerning_hb(
    font_data: bytes, widths: Dict[Tuple[str, str], int], content: str, cmap: dict
) -> Dict[Tuple[str, str], int]:
    blob = hb.Blob(font_data)
    face = hb.Face(blob)
    font = hb.Font(face)
    buf = hb.Buffer()
    buf.add_str(content)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "liga": False})
    positions = buf.glyph_positions
    kerning = {}
    for i, pos in enumerate(positions[:-1]):
        x_advance = pos.x_advance
        key = (cmap.get(ord(content[i])), cmap.get(ord(content[i + 1])))
        if None not in key:
            value = x_advance - widths[cmap[ord(content[i])]]
            if value != 0:
                if key not in kerning:
                    kerning[key] = value
    return kerning
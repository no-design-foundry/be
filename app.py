import base64
from gc import collect
from io import BytesIO
from pathlib import Path

from defcon import Font
from defcon.objects.base import BaseObject
from flask import Flask, abort, jsonify, request
from flask_cors import CORS, cross_origin
from fontTools.ttLib import TTFont
import base64

from pan.pan import pan
from rasterizer.rasterizer import rasterize
from extruder.extruder import extrude_variable
from rotorizer.rotorizer import rotorize

from tools.generic import (
    extractOpenTypeInfo,
    extract_kerning_hb,
    extractCFF2Glyph,
    extractCFFGlyph,
    extractGlyfGlyph,
    fonts_to_base64,
    get_components_in_subsetted_text,
    rename_name_ttfont,
    rename_name_ufo,
)

BaseObject.addObserver = lambda *args, **kwargs: None
BaseObject.postNotification = lambda *args, **kwargs: None
BaseObject.removeObserver = lambda *args, **kwargs: None
BaseObject.beginSelfNotificationObservation = lambda *args, **kwargs: None
BaseObject.endSelfContourNotificationObservation = lambda *args, **kwargs: None


base = Path(__file__).parent

app = Flask(__name__)
cors = CORS(app)
app.config["CORS_HEADERS"] = "Content-Type"

origins = ["http://localhost:3000", "*"]

suffix_name_map = {
    "rotorizer": ["Rotorized Underlay", "Rotorized Overlay"],
    "rasterizer": ["Rasterized"],
    "extruder": ["Extruded"],
    "pan": ["Panned"],
}

ranges = [
    (32, 126),
]


def is_in_ranges(code_point):
    for start, end in ranges:
        if start <= code_point <= end:
            return True
    return False
    

def process_font(filter_identifier, request, process_for_download=False):
    if filter_identifier not in [
        "rasterizer",
        "rotorizer",
        "extruder",
        "pan"]:
        raise abort(404, description="Filter not found")

    if not request.files.get("font_file"):
        raise AssertionError("Font file is required")

    preview_string = request.form.get("preview_string")
    if preview_string:
        if len(preview_string) > 30:
            raise AssertionError("Preview string is too long")

    font_file = request.files.get("font_file").read()

    binary_font = BytesIO(font_file)
    tt_font = TTFont(binary_font)
    units_per_em = tt_font["head"].unitsPerEm

    glyph_names_to_process = []
    cmap = tt_font.getBestCmap()
    cmap_reversed = {}
    for k, v in cmap.items():
        cmap_reversed.setdefault(v, []).append(k)

    if process_for_download:
        for glyph_name, unicode_values in cmap_reversed.items():
            for unicode_value in unicode_values:
                if is_in_ranges(unicode_value):
                    glyph_names_to_process.append(glyph_name)
    else:
        glyph_names_to_process = [
            cmap.get(ord(char), None) for char in set(preview_string)
        ]

    components = get_components_in_subsetted_text(tt_font, glyph_names_to_process)
    glyph_names_to_process.extend(components)

    ufo = Font()
    ufo.info.unitsPerEm = tt_font["head"].unitsPerEm
    if process_for_download:
        ufo.info.familyName = tt_font["name"].getBestFamilyName()
        ufo.info.styleName = tt_font["name"].getBestSubFamilyName()
    else:
        ufo.info.familyName = "Preview"
        ufo.info.styleName = "Regular"

    for glyph_name in glyph_names_to_process:
        glyph = ufo.newGlyph(glyph_name)
        glyph.unicodes = cmap_reversed.get(glyph_name, None)
        pen = glyph.getPen()
        if filter_identifier in ["extruder", "rotorizer", "pan"]:
            pen = glyph.getPen()
            glyph.width = tt_font["hmtx"].metrics[glyph_name][0]
            if "CFF " in tt_font:
                extractCFFGlyph(tt_font, glyph_name, pen)
            elif "CFF2" in tt_font:
                extractCFF2Glyph(tt_font, glyph_name, pen)
            elif "glyf" in tt_font:
                extractGlyfGlyph(tt_font, glyph_name, pen)
            else:
                raise AssertionError("Unsupported font format")

    if filter_identifier == "rasterizer":
        resolution = int(request.form.get("resolution", 30))
        output = [
            rasterize(
                ufo=ufo,
                tt_font=tt_font,
                binary_font=binary_font,
                glyph_names_to_process=glyph_names_to_process,
                resolution=resolution,
            )
        ]
    elif filter_identifier == "rotorizer":
        depth = int(request.form.get("depth", 200))
        output = rotorize(
            ufo=ufo,
            glyph_names_to_process=glyph_names_to_process,
            depth=depth,
        )

    elif filter_identifier == "extruder":
        angle = int(request.form.get("angle", 330))
        if not process_for_download:
            extractOpenTypeInfo(tt_font, ufo)
            widths = {k:v[0] for k,v in tt_font["hmtx"].metrics.items() if k in glyph_names_to_process}
            extracted_kerning = extract_kerning_hb(font_file, widths, content=preview_string, cmap=cmap)
            for k,v in extracted_kerning.items():
                ufo.kerning[k] = v
        extractOpenTypeInfo(tt_font, ufo)
        widths = {
            k: v[0]
            for k, v in tt_font["hmtx"].metrics.items()
            if k in glyph_names_to_process
        }
        extracted_kerning = extract_kerning_hb(
            font_file, widths, content=preview_string, cmap=cmap
        )
        for k, v in extracted_kerning.items():
            ufo.kerning[k] = v
        output = [
            extrude_variable(
                ufo=ufo,
                glyph_names_to_process=glyph_names_to_process,
                angle=angle,
                depths=[20, 400]
            )
        ]
    elif filter_identifier == "pan":
        output = [
            pan(
                ufo,
                glyph_names_to_process,
                units_per_em / 1000,
                shadow=request.form.get("shadow", False),
            )
        ]

    for f, font in enumerate(output):
        suffix = suffix_name_map[filter_identifier][f]
        if suffix:
            if isinstance(font, Font):
                rename_name_ufo(font, suffix)
            else:
                rename_name_ttfont(font, suffix)

    response = fonts_to_base64(output)
    if filter_identifier in ["extruder"]:
        response.append(base64.b64encode(font_file).decode("ascii"))

    collect()

    if process_for_download:
        return jsonify({"fonts": response}), 200
    else:
        warnings = []
        missing_glyphs = [
            character
            for character in preview_string
            if cmap.get(ord(character), None) is None
        ]
        if missing_glyphs:
            warnings.append(
                f'Your font is missing these characters: {", ".join(missing_glyphs)}'
            )
        return jsonify(
            {
                "fonts": response,
                "warnings": warnings,
                # "margins": get_margins(tt_font),
                "preview_string": "".join(
                    [char for char in preview_string if char not in missing_glyphs]
                ),
            }
        ), 200


@app.route("/filters/<filter_identifier>", methods=["POST"])
@cross_origin()
def filter_preview(filter_identifier):
    return_value = process_font(filter_identifier, request, process_for_download=False)
    collect()
    return return_value


@app.route("/filters/<filter_identifier>/get", methods=["POST"])
@cross_origin()
def filter_download(filter_identifier):
    return_value = process_font(filter_identifier, request, process_for_download=True)
    collect()
    return return_value


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)

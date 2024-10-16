import traceback

from datetime import datetime
from io import BytesIO
from pathlib import Path
from flask import Flask, abort, jsonify, request
from flask_cors import CORS, cross_origin
from fontTools.ttLib import TTFont
from pan.pan import pan
from rasterizer.rasterizer import rasterize
from rotorizer.rotorizer import rotorize
from x_ray.x_ray import x_ray
from tools.generic import (
	extractOpenTypeInfo,
	extract_kerning_hb,
	fonts_to_base64,
	get_components_in_subsetted_text,
	rename_name_ttfont,
	rename_name_ufo,
)
from ufoLib2.objects.font import Font


base = Path(__file__).parent

# Define the Flask app
app = Flask(__name__)
CORS(app)
app.config["CORS_HEADERS"] = "Content-Type"

class FontProcessor:
	suffix_name_map = {
		"rotorizer": ["Rotorized Underlay", "Rotorized Overlay"],
		"rasterizer": ["Rasterized"],
		"pan": ["Panned"],
		"x_ray": ["X-Ray"],
	}

	ranges = [
		(32, 126),
	]

	def __init__(self, filter_identifier, request, process_for_download=False):
		self.filter_identifier = filter_identifier
		self.request = request
		self.process_for_download = process_for_download
		self.validate()

	def validate(self):
		"""Check if filter is valid"""
		if self.filter_identifier not in ["rasterizer", "rotorizer", "pan", "x_ray"]:
			abort(404, description="Filter not found")
		
		if not self.request.files.get("font_file"):
			raise AssertionError("Font file is required")
		
		preview_string = self.request.form.get("preview_string")
		if preview_string:
			if len(preview_string) > 30:
				raise AssertionError("Preview string is too long")
		else:
			raise AssertionError("Preview string is required")


	def is_in_ranges(self, code_point):
		"""Check if code point is in defined ranges"""
		for start, end in self.ranges:
			if start <= code_point <= end:
				return True
		return False

	def load_font(self):
		"""Load and process the font file"""
		self.font_file = self.request.files.get("font_file").read()
		self.binary_font = BytesIO(self.font_file)
		self.tt_font = TTFont(self.binary_font)
		self.units_per_em = self.tt_font["head"].unitsPerEm
		self.glyph_order = self.tt_font.getGlyphOrder()
		self.cmap = self.tt_font.getBestCmap()
		if not self.cmap:
			self.cmap = self.tt_font.getBestCmap(cmapPreferences=((1, 0), (3, 0)))
		self.cmap_reversed = {}
		for k, v in self.cmap.items():
			self.cmap_reversed.setdefault(v, []).append(k)

		preview_string = self.request.form.get("preview_string")
		self.glyph_names_to_process = self.get_glyph_names_to_process(preview_string)

	def get_glyph_names_to_process(self, preview_string):
		"""Get glyph names for processing"""
		glyph_names = []
		if self.process_for_download:
			for glyph_name, unicode_values in self.cmap_reversed.items():
				if all(self.is_in_ranges(u) for u in unicode_values):
					glyph_names.append(glyph_name)
		else:
			glyph_names = [
				self.cmap.get(ord(char), None) for char in set(preview_string)
			]
		components = get_components_in_subsetted_text(self.tt_font, glyph_names)
		return_value = [g for g in glyph_names + components if g in self.glyph_order]
		return set(glyph_names + return_value)

	def create_ufo(self):
		"""Create UFO object and extract OpenType info"""
		self.ufo = Font()
		self.ufo.info.unitsPerEm = self.tt_font["head"].unitsPerEm
		self.ufo.info.ascender = self.tt_font["hhea"].ascent
		self.ufo.info.descender = self.tt_font["hhea"].descent
		self.ufo.info.familyName = "Preview" if not self.process_for_download else self.tt_font["name"].getBestFamilyName()
		self.ufo.info.styleName = "Regular" if not self.process_for_download else self.tt_font["name"].getBestSubFamilyName()

		try:
			self.ufo.info.capHeight = self.tt_font["OS/2"].sCapHeight
			self.ufo.info.xHeight = self.tt_font["OS/2"].sxHeight
		except:
			pass

		
		if self.process_for_download:
			pass
		else:
			widths = {
				k: v[0]
				for k, v in self.tt_font["hmtx"].metrics.items()
				if k in self.glyph_names_to_process
			}
			try:
				extracted_kerning = extract_kerning_hb(
					self.font_file, widths, content=self.request.form.get("preview_string"), cmap=self.cmap
				)
				self.ufo.kerning.update(extracted_kerning)
			except Exception as e:
				print(f"Kerning extraction failed: {e}")
		
		try:
			extractOpenTypeInfo(self.tt_font, self.ufo)
		except AttributeError:
			pass

	def extract_glyphs(self):
		"""Extract glyph data for the UFO"""
		glyph_set = self.tt_font.getGlyphSet()
		for glyph_name in set(self.glyph_names_to_process):
			if glyph_name not in self.ufo:
				glyph = self.ufo.newGlyph(glyph_name)
				glyph.unicodes = self.cmap_reversed.get(glyph_name, [])
				pen = glyph.getPen()
				glyph_set_glyph = glyph_set[glyph_name]
				glyph_set_glyph.draw(pen)
				glyph.width = glyph_set_glyph.width

	def apply_filter(self):
		"""Apply the selected filter"""
		if self.filter_identifier == "rasterizer":
			resolution = int(self.request.form.get("resolution", 30))
			return [rasterize(self.ufo, self.binary_font, self.glyph_names_to_process, resolution, self.tt_font)]
		elif self.filter_identifier == "rotorizer":
			return rotorize(self.ufo, self.glyph_names_to_process, is_cff="glyf" not in self.tt_font)
		elif self.filter_identifier == "pan":
			step = int(self.request.form.get("step", 40))
			assert 60 >= step >= 30, "Step must be between 30 and 60"
			return [pan(self.ufo, step * self.units_per_em / 1000, glyph_names_to_process=self.glyph_names_to_process, shadow=self.request.form.get("shadow", False), scale_factor=self.units_per_em / 1000)]
		elif self.filter_identifier == "x_ray":
			outline_color = self.request.form.get("outline_color", "#000000")
			line_color = self.request.form.get("line_color", "#000000")
			point_color = self.request.form.get("point_color", "#000000")
			return [x_ray(self.ufo, outline_color=outline_color, line_color=line_color, point_color=point_color)]
		else:
			raise AssertionError("Unsupported filter")

	def process(self):
		"""Main process logic"""
		self.load_font()
		self.create_ufo()
		self.extract_glyphs()
		output = self.apply_filter()

		for f, font in enumerate(output):
			suffix = self.suffix_name_map[self.filter_identifier][f]
			if isinstance(font, Font):
				rename_name_ufo(font, suffix)
			else:
				rename_name_ttfont(font, suffix)

		response = fonts_to_base64(output)
		if self.process_for_download:
			return jsonify({"fonts": response}), 200
		else:
			warnings, preview_string = self.check_missing_glyphs()
			return jsonify({"fonts": response, "warnings": warnings, "preview_string": preview_string}), 200

	def check_missing_glyphs(self):
		"""Check for missing glyphs"""
		preview_string = self.request.form.get("preview_string", "")
		missing_glyphs = [char for char in preview_string if self.cmap.get(ord(char), None) is None]
		warnings = []
		if missing_glyphs:
			warnings.append(f'Your font is missing these characters: {", ".join(missing_glyphs)}')
		return warnings, "".join([char for char in preview_string if char not in missing_glyphs])


@app.route("/filters/<filter_identifier>", methods=["POST"])
@cross_origin()
def filter_preview(filter_identifier):
	try:
		processor = FontProcessor(filter_identifier, request, process_for_download=False)
		return_value = processor.process()
		return return_value
	except Exception as e:
		print(traceback.format_exc())
		return jsonify({"warnings": [f"{e.__class__.__name__}: {e}"]}), 400


@app.route("/filters/<filter_identifier>/get", methods=["POST"])
@cross_origin()
def filter_download(filter_identifier):
	processor = FontProcessor(filter_identifier, request, process_for_download=True)
	return processor.process()


if __name__ == "__main__":
	app.run(host="127.0.0.1", port=8000, debug=True)

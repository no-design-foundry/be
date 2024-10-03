from base64 import b64decode
from io import BytesIO
from pathlib import Path
from unicodedata import normalize

import pytest
from fontTools.ttLib import TTFont

base = Path(__file__).parent

test_fonts_data = []
for font_path in (base / "test_fonts").glob("*.[ot]tf"):
# for f, font_path in enumerate(Path("/System/Library/Fonts/Supplemental").glob("*.[ot]tf")):
	test_fonts_data.append(font_path)


@pytest.mark.parametrize("font_path", test_fonts_data)
def test_post_rotorizer(client, font_path):
	with open(font_path, "rb") as input_file:
		font_file_read = input_file.read()
		data = {"preview_string": "Hello World!", "depth": "20"}
		data["font_file"] = BytesIO(font_file_read), font_path.name
		response = client.post(
			"/filters/rotorizer", data=data, content_type="multipart/form-data"
		)
		response_data = response.get_json()
		assert len(response_data["fonts"]) == 2
		preview_string_characters_in_output_font = False
		for font_bytes in response_data["fonts"]:
			tt_font = TTFont(BytesIO(b64decode(font_bytes)))
			preview_string_characters_in_output_font = True
			cmap_chars = [
				normalize("NFKC", chr(value)) for value in tt_font.getBestCmap().keys()
			]
			for char in data["preview_string"]:
				if char not in cmap_chars:
					break
			assert (
				preview_string_characters_in_output_font
			), f"Character '{char}' not found in output font cmap"


@pytest.mark.parametrize("font_path", test_fonts_data)
def test_post_rasterizer(client, font_path):
	with open(font_path, "rb") as input_file:
		font_file_read = input_file.read()
		data = {"preview_string": "Hello World!", "resolution": "20"}
		data["font_file"] = BytesIO(font_file_read), font_path.name
		response = client.post(
			"/filters/rasterizer", data=data, content_type="multipart/form-data"
		)
		response_data = response.get_json()
		assert len(response_data["fonts"]) == 1
		preview_string_characters_in_output_font = False
		for font_bytes in response_data["fonts"]:
			tt_font = TTFont(BytesIO(b64decode(font_bytes)))
			preview_string_characters_in_output_font = True
			cmap_chars = [
				normalize("NFKC", chr(value)) for value in tt_font.getBestCmap().keys()
			]
			for char in data["preview_string"]:
				if char not in cmap_chars:
					break
			assert (
				preview_string_characters_in_output_font
			), f"Character '{char}' not found in output font cmap"

@pytest.mark.parametrize("font_path", test_fonts_data)
def test_post_pan(client, font_path):
	with open(font_path, "rb") as input_file:
		font_file_read = input_file.read()
		data = {"preview_string": "Hello World!"}
		data["font_file"] = BytesIO(font_file_read), font_path.name
		response = client.post(
			"/filters/pan", data=data, content_type="multipart/form-data"
		)
		response_data = response.get_json()
		assert len(response_data["fonts"]) == 1
		preview_string_characters_in_output_font = False
		for font_bytes in response_data["fonts"]:
			tt_font = TTFont(BytesIO(b64decode(font_bytes)))
			preview_string_characters_in_output_font = True
			cmap_chars = [
				normalize("NFKC", chr(value)) for value in tt_font.getBestCmap().keys()
			]
			for char in data["preview_string"]:
				if char not in cmap_chars:
					break
			assert (
				preview_string_characters_in_output_font
			), f"Character '{char}' not found in output font cmap"

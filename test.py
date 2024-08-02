from fontTools.pens.freetypePen import FreeTypePen
from fontTools.ttLib import TTFont
from pathlib import Path
from fontTools.misc.transform import Offset

base = Path(__file__).parent

freetype_pen = FreeTypePen([])

font = TTFont(base/"tests"/"test_fonts"/'Honey Crepes.ttf')
gs = font.getGlyphSet()
glyph = gs['a']
glyph.draw(freetype_pen)

width, ascender, descender = glyph.width, font['OS/2'].usWinAscent, -font['OS/2'].usWinDescent
height = ascender - descender

freetype_pen.show(width=width, height=height, transform=Offset(0, -descender))

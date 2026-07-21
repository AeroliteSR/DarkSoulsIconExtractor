from PIL import Image, ImageDraw
import numpy as np
from io import BytesIO
from pathlib import Path
from PySide6.QtGui import QPixmap, QImage
from DSTextureStudio.Enums import Game
from DSTextureStudio.GUI import gameTypeDialog
from DSTextureStudio.GameInfo import LAYOUT_PATHS
from DSTextureStudio.Utilities import path_has_sequence
from soulstruct.dcx import core
import tempfile

def getLayoutData(dcx_path):
    with open(dcx_path, "rb") as f:
        decompressed_bytes, _ = core.decompress(f)
        start_index = decompressed_bytes.find(b"<TextureAtlas")
        xml_bytes = decompressed_bytes[start_index:]
        xml_text = xml_bytes.decode("utf-8", errors="ignore").replace("\x00", "")
        return f"<Root>{xml_text}</Root>"

def getFreeSpace(atlas_size, used_rects, w, h, step=4, padding=2):
    atlas_w, atlas_h = atlas_size

    for y in range(padding, atlas_h - h - padding, step):
        for x in range(padding, atlas_w - w - padding, step):

            new_rect = (x - padding, y - padding, x + w + padding, y + h + padding)

            overlap = False
            for r in used_rects:
                if not (
                    new_rect[2] <= r[0] or  # left
                    new_rect[0] >= r[2] or  # right
                    new_rect[3] <= r[1] or  # above
                    new_rect[1] >= r[3]     # below
                ):
                    overlap = True
                    break

            if not overlap:
                return x, y

    return None

def cleanByAlpha(img: Image.Image, threshold: int = 5) -> Image.Image:
    """Zero RGB values where alpha <= threshold."""
    arr = np.array(img)
    mask = arr[..., 3] <= threshold
    arr[mask, :3] = 0
    return Image.fromarray(arr, "RGBA")

def parseGameType(path) -> Game:
    game_type = None
    parts = Path(path).parts

    if "PS3_GAME" in parts:
        game_type = 'Demon\'s Souls'
    if path_has_sequence(parts, ["steamapps", "common", "DARK SOULS REMASTERED"]):
        game_type = 'Dark Souls 1'
    elif path_has_sequence(parts, ["steamapps", "common", "Dark Souls II Scholar of the First Sin"]):
        game_type = 'Dark Souls 2'
    elif path_has_sequence(parts, ["steamapps", "common", "DARK SOULS III"]):
        game_type = 'Dark Souls 3'
    elif path_has_sequence(parts, ["Bloodborne", "CUSA03173", "dvdroot_ps4"]):
        game_type = 'Bloodborne'
    elif path_has_sequence(parts, ["steamapps", "common", "Sekiro"]):
        game_type = 'Sekiro'
    elif path_has_sequence(parts, ["steamapps", "common", "ARMORED CORE VI FIRES OF RUBICON"]):
        game_type = "Armored Core 6"
    elif path_has_sequence(parts, ["steamapps", "common", "ELDEN RING NIGHTREIGN"]):
        game_type = 'Nightreign'
    elif path_has_sequence(parts, ["steamapps", "common", "ELDEN RING"]):
        game_type = 'Elden Ring'

    return Game(game_type)

def createDebugGrid(image, subtextures):
    """Outputs a png with grid lines for debugging"""
    if len(subtextures) == 0:
        return image
    
    debug = image.copy()
    draw = ImageDraw.Draw(debug)

    for icn in subtextures:
        width = icn.width
        height = icn.height
        x = icn.x
        y = icn.y
        draw.rectangle([x, y, x + width, y + height], outline="red", width=1)

    return debug

def pil2Qpixmap(pil_img) -> QPixmap:
    """Convert PIL Image to QPixmap without destroying the aspect ratio lol"""
    data = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)

def getPngSize(pil_img):
    """Simulate a png export to get file size."""
    buf = BytesIO()
    pil_img.save(buf, format="PNG")
    return len(buf.getvalue())

def checkGame(path: str) -> Game:
    game = parseGameType(path=path)
    if game.name is None:
        game = gameTypeDialog()
    return game

def createBlankImage(dimensions: tuple) -> str:
    img = Image.new("RGBA", dimensions, (0, 0, 0, 0))
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img.save(temp_file.name, "PNG")

    return temp_file.name

def getLayoutPath(game, **kwargs):
    """
    Returns full virtual path for a layout file including common root.
    
    Expects:
    
    file - parent file, eg. '01_Common`
    
    format_mode - what resolution the file is for. generally hi/low
    
    layout_name - name of the .layout file"""
    return LAYOUT_PATHS[game].format(**kwargs)

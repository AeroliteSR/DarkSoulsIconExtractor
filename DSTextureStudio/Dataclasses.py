import logging
from dataclasses import dataclass, field
from textwrap import indent
from typing import Optional, Callable
from PIL import Image
from pathlib import Path
from copy import deepcopy
from io import BytesIO
from soulstruct.containers.tpf import TPFTexture, TPFPlatform, TPF
from soulstruct.containers import Binder, BinderEntry, BinderVersion, BinderVersion4Info
from soulstruct.base.textures.dds import DDS
from soulstruct.base.textures.dds.swizzle import swizzle_dds_bytes_ps4
from soulstruct.dcx import DCXType
from DSTextureStudio.Utilities import path_has_sequence, findLast
from DSTextureStudio.Enums import ImageType, Game, Resolution
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)
# region LAYOUT
@dataclass(slots=True)
class AtlasLayout:
    path: Path # internal entry paths
    element: ET.Element = field(default_factory=lambda: ET.Element("TextureAtlas"))

    # region Properties

    @property
    def name(self) -> str:
        return Path(self.imagePath).stem

    @property
    def commonPath(self) -> Path:
        return Path(self.path).parent

    @property
    def res(self) -> Resolution|None:
        for r in ["Hi", "Low", "High"]:
            if path_has_sequence(self.path.parts, [r]):
                return Resolution.from_str(r)
        return None
    
    @property
    def imagePath(self) -> str:
        return self.element.get("imagePath")
    
    @property
    def xml(self) -> str:
        return ET.tostring(self.element, encoding='utf-8', method='xml')

    # region Build
    
    @classmethod
    def from_element(cls, path, el: ET.Element) -> "AtlasLayout":
        return cls(path=path,element=el)

    @classmethod
    def from_binder(cls, binder: Binder|Path) -> list["AtlasLayout"]:
        if isinstance(binder, Path):
            binder = Binder(binder)

        return [
            cls(
                path=Path(entry.path),
                element=ET.fromstring(entry.data, parser=ET.XMLParser(encoding="utf-8"))
            ) for entry in binder
        ]
    
    @classmethod
    def create(cls, imagePath: str, entryPath: str, subtextures: list[SubTexture], dimensions: Optional[tuple[int, int]] = None) -> "AtlasLayout":
        """Creates a new AtlasLayout entry.
        
        imagePath - the internal path name written in each TextureAtlas element in the .layout files
        
        entryPath - the internal path name OF each .layout file and its BinderEntry

        subtextures - list of SubTexture objects to add to the Layout's root
        
        dimensions - optional TextureAtlas properties for Nightreign. Expects tuple[width, height]"""

        root = ET.Element("TextureAtlas")
        root.set("imagePath", imagePath)
        if dimensions is not None:
            root.set("width", str(dimensions[0]))
            root.set("height", str(dimensions[1]))

        obj = cls(path=entryPath, element=root)
        obj.add_subtextures(subtextures)
        return obj

    def build(layout_objs: list[AtlasLayout], output: Path) -> None:
        """
        Writes a list of AtlasLayouts to sblytbnd.dcx

        layout_objs - list of all loaded AtlasLayouts to be added as entries to the Binder

        output - where to write dcx to"""

        binder = Binder(
            version=BinderVersion.V4,
            dcx_type=DCXType.DCX_KRAK,
            v4_info=BinderVersion4Info(False, False, True, 4)
        )

        for atlas in layout_objs:
            binder.add_entry(
                entry=BinderEntry(
                    data=ET.tostring(atlas.element, encoding='utf-8', method='xml'),
                    entry_id=binder.get_first_new_entry_id_in_range(0, 1000000),
                    path=str(atlas.path),
                    flags=0x2
                )
            )

        binder.write(output)

    # region Subtexture Handling

    def iter_subtextures(self) -> list[ET.Element[str]]:
        return self.element.findall("SubTexture")

    def has_subtexture(self, name: str) -> bool:
        return any(st.get("name") == name for st in self.iter_subtextures())

    def add_subtextures(self, subtextures: list[SubTexture]) -> None:
        """Adds a list of SubTexture objects to the parent AtlasLayout's Element"""
        atlas = self.element
        for sub in subtextures:
            name = sub.name
            if not name.endswith('.png'):
                name = f"{name}.png"

            if self.has_subtexture(name):
                logger.info("Subtexture entry `%s` already exists in layout file. Skipping.", name)
                continue

            item = ET.SubElement(atlas, "SubTexture", {
                "name": name,
                "x": str(sub.x),
                "y": str(sub.y),
                "width": str(sub.width),
                "height": str(sub.height),
                "half": str(int(sub.half))})
            
            logger.info("Adding Subtexture to %s:\n%s", sub.parent, ET.tostring(item, encoding='unicode'))
            
            if len(atlas) == 1:
                atlas.text = '\r\n\t'
            else:
                atlas[-2].tail = '\r\n\t'

            item.tail = '\r\n'

    # region Helpers

    def getImagePath(game: Game, **kwargs):
        match game.name:
            case "Nightreign":
                imgpath = r"W:\CL\data\Target\INTERROOT_win64\menu\ScaleForm\Tif\01_Common\{res}\{atlas_name}.tif" 
            case "Armored Core 6":
                imgpath = r"W:\FNR\data\Menu\ScaleForm\Tif\01_Common\{atlas_name}\{res}\exp\{atlas_name}.png"
            case _:
                imgpath = r"{atlas_name}.png"

        return imgpath.format(**kwargs)

    def __repr__(self) -> str:
        return (
            f"AtlasLayout(\n"
            f"    Name = {self.name}\n"
            f"    Internal Path = {self.path}\n"
            f"    imagePath = {self.imagePath}\n"
            f"    Element = {self.element.__repr__()}\n"
            f"    Subtexture Count = {len(self.iter_subtextures())}\n"
            f")"
        )
# region ATLAS
@dataclass(slots=True)
class Atlas:
    name: str
    parent: Optional[Path] # when None, is written as a standalone file 

    texture: TPFTexture
    dimensions: Optional[tuple[int, int]] = None # only needed for custom Atlases, used for writing TextureAtlas xml properties

    subtextures: list[SubTexture] = field(default_factory=list)

    # Modifications
    replacements: list[SubTexture|Image.Image] = field(default_factory=list)
    additions: list[SubTexture] = field(default_factory=list)

    # region Properties
    @property
    def itype(self) -> ImageType:
        """Checks if self Atlas object is an atlas with SubTextures or just a plain Texture"""
        return ImageType.Atlas if self.count > 0 else ImageType.Texture

    @property
    def count(self) -> int:
        """Returns number of child SubTexture objects."""
        return len(self.subtextures)

    @property
    def viewable(self) -> Image.Image:
        """Returns a viewable Image of self.texture's dds"""
        # existing textures return due to being a valid DDS, custom are not swizzled; PC skips deswizzling
        # this covers both PC and PS4 games unlike BytesIO(texture.data) which wouldn't work on headerless BB textures
        dds = self.texture.get_headerized_data(TPFPlatform.PC) 
        return Image.open(BytesIO(dds)).convert("RGBA")

    @property
    def modified(self) -> bool:
        return (len(self.replacements) + len(self.additions)) > 0

    @property
    def modifications(self) -> dict:
        return {
            "Name": self.name,
            "Additions": self.additions,
            "Replacements": self.replacements
        }
    
    # region Helpers
    def renameAttrParent(self, attr, new_name):
        for s in getattr(self, attr):
            if s.parent is not None:
                s.parent = new_name

    def rename(self, new_name) -> bool:
        """Renames Atlas object. Returns True if successful"""
        if new_name != self.name:
            self.name = new_name
            self.texture.stem = new_name
            for i in ["subtextures", "additions", "replacements"]:
                self.renameAttrParent(i, new_name)
            return True
        return False

    # region Subtexture Helpers
    def add(self, subtexture: SubTexture) -> None:
        """Appends a SubTexture to self list"""
        self.subtextures.append(subtexture)

    def match(self, name: str, attr: str = "subtextures") -> tuple[SubTexture, int]|tuple[None, None]:
        """Helper function to find SubTexture and index from self list"""
        for idx, sub in enumerate(getattr(self, attr)):
            if sub.name == name:
                return sub,idx
        return None, None

    def fetch(self, name: str) -> SubTexture|None:
        """Returns SubTexture object of a certain name belonging to parent Atlas"""
        sub,_ = self.match(name)
        return sub if sub is not None else None
    
    def subrename(self, name: str, new_name: str) -> None:
        """Renames SubTextures of a certain name from the Atlas."""
        sub,_ = self.match(name)
        if sub is not None:
            sub.name = new_name
        
    def rem(self, name: str) -> SubTexture|None:
        """Removes SubTextures of a certain name from the Atlas. Returns like {}.pop()"""
        _,idx = self.match(name)
        if idx is not None:
            return self.subtextures.pop(idx)
        return None

    def replace(self, name: str, image: Image.Image) -> None:
        """Finds SubTexture object of 'name' and replaces its 'img' field with a provided image"""
        sub,_ = self.match(name)
        if sub is not None:
            sub.img = image

    # region Writing     
    def writetpf(self, output: Path, dcx_type: DCXType = DCXType.Null, encoding: int = 1, flags: int = 3, platform: TPFPlatform = TPFPlatform.PC):
        """Writes a .tpf file to disk using info from self Atlas object. Mostly useful for DS2 files. Output is parent dir."""
        TPF(platform=platform,
            encoding_type=encoding,
            tpf_flags=flags,
            textures=[self.texture],
            dcx_type=dcx_type).write((output / self.name).with_suffix(".tpf"))
        logger.info("Wrote standalone file with compression '%s':\n%s", dcx_type.name, output/self.name)

    def compileTexture(self) -> Image.Image:
        """Builds new Image() from self, applying all modifications."""
        IMG = self.viewable

        for add in self.additions:
            if add.parent != self.name or add.img is None:
                continue

            img = add.img
            x, y = add.pos

            if y + img.height > IMG.height:
                new_height = y + img.height
                new_img = Image.new("RGBA", (IMG.width, new_height), (0, 0, 0, 0))
                new_img.paste(IMG, (0, 0))
                IMG = new_img

            IMG.paste(img, (x, y))

        last_full_replacement = findLast(self.replacements, Image.Image)
        if last_full_replacement is not None: # replacements contain an Image() object, entire atlas will be replaced
            IMG = self.replacements[last_full_replacement]
        else: # no full replacements, append subtexture replacements
            for rep in self.replacements:
                rep.paste_into(IMG)

        return IMG

    def add_to_TPF(self, _TPF: TPF, swizzle: bool = False):
        """Adds self texture to a TPF binder."""
        texture: TPFTexture = self.texture

        if swizzle:
            dds = DDS.from_bytes(texture.get_headerized_data(TPFPlatform.PC)) # dont deswizzle as image is already not swizzled
            swizzled = swizzle_dds_bytes_ps4(
                deswizzled=dds.data,
                dxgi_format=texture.console_info.dxgi_format,
                width=texture.console_info.width,
                height=texture.console_info.height,
            )
            texture.data = swizzled

        _TPF.textures.append(texture)


    def __repr__(self) -> str:
        return (
            f"Atlas(\n"
            f"    Name = {self.name}\n"
            f"    Parent = {self.parent}\n"
            f"    Subtexture Count = {self.count}\n"
            f"    Dimensions = {self.dimensions}\n"
            f"    Texture = \n{indent(self.texture.__repr__(), "        ")}\n" 
           # f"    Subtextures = \n{indent(self.subtextures.__repr__(), "        ")}\n"
            f")"
        )
# region SUBTEXTURE
@dataclass(slots=True)
class SubTexture:
    name: str
    x: int
    y: int
    width: int
    height: int

    img: Optional[Image.Image] = None

    parent: Optional[str] = None # name of parent atlas
    vanilla: Optional[bool] = False # set to True on load. Custom additions are False, and therefore can be filtered for 

    blank: bool = False
    half: Optional[bool] = False # what even is this bro

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)

    def setpos(self, x, y):
        self.x = x
        self.y = y

    def rename(self, new_name):
        self.name = new_name

    def box(self, padding: int = 0) -> tuple[int, int, int, int]:
        """Return tuple of coordinates for a box to crop to this subtexture. Allows optional padding"""
        return (self.x - padding, self.y - padding, self.x + self.width + padding, self.y + self.height + padding)
    
    def paste_into(self, atlas_img: Image.Image, mask: Image.Image | None = None) -> None:
        """Pastes self into an image"""
        if self.img is None:
            raise Exception("SubTexture object does not contain an image.")
        atlas_img.paste(self.img, self.box(), mask=mask)

    def __repr__(self) -> str:
        return (
            f"SubTexture(\n"
            f"    Name = {self.name}\n"
            f"    Parent = {self.parent}\n"
            f"    Is Vanilla = {self.vanilla}\n"
            f"    Image = {self.img}\n"
            f"    Coordinates = {self.pos}\n"
            f"    Dimensions = {self.width}x{self.height}\n"
            f"    Blank = {self.blank}\n"
            f"    Half = {self.half}\n"
            f")"
        )
    
@dataclass
class Command:
    func: Callable
    help: str


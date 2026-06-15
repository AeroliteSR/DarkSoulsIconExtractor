from dataclasses import dataclass, field
from textwrap import indent
from typing import Optional
from PIL import Image
from pathlib import Path
from soulstruct.containers.tpf import TPFTexture, TPFPlatform, TPF
from soulstruct.containers import Binder, BinderEntry, BinderVersion, BinderVersion4Info
from soulstruct.dcx import DCXType
from .Helpers import replaceTerms
from .Enums import ImageType
import xml.etree.ElementTree as ET

@dataclass(slots=True)
class AtlasLayout:
    element: ET.Element = field(default_factory=lambda: ET.Element("TextureAtlas"))

    @property
    def name(self) -> str:
        return Path(self.imagePath).stem
    
    @property
    def imagePath(self) -> str:
        return self.element.get("imagePath")
    
    @property
    def xml(self) -> str:
        return ET.tostring(self.element, encoding='utf-8', method='xml')
    
    @classmethod
    def from_element(cls, el: ET.Element) -> "AtlasLayout":
        return cls(element=el)
    
    @classmethod
    def create(cls, image_path: str, subtextures: list[SubTexture]) -> "AtlasLayout":
        """Creates a new AtlasLayout entry."""
        root = ET.Element("TextureAtlas")
        root.set("imagePath", image_path)

        obj = cls(element=root)
        obj.add_subtextures(subtextures)
        return obj

    def build(layout_objs: list[AtlasLayout], root: Path|str, output: Path) -> None:
        """
        Writes a list of AtlasLayouts to sblytbnd.dcx

        layout_objs - list of all loaded AtlasLayouts

        root - the texture root for each Layout entry

        output - where to write dcx to"""

        binder = Binder(
            version=BinderVersion.V4,
            dcx_type=DCXType.DCX_KRAK,
            v4_info=BinderVersion4Info(False, False, True, 4)
        )

        for atlas in layout_objs:
            xml_bytes = ET.tostring(atlas.element, encoding='utf-8', method='xml')
            layout_name = replaceTerms(atlas.imagePath, {'.png': '.layout', '.tif': '.layout'})

            entry = BinderEntry(
                data=xml_bytes,
                entry_id=binder.get_first_new_entry_id_in_range(0, 1000000),
                path=str(root / layout_name),
                flags=0x2
            )

            binder.add_entry(entry=entry)

        binder.write(output)

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
                print(f"Subtexture entry `{name}` already exists in layout file. Skipping.")
                continue

            item = ET.SubElement(atlas, "SubTexture", {
                "name": name,
                "x": str(sub.x),
                "y": str(sub.y),
                "width": str(sub.width),
                "height": str(sub.height),
                "half": str(int(sub.half))})
            
            print(f"Adding Subtexture to {sub.parent}:\n{ET.tostring(item, encoding='unicode')}")
            
            if len(atlas) == 1:
                atlas.text = '\r\n\t'
            else:
                atlas[-2].tail = '\r\n\t'

            item.tail = '\r\n'

    def __repr__(self) -> str:
        return (
            f"AtlasLayout(\n"
            f"    name = {self.name}\n"
            f"    imagePath = {self.imagePath}\n"
            f"    element = {self.element.__repr__()}\n"
            f"    subtexture count = {len(self.iter_subtextures())}\n"
            f")"
        )

@dataclass(slots=True)
class Atlas:
    name: str
    texture: TPFTexture
    parent: Path

    subtextures: list[SubTexture] = field(default_factory=list)

    @property
    def itype(self) -> ImageType:
        """Checks if self Atlas object is an atlas with SubTextures or just a plain Texture"""
        return ImageType.Atlas if self.count > 0 else ImageType.Texture

    @property
    def count(self) -> int:
        """Returns number of child SubTexture objects."""
        return len(self.subtextures)
    
    def add(self, subtexture: SubTexture) -> None:
        """Appends a SubTexture to self list"""
        self.subtextures.append(subtexture)

    def match(self, name: str) -> tuple[SubTexture, int]|None:
        """Helper function to find SubTexture and index from self list"""
        for idx, sub in enumerate(self.subtextures):
            if sub.name == name:
                return sub,idx
        return None

    def fetch(self, name: str) -> SubTexture|None:
        """Returns SubTexture object of a certain name belonging to parent Atlas"""
        return self.match(name)[0]
    
    def rename(self, name: str, new_name: str) -> SubTexture|None:
        """Renames SubTextures of a certain name from the Atlas."""
        sub = self.match(name)[0]
        sub.name = new_name
        
    def rem(self, name: str) -> SubTexture|None:
        """Removes SubTextures of a certain name from the Atlas. Returns like {}.pop()"""
        idx = self.match(name)[1]
        return self.subtextures.pop(idx)

    def replace(self, name: str, image: Image.Image) -> None:
        """Finds SubTexture object of 'name' and replaces its 'img' field with a provided image"""
        sub = self.match(name)[0]
        sub.img = image
            
    def writetpf(self, encoding: int = 2, flags: int = 3, platform: TPFPlatform = TPFPlatform.PC):
        """Writes a .tpf file to disk using info from self Atlas object. Mostly useful for DS2 files."""
        TPF(platform=platform,
            encoding_type=encoding,
            tpf_flags=flags,
            textures=[self.texture]).write(f"{self.parent.parent/self.name}.tpf")

    def __repr__(self) -> str:
        return (
            f"Atlas(\n"
            f"    name = {self.name}\n"
            f"    parent = {self.parent}\n"
            f"    subtexture count = {self.count()}\n"
            f"    texture = \n{indent(self.texture.__repr__(), "        ")}\n"
            f"    subtextures = \n{indent(self.subtextures.__repr__(), "        ")}\n"
            f")"
        )

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
            f"    name = {self.name}\n"
            f"    parent = {self.parent}\n"
            f"    image = {self.img}\n"
            f"    coordinates = {self.pos}\n"
            f"    dimensions = {self.width}x{self.height}\n"
            f"    blank = {self.blank}\n"
            f"    half = {self.half}\n"
            f")"
        )
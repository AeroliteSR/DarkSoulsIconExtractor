from dataclasses import dataclass, field
from typing import Optional
from PIL import Image
from pathlib import Path
from soulstruct.containers.tpf import TPFTexture
from soulstruct.containers import Binder, BinderEntry, BinderVersion, BinderVersion4Info
from soulstruct.dcx import DCXType
from .Helpers import replaceTerms
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

    def build(layout_objs: list[AtlasLayout], root: Path|str, output: Path):
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

    def iter_subtextures(self):
        return self.element.findall("SubTexture")

    def has_subtexture(self, name: str) -> bool:
        return any(st.get("name") == name for st in self.iter_subtextures())

    def add_subtextures(self, subtextures: list[SubTexture]):
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
            f")"
        )

@dataclass(slots=True)
class Atlas:
    name: str
    texture: TPFTexture
    parent: Path

@dataclass(slots=True)
class SubTexture:
    name: str
    x: int
    y: int
    width: int
    height: int

    img: Optional[Image.Image] = None

    parent: Optional[str] = None
    blank: bool = False
    half: Optional[bool] = False

    def pos(self):
        return (self.x, self.y)

    def box(self, padding: int = 0) -> tuple[int, int, int, int]:
        """Return tuple of coordinates for a box to crop to this subtexture. Allows optional padding"""
        return (self.x - padding, self.y - padding, self.x + self.width + padding, self.y + self.height + padding)
    
    def paste_into(self, atlas_img: Image.Image, mask: Image.Image | None = None) -> None:
        """Pastes self into an image"""
        if self.img is None:
            raise Exception("SubTexture object does not contain an image.")
        atlas_img.paste(self.img, self.box(), mask=mask)
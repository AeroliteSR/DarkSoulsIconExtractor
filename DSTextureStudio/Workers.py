from __future__ import annotations
# Basic Modules
import os
import numpy as np
from io import BytesIO
from copy import deepcopy
from tempfile import NamedTemporaryFile
import xml.etree.ElementTree as ET
from pathlib import Path
import traceback
# GUI
from PySide6.QtCore import QObject, Signal
# Soulstruct
from soulstruct.containers.tpf import TPF, TPFPlatform, TPFTexture
from soulstruct.dcx import core
# Custom
from DSTextureStudio.GameInfo import Maps, Types
from DSTextureStudio.Dataclasses import *
from DSTextureStudio.Enums import *
from DSTextureStudio.Helpers import *

class LoadWorker(QObject):
    progress = Signal(int, str)   # percent, message
    finished = Signal(object, object, object, str)  # atlases, loaded dcx files, parsed xml data, error msg

    def __init__(self, file_mappings, game: Game):
        super().__init__()
        self.file_mappings = file_mappings
        self.game = game
        self.LOADED_DCX_FILES = {}
        self.LAYOUT_DATA = {}

    def run(self):
        match self.game.type:
            case GameType.MODERN:
                self.processModern()
            case GameType.OLD | GameType.PS:
                self.processOld()
            case _:
                self.processOld()

    def handleUnpack(self, path):
        if self.game.type == GameType.PS:
            try:
                tex,_ = core.decompress(path)
                tpfdcx = TPF.from_bytes(tex)
            except core.DCXError:
                tpfdcx = TPF(path) # it's probably a tpf file, may as well try
        else:
            tpfdcx = TPF(path)

        self.LOADED_DCX_FILES[path] = tpfdcx

        for texture in tpfdcx.textures:
            if self.game.type == GameType.PS:
                match self.game.name:
                    case "Bloodborne":
                        platform = TPFPlatform.PS4
                    case "Demon's Souls":
                        platform = TPFPlatform.PC

                dds_data = texture.get_headerized_data(platform)

                texture = TPFTexture(    
                    stem=texture.stem,
                    data=dds_data,
                    platform=platform,
                    console_info=texture.console_info,
                    format=texture.format,
                    texture_type=texture.texture_type,
                    mipmap_count=texture.mipmap_count,
                    texture_flags=texture.texture_flags)
            
            yield texture

    def generateTextDict(self, dcx_path, percent):
        textures_dict: dict = {}
        self.progress.emit(percent, f"Unpacking {dcx_path.stem}...")

        paths = []
        if dcx_path.is_dir():
            paths = [Path(dcx_path) / f for f in os.listdir(dcx_path) if f.endswith('tpf.dcx') or f.endswith('.tpf')]
        else:
            paths = [Path(dcx_path)]

        for path in paths:
            for texture in self.handleUnpack(path):
                textures_dict[texture.stem] = texture

        self.progress.emit(percent, f"Loaded {dcx_path.stem}")
        return textures_dict

    def processModern(self):
        try:
            atlases: dict[str, Atlas] = {}
            total_files = len(self.file_mappings)

            self.progress.emit(0, f'Loading {total_files} files...')
            for f_idx, file in enumerate(self.file_mappings, 1):
                percent = int(f_idx / total_files * 100 - 1)
                if isinstance(file, dict):
                    layout_path = file['layout']
                    textures_dict: dict = self.generateTextDict(file['file'], percent)

                    layout_xml = getLayoutData(layout_path)
                    root = ET.fromstring(layout_xml, parser=ET.XMLParser(encoding="utf-8"))
                    self.progress.emit(percent, "Parsing layout XML...")

                    atlas_nodes = [AtlasLayout.from_element(el) for el in root.findall("TextureAtlas")]
                    self.LAYOUT_DATA[file['file']] = atlas_nodes
                    total_atlases = len(atlas_nodes)

                    if total_atlases == 0:
                        self.progress.emit(100, "No atlases found")
                        self.finished.emit({}, {}, {})
                        return

                    for texture_atlas in atlas_nodes:
                        filepath = texture_atlas.imagePath
                        filename = Path(filepath).stem

                        if filename not in textures_dict:
                            self.progress.emit(int(f_idx / total_files * 100), f"{filename} not found, skipping.")
                            continue

                        subtextures = [SubTexture(name=Path(sub.get("name")).stem,
                                                  parent=filename,
                                                  x=int(sub.get("x")),
                                                  y=int(sub.get("y")),
                                                  width=int(sub.get("width")),
                                                  height=int(sub.get("height")),
                                                  blank=False,
                                                  vanilla=True,
                                            ) for sub in texture_atlas.iter_subtextures()]

                        atlases[filename] = Atlas(name=filename,
                                                  texture=textures_dict[filename],
                                                  parent=file['file'],
                                                  subtextures=subtextures
                                                )

                elif isinstance(file, Path):
                    textures_dict: dict = self.generateTextDict(file, percent)
                    # add any textures that were not included in the layout
                    for name, texture in textures_dict.items():
                        if name not in atlases:
                            atlases[name] = Atlas(name=name, texture=texture, parent=file, subtextures=[]) # no layout info since single textures go to atlases

            self.finished.emit(atlases, self.LOADED_DCX_FILES, self.LAYOUT_DATA, "")
            self.progress.emit(100, 'Successfully loaded all files!')

        except Exception as e:
            self.progress.emit(0, f"Error: {e}")
            self.finished.emit({}, {}, {}, {}, traceback.format_exc())

    def processOld(self):  
        try:
            atlases: dict[str, Atlas] = {}
            total_files = len(self.file_mappings)

            for f_idx, file in enumerate(self.file_mappings, 1):
                percent = int(f_idx / total_files * 100 - 1)
                textures_dict: dict = self.generateTextDict(file, percent)

                for name, texture in textures_dict.items():
                    atlases[name] = Atlas(name=name, texture=texture, parent=file, subtextures=[])
                    dds = texture.get_dds()
                    image = Image.open(BytesIO(dds.to_bytes())).convert("RGBA")

                    texmap = Maps.TextureDimensions[self.game.name]
                    dimensions = texmap.get(name, None)
                    if dimensions:
                        tile_width, tile_height = dimensions['width'], dimensions['height']

                        atlas_width, atlas_height = dds.header.width, dds.header.height
                        tiles_per_row = atlas_width // tile_width
                        tiles_per_column = atlas_height // tile_height

                        total_tiles = tiles_per_row * tiles_per_column

                        for idx in range(total_tiles):
                            row = idx // tiles_per_row
                            col = idx % tiles_per_row
                            x = col * tile_width
                            y = row * tile_height

                            tile = image.crop((x, y, x + tile_width, y + tile_height))
                            alpha = np.array(tile.getchannel("A"))
                            opacity_ratio = np.count_nonzero(alpha) / alpha.size
                            isBlank: bool = opacity_ratio < 0.01

                            atlases[name].add(SubTexture(name=str(idx),
                                                         parent=name,
                                                         x=x,
                                                         y=y,
                                                         width=tile_width,
                                                         height=tile_height,
                                                         blank=isBlank,
                                                         vanilla=True
                                                    ))
            
                        self.progress.emit(percent, f"Processed {name}")

            self.finished.emit(atlases, self.LOADED_DCX_FILES, {}, "")

        except Exception as e:
            self.progress.emit(0, f"Error: {e}")
            self.finished.emit({}, {}, {}, traceback.format_exc())

class ExtractWorker(QObject):
    progress = Signal(int, str) # percent, message
    finished = Signal(bool) # success

    def __init__(self, atlases, output_dir, loader, tasks=None, mode=ExportMode.SUBTEXTURE, filetype='png', gridOverlay=False):
        super().__init__()
        self.atlases = atlases
        self.output_dir = Path(output_dir)
        self.pilLoader = loader
        self.tasks = tasks if tasks is not None else []
        self.mode = mode
        self.filetype = filetype
        self.gridOverlay = gridOverlay
        self._interrupted = False

    def interrupt(self):
        self._interrupted = True

    def exportImg(self, image, filename, out_path, progress, message):
        out_path = Path(out_path)
        if not out_path.exists():
            out_path.mkdir(parents=True, exist_ok=True)
        if not filename.endswith('.png'):
            filename = f"{filename}.png"
        image.save(out_path / filename)
        self.progress.emit(progress, message)

    def run(self):
        if not self.tasks: # dump mode
            match self.mode:
                case ExportMode.ATLAS:
                    if not self.atlases:
                        self.finished.emit(False)
                        return

                    for atlas_name in self.atlases:
                        self.tasks.append((atlas_name, None))

                case ExportMode.SUBTEXTURE:
                    if not any([a.count>0 for a in self.atlases.values()]):
                        self.finished.emit(False)
                        return

                    for atlas_name,_atlas in self.atlases.items():
                            for st in _atlas.subtextures:
                                self.tasks.append((atlas_name, st))

        total = len(self.tasks)
        for i, (atlas_name, st) in enumerate(self.tasks, 1):
            if self._interrupted:
                break
            
            match self.filetype:
                case 'dds':
                    texture: TPFTexture = self.atlases[atlas_name].texture
                    output_path = Path(self.output_dir) / ".Atlases" / f"{atlas_name}.dds"
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    texture.write_dds(output_path)
                    self.progress.emit(100, f"Exported atlas: {atlas_name}")

                case _:
                    atlas_img = self.pilLoader(atlas_name=atlas_name)
                    percent = int(i / total * 100 - 1)

                    match self.mode:
                        case ExportMode.ATLAS:
                            out_path = self.output_dir / '.Atlases'
                            filename = atlas_name
                            message = f"Exported atlas: {atlas_name}"

                            if self.gridOverlay:
                                atlas_img = createDebugGrid(atlas_img, self.atlases[atlas_name].subtextures)

                        case ExportMode.SUBTEXTURE:
                            out_path = self.output_dir / atlas_name
                            filename = st.name
                            message = f"Exported {filename} from {atlas_name}"
                            atlas_img = atlas_img.crop(st.box()) # crop if in subtexture mode

                    self.exportImg(image=atlas_img, filename=filename, out_path=out_path, progress=percent, message=message)

        self.finished.emit(True)

class WriteWorker(QObject):
    finished = Signal(bool, str, Path)  # success, message

    def __init__(self, new_atlases, replacements, additions, loaded_files, layouts, getPilImage, game, resolutions):
        super().__init__()
        self.new_atlases = new_atlases
        self.replacements = replacements
        self.additions = additions
        self.getPilImage = getPilImage
        self.LOADED_DCX_FILES = loaded_files
        self.LAYOUT_FILES = layouts
        self.game = game
        self.RESOLUTIONS = resolutions

    def buildOperations(self):
        print("Building operations map...")

        dcx_ops = {}

        # new atlases
        for dcx_path, atlases in self.new_atlases.items():
            base_name = Path(dcx_path)
            dcx_ops.setdefault(base_name, {"new_atlases": [], "atlases": {}})
            dcx_ops[base_name]["new_atlases"].extend(atlases)

        # replacements
        for dcx_path, atlases in self.replacements.items():
            base_name = Path(dcx_path)
            dcx_ops.setdefault(base_name, {"new_atlases": [], "atlases": {}})

            for atlas_name, changes in atlases.items():
                dcx_ops[base_name]["atlases"].setdefault(atlas_name, {"replacements": {}, "additions": []})
                dcx_ops[base_name]["atlases"][atlas_name]["replacements"].update(changes)

        # Additions
        for dcx_path, add_data in self.additions.items():
            base_name = Path(dcx_path)

            dcx_ops.setdefault(base_name, {"new_atlases": [], "atlases": {}})

            additions_by_atlas = {}

            for sub in add_data["additions"]:
                if sub.vanilla:
                    continue

                additions_by_atlas.setdefault(sub.parent, []).append(sub)

            for atlas_name, subs in additions_by_atlas.items():
                dcx_ops[base_name]["atlases"].setdefault(atlas_name, {"replacements": {}, "additions": []})
                dcx_ops[base_name]["atlases"][atlas_name]["additions"].extend(subs)

        # Layout handling
        for dcx_name, data in dcx_ops.items():
            base_name = Path(dcx_name)

            if dcx_name not in self.LAYOUT_FILES:
                continue

            print(f"Processing layout for: {base_name}")

            layout_objs = list(self.LAYOUT_FILES[dcx_name])

            layout_map = {
                replaceTerms(Path(layout.imagePath).stem, {"_h": "", "_l": ""}): layout # atlas name to AtlasLayout objects
                for layout in layout_objs
            }

            filename = base_name.name.split('.')[0]
            if self.game.name == "Nightreign":
                filename = replaceTerms(filename, {"_h": "", "_l": ""})

            game_format_mode = ResFormat.from_name(self.game.name).get(self.RESOLUTIONS.get(filename, Resolution.HIGH))
            root = Types.ROOTS.get(self.game.name, "") / game_format_mode

            for atlas_name, atlas_ops in data["atlases"].items():
                additions = atlas_ops["additions"]
                if not additions:
                    continue

                existing_layout = layout_map.get(atlas_name)

                if existing_layout:
                    print(f"Adding {len(additions)} subtexture(s) to existing layout '{atlas_name}'")
                    existing_layout.add_subtextures(additions)

                else:
                    print(f"Creating layout entry for '{atlas_name}' with {len(additions)} subtexture(s)")

                    imgpath = (rf"W:\CL\data\Target\INTERROOT_win64\menu\ScaleForm\Tif\01_Common\{game_format_mode}\{atlas_name}.tif"
                            if self.game.name == "Nightreign"
                            else f"{atlas_name}.png")

                    new_layout = AtlasLayout.create(
                        image_path=imgpath,
                        subtextures=additions
                    )

                    layout_objs.append(new_layout)
                    layout_map[atlas_name] = new_layout

            AtlasLayout.build(
                layout_objs=layout_objs,
                root=root,
                output=base_name.with_name(
                    base_name.name.replace('.tpf.dcx', '.sblytbnd.dcx')
                )
            )

        print("\nFinished building operations.")
        print("Summary of DCX operations:")

        for dcx_name, data in dcx_ops.items():
            print(f"File: {dcx_name}")

            if data["new_atlases"]:
                print(f"  New Atlases: {[t.name for t in data['new_atlases']]}")

            for atlas_name, ops in data["atlases"].items():
                rep_keys = list(ops["replacements"].keys())
                add_names = [sub.name for sub in ops["additions"]]

                print(f"  Atlas: {atlas_name} | "
                      f"Replacements: {rep_keys} | "
                      f"Additions: {add_names}")

        return dcx_ops

    def run(self):
        self.outputLoc = None
        try:
            for base_path, data in self.buildOperations().items():
                self.outputLoc = base_path.parent
                base: TPF = deepcopy(self.LOADED_DCX_FILES[base_path])

                if data["new_atlases"]:
                    if self.game.name == "Dark Souls 2":
                        for t in data['new_atlases']:
                            t.writetpf()
                        continue # hacky but whatever i cba
                    else:
                        base.textures.extend([t.texture for t in data["new_atlases"]])

                atlas_cache = {}

                for atlas_name, ops in data["atlases"].items():
                    if atlas_name not in atlas_cache:
                        atlas_cache[atlas_name] = self.getPilImage(atlas_name).copy()
                    atlas_img = atlas_cache[atlas_name]

                    for add in ops["additions"]:
                            if add.img:
                                add.paste_into(atlas_img)

                    for sub_name, new_img in ops["replacements"].items():
                        if sub_name != "*Self*":  # subtexture replacement
                            st = self.getPilImage(atlas_name, return_atlas=True).fetch(sub_name) # im so sorry
                            if not st:
                                raise Exception(f"Could not resolve subtexture '{sub_name}' in atlas '{atlas_name}'")
                            atlas_img.paste(new_img, (st.x, st.y))
                        else:  # full atlas replacement
                            atlas_img = new_img.copy()
                            atlas_cache[atlas_name] = atlas_img

                for atlas_name, atlas_img in atlas_cache.items():
                    with NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                        temp_path = tmp.name
                        atlas_img.save(temp_path)
                    try:
                        texture = TPF.find_texture_stem(base, atlas_name)
                        texture.replace_dds(temp_path)
                    finally:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)

                base.write(base_path)

            self.finished.emit(True, "All changes applied successfully!", self.outputLoc)

        except Exception:
            self.finished.emit(False, traceback.format_exc(), self.outputLoc)

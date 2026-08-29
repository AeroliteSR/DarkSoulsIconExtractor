from __future__ import annotations
# Basic Modules
import sys, shutil
from pathlib import Path
from collections import defaultdict
from PIL import Image, UnidentifiedImageError
from math import gcd
from webbrowser import open_new_tab
from typing import Optional
from tempfile import NamedTemporaryFile
# GUI
from multiprocessing import Process, Queue
from queue import Empty
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QListWidget, QHBoxLayout, QFileDialog, QPushButton,
QMessageBox, QSplitter, QProgressDialog, QInputDialog, QMenu, QLineEdit)
from PySide6.QtGui import QIcon, QDesktopServices, QAction
from PySide6.QtCore import Qt, QThread, QUrl, QPoint, QTimer, QSize, Signal
# Soulstruct
from soulstruct.dcx import oodle
from soulstruct.containers.tpf import TPF_TEXTURE_FORMAT_TO_DXGI_FORMAT, TPFTexture, TPFPlatform
from soulstruct.base.textures.dds.enums import DXGI_FORMAT_BPP, DXGI_FORMAT
# DSTS
from DSTextureStudio.GameInfo import DXGI_STRUCT_MAP
from DSTextureStudio.Dataclasses import Atlas, SubTexture
from DSTextureStudio.Enums import Game, ImageType, IconMode, ExportMode, Resolution, Modified, GameType, DeltaMode
from DSTextureStudio.Helpers import checkGame, getFreeSpace, createBlankImage, createDebugGrid, getPngSize, validateImageForSwizzle
from DSTextureStudio.Workers import LoadWorker, WriteWorker, ExtractWorker, make_delta_process
from DSTextureStudio.GUI import (Delegate, ExpandableLabel, Palettes, TextureListWidget, TextureNamePrompt, DefineSubtexturePrompt, ImageLabel,
showError, showQuery, showSelectOptions, NaturalListItem, getOutputPath, CompressionPrompt, ProcessingBar, RadioButtonDialog)
from DSTextureStudio.log_utils import setuplog, addQtHandler, handle_exception, LogEmitter
from DSTextureStudio.Console import ConsoleWindow
from DSTextureStudio.Utilities import replaceTerms, loadJson, getDSTSdir, findLast

BLANK_PATH = Path('.')

class TextureStudio(QMainWindow):
    logSignal = Signal(str)

    def __init__(self, project_dir):
        super().__init__()
        self.project_dir = project_dir
        self.alphaThreshold = 0

        self.setWindowTitle("DSTS")
        self.setGeometry(100, 100, 1100, 700)

        self._context_menu = QMenu(self)

        self.atlases = {}
        self.LOADED_DCX_FILES = {}
        self.LAYOUT_DATA = {}        
        self.current_crop = None
        self.current_atlas = None
        self.thumbnail_cache = {}
        self.pending_new_atlases = []
        self.game = Game(None)

        self.console = ConsoleWindow(self, emitter=log_emitter)
        self.console.set_objects(
            instance=lambda: self,
            atlases=lambda: self.atlases,
            current=lambda: self.current_atlas,
            file=lambda: self.atlas_list.currentItem().data(Qt.UserRole+1),
            game=lambda: self.game,
            crop=lambda: self.current_crop,
            cache=lambda: self.thumbnail_cache,
            mods=lambda: [atlas.modifications for atlas in self.atlases.values() if atlas.modified],
            new=lambda: self.pending_new_atlases,
            loaded=lambda: self.LOADED_DCX_FILES,
            layouts=lambda: self.LAYOUT_DATA,
        )
        self.createMenu()

        container = QWidget()
        layout = QHBoxLayout(container)
        splitter = QSplitter(Qt.Horizontal)

        atlas_panel = QWidget()
        atlas_layout = QVBoxLayout(atlas_panel)
        atlas_layout.setContentsMargins(0, 0, 0, 0)

        self.atlas_search = QLineEdit()
        self.atlas_search.setPlaceholderText("Search atlases...")
        self.atlas_search.textEdited.connect(lambda text: self.filterList(text, self.atlas_list))
        atlas_layout.addWidget(self.atlas_search)

        self.atlas_list = TextureListWidget()
        self.atlas_list.setItemDelegate(Delegate(self.atlas_list))
        self.atlas_list.itemClicked.connect(self.showAtlas)
        self.atlas_list.itemActivated.connect(self.showAtlas)
        self.atlas_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.atlas_list.customContextMenuRequested.connect(self.openSubtextureMenu)
        self.atlas_list.add_button.clicked.connect(self.addAtlas)
        atlas_layout.addWidget(self.atlas_list)

        splitter.addWidget(atlas_panel)

        subtexture_panel = QWidget()
        subtexture_layout = QVBoxLayout(subtexture_panel)
        subtexture_layout.setContentsMargins(0, 0, 0, 0)

        self.subtexture_search = QLineEdit()
        self.subtexture_search.setPlaceholderText("Search subtextures...")
        self.subtexture_search.textEdited.connect(lambda text: self.filterList(text, self.subtexture_list))
        subtexture_layout.addWidget(self.subtexture_search)

        self.subtexture_list = TextureListWidget(mode=ImageType.Subtexture, check_game=lambda: self.game)
        self.subtexture_list.setItemDelegate(Delegate(self.subtexture_list))
        self.subtexture_list.itemClicked.connect(self.showSubtexture)
        self.subtexture_list.itemActivated.connect(self.showSubtexture)
        self.subtexture_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.subtexture_list.customContextMenuRequested.connect(self.openSubtextureMenu)
        self.subtexture_list.def_option.triggered.connect(lambda: self.addIcon(IconMode.Define))
        self.subtexture_list.add_option.triggered.connect(lambda: self.addIcon(IconMode.Append))
        subtexture_layout.addWidget(self.subtexture_list)

        splitter.addWidget(subtexture_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.preview_label = ImageLabel("Texture Preview", fetchimg=self.getPixmap)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("border: 1px solid gray; background: #222; color: white;")
        self.preview_label.setMinimumSize(600, 425)
        right_layout.addWidget(self.preview_label)

        self.info_label = ExpandableLabel("Texture Info", "Texture Info")
        self.info_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.info_label.setStyleSheet("background: #333; color: white; padding: 6px; border-radius: 4px;")
        self.info_label.setMinimumHeight(150)
        right_layout.addWidget(self.info_label)

        self.save_button = QPushButton("Export Selected Texture")
        self.save_button.clicked.connect(self.saveSelection)
        right_layout.addWidget(self.save_button)

        self.replace_button = QPushButton("Replace Selected Texture")
        self.replace_button.clicked.connect(self.registerReplacement)
        right_layout.addWidget(self.replace_button)

        splitter.addWidget(right_panel)

        layout.addWidget(splitter)
        self.setCentralWidget(container)

    def hasPendingChanges(self):
        return bool(self.pending_new_atlases or any(a.modified for a in self.atlases.values()))

    def closeEvent(self, event):
        if not self.hasPendingChanges():
            event.accept()
            return

        result = QMessageBox.question(self, "Active Changes", "You have active changes. Are you sure you want to exit?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if result == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

    def createMenu(self):
        """Handles the creation of the menu bar and its features."""
        menu = self.menuBar()
        def createAction(name, func):
            action = QAction(name, self)
            action.triggered.connect(func)
            return action

        self.file_menu = menu.addMenu("File")
        self.file_menu.addAction(createAction("Open File", lambda: self.openDcxDialog(dirmode=False)))
        self.file_menu.addAction(createAction("Open Directory", lambda: self.openDcxDialog(dirmode=True)))
        self.file_menu.addSeparator()
        self.file_menu.addAction(createAction("Save As", self.applyChanges))
        self.file_menu.addSeparator()
        self.file_menu.addAction(createAction("Undo All Changes", self.undoChanges))
        self.file_menu.addAction(createAction("Clear Workspace", self.clear))

        self.settings_menu = menu.addMenu("Settings")

        self.btn_useCustomNames = QAction("Community Names", self)
        self.btn_useCustomNames.setCheckable(True)
        self.btn_useCustomNames.toggled.connect(self.toggleCustomNames)

        self.btn_calcImageSize = QAction("Calculate Image Size", self)
        self.btn_calcImageSize.setCheckable(True)

        self.btn_hideBlankIcons = QAction("Hide Blank Icons", self)
        self.btn_hideBlankIcons.setCheckable(True)
        self.btn_hideBlankIcons.setChecked(True)
        self.btn_hideBlankIcons.toggled.connect(lambda: self.showAtlas(self.atlas_list.currentItem()))

        self.btn_atlasGrid = QAction("Show Icon Borders", self)
        self.btn_atlasGrid.setCheckable(True)
        self.btn_atlasGrid.toggled.connect(lambda: self.showAtlas(self.atlas_list.currentItem()))

        self.btn_alphaThreshold = QAction(f"Alpha Threshold = {self.alphaThreshold}", self)
        self.btn_alphaThreshold.triggered.connect(self.promptAlphaThreshold)

        self.settings_menu.addAction(self.btn_useCustomNames)
        self.settings_menu.addAction(self.btn_hideBlankIcons)
        self.settings_menu.addAction(self.btn_calcImageSize)
        self.settings_menu.addAction(self.btn_atlasGrid)
        self.settings_menu.addSeparator()
        self.settings_menu.addAction(self.btn_alphaThreshold)

        self.tools_menu = menu.addMenu("Tools")
        deltapatch = self.tools_menu.addMenu("Merging")
        deltapatch.addAction(createAction("Generate Delta", self.createDelta))
        deltapatch.addAction(createAction("Import Delta", self.mergeDelta))
        dump = self.tools_menu.addMenu("Dumpers")
        dump.addAction(createAction("Atlases", lambda: self.dumpTextures(mode=ExportMode.ATLAS)))
        dump.addAction(createAction("Subtextures", lambda: self.dumpTextures(mode=ExportMode.SUBTEXTURE)))
        
        self.help_menu = menu.addMenu("Help")
        self.help_menu.addAction(createAction("Settings", lambda: QMessageBox.information(self, "Settings Info", "<b>Custom Names:</b><br> When enabled, this setting replaces" \
                                                                                                " most atlas and subtexture names with more user-friendly ones. " \
                                                                                                "The new atlas names were written manually by me, and are not " \
                                                                                                "perfect. However, they may help someone less familiar with fromsoft " \
                                                                                                "find what they are looking for. Most subtexture names were mapped " \
                                                                                                "with a script using data from Smithbox exports, and should"
                                                                                                " be accurate.<br><br>" \
                                                                                                "<b>Hide Blank Icons:</b><br>" \
                                                                                                "Only for older games with no layout system. DSTS crops the atlases" \
                                                                                                " in a grid layout. Because of this, some \'tiles\' may be blank. " \
                                                                                                "DSTS automatically recognises these blank spaces and ignores them " \
                                                                                                "when building the subtexture list. Disable this setting to show " \
                                                                                                "the aforementioned blank spaces, for example, if you wanted to " \
                                                                                                "place a new icon in that spot.<br><br>" \
                                                                                                "<b>Calculate Image Size:</b><br>" \
                                                                                                "When enabled, this setting will attempt to silently convert " \
                                                                                                "images to PNGs within memory in order to estimate their " \
                                                                                                "compressed size. This may be useful for someone doing batch " \
                                                                                                "exports, but it slows loading time substantially, so it's " \
                                                                                                "disabled by default.<br><br>" \
                                                                                                "<b>Show Icon Borders:</b><br>" \
                                                                                                "Draws a red bounding box around subtextures wherever possible. " \
                                                                                                "This will not be visible on texture dumps or replacements, " \
                                                                                                "but can be optionally selected for atlas exports.<br><br>" \
                                                                                                "<b>Alpha Threshold:</b><br>" \
                                                                                                "Any pixel with an alpha value less than or equal to this number " \
                                                                                                "will have their RGB values set to 0. Click to update the value.")))
        self.help_menu.addAction(createAction("Documentation", lambda: open_new_tab("https://darksoulstexturestudio.readthedocs.io/en/latest/")))
        self.help_menu.addSeparator()
        self.help_menu.addAction(createAction("Hello", lambda: QMessageBox.information(self, "Hello", 
                                                                                       "<span style=\"font-size:18pt;\">" \
                                                                                       "Heyo o/<br>" \
                                                                                       "- <a href='https://linktr.ee/aerolitesr'>Aero</a> :><br><br> </span>")))
        self.help_menu.addSeparator()
        self.help_menu.addAction(createAction("Console", self.console.show))

    def filterList(self, text, widget):
        text = text.lower()
        for i in range(widget.count()):
            item = widget.item(i)
            item.setHidden(text not in item.text().lower())

    def undoChanges(self):
        self.pending_new_atlases = []
        for a in self.atlases.values():
            a.clearChanges()

        self.atlas_list.setCurrentRow(0)
        self.showAtlas(self.atlas_list.currentItem())

    def createDelta(self):
        self.checkOodleDLL()

        def check_process(open_path):
            try:
                message, data = self.queue.get_nowait()
            except Empty:
                if not self.process.is_alive():
                    self.timer.stop()
                    self.progress.close()

                    showError("Delta process exited unexpectedly.")

                return

            self.timer.stop()
            self.progress.close()

            self.process.join()
            self.process = None

            if message == 'error':
                showError(data)

            if message == "finished":
                self.extractionDone(saved_path=open_path)

        if self.hasPendingChanges():
            showError("Current file has no pending changes!")
            return

        if not self.game.type != GameType.MODERN:
            showError("This feature is only for modern games for now. Sorry!")
            return

        dlg = RadioButtonDialog(
            "Delta Options",
            "Choose delta creation mode.",
            options={
                0: "Create Delta from queued modifications",
                1: "Create Delta from diffs against a vanilla file"
            }
        )

        if not dlg.exec():
            return

        match dlg.selected():
            case 0: # from self mods
                mode = DeltaMode.SELF
                file_path, try_lyt = None, None

            case 1: # diff against external file
                mode = DeltaMode.DIFF
                file_path = Path(QFileDialog.getOpenFileName(self, "Select Vanilla File", "", "Texture Containers (*.tpf.dcx *.tpf);;All Files (*.*)")[0])
                if not file_path or file_path == BLANK_PATH:
                    logger.warning("%s is either an invalid path or wasn't returned on prompt. Atlases will not be processed.", file_path.name)
                    return

                try_lyt = file_path.parent / file_path.name.replace('.tpf', '.sblytbnd')
                if not try_lyt.exists():
                    layout = Path(QFileDialog.getOpenFileName(None, "Navigate to corresponding sblytbnd.dcx", "", "Layout Files (*.sblytbnd.dcx)")[0])
                    if not (layout != BLANK_PATH and layout.exists()):
                        logger.warning("Layout file for %s is either an invalid path or wasn't returned on prompt. Atlases will not be processed.", try_lyt.name)
                        return              
                                
            
        output = Path(QFileDialog.getSaveFileName(self, "Save As", "", "Delta Patches (*.delta)")[0])

        self.progress = ProcessingBar("Generating Delta...")
        self.queue = Queue()

        self.process = Process(
            target=make_delta_process,
            args=(mode, list(self.atlases.values()), None, (file_path, try_lyt), output, self.queue)
        )
        self.process.start()

        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: check_process(output.parent)) 
        self.timer.start(100)
        
    def mergeDelta(self):
        if self.atlas_list.count() == 0:
            showError("No files loaded!")
            return
        
        file_path = Path(QFileDialog.getOpenFileName(self, "Select File", "", "Delta Patches (*.delta)")[0])
        if not file_path or file_path == BLANK_PATH:
            return

        atlases = Atlas.readDeltaFile(file_path)

        for atlas in atlases:
            if atlas.name not in self.atlases:
                dims = atlas.texture.size
                with NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    temp_path = tmp.name
                    atlas.texture.save(temp_path)

                blank = TPFTexture(stem=atlas.name, mipmap_count=1, format=102, platform=TPFPlatform.PC) # TODO: don't assume?
                blank.replace_dds(temp_path, dds_format="BC7_UNORM")

                atlas.texture = blank 
                atlas.dimensions = dims
                self.pending_new_atlases.append(atlas)
                continue

            existing = self.atlases[atlas.name]
            existing.update(atlas)

        self.atlas_list.setCurrentRow(0)
        self.showAtlas(self.atlas_list.currentItem())
        self.reloadHighlighting()

    def openSubtextureMenu(self, position: QPoint):
        sender = self.sender()

        if sender == self.subtexture_list:
            item = self.subtexture_list.itemAt(position)
            if item is None:
                return

            current = self.atlas_list.currentItem()
            atlas_name = current.data(Qt.UserRole)
            sub_name = item.data(Qt.UserRole)

            modify = self.isModified(atlas_name, sub_name)
            if modify == Modified.FALSE:
                return

            self.subtexture_list.setCurrentItem(item)
            self.showSubtexture(item)

            menu_pos = self.subtexture_list.viewport().mapToGlobal(position)

            menu = QMenu(self)

            if modify == Modified.ADDED:
                menu.addAction("Rename", lambda: self.renameSubtexture(item))
                menu.addAction("Move", lambda: self.moveSubtexture(item))
                menu.addAction("Delete", lambda: self.deleteSubtexture(item))

            elif modify == Modified.REPLACED:
                menu.addAction("Revert", lambda: self.revertSubtexture(item))

            menu.exec(menu_pos)

        elif sender == self.atlas_list:
            item = self.atlas_list.itemAt(position)
            if item is None:
                return

            atlas_name = item.data(Qt.UserRole)

            modify = self.isModified(atlas_name)
            if modify == Modified.FALSE:
                return

            self.atlas_list.setCurrentItem(item)
            self.showAtlas(item)

            menu_pos = self.atlas_list.viewport().mapToGlobal(position)

            menu = QMenu(self)

            if modify == Modified.ADDED:
                menu.addAction("Delete", lambda: self.deleteAtlas(item))
                menu.addAction("Rename", lambda: self.renameAtlas(item))

            elif modify == Modified.REPLACED:
                menu.addAction("Revert", lambda: self.revertAtlas(item))

            menu.exec(menu_pos)

    def deleteSubtexture(self, sub_item):
        atlas_item = self.atlas_list.currentItem()
        if not atlas_item or not sub_item:
            return

        atlas_name = atlas_item.data(Qt.UserRole)
        sub_name = sub_item.data(Qt.UserRole)

        atlas: Atlas = self.atlases.get(atlas_name, {})

        _,index = atlas.match(sub_name, attr="additions")
        if index is not None:
            atlas.additions.pop(index)

        _,index = atlas.match(sub_name, attr="replacements")
        if index is not None:
            atlas.replacements.pop(index)

        self.updateCache(atlas_name)
        self.subtexture_list.takeItem(self.subtexture_list.row(sub_item))

        items = [self.subtexture_list.item(i) for i in range(self.subtexture_list.count())]

        if all(self.isModified(atlas_name, it.data(Qt.UserRole)) == Modified.FALSE for it in items):
            atlas_item.setForeground(Qt.white)

        self.showAtlas(atlas_item)

    def revertSubtexture(self, sub_item):
        atlas_item = self.atlas_list.currentItem()
        if not atlas_item or not sub_item:
            return

        atlas_name = atlas_item.data(Qt.UserRole)
        sub_name = sub_item.data(Qt.UserRole)

        atlas: Atlas = self.atlases.get(atlas_name, {})

        _,index = atlas.match(sub_name, attr="replacements")
        if index is not None:
            atlas.replacements.pop(index)

        self.updateCache(atlas_name)

        sub_item.setForeground(Qt.white)

        items = [self.subtexture_list.item(i) for i in range(self.subtexture_list.count())]

        if all(self.isModified(atlas_name, it.data(Qt.UserRole)) == Modified.FALSE for it in items):
            atlas_item.setForeground(Qt.white)

        self.showSubtexture(sub_item)

    def renameSubtexture(self, sub_item):
        atlas_item = self.atlas_list.currentItem()
        if not atlas_item or not sub_item:
            return

        atlas_name = atlas_item.data(Qt.UserRole)
        old_name = sub_item.data(Qt.UserRole)

        dialog = TextureNamePrompt(resizeprompt=False, halfprompt=False, padprompt=False)
        if not dialog.exec():
            return

        new_name, *_ = dialog.get_result()

        if self.atlases.get(atlas_name, {}).fetch(new_name): # returns None if SubTexture of that name isn't found
            showError(f"A subtexture named '{new_name}' already exists!")
            return

        atlas: Atlas = self.atlases.get(atlas_name)

        sub,_ = atlas.match(old_name, attr="additions")
        if sub is not None:
            sub.rename(new_name)

        sub,_ = atlas.match(old_name, attr="replacements")
        if sub is not None:
            sub.rename(new_name)

        sub_item.setText(new_name)
        sub_item.setData(Qt.UserRole, new_name)

        self.updateCache(atlas_name)
        self.showSubtexture(sub_item)

    def moveSubtexture(self, sub_item):
        atlas_item = self.atlas_list.currentItem()
        if not atlas_item or not sub_item:
            return

        atlas_name = atlas_item.data(Qt.UserRole)
        sub_name = sub_item.data(Qt.UserRole)

        additions = self.atlases.get(atlas_name).additions

        sub = next((s for s in additions if s.name == sub_name), None)
        if sub is None:
            return

        dlg = DefineSubtexturePrompt(new=False)
        if not dlg.exec():
            return

        sub.setpos(*dlg.get_result())

        self.thumbnail_cache.pop(atlas_name, None)
        self.showAtlas(atlas_item)

    def deleteAtlas(self, atlas_item):
        if not atlas_item:
            return

        atlas_name = atlas_item.data(Qt.UserRole)

        self.pending_new_atlases = [a for a in self.pending_new_atlases if a.name != atlas_name]
        self.thumbnail_cache.pop(atlas_name, None)

        self.atlas_list.takeItem(self.atlas_list.row(atlas_item))

    def renameAtlas(self, atlas_item):
        if not atlas_item:
            return

        old_name = atlas_item.data(Qt.UserRole)
        dialog = TextureNamePrompt(mode=ImageType.Texture, formatprompt=False, blankprompt=False)

        if not dialog.exec():
            return

        new_name, *_ = dialog.get_result()

        if new_name in self.atlases:
            showError(f"An atlas named '{new_name}' already exists!")
            return

        atlas = self.atlases.get(old_name)
        atlas.rename(new_name)

        if old_name in self.thumbnail_cache:
            self.thumbnail_cache[new_name] = self.thumbnail_cache.pop(old_name)

        atlas_item.setText(new_name)
        atlas_item.setData(Qt.UserRole, new_name)

    def revertAtlas(self, atlas_item):
        if not atlas_item:
            return

        atlas_name = atlas_item.data(Qt.UserRole)
        atlas: Atlas = self.atlases.get(atlas_name)

        index = findLast(atlas.replacements, Image.Image)
        if index is not None:
            atlas.replacements.pop(index)

        self.updateCache(atlas_name)
        self.showAtlas(atlas_item)

    def addAtlas(self):
        if self.atlas_list.count() == 0:
            answer = showQuery("Creation", "You currently have no loaded files.\nWould you like to create a custom TPF?")
            if answer != QMessageBox.Yes:
                return
            self.checkOodleDLL()
            self.game = Game("Dark Souls 2")
                
        if self.game.name != "Dark Souls 2": # doesn't need a parent as it writes to a standalone tpf
            files = list(self.LOADED_DCX_FILES.keys())
            if len(files) > 1:
                ok, parent = showSelectOptions("Select parent file", "Files:", files)
                if not ok:
                    return
                parent = Path(parent)
            else:
                parent = files[0]
        else:
            parent = "None"

        dialog = TextureNamePrompt(mode=ImageType.Texture)
        if not dialog.exec():
            return
        name, _format, dimensions = dialog.get_result()

        if not hasattr(self, "atlases"): # if no project loaded, aka writing custom tpfs, init these so they dont throw errors elsewhere
            self.atlases = {}
            self.LOADED_DCX_FILES = {}
            self.LAYOUT_DATA = {}

        if dimensions: # blank option was selected and returned tuple
            img_path = createBlankImage(dimensions)
            if not img_path or img_path == BLANK_PATH:
                return
        else: # dimensions is None, select image
            img_path = Path(QFileDialog.getOpenFileName(self, "Select Image", "", "Image Files (*.png *.dds *.jpg *.webm *.jpeg);;All Files (*.*)")[0])
            if not img_path or img_path == BLANK_PATH:
                return

        if name in [i.name for i in self.atlases.values()]:
            showError("A texture of this name already exists!")
            return

        match self.game.name:
            case 'Bloodborne':
                img = validateImageForSwizzle(Image.open(img_path))
                if img is None:
                    return
                
                w,h = img.size

                with NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    img_path = tmp.name
                    img.save(tmp.name)

                platform = TPFPlatform.PS4
                consoleinfo = TPFTexture.ConsoleInfo(
                    width=w,
                    height=h,
                    texture_count=1,
                    unk2=13,
                    dxgi_format=DXGI_FORMAT[_format]
                )
            
            case "Demon's Souls":
                img = Image.open(img_path)
                w,h = img.size
                platform = TPFPlatform.PC
                consoleinfo = TPFTexture.ConsoleInfo(
                    width=w,
                    height=h,
                    texture_count=1,
                    unk2=13,
                    dxgi_format=DXGI_FORMAT[_format]
                )

            case _:
                img = Image.open(img_path)
                platform = TPFPlatform.PC
                consoleinfo = None

        blank = TPFTexture(stem=name, mipmap_count=1, format=DXGI_STRUCT_MAP[DXGI_FORMAT[_format]], platform=platform, console_info=consoleinfo)
        blank.replace_dds(img_path, dds_format=_format)
        new_atlas = Atlas(
            name=name,
            texture=blank,
            dimensions=img.size,
            parent=parent
        )

        self.pending_new_atlases.append(new_atlas)
        self.atlases.setdefault(name, new_atlas)

        item = NaturalListItem(name)
        item.setData(Qt.UserRole, name) # original name
        item.setData(Qt.UserRole+1, parent) # parent file
        item.setSizeHint(QSize(0, 30))
        item.setData(Qt.UserRole+2, ImageType.Custom) # image type
        self.atlas_list.addItem(item)

        self.updateCache(name)
        self.atlas_list.setCurrentItem(item)
        self.showAtlas(self.atlas_list.currentItem())

    def addIcon(self, mode: IconMode = IconMode.Append):
        if self.game.name == "Dark Souls 2": # no point adding a subtexture to a single icon
            showError("If you're trying to add icons for DS2, see:<br><a href='https://darksoulstexturestudio.readthedocs.io/en/latest/custom-files/'>Docs</a>", _type=QMessageBox.Information)
            return
        
        if self.atlas_list.count() == 0:
            showError('No atlases loaded!')
            return

        atlas_item = self.atlas_list.currentItem()
        if not atlas_item:
            showError('No atlas loaded!')
            return

        atlas_name = atlas_item.data(Qt.UserRole)
        atlas_obj = self.atlases.get(atlas_name)
        subs = atlas_obj.subtextures

        if self.game.type != GameType.MODERN and len(subs) == 0:
            showError("Sorry, this atlas isn't mapped yet!<br>Consider mapping them yourself in Dimensions.json :D")
            return
        
        if atlas_obj.parent == "None":
            showError("This file has no layout.")
            return
        
        atlas_img = self.getPilImage(atlas_name)

        match mode:
            case IconMode.Append:
                dialog = TextureNamePrompt()
                if not dialog.exec():
                    return

                name, padding, resize, half = dialog.get_result()

                if any(name==i.name for i in subs):
                    showError("An icon of this name already exists!")
                    return
        
                img_path = Path(QFileDialog.getOpenFileName(self, "Select Image", "", "Image Files (*.png *.dds *.jpg *.webm *.jpeg);;All Files (*.*)")[0])
                if not img_path or img_path == BLANK_PATH:
                    return
                
                img = Image.open(img_path).convert('RGBA')

                if resize:
                    w, h = resize
                    img = img.resize(resize, Image.Resampling.LANCZOS)
                else:
                    w, h = img.size

                if self.game.name == "Bloodborne": # check for valid img size
                    img = validateImageForSwizzle(img, atlas_img.size, (padding, padding))
                    if img is None:
                        return
                    w, h = img.size

                used_rects = [st.box(padding=padding) for st in subs]
                pos = getFreeSpace(atlas_img.size, used_rects, w, h, padding=padding)

                if pos:
                    x, y = pos
                else:
                    x = 0
                    y = atlas_img.size[1] + padding
                
            case IconMode.Define:
                dialog = DefineSubtexturePrompt(*atlas_img.size)
                if not dialog.exec():
                    return

                name, hw, xy, half = dialog.get_result()

                if any(name==i.name for i in subs):
                    showError("An icon of this name already exists!")
                    return
                
                w, h = hw
                x, y = xy
                img = None
                
        sub = SubTexture(
            name=name,
            x=x,
            y=y,
            width=w,
            height=h,
            parent=atlas_name,
            image=img,
            vanilla=False,
            flag_half=half
        )

        atlas_obj.add(sub)
        atlas_obj.additions.append(sub)

        self.updateCache(atlas_name)
        self.showAtlas(atlas_item)

    def clear(self):
        """Completely reset the window."""
        if self.hasPendingChanges():
            result = QMessageBox.question(self, "Active Changes", "You have active changes. Are you sure you want to discard them?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if result != QMessageBox.Yes:
                return False

        self.setWindowTitle("DSTS")
        self.atlas_list.clear()
        self.subtexture_list.clear()
        self.atlases = {}
        self.current_crop = None
        self.current_atlas = None
        self.thumbnail_cache = {}
        self.pending_new_atlases = []
        self.game = Game(None)
        self.preview_label.setText("Texture Preview")
        self.info_label.setText(("Texture Info", "Texture Info"))
        return True

    def checkOodleDLL(self):
        """Find the oodle dll, or prompt for its location"""
        target = self.project_dir / "oo2core_6_win64.dll"

        try:
            oodle.LOAD_DLL(target)
        except oodle.MissingOodleDLLError:
            try:
                dll = oodle.LOAD_DLL() # no args, checks default paths
                shutil.copy(dll, target)
                logger.info("oo2core dll was found in default paths and has been copied to DSTS. No action required.")
                
            except oodle.MissingOodleDLLError:

                result = QMessageBox.question(self, "DLL Missing",
                                                    "Could not find oo2core_6_win64.dll within default paths.\n"
                                                    "DCX_KRAK compression will be unavailable without it.\n\n"
                                                    "Would you like to manually locate it?",
                                                    QMessageBox.Yes | QMessageBox.No,
                                                    QMessageBox.No)
                
                if result == QMessageBox.Yes:
                    dll = Path(QFileDialog.getOpenFileName(self, "Navigate to oo2core_6_win64.dll", "", "DLL Files (*.dll)")[0])
                    if dll and Path(dll).exists():
                        if dll.name != "oo2core_6_win64.dll":
                            QMessageBox.warning(self, "Warning", "This dll doesn't match the expected version.")
                            return
                        try:
                            oodle.LOAD_DLL(dll)
                            # Copy DLL next to the exe for future runs
                            shutil.copy(dll, target)
                            QMessageBox.information(self, "DLL Copied", f"{dll.name} has been copied to DSTS.\n"
                                                                        "Future runs will automatically use this DLL.")
                            
                        except Exception as e:
                            QMessageBox.critical(self, "Error", f"Failed to load DLL:\n{e}")

    def openDcxDialog(self, file: Optional[Path] = None, dirmode: bool = False):
        """Handles everything to do with loading files. If dirmode = True, loads every dcx/tpf in a directory."""    
        if not self.clear():
            return
        self.checkOodleDLL()

        if file:
            files = [file]
        else:
            if not dirmode:
                file_path = Path(QFileDialog.getOpenFileName(self, "Select File", "", "Texture Containers (*.tpf.dcx *.tpf);;All Files (*.*)")[0])
                if not file_path or file_path == BLANK_PATH:
                    return
                files = [file_path] if file_path else []
            else:
                dir_path = Path(QFileDialog.getExistingDirectory(self, "Select Folder"))
                if not dir_path or dir_path == BLANK_PATH:
                    return
                files = [f for pattern in ["*.tpf.dcx", "*.tpf", "*sblytbnd.dcx"] for f in dir_path.glob(pattern)]

            if not files:
                return

        str_path = str(files[0].parent if dirmode else files[0])
        self.setWindowTitle(f"DSTS - {str_path}")

        game = checkGame(path=str_path)
        if game is None:
            return
        self.game = game

        file_mappings = []
        if self.game.name == 'Nightreign':
            if not dirmode:
                files += [f for f in file_path.parent.glob("*.sblytbnd.dcx")]

            groups = defaultdict(lambda: {Resolution.HI: {}, Resolution.LOW: {}})
            standalone = []

            for f in files:
                name = f.name

                if "_h." in name:
                    prefix = name.split("_h.")[0]
                    res = Resolution.HI
                elif "_l." in name:
                    prefix = name.split("_l.")[0]
                    res = Resolution.LOW
                else:
                    standalone.append(f)
                    continue

                if "sblytbnd" in name:
                    groups[prefix][res]["layout"] = f
                elif ".tpf" in name:
                    groups[prefix][res]["tpf"] = f
                else:
                    standalone.append(f)

            for prefix, data in groups.items():
                available = []

                for res in [Resolution.HI, Resolution.LOW]:
                    if "tpf" in data[res]:
                        available.append(res)

                if not available:
                    continue

                if len(available) > 1:
                    ok, choice = showSelectOptions("Select Resolution", f"{prefix} has both high and low resolution. Which do you want?", 
                                                   [i.display for i in available])
                    if not ok:
                        return
                    choice = next(r for r in available if r.name == choice)
                else:
                    choice = available[0]

                tpf = data[choice].get("tpf")
                layout = data[choice].get("layout")

                if tpf and not layout and ('_common_' in Path(tpf).stem):
                    layout = Path(QFileDialog.getOpenFileName(self, f"Select layout for {tpf.name}", str(tpf.parent), "Layout Files (*.sblytbnd.dcx)")[0])

                    if not (layout != BLANK_PATH and layout.exists()):
                        layout = None
                        logger.warning("Layout file for %s is either an invalid path or wasn't returned on prompt. Atlases will not be processed.", tpf.name)

                if layout is not None:
                    file_mappings.append({"file": tpf, "layout": layout})
                else:
                    file_mappings.append(tpf)

            file_mappings.extend(standalone) # no layout

        elif self.game.name in ['Sekiro', 'Armored Core 6', 'Elden Ring']:
            for f in files:
                if 'sblytbnd' in str(f):
                    continue

                base_name = replaceTerms(f.stem, {'.tpf': ''})
                layout = None

                if "common" in f.stem:
                    try_lyt = f.parent / f"{base_name}.sblytbnd.dcx"

                    if try_lyt.exists():
                        layout = try_lyt
                    else:
                        layout = Path(QFileDialog.getOpenFileName(None, "Navigate to corresponding sblytbnd.dcx", "", "Layout Files (*.sblytbnd.dcx)")[0])
                        if not (layout != BLANK_PATH and layout.exists()):
                            layout = None
                            logger.warning("Layout file for %s is either an invalid path or wasn't returned on prompt. Atlases will not be processed.", base_name)

                if layout is not None:
                    file_mappings.append({"file": f, "layout": layout})
                else:
                    file_mappings.append(f)

        else:
            file_mappings = files

        self.progress_dialog = QProgressDialog("Loading DCX...", None, 0, 100, self)
        self.progress_dialog.setWindowTitle("Loading")
        self.progress_dialog.setWindowModality(Qt.ApplicationModal)
        self.progress_dialog.setStyleSheet("QProgressDialog {padding:0px;margin:0px;}")
        self.progress_dialog.show()

        self.thread = QThread()
        self.worker = LoadWorker(file_mappings, self.game)
        self.worker.moveToThread(self.thread)

        self.worker.progress.connect(self.updateProgress)
        self.worker.finished.connect(self.loadDone)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def loadDone(self, atlases, LOADED_DCX_FILES, LAYOUT_DATA, msg):
        """Stuff to do on successful load of files."""
        self.progress_dialog.close()

        if not LOADED_DCX_FILES:
            showError(msg)
            return

        self.atlases = atlases
        self.LOADED_DCX_FILES = LOADED_DCX_FILES
        self.LAYOUT_DATA = LAYOUT_DATA

        self.atlas_list.clear()
        for name, _atlas in atlases.items():
            item = NaturalListItem(name)
            item.setData(Qt.UserRole, name) # original name
            item.setData(Qt.UserRole+1, _atlas.parent) # parent file
            item.setSizeHint(QSize(0, 30))
            item.setData(Qt.UserRole+2, self.atlases.get(name, {}).itype) # image type
            self.atlas_list.addItem(item)
        logger.info("Finished populating atlas list")

        self.atlas_list.sortItems()
        self.toggleCustomNames() # simply update it just in case setting was on before load
        self.atlas_list.setCurrentRow(0)
        self.showAtlas(self.atlas_list.currentItem())

    def runExtraction(self, tasks=None, mode=ExportMode.SUBTEXTURE, gridOverlay=False):
        """Start the extract process for images."""
        output_dir = getOutputPath()
        if not output_dir:
            return

        if mode == ExportMode.ATLAS:
            ok, filetype = showSelectOptions('File Type', 'Would you like to export in PNG or DDS?', ['png', 'dds'])
            if not ok:
                return
        else:
            filetype = 'png'

        self.progress_dialog = QProgressDialog("Exporting...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowTitle("Exporting")
        self.progress_dialog.setWindowModality(Qt.ApplicationModal)
        self.progress_dialog.show()
        QApplication.processEvents()

        thread = QThread(self)
        worker = ExtractWorker(self.atlases, output_dir, loader=self.getPilImage, tasks=tasks, mode=mode, filetype=filetype, gridOverlay=gridOverlay)
        worker.moveToThread(thread)

        self.Ethread = thread
        self.Eworker = worker
        self.progress_dialog.canceled.connect(self.Eworker.interrupt)

        worker.progress.connect(self.updateProgress, Qt.QueuedConnection)
        worker.finished.connect(self.extractionDone, Qt.QueuedConnection)
        worker.finished.connect(lambda: QTimer.singleShot(0, thread.quit))

        thread.started.connect(worker.run)
        thread.start()

    def updateProgress(self, percent, message):
        """Updates the loading dialog values."""
        self.progress_dialog.setValue(percent)
        self.progress_dialog.setLabelText(message)

    def extractionDone(self, success=True, saved_path: Optional[Path] = None):
        """Stuff to do after extraction finishes"""
        if hasattr(self, "progress_dialog"):
            self.progress_dialog.close()

        if saved_path is None:
            saved_path = self.project_dir / "Output"

        if success:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Saved")
            msg.setText(f"Export saved to:\n{saved_path}")
            _open = QPushButton("Open Folder")
            msg.addButton(_open, QMessageBox.ActionRole)
            msg.addButton(QMessageBox.Ok)
            _open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(saved_path))))
            msg.exec()

    def toggleCustomNames(self):
        """Replaces displaying text for QListWidgetItems with the mapped ones whilst retaining the original in UserRole"""

        def restoreNames(widget: QListWidget):
            for idx in range(widget.count()):
                item = widget.item(idx)
                item.setText(item.data(Qt.UserRole))

        if self.btn_useCustomNames.isChecked():
            ATLASNAMES = loadJson("Atlas_Names")
            SUBNAMES = loadJson("Subtexture_Names")
            for idx in range(self.atlas_list.count()):
                item = self.atlas_list.item(idx)
                text = item.text()
                if self.game.name == 'Dark Souls 2': # special handling due to weird naming system
                    text = text[text.rfind('_')+1:]

                name = ATLASNAMES.get(self.game.name, {}).get(text, None) or item.text()
                item.setText(name)
            
            for idx in range(self.subtexture_list.count()):
                item = self.subtexture_list.item(idx)
                text = item.text()

                _, *pieces = text.split('_')
                try:
                    id = pieces[-1]
                    _type = pieces[0]
                    name = SUBNAMES.get(self.game.name, {}).get(_type, {}).get(id.lstrip('0'), None) or text
                except IndexError:
                    name = text

                item.setText(name)

        else:
            restoreNames(self.atlas_list)
            restoreNames(self.subtexture_list)

    def promptAlphaThreshold(self):
        num, ok = QInputDialog.getInt(None, "Prompt", "Enter new Alpha Threshold:", 10, 0, 255, 1)
        if not ok:
            return
        self.alphaThreshold = num
        self.btn_alphaThreshold.setText(f"Alpha Threshold = {num}")
        self.showAtlas(self.atlas_list.currentItem())

    def getSubtextureRect(self, atlas_name, sub_name, atlas_img) -> tuple[int, int, int, int]:
        """Return subtexture rect from either layout or grid system."""

        st = self.atlases.get(atlas_name, {}).fetch(sub_name)
        if st:
            return st.x, st.y, st.width, st.height

        dimensions = loadJson("Dimensions").get(self.game.name, {}).get(atlas_name)

        if not dimensions:
            return None

        tile_w = dimensions['width']
        tile_h = dimensions['height']

        atlas_w, _ = atlas_img.size
        tiles_per_row = atlas_w // tile_w

        try:
            idx = int(sub_name)
        except:
            return None

        row = idx // tiles_per_row
        col = idx % tiles_per_row

        x = col * tile_w
        y = row * tile_h

        return x, y, tile_w, tile_h

    def queueReplacement(self, atlas_item, sub_item, img_path: Path):
        atlas_name = atlas_item.data(Qt.UserRole)
        atlas: Atlas = self.atlases.get(atlas_name)

        try:
            new_img = Image.open(img_path).convert("RGBA")
        except UnidentifiedImageError:
            showError("Selected file is not an image supported by PIL.")
            return

        if not sub_item: # atlas replacement
            atlas_img = self.atlases[atlas_name].viewable
            new_img = new_img.resize((atlas_img.width, atlas_img.height), Image.Resampling.LANCZOS)

            atlas.replacements.append(new_img)

        else: # subtexture replacement
            sub_name = sub_item.data(Qt.UserRole)

            atlas_img = self.getPilImage(atlas_name)
            x,y,w,h = self.getSubtextureRect(atlas_name, sub_name, atlas_img)

            if not (w and h):
                showError(f"Could not resolve subtexture: {sub_name}")
                return

            new_img = new_img.resize((w, h), Image.Resampling.LANCZOS)

            atlas.replacements.append(
                SubTexture(
                    name=sub_name,
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                    image=new_img,
                    parent=atlas.name,
                )
            )

        self.updateCache(atlas_name)

        atlas_item.setForeground(Qt.yellow)
        if sub_item:
            sub_item.setForeground(Qt.yellow)
            self.showSubtexture(sub_item)
        else:
            self.showAtlas(atlas_item)

    def registerReplacement(self):
        """Prompt the user for an image, then add it to the replacement queue with the currently selected texture as the target."""
        if self.game.type is None:
            showError("No files loaded!")
        
        atlas = self.atlas_list.currentItem()
        atlas_name = atlas.data(Qt.UserRole)
        sub = self.subtexture_list.currentItem()
        atlas_obj = self.atlases.get(atlas_name)

        if atlas_obj.parent == "None":
            showError("Custom files cannot be replaced.<br>Try deleting it and making a new one with the image you want.")

        if not atlas:
            showError('No atlas loaded!')
            return

        img_path = Path(QFileDialog.getOpenFileName(self, "Select Image", "", "Image Files (*.png *.dds *.jpg *.webp *.jpeg);;All Files (*.*)")[0])
        if not img_path or img_path == BLANK_PATH:
            return
        
        self.queueReplacement(atlas, sub, img_path)

    def applyChanges(self):
        """Start replacement from File menu and create popup."""
        if not self.hasPendingChanges():
            QMessageBox.information(self, "Info", "No actions queued.")
            return
        
        output_dir = getOutputPath()
        if not output_dir:
            return
    
        self.replace_dialog = ProcessingBar("Applying changes...")

        self.r_thread = QThread()
        self.r_worker = WriteWorker(self.atlases, self.pending_new_atlases,self.LOADED_DCX_FILES, self.LAYOUT_DATA, self.alphaThreshold,  self.game, output_dir)
        self.r_worker.moveToThread(self.r_thread)
        self.r_thread.started.connect(self.r_worker.run)

        self.r_worker.requestCompression.connect(self.showCompressionDialog)
        self.r_worker.finished.connect(self.r_thread.quit)
        self.r_worker.finished.connect(self.changesDone)
        self.r_worker.finished.connect(self.r_worker.deleteLater)
        self.r_thread.finished.connect(self.r_thread.deleteLater)
        
        self.r_thread.start()

    def showCompressionDialog(self, name):
        dialog = CompressionPrompt(name)
        dialog.exec()
        self.r_worker._result = dialog.get_result()
        self.r_worker._event.set()

    def changesDone(self, success: bool, msg: str, saved_path: Path):
        """Triggered on completion of tpf/dcx export."""
        if hasattr(self, "replace_dialog"):
            self.replace_dialog.close()
        if success:
            self.extractionDone(True, saved_path)
        else:
            showError(msg)

    def formatImageInfo(self, name, file, pil_img, coords='None', img_type: ImageType = ImageType.Atlas):
        """Properly format information about the selected preview to display."""
        def formatSize(bytes_val):
            kb = bytes_val / 1024
            if kb < 1024:
                return f"{kb:.1f} KB"
            return f"{kb / 1024:.2f} MB"
        
        if isinstance(file, Path):
            file = file.name
        
        width, height = pil_img.size
        g = gcd(width, height)
        size_uc = formatSize(width * height * len(pil_img.getbands()))
        size_c = formatSize(getPngSize(pil_img)) if self.btn_calcImageSize.isChecked() else "???"

        short = (
            f"<b>Type:</b> {img_type.name}<br>"
            f"<b>Name:</b> {name}<br>"
            f"<b>In:</b> {file}<br>"
            f"<b>Coordinates:</b> {coords}<br>"
            f"<b>Dimensions:</b> {width} × {height}px<br>"
            f"<b>Aspect Ratio:</b> {width//g}:{height//g}<br>"
            f"<b>Uncompressed Size:</b> {size_uc}<br>"
            f"<b>Compressed Size:</b> {size_c}<br><br>")
        
        expanded = short 
        
        if img_type != ImageType.Subtexture:
            tpft = self.atlases[name].texture
            c_info = tpft.console_info
            if c_info is not None:
                c_info = (f"<br><b>Texture Count:</b> {c_info.texture_count}<br>"
                        f"<b>DXGI Format:</b> {c_info.dxgi_format}<br>"
                        f"<b>unk1:</b> {c_info.unk1}<br>"
                        f"<b>unk2:</b> {c_info.unk2}")
            format_num = tpft.format
            t_info = tpft.get_texture_format_info(format_num)
            t_format = TPF_TEXTURE_FORMAT_TO_DXGI_FORMAT[format_num]
            
            expanded += (
            f"<b>Platform:</b> {tpft.platform.name}<br>"
            f"<b>Format:</b> {t_format.name} | {format_num}<br>"
            f"<b>Mipmap Count:</b> {tpft.mipmap_count}<br>"
            f"<b>Texture Flags:</b> {tpft.texture_flags}<br>"
            f"<b>Fourcc:</b> {t_info[0]}<br>"
            f"<b>Bytes Per Block:</b> {t_info[1]}<br>"
            f"<b>Bits Per Pixel:</b> {DXGI_FORMAT_BPP[t_format]}<br>"
            f"<b>Is Compressed:</b> {t_info[2]}<br><br>"
            f"<b>Console Info:</b> {c_info}<br><br>")
        
        return short, expanded

    def updateCache(self, atlas_name):
        """Updates thumbnail cache with an atlas' image that has had all modifications compiled"""
        atlas = next((a for a in self.pending_new_atlases
                      if a.name == atlas_name), None) or self.atlases[atlas_name]
        self.thumbnail_cache[atlas_name] = atlas.compileTexture(self.alphaThreshold)

    def getPilImage(self, atlas_name, createDebug=False):
        """Returns rendered preview (rebuild if needed)"""
        if atlas_name not in self.thumbnail_cache:
            self.updateCache(atlas_name)

        img = self.thumbnail_cache[atlas_name]

        if createDebug:
            img = createDebugGrid(img, self.atlases[atlas_name].subtextures)

        return img

    def getPixmap(self, img: Optional[Image.Image] = None, resample: bool = False, crop_to: Optional[tuple] = None):
        """Returns pixmap of current texture preview. Used to ensure proper quality with no downscaling in the Texture Viewer."""
        if img is None:
            sub = self.subtexture_list.currentItem()
            if sub is not None: # subtexture
                name = self.subtexture_list.currentItem().data(Qt.UserRole)
                st = self.atlases[self.current_atlas].fetch(name)
                img = self.getPilImage(self.current_atlas).crop(st.box())

            else: # atlas
                atlas_name = self.atlas_list.currentItem().data(Qt.UserRole)
                img = self.getPilImage(atlas_name, createDebug=self.btn_atlasGrid.isChecked()).copy()

        if crop_to is not None:
            img = img.crop(crop_to)

        if resample:
            img = img.copy()
            img.thumbnail(self.preview_label.size().toTuple(), Image.Resampling.LANCZOS)

        return img.toqpixmap()

    def reloadHighlighting(self, only_current: bool = False):
        if only_current:
            items = [self.atlas_list.currentItem()]
        else:
            items = [self.atlas_list.item(x) for x in range(self.atlas_list.count())]

        for item in items:
            match self.isModified(item.data(Qt.UserRole), None):
                case Modified.ADDED:
                    item.setForeground(Qt.green)
                case Modified.REPLACED:
                    item.setForeground(Qt.yellow)

    def isModified(self, atlas_name, sub_name=None):
        """Returns True if subtexture has been modified, for recoloring its entry."""
        atlas: Atlas = self.atlases.get(atlas_name)

        if sub_name is None: # atlas check
            if atlas.additions or atlas.replacements:
                return Modified.REPLACED # not actually replaced, but it gets colored yellow cuz subitems are modified
            
            if findLast(atlas.replacements, Image.Image) is not None:
                return Modified.REPLACED

            if any(atlas_name == atlas.name for atlas in self.pending_new_atlases):
                return Modified.ADDED

            return Modified.FALSE

        if atlas.match(sub_name, "additions")[1] is not None:
            return Modified.ADDED

        if atlas.match(sub_name, "replacements")[1] is not None:
            return Modified.REPLACED
        
        return Modified.FALSE

    def showAtlas(self, current):
        """Display the selected atlas, and load all subtextures to the list."""
        if not current:
            return
        atlas_name = current.data(Qt.UserRole)
        dcx_file = current.data(Qt.UserRole+1)
        self.current_atlas = atlas_name
        self.current_crop = None

        atlas_img = self.getPilImage(atlas_name, createDebug=self.btn_atlasGrid.isChecked())
        self.preview_label.setPixmap(self.getPixmap(atlas_img, resample=True))

        # Load subtextures
        self.subtexture_list.blockSignals(True)
        self.subtexture_list.clear()
        for sub in self.atlases.get(atlas_name).subtextures:
            if self.btn_hideBlankIcons.isChecked() and sub.blank:
                continue
            name = sub.name

            item = NaturalListItem(name)
            item.setData(Qt.UserRole, name)
            item.setSizeHint(QSize(0, 30))

            match self.isModified(atlas_name, name):
                case Modified.REPLACED:
                    item.setForeground(Qt.yellow)
                case Modified.ADDED:
                    item.setForeground(Qt.green)

            self.subtexture_list.addItem(item)
        
        self.reloadHighlighting(only_current=True) # check if whole atlas is modified

        self.subtexture_list.blockSignals(False)
        self.subtexture_list.sortItems()

        self.info_label.setText(self.formatImageInfo(atlas_name, dcx_file, atlas_img, img_type=current.data(Qt.UserRole+2)))
        self.toggleCustomNames() # just to update it

    def showSubtexture(self, current):
        """Display a preview of the selected subtexture."""
        if not current or not self.current_atlas:
            return
        
        try:
            name = current.data(Qt.UserRole)
            st = self.atlases[self.current_atlas].fetch(name)
            dcx_file = self.atlas_list.currentItem().data(Qt.UserRole+1)
            if isinstance(dcx_file, Path):
                dcx_file = dcx_file.name
        except KeyError:
            self.subtexture_list.blockSignals(False)
            return

        atlas_img = self.getPilImage(self.current_atlas)
        cropped_img = atlas_img.crop(st.box())

        self.preview_label.setPixmap(self.getPixmap(cropped_img, resample=True))
        self.current_crop = cropped_img
        self.info_label.setText(self.formatImageInfo(name, dcx_file, cropped_img, st.pos, img_type=ImageType.Subtexture))

    def saveSelection(self):
        """Save current subtexture or whole atlas"""
        if not self.current_atlas:
            QMessageBox.warning(self, "Warning", "No atlas selected.")
            return

        if self.current_crop is not None and self.subtexture_list.currentItem(): # Subtexture selected
            key = self.subtexture_list.currentItem().data(Qt.UserRole)
            self.runExtraction(tasks=[(self.current_atlas, self.atlases[self.current_atlas].fetch(key))])

        else: # No subtexture selected, export the full atlas   
            img_type = self.atlas_list.currentItem().data(Qt.UserRole+2)
            if img_type == ImageType.Atlas:
                dlg = RadioButtonDialog(
                    "Select Export Type",
                    f"The currently selected texture is an atlas.\nWould you like to export the whole image, or its subtextures?",
                    options={
                        0: "Full Atlas Texture",
                        1: "Dump All Subtextures"
                    }
                )
                if not dlg.exec():
                    return
                
                if dlg.selected() == 1:#"All Subtextures"
                    self.saveAll()
                    return

            gridOverlay = self.btn_atlasGrid.isChecked()
            if gridOverlay:
                answer = showQuery('Export', 'You currently have the Grid Overlay enabled, do you want to keep it in the image for this export?')
                if answer == QMessageBox.Cancel:
                    return
                
                elif answer == QMessageBox.No:
                    gridOverlay = False

            self.runExtraction(tasks=[(self.current_atlas, None)], mode=ExportMode.ATLAS, gridOverlay=gridOverlay)

    def saveAll(self):
        """Export all subtextures from the currently selected atlas"""
        if not self.current_atlas:
            QMessageBox.warning(self, "Warning", "No atlas selected.")
            return

        tasks = [(self.current_atlas, st) for st in self.atlases.get(self.current_atlas).subtextures]
        if not tasks:
            QMessageBox.information(self, "Info", f"No subtextures found for {self.current_atlas}.")
            return

        self.runExtraction(tasks=tasks)

    def dumpTextures(self, mode=ExportMode.SUBTEXTURE):
        """Export all atlases or subtextures. Subtextures go into directories for their atlases"""
        gridOverlay = self.btn_atlasGrid.isChecked()
        if gridOverlay and mode == ExportMode.ATLAS:
            answer = showQuery('Export', 'You currently have the Grid Overlay enabled, do you want to keep it in the image for these exports?')
            if answer == QMessageBox.Cancel:
                return
            
            elif answer == QMessageBox.No:
                gridOverlay = False

        self.runExtraction(mode=mode, gridOverlay=gridOverlay)

def main():
    app = QApplication(sys.argv)
    base_dir = getDSTSdir()
    app.setStyle("Fusion")
    app.setStyleSheet(Palettes.DARK_STYLESHEET)
    app.setWindowIcon(QIcon(str(base_dir / "icon.ico")))
    window = TextureStudio(project_dir=base_dir)
    window.show()

    addQtHandler(logger, window.logSignal, log_emitter)
    logger.info("Application Started.")
    if len(sys.argv) > 1:
        filename = sys.argv[1]
        logger.info("Autorunning file passed as argument: %s", filename)
        window.openDcxDialog(file=Path(filename))
    sys.exit(app.exec())

if __name__ == "__main__":
    sys.excepthook = handle_exception
    global logger, log_emitter
    logger = setuplog()
    log_emitter = LogEmitter()
    main()

# nuitka --standalone --onefile --windows-console-mode=disable --enable-plugin=pyside6 --windows-icon-from-ico=icon.ico --include-data-file=icon.ico=icon.ico --include-data-file=soulstruct\base\textures\texconv.exe=soulstruct\base\textures\texconv.exe --include-module=constrata --include-module=soulstruct --msvc=latest --lto=yes DSTS.py
# pyinstaller DSTS.py --noconsole --icon=icon.ico --add-data "icon.ico;." --add-binary "soulstruct/base/textures/texconv.exe;soulstruct/base/textures" --collect-data soulstruct
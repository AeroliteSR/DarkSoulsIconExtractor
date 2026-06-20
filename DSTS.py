from __future__ import annotations
# Basic Modules
import sys, shutil
from io import BytesIO
from pathlib import Path
from collections import defaultdict
from PIL import Image, UnidentifiedImageError
from math import gcd
# GUI
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QListWidget, QHBoxLayout, QFileDialog, QPushButton,
QMessageBox, QSplitter, QProgressDialog, QInputDialog, QMenu)
from PySide6.QtGui import QIcon, QDesktopServices, QAction
from PySide6.QtCore import Qt, QThread, QUrl, QPoint, QTimer, QSize
# Soulstruct
from soulstruct.dcx import oodle
from soulstruct.containers.tpf import TPF_TEXTURE_FORMAT_TO_DXGI_FORMAT, TPFTexture, TPFPlatform
from soulstruct.base.textures.dds.enums import DXGI_FORMAT_BPP
# DSTS
from DSTextureStudio.GameInfo import Maps, Types
from DSTextureStudio.Dataclasses import Atlas, SubTexture
from DSTextureStudio.Enums import Game, ImageType, IconMode, ExportMode, Resolution, Modified, GameType
from DSTextureStudio.Helpers import replaceTerms, checkGame, path_has_sequence, pil2Qpixmap, getFreeSpace, createBlankImage, createDebugGrid, cleanByAlpha, getPngSize
from DSTextureStudio.Workers import LoadWorker, WriteWorker, ExtractWorker
from DSTextureStudio.GUI import (Delegate, ExpandableLabel, Palettes, SearchWindow, TextureListWidget, TextureNamePrompt, DefineSubtexturePrompt, ImageLabel,
showError, showQuery, showSelectOptions, NaturalListItem, getOutputPath)

BLANK_PATH = Path('.')

class TextureStudio(QMainWindow):
    def __init__(self, project_dir):
        super().__init__()
        self.project_dir = project_dir
        self.alphaThreshold = 0

        self.setWindowTitle("DSTS")
        self.setGeometry(100, 100, 1100, 700)
        self.createMenu()

        self._context_menu = QMenu(self)

        self.current_crop = None
        self.current_atlas = None
        self.thumbnail_cache = {}
        self.pending_replacements = {}
        self.pending_additions = {}
        self.pending_new_atlases = {}
        self.RESOLUTIONS = {}
        self.game = Game(None)

        container = QWidget()
        layout = QHBoxLayout(container)
        splitter = QSplitter(Qt.Horizontal)

        self.atlas_list = TextureListWidget()
        self.atlas_list.setItemDelegate(Delegate(self.atlas_list))
        self.atlas_list.itemClicked.connect(self.showAtlas)
        self.atlas_list.itemActivated.connect(self.showAtlas)
        self.atlas_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.atlas_list.customContextMenuRequested.connect(self.openSubtextureMenu)
        self.atlas_list.add_button.clicked.connect(self.addAtlas)
        splitter.addWidget(self.atlas_list)

        self.subtexture_list = TextureListWidget(mode=ImageType.Subtexture)
        self.subtexture_list.setItemDelegate(Delegate(self.subtexture_list))
        self.subtexture_list.itemClicked.connect(self.showSubtexture)
        self.subtexture_list.itemActivated.connect(self.showSubtexture)
        self.subtexture_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.subtexture_list.customContextMenuRequested.connect(self.openSubtextureMenu)
        self.subtexture_list.def_option.triggered.connect(lambda: self.addIcon(IconMode.Define))
        self.subtexture_list.add_option.triggered.connect(lambda: self.addIcon(IconMode.Append))
        splitter.addWidget(self.subtexture_list)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        self.preview_label = ImageLabel("Texture Preview")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("border: 1px solid gray; background: #222; color: white;")
        self.preview_label.setMinimumSize(600, 400)
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

    def closeEvent(self, event):
        def hasPendingChanges():
            return any((self.pending_additions, self.pending_replacements, self.pending_new_atlases))
        
        if not hasPendingChanges():
            event.accept()
            return

        result = QMessageBox.question(self, "Unsaved Changes", "You have unsaved changes. Are you sure you want to exit?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

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
        self.file_menu.addAction(createAction("Apply Changes", self.applyChanges))
        dump = self.file_menu.addMenu("Dump")
        dump.addAction(createAction("Atlases", lambda: self.dumpTextures(mode=ExportMode.ATLAS)))
        dump.addAction(createAction("Subtextures", lambda: self.dumpTextures(mode=ExportMode.SUBTEXTURE)))
        self.file_menu.addSeparator()
        self.file_menu.addAction(createAction("Clear", self.clear))
        self.file_menu.addAction(createAction("Exit", self.close))

        self.settings_menu = menu.addMenu("Settings")

        self.btn_useCustomNames = QAction("Custom Names", self)
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
        
        self.searchButton = menu.addAction(createAction("Search", self.openSearchWindow))

        self.help_menu = menu.addMenu("Help")
        self.help_menu.addAction(createAction("Settings", lambda: QMessageBox.information(self, "Settings", "<b>Custom Names:</b><br> When enabled, this setting replaces" \
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
        self.help_menu.addAction(createAction("Replacement", lambda: QMessageBox.information(self, "Replacement", 
                                                                                         "Pressing \"Replace\" will prompt you for an image file.<br>" \
                                                                                         "DSTS will then replace the currently selected texture, whether that be" \
                                                                                         " an atlas or a subtexture.<br><br>After replacing, go to" \
                                                                                         " File->Apply Changes to save. This may take a while.")))
        self.help_menu.addAction(createAction("Adding Icons", lambda: QMessageBox.information(self, "Adding Icons", 
                                                                                         "Pressing \"Add\" will prompt you for an image file.<br>" \
                                                                                         "DSTS will then append the image to the current selected atlas," \
                                                                                         " if possible.<br><br>Afterwards, go to" \
                                                                                         " File->Apply Changes to save. This may take a while.")))
        self.help_menu.addAction(createAction("About", lambda: QMessageBox.information(self, "About", 
                                                                                       "Made by <a href='https://linktr.ee/aerolitesr'>Aero</a> :><br><br>")))

    def openSubtextureMenu(self, position: QPoint):
        sender = self.sender()

        if sender == self.subtexture_list:
            item = self.subtexture_list.itemAt(position)
            if item is None:
                return

            current = self.atlas_list.currentItem()
            atlas_name = current.data(Qt.UserRole)
            dcx_file = Path(current.data(Qt.UserRole + 1))
            sub_name = item.data(Qt.UserRole)

            modify = self.isModified(dcx_file, atlas_name, sub_name)
            if modify == Modified.FALSE:
                return

            self.subtexture_list.setCurrentItem(item)
            self.showSubtexture(item)

            menu_pos = self.subtexture_list.viewport().mapToGlobal(position)

            menu = QMenu(self)

            if modify == Modified.ADDED:
                menu.addAction("Delete", lambda: self.deleteSubtexture(item))
                menu.addAction("Rename", lambda: self.renameSubtexture(item))

            elif modify == Modified.REPLACED:
                menu.addAction("Revert", lambda: self.revertSubtexture(item))

            menu.exec(menu_pos)

        elif sender == self.atlas_list:
            item = self.atlas_list.itemAt(position)
            if item is None:
                return

            atlas_name = item.data(Qt.UserRole)
            dcx_file = Path(item.data(Qt.UserRole + 1))

            modify = self.isModified(dcx_file, atlas_name)
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
        dcx_file = Path(atlas_item.data(Qt.UserRole+1))
        sub_name = sub_item.data(Qt.UserRole)

        self.atlases.get(atlas_name, {}).rem(sub_name)

        pending = self.pending_additions.get(dcx_file)
        if pending:
            pending["additions"] = [a for a in pending.get("additions", []) if a.name != sub_name]
            if not pending["additions"]:
                self.pending_additions.pop(dcx_file, None)

        repls_file = self.pending_replacements.get(dcx_file, {})
        repls_atlas = repls_file.get(atlas_name, {})

        if sub_name in repls_atlas:
            del repls_atlas[sub_name]

        if repls_file and not repls_atlas:
            repls_file.pop(atlas_name, None)
        if dcx_file in self.pending_replacements and not repls_file:
            self.pending_replacements.pop(dcx_file, None)

        self.rebuildAtlas(atlas_name, dcx_file)
        self.subtexture_list.takeItem(self.subtexture_list.row(sub_item))

        items = [self.subtexture_list.item(i) for i in range(self.subtexture_list.count())]

        if all(self.isModified(dcx_file, atlas_name, it.data(Qt.UserRole)) == Modified.FALSE for it in items):
            atlas_item.setForeground(Qt.white)

        self.showAtlas(atlas_item)

    def revertSubtexture(self, sub_item):
        atlas_item = self.atlas_list.currentItem()
        if not atlas_item or not sub_item:
            return

        atlas_name = atlas_item.data(Qt.UserRole)
        dcx_file = Path(atlas_item.data(Qt.UserRole+1))
        sub_name = sub_item.data(Qt.UserRole)

        repls_file = self.pending_replacements.get(dcx_file, {})
        repls_atlas = repls_file.get(atlas_name, {})

        if sub_name in repls_atlas:
            del repls_atlas[sub_name]

        if not repls_atlas:
            repls_file.pop(atlas_name, None)
        if not repls_file:
            self.pending_replacements.pop(dcx_file, None)

        self.rebuildAtlas(atlas_name, dcx_file)

        sub_item.setForeground(Qt.white)

        items = [self.subtexture_list.item(i) for i in range(self.subtexture_list.count())]

        if all(self.isModified(dcx_file, atlas_name, it.data(Qt.UserRole)) == Modified.FALSE for it in items):
            atlas_item.setForeground(Qt.white)

        self.showSubtexture(sub_item)

    def renameSubtexture(self, sub_item):
        atlas_item = self.atlas_list.currentItem()
        if not atlas_item or not sub_item:
            return

        atlas_name = atlas_item.data(Qt.UserRole)
        dcx_file = Path(atlas_item.data(Qt.UserRole+1))
        old_name = sub_item.data(Qt.UserRole)

        dialog = TextureNamePrompt(halfprompt=False, padprompt=False)
        if not dialog.exec():
            return

        new_name, _ = dialog.get_result()

        if self.atlases.get(atlas_name, {}).fetch(new_name): # returns None if SubTexture of that name isn't found
            showError(f"A subtexture named '{new_name}' already exists!")
            return

        self.atlases.get(atlas_name, {}).rename(old_name, new_name)

        for info in self.pending_additions.values():
            for a in info.get("additions", []):
                if a.name == old_name:
                    a.name = new_name

        repls = self.pending_replacements.get(dcx_file, {}).get(atlas_name, {})
        if old_name in repls:
            repls[new_name] = repls.pop(old_name)

        sub_item.setText(new_name)
        sub_item.setData(Qt.UserRole, new_name)

        self.rebuildAtlas(atlas_name, dcx_file)
        self.showSubtexture(sub_item)

    def deleteAtlas(self, atlas_item):
        if not atlas_item:
            return

        atlas_name = atlas_item.data(Qt.UserRole)
        dcx_file = Path(atlas_item.data(Qt.UserRole+1))

        pending = self.pending_new_atlases.get(dcx_file, [])
        self.pending_new_atlases[dcx_file] = [a for a in pending if a.name != atlas_name]

        if not self.pending_new_atlases[dcx_file]:
            self.pending_new_atlases.pop(dcx_file, None)

        add_data = self.pending_additions.get(dcx_file)
        if add_data:
            add_data["additions"] = [a for a in add_data["additions"] if a.parent != atlas_name]

            if not add_data["additions"]:
                self.pending_additions.pop(dcx_file, None)

        repls = self.pending_replacements.get(dcx_file, {})
        repls.pop(atlas_name, None)

        if not repls:
            self.pending_replacements.pop(dcx_file, None)

        self.thumbnail_cache.pop(atlas_name, None)

        self.atlas_list.takeItem(self.atlas_list.row(atlas_item))

    def renameAtlas(self, atlas_item):
        if not atlas_item:
            return

        old_name = atlas_item.data(Qt.UserRole)
        dcx_file = Path(atlas_item.data(Qt.UserRole+1))
        dialog = TextureNamePrompt(mode=ImageType.Texture)

        if not dialog.exec():
            return

        new_name, *_ = dialog.get_result()

        if new_name in self.atlases:
            showError(f"An atlas named '{new_name}' already exists!")
            return

        for atlases in self.pending_new_atlases.values():
            for atlas in atlases:
                if atlas.name == old_name:
                    atlas.name = new_name

        for info in self.pending_additions.values():
            for sub in info["additions"]:
                if sub.parent == old_name:
                    sub.parent = new_name

        repls = self.pending_replacements.get(dcx_file, {})
        if old_name in repls:
            repls[new_name] = repls.pop(old_name)

        if old_name in self.thumbnail_cache:
            self.thumbnail_cache[new_name] = self.thumbnail_cache.pop(old_name)

        if old_name in self.atlases:
            item = self.atlases.pop(old_name)
            item.name = new_name
            for sub in item.subtextures:
                if sub.parent is not None:
                    print(sub.parent, new_name)
                    sub.parent = new_name
            self.atlases[new_name] = item

        atlas_item.setText(new_name)
        atlas_item.setData(Qt.UserRole, new_name)

    def revertAtlas(self, atlas_item):
        if not atlas_item:
            return

        atlas_name = atlas_item.data(Qt.UserRole)
        dcx_file = Path(atlas_item.data(Qt.UserRole+1))

        repls = self.pending_replacements.get(dcx_file, {})
        atlas_repls = repls.get(atlas_name, {})

        atlas_repls.pop("*Self*", None)

        if not atlas_repls:
            repls.pop(atlas_name, None)

        if not repls:
            self.pending_replacements.pop(dcx_file, None)

        self.rebuildAtlas(atlas_name, dcx_file)
        self.showAtlas(atlas_item)

    def addAtlas(self):
        if self.game.type == GameType.PS:
            showError("Sorry! Additions are not currently supported for PS games (BB/DES)")
            return
        
        if self.atlas_list.count() == 0:
            showError('No files loaded!')
            return

        files = list(self.LOADED_DCX_FILES.keys())
        if len(files) > 1 and self.game.name != "Dark Souls 2": # doesn't need a parent as it writes to a standalone tpf
            ok, parent = showSelectOptions("Select parent file", "Files:", files)
            if not ok:
                return
        else:
            parent = files[0]
        dcx_file = Path(parent)


        dialog = TextureNamePrompt(mode=ImageType.Texture)
        if not dialog.exec():
            return
        name, _format, dimensions = dialog.get_result()

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

        blank = TPFTexture(stem=name, mipmap_count=1, format=Types.DDSFormats[_format], platform=TPFPlatform.PC)
        blank.replace_dds(img_path, dds_format=_format)
        new_atlas = Atlas(
            name=name,
            texture=blank,
            parent=parent
        )

        self.pending_new_atlases.setdefault(dcx_file, [])
        self.pending_new_atlases[dcx_file].append(new_atlas)
        self.atlases.setdefault(name, new_atlas)

        item = NaturalListItem(name)
        item.setData(Qt.UserRole, name) # original name
        item.setData(Qt.UserRole+1, parent) # parent file
        item.setSizeHint(QSize(0, 30))
        item.setData(Qt.UserRole+2, ImageType.Custom) # image type
        self.atlas_list.addItem(item)

        self.rebuildAtlas(name, dcx_file)
        self.atlas_list.setCurrentItem(item)
        self.showAtlas(self.atlas_list.currentItem())

    def addIcon(self, mode: IconMode = IconMode.Append):
        if self.game.type == GameType.PS:
            showError("Sorry! Additions are not currently supported for PS games (BB/DES)")
            return
        
        if self.atlas_list.count() == 0:
            showError('No atlases loaded!')
            return

        atlas_item = self.atlas_list.currentItem()
        if not atlas_item:
            showError('No atlas loaded!')
            return

        atlas_name = atlas_item.data(Qt.UserRole)
        dcx_file = Path(atlas_item.data(Qt.UserRole+1))
        subs = self.atlases.get(atlas_name, {}).subtextures

        match mode:
            case IconMode.Append:
                if not subs and not any(atlas_name == atlas.name for atlas in self.pending_new_atlases[dcx_file]):
                    showError("This atlas isn't mapped, sorry!")
                    return
    
                dialog = TextureNamePrompt()
                if not dialog.exec():
                    return

                name, padding, half = dialog.get_result()

                if name in subs:
                    showError("An icon of this name already exists!")
                    return
        
                img_path = Path(QFileDialog.getOpenFileName(self, "Select Image", "", "Image Files (*.png *.dds *.jpg *.webm *.jpeg);;All Files (*.*)")[0])
                if not img_path or img_path == BLANK_PATH:
                    return
                
                img = Image.open(img_path).convert('RGBA')
                w, h = img.size
                atlas_img = self.getPilImage(atlas_name)

                used_rects = [st.box(padding=padding) for st in subs]
                pos = getFreeSpace(atlas_img.size, used_rects, w, h, padding=padding)

                if pos:
                    x, y = pos
                else:
                    x = 0
                    y = atlas_img.size[1] + padding
                
            case IconMode.Define:
                dialog = DefineSubtexturePrompt()
                if not dialog.exec():
                    return

                name, hw, xy, half = dialog.get_result()

                if name in subs:
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
            img=img,
            vanilla=False,
            half=half
        )

        self.pending_additions.setdefault(dcx_file, {
            "data": self.LAYOUT_DATA.get(dcx_file),
            "additions": [],
            "output": dcx_file.with_name(dcx_file.name.replace('.tpf.dcx', '.sblytbnd.dcx'))
        })

        self.pending_additions[dcx_file]["additions"].append(sub)
        self.atlases[atlas_name].add(sub)

        self.rebuildAtlas(atlas_name, dcx_file)
        self.showAtlas(atlas_item)

    def clear(self):
        """Completely reset the window."""
        self.setWindowTitle("DSTS")
        self.atlas_list.clear()
        self.subtexture_list.clear()
        self.atlases = {}
        self.current_crop = None
        self.current_atlas = None
        self.thumbnail_cache = {}
        self.pending_additions = {}
        self.pending_replacements = {}
        self.pending_new_atlases = {}
        self.RESOLUTIONS = {}
        self.game = Game(None)
        self.preview_label.setText("Texture Preview")
        self.info_label.setText(("Texture Info", "Texture Info"))

    def checkOodleDLL(self):
        """Find the oodle dll, or prompt for its location"""
        target = self.project_dir / "oo2core_6_win64.dll"

        try:
            oodle.LOAD_DLL(target)
        except oodle.MissingOodleDLLError:
            try:
                dll = oodle.LOAD_DLL() # no args, checks default paths
                shutil.copy(dll, target)
                print("DEBUG:: oodle dll found in default paths and copied to DSTS")
                
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

    def openDcxDialog(self, dirmode: bool = False):
        """Handles everything to do with loading files. If dirmode = True, loads every dcx/tpf in a directory."""    
        self.clear()
        self.checkOodleDLL()

        if not dirmode:
            file_path = Path(QFileDialog.getOpenFileName(self, "Select File", "", "Texture Files (*.tpf.dcx *.tpf);;All Files (*.*)")[0])
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

            groups = defaultdict(lambda: {Resolution.HIGH: {}, Resolution.LOW: {}})
            standalone = []

            for f in files:
                name = f.name

                if "_h." in name:
                    prefix = name.split("_h.")[0]
                    res = Resolution.HIGH
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

                for res in [Resolution.HIGH, Resolution.LOW]:
                    if "tpf" in data[res]:
                        available.append(res)

                if not available:
                    continue

                if len(available) > 1:
                    ok, choice = showSelectOptions("Select Resolution", f"{prefix} has both high and low resolution. Which do you want?", 
                                                        [i.display   for i in available])
                    if not ok:
                        return
                    choice = next(r for r in available if r.name == choice)
                else:
                    choice = available[0]

                tpf = data[choice].get("tpf")
                layout = data[choice].get("layout")

                if tpf and not layout and ('_common_' in Path(tpf).stem):
                    layout_path = QFileDialog.getOpenFileName(self, f"Select layout for {tpf.name}", str(tpf.parent), "Layout Files (*.sblytbnd.dcx)")[0]

                    if layout_path:
                        layout = Path(layout_path)
                    else:
                        showError("Layout file doesn't exist. Loading raw atlases instead.")

                if layout:
                    file_mappings.append({"file": tpf, "layout": layout})
                else:
                    file_mappings.append(tpf)
                
                self.RESOLUTIONS[prefix] = choice

            file_mappings.extend(standalone) # no layout

        elif self.game.name in ['Sekiro', 'Elden Ring']:
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

                        if not layout.exists():
                            showError("Layout file doesn't exist!")
                            return

                if layout:
                    file_mappings.append({"file": f, "layout": layout})
                else:
                    file_mappings.append(f)

                self.RESOLUTIONS[base_name] = Resolution.LOW if path_has_sequence(f.parts, ['menu', 'low']) else Resolution.HIGH
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

    def extractionDone(self, success=True, saved_path: Path|None = None):
        """Stuff to do after extraction finishes"""
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
        else:
            QMessageBox.critical(self, "Error", f"Tasks Failed!")

    def toggleCustomNames(self):
        """Replaces displaying text for QListWidgetItems with the mapped ones whilst retaining the original in UserRole"""

        def restoreNames(widget: QListWidget):
            for idx in range(widget.count()):
                item = widget.item(idx)
                item.setText(item.data(Qt.UserRole))

        if self.btn_useCustomNames.isChecked():
            for idx in range(self.atlas_list.count()):
                item = self.atlas_list.item(idx)
                text = item.text()
                if self.game.name == 'Dark Souls 2': # special handling due to weird naming system
                    text = text[text.rfind('_')+1:]

                name = Maps.AtlasNames[self.game.name].get(text, None) or item.text()
                item.setText(name)
            
            for idx in range(self.subtexture_list.count()):
                item = self.subtexture_list.item(idx)
                text = item.text()

                _, *pieces = text.split('_')
                try:
                    id = pieces[-1]
                    _type = pieces[0]
                    name = Maps.TextureNames[self.game.name].get(_type, {}).get(id.lstrip('0'), None) or text
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

    def openSearchWindow(self):
        """Creates a SearchWindow instance and handles the search."""

        def handle_search(text, atlasMode):
            widget = self.atlas_list if atlasMode else self.subtexture_list

            if widget.count() == 0:
                showError('No Textures are loaded.')
                return

            text = text.lower().strip()
            found = False
            first_match = None

            for i in range(widget.count()):
                item = widget.item(i)

                matches = text in item.text().lower()
                item.setHidden(not matches)

                if matches and first_match is None:
                    first_match = item
                    found = True

            if found:
                widget.setCurrentItem(first_match)
                first_match.setSelected(True)
                widget.scrollToItem(first_match)
            else:
                showError('No results found!')

        self.searchInstance = SearchWindow()
        self.searchInstance.results.connect(handle_search)
        self.searchInstance.show()

    def resolveSubtexture(self, atlas_name, sub_name, atlas_img) -> SubTexture:
        """Return subtexture rect from either layout or grid system."""

        st = self.atlases.get(atlas_name, {}).fetch(sub_name)
        if st:
            return st

        texmap = Maps.TextureDimensions[self.game.name]
        dimensions = texmap.get(atlas_name)

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

        return SubTexture(
            name=sub_name,
            x=col * tile_w,
            y=row * tile_h,
            width=tile_w,
            height=tile_h
        )

    def queueReplacement(self, dcx_file: Path, atlas_item, sub_item, img_path: Path):
        atlas_name = atlas_item.data(Qt.UserRole)
        dcx_file = Path(dcx_file)
        sub_name = sub_item.data(Qt.UserRole) if sub_item else "*Self*"

        try:
            new_img = Image.open(img_path).convert("RGBA")
        except UnidentifiedImageError:
            showError("Selected file is not an image supported by PIL.")
            return

        if sub_name and sub_name != "*Self*":
            atlas_img = self.getPilImage(atlas_name)
            st = self.resolveSubtexture(atlas_name, sub_name, atlas_img)

            if not st:
                showError(f"Could not resolve subtexture: {sub_name}")
                return

            new_img = new_img.resize((st.width, st.height), Image.Resampling.LANCZOS)

        self.pending_replacements.setdefault(dcx_file, {}).setdefault(atlas_name, {})
        self.pending_replacements[dcx_file][atlas_name][sub_name] = new_img

        self.rebuildAtlas(atlas_name, dcx_file)

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

        if self.game.type == GameType.PS:
            showError("Sorry! Replacements are not currently supported for PS4 games (BB/DES)")
            return
        
        atlas = self.atlas_list.currentItem()
        sub = self.subtexture_list.currentItem()
        dcx_file = atlas.data(Qt.UserRole+1)

        if not atlas:
            showError('No atlas loaded!')
            return

        img_path = Path(QFileDialog.getOpenFileName(self, "Select Image", "", "Image Files (*.png *.dds *.jpg *.webp *.jpeg);;All Files (*.*)")[0])
        if not img_path or img_path == BLANK_PATH:
            return
        
        self.queueReplacement(Path(dcx_file), atlas, sub, Path(img_path))

    def applyChanges(self):
        """Start replacement from File menu and create popup."""
        if not self.pending_replacements and not self.pending_additions and not self.pending_new_atlases:
            QMessageBox.information(self, "Info", "No actions queued.")
            return
        
        output_dir = getOutputPath()
        if not output_dir:
            return
    
        self.replace_dialog = QProgressDialog("Applying changes...", None, 0, 0, self)
        self.replace_dialog.setWindowTitle("Processing")
        self.replace_dialog.setWindowModality(Qt.ApplicationModal)
        self.replace_dialog.setCancelButton(None)
        self.replace_dialog.setMinimumDuration(0)
        self.replace_dialog.setMinimumWidth(300)
        self.replace_dialog.show()
        self.replace_dialog.setStyleSheet("""QLabel {qproperty-alignment: AlignCenter;} QProgressBar {text-align: center;}""")

        self.r_thread = QThread()
        self.r_worker = WriteWorker(self.pending_new_atlases, self.pending_replacements, self.pending_additions, self.LOADED_DCX_FILES, self.LAYOUT_DATA,
                                      self.getPilImage, self.game, self.RESOLUTIONS, output_dir)
        self.r_worker.moveToThread(self.r_thread)
        self.r_thread.started.connect(self.r_worker.run)

        self.r_worker.finished.connect(self.r_thread.quit)
        self.r_worker.finished.connect(self.changesDone)
        self.r_worker.finished.connect(self.r_worker.deleteLater)
        self.r_thread.finished.connect(self.r_thread.deleteLater)
        
        self.r_thread.start()

    def changesDone(self, success: bool, msg: str, saved_path: Path):
        """Triggered on completion of tpf/dcx export."""
        self.replace_dialog.close()
        if success:
            self.extractionDone(True, saved_path)
            self.pending_replacements.clear()
        else:
            showError(msg)

    def formatImageInfo(self, name, file, pil_img, coords='None', img_type: ImageType = ImageType.Atlas):
        """Properly format information about the selected preview to display."""
        def formatSize(bytes_val):
            kb = bytes_val / 1024
            if kb < 1024:
                return f"{kb:.1f} KB"
            return f"{kb / 1024:.2f} MB"
        
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
            t_info = tpft.get_texture_format_info(tpft.format)
            t_format = TPF_TEXTURE_FORMAT_TO_DXGI_FORMAT[tpft.format]
            
            expanded += (
            f"<b>Platform:</b> {tpft.platform.name}<br>"
            f"<b>Format:</b> {t_format.name}<br>"
            f"<b>Mipmap Count:</b> {tpft.mipmap_count}<br>"
            f"<b>Texture Flags:</b> {tpft.texture_flags}<br>"
            f"<b>Fourcc:</b> {t_info[0]}<br>"
            f"<b>Bytes Per Block:</b> {t_info[1]}<br>"
            f"<b>Bits Per Pixel:</b> {DXGI_FORMAT_BPP[t_format]}<br>"
            f"<b>Is Compressed:</b> {t_info[2]}<br><br>"
            f"<b>Console Info:</b> {c_info}<br><br>")
        
        return short, expanded

    def rebuildAtlas(self, atlas_name, dcx_file):
        """Reconstruct the atlas with its changes"""
        base_img = self.resolveAtlas(atlas_name, dcx_file)

        additions = (self.pending_additions.get(dcx_file, {}).get("additions", []))

        for add in additions:
            if add.parent != atlas_name or add.img is None:
                continue

            img = add.img
            x = int(add.x)
            y = int(add.y)

            if y + img.height > base_img.height:
                new_height = y + img.height
                new_img = Image.new("RGBA", (base_img.width, new_height), (0, 0, 0, 0))
                new_img.paste(base_img, (0, 0))
                base_img = new_img

            base_img.paste(img, (x, y))

        atlas_repls = (self.pending_replacements.get(dcx_file, {}).get(atlas_name, {}))

        for sub_name, img in atlas_repls.items():
            if sub_name == "*Self*": # full atlas replacement
                base_img = img.copy()
                continue

            st = self.resolveSubtexture(atlas_name, sub_name, base_img)
            if not st:
                continue

            base_img.paste(img, st.pos)

        self.thumbnail_cache[atlas_name] = base_img

    def resolveAtlas(self, atlas_name, dcx_file):
        """Returns pending new atlases first, else original"""
        pending = self.pending_new_atlases.get(dcx_file, [])
        for a in pending:
            if a.name == atlas_name:
                return self.getBaseImage(texture=a.texture)

        return self.getBaseImage(atlas=atlas_name)

    def getBaseImage(self, atlas=None, texture=None):
        """Converts texture bytes to viewable image. If no texture is given it fetches the texture from atlas name"""
        if not texture:
            texture = self.atlases[atlas].texture
        with BytesIO(texture.data) as dds_buffer:
            return Image.open(dds_buffer).convert("RGBA")

    def getPilImage(self, atlas_name, return_atlas=False, createDebug=False):
        """Returns rendered preview (rebuild if needed)"""
        
        if return_atlas: # hacky way of getting a raw Atlas object into WriteWorker but i cba
            return self.atlases[atlas_name]

        if atlas_name not in self.thumbnail_cache:
            atlas_item = self.atlas_list.currentItem()
            dcx_file = Path(atlas_item.data(Qt.UserRole+1)).name
            self.rebuildAtlas(atlas_name, dcx_file)

        img = self.thumbnail_cache.get(atlas_name)

        if img is None:
            img = self.getBaseImage(atlas=atlas_name)

        if createDebug:
            img = createDebugGrid(img, self.atlases[atlas_name].subtextures)

        if self.alphaThreshold > 0:
            img = cleanByAlpha(img, threshold=self.alphaThreshold)

        return img

    def isModified(self, dcx_file, atlas_name, sub_name=None):
        """Returns True if subtexture has been modified, for recoloring its entry."""
        if sub_name is None: # atlas check
            if self.pending_replacements.get(dcx_file, {}).get(atlas_name) == "*Self*":
                return Modified.REPLACED

            if any(atlas_name == atlas.name for atlas in self.pending_new_atlases.get(dcx_file, [])):
                return Modified.ADDED

            return Modified.FALSE
        
        if sub_name in self.pending_replacements.get(dcx_file, {}).get(atlas_name, {}):
            return Modified.REPLACED
        additions = self.pending_additions.get(dcx_file, {}).get('additions', [])
        if any(sub_name == i.name for i in additions):
            return Modified.ADDED
        
        return Modified.FALSE

    def showAtlas(self, current):
        """Display the selected atlas, and load all subtextures to the list."""
        if not current:
            return
        atlas_name = current.data(Qt.UserRole)
        dcx_file = Path(current.data(Qt.UserRole+1))
        self.current_atlas = atlas_name
        self.current_crop = None

        atlas_img = self.getPilImage(atlas_name, createDebug=self.btn_atlasGrid.isChecked())
        preview_img = atlas_img.copy()
        preview_img.thumbnail(self.preview_label.size().toTuple(), Image.Resampling.LANCZOS)
        self.preview_label.setPixmap(pil2Qpixmap(preview_img))

        # Load subtextures
        self.subtexture_list.blockSignals(True)
        self.subtexture_list.clear()
        for sub in self.atlases.get(atlas_name, Atlas).subtextures:
            if self.btn_hideBlankIcons.isChecked() and sub.blank:
                continue
            name = sub.name

            item = NaturalListItem(name)
            item.setData(Qt.UserRole, name)
            item.setSizeHint(QSize(0, 30))

            match self.isModified(dcx_file, atlas_name, name):
                case Modified.REPLACED:
                    item.setForeground(Qt.yellow)
                    current.setForeground(Qt.yellow)
                case Modified.ADDED:
                    item.setForeground(Qt.green)
                    current.setForeground(Qt.yellow)

            self.subtexture_list.addItem(item)
        
        match self.isModified(dcx_file, atlas_name, None): # check if whole atlas is modified
            case Modified.ADDED:
                current.setForeground(Qt.green)
            case Modified.REPLACED:
                current.setForeground(Qt.yellow)

        self.subtexture_list.blockSignals(False)
        self.subtexture_list.sortItems()

        self.info_label.setText(self.formatImageInfo(atlas_name, dcx_file.name, atlas_img, img_type=current.data(Qt.UserRole+2)))
        self.toggleCustomNames() # just to update it

    def showSubtexture(self, current):
        """Display a preview of the selected subtexture."""
        if not current or not self.current_atlas:
            return
        
        try:
            name = current.data(Qt.UserRole)
            st = self.atlases[self.current_atlas].fetch(name)
            atlas_img = self.getPilImage(self.current_atlas)
            dcx_file = self.atlas_list.currentItem().data(Qt.UserRole+1).name
        except KeyError:
            self.subtexture_list.blockSignals(False)
            return

        cropped = atlas_img.crop(st.box())
        cropped.thumbnail(self.preview_label.size().toTuple(), Image.Resampling.LANCZOS)

        self.preview_label.setPixmap(pil2Qpixmap(cropped))
        self.current_crop = cropped
        self.info_label.setText(self.formatImageInfo(name, dcx_file, cropped, st.pos, img_type=ImageType.Subtexture))

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
                ok, choice = showSelectOptions("Select Export", f"The currently selected texture is an atlas.\nWould you like to export the whole image, " \
                                                    "or its subtextures?", ["Full Atlas", "All Subtextures"])
                
                if not ok:
                    return
                if choice == "All Subtextures":
                    self.saveAll()
                    return

            out_path = self.project_dir / "Output" / ".Atlases"
            out_path.mkdir(parents=True, exist_ok=True)

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

def getIcon(base_path):
    if getattr(sys, 'frozen', False):
        return QIcon(str(Path(sys.executable).parent / 'icon.ico'))
    else:
        return QIcon(str(base_path / 'icon.ico'))

def main():
    app = QApplication(sys.argv)
    base_path = Path(sys.argv[0]).parent
    app.setStyleSheet(Palettes.DARK_STYLESHEET)
    app.setWindowIcon(getIcon(base_path))
    window = TextureStudio(project_dir=base_path)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

# nuitka --standalone --onefile --windows-console-mode=disable --enable-plugin=pyside6 --windows-icon-from-ico=icon.ico --include-data-file=icon.ico=icon.ico --include-data-file=soulstruct\base\textures\texconv.exe=soulstruct\base\textures\texconv.exe --include-module=constrata --include-module=soulstruct --msvc=latest --lto=yes DSTS.py
# pyinstaller DSTS.py --noconsole --icon=icon.ico --add-data "icon.ico;." --add-binary "soulstruct/base/textures/texconv.exe;soulstruct/base/textures" --collect-data soulstruct
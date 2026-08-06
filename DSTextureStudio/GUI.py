from PySide6.QtWidgets import (QWidget, QVBoxLayout, QCheckBox, QDialog, QLabel, QPushButton, QMessageBox, QLineEdit, QComboBox, QDialogButtonBox, QButtonGroup, QRadioButton,
QStyledItemDelegate, QGraphicsView, QGraphicsScene, QListWidget, QInputDialog, QSpinBox, QHBoxLayout, QMenu, QListWidgetItem, QFileDialog, QFormLayout)
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QRect, QPoint, QTimer
from PySide6.QtGui import QPalette, QPainter, QAction, QCursor, QColor, QGuiApplication, QBrush, QPixmap, QTextDocumentFragment
from DSTextureStudio.GameInfo import DXGI_STRUCT_MAP, SubtexturePrefix
from DSTextureStudio.Enums import Game, ImageType, GameType, BackgroundMode
from typing import Callable, Optional
import re
from pathlib import Path
from soulstruct.dcx.core import DCXType
import logging

logger = logging.getLogger(__name__)

class NaturalListItem(QListWidgetItem):
    def __init__(self, text):
        super().__init__(text)
        self.setForeground(Qt.white)

    @staticmethod
    def naturalSortKey(text):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', text)]
    
    def __lt__(self, other):
        return NaturalListItem.naturalSortKey(self.text()) < NaturalListItem.naturalSortKey(other.text())

class Delegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)

        brush = index.data(Qt.ForegroundRole)
        if brush:
            option.palette.setBrush(QPalette.HighlightedText, brush)

class ExpandableLabel(QLabel):
    def __init__(self, short_text, full_text, parent=None, ispopup=False):
        super().__init__(short_text, parent)

        self.short_text = short_text
        self.full_text = full_text
        self.ispopup = ispopup

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            match self.ispopup:
                case True:
                    self.collapse()
                case False:
                    self.expand()
            return

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        copy_action = menu.addAction("Copy")
        action = menu.exec(event.globalPos())

        if action == copy_action:
            text = QTextDocumentFragment.fromHtml(self.text()).toPlainText()
            QGuiApplication.clipboard().setText(text)

    def setText(self, text: tuple[str, str]):
        """Takes a tuple of short text and full text for when expanded."""
        self.short_text, self.full_text = text
        super().setText(self.full_text if self.ispopup else self.short_text)

        if not self.ispopup and hasattr(self, "popup") and self.popup is not None:
            try:
                self.popup.setText(text)
            except RuntimeError:
                self.popup = None

    def expand(self):
        window = self.window()
        window._min = window.minimumSize()
        window._max = window.maximumSize()
        size = window.size()
        window.setMinimumSize(size)
        window.setMaximumSize(size)

        top_left = self.mapTo(window, self.rect().topLeft())

        start_rect = QRect(top_left.x(), top_left.y(), self.width(), self.height())
        end_rect = start_rect.adjusted(-80, -240, 0, 0)

        self.popup = ExpandableLabel(
            self.full_text,
            self.full_text,
            window,
            ispopup=True)
        self.popup.setWordWrap(True)
        self.popup.setGeometry(start_rect)
        self.popup.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.popup.setStyleSheet("""
            QLabel {
                background-color: #333333;
                border: 2px solid #888;
                border-radius: 8px;
                padding: 10px;
            }""")
        self.popup.show()

        self.popup.origin_rect = start_rect

        self.anim = QPropertyAnimation(self.popup, b"geometry")
        self.anim.setDuration(100)
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(end_rect)
        self.anim.start()

    def collapse(self):
        window = self.window()
        end_rect = self.origin_rect

        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(100)
        self.anim.setStartValue(self.geometry())
        self.anim.setEndValue(end_rect)

        def unlock():
            window.setMinimumSize(window._min)
            window.setMaximumSize(window._max)
            self.deleteLater()

        self.anim.finished.connect(unlock)
        self.anim.start()

class Palettes():
    DARK_STYLESHEET = """
    QWidget {
        background-color: #1E1E1E;
        color: #FFFFFF;
    }

    QPushButton {
        background-color: #2D2D2D;
        color: #FFFFFF;
    }

    QPushButton:hover {
        background-color: #313131;
    }

    QPushButton:pressed {
        background-color: #2A2A2A;
    }

    QPushButton:disabled {
        color: #777777;
    }

    QListWidget {
        background-color: #2D2D2D;
        color: #FFFFFF;
        border: 1px solid #2D2D2D;
        border-radius: 6px;
    }

    QMenuBar {
        background-color: #1E1E1E;
    }

    QMenuBar::item {
        background: transparent;
        color: white;
        padding: 4px 8px;
    }

    QMenuBar::item:selected {
        background-color: #313131;
    }

    QMenuBar::item:pressed {
        background-color: #313131;
    }

    QMenu {
        background-color: #0F0F0F;
        color: #FFFFFF;
        border: 1px solid #3A3A3A;
        border-radius: 6px;
    }

    QMenu::item {
        background-color: #0F0F0F;
        padding: 5px 30px 5px 10px; /* top right bottom left */
        border: 0px solid #3A3A3A;
        border-radius: 6px;
    }

    QMenu::item:selected {
        background-color: #1D1D1D;
        padding: 3px 30px 3px 10px; /* top right bottom left */
        border-radius: 6px;
    }

    QMenu::separator {
        height: 1px;
        background: #3A3A3A;
        margin: 5px 6px 5px 6px;
    }

    QSplitter::handle {
        background: #1E1E1E;
    } /* if i ever wana try get fusion to work */

    QCheckBox {
        color: #FFFFFF;
    }

    QComboBox {
        background-color: #2D2D2D;
        color: white;
        padding: 3px 0px 3px 4px;
        border: 1px solid #555;
    }

    QSpinBox {
        background-color: #3C3C3C;
    }

    QLineEdit {
        background-color: #3C3C3C;
        border-radius: 4px;
    }

    QMessageBox,
    QInputDialog {
        background-color: #1E1E1E;
        color: #FFFFFF;
    }

    QListWidget {
        background-color: #2D2D2D;
        color: #FFFFFF;
        border: none;
        outline: 0;
        font-family: "Segoe UI";
        font-size: 9pt;
        padding: 1px;
    }

    QListWidget::item {
        border: none;
        padding: 0px 8px 0px 8px; /* top right bottom left */
        border-radius: 4px;
    }

    QListWidget::item:hover {
        background-color: #3A3A3A;
        border-radius: 4px;
        margin: 2px 2px 2px 0px; /* top right bottom left */
    }

    QListWidget::item:selected {
        background-color: #393939;
        padding: 0px 10px 0px 10px; /* top right bottom left */

        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,

            stop:0      transparent,
            stop:0.015  #2AA8FF,
            stop:0.022  #2AA8FF,
            stop:0.023  transparent,
            stop:0.05   #464646,
            stop:1      #464646
        );

        border-radius: 4px;
        margin: 2px;
    }

    QListWidget::item:focus {
        outline: none;
        border-radius: 4px;
    }

    QListWidget QScrollBar:vertical {
        background: #2D2D2D;
        width: 6px;
        margin: 0px;
        padding: 5px 0px 5px 0px; /* top right bottom left */
        border-radius: 3px;
    }

    QListWidget QScrollBar::handle:vertical {
        background: #444444;
        border: 0px;
        border-radius: 3px;
        min-height: 50px;
    }

    QListWidget QScrollBar::handle:vertical:hover {
        background: #575757;
    }

    QListWidget QScrollBar::add-line:vertical,
    QListWidget QScrollBar::sub-line:vertical {
        height: 0px;
    }

    QListWidget QScrollBar::add-page:vertical,
    QListWidget QScrollBar::sub-page:vertical {
        background: none;
    }
    """

class TextureNamePrompt(QDialog):
    def __init__(self, mode: ImageType = ImageType.Subtexture, resizeprompt=True, padprompt=True, halfprompt=True, formatprompt=True, blankprompt=True):
        super().__init__()
        self.mode = mode
        self.halfprompt = halfprompt # s
        self.padprompt = padprompt # s
        self.resizeprompt = resizeprompt # s
        self.formatprompt = formatprompt # a
        self.blankprompt = blankprompt # a
        self.setWindowTitle("Prompt")

        self.b_width_label = None
        self.b_height_label = None
        self.b_width_input = None
        self.b_height_input = None

        self.r_width_label = None
        self.r_height_label = None
        self.r_width_input = None
        self.r_height_input = None

        self.layout = QVBoxLayout()

        if self.mode == ImageType.Subtexture:
            self.layout.addWidget(QLabel("Prefix:"))
            self.prefix_input = QComboBox()
            self.prefix_input.addItems(SubtexturePrefix)
            self.prefix_input.setEditable(True)
            self.layout.addWidget(self.prefix_input)

            self.layout.addWidget(QLabel("Icon ID:"))
            self.id_input = QLineEdit()
            self.layout.addWidget(self.id_input)

            if self.padprompt:
                self.padding_label = QLabel("Padding:")
                self.padding_input = QSpinBox()
                self.padding_input.setRange(0, 512)
                self.padding_input.setValue(2)

                self.layout.addWidget(self.padding_label)
                self.layout.addWidget(self.padding_input)

            if self.halfprompt:
                self.half_checkbox = QCheckBox("Half")
                self.layout.addWidget(self.half_checkbox)

            if self.resizeprompt:
                self.resize_checkbox = QCheckBox("Resize Image")
                self.resize_checkbox.toggled.connect(self.resize_toggle_size_fields)
                self.layout.addWidget(self.resize_checkbox)

                self.resize_container = QWidget()
                resize_layout = QFormLayout(self.resize_container)

                self.r_width_input = QSpinBox()
                self.r_width_input.setRange(1, 8192)
                self.r_width_input.setValue(160)

                self.r_height_input = QSpinBox()
                self.r_height_input.setRange(1, 8192)
                self.r_height_input.setValue(160)

                resize_layout.addRow("Width:", self.r_width_input)
                resize_layout.addRow("Height:", self.r_height_input)

                self.layout.addWidget(self.resize_container)

                self.resize_container.hide()

        else:
            self.layout.addWidget(QLabel("Atlas Name:"))
            self.name_input = QLineEdit()
            self.layout.addWidget(self.name_input)

            if self.formatprompt:
                self.layout.addWidget(QLabel("Format:"))
                self.format_input = QComboBox()
                self.format_input.addItems([i.name for i in DXGI_STRUCT_MAP.keys()])
                self.layout.addWidget(self.format_input)
            
            if self.blankprompt:
                self.blank_checkbox = QCheckBox("Blank Image")
                self.blank_checkbox.toggled.connect(self.blank_toggle_size_fields)
                self.layout.addWidget(self.blank_checkbox)

                self.blank_container = QWidget()
                blank_layout = QFormLayout(self.blank_container)

                self.b_width_input = QSpinBox()
                self.b_width_input.setRange(1, 8192)
                self.b_width_input.setValue(1024)

                self.b_height_input = QSpinBox()
                self.b_height_input.setRange(1, 8192)
                self.b_height_input.setValue(1024)

                blank_layout.addRow("Width:", self.b_width_input)
                blank_layout.addRow("Height:", self.b_height_input)

                self.layout.addWidget(self.blank_container)

                self.blank_container.hide()

        self.form_layout = QVBoxLayout()
        self.layout.addLayout(self.form_layout)

        self.submit_button = QPushButton("Submit")
        self.layout.addWidget(self.submit_button)

        self.setLayout(self.layout)

        self.submit_button.clicked.connect(self.accept)

    def blank_toggle_size_fields(self, checked):
        self.blank_container.setVisible(checked)
        self.adjustSize()

    def resize_toggle_size_fields(self, checked):
        self.resize_container.setVisible(checked)
        self.adjustSize()
            
    def get_result(self):
        if self.mode == ImageType.Subtexture:
            half = self.half_checkbox.isChecked() if self.halfprompt else False

            resize = ((self.r_width_input.value(), self.r_height_input.value()) if self.resizeprompt and self.resize_checkbox.isChecked() else None)

            image_id = self.id_input.text()
            if not image_id.isdigit() or not 0 <= int(image_id) < 65536:
                showError(
                    "Inputted ID is not an asserted UInt16.<br>"
                    "This may throw errors in Smithbox or elsewhere.<br>"
                    "Rename this icon if that wasn't your intention.",
                    "Warning",
                    QMessageBox.Warning)

            name = f"{self.prefix_input.currentText()}{image_id}"

            if self.padprompt:
                return name, self.padding_input.value(), resize, half
            return name, resize, half

        coords = ((self.b_width_input.value(), self.b_height_input.value()) if self.blankprompt and self.blank_checkbox.isChecked() else None)
        fmt = self.format_input.currentText() if self.formatprompt else None
        return self.name_input.text(), fmt, coords
        
class DefineSubtexturePrompt(QDialog):
    def __init__(self, maxwidth, maxheight):
        super().__init__()
        self.setWindowTitle("Prompt")

        self.layout = QVBoxLayout()

        self.layout.addWidget(QLabel("Prefix:"))
        self.prefix_input = QComboBox()
        self.prefix_input.addItems(SubtexturePrefix)
        self.prefix_input.setEditable(True)
        self.layout.addWidget(self.prefix_input)

        self.layout.addWidget(QLabel("Icon ID:"))
        self.id_input = QLineEdit()
        self.layout.addWidget(self.id_input)
        
        size_layout = QHBoxLayout()

        size_layout.addWidget(QLabel("Width:"))
        self.width_input = QSpinBox()
        self.width_input.setRange(1, maxwidth)
        self.width_input.setValue(128)
        size_layout.addWidget(self.width_input)

        size_layout.addSpacing(10)

        size_layout.addWidget(QLabel("Height:"))
        self.height_input = QSpinBox()
        self.height_input.setRange(1, maxheight)
        self.height_input.setValue(128)
        size_layout.addWidget(self.height_input)

        self.layout.addLayout(size_layout)

        xy_layout = QHBoxLayout()

        xy_layout.addWidget(QLabel("X:"))
        self.x_input = QSpinBox()
        self.x_input.setRange(0, 8192)
        self.x_input.setValue(0)
        xy_layout.addWidget(self.x_input)

        xy_layout.addSpacing(10)

        xy_layout.addWidget(QLabel("Y:"))
        self.y_input = QSpinBox()
        self.y_input.setRange(0, 8192)
        self.y_input.setValue(0)
        xy_layout.addWidget(self.y_input)

        self.layout.addLayout(xy_layout)

        self.half_checkbox = QCheckBox("Half")
        self.layout.addWidget(self.half_checkbox)

        self.submit_button = QPushButton("Submit")
        self.layout.addWidget(self.submit_button)

        self.setLayout(self.layout)

        self.submit_button.clicked.connect(self.accept)

    def get_result(self):
        half = self.half_checkbox.isChecked()

        id = self.id_input.text()
        if not id.isdigit() or not 0 <= int(id) < 65536:
            showError("Inputted ID is not an asserted UInt16.<br>This may silently throw errors in Smithbox or elsewhere.<br>Rename this icon if that wasn't your intention.", "Warning", QMessageBox.Warning)
        
        hwcoords = (self.width_input.value(), self.height_input.value())
        xycoords = (self.x_input.value(), self.y_input.value())
        return f"{self.prefix_input.currentText()}{id}", hwcoords, xycoords, half

class CompressionPrompt(QDialog):
    def __init__(self, name):
        super().__init__()
        self.setWindowTitle("Prompt")
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)

        self.layout = QVBoxLayout()

        self.compression_label = QLabel(f"Select compression for: \'{name}\'")
        self.compression_label.setToolTip("Set to Null to write uncompressed TPF")
        self.layout.addWidget(self.compression_label)
        self.format_input = QComboBox()
        self.format_input.addItems([i.name for i in DCXType if i.name != "Unknown"])
        self.layout.addWidget(self.format_input)

        self.encoding_input = QSpinBox()
        self.encoding_input.setRange(0, 2)
        self.encoding_input.setValue(2)
        self.encoding_input.setToolTip("0/2 = shift_jis_2004; 1 = UTF-16")

        enc_layout = QHBoxLayout()
        enc_layout.addWidget(QLabel("Encoding Type:"))
        enc_layout.addWidget(self.encoding_input)

        self.layout.addLayout(enc_layout)

        self.reuse_checkbox = QCheckBox("Use for all exports")
        self.layout.addWidget(self.reuse_checkbox)

        self.submit_button = QPushButton("Submit")
        self.layout.addWidget(self.submit_button)

        self.setLayout(self.layout)

        self.submit_button.clicked.connect(self.accept)

    def get_result(self):
        return self.format_input.currentText(), self.encoding_input.value(), self.reuse_checkbox.isChecked()
   
class InvalidImagePrompt(QDialog):
    CANCEL = 0
    IGNORE = 1
    RESIZE = 2
    PAD = 3
    NEW = 4

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Invalid Texture")

        layout = QVBoxLayout(self)

        self.group = QButtonGroup(self)

        info = QLabel("Swizzled textures should have dimensions divisible by 8.\nWhat would you like to do with this texture?")

        cancel = QRadioButton("Cancel Addition")
        ignore = QRadioButton("Ignore Warning")
        resize = QRadioButton("Resize Image")
        pad = QRadioButton("Pad Image With Alpha")
        new = QRadioButton("Choose A New Image")

        self.group.addButton(cancel, self.CANCEL)
        self.group.addButton(ignore, self.IGNORE)
        self.group.addButton(resize, self.RESIZE)
        self.group.addButton(pad, self.PAD)
        self.group.addButton(new, self.NEW)

        cancel.setChecked(True)

        layout.addWidget(info)
        layout.addWidget(cancel)
        layout.addWidget(ignore)
        layout.addWidget(resize)
        layout.addWidget(pad)
        layout.addWidget(new)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

    def selected(self):
        return self.group.checkedId()


class ImageLabel(QLabel):
    def __init__(self, text, fetchimg, parent=None):
        self.fetch_img = fetchimg
        super().__init__(parent, text=text)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.openView()

    def openView(self):
        if self.pixmap():
            self.viewer = ImageViewer(self.fetch_img())
            self.viewer.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
            self.viewer.showFullScreen()

class ImageViewer(QGraphicsView):
    def makeCheckerBrush(self, size=16):
        pix = QPixmap(size * 2, size * 2)
        pix.fill(QColor(240, 240, 240))

        p = QPainter(pix)
        p.fillRect(0, 0, size, size, QColor(200, 200, 200))
        p.fillRect(size, size, size, size, QColor(200, 200, 200))
        p.end()

        return QBrush(pix)

    def __init__(self, pixmap, parent=None):
        super().__init__(parent)

        self.setScene(QGraphicsScene(self))
        self.pixmap_item = self.scene().addPixmap(pixmap)
        self.setRenderHints(self.renderHints() |
                            QPainter.Antialiasing |
                            QPainter.SmoothPixmapTransform)

        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("background-color: black; border: none;")
        self.zoom_factor = 1.0
        self.zoom_step = 1.25
        self.min_zoom = 0.1
        self.max_zoom = 75.0
        self.auto_fit = True
        self.checker_brush = self.makeCheckerBrush()
        self.background_mode = BackgroundMode.BLACK  # 0=black, 1=white, 2=checkerboard

        self.scene().setSceneRect(self.pixmap_item.boundingRect().adjusted(-100, -100, 100, 100))

        self.hud = QLabel(
            "ESC / RMB - Close\n"
            "R - Reset zoom/pan\n"
            "C - Copy image\n"
            "P - Copy pixel data\n"
            "B - Cycle background\n"
            "H - Toggle UI",
            self
        )

        style = """
            QLabel {
                color: white;
                background-color: rgba(0, 0, 0, 120);
                padding: 6px 10px;
                border-radius: 6px;
                font-size: 16px;
            }"""

        self.hud.setStyleSheet(style)

        self.hud.adjustSize()
        self.hud.move(10, 10)
        self.hud.raise_()
        self.hud.show()

        self.pixel_info = QLabel(self)
        self.pixel_info.setStyleSheet(style)

        self.pixel_info.show()
        self.image = pixmap.toImage()

        self.color_preview = QLabel(self)
        self.color_preview.setFixedSize(32, 32)
        self.color_preview.setStyleSheet("border: 1px solid white;")

        self.copy_popup = QLabel(self)
        self.copy_popup.setStyleSheet(style)
        self.copy_popup.hide()

        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        self.resetView()

    def drawBackground(self, painter, rect):
        match self.background_mode:
            case BackgroundMode.BLACK:
                painter.fillRect(rect, Qt.black)
            case BackgroundMode.WHITE:
                painter.fillRect(rect, Qt.white)
            case BackgroundMode.CHECKERED:
                painter.fillRect(rect, self.checker_brush)

    def updateOverlayPositions(self):
        self.pixel_info.move(self.width() - self.pixel_info.width() - 10, 10)
        self.color_preview.move(self.pixel_info.x() - 40, self.pixel_info.y())

    def showPopup(self, text, duration=1500):
        self.copy_popup.setText(text)
        self.copy_popup.adjustSize()

        x = (self.width() - self.copy_popup.width()) // 2
        y = self.height() - self.copy_popup.height() - 30

        self.copy_popup.move(x, y)
        self.copy_popup.show()
        self.copy_popup.raise_()

        QTimer.singleShot(duration, self.copy_popup.hide)

    def toggleUi(self):
        visible = not self.hud.isVisible()

        self.hud.setVisible(visible)
        self.pixel_info.setVisible(visible)
        self.color_preview.setVisible(visible)

    def getColorData(self, scene_pos):

        x = int(scene_pos.x())
        y = int(scene_pos.y())

        if 0 <= x < self.image.width() and 0 <= y < self.image.height():

            color = self.image.pixelColor(x, y)

            r, g, b, a = color.getRgb()

            hex_rgba = "#{:02X}{:02X}{:02X}{:02X}".format(r, g, b, a)
            h, s, v, _ = color.getHsv()
            #h, s, l, _ = color.getHsl()
            lum = int(0.2126 * r + 0.7152 * g + 0.0722 * b)

            return (r, g, b, a), (
                f"X: {x}  Y: {y}\n"
                f"RGBA: {r}, {g}, {b}, {a}\n"
                f"HEX: {hex_rgba}\n"
                f"HSV: {h}°, {s/255:.1%}, {v/255:.1%}\n"
                #f"HSL: {h}°, {s/255*100:.1f}%, {l/255*100:.1f}%\n"
                f"Lum: {lum} ({lum/255*100:.1f}%)"
            )
        return (0, 0, 0, 0), ""

    def copyData(self):
        rgba, text = self.getColorData(self.mapToScene(self.mapFromGlobal(QCursor.pos())))
        QGuiApplication.clipboard().setText(text)
        logger.info("Copied pixel data to clipboard: %s", rgba)
        self.showPopup("Info Copied!")

    def copyImage(self):
        QGuiApplication.clipboard().setPixmap(self.pixmap_item.pixmap())
        logger.info("Copied image to clipboard!")
        self.showPopup("Image Copied!")

    def resetView(self):
        self.resetTransform()
        self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
        self.zoom_factor = self.transform().m11()
        self.auto_fit = True

    def wheelEvent(self, event):
        self.auto_fit = False
        if event.angleDelta().y() == 0:
            return

        factor = self.zoom_step if event.angleDelta().y() > 0 else 1 / self.zoom_step

        new_zoom = self.zoom_factor * factor
        if not self.min_zoom <= new_zoom <= self.max_zoom:
            return

        self.zoom_factor = new_zoom
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.close()
            return

        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        match event.key():
            case Qt.Key_Escape:
                self.close()
            case Qt.Key_R:
                self.resetView()
            case Qt.Key_C:
                self.copyImage()
            case Qt.Key_P:
                self.copyData()
            case Qt.Key_H:
                self.toggleUi()
            case Qt.Key_B:
                self.background_mode = BackgroundMode((self.background_mode + 1) % len(BackgroundMode))
                self.viewport().update()
                self.showPopup(self.background_mode.name.title())
            case _:
                super().keyPressEvent(event)
        
    def mouseMoveEvent(self, event):
        rgba, text = self.getColorData(self.mapToScene(event.pos()))
        self.pixel_info.setText(text)
        r, g, b, a = rgba
        pix = QPixmap(32, 32)
        pix.fill(QColor(r, g, b, a))
        self.color_preview.setPixmap(pix)
        self.updateOverlayPositions()
        self.pixel_info.adjustSize()

        super().mouseMoveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if self.auto_fit:
            self.resetTransform()
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
            self.zoom_factor = self.transform().m11()

        self.pixel_info.move(self.width() - self.pixel_info.width() - 10, 10)
        self.color_preview.move(self.pixel_info.x() - 40, self.pixel_info.y())

class TextureListWidget(QListWidget):
    def __init__(self, parent=None, mode: ImageType = ImageType.Atlas, check_game: Optional[Callable] = None):
        super().__init__(parent)
        self.checkGame = check_game

        self.add_button = QPushButton("+", self)
        self.add_button.setFixedSize(28, 28)
        self.add_button.setStyleSheet("""
        QPushButton {
            background-color: #2D2D2D;
            font-size: 17px;
            font-weight: bold;
            padding-bottom: 4px;
        }""")
        
        if mode == ImageType.Subtexture:
            self.menu = QMenu()
            self.def_option = QAction("Define", self)
            self.add_option = QAction("Append", self)
            self.add_button.clicked.connect(self.showMenu)

        self.repositionButton()

    def keyPressEvent(self, event):
        super().keyPressEvent(event)

        if event.key() in (Qt.Key_Up, Qt.Key_Down):
            item = self.currentItem()
            if item:
                self.itemActivated.emit(item)

    def showMenu(self):
        game = self.checkGame() # checkGame will never be None as showMenu is only used by subtexture_list
        if game.type != GameType.MODERN:
            self.add_option.trigger() # PS gametype will return append as well which skips having to select an option before it tells you that you cant
            return

        self.menu.clear()
        self.menu.addAction(self.def_option)
        self.menu.addAction(self.add_option)

        self.menu.exec(self.add_button.mapToGlobal(QPoint(0, -self.menu.sizeHint().height())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.repositionButton()

    def repositionButton(self, margin=10):
        self.add_button.move(self.width() - self.add_button.width() - margin, self.height() - self.add_button.height() - margin)


def showError(text, title="Error", _type=QMessageBox.Critical):
    """Error popup with specified text"""
    msg = QMessageBox()
    msg.setIcon(_type)
    msg.setWindowTitle(title)
    msg.setTextFormat(Qt.RichText)

    if _type == QMessageBox.Critical:
        msg.setText(f"""
            <b>An unexpected error occurred.</b><br><br>
            <pre>{text}</pre>
            """)
    else:
        msg.setText(text)

    msg.exec()

def showQuery(title, text):
    return QMessageBox.question(None, title, text, QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)

def showSelectOptions(title, text, options):
    choice, ok = QInputDialog.getItem(None, title, text, [str(i) for i in options], 0, False)
    return ok, choice

def gameTypeDialog() -> Game:
    options = [
        "Demon's Souls",
        "Dark Souls 1",
        "Dark Souls 2",
        "Dark Souls 3",
        "Bloodborne",
        "Sekiro",
        "Armored Core 6",
        "Elden Ring",
        "Nightreign"
    ]

    dialog = QDialog(None)
    dialog.setWindowTitle("Select Game Type")
    dialog.setModal(True)

    layout = QVBoxLayout(dialog)

    label = QLabel("Choose one of the following:")
    combo = QComboBox()
    combo.setStyleSheet("""QComboBox {padding: 3px 0px 3px 6px;}""")
    combo.addItems(options)

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )

    layout.addWidget(label)
    layout.addWidget(combo)
    layout.addWidget(buttons)

    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)

    result = dialog.exec()

    if result == QDialog.Accepted:
        return Game(combo.currentText())

    return Game(None)

def getOutputPath() -> Path:
    folder = QFileDialog.getExistingDirectory(
        None,
        "Select Output Folder"
    )
    return Path(folder) if folder else None

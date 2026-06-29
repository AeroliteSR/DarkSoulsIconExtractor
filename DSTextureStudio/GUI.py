from PySide6.QtWidgets import (QWidget, QVBoxLayout, QCheckBox, QDialog, QLabel, QPushButton, QMessageBox, QLineEdit, QComboBox, QDialogButtonBox,
QStyledItemDelegate, QGraphicsView, QGraphicsScene, QListWidget, QInputDialog, QSpinBox, QHBoxLayout, QMenu, QListWidgetItem, QFileDialog, QFormLayout)
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QRect, QPoint
from PySide6.QtGui import QPalette, QPainter, QAction
from .GameInfo import Types
from .Enums import Game, ImageType
import re
from pathlib import Path

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
        color: #FFFFFF;
        padding: 3px 0px 3px 0px; /* top right bottom left */
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

class SearchWindow(QWidget):
    results = Signal(str, bool) # text, atlas search mode

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Search")
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Search text:"))
        self.search_input = QLineEdit()

        self.atlas_search = QCheckBox("Search Atlases")

        flags_layout = QVBoxLayout()
        flags_layout.addWidget(self.atlas_search)

        self.search_button = QPushButton("Search")
        layout.addWidget(self.search_input)
        layout.addLayout(flags_layout)
        layout.addWidget(self.search_button)

        self.setLayout(layout)
        self.search_button.clicked.connect(self.emit_search)

    def emit_search(self):
        text = self.search_input.text()
        self.results.emit(text, self.atlas_search.isChecked())

class TextureNamePrompt(QDialog):
    def __init__(self, mode: ImageType = ImageType.Subtexture, resizeprompt=True, padprompt=True, halfprompt=True):
        super().__init__()
        self.mode = mode
        self.halfprompt = halfprompt
        self.padprompt = padprompt
        self.resizeprompt = resizeprompt
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
            self.prefix_input.addItems(Types.SubtexturePrefix)
            self.prefix_input.setEditable(True)
            self.layout.addWidget(self.prefix_input)

            self.layout.addWidget(QLabel("Icon ID:"))
            self.id_input = QLineEdit()
            self.layout.addWidget(self.id_input)

            if self.padprompt:
                self.padding_label = QLabel("Padding:")
                self.padding_input = QSpinBox()
                self.padding_input.setRange(1, 512)
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

            self.layout.addWidget(QLabel("Format:"))
            self.format_input = QComboBox()
            self.format_input.addItems(Types.DDSFormats.keys())
            self.format_input.setEditable(True)
            self.layout.addWidget(self.format_input)

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
            if self.halfprompt:
                half = self.half_checkbox.isChecked()
            else:
                half = False

            if self.resizeprompt and self.resize_checkbox.isChecked():
                resize = (self.r_width_input.value(), self.r_height_input.value())
            else:
                resize = None

            id = self.id_input.text()
            if not id.isdigit() or not 0 <= int(id) < 65536:
                showError("Inputted ID is not an asserted UInt16.\nThis may silently throw errors in Smithbox or elsewhere.\nRename this icon if that wasn't your intention.", "Warning", QMessageBox.Warning)
            
            if self.padprompt:
                return f"{self.prefix_input.currentText()}_{id}", self.padding_input.value(), resize, half
            else:
                return f"{self.prefix_input.currentText()}_{id}", resize, half
        
        else:
            coords = (self.b_width_input.value(), self.b_height_input.value()) if self.blank_checkbox.isChecked() else None
            return self.name_input.text(), self.format_input.currentText(), coords
        
class DefineSubtexturePrompt(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Prompt")

        self.layout = QVBoxLayout()

        self.layout.addWidget(QLabel("Prefix:"))
        self.prefix_input = QComboBox()
        self.prefix_input.addItems(Types.SubtexturePrefix)
        self.prefix_input.setEditable(True)
        self.layout.addWidget(self.prefix_input)

        self.layout.addWidget(QLabel("Icon ID:"))
        self.id_input = QLineEdit()
        self.layout.addWidget(self.id_input)
        
        size_layout = QHBoxLayout()

        size_layout.addWidget(QLabel("Width:"))
        self.width_input = QSpinBox()
        self.width_input.setRange(1, 8192)
        self.width_input.setValue(128)
        size_layout.addWidget(self.width_input)

        size_layout.addSpacing(10)

        size_layout.addWidget(QLabel("Height:"))
        self.height_input = QSpinBox()
        self.height_input.setRange(1, 8192)
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
            showError("Inputted ID is not an asserted UInt16.\nThis may silently throw errors in Smithbox or elsewhere.\nRename this icon if that wasn't your intention.", "Warning", QMessageBox.Warning)
        
        hwcoords = (self.width_input.value(), self.height_input.value())
        xycoords = (self.x_input.value(), self.y_input.value())
        return f"{self.prefix_input.currentText()}_{id}", hwcoords, xycoords, half

class ImageLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(parent, text=text)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.openView()

    def openView(self):
        if self.pixmap():
            self.viewer = ImageViewer(self.pixmap())
            self.viewer.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
            self.viewer.showFullScreen()

class ImageViewer(QGraphicsView):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)

        self.setScene(QGraphicsScene(self))
        self.pixmap_item = self.scene().addPixmap(pixmap)
        self.setRenderHints(self.renderHints() |
                            QPainter.Antialiasing |
                            QPainter.SmoothPixmapTransform)

        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setStyleSheet("background-color: black; border: none;")
        self.zoom_level = 0

        self.scene().setSceneRect(self.pixmap_item.boundingRect().adjusted(-100, -100, 100, 100))

        self.hud = QLabel("ESC / RMB to close\nR to reset", self)
        self.hud.setStyleSheet("""
            QLabel {
                color: white;
                background-color: rgba(0, 0, 0, 120);
                padding: 6px 10px;
                border-radius: 6px;
                font-size: 16px;
            }""")

        self.hud.adjustSize()
        self.hud.move(10, 10)
        self.hud.raise_()
        self.hud.show()

        self.pixel_info = QLabel(self)
        self.pixel_info.setStyleSheet("""
            QLabel {
                color: white;
                background-color: rgba(0, 0, 0, 120);
                padding: 6px 10px;
                border-radius: 6px;
                font-size: 16px;
            }""")

        self.pixel_info.show()
        self.image = pixmap.toImage()

        self.color_preview = QLabel(self)
        self.color_preview.setFixedSize(32, 32)
        self.color_preview.setStyleSheet("border: 1px solid white;")

        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def resetView(self):
        self.resetTransform()
        self.centerOn(self.pixmap_item)
        self.zoom_level = 0

    def wheelEvent(self, event):
        zoom_in = 1.25
        zoom_out = 0.8

        if event.angleDelta().y() > 0:
            factor = zoom_in
            self.zoom_level += 1
        else:
            factor = zoom_out
            self.zoom_level -= 1

        if self.zoom_level < -10:
            self.zoom_level = -10
            return
        if self.zoom_level > 30:
            self.zoom_level = 30
            return

        self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.close()
            return

        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        
        if event.key() == Qt.Key_R:
            self.resetView()
            return
        
    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.pos())

        x = int(scene_pos.x())
        y = int(scene_pos.y())

        if 0 <= x < self.image.width() and 0 <= y < self.image.height():

            color = self.image.pixelColor(x, y)

            r = color.red()
            g = color.green()
            b = color.blue()
            a = color.alpha()

            hex_rgba = "#{:02X}{:02X}{:02X}{:02X}".format(r, g, b, a)
            hsv = color.getHsv()
            #h, s, l, _ = color.getHsl()
            lum = int(0.2126 * r + 0.7152 * g + 0.0722 * b)

            self.pixel_info.setText(
                f"X: {x}  Y: {y}\n"
                f"RGBA: {r}, {g}, {b}, {a}\n"
                f"HEX: {hex_rgba}\n"
                f"HSV: {hsv[0]}, {hsv[1]}, {hsv[2]}\n"
                #f"HSL: {h}°, {s/255*100:.1f}%, {l/255*100:.1f}%\n"
                f"Lum: {lum} ({lum/255*100:.1f}%)"
            )
            self.color_preview.setStyleSheet(f"background-color: rgba({r},{g},{b},{a});border: 1px solid white;")
            self.color_preview.move(self.pixel_info.x() - 40, self.pixel_info.y())

            self.pixel_info.adjustSize()
            self.pixel_info.move(self.width() - self.pixel_info.width() - 10, 10)

        super().mouseMoveEvent(event)

class TextureListWidget(QListWidget):
    def __init__(self, parent=None, mode: ImageType = ImageType.Atlas):
        super().__init__(parent)

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
            self.menu.addAction(self.def_option)
            self.menu.addAction(self.add_option)

            self.add_button.clicked.connect(self.showMenu)

        self.repositionButton()

    def keyPressEvent(self, event):
        super().keyPressEvent(event)

        if event.key() in (Qt.Key_Up, Qt.Key_Down):
            item = self.currentItem()
            if item:
                self.itemActivated.emit(item)

    def showMenu(self):
        pos = self.add_button.mapToGlobal(QPoint(0, -self.menu.sizeHint().height()))
        self.menu.popup(pos)

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

import json
import os
import sys

from PyQt6 import QtCore, QtGui, QtWidgets

QT6 = True


def qt_align_center():
    return QtCore.Qt.AlignmentFlag.AlignCenter if QT6 else QtCore.Qt.AlignCenter


def qt_keep_aspect():
    return (
        QtCore.Qt.AspectRatioMode.KeepAspectRatio
        if QT6
        else QtCore.Qt.KeepAspectRatio
    )


def qt_smooth():
    return (
        QtCore.Qt.TransformationMode.SmoothTransformation
        if QT6
        else QtCore.Qt.SmoothTransformation
    )


def qt_frame_styled_panel():
    return (
        QtWidgets.QFrame.Shape.StyledPanel
        if QT6
        else QtWidgets.QFrame.StyledPanel
    )


def qt_cursor_pointing():
    return (
        QtCore.Qt.CursorShape.PointingHandCursor
        if QT6
        else QtCore.Qt.PointingHandCursor
    )


def qt_cursor_arrow():
    return (
        QtCore.Qt.CursorShape.ArrowCursor if QT6 else QtCore.Qt.ArrowCursor
    )


def qt_mouse_left():
    return (
        QtCore.Qt.MouseButton.LeftButton if QT6 else QtCore.Qt.LeftButton
    )


def qt_focus_strong():
    return (
        QtCore.Qt.FocusPolicy.StrongFocus if QT6 else QtCore.Qt.StrongFocus
    )


def qt_graphics_drag_hand():
    return (
        QtWidgets.QGraphicsView.DragMode.ScrollHandDrag
        if QT6
        else QtWidgets.QGraphicsView.ScrollHandDrag
    )


def qt_anchor_under_mouse():
    return (
        QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
        if QT6
        else QtWidgets.QGraphicsView.AnchorUnderMouse
    )


def qt_painter_smooth():
    return (
        QtGui.QPainter.RenderHint.SmoothPixmapTransform
        if QT6
        else QtGui.QPainter.SmoothPixmapTransform
    )


IMAGE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".avif",
}


def is_image_file(name):
    return os.path.splitext(name)[1].lower() in IMAGE_EXTS


def parse_fav_yaml(path):
    sections = []
    section_index = {}
    current_date = None
    if not os.path.exists(path):
        return sections

    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if not line.startswith("-") and line.endswith(":"):
                date = line[:-1].strip()
                if not date:
                    current_date = None
                    continue
                current_date = date
                if date not in section_index:
                    entry = {"date": date, "numbers": []}
                    section_index[date] = entry
                    sections.append(entry)
                continue
            if not line.startswith("-") or not current_date:
                continue
            value = line[1:].strip()
            if not value:
                continue
            entry = section_index.get(current_date)
            if entry and value not in entry["numbers"]:
                entry["numbers"].append(value)
    return sections


def find_file_for_number(base_dir, date, number):
    folder = os.path.join(base_dir, date)
    if not os.path.isdir(folder):
        return None
    try:
        entries = os.listdir(folder)
    except OSError:
        return None
    files = [name for name in entries if os.path.isfile(os.path.join(folder, name))]
    for name in files:
        if number in name and is_image_file(name):
            return os.path.join(folder, name)
    for name in files:
        if number in name:
            return os.path.join(folder, name)
    return None


def find_json_candidate(text, start_index):
    depth = 0
    in_string = False
    escape = False
    for idx in range(start_index, len(text)):
        char = text[idx]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start_index : idx + 1]
    return None


def extract_json_from_bytes(data, max_scan=5 * 1024 * 1024):
    view = data[:max_scan]
    text = view.decode("utf-8", errors="ignore")
    search_index = 0
    while True:
        start = text.find("{", search_index)
        if start == -1:
            return None
        candidate = find_json_candidate(text, start)
        if not candidate:
            search_index = start + 1
            continue
        try:
            parsed = json.loads(candidate)
            return json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            search_index = start + 1


class ImageView(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._zoom = 1.0
        scene = QtWidgets.QGraphicsScene(self)
        self.setScene(scene)
        self._pixmap_item = QtWidgets.QGraphicsPixmapItem()
        scene.addItem(self._pixmap_item)
        self.setBackgroundBrush(QtGui.QColor(18, 18, 18))
        self.setRenderHint(qt_painter_smooth())
        self.setDragMode(qt_graphics_drag_hand())
        self.setTransformationAnchor(qt_anchor_under_mouse())
        self.setResizeAnchor(qt_anchor_under_mouse())

    def set_pixmap(self, pixmap):
        self._pixmap_item.setPixmap(pixmap)
        self.scene().setSceneRect(QtCore.QRectF(pixmap.rect()))
        self.set_zoom(1.0)

    def set_zoom(self, value):
        self._zoom = max(0.2, min(8.0, value))
        self.resetTransform()
        self.scale(self._zoom, self._zoom)

    def adjust_zoom(self, delta):
        self.set_zoom(self._zoom + delta)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        factor = 1.25 if delta > 0 else 0.8
        new_zoom = self._zoom * factor
        if 0.2 <= new_zoom <= 8.0:
            self._zoom = new_zoom
            self.scale(factor, factor)
        event.accept()


class ImageDialog(QtWidgets.QDialog):
    def __init__(self, path, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preview")
        self.resize(1000, 700)
        self.path = path
        self.original_pixmap = QtGui.QPixmap(path) if path else QtGui.QPixmap()

        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        layout.addLayout(header)

        text_wrap = QtWidgets.QVBoxLayout()
        header.addLayout(text_wrap)
        header.addStretch()

        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("font-weight: 600; font-size: 16px;")
        self.path_label = QtWidgets.QLabel(path or "")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #9aa0a6;")
        text_wrap.addWidget(title_label)
        text_wrap.addWidget(self.path_label)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)

        body = QtWidgets.QHBoxLayout()
        layout.addLayout(body, 1)

        self.image_view = ImageView()
        self.image_view.setMinimumHeight(320)
        body.addWidget(self.image_view, 3)

        meta_container = QtWidgets.QWidget()
        meta_layout = QtWidgets.QVBoxLayout(meta_container)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(6)

        meta_label = QtWidgets.QLabel("Metadata JSON")
        meta_label.setStyleSheet("font-weight: 600; color: #cfcfcf;")
        meta_layout.addWidget(meta_label)

        self.meta_view = QtWidgets.QTextEdit()
        self.meta_view.setReadOnly(True)
        self.meta_view.setFontFamily("Consolas")
        self.meta_view.setStyleSheet(
            "background: #101114; color: #f0f0f0; border: 1px solid #2b2e35;"
        )
        self.meta_view.setMinimumWidth(320)
        self.meta_view.setPlainText("Loading metadata...")
        meta_layout.addWidget(self.meta_view, 1)

        body.addWidget(meta_container, 2)

        footer = QtWidgets.QHBoxLayout()
        layout.addLayout(footer)
        footer.addStretch()

        zoom_out = QtWidgets.QPushButton("-")
        zoom_out.clicked.connect(lambda: self.image_view.adjust_zoom(-0.2))
        zoom_reset = QtWidgets.QPushButton("Reset")
        zoom_reset.clicked.connect(lambda: self.image_view.set_zoom(1.0))
        zoom_in = QtWidgets.QPushButton("+")
        zoom_in.clicked.connect(lambda: self.image_view.adjust_zoom(0.2))
        footer.addWidget(zoom_out)
        footer.addWidget(zoom_reset)
        footer.addWidget(zoom_in)

        self.load_preview()
        self.load_metadata()

    def load_preview(self):
        if self.original_pixmap.isNull():
            self.image_view.set_pixmap(QtGui.QPixmap())
            return
        self.image_view.set_pixmap(self.original_pixmap)

    def load_metadata(self):
        if not self.path or not os.path.exists(self.path):
            self.meta_view.setPlainText("Unable to load metadata for this file.")
            return
        try:
            with open(self.path, "rb") as handle:
                data = handle.read(5 * 1024 * 1024)
            json_text = extract_json_from_bytes(data)
            if json_text:
                self.meta_view.setPlainText(json_text)
            else:
                self.meta_view.setPlainText("No JSON metadata found.")
        except OSError:
            self.meta_view.setPlainText("Unable to load metadata for this file.")


class ImageCard(QtWidgets.QFrame):
    def __init__(self, date, number, path, parent=None):
        super().__init__(parent)
        self.date = date
        self.number = number
        self.path = path
        self.setFrameShape(qt_frame_styled_panel())
        self.setStyleSheet(
            "QFrame { background: #1c1e22; border: 1px solid #2c2f36; border-radius: 10px; }"
        )
        self.setCursor(QtGui.QCursor(qt_cursor_pointing()))

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.thumb = QtWidgets.QLabel("Searching for matching file...")
        self.thumb.setAlignment(qt_align_center())
        self.thumb.setStyleSheet("background: #25282e; color: #9aa0a6;")
        self.thumb.setFixedHeight(160)
        layout.addWidget(self.thumb)

        num_label = QtWidgets.QLabel(f"#{number}")
        num_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(num_label)

        self.file_label = QtWidgets.QLabel("Scanning folder...")
        self.file_label.setStyleSheet("color: #9aa0a6;")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        self.setFocusPolicy(qt_focus_strong())

        self.apply_path(path)

    def apply_path(self, path):
        self.path = path
        if not path:
            self.thumb.setText("No matching file found.")
            self.file_label.setText("Missing preview.")
            self.setCursor(QtGui.QCursor(qt_cursor_arrow()))
            return
        filename = os.path.basename(path)
        self.file_label.setText(filename)
        pixmap = QtGui.QPixmap(path)
        if pixmap.isNull():
            self.thumb.setText("Preview unavailable.")
            return
        scaled = pixmap.scaled(
            self.thumb.width(), self.thumb.height(), qt_keep_aspect(), qt_smooth()
        )
        self.thumb.setPixmap(scaled)

    def mousePressEvent(self, event):
        if event.button() == qt_mouse_left() and self.path:
            dialog = ImageDialog(
                self.path, f"{self.date} / {self.number}", parent=self
            )
            dialog.exec()
        super().mousePressEvent(event)


class FavoritesViewer(QtWidgets.QMainWindow):
    def __init__(self, base_dir):
        super().__init__()
        self.base_dir = base_dir
        self.setWindowTitle("ComfyUI Favorites Viewer")
        self.resize(1200, 800)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        outer.addLayout(header)

        title = QtWidgets.QLabel("Favorites Viewer")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        reload_btn = QtWidgets.QPushButton("Reload")
        reload_btn.clicked.connect(self.load_sections)
        header.addWidget(reload_btn)

        self.status = QtWidgets.QLabel("Ready.")
        self.status.setStyleSheet("color: #9aa0a6;")
        outer.addWidget(self.status)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        outer.addWidget(self.scroll, 1)

        self.scroll_widget = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setSpacing(18)
        self.scroll_layout.addStretch()
        self.scroll.setWidget(self.scroll_widget)

        self.load_sections()

    def clear_sections(self):
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def load_sections(self):
        self.status.setText("Loading favorites...")
        self.clear_sections()
        fav_path = os.path.join(self.base_dir, "fav.yaml")
        sections = parse_fav_yaml(fav_path)
        if not sections:
            self.status.setText("No dates found in fav.yaml.")
            return

        viewport_width = self.scroll.viewport().width()
        columns = max(1, viewport_width // 260) if viewport_width else 4

        for section in sections:
            if not section["numbers"]:
                continue
            date = section["date"]
            numbers = section["numbers"]

            container = QtWidgets.QFrame()
            container.setStyleSheet(
                "QFrame { background: #191b1f; border: 1px solid #2a2d33; border-radius: 12px; }"
            )
            container_layout = QtWidgets.QVBoxLayout(container)
            container_layout.setContentsMargins(14, 14, 14, 14)

            header = QtWidgets.QHBoxLayout()
            date_label = QtWidgets.QLabel(date)
            date_label.setStyleSheet("font-weight: 600; font-size: 16px;")
            count_label = QtWidgets.QLabel(f"{len(numbers)} favorites")
            count_label.setStyleSheet("color: #9aa0a6;")
            header.addWidget(date_label)
            header.addStretch()
            header.addWidget(count_label)
            container_layout.addLayout(header)

            grid = QtWidgets.QGridLayout()
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(12)
            container_layout.addLayout(grid)

            for index, number in enumerate(numbers):
                path = find_file_for_number(self.base_dir, date, number)
                card = ImageCard(date, number, path)
                row = index // columns
                col = index % columns
                grid.addWidget(card, row, col)

            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, container)

        self.status.setText("Loaded favorites.")


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(
        """
        QMainWindow, QWidget {
            background-color: #141417;
            color: #e6e6e6;
        }
        QLabel {
            color: #e6e6e6;
        }
        QScrollArea {
            background-color: transparent;
        }
        QScrollArea > QWidget > QWidget {
            background-color: transparent;
        }
        QPushButton {
            background-color: #2a2d33;
            color: #e6e6e6;
            border: 1px solid #3a3d44;
            border-radius: 6px;
            padding: 6px 12px;
        }
        QPushButton:hover {
            background-color: #343842;
        }
        QTextEdit {
            background-color: #101114;
            color: #e6e6e6;
            border: 1px solid #2b2e35;
            border-radius: 6px;
        }
        """
    )
    base_dir = os.path.abspath(os.path.dirname(__file__))
    viewer = FavoritesViewer(base_dir)
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

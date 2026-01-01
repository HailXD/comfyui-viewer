import json
import os
import sqlite3
import sys
import zlib

from PyQt6 import QtCore, QtGui, QtWidgets

QT6 = True

ZOOM_MIN = 0.05
ZOOM_MAX = 8.0


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

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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


def open_cache(base_dir):
    cache_dir = os.path.join(base_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "db.sqlite")
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_cache (
            date TEXT NOT NULL,
            number TEXT NOT NULL,
            path TEXT NOT NULL,
            metadata_json TEXT,
            ckpt_name TEXT,
            sampler_name1 TEXT,
            sampler_name2 TEXT,
            PRIMARY KEY (date, number)
        )
        """
    )
    return conn


def get_cached_path(conn, date, number):
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT path FROM file_cache WHERE date = ? AND number = ?",
            (date, number),
        ).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    path = row[0]
    if path and os.path.exists(path):
        return path
    if path:
        try:
            conn.execute(
                "DELETE FROM file_cache WHERE date = ? AND number = ?",
                (date, number),
            )
            conn.commit()
        except sqlite3.Error:
            return None
    return None


def get_cached_metadata(conn, path):
    if conn is None or not path:
        return None
    if not os.path.exists(path):
        try:
            conn.execute("DELETE FROM file_cache WHERE path = ?", (path,))
            conn.commit()
        except sqlite3.Error:
            return None
        return None
    try:
        row = conn.execute(
            """
            SELECT metadata_json, ckpt_name, sampler_name1, sampler_name2
            FROM file_cache
            WHERE path = ?
            """,
            (path,),
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    metadata_json, ckpt_name, sampler1, sampler2 = row
    if (
        metadata_json is None
        and ckpt_name is None
        and sampler1 is None
        and sampler2 is None
    ):
        return None
    samplers = [value for value in (sampler1, sampler2) if value]
    return {
        "metadata_json": metadata_json,
        "ckpt_name": ckpt_name,
        "samplers": samplers,
    }


def update_cache(conn, date, number, path):
    if conn is None or not path:
        return
    try:
        row = conn.execute(
            "SELECT path FROM file_cache WHERE date = ? AND number = ?",
            (date, number),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO file_cache (date, number, path) VALUES (?, ?, ?)",
                (date, number, path),
            )
        elif row[0] != path:
            conn.execute(
                """
                UPDATE file_cache
                SET path = ?, metadata_json = NULL, ckpt_name = NULL,
                    sampler_name1 = NULL, sampler_name2 = NULL
                WHERE date = ? AND number = ?
                """,
                (path, date, number),
            )
        conn.commit()
    except sqlite3.Error:
        return


def update_metadata_cache(conn, path, metadata_json, ckpt_name, sampler_names):
    if conn is None or not path:
        return
    sampler1 = sampler_names[0] if len(sampler_names) > 0 else None
    sampler2 = sampler_names[1] if len(sampler_names) > 1 else None
    try:
        conn.execute(
            """
            UPDATE file_cache
            SET metadata_json = ?, ckpt_name = ?, sampler_name1 = ?, sampler_name2 = ?
            WHERE path = ?
            """,
            (metadata_json, ckpt_name, sampler1, sampler2, path),
        )
        conn.commit()
    except sqlite3.Error:
        return


def find_file_for_number(base_dir, date, number, cache_conn=None):
    cached = get_cached_path(cache_conn, date, number)
    if cached:
        return cached
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
            path = os.path.join(folder, name)
            update_cache(cache_conn, date, number, path)
            return path
    for name in files:
        if number in name:
            path = os.path.join(folder, name)
            update_cache(cache_conn, date, number, path)
            return path
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


def extract_json_from_text(text):
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


def extract_json_from_bytes(data, max_scan=5 * 1024 * 1024):
    view = data[:max_scan]
    text = view.decode("utf-8", errors="ignore")
    return extract_json_from_text(text)


def _collect_values(obj, key, max_count, results):
    if len(results) >= max_count:
        return
    if isinstance(obj, dict):
        for obj_key, value in obj.items():
            if obj_key == key and not isinstance(value, (dict, list)):
                results.append(str(value))
                if len(results) >= max_count:
                    return
            _collect_values(value, key, max_count, results)
    elif isinstance(obj, list):
        for value in obj:
            _collect_values(value, key, max_count, results)


def extract_metadata_fields(json_text):
    if not json_text:
        return None, []
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        return None, []
    ckpt_values = []
    sampler_values = []
    _collect_values(parsed, "ckpt_name", 1, ckpt_values)
    _collect_values(parsed, "sampler_name", 2, sampler_values)
    ckpt_name = ckpt_values[0] if ckpt_values else None
    return ckpt_name, sampler_values


def extract_text_from_png_chunk(chunk_type, data):
    try:
        if chunk_type == b"tEXt":
            _, text = data.split(b"\x00", 1)
            return text.decode("latin-1", errors="ignore")
        if chunk_type == b"zTXt":
            _, rest = data.split(b"\x00", 1)
            if not rest:
                return None
            if rest[0] != 0:
                return None
            try:
                text = zlib.decompress(rest[1:])
            except zlib.error:
                return None
            return text.decode("latin-1", errors="ignore")
        if chunk_type == b"iTXt":
            _, rest = data.split(b"\x00", 1)
            if len(rest) < 2:
                return None
            compressed = rest[0]
            if compressed not in (0, 1):
                return None
            if rest[1] != 0 and compressed == 1:
                return None
            rest = rest[2:]
            parts = rest.split(b"\x00", 2)
            if len(parts) != 3:
                return None
            _, _, text = parts
            if compressed == 1:
                try:
                    text = zlib.decompress(text)
                except zlib.error:
                    return None
            return text.decode("utf-8", errors="ignore")
    except ValueError:
        return None
    return None


def extract_json_from_png(path):
    try:
        with open(path, "rb") as handle:
            if handle.read(8) != PNG_SIGNATURE:
                return None
            while True:
                header = handle.read(8)
                if len(header) < 8:
                    return None
                length = int.from_bytes(header[:4], "big")
                chunk_type = header[4:8]
                if length < 0:
                    return None
                if chunk_type in (b"tEXt", b"zTXt", b"iTXt"):
                    data = handle.read(length)
                    handle.read(4)
                    text = extract_text_from_png_chunk(chunk_type, data)
                    if text:
                        json_text = extract_json_from_text(text)
                        if json_text:
                            return json_text
                else:
                    handle.seek(length + 4, os.SEEK_CUR)
                if chunk_type == b"IEND":
                    return None
    except OSError:
        return None


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
        self._zoom = 1.0
        self.resetTransform()

    def set_zoom(self, value):
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, value))
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
        if ZOOM_MIN <= new_zoom <= ZOOM_MAX:
            self._zoom = new_zoom
            self.scale(factor, factor)
        event.accept()

    def fit_to_view(self):
        pixmap = self._pixmap_item.pixmap()
        if pixmap.isNull():
            return
        view_rect = self.viewport().rect()
        pixmap_rect = self._pixmap_item.boundingRect()
        if (
            view_rect.width() <= 0
            or view_rect.height() <= 0
            or pixmap_rect.width() <= 0
            or pixmap_rect.height() <= 0
        ):
            return
        scale = min(
            view_rect.width() / pixmap_rect.width(),
            view_rect.height() / pixmap_rect.height(),
            1.0,
        )
        self._zoom = scale
        self.resetTransform()
        self.scale(scale, scale)


class ImageDialog(QtWidgets.QDialog):
    def __init__(self, path, title, cache_conn=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preview")
        self.resize(1000, 700)
        self.path = path
        self.cache_conn = cache_conn
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

        meta_label = QtWidgets.QLabel("Metadata")
        meta_label.setStyleSheet("font-weight: 600; color: #cfcfcf;")
        meta_layout.addWidget(meta_label)

        self.ckpt_label = QtWidgets.QLabel("ckpt_name: -")
        self.ckpt_label.setStyleSheet("color: #9aa0a6;")
        self.ckpt_label.setWordWrap(True)
        meta_layout.addWidget(self.ckpt_label)

        self.sampler_label = QtWidgets.QLabel("sampler_name: -")
        self.sampler_label.setStyleSheet("color: #9aa0a6;")
        self.sampler_label.setWordWrap(True)
        meta_layout.addWidget(self.sampler_label)

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
        QtCore.QTimer.singleShot(0, self.image_view.fit_to_view)

    def load_metadata(self):
        if not self.path or not os.path.exists(self.path):
            self.ckpt_label.setText("ckpt_name: -")
            self.sampler_label.setText("sampler_name: -")
            self.meta_view.setPlainText("Unable to load metadata for this file.")
            return
        try:
            ext = os.path.splitext(self.path)[1].lower()
            cached = get_cached_metadata(self.cache_conn, self.path)
            if cached is not None:
                json_text = cached["metadata_json"]
                ckpt_name = cached["ckpt_name"]
                sampler_names = cached["samplers"]
                if json_text and (ckpt_name is None and not sampler_names):
                    ckpt_name, sampler_names = extract_metadata_fields(json_text)
                    update_metadata_cache(
                        self.cache_conn,
                        self.path,
                        json_text,
                        ckpt_name,
                        sampler_names,
                    )
            else:
                if ext == ".png":
                    json_text = extract_json_from_png(self.path)
                else:
                    with open(self.path, "rb") as handle:
                        data = handle.read(5 * 1024 * 1024)
                    json_text = extract_json_from_bytes(data)
                ckpt_name, sampler_names = extract_metadata_fields(json_text)
                cached_json = json_text if json_text is not None else ""
                update_metadata_cache(
                    self.cache_conn,
                    self.path,
                    cached_json,
                    ckpt_name,
                    sampler_names,
                )
            ckpt_display = ckpt_name or "-"
            sampler_display = ", ".join(sampler_names) if sampler_names else "-"
            self.ckpt_label.setText(f"ckpt_name: {ckpt_display}")
            self.sampler_label.setText(f"sampler_name: {sampler_display}")
            if json_text:
                self.meta_view.setPlainText(json_text)
            else:
                self.meta_view.setPlainText("No JSON metadata found.")
        except OSError:
            self.ckpt_label.setText("ckpt_name: -")
            self.sampler_label.setText("sampler_name: -")
            self.meta_view.setPlainText("Unable to load metadata for this file.")


class ImageCard(QtWidgets.QFrame):
    def __init__(self, date, number, path, cache_conn=None, parent=None):
        super().__init__(parent)
        self.date = date
        self.number = number
        self.path = path
        self.cache_conn = cache_conn
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
                self.path,
                f"{self.date} / {self.number}",
                cache_conn=self.cache_conn,
                parent=self,
            )
            dialog.exec()
        super().mousePressEvent(event)


class FavoritesViewer(QtWidgets.QMainWindow):
    def __init__(self, base_dir):
        super().__init__()
        self.base_dir = base_dir
        self.cache_conn = open_cache(base_dir)
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

        QtCore.QTimer.singleShot(0, self.load_sections)

    def clear_sections(self):
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def closeEvent(self, event):
        if self.cache_conn:
            self.cache_conn.close()
        super().closeEvent(event)

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
                path = find_file_for_number(
                    self.base_dir, date, number, self.cache_conn
                )
                card = ImageCard(date, number, path, cache_conn=self.cache_conn)
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
    viewer.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

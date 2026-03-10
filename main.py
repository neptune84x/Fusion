import sys
import os
import subprocess
import glob
import re

try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                                 QWidget, QLabel, QProgressBar, QScrollArea, 
                                 QFrame, QPushButton, QFileDialog)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtGui import QPainter, QColor, QPen
except ImportError:
    sys.exit(1)

class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)

    def __init__(self, input_file, widget):
        super().__init__()
        self.input_file = input_file
        self.widget = widget

    def run(self):
        # Paket içindeki FFmpeg yolunu bul
        ffmpeg_path = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'
        base_path = os.path.splitext(self.input_file)[0]
        output_file = f"{base_path}_Fusion.mkv"
        
        # Dış altyazıları bul
        subs = glob.glob(f"{base_path}*.*")
        ext_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass'))]

        # FFmpeg Komutunu Oluştur
        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in ext_subs:
            cmd.extend(['-i', sub])

        # Video, ses ve mevcut altyazıları kopyala
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        
        # Dış altyazıları map et ve dil kodunu (.tr.srt -> tr) işle
        for i, sub_path in enumerate(ext_subs):
            cmd.extend(['-map', str(i + 1)])
            match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', sub_path.lower())
            lang = match.group(1) if match else 'und'
            cmd.extend([f'-metadata:s:s:{i}', f'language={lang}'])

        # Chapterları koru, başlık (title) ve tagları sil
        cmd.extend([
            '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt',
            '-map_metadata', '-1', 
            '-map_chapters', '0', 
            '-y', output_file
        ])
        
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
        self.finished_signal.emit(self)

class StripedWidget(QWidget):
    """Subler tipi pijama çizgili arkaplan"""
    def paintEvent(self, event):
        painter = QPainter(self)
        line_height = 30
        painter.setPen(QPen(QColor(235, 235, 235), 1)) # İnce ayırıcı gri çizgi
        for y in range(0, self.height(), line_height):
            painter.drawLine(0, y, self.width(), y)

class FileWidget(QFrame):
    def __init__(self, filename):
        super().__init__()
        self.setFixedHeight(30)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        
        self.status_icon = QLabel("⚪") # Bekliyor
        self.name_label = QLabel(filename)
        self.name_label.setStyleSheet("font-size: 13px; color: #333;")
        self.info_icon = QLabel("ⓘ")
        self.info_icon.setStyleSheet("color: #bbb; font-size: 14px;")

        layout.addWidget(self.status_icon)
        layout.addWidget(self.name_label)
        layout.addStretch()
        layout.addWidget(self.info_icon)

    def set_status(self, mode):
        icons = {"working": "🟠", "done": "✅", "error": "❌"}
        self.status_icon.setText(icons.get(mode, "⚪"))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Queue")
        self.resize(600, 500)
        self.setAcceptDrops(True)
        
        main_w = QWidget()
        self.setCentralWidget(main_w)
        layout = QVBoxLayout(main_w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Toolbar ---
        toolbar = QWidget()
        toolbar.setFixedHeight(95)
        toolbar.setStyleSheet("background: white; border-bottom: 1px solid #d1d1d1;")
        t_layout = QHBoxLayout(toolbar)
        t_layout.setContentsMargins(20, 0, 20, 0)
        t_layout.setSpacing(15)
        
        self.start_btn = self.create_nav_btn("Start", "▶️")
        self.settings_btn = self.create_nav_btn("Settings", "⚙️")
        self.add_btn = self.create_nav_btn("Add Item", "➕")
        
        t_layout.addStretch()
        t_layout.addWidget(self.start_btn)
        t_layout.addWidget(self.settings_btn)
        t_layout.addWidget(self.add_btn)

        self.add_btn.clicked.connect(self.open_files)
        self.start_btn.clicked.connect(self.start_processing)

        # --- List Area ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = StripedWidget()
        self.container.setStyleSheet("background: white;")
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.container)

        # --- Footer ---
        footer = QWidget()
        footer.setFixedHeight(50)
        footer.setStyleSheet("background: #fdfdfd; border-top: 1px solid #d1d1d1;")
        f_layout = QHBoxLayout(footer)
        
        self.status_label = QLabel("0 items in queue.")
        self.status_label.setStyleSheet("font-size: 12px; color: #444;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(180)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)

        f_layout.addWidget(self.status_label)
        f_layout.addStretch()
        f_layout.addWidget(self.progress_bar)

        layout.addWidget(toolbar)
        layout.addWidget(self.scroll)
        layout.addWidget(footer)

        self.queue = []
        self.threads = []
        self.total_tasks = 0

    def create_nav_btn(self, text, icon):
        btn = QPushButton(f"{icon}\n\n{text}")
        btn.setFixedSize(80, 75)
        btn.setStyleSheet("""
            QPushButton { border: none; font-size: 11px; color: #555; background: transparent; }
            QPushButton:hover { color: #000; background: #f5f5f5; border-radius: 10px; }
        """)
        return btn

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Videos", "", "Videos (*.mp4 *.mkv)")
        if files: self.add_to_queue(files)

    def add_to_queue(self, paths):
        for p in paths:
            w = FileWidget(os.path.basename(p))
            self.list_layout.addWidget(w)
            self.queue.append((p, w))
        self.total_tasks = len(self.queue)
        self.status_label.setText(f"{self.total_tasks} items in queue.")

    def start_processing(self):
        if not self.queue: return
        self.start_btn.setEnabled(False)
        self.process_next()

    def process_next(self):
        if not self.queue:
            self.status_label.setText("Completed.")
            self.start_btn.setEnabled(True)
            self.progress_bar.setValue(100)
            return
        
        self.status_label.setText("Working...")
        path, widget = self.queue.pop(0)
        widget.set_status("working")
        
        completed = self.total_tasks - len(self.queue)
        self.progress_bar.setValue(int(((completed - 1) / self.total_tasks) * 100))

        t = ConversionThread(path, widget)
        t.finished_signal.connect(self.on_task_done)
        self.threads.append(t)
        t.start()

    def on_task_done(self, t):
        t.widget.set_status("done")
        if t in self.threads: self.threads.remove(t)
        self.process_next()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]
        self.add_to_queue(files)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("macintosh")
    app.setStyleSheet("QProgressBar::chunk { background-color: #007aff; border-radius: 4px; }")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

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
        ffmpeg_path = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'
        base_path = os.path.splitext(self.input_file)[0]
        output_file = f"{base_path}_Fusion.mkv"
        
        # 1. Mevcut izlerin (track) dil kodlarını korumak ve tagları silmek için komut
        # 2. Dış altyazıları (.tr.srt gibi) tespit etme ve dil kodunu ayıklama
        subs = glob.glob(f"{base_path}*.*")
        ext_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass'))]

        cmd = [ffmpeg_path, '-i', self.input_file]
        
        # Dış altyazıları ekle
        for sub in ext_subs:
            cmd.extend(['-i', sub])

        # Map her şeyi (video, audio, subs)
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        
        # Dış altyazıları maple ve dil kodlarını ata
        for i, sub_path in enumerate(ext_subs):
            cmd.extend(['-map', str(i + 1)])
            # Dosya adından dil kodunu bul (örn: video.tr.srt -> tr)
            match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', sub_path.lower())
            lang = match.group(1) if match else 'und'
            cmd.extend([f'-metadata:s:s:{i}', f'language={lang}'])

        # Global tagları/title'ları sil ama chapterları koru
        cmd.extend([
            '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt',
            '-map_metadata', '-1',             # Tüm global tagları/titleları siler
            '-map_chapters', '0',               # Chapterları korur
            '-movflags', 'use_metadata_tags',   # Bazı container taglarını temiz tutar
            '-y', output_file
        ])
        
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
        self.finished_signal.emit(self)

class StripedWidget(QWidget):
    """Subler tipi 'pijamalı' (zebra çizgili değil, ince gri çizgili) arkaplan"""
    def paintEvent(self, event):
        painter = QPainter(self)
        line_height = 30 # Subler'a uygun satır yüksekliği
        painter.setPen(QPen(QColor(235, 235, 235), 1)) # Çok ince gri çizgi
        for y in range(0, self.height(), line_height):
            painter.drawLine(0, y, self.width(), y)

class FileWidget(QFrame):
    def __init__(self, filename):
        super().__init__()
        self.setFixedHeight(30)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        
        self.status_icon = QLabel("⚪")
        self.name_label = QLabel(filename)
        self.name_label.setStyleSheet("font-size: 13px; color: #222; font-family: 'SF Pro Text', sans-serif;")
        self.info_icon = QLabel("ⓘ")
        self.info_icon.setStyleSheet("color: #aaa; font-size: 15px;")

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
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Toolbar (İkonlar Büyütüldü) ---
        toolbar = QWidget()
        toolbar.setFixedHeight(90) # Biraz daha genişlettik
        toolbar.setStyleSheet("background: white; border-bottom: 1px solid #d1d1d1;")
        t_layout = QHBoxLayout(toolbar)
        t_layout.setSpacing(15)
        
        # Subler stili büyük ikonlar
        self.start_btn = self.create_tool_btn("Start", "▶️")
        self.settings_btn = self.create_tool_btn("Settings", "⚙️")
        self.add_btn = self.create_tool_btn("Add Item", "➕")
        
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
        self.status_label.setStyleSheet("font-size: 12px; color: #444; font-weight: 400;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(180)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)

        f_layout.addWidget(self.status_label)
        f_layout.addStretch()
        f_layout.addWidget(self.progress_bar)

        main_layout.addWidget(toolbar)
        main_layout.addWidget(self.scroll)
        main_layout.addWidget(footer)

        self.queue = []
        self.threads = []
        self.total_tasks = 0

    def create_tool_btn(self, text, icon_char):
        btn = QPushButton()
        btn.setFixedSize(75, 75)
        btn.setText(f"{icon_char}\n{text}")
        # İkon kısmını büyütmek için CSS
        btn.setStyleSheet("""
            QPushButton { 
                border: none; 
                font-size: 11px; 
                color: #666; 
                background: transparent;
                padding-top: 5px;
            }
            QPushButton:hover { color: #000; background: #f5f5f5; border-radius: 8px; }
        """)
        return btn

    def add_to_queue(self, paths):
        for p in paths:
            item_widget = FileWidget(os.path.basename(p))
            self.list_layout.addWidget(item_widget)
            self.queue.append((p, item_widget))
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

        thread = ConversionThread(path, widget)
        thread.finished_signal.connect(self.on_task_finished)
        self.threads.append(thread)
        thread.start()

    def on_task_finished(self, thread):
        thread.widget.set_status("done")
        self.threads.remove(thread)
        self.process_next()

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Videos", "", "Videos (*.mp4 *.mkv *.avi)")
        if files: self.add_to_queue(files)

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
    sys.exit(app.exec())        for i in range(len(ext_subs)):
            cmd.extend(['-map', str(i + 1)])

        cmd.extend([
            '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt',
            '-map_metadata', '-1', '-map_chapters', '0', '-y', output_file
        ])
        
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
        self.finished_signal.emit(self)

class StripedWidget(QWidget):
    """Subler style zebra-striped background"""
    def paintEvent(self, event):
        painter = QPainter(self)
        line_height = 25
        painter.setPen(QPen(QColor(245, 245, 245), 1))
        for y in range(0, self.height(), line_height):
            painter.drawLine(0, y, self.width(), y)

class FileWidget(QFrame):
    def __init__(self, filename):
        super().__init__()
        self.setFixedHeight(25)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        
        self.status_icon = QLabel("⚪") # Waiting
        self.name_label = QLabel(filename)
        self.name_label.setStyleSheet("font-size: 12px; color: #333;")
        self.info_icon = QLabel("ⓘ")
        self.info_icon.setStyleSheet("color: #bbb;")

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
        self.resize(550, 450)
        self.setAcceptDrops(True)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Toolbar ---
        toolbar = QWidget()
        toolbar.setFixedHeight(70)
        toolbar.setStyleSheet("background: white; border-bottom: 1px solid #d1d1d1;")
        t_layout = QHBoxLayout(toolbar)
        
        self.start_btn = self.create_tool_btn("Start", "▶️")
        self.settings_btn = self.create_tool_btn("Settings", "⚙️")
        self.add_btn = self.create_tool_btn("Add Item", "➕")
        
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
        footer.setFixedHeight(40)
        footer.setStyleSheet("background: #f9f9f9; border-top: 1px solid #d1d1d1;")
        f_layout = QHBoxLayout(footer)
        
        self.status_label = QLabel("0 items in queue.")
        self.status_label.setStyleSheet("font-size: 11px;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(150)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)

        f_layout.addWidget(self.status_label)
        f_layout.addStretch()
        f_layout.addWidget(self.progress_bar)

        main_layout.addWidget(toolbar)
        main_layout.addWidget(self.scroll)
        main_layout.addWidget(footer)

        self.queue = []
        self.threads = []
        self.total_tasks = 0

    def create_tool_btn(self, text, icon):
        btn = QPushButton(f"{icon}\n{text}")
        btn.setFixedSize(60, 55)
        btn.setStyleSheet("QPushButton { border: none; font-size: 10px; color: #555; } QPushButton:hover { color: black; }")
        return btn

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Videos", "", "Videos (*.mp4 *.mkv)")
        if files: self.add_to_queue(files)

    def add_to_queue(self, paths):
        for p in paths:
            item_widget = FileWidget(os.path.basename(p))
            self.list_layout.addWidget(item_widget)
            self.queue.append((p, item_widget))
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
            return
        
        self.status_label.setText("Working...")
        path, widget = self.queue.pop(0)
        widget.set_status("working")
        
        # Update overall progress
        completed = self.total_tasks - len(self.queue)
        self.progress_bar.setValue(int((completed / self.total_tasks) * 100))

        thread = ConversionThread(path, widget)
        thread.finished_signal.connect(self.on_task_finished)
        self.threads.append(thread)
        thread.start()

    def on_task_finished(self, thread):
        thread.widget.set_status("done")
        self.threads.remove(thread)
        self.process_next()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]
        self.add_to_queue(files)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("macintosh")
    app.setStyleSheet("QProgressBar::chunk { background-color: #007aff; border-radius: 3px; }")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

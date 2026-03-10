import sys
import os
import subprocess
import glob

try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                                 QWidget, QLabel, QProgressBar, QScrollArea, 
                                 QFrame, QPushButton, QFileDialog)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
except ImportError:
    sys.exit(1)

class ConversionThread(QThread):
    file_progress = pyqtSignal(int)
    finished_signal = pyqtSignal(str, object)

    def __init__(self, input_file):
        super().__init__()
        self.input_file = input_file

    def run(self):
        if hasattr(sys, '_MEIPASS'):
            ffmpeg_path = os.path.join(sys._MEIPASS, 'ffmpeg')
        else:
            ffmpeg_path = os.path.join(os.path.dirname(__file__), 'ffmpeg')

        base_path = os.path.splitext(self.input_file)[0]
        output_file = f"{base_path}_Fusion.mkv"
        
        subs = glob.glob(f"{base_path}*.*")
        valid_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass'))]

        cmd = [ffmpeg_path, '-i', self.input_file]
        
        for sub in valid_subs:
            cmd.extend(['-i', sub])

        cmd.extend(['-map', '0:v', '-map', '0:a?'])
        
        for i in range(len(valid_subs)):
            cmd.extend(['-map', str(i + 1)])

        cmd.extend([
            '-c:v', 'copy', 
            '-c:a', 'copy', 
            '-c:s', 'srt',
            '-map_metadata', '-1',
            '-map_chapters', '0'
        ])

        for i, sub_path in enumerate(valid_subs):
            parts = sub_path.split('.')
            lang = "eng"
            if len(parts) >= 3:
                short_lang = parts[-2].lower()
                lang_map = {"tr": "tur", "en": "eng", "fr": "fra", "de": "deu"}
                lang = lang_map.get(short_lang, "eng")
            
            cmd.extend([f'-metadata:s:s:{i}', f'language={lang}', f'-metadata:s:s:{i}', 'title='])

        cmd.extend(['-y', output_file])
        
        try:
            self.file_progress.emit(30)
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            process.wait()
            self.file_progress.emit(100)
            self.finished_signal.emit(output_file, self)
        except Exception:
            self.finished_signal.emit("error", self)

class FileWidget(QFrame):
    def __init__(self, filename):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QFrame { background: transparent; border-bottom: 1px solid #333; }")
        layout = QHBoxLayout()
        self.label = QLabel(filename)
        self.label.setStyleSheet("font-size: 13px;")
        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(12)
        layout.addWidget(self.label, 2)
        layout.addWidget(self.pbar, 1)
        self.setLayout(layout)

    def update_progress(self, val):
        self.pbar.setValue(val)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion")
        self.resize(800, 550)
        self.setAcceptDrops(True)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(10, 5, 10, 5)
        self.add_btn = QPushButton("+ Add Files")
        self.add_btn.clicked.connect(self.open_files)
        toolbar.addWidget(self.add_btn)
        toolbar.addStretch()
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background-color: #1e1e1e; border: none;")
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.list_container)

        self.drop_overlay = QLabel("Drag files here or use the + button")
        self.drop_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_overlay.setStyleSheet("color: #666; font-size: 16px;")
        
        self.footer = QWidget()
        self.footer.setFixedHeight(40)
        footer_layout = QHBoxLayout(self.footer)
        self.total_pbar = QProgressBar()
        self.total_pbar.setFixedHeight(15)
        footer_layout.addWidget(self.total_pbar)

        self.main_layout.addLayout(toolbar)
        self.main_layout.addWidget(self.scroll)
        self.main_layout.addWidget(self.footer)

        self.threads = []
        self.completed_count = 0
        self.total_count = 0

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Videos", "", "Video Files (*.mp4 *.mkv *.mov *.avi)")
        if files: self.process_files(files)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if os.path.isfile(u.toLocalFile())]
        if files: self.process_files(files)

    def process_files(self, files):
        self.drop_overlay.hide()
        self.total_count += len(files)
        for path in files:
            item = FileWidget(os.path.basename(path))
            self.list_layout.addWidget(item)
            thread = ConversionThread(path)
            thread.file_progress.connect(item.update_progress)
            thread.finished_signal.connect(self.on_finished)
            self.threads.append(thread)
            thread.start()
        self.update_total_status()

    def on_finished(self, result, thread_obj):
        self.completed_count += 1
        self.update_total_status()
        if thread_obj in self.threads: self.threads.remove(thread_obj)

    def update_total_status(self):
        if self.total_count > 0:
            val = int((self.completed_count / self.total_count) * 100)
            self.total_pbar.setValue(val)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

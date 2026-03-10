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
        external_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass'))]

        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in external_subs:
            cmd.extend(['-i', sub])

        cmd.extend([
            '-map', '0:v', 
            '-map', '0:a?', 
            '-map', '0:s?', # Kaynak dosyadaki altyazıları dahil et
        ])
        
        for i in range(len(external_subs)):
            cmd.extend(['-map', str(i + 1)])

        cmd.extend([
            '-c:v', 'copy', 
            '-c:a', 'copy', 
            '-c:s', 'srt', # Hem iç hem dış tüm altyazıları SRT yap
            '-map_metadata', '-1',
            '-map_chapters', '0',
            '-y', output_file
        ])
        
        try:
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            process.wait()
            self.file_progress.emit(100)
            self.finished_signal.emit(output_file, self)
        except Exception:
            self.finished_signal.emit("error", self)

class FileWidget(QFrame):
    def __init__(self, filename):
        super().__init__()
        self.setFixedHeight(50)
        self.setStyleSheet("""
            QFrame { 
                background: transparent; 
                border-bottom: 1px solid #d1d1d1;
            }
            QLabel { color: #333; font-size: 13px; font-family: 'Helvetica'; }
        """)
        layout = QHBoxLayout()
        self.label = QLabel(filename)
        self.pbar = QProgressBar()
        # Native macOS style enforcement
        self.pbar.setAttribute(Qt.WidgetAttribute.WA_MacStyleToolBar) 
        layout.addWidget(self.label, 2)
        layout.addWidget(self.pbar, 1)
        self.setLayout(layout)

    def update_progress(self, val):
        self.pbar.setValue(val)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion")
        self.resize(800, 600)
        self.setAcceptDrops(True)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(45)
        toolbar.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f6f6f6, stop:1 #dcdcdc); border-bottom: 1px solid #b1b1b1;")
        t_layout = QHBoxLayout(toolbar)
        
        self.add_btn = QPushButton("+ Add Files")
        self.start_btn = QPushButton("▶ Start All")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start_all)
        self.add_btn.clicked.connect(self.open_files)
        
        t_layout.addWidget(self.add_btn)
        t_layout.addWidget(self.start_btn)
        t_layout.addStretch()
        
        # Subler-style Striped Paper Background
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("""
            QScrollArea { 
                border: none;
                background-color: #f0f0f0;
                background-image: url('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAyCAYAAAC9979pAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAABhJREFUeNpiYGBgYPiPAf8D8T8AAnwBAGYBA/6TfN4AAAAASUVORK5CYII=');
            }
        """)
        
        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.list_container)

        self.main_layout.addWidget(toolbar)
        self.main_layout.addWidget(self.scroll)

        self.queue = []
        self.threads = []
        self.total_count = 0
        self.completed_count = 0

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Videos", "", "Video Files (*.mp4 *.mkv *.mov *.avi)")
        if files: self.add_to_list(files)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if os.path.isfile(u.toLocalFile())]
        if files: self.add_to_list(files)

    def add_to_list(self, files):
        for path in files:
            item = FileWidget(os.path.basename(path))
            self.list_layout.addWidget(item)
            self.queue.append((path, item))
        self.start_btn.setEnabled(True)

    def start_all(self):
        self.start_btn.setEnabled(False)
        for path, widget in self.queue:
            thread = ConversionThread(path)
            thread.file_progress.connect(widget.update_progress)
            thread.finished_signal.connect(self.on_finished)
            self.threads.append(thread)
            thread.start()
        self.queue = []

    def on_finished(self, result, thread_obj):
        self.completed_count += 1
        if thread_obj in self.threads: self.threads.remove(thread_obj)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # macOS system style force
    app.setStyle("macos") 
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

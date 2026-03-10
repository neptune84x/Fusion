import sys
import os
import subprocess
import glob
import base64

try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                                 QWidget, QLabel, QProgressBar, QScrollArea, 
                                 QFrame, QPushButton, QFileDialog)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
    from PyQt6.QtGui import QPalette, QBrush, QColor, QPainter
except ImportError:
    sys.exit(1)

class ConversionThread(QThread):
    file_progress = pyqtSignal(int)
    finished_signal = pyqtSignal(str, object)

    def __init__(self, input_file):
        super().__init__()
        self.input_file = input_file

    def run(self):
        # FFmpeg path check
        ffmpeg_path = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'
        
        base_path = os.path.splitext(self.input_file)[0]
        output_file = f"{base_path}_Fusion.mkv"
        
        # Find external subs
        subs = glob.glob(f"{base_path}*.*")
        external_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass'))]

        # Build FFmpeg command
        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in external_subs:
            cmd.extend(['-i', sub])

        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        for i in range(len(external_subs)):
            cmd.extend(['-map', str(i + 1)])

        cmd.extend([
            '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt',
            '-map_metadata', '-1', '-map_chapters', '0', '-y', output_file
        ])
        
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            process.wait()
            self.file_progress.emit(100)
            self.finished_signal.emit(output_file, self)
        except Exception:
            self.finished_signal.emit("error", self)

class FileWidget(QFrame):
    def __init__(self, filename):
        super().__init__()
        self.setFixedHeight(30) # Subler typical row height
        self.setStyleSheet("""
            QFrame { 
                border-bottom: 1px solid #e0e0e0;
                background-color: transparent;
            }
            QLabel { color: #222; font-size: 12px; }
        """)
        layout = QHBoxLayout()
        layout.setContentsMargins(15, 0, 15, 0)
        
        self.label = QLabel(filename)
        self.pbar = QProgressBar()
        self.pbar.setFixedWidth(150)
        self.pbar.setTextVisible(False)
        self.pbar.setProperty("type", "macos") # Custom property for potential CSS target

        layout.addWidget(self.label)
        layout.addStretch()
        layout.addWidget(self.pbar)
        self.setLayout(layout)

    def update_progress(self, val):
        self.pbar.setValue(val)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion - Queue")
        self.resize(700, 500)
        self.setAcceptDrops(True)
        
        # Central Setup
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. Subler Toolbar
        self.toolbar = QWidget()
        self.toolbar.setFixedHeight(55)
        self.toolbar.setStyleSheet("background: #ffffff; border-bottom: 1px solid #c0c0c0;")
        t_layout = QHBoxLayout(self.toolbar)
        
        self.start_btn = QPushButton("Start")
        self.add_btn = QPushButton("Add Item")
        
        # Style buttons to look more like macOS/Subler
        btn_style = "QPushButton { padding: 5px 15px; }"
        self.start_btn.setStyleSheet(btn_style)
        self.add_btn.setStyleSheet(btn_style)
        
        self.start_btn.clicked.connect(self.start_processing)
        self.add_btn.clicked.connect(self.open_files)
        
        t_layout.addStretch()
        t_layout.addWidget(self.start_btn)
        t_layout.addWidget(self.add_btn)
        t_layout.setContentsMargins(10, 0, 10, 0)

        # 2. Striped Background Area (The Notebook Look)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        # CSS to create the striped "Notebook" effect
        self.scroll.setStyleSheet("""
            QScrollArea { background-color: white; }
            QWidget#Container { 
                background-color: white;
                background-image: url(line.png); /* Fallback */
                background-attachment: fixed;
            }
        """)
        
        self.container = QWidget()
        self.container.setObjectName("Container")
        
        # Subler Striped pattern using QPalette for reliability
        palette = self.container.palette()
        brush = QBrush(QColor(245, 247, 250)) # Very light blue/grey for stripes
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll.setWidget(self.container)

        # 3. Footer
        self.footer = QLabel(" 0 items in queue.")
        self.footer.setFixedHeight(25)
        self.footer.setStyleSheet("background: #f0f0f0; border-top: 1px solid #c0c0c0; font-size: 11px; color: #555;")

        self.main_layout.addWidget(self.toolbar)
        self.main_layout.addWidget(self.scroll)
        self.main_layout.addWidget(self.footer)

        self.queue_data = [] # Stores (path, widget)
        self.active_threads = []

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.accept()
        else:
            e.ignore()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]
        self.add_files_to_ui(files)

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Files", "", "Videos (*.mp4 *.mkv *.avi *.mov)")
        if files:
            self.add_files_to_ui(files)

    def add_files_to_ui(self, paths):
        for path in paths:
            if not os.path.isfile(path): continue
            item_widget = FileWidget(os.path.basename(path))
            self.list_layout.addWidget(item_widget)
            self.queue_data.append((path, item_widget))
        
        self.footer.setText(f" {len(self.queue_data)} items in queue.")

    def start_processing(self):
        if not self.queue_data: return
        self.start_btn.setEnabled(False)
        
        for path, widget in self.queue_data:
            thread = ConversionThread(path)
            thread.file_progress.connect(widget.update_progress)
            thread.finished_signal.connect(self.on_item_finished)
            self.active_threads.append(thread)
            thread.start()
        
        self.queue_data = [] # Clear queue after starting

    def on_item_finished(self, result, thread):
        if thread in self.active_threads:
            self.active_threads.remove(thread)
        if not self.active_threads:
            self.start_btn.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # This is crucial for macOS UI
    app.setStyle("macintosh") 
    
    # Force Progress Bar to be the macOS native blue one
    app.setStyleSheet("""
        QProgressBar {
            border: 1px solid #bbb;
            border-radius: 5px;
            background-color: #eee;
            height: 12px;
        }
        QProgressBar::chunk {
            background-color: #007aff; /* macOS Blue */
            width: 1px;
        }
    """)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
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

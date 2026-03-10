import sys
import os
import subprocess
import glob

try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                                 QWidget, QLabel, QProgressBar, QScrollArea, 
                                 QFrame, QPushButton, QFileDialog)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtGui import QPainter, QColor, QPen
except ImportError:
    sys.exit(1)

class ConversionThread(QThread):
    file_progress = pyqtSignal(int)
    finished_signal = pyqtSignal(str, object)

    def __init__(self, input_file):
        super().__init__()
        self.input_file = input_file

    def run(self):
        ffmpeg_path = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'
        base_path = os.path.splitext(self.input_file)[0]
        output_file = f"{base_path}_Fusion.mkv"
        
        subs = glob.glob(f"{base_path}*.*")
        external_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass'))]

        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in external_subs:
            cmd.extend(['-i', sub])

        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        for i in range(len(external_subs)):
            cmd.extend(['-map', str(i + 1)])

        # Buradaki girinti (indentation) hatası düzeltildi
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

class StripedWidget(QWidget):
    """Subler style notebook paper background"""
    def paintEvent(self, event):
        painter = QPainter(self)
        line_height = 30
        painter.setPen(QPen(QColor(230, 230, 230), 1))
        for y in range(0, self.height(), line_height):
            painter.drawLine(0, y, self.width(), y)

class FileWidget(QFrame):
    def __init__(self, filename):
        super().__init__()
        self.setFixedHeight(30)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        layout = QHBoxLayout()
        layout.setContentsMargins(15, 0, 15, 0)
        
        self.label = QLabel(filename)
        self.label.setStyleSheet("color: #333; font-size: 13px;")
        self.pbar = QProgressBar()
        self.pbar.setFixedWidth(120)
        self.pbar.setTextVisible(False)
        self.pbar.setFixedHeight(10)
        
        layout.addWidget(self.label)
        layout.addStretch()
        layout.addWidget(self.pbar)
        self.setLayout(layout)

    def update_progress(self, val):
        self.pbar.setValue(val)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion")
        self.resize(750, 500)
        self.setAcceptDrops(True)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(50)
        toolbar.setStyleSheet("background: #fff; border-bottom: 1px solid #d1d1d1;")
        t_layout = QHBoxLayout(toolbar)
        
        self.add_btn = QPushButton("Add Item")
        self.start_btn = QPushButton("Start")
        self.start_btn.setEnabled(False)
        
        self.add_btn.clicked.connect(self.open_files)
        self.start_btn.clicked.connect(self.start_process)
        
        t_layout.addStretch()
        t_layout.addWidget(self.start_btn)
        t_layout.addWidget(self.add_btn)

        # List Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.container = StripedWidget()
        self.container.setStyleSheet("background-color: white;")
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.container)

        # Footer
        self.footer = QLabel(" 0 items in queue.")
        self.footer.setFixedHeight(25)
        self.footer.setStyleSheet("background: #f8f8f8; border-top: 1px solid #d1d1d1; font-size: 11px;")

        layout.addWidget(toolbar)
        layout.addWidget(self.scroll)
        layout.addWidget(self.footer)

        self.queue = []
        self.threads = []

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        self.add_to_list(paths)

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Files", "", "Videos (*.mp4 *.mkv *.avi *.mov)")
        if files: self.add_to_list(files)

    def add_to_list(self, paths):
        for p in paths:
            if os.path.isfile(p):
                item = FileWidget(os.path.basename(p))
                self.list_layout.addWidget(item)
                self.queue.append((p, item))
        self.start_btn.setEnabled(True)
        self.footer.setText(f" {len(self.queue)} items in queue.")

    def start_process(self):
        self.start_btn.setEnabled(False)
        for path, widget in self.queue:
            t = ConversionThread(path)
            t.file_progress.connect(widget.update_progress)
            t.finished_signal.connect(self.on_finished)
            self.threads.append(t)
            t.start()
        self.queue = []

    def on_finished(self, res, t):
        if t in self.threads: self.threads.remove(t)
        if not self.threads: self.footer.setText(" All tasks completed.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("macintosh") # Native macOS UI
    app.setStyleSheet("QProgressBar::chunk { background-color: #007aff; }")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

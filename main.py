import sys
import os
import subprocess

try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, 
                                 QWidget, QLabel, QProgressBar, 
                                 QScrollArea, QFrame)
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

        base_name = os.path.splitext(os.path.basename(self.input_file))[0]
        output_file = os.path.join(os.path.dirname(self.input_file), f"{base_name}_Fusion.mkv")
        
        cmd = [ffmpeg_path, '-i', self.input_file, '-c:v', 'copy', '-c:a', 'copy', '-y', output_file]
        
        try:
            self.file_progress.emit(25)
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
            process.wait()
            self.file_progress.emit(100)
            self.finished_signal.emit(output_file, self)
        except Exception:
            self.finished_signal.emit("error", self)

class FileWidget(QFrame):
    def __init__(self, filename):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame { background-color: #2b2b2b; border-radius: 5px; margin: 2px; } QLabel { color: #eee; }")
        layout = QVBoxLayout()
        self.label = QLabel(filename)
        self.pbar = QProgressBar()
        self.pbar.setStyleSheet("QProgressBar { border: 1px solid grey; border-radius: 5px; text-align: center; } QProgressBar::chunk { background-color: #05B8CC; }")
        layout.addWidget(self.label)
        layout.addWidget(self.pbar)
        self.setLayout(layout)

    def update_progress(self, val):
        self.pbar.setValue(val)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion v2.0")
        self.resize(750, 500)
        self.setAcceptDrops(True)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        self.drop_label = QLabel("Drag and Drop Video Files Here")
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_label.setMinimumHeight(150)
        self.drop_label.setStyleSheet("border: 2px dashed #666; border-radius: 12px; color: #888; font-size: 20px; background: #1e1e1e;")
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.list_container)

        self.total_pbar = QProgressBar()
        self.total_pbar.setFormat("Total Progress: %p%")
        self.total_pbar.setFixedHeight(25)
        
        self.main_layout.addWidget(self.drop_label)
        self.main_layout.addWidget(self.scroll)
        self.main_layout.addWidget(self.total_pbar)

        self.threads = []
        self.completed_count = 0
        self.total_count = 0

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.accept()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if os.path.isfile(u.toLocalFile())]
        if not files: return

        self.total_count += len(files)
        self.update_total_status()

        for path in files:
            self.start_conversion(path)

    def start_conversion(self, path):
        item = FileWidget(os.path.basename(path))
        self.list_layout.addWidget(item)
        
        thread = ConversionThread(path)
        thread.file_progress.connect(item.update_progress)
        thread.finished_signal.connect(self.on_finished)
        
        self.threads.append(thread)
        thread.start()

    def on_finished(self, result, thread_obj):
        self.completed_count += 1
        self.update_total_status()
        if thread_obj in self.threads:
            self.threads.remove(thread_obj)

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

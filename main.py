import sys
import os
import subprocess

try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, 
                                 QWidget, QLabel, QProgressBar, QTextEdit, 
                                 QScrollArea, QFrame)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
except ImportError:
    sys.exit(1)

class ConversionThread(QThread):
    file_progress = pyqtSignal(int)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str)

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
        
        cmd = [ffmpeg_path, '-i', self.input_file, '-c', 'copy', '-y', output_file]
        
        try:
            self.file_progress.emit(20)
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True, encoding='utf-8')
            process.wait()
            self.file_progress.emit(100)
            if process.returncode == 0:
                self.finished_signal.emit(f"Done: {os.path.basename(output_file)}")
            else:
                self.finished_signal.emit(f"Error: {os.path.basename(self.input_file)}")
        except Exception as e:
            self.finished_signal.emit(f"Failed: {str(e)}")

class FileWidget(QFrame):
    def __init__(self, filename):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout()
        self.label = QLabel(filename)
        self.pbar = QProgressBar()
        self.pbar.setRange(0, 100)
        layout.addWidget(self.label)
        layout.addWidget(self.pbar)
        self.setLayout(layout)

    def update_progress(self, val):
        self.pbar.setValue(val)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion v2.0")
        self.setMinimumSize(750, 500)
        self.setAcceptDrops(True)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        self.drop_label = QLabel("Drag and Drop Video Files Here")
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_label.setStyleSheet("border: 2px dashed #555; border-radius: 10px; padding: 20px; font-size: 18px;")
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.list_container)

        self.total_label = QLabel("Total Progress:")
        self.total_pbar = QProgressBar()
        
        self.main_layout.addWidget(self.drop_label)
        self.main_layout.addWidget(self.scroll)
        self.main_layout.addWidget(self.total_label)
        self.main_layout.addWidget(self.total_pbar)

        self.active_threads = 0
        self.completed_threads = 0
        self.total_files = 0

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        self.total_files += len(urls)
        self.update_total_bar()

        for url in urls:
            path = url.toLocalFile()
            if os.path.isfile(path):
                self.start_conversion(path)

    def start_conversion(self, path):
        item = FileWidget(os.path.basename(path))
        self.list_layout.addWidget(item)
        
        thread = ConversionThread(path)
        thread.file_progress.connect(item.update_progress)
        thread.finished_signal.connect(lambda msg: self.on_file_finished(msg))
        
        self.active_threads += 1
        thread.start()

    def on_file_finished(self, msg):
        self.completed_threads += 1
        self.update_total_bar()

    def update_total_bar(self):
        if self.total_files > 0:
            val = int((self.completed_threads / self.total_files) * 100)
            self.total_pbar.setValue(val)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

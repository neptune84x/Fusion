import sys
import os
import subprocess
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, 
                             QWidget, QLabel, QProgressBar, QTextEdit)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

class ProcessThread(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, input_file):
        super().__init__()
        self.input_file = input_file

    def run(self):
        base_path = os.path.dirname(self.input_file)
        file_name = os.path.splitext(os.path.basename(self.input_file))[0]
        output_file = os.path.join(base_path, f"Fusion_{file_name}.mkv")
        
        ffmpeg_path = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'

        # Altyazı Tarama
        subs = []
        lang_map = {'tr': 'tur', 'en': 'eng', 'de': 'ger', 'fr': 'fra', 'es': 'spa'}
        
        try:
            for f in os.listdir(base_path):
                if f.startswith(file_name) and f.endswith(('.srt', '.ass', '.vtt')):
                    lang_code = 'und'
                    for suffix, code in lang_map.items():
                        if f".{suffix}." in f.lower() or f"_{suffix}." in f.lower():
                            lang_code = code
                            break
                    subs.append({'file': os.path.join(base_path, f), 'lang': lang_code})

            cmd = [ffmpeg_path, '-i', self.input_file]
            for s in subs:
                cmd.extend(['-i', s['file']])

            cmd.extend(['-map', '0:v', '-map', '0:a', '-map', '0:t?'])
            
            for i, s in enumerate(subs):
                cmd.extend(['-map', str(i+1), f'-c:s:{i}', 'subrip', f'-metadata:s:s:{i}', f'language={s["lang"]}'])

            cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-map_metadata', '0', '-metadata', 'title=', 
                        '-metadata:s:v', 'title=', '-metadata:s:a', 'title=', '-y', output_file])

            self.log.emit(f"🚀 Fusion İşlemi Başladı: {file_name}")
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True, encoding='utf-8')
            
            for line in process.stderr:
                if "time=" in line:
                    self.progress.emit(50) 

            process.wait()
            self.log.emit(f"✅ Tamamlandı!\n📂 Dosya: {output_file}")
        except Exception as e:
            self.log.emit(f"❌ Hata oluştu: {str(e)}")
        
        self.finished.emit()

class DropArea(QLabel):
    fileDropped = pyqtSignal(str)

    def __init__(self):
        super().__init__("Videonuzu Buraya Sürükleyin")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            QLabel {
                border: 3px dashed #555;
                border-radius: 15px;
                color: #888;
                background-color: #252525;
                font-size: 18px;
                font-weight: bold;
            }
            QLabel:hover {
                border-color: #ff9500;
                color: #fff;
                background-color: #2b2b2b;
            }
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            self.setStyleSheet(self.styleSheet().replace("#555", "#ff9500"))
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self.styleSheet().replace("#ff9500", "#555"))

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files:
            self.fileDropped.emit(files[0])

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion - v1.0")
        self.setFixedSize(600, 450)
        self.setStyleSheet("QMainWindow { background-color: #1a1a1a; }")

        layout = QVBoxLayout()
        self.drop_area = DropArea()
        self.drop_area.fileDropped.connect(self.start_process)
        
        self.progress = QProgressBar()
        self.progress.setStyleSheet("""
            QProgressBar { border: 1px solid #333; border-radius: 5px; text-align: center; color: white; background: #222; }
            QProgressBar::chunk { background-color: #ff9500; }
        """)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #000; color: #00ff00; font-family: 'Courier New'; font-size: 11px; border: 1px solid #333;")

        layout.addWidget(self.drop_area, 2)
        layout.addWidget(self.progress)
        layout.addWidget(self.log_view, 1)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def start_process(self, file_path):
        if not file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov')):
            self.log_view.append("⚠️ Hata: Sadece video dosyalarını sürükleyin!")
            return
            
        self.drop_area.setEnabled(False)
        self.drop_area.setText("Fusion İşliyor...")
        self.progress.setRange(0, 0)
        self.thread = ProcessThread(file_path)
        self.thread.log.connect(self.log_view.append)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()

    def on_finished(self):
        self.drop_area.setEnabled(True)
        self.drop_area.setText("Videonuzu Buraya Sürükleyin")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

import sys
import os
import subprocess
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                             QWidget, QFileDialog, QLabel, QProgressBar, QTextEdit)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

class ProcessThread(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, input_file):
        super().__init__()
        self.input_file = input_file

    def run(self) -> None:
        base_path = os.path.dirname(self.input_file)
        file_name = os.path.splitext(os.path.basename(self.input_file))[0]
        # Çıktı dosyası ismi Fusion_ ekiyle oluşturulur
        output_file = os.path.join(base_path, f"Fusion_{file_name}.mkv")
        
        ffmpeg_path = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'

        # Altyazı Tarama ve Dil Eşleştirme
        subs = []
        lang_map = {'tr': 'tur', 'en': 'eng', 'de': 'ger', 'fr': 'fra', 'es': 'spa', 'it': 'ita'}
        
        for f in os.listdir(base_path):
            if f.startswith(file_name) and f.endswith(('.srt', '.ass', '.vtt')):
                lang_code = 'und'
                for suffix, code in lang_map.items():
                    if f".{suffix}." in f.lower() or f"_{suffix}." in f.lower():
                        lang_code = code
                        break
                subs.append({'file': os.path.join(base_path, f), 'lang': lang_code})

        # FFmpeg Komut İnşası
        cmd = [ffmpeg_path, '-i', self.input_file]
        for s in subs:
            cmd.extend(['-i', s['file']])

        cmd.extend(['-map', '0:v', '-map', '0:a', '-map', '0:t?'])
        
        for i, s in enumerate(subs):
            cmd.extend(['-map', str(i+1)])
            cmd.extend([f'-c:s:{i}', 'subrip'])
            cmd.extend([f'-metadata:s:s:{i}', f'language={s["lang"]}'])

        cmd.extend([
            '-c:v', 'copy', '-c:a', 'copy',
            '-map_metadata', '0',
            '-metadata', 'title=', 
            '-metadata:s:v', 'title=', '-metadata:s:a', 'title=',
            '-y', output_file
        ])

        self.log.emit(f"Fusion İşlemi Başladı: {file_name}")
        
        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True, encoding='utf-8')
        
        for line in process.stderr:
            if "time=" in line:
                self.log.emit("İşleniyor...")
                self.progress.emit(50) 

        process.wait()
        self.log.emit(f"İşlem Tamamlandı!\nKaydedilen: {output_file}")
        self.finished.emit()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion - Media Tagger & Merger")
        self.setFixedSize(550, 400)

        layout = QVBoxLayout()
        self.label = QLabel("Temizlemek ve Altyazı Eklemek İçin Video Seçin")
        self.label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.btn = QPushButton("Video Dosyası Seç")
        self.btn.setFixedHeight(40)
        self.btn.clicked.connect(self.open_file)
        
        self.progress = QProgressBar()
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: monospace;")

        layout.addWidget(self.label)
        layout.addWidget(self.btn)
        layout.addWidget(self.progress)
        layout.addWidget(self.log_view)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Video Seç", "", "Video Dosyaları (*.mp4 *.mkv *.avi *.mov)")
        if file_path:
            self.start_process(file_path)

    def start_process(self, file_path):
        self.btn.setEnabled(False)
        self.progress.setRange(0, 0) # Belirsiz ilerleme (Busy indicator)
        self.thread = ProcessThread(file_path)
        self.thread.log.connect(self.log_view.append)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()

    def on_finished(self):
        self.btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

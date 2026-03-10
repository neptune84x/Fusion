import sys
import os
import subprocess
import re
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
        output_file = os.path.join(base_path, f"{file_name}_cleaned.mkv")
        
        # FFmpeg yolunu belirle (Gömülü paket içindeki yol)
        ffmpeg_path = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'

        # 1. Altyazı Dosyalarını Tara
        subs = []
        lang_map = {'tr': 'tur', 'en': 'eng', 'de': 'ger', 'fr': 'fra', 'es': 'spa'}
        
        for f in os.listdir(base_path):
            if f.startswith(file_name) and f.endswith(('.srt', '.ass', '.vtt')):
                lang_code = 'und'
                for suffix, code in lang_map.items():
                    if f".{suffix}." in f.lower():
                        lang_code = code
                        break
                subs.append({'file': os.path.join(base_path, f), 'lang': lang_code})

        # 2. FFmpeg Komutunu Oluştur
        cmd = [ffmpeg_path, '-i', self.input_file]
        for s in subs:
            cmd.extend(['-i', s['file']])

        cmd.extend(['-map', '0:v', '-map', '0:a', '-map', '0:t?']) # Video, Ses ve Fontları al
        
        # Altyazıları ekle ve SRT'ye çevir
        for i, s in enumerate(subs):
            cmd.extend(['-map', str(i+1)])
            cmd.extend([f'-c:s:{i}', 'subrip'])
            cmd.extend([f'-metadata:s:s:{i}', f'language={s["lang"]}'])

        # Metadata temizliği (Chapter hariç)
        cmd.extend([
            '-c:v', 'copy', '-c:a', 'copy',
            '-map_metadata', '0', # Global metadatayı önce kopyala
            '-metadata', 'title=', # Başlığı sil
            '-metadata:s:v', 'title=', '-metadata:s:a', 'title=', # Stream başlıklarını sil
            '-y', output_file
        ])

        self.log.emit(f"İşlem başlıyor: {file_name}")
        
        # FFmpeg'i çalıştır ve ilerlemeyi oku
        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True, encoding='utf-8')
        
        # Basit ilerleme çubuğu simülasyonu (FFmpeg çıktı analizi)
        for line in process.stderr:
            if "time=" in line:
                self.log.emit(line.strip())
                self.progress.emit(50) # Örnek sabit değer, geliştirilebilir

        process.wait()
        self.log.emit(f"Tamamlandı! Dosya: {output_file}")
        self.finished.emit()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MKV Tag Cleaner & Subtitle Merger")
        self.setFixedSize(500, 350)

        layout = QVBoxLayout()
        self.label = QLabel("Video dosyasını seçin veya buraya bırakın")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.btn = QPushButton("Dosya Seç")
        self.btn.clicked.connect(self.open_file)
        
        self.progress = QProgressBar()
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)

        layout.addWidget(self.label)
        layout.addWidget(self.btn)
        layout.addWidget(self.progress)
        layout.addWidget(self.log_view)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Video Seç", "", "Videos (*.mp4 *.mkv *.avi)")
        if file_path:
            self.start_process(file_path)

    def start_process(self, file_path):
        self.btn.setEnabled(False)
        self.thread = ProcessThread(file_path)
        self.thread.progress.connect(self.progress.setValue)
        self.thread.log.connect(self.log_view.append)
        self.thread.finished.connect(lambda: self.btn.setEnabled(True))
        self.thread.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

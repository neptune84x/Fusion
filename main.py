import sys
import os
import subprocess
import traceback

# Kütüphane yükleme hatalarını terminale basması için en başa alıyoruz
try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, 
                                 QWidget, QLabel, QProgressBar, QTextEdit, QMessageBox)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
except ImportError as e:
    print(f"Kritik Kütüphane Hatası: {e}")
    sys.exit(1)

def exception_hook(exctype, value, tb):
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    print(error_msg)
    # Uygulama açılırsa hata kutusu gösterir
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setText("Uygulama Çalışma Hatası")
    msg.setInformativeText(error_msg)
    msg.exec()

sys.excepthook = exception_hook

class ProcessThread(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, input_file):
        super().__init__()
        self.input_file = input_file

    def run(self):
        # Bundle içindeki FFmpeg yolunu bulma (Modern Yöntem)
        if hasattr(sys, '_MEIPASS'):
            ffmpeg_path = os.path.join(sys._MEIPASS, 'ffmpeg')
        else:
            ffmpeg_path = os.path.join(os.path.dirname(__file__), 'ffmpeg')

        output_file = os.path.join(os.path.dirname(self.input_file), f"Fusion_{os.path.basename(self.input_file)}")
        
        cmd = [ffmpeg_path, '-i', self.input_file, '-c', 'copy', '-y', output_file]
        
        try:
            self.log.emit("⏳ İşlem başlatıldı...")
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True, encoding='utf-8')
            process.wait()
            if process.returncode == 0:
                self.log.emit(f"✅ Başarılı: {output_file}")
            else:
                self.log.emit("❌ FFmpeg hatası oluştu.")
        except Exception as e:
            self.log.emit(f"❌ Sistem Hatası: {str(e)}")
        
        self.finished.emit()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion v2026")
        self.setFixedSize(500, 350)
        self.setAcceptDrops(True)
        
        layout = QVBoxLayout()
        self.label = QLabel("Videoyu Buraya Sürükle ve Bırak")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("""
            QLabel { 
                border: 2px dashed #555; 
                border-radius: 10px; 
                background: #222; 
                color: #aaa; 
                font-size: 16px;
            }
        """)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background: #000; color: #0f0; font-family: monospace;")
        
        layout.addWidget(self.label, 1)
        layout.addWidget(self.log_view, 1)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()
    
    def dropEvent(self, e):
        file_path = e.mimeData().urls()[0].toLocalFile()
        self.log_view.append(f"📁 Dosya alındı: {os.path.basename(file_path)}")
        self.thread = ProcessThread(file_path)
        self.thread.log.connect(self.log_view.append)
        self.thread.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # macOS üzerinde standart görünüm için
    window = MainWindow()
    window.show()
    sys.exit(app.exec())            if hasattr(sys, '_MEIPASS'):
                ffmpeg_path = os.path.join(sys._MEIPASS, 'ffmpeg')
            else:
                ffmpeg_path = 'ffmpeg'

            # Altyazı Tarama (Aynı isimli .srt dosyaları)
            subs = []
            lang_map = {'tr': 'tur', 'en': 'eng', 'de': 'ger', 'fr': 'fra', 'es': 'spa'}
            
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

            self.log.emit(f"🚀 İşlem Başladı: {file_name}")
            
            # subprocess.STARTUPINFO macOS'ta gerekmez, sadece Popen yeterli
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True, encoding='utf-8')
            
            while True:
                line = process.stderr.readline()
                if not line: break
                if "time=" in line:
                    self.progress.emit(50)

            process.wait()
            self.log.emit(f"✅ Tamamlandı!\n📂 Dosya: {output_file}")
            
        except Exception as e:
            self.log.emit(f"❌ Hata: {str(e)}")
        
        self.finished.emit()

class DropArea(QLabel):
    fileDropped = pyqtSignal(str)
    def __init__(self):
        super().__init__("Videonuzu Buraya Sürükleyin")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setStyleSheet("QLabel { border: 3px dashed #555; border-radius: 15px; color: #888; background-color: #252525; font-size: 18px; font-weight: bold; } QLabel:hover { border-color: #ff9500; color: #fff; }")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files: self.fileDropped.emit(files[0])

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion v1.0")
        self.setFixedSize(600, 450)
        self.setStyleSheet("QMainWindow { background-color: #1a1a1a; }")
        layout = QVBoxLayout()
        self.drop_area = DropArea()
        self.drop_area.fileDropped.connect(self.start_process)
        self.progress = QProgressBar()
        self.progress.setStyleSheet("QProgressBar { border: 1px solid #333; border-radius: 5px; text-align: center; color: white; background: #222; } QProgressBar::chunk { background-color: #ff9500; }")
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #000; color: #00ff00; font-family: 'Courier New'; font-size: 11px;")
        layout.addWidget(self.drop_area, 2); layout.addWidget(self.progress); layout.addWidget(self.log_view, 1)
        container = QWidget(); container.setLayout(layout); self.setCentralWidget(container)

    def start_process(self, file_path):
        if not file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov')): return
        self.drop_area.setEnabled(False); self.progress.setRange(0, 0)
        self.thread = ProcessThread(file_path)
        self.thread.log.connect(self.log_view.append)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()

    def on_finished(self):
        self.drop_area.setEnabled(True); self.progress.setRange(0, 100); self.progress.setValue(100)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

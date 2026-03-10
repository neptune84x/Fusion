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
    sys.exit(app.exec())

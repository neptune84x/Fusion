import sys
import os
import subprocess
import glob
import re

try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                                 QWidget, QLabel, QProgressBar, QScrollArea, 
                                 QFrame, QPushButton, QFileDialog)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont
except ImportError:
    sys.exit(1)

class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)

    def __init__(self, input_file, widget):
        super().__init__()
        self.input_file = input_file
        self.widget = widget

    def run(self):
        ffmpeg_path = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'
        base_path = os.path.splitext(self.input_file)[0]
        output_file = f"{base_path}_Fusion.mkv"
        
        # Ek altyazıları tara
        subs = glob.glob(f"{base_path}*.*")
        ext_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass')) and s != self.input_file]

        # Komut Başlangıcı
        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in ext_subs:
            cmd.extend(['-i', sub])

        # MAP: Video, Ses ve Kaynak Altyazıları Olduğu Gibi Al
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        
        # Metadata: Kaynaktaki tüm track dillerini koru, global title'ı sil
        cmd.extend(['-map_metadata', '0', '-map_metadata:g', '-1', '-map_chapters', '0'])

        # DIŞ ALTYAZI DİL ATAMASI (KARIŞIKLIĞI ÖNLEME):
        # Kaynaktaki altyazıların üzerine yazmamak için indisleri doğru yönetiyoruz.
        for i, sub_path in enumerate(ext_subs):
            cmd.extend(['-map', str(i + 1)]) # Dış altyazıyı ekle
            
            # Dil yakalama (en, tr, ger...)
            match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', sub_path.lower())
            lang = match.group(1) if match else 'und'
            
            # Kaynak dosyadaki altyazıların (0:s) sonrasına, yeni stream'ler olarak metadata ekle
            # Dış altyazılar FFmpeg'de stream sırasında sona eklenir.
            # -metadata:s:s:{N} komutuyla N. altyazı kanalına dil atanır.
            cmd.extend([f'-metadata:s:s:{i}', f'language={lang}'])

        # KODLAMA: Her şeyi kopyala, altyazıları srt yap
        cmd.extend([
            '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt',
            '-y', output_file
        ])
        
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
        self.finished_signal.emit(self)

class SublerListWidget(QWidget):
    """Subler tipi gerçek pijama deseni"""
    def paintEvent(self, event):
        painter = QPainter(self)
        row_height = 25
        color_alt = QColor(243, 246, 250)
        for i in range(0, (self.height() // row_height) + 1):
            if i % 2 == 1:
                painter.fillRect(0, i * row_height, self.width(), row_height, QBrush(color_alt))

class FileWidget(QFrame):
    def __init__(self, filename):
        super().__init__()
        self.setFixedHeight(25)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        self.status_icon = QLabel("⚪")
        self.status_icon.setFixedWidth(24)
        self.name_label = QLabel(filename)
        self.name_label.setStyleSheet("font-size: 13px; color: #111;")
        self.info_icon = QLabel("ⓘ")
        self.info_icon.setStyleSheet("color: #999; font-size: 16px;")
        layout.addWidget(self.status_icon)
        layout.addWidget(self.name_label)
        layout.addStretch()
        layout.addWidget(self.info_icon)

    def set_status(self, mode):
        icons = {"working": "🟠", "done": "✅", "error": "❌"}
        self.status_icon.setText(icons.get(mode, "⚪"))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Queue")
        self.resize(650, 550)
        self.setAcceptDrops(True)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # --- TOOLBAR (Görseldeki Gibi Büyük İkonlar) ---
        toolbar = QWidget()
        toolbar.setFixedHeight(110) # Daha yüksek toolbar
        toolbar.setStyleSheet("background: white; border-bottom: 1px solid #C0C0C0;")
        t_layout = QHBoxLayout(toolbar)
        t_layout.setContentsMargins(25, 10, 25, 10)
        t_layout.setSpacing(30)
        
        # İkonları belirgin şekilde büyüttük (24px -> 40px civarı emoji boyutu)
        self.start_btn = self.create_nav_btn("Start", "▶️")
        self.settings_btn = self.create_nav_btn("Settings", "⚙️")
        self.add_btn = self.create_nav_btn("Add Item", "➕")
        
        t_layout.addStretch()
        t_layout.addWidget(self.start_btn)
        t_layout.addWidget(self.settings_btn)
        t_layout.addWidget(self.add_btn)

        # --- LİSTE ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = SublerListWidget()
        self.container.setStyleSheet("background: white;")
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.container)

        # --- FOOTER ---
        footer = QWidget()
        footer.setFixedHeight(55)
        footer.setStyleSheet("background: #F0F0F0; border-top: 1px solid #C0C0C0;")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(15, 0, 15, 0)
        self.status_label = QLabel("0 items in queue.")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(220)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setTextVisible(False)
        f_layout.addWidget(self.status_label)
        f_layout.addStretch()
        f_layout.addWidget(self.progress_bar)

        main_layout.addWidget(toolbar)
        main_layout.addWidget(self.scroll)
        main_layout.addWidget(footer)
        cw = QWidget(); cw.setLayout(main_layout); self.setCentralWidget(cw)

        self.queue = []; self.threads = []; self.total_tasks = 0
        self.add_btn.clicked.connect(self.open_files)
        self.start_btn.clicked.connect(self.start_processing)

    def create_nav_btn(self, text, icon_char):
        btn = QPushButton()
        btn.setFixedSize(90, 90) # Buton alanı büyütüldü
        # Subler stili: İkon ve metni alt alta büyük boyutta göster
        btn.setText(f"{icon_char}\n\n{text}")
        btn.setStyleSheet("""
            QPushButton { 
                border: none; 
                font-size: 13px; /* Yazı boyutu büyütüldü */
                color: #333; 
                background: transparent; 
                font-weight: 500;
                padding: 10px;
            }
            QPushButton:hover { background-color: #F5F5F5; border-radius: 15px; }
        """)
        # Emojiyi (ikonu) büyütmek için font ayarı
        font = QFont()
        font.setPointSize(28) # İkon (emoji) büyüklüğü
        btn.setFont(font)
        return btn

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Videos", "", "Videos (*.mp4 *.mkv *.avi)")
        if files: self.add_to_queue(files)

    def add_to_queue(self, paths):
        for p in paths:
            w = FileWidget(os.path.basename(p))
            self.list_layout.addWidget(w)
            self.queue.append((p, w))
        self.total_tasks = len(self.queue)
        self.status_label.setText(f"{self.total_tasks} items in queue.")

    def start_processing(self):
        if not self.queue: return
        self.start_btn.setEnabled(False); self.process_next()

    def process_next(self):
        if not self.queue:
            self.status_label.setText("Completed."); self.start_btn.setEnabled(True); self.progress_bar.setValue(100)
            return
        self.status_label.setText("Working."); path, widget = self.queue.pop(0)
        widget.set_status("working")
        done = self.total_tasks - len(self.queue)
        self.progress_bar.setValue(int(((done - 1) / self.total_tasks) * 100))
        t = ConversionThread(path, widget)
        t.finished_signal.connect(self.on_task_finished); self.threads.append(t); t.start()

    def on_task_finished(self, t):
        t.widget.set_status("done"); self.threads.remove(t); self.process_next()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]
        self.add_to_queue(files)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("macintosh")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

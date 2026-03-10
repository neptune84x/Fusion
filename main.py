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
    from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
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

        # Komut başla
        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in ext_subs:
            cmd.extend(['-i', sub])

        # MAP ve METADATA: 
        # 1. Kaynaktaki tüm streamleri ve dillerini olduğu gibi al (-map_metadata 0)
        # 2. Gereksiz global tagleri sil (-map_metadata:g -1)
        cmd.extend([
            '-map', '0',               # Kaynaktaki her şeyi al (video, audio, sub)
            '-map_metadata', '0',      # Track bazlı dilleri koru
            '-map_metadata:g', '-1',   # Global 'Title' gibi tagleri temizle
            '-map_chapters', '0'       # Chapterları koru
        ])

        # Dış altyazıları maple ve dil kodlarını ata
        for i, sub_path in enumerate(ext_subs):
            cmd.extend(['-map', str(i + 1)])
            
            # Dil yakalama (en, tr, ger...)
            match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', sub_path.lower())
            lang = match.group(1) if match else 'und'
            
            # NOT: Kaynaktaki altyazı sayısını bilmediğimiz için 
            # FFmpeg'in 'next available' mantığını kullanıyoruz
            cmd.extend([f'-metadata:s:s:{i}', f'language={lang}'])

        # Kodlama: Her şeyi kopyala, altyazıları srt yap
        cmd.extend([
            '-c:v', 'copy', 
            '-c:a', 'copy', 
            '-c:s', 'srt', 
            '-disposition:s:0', 'default', # İlk altyazıyı varsayılan yap
            '-y', output_file
        ])
        
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
        self.finished_signal.emit(self)

class SublerListWidget(QWidget):
    """Subler'ın gerçek pijama deseni (Alternating row colors)"""
    def paintEvent(self, event):
        painter = QPainter(self)
        row_height = 25
        # Subler gri rengi: #F3F6FA veya #F2F2F2
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
        
        self.status_icon = QLabel("⚪") # Durum ikonu
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
        # Simgeleri biraz büyüttük ve görsele yaklaştırdık
        icons = {"working": "🟠", "done": "✅", "error": "❌"}
        self.status_icon.setText(icons.get(mode, "⚪"))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Queue")
        self.resize(650, 500)
        self.setAcceptDrops(True)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # --- TOOLBAR (Gerçek Subler Boyutları) ---
        toolbar = QWidget()
        toolbar.setFixedHeight(100)
        toolbar.setStyleSheet("background: white; border-bottom: 1px solid #C0C0C0;")
        t_layout = QHBoxLayout(toolbar)
        t_layout.setContentsMargins(20, 10, 20, 10)
        t_layout.setSpacing(10)
        
        # Büyük ikonlar ve alt metinler
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
        self.status_label.setStyleSheet("font-size: 13px; color: #333;")
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(220)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background: #E0E0E0; border-radius: 5px; border: 1px solid #CCC; }
            QProgressBar::chunk { background: #007AFF; border-radius: 4px; }
        """)

        f_layout.addWidget(self.status_label)
        f_layout.addStretch()
        f_layout.addWidget(self.progress_bar)

        main_layout.addWidget(toolbar)
        main_layout.addWidget(self.scroll)
        main_layout.addWidget(footer)
        
        cw = QWidget()
        cw.setLayout(main_layout)
        self.setCentralWidget(cw)

        self.queue = []
        self.threads = []
        self.total_tasks = 0

        self.add_btn.clicked.connect(self.open_files)
        self.start_btn.clicked.connect(self.start_processing)

    def create_nav_btn(self, text, icon_char):
        btn = QPushButton()
        btn.setFixedSize(85, 80)
        # Subler stili: İkon üstte büyük, metin altta küçük
        btn.setText(f"{icon_char}\n\n{text}")
        btn.setStyleSheet("""
            QPushButton { 
                border: none; font-size: 11px; color: #444; 
                background: transparent; font-weight: 500;
            }
            QPushButton:hover { background-color: #F2F2F2; border-radius: 12px; color: #000; }
        """)
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
        self.start_btn.setEnabled(False)
        self.process_next()

    def process_next(self):
        if not self.queue:
            self.status_label.setText("Completed.")
            self.start_btn.setEnabled(True)
            self.progress_bar.setValue(100)
            return
        
        self.status_label.setText("Working.")
        path, widget = self.queue.pop(0)
        widget.set_status("working")
        
        done = self.total_tasks - len(self.queue)
        self.progress_bar.setValue(int(((done - 1) / self.total_tasks) * 100))

        t = ConversionThread(path, widget)
        t.finished_signal.connect(self.on_task_finished)
        self.threads.append(t)
        t.start()

    def on_task_finished(self, t):
        t.widget.set_status("done")
        self.threads.remove(t)
        self.process_next()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]
        self.add_to_queue(files)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("macintosh")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())        for sub in ext_subs:
            cmd.extend(['-i', sub])

        # MAPLEME:
        # 0:v (Video), 0:a? (Tüm sesler ve dilleri), 0:s? (Kaynaktaki tüm altyazılar ve dilleri)
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        
        # DIŞ ALTYAZI İŞLEME:
        for i, sub_path in enumerate(ext_subs):
            cmd.extend(['-map', str(i + 1)]) # Her dış dosya yeni bir input
            
            # Dil kodunu ayıkla (video.en.srt -> en)
            match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', sub_path.lower())
            lang = match.group(1) if match else 'und'
            
            # Dış altyazı kanalına dil kodunu ata (0:s kaynaktakiler, i+1 dıştakiler)
            # FFmpeg'de yeni eklenen streamler mevcutların arkasına dizilir
            cmd.extend([f'-metadata:s:s:{i}', f'language={lang}'])

        # KODLAMA VE TEMİZLİK:
        cmd.extend([
            '-c:v', 'copy', 
            '-c:a', 'copy', 
            '-c:s', 'srt',           # Tüm altyazıları SRT'ye çevir
            '-map_metadata', '-1',   # Title, tag, encoder bilgilerini sil
            '-map_chapters', '0',     # Bölümleri (Chapters) KORU
            '-y', output_file
        ])
        
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
        self.finished_signal.emit(self)

class StripedWidget(QWidget):
    """Subler pijama stili: Sadece yatay ince ayırıcı çizgiler"""
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
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        
        self.status_icon = QLabel("⚪") # Bekliyor
        self.name_label = QLabel(filename)
        self.name_label.setStyleSheet("font-size: 13px; color: #333; font-weight: 400;")
        self.info_icon = QLabel("ⓘ")
        self.info_icon.setStyleSheet("color: #bbb; font-size: 14px;")

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
        self.resize(600, 550)
        self.setAcceptDrops(True)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # --- TOOLBAR (Subler stili dikey yerleşim) ---
        toolbar = QWidget()
        toolbar.setFixedHeight(90)
        toolbar.setStyleSheet("background: white; border-bottom: 1px solid #dcdcdc;")
        t_layout = QHBoxLayout(toolbar)
        t_layout.setContentsMargins(15, 0, 15, 5)
        
        self.start_btn = self.create_nav_btn("Start", "▶️") # Görseldeki Start ikonu benzeri
        self.settings_btn = self.create_nav_btn("Settings", "⚙️")
        self.add_btn = self.create_nav_btn("Add Item", "➕")
        
        t_layout.addStretch()
        t_layout.addWidget(self.start_btn)
        t_layout.addWidget(self.settings_btn)
        t_layout.addWidget(self.add_btn)

        # --- LİSTE ALANI (Çizgili Defter) ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = StripedWidget()
        self.container.setStyleSheet("background: white;")
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.container)

        # --- FOOTER (Genel Progress) ---
        footer = QWidget()
        footer.setFixedHeight(45)
        footer.setStyleSheet("background: #fcfcfc; border-top: 1px solid #dcdcdc;")
        f_layout = QHBoxLayout(footer)
        
        self.status_label = QLabel("0 items in queue.")
        self.status_label.setStyleSheet("font-size: 12px; color: #555;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(180)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)

        f_layout.addWidget(self.status_label)
        f_layout.addStretch()
        f_layout.addWidget(self.progress_bar)

        main_layout.addWidget(toolbar)
        main_layout.addWidget(self.scroll)
        main_layout.addWidget(footer)
        
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.queue = []
        self.threads = []
        self.total_tasks = 0

        self.add_btn.clicked.connect(self.open_files)
        self.start_btn.clicked.connect(self.start_processing)

    def create_nav_btn(self, text, icon):
        btn = QPushButton(f"{icon}\n{text}")
        btn.setFixedSize(75, 75)
        btn.setStyleSheet("""
            QPushButton { border: none; font-size: 11px; color: #555; background: transparent; padding-top: 10px; }
            QPushButton:hover { background-color: #f0f0f0; border-radius: 10px; color: #000; }
        """)
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
        self.start_btn.setEnabled(False)
        self.process_next()

    def process_next(self):
        if not self.queue:
            self.status_label.setText("Completed.")
            self.start_btn.setEnabled(True)
            self.progress_bar.setValue(100)
            return
        
        self.status_label.setText("Working...")
        path, widget = self.queue.pop(0)
        widget.set_status("working")
        
        completed_count = self.total_tasks - len(self.queue)
        self.progress_bar.setValue(int(((completed_count - 1) / self.total_tasks) * 100))

        thread = ConversionThread(path, widget)
        thread.finished_signal.connect(self.on_task_finished)
        self.threads.append(thread)
        thread.start()

    def on_task_finished(self, thread):
        thread.widget.set_status("done")
        self.threads.remove(thread)
        self.process_next()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]
        self.add_to_queue(files)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("macintosh")
    app.setStyleSheet("QProgressBar::chunk { background-color: #007aff; border-radius: 4px; }")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

import sys, os, subprocess, json, glob, re
try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                                 QWidget, QLabel, QProgressBar, QScrollArea, 
                                 QFrame, QPushButton, QFileDialog, QSizePolicy)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
    from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QIcon, QAction
except ImportError:
    sys.exit(1)

class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)
    def __init__(self, input_file, widget):
        super().__init__()
        self.input_file = input_file
        self.widget = widget
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        if not self._is_running: return
        ffmpeg_path = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'
        ffprobe_path = os.path.join(sys._MEIPASS, 'ffprobe') if hasattr(sys, '_MEIPASS') else 'ffprobe'
        base_path = os.path.splitext(self.input_file)[0]
        output_file = f"{base_path}_Fusion.mkv"

        # FFprobe ile dilleri JSON olarak çek (Teknik kısım - Değişmedi)
        probe_cmd = [ffprobe_path, '-v', 'quiet', '-print_format', 'json', '-show_streams', self.input_file]
        source_langs = {"audio": [], "subtitle": []}
        try:
            probe_data = json.loads(subprocess.check_output(probe_cmd))
            for s in probe_data.get('streams', []):
                lang = s.get('tags', {}).get('language', 'und')
                if s['codec_type'] == 'audio': source_langs['audio'].append(lang)
                if s['codec_type'] == 'subtitle': source_langs['subtitle'].append(lang)
        except: pass

        if not self._is_running: return

        # Dış Altyazılar (Dizindeki .tr.srt vb.)
        subs = glob.glob(f"{base_path}*.*")
        ext_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass')) and s != self.input_file]

        # Komut İnşası (HatasızMetadata)
        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in ext_subs: cmd.extend(['-i', sub])
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        for i in range(len(ext_subs)): cmd.extend(['-map', str(i + 1)])

        cmd.extend(['-map_metadata', '-1', '-map_chapters', '0']) # Judas temizliği

        for i, lang in enumerate(source_langs['audio']): cmd.extend([f'-metadata:s:a:{i}', f'language={lang}'])
        for i, lang in enumerate(source_langs['subtitle']): cmd.extend([f'-metadata:s:s:{i}', f'language={lang}'])
        
        start_idx = len(source_langs['subtitle'])
        for i, sub_path in enumerate(ext_subs):
            match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', sub_path.lower())
            lang = match.group(1) if match else 'und'
            cmd.extend([f'-metadata:s:s:{start_idx + i}', f'language={lang}'])

        cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt', '-y', output_file])
        try: subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
        self.finished_signal.emit(self)

class SublerListWidget(QWidget):
    """Subler pijama stili (zebra deseni)"""
    def paintEvent(self, event):
        painter = QPainter(self)
        row_height = 28 # Biraz daha ferah bir satır aralığı
        color_alt = QColor(243, 246, 250)
        for i in range(0, (self.height() // row_height) + 1):
            if i % 2 == 1:
                painter.fillRect(0, i * row_height, self.width(), row_height, QBrush(color_alt))

class FileWidget(QFrame):
    """Dosya listesindeki her bir satır"""
    def __init__(self, filename):
        super().__init__()
        self.setFixedHeight(28)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0) # Sol ve sağ boşluklar
        layout.setSpacing(10)
        
        self.status_icon = QLabel("⚪") # Bekliyor
        self.status_icon.setFixedWidth(24)
        
        self.name_label = QLabel(filename)
        self.name_label.setStyleSheet("font-size: 13px; color: #111; font-weight: 400;")
        
        self.info_icon = QLabel("ⓘ")
        self.info_icon.setStyleSheet("color: #bbb; font-size: 16px;")

        layout.addWidget(self.status_icon)
        layout.addWidget(self.name_label)
        layout.addStretch()
        layout.addWidget(self.info_icon)

    def set_status(self, mode):
        # Durum simgelerini güncelledik
        icons = {"working": "🟠", "done": "✅", "error": "❌"}
        self.status_icon.setText(icons.get(mode, "⚪"))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Queue")
        self.resize(700, 600)
        self.setAcceptDrops(True)
        
        # --- ANA LAYOUT ---
        main_w = QWidget()
        self.setCentralWidget(main_w)
        layout = QVBoxLayout(main_w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- TOOLBAR (Subler Look - Resim 8'e sadık kalınarak yeniden yazıldı) ---
        toolbar = QFrame()
        toolbar.setFixedHeight(110) # Daha yüksek ve ferah bir toolbar
        toolbar.setStyleSheet("background: #fdfdfd; border-bottom: 1px solid #dcdcdc;")
        t_layout = QHBoxLayout(toolbar)
        t_layout.setContentsMargins(25, 0, 25, 0) # Yan boşluklar
        t_layout.setSpacing(35) # Butonlar arası boşluk
        
        # Subler referans görselindeki gibi büyük butonlar (100x100)
        # Font bazlı ikonlar yerine emoji ikonlarını devleştirdik.
        self.start_btn = self.create_nav_btn("Start", "▶️") 
        self.stop_btn = self.create_nav_btn("Stop", "■") 
        self.stop_btn.setEnabled(False) # Başlangıçta inaktif
        self.settings_btn = self.create_nav_btn("Settings", "⚙️")
        self.add_btn = self.create_nav_btn("Add Item", "➕")
        
        # Butonları hizalama
        t_layout.addStretch() # Sol tarafı boş bırak
        t_layout.addWidget(self.start_btn)
        t_layout.addWidget(self.stop_btn)
        t_layout.addWidget(self.settings_btn)
        t_layout.addWidget(self.add_btn)

        # Butonların eventlerini bağla
        self.add_btn.clicked.connect(self.open_files)
        self.start_btn.clicked.connect(self.start_processing)
        self.stop_btn.clicked.connect(self.stop_processing)

        # --- LIST AREA (Pijama Stili - zebra deseni) ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame) # Kenarlıkları kaldır
        self.container = SublerListWidget()
        self.container.setStyleSheet("background: white;")
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.container)

        # --- FOOTER (Genel İlerleme Barı ve Durum Metni - Resim 7) ---
        footer = QWidget()
        footer.setFixedHeight(50)
        footer.setStyleSheet("background: #fcfcfc; border-top: 1px solid #dcdcdc;")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(20, 0, 20, 0)
        
        self.status_label = QLabel("0 items in queue.")
        self.status_label.setStyleSheet("font-size: 13px; color: #444; font-weight: 400;")
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(240) # Resim 7'deki gibi sağda duran bar
        self.progress_bar.setFrameShape(QFrame.Shape.NoFrame)
        self.progress_bar.setTextVisible(False) # Yüzdeyi gizle
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background: #e0e0e0; border-radius: 4px; border: none; }
            QProgressBar::chunk { background: #007aff; border-radius: 4px; }
        """)

        f_layout.addWidget(self.status_label)
        f_layout.addStretch()
        f_layout.addWidget(self.progress_bar)

        # Tüm bileşenleri ana layouta ekle
        layout.addWidget(toolbar)
        layout.addWidget(self.scroll)
        layout.addWidget(footer)

        # Değişkenler
        self.queue = []
        self.threads = []
        self.total_tasks = 0
        self.is_stopped = False

    def create_nav_btn(self, text, icon_char):
        """Subler stili dev ikonlu buton"""
        btn = QPushButton()
        btn.setFixedSize(100, 100) # Devasa buton boyutu
        # Subler stili: İkon üstte büyük, metin altta küçük dikey yerleşim
        btn.setText(f"{icon_char}\n\n{text}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton { 
                border: none; 
                font-size: 14px; /* Yazı boyutu büyütüldü */
                color: #333; 
                background: transparent; 
                font-weight: 600;
                padding-top: 10px;
            }
            QPushButton:hover { background-color: #F2F2F2; border-radius: 20px; color: #000; }
            QPushButton:disabled { color: #aaa; background: transparent; }
        """)
        # Emojiyi (ikonu) büyütmek için font ayarı
        font = QFont()
        font.setPointSize(40) # Devasa emoji boyutu
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
        self.is_stopped = False
        self.update_toolbar_state()

    def start_processing(self):
        if not self.queue: return
        self.is_stopped = False
        self.update_toolbar_state()
        self.process_next()

    def stop_processing(self):
        self.is_stopped = True
        self.update_toolbar_state()
        self.status_label.setText("Stopped.")
        # Çalışan threadleri durdurma isteği gönder
        for t in self.threads:
            t.stop()

    def update_toolbar_state(self):
        """Start/Stop butonlarının durumunu güncelle"""
        if self.is_stopped:
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
        else:
            if self.queue: # Kuyruk varsa
                self.start_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
            else: # Kuyruk boşsa
                self.start_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)

    def process_next(self):
        if not self.queue or self.is_stopped:
            if not self.is_stopped:
                self.status_label.setText("Completed.")
                self.progress_bar.setValue(100)
            self.update_toolbar_state()
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
        if thread in self.threads:
            self.threads.remove(thread)
        self.process_next()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]
        self.add_to_queue(files)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # macOS standardı için stile dokunmuyoruz
    app.setStyle("macintosh")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

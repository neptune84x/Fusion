import sys, os, subprocess, json, glob, re, shutil
try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                                 QWidget, QLabel, QProgressBar, QScrollArea, 
                                 QFrame, QPushButton, QFileDialog, QMenu, QMessageBox)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QPoint
    from PyQt6.QtGui import QPainter, QColor, QBrush, QAction, QKeySequence
except ImportError:
    sys.exit(1)

class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)
    
    def __init__(self, input_file, widget, load_external=True, output_format="mkv"):
        super().__init__()
        self.input_file = input_file
        self.widget = widget
        self.load_external = load_external
        self.output_format = output_format

    def get_bin(self, name):
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, "internal", name)
        return name

    def run(self):
        ffmpeg = self.get_bin('ffmpeg')
        ffprobe = self.get_bin('ffprobe')
        mp4box = self.get_bin('mp4box')
        
        base_path = os.path.splitext(self.input_file)[0]
        temp_dir = base_path + ".fusiontemp"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        output_ext = "mp4" if self.output_format == "mp4_vtt" else "mkv"
        output_file = f"{base_path}_Fusion.{output_ext}"
        
        # Bölüm (Chapter) bilgilerini çıkar
        try:
            probe_cmd = [ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_chapters', self.input_file]
            info = json.loads(subprocess.check_output(probe_cmd))
            chapters = info.get('chapters', [])
        except: chapters = []
        
        chap_file = os.path.join(temp_dir, 'chapters.txt')
        if chapters:
            with open(chap_file, 'w', encoding='utf-8') as f:
                for i, c in enumerate(chapters):
                    t = float(c.get('start_time', 0))
                    title = c.get('tags', {}).get('title', f"Chapter {i+1}")
                    f.write(f"{int(t//3600):02d}:{int((t%3600)//60):02d}:{t%60:06.3f} {title}\n")

        if self.output_format == "mp4_vtt":
            # Saf video/ses çıkarımı (HVC1 tag'i ile Apple TV/LG uyumluluğu için)
            temp_mp4 = os.path.join(temp_dir, "pure.mp4")
            subprocess.run([ffmpeg, '-y', '-i', self.input_file, '-map', '0:v:0', '-map', '0:a?', 
                           '-c', 'copy', '-tag:v', 'hvc1', '-sn', '-map_metadata', '-1', temp_mp4])
            
            # MP4Box ile "Tereyağı" kıvamında paketleme (Subler Ayarları)
            box_cmd = [mp4box, "-add", f"{temp_mp4}#video", "-add", f"{temp_mp4}#audio"]
            
            # Altyazıları ekle (Dışarıdan bulursa onları da dahil eder)
            if self.load_external:
                for s in sorted(glob.glob(base_path + "*.srt")):
                    box_cmd.extend(["-add", f"{s}:name= "]) # @GPAC ismini silmek için boşluk
            
            if os.path.exists(chap_file): box_cmd.extend(["-chap", chap_file])
            
            # Final MP4 optimizasyonları
            box_cmd.extend(["-inter", "500", "-tight", "-brand", "mp42:isom", "-ab", "mp42", "-ipod", "-new", output_file])
            subprocess.run(box_cmd)
        else:
            # MKV Modu
            cmd = [ffmpeg, '-y', '-i', self.input_file, '-c', 'copy', '-map_metadata', '0', output_file]
            subprocess.run(cmd)

        if os.path.exists(temp_dir): shutil.rmtree(temp_dir, ignore_errors=True)
        self.finished_signal.emit(self)

class FileWidget(QFrame):
    def __init__(self, filename, parent_list):
        super().__init__(); self.status = "waiting"; self.setFixedHeight(30); self.is_selected = False
        self.layout = QHBoxLayout(self); self.layout.setContentsMargins(15,0,15,0)
        self.status_icon = QLabel("○"); self.name_label = QLabel(filename)
        self.layout.addWidget(self.status_icon); self.layout.addWidget(self.name_label); self.layout.addStretch()
        self.setStyleSheet("background: transparent;")
    def set_status(self, mode):
        self.status = mode
        self.status_icon.setText("●" if mode=="working" else "✓" if mode=="done" else "○")
        self.status_icon.setStyleSheet(f"color: {'#ff9500' if mode=='working' else '#34c759' if mode=='done' else '#8e8e93'}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Fusion"); self.resize(600, 450); self.setAcceptDrops(True)
        self.items = []; self.load_external_subs = True; self.output_format = "mp4_vtt"
        
        main_layout = QVBoxLayout()
        self.scroll = QScrollArea(); self.content = QWidget(); self.container = QVBoxLayout(self.content)
        self.container.setAlignment(Qt.AlignmentFlag.AlignTop); self.scroll.setWidget(self.content); self.scroll.setWidgetResizable(True)
        
        btn_lay = QHBoxLayout()
        self.add_btn = QPushButton("Add Files"); self.start_btn = QPushButton("Start Fusion")
        btn_lay.addWidget(self.add_btn); btn_lay.addWidget(self.start_btn)
        
        main_layout.addLayout(btn_lay); main_layout.addWidget(self.scroll)
        cw = QWidget(); cw.setLayout(main_layout); self.setCentralWidget(cw)
        
        self.add_btn.clicked.connect(self.open_files); self.start_btn.clicked.connect(self.start_processing)

    def open_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Select Videos"); self.add_to_list(fs)
    def add_to_list(self, paths):
        for p in paths:
            w = FileWidget(os.path.basename(p), self); w.full_path = p
            self.container.addWidget(w); self.items.append(w)
    def dragEnterEvent(self, e): e.accept() if e.mimeData().hasUrls() else e.ignore()
    def dropEvent(self, e): self.add_to_list([u.toLocalFile() for u in e.mimeData().urls()])
    
    def start_processing(self):
        self.queue = [i for i in self.items if i.status == "waiting"]
        if self.queue: self.next()
    def next(self):
        if not self.queue: return
        item = self.queue.pop(0); item.set_status("working")
        self.t = ConversionThread(item.full_path, item, self.load_external_subs, self.output_format)
        self.t.finished_signal.connect(lambda: [item.set_status("done"), self.next()])
        self.t.start()

if __name__ == "__main__":
    app = QApplication(sys.argv); w = MainWindow(); w.show(); sys.exit(app.exec())

import sys, os, subprocess, json, glob, shutil
try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                                 QWidget, QLabel, QPushButton, QFileDialog, QFrame, QScrollArea)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
except ImportError:
    sys.exit(1)

class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)
    
    def __init__(self, input_file, widget, output_format="mp4"):
        super().__init__()
        self.input_file = input_file
        self.widget = widget
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
        os.makedirs(temp_dir, exist_ok=True)
        
        output_file = f"{base_path}_Fusion.mp4"
        
        # Bölüm bilgilerini (Chapters) FFprobe ile al
        chap_file = os.path.join(temp_dir, 'chapters.txt')
        try:
            cmd = [ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_chapters', self.input_file]
            data = json.loads(subprocess.check_output(cmd))
            if data.get('chapters'):
                with open(chap_file, 'w', encoding='utf-8') as f:
                    for i, c in enumerate(data['chapters']):
                        t = float(c['start_time'])
                        title = c.get('tags', {}).get('title', f"Chapter {i+1}")
                        f.write(f"{int(t//3600):02d}:{int((t%3600)//60):02d}:{t%60:06.3f} {title}\n")
        except: pass

        # Geçici video çıkarma (HVC1 uyumluluğu ile)
        temp_mp4 = os.path.join(temp_dir, "video_only.mp4")
        subprocess.run([ffmpeg, '-y', '-i', self.input_file, '-map', '0:v:0', '-map', '0:a?', 
                       '-c', 'copy', '-tag:v', 'hvc1', '-sn', '-map_metadata', '-1', temp_mp4])
        
        # MP4Box 2.4 ile Paketleme ve Optimizasyon
        box_cmd = [mp4box, "-add", f"{temp_mp4}#video", "-add", f"{temp_mp4}#audio"]
        
        # Altyazıları ekle
        for s in sorted(glob.glob(base_path + "*.srt")):
            box_cmd.extend(["-add", f"{s}:name="])
            
        if os.path.exists(chap_file):
            box_cmd.extend(["-chap", chap_file])
            
        # Subler benzeri optimizasyon ayarları
        box_cmd.extend(["-inter", "500", "-tight", "-brand", "mp42:isom", "-new", output_file])
        subprocess.run(box_cmd)

        shutil.rmtree(temp_dir, ignore_errors=True)
        self.finished_signal.emit(self)

class FileWidget(QFrame):
    def __init__(self, filename):
        super().__init__(); self.status = "waiting"; self.setFixedHeight(35)
        layout = QHBoxLayout(self); self.lbl = QLabel(filename); layout.addWidget(self.lbl)
    def set_status(self, mode):
        self.status = mode
        self.lbl.setStyleSheet(f"color: {'#ff9500' if mode=='working' else '#34c759' if mode=='done' else 'white'}")

class FusionApp(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Fusion"); self.resize(500, 400); self.items = []
        layout = QVBoxLayout(); self.scroll = QScrollArea(); self.cont = QWidget()
        self.cont_lay = QVBoxLayout(self.cont); self.scroll.setWidget(self.cont); self.scroll.setWidgetResizable(True)
        
        btns = QHBoxLayout(); self.add_btn = QPushButton("Dosya Ekle"); self.run_btn = QPushButton("Başlat")
        btns.addWidget(self.add_btn); btns.addWidget(self.run_btn)
        
        layout.addLayout(btns); layout.addWidget(self.scroll)
        cw = QWidget(); cw.setLayout(layout); self.setCentralWidget(cw)
        
        self.add_btn.clicked.connect(self.add_files); self.run_btn.clicked.connect(self.process)

    def add_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Videoları Seç"); [self.add_one(f) for f in fs]
    def add_one(self, path):
        w = FileWidget(os.path.basename(path)); w.path = path
        self.cont_lay.addWidget(w); self.items.append(w)
    def process(self):
        queue = [i for i in self.items if i.status == "waiting"]
        if queue:
            item = queue[0]; item.set_status("working")
            self.t = ConversionThread(item.path, item)
            self.t.finished_signal.connect(lambda: [item.set_status("done"), self.process()])
            self.t.start()

if __name__ == "__main__":
    app = QApplication(sys.argv); ex = FusionApp(); ex.show(); sys.exit(app.exec())

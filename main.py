import sys, os, subprocess, json, glob, re
try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                                 QWidget, QLabel, QProgressBar, QScrollArea, 
                                 QFrame, QPushButton, QFileDialog, QMenu)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtGui import QPainter, QColor, QBrush, QAction, QKeySequence
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
        ffprobe_path = os.path.join(sys._MEIPASS, 'ffprobe') if hasattr(sys, '_MEIPASS') else 'ffprobe'
        base_path = os.path.splitext(self.input_file)[0]
        output_file = f"{base_path}_Fusion.mkv"

        # 1. ANALİZ: FFprobe ile dilleri çek
        probe_cmd = [ffprobe_path, '-v', 'quiet', '-print_format', 'json', '-show_streams', self.input_file]
        source_langs = {"audio": [], "subtitle": []}
        try:
            probe_data = json.loads(subprocess.check_output(probe_cmd))
            for s in probe_data.get('streams', []):
                lang = s.get('tags', {}).get('language', 'und')
                if s['codec_type'] == 'audio': source_langs['audio'].append(lang)
                if s['codec_type'] == 'subtitle': source_langs['subtitle'].append(lang)
        except: pass

        # 2. DIŞ ALTYAZILAR
        subs = glob.glob(f"{base_path}*.*")
        ext_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass')) and s != self.input_file]

        # 3. KOMUT İNŞASI
        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in ext_subs: cmd.extend(['-i', sub])
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        for i in range(len(ext_subs)): cmd.extend(['-map', str(i + 1)])

        # TEMİZLİK VE CHAPTER KORUMA
        cmd.extend(['-map_metadata', '-1', '-map_chapters', '0'])

        # 4. METADATA: Dilleri ekle
        for i, lang in enumerate(source_langs['audio']):
            cmd.extend([f'-metadata:s:a:{i}', f'language={lang}'])
        for i, lang in enumerate(source_langs['subtitle']):
            cmd.extend([f'-metadata:s:s:{i}', f'language={lang}'])
        
        start_idx = len(source_langs['subtitle'])
        lang_codes = {"tr": "tur", "en": "eng", "ru": "rus", "jp": "jpn", "de": "ger", "fr": "fra"}
        for i, sub_path in enumerate(ext_subs):
            match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', sub_path.lower())
            lang = match.group(1) if match else 'und'
            final_lang = lang_codes.get(lang, lang)
            cmd.extend([f'-metadata:s:s:{start_idx + i}', f'language={final_lang}'])

        # SRT DÖNÜŞTÜRME VE KAYIT
        cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt', '-y', output_file])
        try: subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
        self.finished_signal.emit(self)

class FileWidget(QFrame):
    def __init__(self, filename, parent_list):
        super().__init__()
        self.parent_list = parent_list
        self.is_selected = False
        self.status = "waiting"
        self.setFixedHeight(30)
        
        self.layout = QHBoxLayout(self); self.layout.setContentsMargins(15, 0, 15, 0)
        self.status_icon = QLabel("○"); self.status_icon.setFixedWidth(20)
        self.status_icon.setStyleSheet("color: #8e8e93; font-size: 14px;")
        
        self.name_label = QLabel(filename)
        self.name_label.setStyleSheet("font-size: 13px; color: #111;")
        
        self.layout.addWidget(self.status_icon); self.layout.addWidget(self.name_label); self.layout.addStretch()

    def set_status(self, mode):
        self.status = mode
        icons = {"working": "●", "done": "✓", "waiting": "○"}
        colors = {"working": "#ff9500", "done": "#34c759", "waiting": "#8e8e93"}
        self.status_icon.setText(icons.get(mode, "○"))
        self.status_icon.setStyleSheet(f"color: {colors.get(mode, '#8e8e93')}; font-size: 14px;")

    def mousePressEvent(self, event):
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier or event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            for item in self.parent_list.items: item.is_selected = False; item.update_style()
        self.is_selected = not self.is_selected
        self.update_style()

    def update_style(self):
        bg = "#007aff" if self.is_selected else "transparent"
        txt = "white" if self.is_selected else "#111"
        self.setStyleSheet(f"background-color: {bg}; border: none;")
        self.name_label.setStyleSheet(f"color: {txt}; font-size: 13px;")

class SublerListWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.items = []
        self.layout = QVBoxLayout(self); self.layout.setContentsMargins(0, 0, 0, 0); self.layout.setSpacing(0); self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def paintEvent(self, event):
        painter = QPainter(self)
        row_h = 30
        for i in range(0, (self.height() // row_h) + 1):
            if i % 2 == 1: painter.fillRect(0, i * row_h, self.width(), row_h, QBrush(QColor(245, 245, 247)))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Queue"); self.resize(650, 500); self.setAcceptDrops(True)
        
        main_v = QVBoxLayout(); main_v.setContentsMargins(0,0,0,0); main_v.setSpacing(0)
        
        # Toolbar (Tek Parça Simgeler)
        toolbar = QWidget(); toolbar.setFixedHeight(80); toolbar.setStyleSheet("background: white; border-bottom: 1px solid #d1d1d6;")
        t_lay = QHBoxLayout(toolbar); t_lay.setContentsMargins(20, 5, 20, 5); t_lay.setSpacing(15)
        
        self.start_btn = self.create_nav_btn("▶", "Start")
        self.add_btn = self.create_nav_btn("＋", "Add Item")
        t_lay.addStretch(); t_lay.addWidget(self.start_btn); t_lay.addWidget(self.add_btn)

        # List Area
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = SublerListWidget(); self.scroll.setWidget(self.container)

        # Footer
        footer = QWidget(); footer.setFixedHeight(40); footer.setStyleSheet("background: white; border-top: 1px solid #d1d1d6;")
        f_lay = QHBoxLayout(footer); f_lay.setContentsMargins(20, 0, 20, 0)
        self.st_lbl = QLabel("0 items in queue."); self.pb = QProgressBar()
        self.pb.setFixedWidth(180); self.pb.setFixedHeight(6); self.pb.setTextVisible(False)
        self.pb.setStyleSheet("QProgressBar{background:#eee;border-radius:3px;border:none;} QProgressBar::chunk{background:#007aff;}")
        f_lay.addWidget(self.st_lbl); f_lay.addStretch(); f_lay.addWidget(self.pb)

        main_v.addWidget(toolbar); main_v.addWidget(self.scroll); main_v.addWidget(footer)
        cw = QWidget(); cw.setLayout(main_v); self.setCentralWidget(cw)

        # Events
        self.add_btn.clicked.connect(self.open_files); self.start_btn.clicked.connect(self.start_processing)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)
        
        # Delete Shortcut
        del_act = QAction(self); del_act.setShortcut(QKeySequence("Backspace")); del_act.triggered.connect(self.remove_selected); self.addAction(del_act)

        self.threads = []; self.active_queue = []

    def create_nav_btn(self, icon, text):
        btn = QPushButton()
        btn.setFixedSize(60, 65)
        btn.setStyleSheet("QPushButton{border:none; background:transparent; border-radius:8px;} QPushButton:hover{background:#f0f0f0;}")
        l = QVBoxLayout(btn); l.setContentsMargins(0,5,0,5); l.setSpacing(0)
        ic = QLabel(icon); ic.setAlignment(Qt.AlignmentFlag.AlignCenter); ic.setStyleSheet("font-size: 24px; color: #333; border:none;")
        tx = QLabel(text); tx.setAlignment(Qt.AlignmentFlag.AlignCenter); tx.setStyleSheet("font-size: 11px; color: #666; border:none;")
        ic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        tx.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        l.addWidget(ic); l.addWidget(tx)
        return btn

    def show_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu{background:white; border:1px solid #ccc;} QMenu::item:selected{background:#007aff; color:white;}")
        rem = menu.addAction("Remove Selected")
        rem.triggered.connect(self.remove_selected)
        menu.exec(self.mapToGlobal(pos))

    def open_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Add Videos")
        if fs: self.add_to_list(fs)

    def add_to_list(self, paths):
        for p in paths:
            w = FileWidget(os.path.basename(p), self.container)
            w.full_path = p
            self.container.layout.addWidget(w); self.container.items.append(w)
        self.st_lbl.setText(f"{len(self.container.items)} items in queue.")

    def remove_selected(self):
        for i in [x for x in self.container.items if x.is_selected]:
            self.container.items.remove(i); i.setParent(None)
        self.st_lbl.setText(f"{len(self.container.items)} items in queue.")

    def start_processing(self):
        self.active_queue = [i for i in self.container.items if i.status == "waiting"]
        if not self.active_queue: return
        self.process_next()

    def process_next(self):
        if not self.active_queue: 
            self.st_lbl.setText("Completed."); return
        item = self.active_queue.pop(0)
        item.set_status("working")
        t = ConversionThread(item.full_path, item)
        t.finished_signal.connect(self.on_done)
        self.threads.append(t); t.start()

    def on_done(self, t):
        t.widget.set_status("done")
        total = len(self.container.items)
        done = len([i for i in self.container.items if i.status == "done"])
        self.pb.setValue(int((done / total) * 100))
        self.process_next()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()
    def dropEvent(self, e):
        self.add_to_list([u.toLocalFile() for u in e.mimeData().urls()])

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("macos"); w = MainWindow(); w.show(); sys.exit(app.exec())

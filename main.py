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
    def __init__(self, input_file, widget, load_external=True):
        super().__init__()
        self.input_file = input_file
        self.widget = widget
        self.load_external = load_external

    def clean_subtitle_text(self, text):
        """
        Nihai İtalik Koruma Sistemi.
        """
        # 1. TÜM İtalik varyasyonlarını maskele (FFmpeg'in silmemesi için)
        text = re.sub(r'\{\\i1\}|\\i1|\\i(?![0-9a-zA-Z])|<i\s*>|<I\s*>', '[[F_ITA_S]]', text)
        text = re.sub(r'\{\\i0\}|\\i0|<\s*/i\s*>|<\s*/I\s*>', '[[F_ITA_E]]', text)
        
        # 2. Bold (Kalın) kodlarını SİL
        text = re.sub(r'\{\\b[0-9]+\}|\\b[0-9]+|<\s*b\s*>|<\s*/b\s*>|\[b\]|\[/b\]', '', text, flags=re.IGNORECASE)
        
        # 3. Kalan TÜM süslü parantezli stil ve renk kodlarını temizle ({...})
        text = re.sub(r'\{[^\}]*\}', '', text)
        
        # 4. Diğer tüm HTML etiketlerini temizle
        text = re.sub(r'<[^>]*>', '', text)
        
        # 5. Maskelenmiş italikleri standart SRT <i> etiketine geri çevir
        text = text.replace('[[F_ITA_S]]', '<i>').replace('[[F_ITA_E]]', '</i>')
        
        # 6. Gereksiz karakter temizliği
        text = text.replace('**', '').replace('__', '')
        text = re.sub(r' +', ' ', text)
        
        return text.strip()

    def process_file_cleaning(self, file_path):
        try:
            if not os.path.exists(file_path): return
            with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                content = f.read()
            cleaned = self.clean_subtitle_text(content)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(cleaned)
        except: pass

    def run(self):
        ffmpeg = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'
        ffprobe = os.path.join(sys._MEIPASS, 'ffprobe') if hasattr(sys, '_MEIPASS') else 'ffprobe'
        
        base_path = os.path.splitext(self.input_file)[0]
        temp_dir_path = base_path + ".fusiontemp"
        
        if os.path.exists(temp_dir_path): shutil.rmtree(temp_dir_path)
        os.makedirs(temp_dir_path, exist_ok=True)
        
        try:
            ascript = f'tell application "Finder" to set extension hidden of POSIX file "{temp_dir_path}" to true'
            subprocess.run(['osascript', '-e', ascript], stderr=subprocess.DEVNULL)
        except: pass

        output_file = base_path + "_Fusion.mkv"

        try:
            probe_cmd = [ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_streams', self.input_file]
            info = json.loads(subprocess.check_output(probe_cmd))
        except: info = {}
        
        internal_subs = []
        for s in info.get('streams', []):
            if s.get('codec_type') == 'subtitle':
                lang = s.get('tags', {}).get('language', 'und')
                internal_subs.append({'index': s['index'], 'lang': lang})

        cleaned_list = []
        for i, sub in enumerate(internal_subs):
            sub_file = f"int_{i}.srt"
            temp_sub_path = os.path.join(temp_dir_path, sub_file)
            # İtalik etiketlerini maskelenmiş halde korumak için FFmpeg'i özel flag ile çalıştırıyoruz
            subprocess.run([ffmpeg, '-y', '-i', self.input_file, '-map', f"0:{sub['index']}", "-c:s", "srt", temp_sub_path], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.process_file_cleaning(temp_sub_path)
            cleaned_list.append({'path': temp_sub_path, 'lang': sub['lang']})

        if self.load_external:
            for f in glob.glob(base_path + "*.*"):
                if f.lower().endswith(('.srt', '.ass')) and f != self.input_file:
                    self.process_file_cleaning(f)
                    match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', f.lower())
                    lang = match.group(1) if match else 'und'
                    cleaned_list.append({'path': f, 'lang': lang})

        # MUXING: Chapters ve Metadata Koruma
        cmd = [ffmpeg, '-i', self.input_file]
        for c in cleaned_list: cmd.extend(['-i', c['path']])
        cmd.extend(['-map', '0:v', '-map', '0:a?'])
        
        lang_map = {"tr": "tur", "en": "eng", "ru": "rus", "jp": "jpn", "de": "ger", "fr": "fra", "es": "spa", "it": "ita"}
        for i, c in enumerate(cleaned_list):
            cmd.extend(['-map', str(i + 1)])
            l_code = lang_map.get(c['lang'], c['lang'])
            cmd.extend([f"-metadata:s:s:{i}", f"language={l_code}", f"-metadata:s:s:{i}", "title="])

        cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt', 
                    '-map_metadata', '-1', '-map_chapters', '0', '-y', output_file])
        
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(temp_dir_path, ignore_errors=True)
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
        self.name_label = QLabel(filename)
        self.layout.addWidget(self.status_icon); self.layout.addWidget(self.name_label); self.layout.addStretch()
        self.update_style()

    def set_status(self, mode):
        self.status = mode
        icons = {"working": "●", "done": "✓", "waiting": "○"}
        colors = {"working": "#ff9500", "done": "#34c759", "waiting": "#8e8e93"}
        self.status_icon.setText(icons.get(mode, "○"))
        self.status_icon.setStyleSheet(f"color: {colors.get(mode, '#8e8e93')}; font-size: 14px;")

    def update_style(self):
        bg = "#007aff" if self.is_selected else "transparent"
        txt = "white" if self.is_selected else "#111"
        self.setStyleSheet(f"background-color: {bg}; border-radius: 4px;")
        self.name_label.setStyleSheet(f"color: {txt}; font-size: 13px;")

class SublerListWidget(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.items = []
        self.selection_start = None
        self.selection_rect = QRect()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.layout = QVBoxLayout(self); self.layout.setContentsMargins(5, 5, 5, 5); self.layout.setSpacing(2); self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def paintEvent(self, event):
        painter = QPainter(self)
        row_h = 30
        for i in range(0, (self.height() // row_h) + 1):
            if i % 2 == 1: painter.fillRect(0, i * row_h, self.width(), row_h, QBrush(QColor(245, 245, 247)))
        if not self.selection_rect.isNull():
            painter.setPen(QColor(0, 122, 255, 150))
            painter.setBrush(QColor(0, 122, 255, 50))
            painter.drawRect(self.selection_rect)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selection_start = event.pos()
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                for item in self.items: item.is_selected = False; item.update_style()
            self.update()

    def mouseMoveEvent(self, event):
        if self.selection_start:
            self.selection_rect = QRect(self.selection_start, event.pos()).normalized()
            for item in self.items:
                item.is_selected = self.selection_rect.intersects(item.geometry())
                item.update_style()
            self.update()

    def mouseReleaseEvent(self, event):
        self.selection_start = None
        self.selection_rect = QRect(); self.update()

    def show_context_menu(self, pos):
        menu = QMenu(self)
        act_remove_sel = QAction("Remove selected", self)
        act_remove_sel.setEnabled(any(i.is_selected for i in self.items))
        act_remove_sel.triggered.connect(self.main_window.remove_selected)
        act_clear_comp = QAction("Clear completed items", self)
        act_clear_comp.setEnabled(any(i.status == "done" for i in self.items))
        act_clear_comp.triggered.connect(self.main_window.remove_completed)
        menu.addAction(act_remove_sel); menu.addAction(act_clear_comp)
        menu.exec(self.mapToGlobal(pos))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion"); self.resize(700, 550); self.setAcceptDrops(True)
        self.load_external_subs = True
        main_v = QVBoxLayout(); main_v.setContentsMargins(0,0,0,0); main_v.setSpacing(0)
        toolbar = QWidget(); toolbar.setFixedHeight(75); toolbar.setStyleSheet("background: white; border: none;")
        t_lay = QHBoxLayout(toolbar); t_lay.setContentsMargins(30, 0, 30, 0); t_lay.setSpacing(5)
        self.start_btn = self.create_nav_btn("▶", "Start")
        self.settings_btn = self.create_nav_btn("⚙", "Settings")
        self.add_btn = self.create_nav_btn("＋", "Add Item")
        t_lay.addStretch(); t_lay.addWidget(self.start_btn); t_lay.addWidget(self.settings_btn); t_lay.addWidget(self.add_btn)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = SublerListWidget(self); self.scroll.setWidget(self.container)
        footer = QWidget(); footer.setFixedHeight(45); footer.setStyleSheet("background: #fbfbfd; border-top: 1px solid #d1d1d6;")
        f_lay = QHBoxLayout(footer); f_lay.setContentsMargins(20, 0, 20, 0)
        self.st_lbl = QLabel("0 items in queue."); self.pb = QProgressBar()
        self.pb.setFixedWidth(200); self.pb.setFixedHeight(6); self.pb.setTextVisible(False)
        self.pb.setStyleSheet("QProgressBar{background:#eee;border-radius:3px;border:none;} QProgressBar::chunk{background:#007aff; border-radius:3px;}")
        f_lay.addWidget(self.st_lbl); f_lay.addStretch(); f_lay.addWidget(self.pb)
        main_v.addWidget(toolbar); main_v.addWidget(self.scroll); main_v.addWidget(footer)
        cw = QWidget(); cw.setLayout(main_v); self.setCentralWidget(cw)
        self.setup_menu()
        self.add_btn.clicked.connect(self.open_files)
        self.start_btn.clicked.connect(self.start_processing)
        self.settings_btn.clicked.connect(self.show_settings_menu)
        self.threads = []; self.active_queue = []

    def create_nav_btn(self, icon, text):
        btn = QPushButton(); btn.setFixedSize(60, 65); btn.setStyleSheet("QPushButton{border:none; background:transparent;} QPushButton:hover{background:#f5f5f7; border-radius:10px;}")
        l = QVBoxLayout(btn); l.setContentsMargins(0,0,0,0); l.setSpacing(0)
        ic = QLabel(icon); ic.setAlignment(Qt.AlignmentFlag.AlignCenter); ic.setStyleSheet("font-size: 26px; color: #1d1d1f;")
        tx = QLabel(text); tx.setAlignment(Qt.AlignmentFlag.AlignCenter); tx.setStyleSheet("font-size: 10px; color: #1d1d1f; font-weight: 500;")
        l.addWidget(ic); l.addWidget(tx); return btn

    def setup_menu(self):
        mb = self.menuBar()
        am = mb.addMenu("Fusion")
        a_about = QAction("About Fusion", self); a_about.triggered.connect(self.show_about); am.addAction(a_about)
        a_quit = QAction("Quit", self); a_quit.setShortcut(QKeySequence("Ctrl+Q")); a_quit.triggered.connect(self.close); am.addAction(a_quit)
        fm = mb.addMenu("File")
        a_add = QAction("Add Item...", self); a_add.setShortcut(QKeySequence("Ctrl+O")); a_add.triggered.connect(self.open_files); fm.addAction(a_add)
        em = mb.addMenu("Edit")
        a_rem = QAction("Remove Selected", self); a_rem.setShortcut(QKeySequence("Backspace")); a_rem.triggered.connect(self.remove_selected); em.addAction(a_rem)
        a_clear = QAction("Clear Completed Items", self); a_clear.triggered.connect(self.remove_completed); em.addAction(a_clear)

    def remove_completed(self):
        to_remove = [i for i in self.container.items if i.status == "done"]
        for i in to_remove: self.container.items.remove(i); i.setParent(None)
        self.st_lbl.setText(f"{len(self.container.items)} items in queue.")

    def remove_selected(self):
        to_remove = [i for i in self.container.items if i.is_selected]
        for i in to_remove: self.container.items.remove(i); i.setParent(None)
        self.st_lbl.setText(f"{len(self.container.items)} items in queue.")

    def show_about(self): QMessageBox.about(self, "About Fusion", "Fusion v1.0")
    def show_settings_menu(self):
        menu = QMenu(self)
        act = QAction("Load External Subtitles", self); act.setCheckable(True); act.setChecked(self.load_external_subs)
        act.triggered.connect(lambda s: setattr(self, 'load_external_subs', s))
        menu.addAction(act); menu.exec(self.settings_btn.mapToGlobal(QPoint(0, self.settings_btn.height())))

    def open_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Add Videos")
        if fs: self.add_to_list(fs)

    def add_to_list(self, paths):
        for p in paths:
            w = FileWidget(os.path.basename(p), self.container); w.full_path = p
            self.container.layout.addWidget(w); self.container.items.append(w)
        self.st_lbl.setText(f"{len(self.container.items)} items in queue.")

    def start_processing(self):
        self.active_queue = [i for i in self.container.items if i.status == "waiting"]
        if self.active_queue: self.process_next()

    def process_next(self):
        if not self.active_queue: self.st_lbl.setText("Completed."); return
        item = self.active_queue.pop(0); item.set_status("working")
        t = ConversionThread(item.full_path, item, self.load_external_subs)
        t.finished_signal.connect(self.on_done); self.threads.append(t); t.start()

    def on_done(self, t):
        t.widget.set_status("done")
        done = len([i for i in self.container.items if i.status == "done"])
        total = len(self.container.items)
        if total > 0: self.pb.setValue(int((done / total) * 100))
        self.process_next()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()
    def dropEvent(self, e):
        self.add_to_list([u.toLocalFile() for u in e.mimeData().urls()])

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("macos"); w = MainWindow(); w.show(); sys.exit(app.exec())

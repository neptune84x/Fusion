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

    def clean_and_force_srt_italics(self, text):
        if not text: return ""
        text = re.sub(r'\{\\i1\}|\\i1|<i>|<I>', '', text)
        text = re.sub(r'\{\\i0\}|\\i0|</i>|</I>', '', text)
        text = re.sub(r'\{[^\}]*\}', '', text)
        return f"<i>{text.strip()}</i>"

    def process_ass_to_srt_with_italics(self, ass_path, srt_output_path):
        try:
            with open(ass_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                lines = f.readlines()
            srt_content = []; counter = 1
            for line in lines:
                if line.startswith("Dialogue:"):
                    parts = line.split(',', 9)
                    if len(parts) >= 10:
                        start_time = parts[1].replace('.', ',') + "0"
                        end_time = parts[2].replace('.', ',') + "0"
                        style = parts[3]
                        text = parts[9].strip()
                        if "italic" in style.lower() or "{\\i1}" in text:
                            text = self.clean_and_force_srt_italics(text)
                        else:
                            text = re.sub(r'\{[^\}]*\}', '', text).strip()
                        if text:
                            srt_content.append(f"{counter}\n0{start_time[:-1]} --> 0{end_time[:-1]}\n{text}\n\n")
                            counter += 1
            with open(srt_output_path, 'w', encoding='utf-8-sig') as f:
                f.writelines(srt_content)
        except:
            ffmpeg = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'
            subprocess.run([ffmpeg, '-y', '-i', ass_path, srt_output_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def run(self):
        ffmpeg = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'
        ffprobe = os.path.join(sys._MEIPASS, 'ffprobe') if hasattr(sys, '_MEIPASS') else 'ffprobe'
        base_path = os.path.splitext(self.input_file)[0]
        temp_dir_path = base_path + ".fusiontemp"
        if os.path.exists(temp_dir_path): shutil.rmtree(temp_dir_path)
        os.makedirs(temp_dir_path, exist_ok=True)
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
            temp_sub_path = os.path.join(temp_dir_path, f"int_{i}.srt")
            subprocess.run([ffmpeg, '-y', '-i', self.input_file, '-map', f"0:{sub['index']}", '-f', 'srt', temp_sub_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cleaned_list.append({'path': temp_sub_path, 'lang': sub['lang']})
        if self.load_external:
            for f in glob.glob(base_path + "*.*"):
                ext_check = f.lower()
                if (ext_check.endswith('.srt') or ext_check.endswith('.ass')) and f != self.input_file:
                    temp_ext_path = os.path.join(temp_dir_path, f"ext_{len(cleaned_list)}.srt")
                    if ext_check.endswith('.ass'): self.process_ass_to_srt_with_italics(f, temp_ext_path)
                    else: shutil.copy2(f, temp_ext_path)
                    match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', ext_check)
                    cleaned_list.append({'path': temp_ext_path, 'lang': match.group(1) if match else 'und'})
        cmd = [ffmpeg, '-y', '-i', self.input_file]
        for c in cleaned_list: cmd.extend(['-i', c['path']])
        cmd.extend(['-map', '0:v', '-map', '0:a?'])
        l_map = {"tr":"tur","en":"eng","ru":"rus","jp":"jpn","de":"ger","fr":"fra","es":"spa","it":"ita"}
        for i, c in enumerate(cleaned_list):
            cmd.extend(['-map', str(i + 1)])
            cmd.extend([f"-c:s:{i}", "subrip", f"-metadata:s:s:{i}", f"language={l_map.get(c['lang'], c['lang'])}", f"-metadata:s:s:{i}", "title="])
        cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-map_metadata', '-1', '-map_chapters', '0', output_file])
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(temp_dir_path): shutil.rmtree(temp_dir_path, ignore_errors=True)
        self.finished_signal.emit(self)

class FileWidget(QFrame):
    def __init__(self, filename, parent_list):
        super().__init__()
        self.parent_list = parent_list; self.is_selected = False; self.status = "waiting"; self.setFixedHeight(30)
        self.layout = QHBoxLayout(self); self.layout.setContentsMargins(15, 0, 15, 0); self.status_icon = QLabel("○"); self.status_icon.setFixedWidth(20)
        self.name_label = QLabel(filename); self.layout.addWidget(self.status_icon); self.layout.addWidget(self.name_label); self.layout.addStretch(); self.update_style()
    def set_status(self, mode):
        self.status = mode; icons = {"working": "●", "done": "✓", "waiting": "○"}; colors = {"working": "#ff9500", "done": "#34c759", "waiting": "#8e8e93"}
        self.status_icon.setText(icons.get(mode, "○")); self.status_icon.setStyleSheet(f"color: {colors.get(mode, '#8e8e93')}; font-size: 14px;")
    def update_style(self):
        bg = "#007aff" if self.is_selected else "transparent"; txt = "white" if self.is_selected else "#111"
        self.setStyleSheet(f"background-color: {bg}; border-radius: 4px;"); self.name_label.setStyleSheet(f"color: {txt}; font-size: 13px;")

class SublerListWidget(QWidget):
    def __init__(self, main_window):
        super().__init__(); self.main_window = main_window; self.items = []; self.selection_start = None; self.selection_rect = QRect()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.customContextMenuRequested.connect(self.show_context_menu)
        self.layout = QVBoxLayout(self); self.layout.setContentsMargins(5, 5, 5, 5); self.layout.setSpacing(2); self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    def paintEvent(self, event):
        painter = QPainter(self); row_h = 30
        for i in range(0, (self.height() // row_h) + 1):
            if i % 2 == 1: painter.fillRect(0, i * row_h, self.width(), row_h, QBrush(QColor(245, 245, 247)))
        if not self.selection_rect.isNull():
            painter.setPen(QColor(0, 122, 255, 150)); painter.setBrush(QColor(0, 122, 255, 50)); painter.drawRect(self.selection_rect)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selection_start = event.pos()
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                for item in self.items: item.is_selected = False; item.update_style()
            self.update()
    def mouseMoveEvent(self, event):
        if self.selection_start:
            self.selection_rect = QRect(self.selection_start, event.pos()).normalized()
            for item in self.items: item.is_selected = self.selection_rect.intersects(item.geometry()); item.update_style()
            self.update()
    def mouseReleaseEvent(self, event): self.selection_start = None; self.selection_rect = QRect(); self.update()
    def show_context_menu(self, pos):
        menu = QMenu(self); act_rem = QAction("Remove selected", self); act_rem.setEnabled(any(i.is_selected for i in self.items))
        act_rem.triggered.connect(self.main_window.remove_selected); act_clear = QAction("Clear completed", self)
        act_clear.setEnabled(any(i.status == "done" for i in self.items)); act_clear.triggered.connect(self.main_window.remove_completed)
        menu.addAction(act_rem); menu.addAction(act_clear); menu.exec(self.mapToGlobal(pos))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Fusion"); self.resize(700, 550); self.setAcceptDrops(True); self.load_external_subs = True
        main_v = QVBoxLayout(); main_v.setContentsMargins(0,0,0,0); main_v.setSpacing(0)
        toolbar = QWidget(); toolbar.setFixedHeight(75); toolbar.setStyleSheet("background: white; border: none;")
        t_lay = QHBoxLayout(toolbar); t_lay.setContentsMargins(30, 0, 30, 0); t_lay.setSpacing(5)
        self.start_btn = self.create_nav_btn("▶", "Start"); self.settings_btn = self.create_nav_btn("⚙", "Settings"); self.add_btn = self.create_nav_btn("＋", "Add Item")
        t_lay.addStretch(); t_lay.addWidget(self.start_btn); t_lay.addWidget(self.settings_btn); t_lay.addWidget(self.add_btn)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = SublerListWidget(self); self.scroll.setWidget(self.container)
        footer = QWidget(); footer.setFixedHeight(45); footer.setStyleSheet("background: #fbfbfd; border-top: 1px solid #d1d1d6;")
        f_lay = QHBoxLayout(footer); f_lay.setContentsMargins(20, 0, 20, 0); self.st_lbl = QLabel("0 items."); self.pb = QProgressBar()
        self.pb.setFixedWidth(200); self.pb.setFixedHeight(6); self.pb.setTextVisible(False); self.pb.setStyleSheet("QProgressBar{background:#eee;border-radius:3px;border:none;} QProgressBar::chunk{background:#007aff; border-radius:3px;}")
        f_lay.addWidget(self.st_lbl); f_lay.addStretch(); f_lay.addWidget(self.pb); main_v.addWidget(toolbar); main_v.addWidget(self.scroll); main_v.addWidget(footer)
        cw = QWidget(); cw.setLayout(main_v); self.setCentralWidget(cw); self.setup_menu(); self.add_btn.clicked.connect(self.open_files)
        self.start_btn.clicked.connect(self.start_processing); self.settings_btn.clicked.connect(self.show_settings_menu); self.threads = []; self.active_queue = []
    
    def create_nav_btn(self, icon, text):
        btn = QPushButton(); btn.setFixedSize(60, 65); btn.setStyleSheet("QPushButton{border:none; background:transparent;} QPushButton:hover{background:#f5f5f7; border-radius:10px;}")
        l = QVBoxLayout(btn); l.setContentsMargins(0,0,0,0); l.setSpacing(0); ic = QLabel(icon); ic.setAlignment(Qt.AlignmentFlag.AlignCenter); ic.setStyleSheet("font-size: 26px; color: #1d1d1f;")
        tx = QLabel(text); tx.setAlignment(Qt.AlignmentFlag.AlignCenter); tx.setStyleSheet("font-size: 10px; color: #1d1d1f; font-weight: 500;")
        l.addWidget(ic); l.addWidget(tx); return btn

    def setup_menu(self):
        mb = self.menuBar()
        # Fusion Menüsü
        am = mb.addMenu("Fusion")
        a_about = QAction("About Fusion", self)
        a_about.triggered.connect(self.show_about)
        am.addAction(a_about)
        am.addSeparator()
        a_quit = QAction("Quit", self)
        a_quit.setShortcut(QKeySequence("Ctrl+Q"))
        a_quit.triggered.connect(self.close)
        am.addAction(a_quit)
        
        # File Menüsü
        fm = mb.addMenu("File")
        a_add = QAction("Add Item...", self)
        a_add.setShortcut(QKeySequence("Ctrl+O"))
        a_add.triggered.connect(self.open_files)
        fm.addAction(a_add)
        
        # Edit Menüsü
        em = mb.addMenu("Edit")
        a_rem = QAction("Remove selected", self)
        a_rem.setShortcut(QKeySequence(QKeySequence.StandardKey.Delete))
        a_rem.triggered.connect(self.remove_selected)
        em.addAction(a_rem)
        a_clear = QAction("Clear completed", self)
        a_clear.triggered.connect(self.remove_completed)
        em.addAction(a_clear)

    def show_about(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("About Fusion")
        # Developer kısmına kendi adını veya GitHub kullanıcı adını ekleyebilirsin
        msg.setText("<b>Fusion</b><br>Version: 0.1.0<br>Developer: Your Name<br><br>"
                    "High-performance media optimizer for Apple ecosystems.")
        msg.setInformativeText("Optimized for Infuse, Apple TV, and macOS.")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.exec()

    def remove_completed(self):
        to_rem = [i for i in self.container.items if i.status == "done"]
        for i in to_rem: self.container.items.remove(i); i.setParent(None)
        self.st_lbl.setText(f"{len(self.container.items)} items.")
    def remove_selected(self):
        to_rem = [i for i in self.container.items if i.is_selected]
        for i in to_rem: self.container.items.remove(i); i.setParent(None)
        self.st_lbl.setText(f"{len(self.container.items)} items.")
    def show_settings_menu(self):
        menu = QMenu(self); act = QAction("Load External Subtitles", self); act.setCheckable(True); act.setChecked(self.load_external_subs)
        act.triggered.connect(lambda s: setattr(self, 'load_external_subs', s)); menu.addAction(act); menu.exec(self.settings_btn.mapToGlobal(QPoint(0, self.settings_btn.height())))
    def open_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Add Videos")
        if fs: self.add_to_list(fs)
    def add_to_list(self, paths):
        for p in paths:
            w = FileWidget(os.path.basename(p), self.container); w.full_path = p
            self.container.layout.addWidget(w); self.container.items.append(w)
        self.st_lbl.setText(f"{len(self.container.items)} items.")
    def start_processing(self):
        self.active_queue = [i for i in self.container.items if i.status == "waiting"]
        if self.active_queue: self.process_next()
    def process_next(self):
        if not self.active_queue: self.st_lbl.setText("Completed."); return
        item = self.active_queue.pop(0); item.set_status("working"); t = ConversionThread(item.full_path, item, self.load_external_subs)
        t.finished_signal.connect(self.on_done); self.threads.append(t); t.start()
    def on_done(self, t):
        t.widget.set_status("done"); done = len([i for i in self.container.items if i.status == "done"]); total = len(self.container.items)
        if total > 0: self.pb.setValue(int((done / total) * 100))
        self.process_next()
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()
    def dropEvent(self, e):
        self.add_to_list([u.toLocalFile() for u in e.mimeData().urls()])

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("macos"); w = MainWindow(); w.show(); sys.exit(app.exec())

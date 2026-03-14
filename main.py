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

    def clean_and_force_srt_italics(self, text):
        if not text: return ""
        text = text.replace(r'\N', '\n').replace(r'\\N', '\n')
        text = re.sub(r'\{\\i1\}|\\i1|<i>|<I>', '', text)
        text = re.sub(r'\{\\i0\}|\\i0|</i>|</I>', '', text)
        text = re.sub(r'\{[^\}]*\}', '', text)
        return f"<i>{text.strip()}</i>"

    def convert_to_webvtt(self, srt_path, vtt_path):
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(vtt_path, 'w', encoding='utf-8') as f:
                f.write("WEBVTT\n\n")
                for line in lines:
                    f.write(line.replace(',', '.'))
            return True
        except: return False

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
                        text = parts[9].strip()
                        if "italic" in parts[3].lower() or "{\\i1}" in text:
                            text = self.clean_and_force_srt_italics(text)
                        else:
                            text = text.replace(r'\N', '\n').replace(r'\\N', '\n')
                            text = re.sub(r'\{[^\}]*\}', '', text).strip()
                        if text:
                            srt_content.append(f"{counter}\n0{start_time[:-1]} --> 0{end_time[:-1]}\n{text}\n\n")
                            counter += 1
            with open(srt_output_path, 'w', encoding='utf-8-sig') as f:
                f.writelines(srt_content)
        except:
            ffmpeg = self.get_bin('ffmpeg')
            subprocess.run([ffmpeg, '-y', '-i', ass_path, srt_output_path], capture_output=True)

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
        
        try:
            probe_cmd = [ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_streams', self.input_file]
            info = json.loads(subprocess.check_output(probe_cmd))
        except: info = {}
        
        internal_subs = [s for s in info.get('streams', []) if s.get('codec_type') == 'subtitle']
        l_map = {"tr":"tur","en":"eng","ru":"rus","jp":"jpn","de":"ger","fr":"fra","es":"spa","it":"ita", "pt":"por", "ar":"ara"}
        
        cleaned_list = []
        for i, sub in enumerate(internal_subs):
            lang = sub.get('tags', {}).get('language', 'und')
            temp_srt = os.path.join(temp_dir, f"int_{i}.srt")
            subprocess.run([ffmpeg, '-y', '-i', self.input_file, '-map', f"0:{sub['index']}", '-f', 'srt', temp_srt], capture_output=True)
            final_sub = temp_srt
            if self.output_format == "mp4_vtt":
                temp_vtt = temp_srt.replace('.srt', '.vtt')
                self.convert_to_webvtt(temp_srt, temp_vtt)
                final_sub = temp_vtt
            cleaned_list.append({'path': final_sub, 'lang': l_map.get(lang, lang)})

        if self.load_external:
            for f in sorted(glob.glob(base_path + "*.*")):
                if f.lower().endswith(('.srt', '.ass')) and f != self.input_file:
                    temp_srt = os.path.join(temp_dir, f"ext_{len(cleaned_list)}.srt")
                    if f.lower().endswith('.ass'):
                        self.process_ass_to_srt_with_italics(f, temp_srt)
                    else:
                        shutil.copy2(f, temp_srt)
                    final_sub = temp_srt
                    if self.output_format == "mp4_vtt":
                        temp_vtt = temp_srt.replace('.srt', '.vtt')
                        self.convert_to_webvtt(temp_srt, temp_vtt)
                        final_sub = temp_vtt
                    match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', f.lower())
                    lang = match.group(1) if match else "und"
                    cleaned_list.append({'path': final_sub, 'lang': l_map.get(lang, lang)})

        if self.output_format == "mp4_vtt":
            temp_mp4 = os.path.join(temp_dir, "video_pure.mp4")
            # Hayalet sbtl ve donma yapan eski metadataları tamamen kazıyoruz
            subprocess.run([ffmpeg, '-y', '-i', self.input_file, '-map', '0:v:0', '-map', '0:a?', 
                           '-c', 'copy', '-tag:v', 'hvc1', '-sn', '-map_metadata', '-1', '-map_chapters', '-1', 
                           '-movflags', '+faststart', temp_mp4], capture_output=True)
            
            # MP4Box: -brand mp42 zorlaması ve -inter 500 (Akıcı sarma için)
            box_cmd = [mp4box, "-brand", "mp42", "-ab", "mp42", "-new", "-flat", "-inter", "500"]
            
            # Video ve ses trackleri
            box_cmd.extend(["-add", f"{temp_mp4}#video", "-add", f"{temp_mp4}#audio"])
            
            # Altyazılar (Turkish sonda kalacak şekilde eklenir)
            for i, c in enumerate(cleaned_list):
                is_disabled = ":disable" if i > 0 else ""
                # :tight parametresini her altyazı track'ine ekliyoruz
                box_cmd.extend(["-add", f"{c['path']}:lang={c['lang']}:group=2:name={is_disabled}:tight"])
            
            # -ipod bayrağı Apple cihazlar için final optimizasyonudur
            box_cmd.extend(["-ipod", output_file])
            subprocess.run(box_cmd, capture_output=True)
        else:
            # MKV Modu
            cmd = [ffmpeg, '-y', '-i', self.input_file]
            for c in cleaned_list: cmd.extend(['-i', c['path']])
            cmd.extend(['-map', '0:v:0', '-map', '0:a?'])
            for i, c in enumerate(cleaned_list):
                cmd.extend(['-map', str(i + 1), f"-c:s:{i}", "subrip", f"-metadata:s:s:{i}", f"language={c['lang']}"])
            cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-map_metadata', '-1', '-map_chapters', '0', output_file])
            subprocess.run(cmd, capture_output=True)

        if os.path.exists(temp_dir): shutil.rmtree(temp_dir, ignore_errors=True)
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
        super().__init__(); self.setWindowTitle("Fusion"); self.resize(700, 550); self.setAcceptDrops(True); self.load_external_subs = True; self.output_format = "mkv"
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
        mb = self.menuBar(); am = mb.addMenu("Fusion"); a_about = QAction("About Fusion", self); a_about.triggered.connect(self.show_about); am.addAction(a_about); am.addSeparator()
        a_quit = QAction("Quit", self); a_quit.setShortcut(QKeySequence("Ctrl+Q")); a_quit.triggered.connect(self.close); am.addAction(a_quit)
        fm = mb.addMenu("File"); a_add = QAction("Add Item...", self); a_add.setShortcut(QKeySequence("Ctrl+O")); a_add.triggered.connect(self.open_files); fm.addAction(a_add)
        em = mb.addMenu("Edit"); a_rem = QAction("Remove selected", self); a_rem.setShortcut(QKeySequence(QKeySequence.StandardKey.Delete)); a_rem.triggered.connect(self.remove_selected); em.addAction(a_rem); a_clear = QAction("Clear completed", self); a_clear.triggered.connect(self.remove_completed); em.addAction(a_clear)

    def show_about(self):
        QMessageBox.information(self, "About Fusion", "Fusion v0.2.7\n- Seek Stability (Interleaving 500ms)\n- Apple mp42 Profile Force\n- Clean metadata removal.")

    def show_settings_menu(self):
        menu = QMenu(self)
        act_sub = QAction("Load External Subtitles", self, checkable=True); act_sub.setChecked(self.load_external_subs)
        act_sub.triggered.connect(lambda s: setattr(self, 'load_external_subs', s)); menu.addAction(act_sub); menu.addSeparator()
        fmt_menu = menu.addMenu("Output Format")
        a_mkv = QAction("Matroska (.mkv)", self, checkable=True); a_mkv.setChecked(self.output_format == "mkv")
        a_mp4 = QAction("Apple MP4 (WebVTT)", self, checkable=True); a_mp4.setChecked(self.output_format == "mp4_vtt")
        def set_fmt(f): self.output_format = f; a_mkv.setChecked(f == "mkv"); a_mp4.setChecked(f == "mp4_vtt")
        a_mkv.triggered.connect(lambda: set_fmt("mkv")); a_mp4.triggered.connect(lambda: set_fmt("mp4_vtt"))
        fmt_menu.addAction(a_mkv); fmt_menu.addAction(a_mp4)
        menu.exec(self.settings_btn.mapToGlobal(QPoint(0, self.settings_btn.height())))

    def remove_completed(self):
        to_rem = [i for i in self.container.items if i.status == "done"]
        for i in to_rem: self.container.items.remove(i); i.setParent(None)
        self.st_lbl.setText(f"{len(self.container.items)} items.")
    def remove_selected(self):
        to_rem = [i for i in self.container.items if i.is_selected]
        for i in to_rem: self.container.items.remove(i); i.setParent(None)
        self.st_lbl.setText(f"{len(self.container.items)} items.")
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
        item = self.active_queue.pop(0); item.set_status("working")
        t = ConversionThread(item.full_path, item, self.load_external_subs, self.output_format)
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

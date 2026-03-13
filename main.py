import sys, os, subprocess, json, glob, re
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

    def clean_srt_content(self, srt_path):
        """SRT dosyasındaki italik hariç tüm HTML etiketlerini temizler."""
        try:
            with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            content = content.replace('<i>', '[[i]]').replace('</i>', '[[/i]]')
            content = re.sub(r'<[^>]*>', '', content)
            content = content.replace('[[i]]', '<i>').replace('[[/i]]', '</i>')
            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            print(f"Subtitle cleaning error: {e}")

    def run(self):
        ffmpeg_path = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'
        ffprobe_path = os.path.join(sys._MEIPASS, 'ffprobe') if hasattr(sys, '_MEIPASS') else 'ffprobe'
        base_path = os.path.splitext(self.input_file)[0]
        output_file = f"{base_path}_Fusion.mkv"
        
        probe_cmd = [ffprobe_path, '-v', 'quiet', '-print_format', 'json', '-show_streams', self.input_file]
        source_langs = {"audio": [], "subtitle": []}
        try:
            probe_data = json.loads(subprocess.check_output(probe_cmd))
            for s in probe_data.get('streams', []):
                lang = s.get('tags', {}).get('language', 'und')
                if s['codec_type'] == 'audio': source_langs['audio'].append(lang)
                if s['codec_type'] == 'subtitle': source_langs['subtitle'].append(lang)
        except: pass

        ext_subs = []
        if self.load_external:
            subs = glob.glob(f"{base_path}*.*")
            ext_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass')) and s != self.input_file]
            for s in ext_subs:
                if s.lower().endswith('.srt'): self.clean_srt_content(s)

        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in ext_subs: cmd.extend(['-i', sub])
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        for i in range(len(ext_subs)): cmd.extend(['-map', str(i + 1)])
        cmd.extend(['-map_metadata', '-1', '-map_chapters', '0'])

        lang_codes = {"tr": "tur", "en": "eng", "ru": "rus", "jp": "jpn", "de": "ger", "fr": "fra", "es": "spa", "it": "ita"}
        
        for i, lang in enumerate(source_langs['audio']):
            cmd.extend([f'-metadata:s:a:{i}', f'language={lang}'])
        for i, lang in enumerate(source_langs['subtitle']):
            cmd.extend([f'-metadata:s:s:{i}', f'language={lang}'])
        
        start_idx = len(source_langs['subtitle'])
        for i, sub_path in enumerate(ext_subs):
            match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', sub_path.lower())
            lang = match.group(1) if match else 'und'
            cmd.extend([f'-metadata:s:s:{start_idx + i}', f'language={lang_codes.get(lang, lang)}'])

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
        self.name_label = QLabel(filename)
        self.layout.addWidget(self.status_icon); self.layout.addWidget(self.name_label); self.layout.addStretch()
        self.update_style()

    def set_status(self, mode):
        self.status = mode
        icons = {"working": "●", "done": "✓", "waiting": "○"}
        colors = {"working": "#ff9500", "done": "#34c759", "waiting": "#8e8e93"}
        self.status_icon.setText(icons.get(mode, "○"))
        self.status_icon.setStyleSheet(f"color: {colors.get(mode, '#8e8e93')}; font-size: 14px; border: none;")

    def update_style(self):
        bg = "#007aff" if self.is_selected else "transparent"
        txt = "white" if self.is_selected else "#111"
        self.setStyleSheet(f"background-color: {bg}; border: none; border-radius: 4px;")
        self.name_label.setStyleSheet(f"color: {txt}; font-size: 13px; border: none;")

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
        selected_items = [i for i in self.items if i.is_selected]
        if selected_items:
            rem_sel = QAction("Remove selected", self)
            rem_sel.triggered.connect(self.main_window.remove_selected)
            menu.addAction(rem_sel)
        rem_comp = QAction("Remove completed items", self)
        rem_comp.triggered.connect(self.main_window.remove_completed)
        menu.addAction(rem_comp)
        menu.exec(self.mapToGlobal(pos))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion"); self.resize(700, 550); self.setAcceptDrops(True)
        self.load_external_subs = True
        
        main_v = QVBoxLayout(); main_v.setContentsMargins(0,0,0,0); main_v.setSpacing(0)
        
        # Üst Panel (Toolbar) - Çizgiler kaldırıldı
        toolbar = QWidget(); toolbar.setFixedHeight(95); toolbar.setStyleSheet("background: white; border: none;")
        t_lay = QHBoxLayout(toolbar); t_lay.setContentsMargins(30, 0, 30, 0); t_lay.setSpacing(10)
        
        self.start_btn = self.create_nav_btn("▶", "Start")
        self.settings_btn = self.create_nav_btn("⚙", "Settings")
        self.add_btn = self.create_nav_btn("＋", "Add Item")
        
        t_lay.addStretch(); t_lay.addWidget(self.start_btn); t_lay.addWidget(self.settings_btn); t_lay.addWidget(self.add_btn)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = SublerListWidget(self); self.scroll.setWidget(self.container)

        # Alt Panel (Footer)
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
        # Butonun etrafındaki çizgileri 'border: none' ve 'outline: none' ile siliyoruz
        btn = QPushButton(); btn.setFixedSize(80, 85); btn.setStyleSheet("QPushButton{border:none; outline:none; background:transparent;} QPushButton:hover{background:#f5f5f7; border-radius:12px;}")
        l = QVBoxLayout(btn); l.setContentsMargins(0,0,0,0); l.setSpacing(0)
        ic = QLabel(icon); ic.setAlignment(Qt.AlignmentFlag.AlignCenter); ic.setStyleSheet("font-size: 36px; color: #1d1d1f; border: none; background: none;")
        tx = QLabel(text); tx.setAlignment(Qt.AlignmentFlag.AlignCenter); tx.setStyleSheet("font-size: 11px; color: #1d1d1f; font-weight: 500; border: none; background: none;")
        l.addWidget(ic); l.addWidget(tx); return btn

    def setup_menu(self):
        menubar = self.menuBar()
        app_menu = menubar.addMenu("Fusion")
        about_act = QAction("About Fusion", self); about_act.triggered.connect(self.show_about)
        app_menu.addAction(about_act); app_menu.addSeparator()
        quit_act = QAction("Quit", self); quit_act.setShortcut(QKeySequence("Ctrl+Q")); quit_act.triggered.connect(self.close)
        app_menu.addAction(quit_act)

        file_menu = menubar.addMenu("File")
        add_act = QAction("Add Item...", self); add_act.setShortcut(QKeySequence("Ctrl+O")); add_act.triggered.connect(self.open_files)
        file_menu.addAction(add_act)
        
        edit_menu = menubar.addMenu("Edit")
        rem_sel_act = QAction("Remove Selected", self); rem_sel_act.setShortcut(QKeySequence("Backspace")); rem_sel_act.triggered.connect(self.remove_selected)
        edit_menu.addAction(rem_sel_act)
        rem_comp_act = QAction("Remove Completed", self); rem_comp_act.triggered.connect(self.remove_completed)
        edit_menu.addAction(rem_comp_act)

    def remove_completed(self):
        to_remove = [i for i in self.container.items if i.status == "done"]
        for i in to_remove:
            self.container.items.remove(i); i.setParent(None)
        self.st_lbl.setText(f"{len(self.container.items)} items in queue.")

    def remove_selected(self):
        to_remove = [i for i in self.container.items if i.is_selected]
        for i in to_remove:
            self.container.items.remove(i); i.setParent(None)
        self.st_lbl.setText(f"{len(self.container.items)} items in queue.")

    def show_about(self): QMessageBox.about(self, "About Fusion", "Fusion v1.0\nHigh-performance media optimizer for macOS.")
    def show_settings_menu(self):
        menu = QMenu(self)
        ext_sub_act = QAction("Load External Subtitles", self); ext_sub_act.setCheckable(True); ext_sub_act.setChecked(self.load_external_subs)
        ext_sub_act.triggered.connect(lambda state: setattr(self, 'load_external_subs', state))
        menu.addAction(ext_sub_act); menu.exec(self.settings_btn.mapToGlobal(QPoint(0, self.settings_btn.height())))

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
    app = QApplication(sys.argv); app.setStyle("macos"); w = MainWindow(); w.show(); sys.exit(app.exec())        ffprobe_path = os.path.join(sys._MEIPASS, 'ffprobe') if hasattr(sys, '_MEIPASS') else 'ffprobe'
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

        # 2. DIŞ ALTYAZILAR VE TEMİZLİK
        ext_subs = []
        if self.load_external:
            subs = glob.glob(f"{base_path}*.*")
            ext_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass')) and s != self.input_file]
            for s in ext_subs:
                if s.lower().endswith('.srt'): self.clean_srt_content(s)

        # 3. KOMUT İNŞASI
        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in ext_subs: cmd.extend(['-i', sub])
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        for i in range(len(ext_subs)): cmd.extend(['-map', str(i + 1)])
        cmd.extend(['-map_metadata', '-1', '-map_chapters', '0'])

        # Dil Kodları Eşleştirme
        lang_codes = {"tr": "tur", "en": "eng", "ru": "rus", "jp": "jpn", "de": "ger", "fr": "fra", "es": "spa", "it": "ita"}
        
        for i, lang in enumerate(source_langs['audio']):
            cmd.extend([f'-metadata:s:a:{i}', f'language={lang}'])
        for i, lang in enumerate(source_langs['subtitle']):
            cmd.extend([f'-metadata:s:s:{i}', f'language={lang}'])
        
        start_idx = len(source_langs['subtitle'])
        for i, sub_path in enumerate(ext_subs):
            match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', sub_path.lower())
            lang = match.group(1) if match else 'und'
            cmd.extend([f'-metadata:s:s:{start_idx + i}', f'language={lang_codes.get(lang, lang)}'])

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
        self.setStyleSheet(f"background-color: {bg}; border: none; border-radius: 4px;")
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
        selected_items = [i for i in self.items if i.is_selected]
        if selected_items:
            rem_sel = QAction("Remove selected", self)
            rem_sel.triggered.connect(self.main_window.remove_selected)
            menu.addAction(rem_sel)
        rem_comp = QAction("Remove completed items", self)
        rem_comp.triggered.connect(self.main_window.remove_completed)
        menu.addAction(rem_comp)
        menu.exec(self.mapToGlobal(pos))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion"); self.resize(700, 550); self.setAcceptDrops(True)
        self.load_external_subs = True
        
        main_v = QVBoxLayout(); main_v.setContentsMargins(0,0,0,0); main_v.setSpacing(0)
        
        toolbar = QWidget(); toolbar.setFixedHeight(95); toolbar.setStyleSheet("background: white; border-bottom: 1px solid #d1d1d6;")
        t_lay = QHBoxLayout(toolbar); t_lay.setContentsMargins(30, 0, 30, 0); t_lay.setSpacing(25)
        
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
        btn = QPushButton(); btn.setFixedSize(80, 85); btn.setStyleSheet("QPushButton{border:none; background:transparent; border-radius:12px;} QPushButton:hover{background:#f5f5f7;}")
        l = QVBoxLayout(btn); l.setContentsMargins(0,0,0,0); l.setSpacing(0)
        ic = QLabel(icon); ic.setAlignment(Qt.AlignmentFlag.AlignCenter); ic.setStyleSheet("font-size: 36px; color: #1d1d1f;")
        tx = QLabel(text); tx.setAlignment(Qt.AlignmentFlag.AlignCenter); tx.setStyleSheet("font-size: 11px; color: #1d1d1f; font-weight: 500;")
        l.addWidget(ic); l.addWidget(tx); return btn

    def setup_menu(self):
        menubar = self.menuBar()
        app_menu = menubar.addMenu("Fusion")
        about_act = QAction("About Fusion", self); about_act.triggered.connect(self.show_about)
        app_menu.addAction(about_act); app_menu.addSeparator()
        quit_act = QAction("Quit", self); quit_act.setShortcut(QKeySequence("Ctrl+Q")); quit_act.triggered.connect(self.close)
        app_menu.addAction(quit_act)

        file_menu = menubar.addMenu("File")
        add_act = QAction("Add Item...", self); add_act.setShortcut(QKeySequence("Ctrl+O")); add_act.triggered.connect(self.open_files)
        file_menu.addAction(add_act)
        
        edit_menu = menubar.addMenu("Edit")
        rem_sel_act = QAction("Remove Selected", self); rem_sel_act.setShortcut(QKeySequence("Backspace")); rem_sel_act.triggered.connect(self.remove_selected)
        edit_menu.addAction(rem_sel_act)
        rem_comp_act = QAction("Remove Completed", self); rem_comp_act.triggered.connect(self.remove_completed)
        edit_menu.addAction(rem_comp_act)

    def remove_completed(self):
        to_remove = [i for i in self.container.items if i.status == "done"]
        for i in to_remove:
            self.container.items.remove(i); i.setParent(None)
        self.st_lbl.setText(f"{len(self.container.items)} items in queue.")

    def remove_selected(self):
        to_remove = [i for i in self.container.items if i.is_selected]
        for i in to_remove:
            self.container.items.remove(i); i.setParent(None)
        self.st_lbl.setText(f"{len(self.container.items)} items in queue.")

    def show_about(self): QMessageBox.about(self, "About Fusion", "Fusion v1.0\nHigh-performance media optimizer for macOS.")
    def show_settings_menu(self):
        menu = QMenu(self)
        ext_sub_act = QAction("Load External Subtitles", self); ext_sub_act.setCheckable(True); ext_sub_act.setChecked(self.load_external_subs)
        ext_sub_act.triggered.connect(lambda state: setattr(self, 'load_external_subs', state))
        menu.addAction(ext_sub_act); menu.exec(self.settings_btn.mapToGlobal(QPoint(0, self.settings_btn.height())))

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

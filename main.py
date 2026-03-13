import sys, os, subprocess, json, glob, re
try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                                 QWidget, QLabel, QProgressBar, QScrollArea, 
                                 QFrame, QPushButton, QFileDialog, QMenu, QMessageBox)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QPoint, QSize
    from PyQt6.QtGui import QPainter, QColor, QBrush, QAction, QKeySequence, QFont
except ImportError:
    sys.exit(1)

# ... ConversionThread sınıfı (değişmedi, aynen korunuyor) ...
class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)
    def __init__(self, input_file, widget, load_external=True):
        super().__init__()
        self.input_file = input_file
        self.widget = widget
        self.load_external = load_external

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

        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in ext_subs: cmd.extend(['-i', sub])
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        for i in range(len(ext_subs)): cmd.extend(['-map', str(i + 1)])
        cmd.extend(['-map_metadata', '-1', '-map_chapters', '0', '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt', '-y', output_file])
        
        try: subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
        self.finished_signal.emit(self)

class FileWidget(QFrame):
    def __init__(self, filename, parent_list):
        super().__init__()
        self.parent_list = parent_list
        self.is_selected = False
        self.status = "waiting"
        self.setFixedHeight(35) # Biraz daha genişlettik
        self.layout = QHBoxLayout(self); self.layout.setContentsMargins(10, 0, 10, 0); self.layout.setSpacing(10)
        
        # Dosya İkonu (Apple tarzı)
        self.file_icon = QLabel("📄"); self.file_icon.setStyleSheet("font-size: 14px; color: #8e8e93;")
        self.status_icon = QLabel("○"); self.status_icon.setFixedWidth(20)
        self.name_label = QLabel(filename)
        
        self.layout.addWidget(self.status_icon)
        self.layout.addWidget(self.file_icon)
        self.layout.addWidget(self.name_label)
        self.layout.addStretch()
        self.update_style()

    def set_status(self, mode):
        self.status = mode
        icons = {"working": "●", "done": "✓", "waiting": "○"}
        colors = {"working": "#ff9500", "done": "#34c759", "waiting": "#8e8e93"}
        self.status_icon.setText(icons.get(mode, "○"))
        self.status_icon.setStyleSheet(f"color: {colors.get(mode, '#8e8e93')}; font-size: 15px; font-weight: bold;")

    def update_style(self):
        # Seçim rengi macOS standart mavi tonuna çekildi
        bg = "#007aff" if self.is_selected else "transparent"
        txt = "white" if self.is_selected else "#1d1d1f"
        radius = "6px" if self.is_selected else "0px"
        self.setStyleSheet(f"QFrame {{ background-color: {bg}; border-radius: {radius}; border: none; }}")
        self.name_label.setStyleSheet(f"color: {txt}; font-size: 13px; font-weight: 400;")
        if self.is_selected: self.file_icon.setStyleSheet("color: white; font-size: 14px;")
        else: self.file_icon.setStyleSheet("color: #8e8e93; font-size: 14px;")

class SublerListWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.items = []
        self.selection_start = None
        self.selection_rect = QRect()
        self.layout = QVBoxLayout(self); self.layout.setContentsMargins(5, 5, 5, 5); self.layout.setSpacing(2); self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def paintEvent(self, event):
        painter = QPainter(self)
        # Arka plan çizgileri (Alternating row colors) - Daha hafif tonlar
        row_h = 35
        for i in range(0, (self.height() // row_h) + 1):
            if i % 2 == 1: painter.fillRect(0, i * row_h, self.width(), row_h, QBrush(QColor(250, 250, 252)))
        
        # Seçim alanı dikdörtgeni (Videodaki gibi yarı saydam mavi)
        if not self.selection_rect.isNull():
            painter.setPen(QColor(0, 122, 255, 200))
            painter.setBrush(QColor(0, 122, 255, 40))
            painter.drawRoundedRect(self.selection_rect, 4, 4)

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
                # Öğe geometrisini kontrol ederek seçimi yap
                item_rect = item.geometry()
                item.is_selected = self.selection_rect.intersects(item_rect)
                item.update_style()
            self.update()

    def mouseReleaseEvent(self, event):
        self.selection_start = None
        self.selection_rect = QRect(); self.update()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion"); self.resize(700, 550); self.setAcceptDrops(True)
        self.load_external_subs = True
        
        main_v = QVBoxLayout(); main_v.setContentsMargins(0,0,0,0); main_v.setSpacing(0)
        
        # Toolbar İyileştirmesi: Çizgiler kaldırıldı ve butonlar büyütüldü
        toolbar = QWidget(); toolbar.setFixedHeight(100); toolbar.setStyleSheet("background: #ffffff; border-bottom: 1px solid #e5e5ea;")
        t_lay = QHBoxLayout(toolbar); t_lay.setContentsMargins(30, 0, 30, 0); t_lay.setSpacing(25)
        
        self.start_btn = self.create_nav_btn("▶", "Start")
        self.settings_btn = self.create_nav_btn("⚙", "Settings")
        self.add_btn = self.create_nav_btn("＋", "Add Item")
        
        t_lay.addStretch(); t_lay.addWidget(self.start_btn); t_lay.addWidget(self.settings_btn); t_lay.addWidget(self.add_btn)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: #ffffff;")
        self.container = SublerListWidget(); self.scroll.setWidget(self.container)

        footer = QWidget(); footer.setFixedHeight(45); footer.setStyleSheet("background: #fbfbfd; border-top: 1px solid #e5e5ea;")
        f_lay = QHBoxLayout(footer); f_lay.setContentsMargins(20, 0, 20, 0)
        self.st_lbl = QLabel("0 items in queue."); self.st_lbl.setStyleSheet("color: #8e8e93; font-size: 12px;")
        self.pb = QProgressBar(); self.pb.setFixedWidth(200); self.pb.setFixedHeight(6); self.pb.setTextVisible(False)
        self.pb.setStyleSheet("QProgressBar{background:#e5e5ea;border-radius:3px;border:none;} QProgressBar::chunk{background:#34c759; border-radius:3px;}")
        f_lay.addWidget(self.st_lbl); f_lay.addStretch(); f_lay.addWidget(self.pb)

        main_v.addWidget(toolbar); main_v.addWidget(self.scroll); main_v.addWidget(footer)
        cw = QWidget(); cw.setLayout(main_v); self.setCentralWidget(cw)

        self.setup_menu(); self.threads = []; self.active_queue = []
        self.add_btn.clicked.connect(self.open_files)
        self.start_btn.clicked.connect(self.start_processing)
        self.settings_btn.clicked.connect(self.show_settings_menu)

    def create_nav_btn(self, icon, text):
        # Buton boyutları ve simge boyutları %50 büyütüldü
        btn = QPushButton(); btn.setFixedSize(85, 90); btn.setStyleSheet("QPushButton{border:none; background:transparent; border-radius:12px;} QPushButton:hover{background:#f2f2f7;}")
        l = QVBoxLayout(btn); l.setContentsMargins(0,10,0,10); l.setSpacing(4)
        ic = QLabel(icon); ic.setAlignment(Qt.AlignmentFlag.AlignCenter); ic.setStyleSheet("font-size: 36px; color: #1d1d1f;") # 24px -> 36px
        tx = QLabel(text); tx.setAlignment(Qt.AlignmentFlag.AlignCenter); tx.setStyleSheet("font-size: 12px; color: #1d1d1f; font-weight: 500;")
        l.addWidget(ic); l.addWidget(tx); return btn

    # ... Diğer metodlar (setup_menu, open_files, vb.) aynen korunuyor ...
    def setup_menu(self):
        menubar = self.menuBar()
        app_menu = menubar.addMenu("Fusion")
        about_act = QAction("About Fusion", self); about_act.triggered.connect(self.show_about)
        app_menu.addAction(about_act); app_menu.addSeparator()
        quit_act = QAction("Quit", self); quit_act.setShortcut("Ctrl+Q"); quit_act.triggered.connect(self.close); app_menu.addAction(quit_act)
        file_menu = menubar.addMenu("File")
        add_act = QAction("Add Item...", self); add_act.setShortcut("Ctrl+O"); add_act.triggered.connect(self.open_files); file_menu.addAction(add_act)
        edit_menu = menubar.addMenu("Edit")
        rem_act = QAction("Remove Selected", self); rem_act.setShortcut("Backspace"); rem_act.triggered.connect(self.remove_selected); edit_menu.addAction(rem_act)

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

    def remove_selected(self):
        for i in [x for x in self.container.items if x.is_selected]:
            self.container.items.remove(i); i.setParent(None)
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
        self.pb.setValue(int((done / len(self.container.items)) * 100)); self.process_next()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()
    def dropEvent(self, e):
        self.add_to_list([u.toLocalFile() for u in e.mimeData().urls()])

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("macos"); w = MainWindow(); w.show(); sys.exit(app.exec())

import sys, os, subprocess, json, glob, re

# PyQt6 bileşenlerini sadece ihtiyaç duyulduğunda yükleyerek açılış hızını artırıyoruz
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QWidget, QLabel, QProgressBar, QScrollArea, 
                             QFrame, QPushButton, QFileDialog, QMenu)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QBrush, QFont, QAction, QKeySequence

class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)
    def __init__(self, full_path, widget):
        super().__init__()
        self.full_path = full_path
        self.widget = widget
        self.is_running = True

    def run(self):
        if not self.is_running: return
        # Binary yollarını belirleme
        bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
        ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg')
        ffprobe_path = os.path.join(bundle_dir, 'ffprobe')
        
        base_path = os.path.splitext(self.full_path)[0]
        output_file = f"{base_path}_Fusion.mkv"

        # FFprobe Analizi
        try:
            probe_cmd = [ffprobe_path, '-v', 'quiet', '-print_format', 'json', '-show_streams', self.full_path]
            probe_data = json.loads(subprocess.check_output(probe_cmd))
            source_langs = {"audio": [], "subtitle": []}
            for s in probe_data.get('streams', []):
                lang = s.get('tags', {}).get('language', 'und')
                if s['codec_type'] == 'audio': source_langs['audio'].append(lang)
                if s['codec_type'] == 'subtitle': source_langs['subtitle'].append(lang)
        except: source_langs = {"audio": [], "subtitle": []}

        subs = glob.glob(f"{base_path}*.[sS][rR][tT]")
        ext_subs = [s for s in subs if s != self.full_path]

        cmd = [ffmpeg_path, '-i', self.full_path]
        for sub in ext_subs: cmd.extend(['-i', sub])
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        for i in range(len(ext_subs)): cmd.extend(['-map', str(i + 1)])
        cmd.extend(['-map_metadata', '-1', '-map_chapters', '0'])

        # Dil metadatalarını ekle
        for i, lang in enumerate(source_langs['audio']):
            cmd.extend([f'-metadata:s:a:{i}', f'language={lang}'])
        for i, lang in enumerate(source_langs['subtitle']):
            cmd.extend([f'-metadata:s:s:{i}', f'language={lang}'])
        
        start_idx = len(source_langs['subtitle'])
        for i, sub_path in enumerate(ext_subs):
            match = re.search(r'\.([a-z]{2,3})\.srt$', sub_path.lower())
            lang = match.group(1) if match else 'und'
            cmd.extend([f'-metadata:s:s:{start_idx + i}', f'language={lang}'])

        cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt', '-y', output_file])
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
        self.finished_signal.emit(self)

class FileWidget(QFrame):
    def __init__(self, full_path, parent_list):
        super().__init__()
        self.parent_list, self.full_path = parent_list, full_path
        self.status, self.is_selected = "waiting", False
        self.setFixedHeight(28)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        
        self.status_icon = QLabel("⚪")
        self.status_icon.setFixedWidth(24)
        self.name_label = QLabel(os.path.basename(full_path))
        self.name_label.setStyleSheet("font-size: 13px; color: #111;")
        layout.addWidget(self.status_icon); layout.addWidget(self.name_label); layout.addStretch()

    def set_status(self, mode):
        self.status = mode
        icons = {"working": "🟠", "done": "✅", "error": "❌"}
        self.status_icon.setText(icons.get(mode, "⚪"))

    def toggle_selection(self):
        self.is_selected = not self.is_selected
        self.setStyleSheet(f"background-color: {'#007aff' if self.is_selected else 'transparent'};")
        self.name_label.setStyleSheet(f"color: {'white' if self.is_selected else '#111'}; font-size: 13px;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not (event.modifiers() & Qt.KeyboardModifier.MetaModifier):
                self.parent_list.clear_selection()
            self.toggle_selection()
        elif event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            rem = menu.addAction("Remove Item")
            rem.triggered.connect(self.parent_list.remove_selected)
            menu.exec(event.globalPosition().toPoint())

class SublerListWidget(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window, self.items = main_window, []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0); self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def paintEvent(self, event):
        painter = QPainter(self)
        row_h = 28
        for i in range(0, (self.height() // row_h) + 1):
            if i % 2 == 1: painter.fillRect(0, i * row_h, self.width(), row_h, QBrush(QColor(243, 246, 250)))

    def clear_selection(self):
        for i in self.items:
            if i.is_selected: i.toggle_selection()

    def remove_selected(self):
        for i in [x for x in self.items if x.is_selected]:
            self.items.remove(i); i.setParent(None)
        self.main_window.update_status()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Queue"); self.resize(700, 600); self.setAcceptDrops(True)
        self.is_processing = False
        
        # Menu
        mb = self.menuBar(); edit = mb.addMenu("Edit")
        all_act = QAction("Select All", self); all_act.setShortcut(QKeySequence("Ctrl+A"))
        all_act.triggered.connect(lambda: [i.toggle_selection() for i in self.container.items if not i.is_selected])
        edit.addAction(all_act)

        # UI
        main_v = QVBoxLayout(); main_v.setContentsMargins(0,0,0,0); main_v.setSpacing(0)
        toolbar = QWidget(); toolbar.setFixedHeight(110); toolbar.setStyleSheet("background:white; border-bottom:1px solid #ddd;")
        t_lay = QHBoxLayout(toolbar); t_lay.setContentsMargins(30,0,30,0); t_lay.setSpacing(40)
        
        self.main_btn = self.create_btn("Start", "▶️")
        self.add_btn = self.create_btn("Add", "📥")
        t_lay.addStretch(); t_lay.addWidget(self.main_btn); t_lay.addWidget(self.add_btn)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = SublerListWidget(self); self.scroll.setWidget(self.container)

        footer = QWidget(); footer.setFixedHeight(50); footer.setStyleSheet("background:#f8f8f8; border-top:1px solid #ccc;")
        f_lay = QHBoxLayout(footer); self.st_lbl = QLabel("0 items"); self.pb = QProgressBar()
        self.pb.setFixedWidth(200); self.pb.setFixedHeight(8); self.pb.setTextVisible(False)
        self.pb.setStyleSheet("QProgressBar{background:#eee;border-radius:4px;} QProgressBar::chunk{background:#007aff;border-radius:4px;}")
        f_lay.addWidget(self.st_lbl); f_lay.addStretch(); f_lay.addWidget(self.pb)

        main_v.addWidget(toolbar); main_v.addWidget(self.scroll); main_v.addWidget(footer)
        cw = QWidget(); cw.setLayout(main_v); self.setCentralWidget(cw)

        self.add_btn.clicked.connect(self.open_f); self.main_btn.clicked.connect(self.toggle)

    def create_btn(self, txt, ico):
        b = QPushButton(f"{ico}\n\n{txt}"); b.setFixedSize(90,90)
        b.setStyleSheet("QPushButton{border:none;font-size:13px;color:#555;} QPushButton:hover{background:#f0f0f0;border-radius:45px;}")
        b.setFont(QFont("", 36)); return b

    def toggle(self):
        if not self.is_processing:
            waiting = [i for i in self.container.items if i.status == "waiting"]
            if not waiting: return
            self.is_processing = True; self.main_btn.setText("⏹️\n\nStop"); self.next()
        else:
            self.is_processing = False; self.main_btn.setText("▶️\n\nStart")

    def open_f(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Select Videos")
        if fs:
            for f in fs:
                w = FileWidget(f, self.container); self.container.layout.addWidget(w); self.container.items.append(w)
            self.update_status()

    def update_status(self): self.st_lbl.setText(f"{len(self.container.items)} items")

    def next(self):
        waiting = [i for i in self.container.items if i.status == "waiting"]
        if not waiting or not self.is_processing:
            if not waiting: self.toggle(); self.pb.setValue(100)
            return
        item = waiting[0]; item.set_status("working")
        t = ConversionThread(item.full_path, item); t.finished_signal.connect(self.done); t.start()

    def done(self, t): t.widget.set_status("done"); self.next()

    def dragEnterEvent(self, e): e.accept() if e.mimeData().hasUrls() else None
    def dropEvent(self, e):
        for u in e.mimeData().urls():
            w = FileWidget(u.toLocalFile(), self.container); self.container.layout.addWidget(w); self.container.items.append(w)
        self.update_status()

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("macos")
    window = MainWindow(); window.show(); sys.exit(app.exec())

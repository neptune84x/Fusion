import sys, os, subprocess, json, glob, re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QWidget, QLabel, QProgressBar, QScrollArea, 
                             QFrame, QPushButton, QFileDialog, QMenu)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QColor, QBrush, QFont, QAction, QKeySequence, QPen

# Binary Yollarını Güvenli Hale Getirme [Çökme Çözümü]
def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)
    def __init__(self, full_path, widget):
        super().__init__()
        self.full_path = full_path
        self.widget = widget
        self.is_running = True

    def run(self):
        if not self.is_running: return
        ffmpeg_path = get_resource_path('ffmpeg')
        ffprobe_path = get_resource_path('ffprobe')
        
        base_path = os.path.splitext(self.full_path)[0]
        output_file = f"{base_path}_Fusion.mkv"

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
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?', '-map_metadata', '-1', '-map_chapters', '0'])

        cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt', '-y', output_file])
        
        try:
            # shell=False kullanarak çökme riskini azaltıyoruz
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except: pass
        self.finished_signal.emit(self)

class FileWidget(QFrame):
    def __init__(self, full_path, parent_list):
        super().__init__()
        self.parent_list, self.full_path = parent_list, full_path
        self.status, self.is_selected = "waiting", False
        self.setFixedHeight(30)
        self.setStyleSheet("background: transparent; border: none;")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        
        self.status_icon = QLabel("○") # Bekleme simgesi
        self.status_icon.setFixedWidth(24)
        self.name_label = QLabel(os.path.basename(full_path))
        self.name_label.setStyleSheet("font-size: 13px; color: #111;")
        
        layout.addWidget(self.status_icon)
        layout.addWidget(self.name_label)
        layout.addStretch()

    def set_status(self, mode):
        self.status = mode
        icons = {"working": "●", "done": "✔", "error": "✕"}
        self.status_icon.setText(icons.get(mode, "○"))
        self.status_icon.setStyleSheet(f"color: {'#ff9500' if mode=='working' else '#34c759' if mode=='done' else '#ff3b30' if mode=='error' else '#8e8e93'};")

    def mousePressEvent(self, event):
        # macOS Seçim Davranışı: Tıklananın seçilmesi, diğerlerinin bırakılması
        if not (event.modifiers() & Qt.KeyboardModifier.MetaModifier):
            self.parent_list.clear_selection()
        
        self.is_selected = not self.is_selected
        self.update_style()

    def update_style(self):
        if self.is_selected:
            self.setStyleSheet("background-color: #007aff; border: none;")
            self.name_label.setStyleSheet("color: white; font-size: 13px;")
            self.status_icon.setStyleSheet("color: white;")
        else:
            self.setStyleSheet("background-color: transparent; border: none;")
            self.name_label.setStyleSheet("color: #111; font-size: 13px;")
            self.status_icon.setStyleSheet(f"color: #8e8e93;")

class SublerListWidget(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window, self.items = main_window, []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0); self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def paintEvent(self, event):
        painter = QPainter(self)
        row_h = 30
        for i in range(0, (self.height() // row_h) + 1):
            if i % 2 == 1: painter.fillRect(0, i * row_h, self.width(), row_h, QBrush(QColor(242, 242, 247)))

    def clear_selection(self):
        for i in self.items:
            i.is_selected = False
            i.update_style()

    def remove_selected(self):
        to_remove = [x for x in self.items if x.is_selected]
        for i in to_remove:
            self.items.remove(i); i.setParent(None)
        self.main_window.update_status()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion Queue"); self.resize(720, 580); self.setAcceptDrops(True)
        self.is_processing = False
        
        # Menu Bar
        mb = self.menuBar(); edit = mb.addMenu("Edit")
        rem_act = QAction("Remove Selected", self); rem_act.setShortcut(QKeySequence("Backspace"))
        rem_act.triggered.connect(self.remove_selected_items)
        edit.addAction(rem_act)

        # UI Layout
        main_v = QVBoxLayout(); main_v.setContentsMargins(0,0,0,0); main_v.setSpacing(0)
        
        # Toolbar (Sade ve Şık Grafik Butonlar)
        toolbar = QWidget(); toolbar.setFixedHeight(100); toolbar.setStyleSheet("background: white; border-bottom: 1px solid #d1d1d6;")
        t_lay = QHBoxLayout(toolbar); t_lay.setContentsMargins(40,0,40,0); t_lay.setSpacing(50)
        
        self.main_btn = self.create_nav_btn("Start", "#34c759") # Yeşil Başlat
        self.add_btn = self.create_nav_btn("Add", "#8e8e93")    # Gri Ekle
        
        t_lay.addStretch(); t_lay.addWidget(self.main_btn); t_lay.addWidget(self.add_btn)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = SublerListWidget(self); self.scroll.setWidget(self.container)

        # Footer
        footer = QWidget(); footer.setFixedHeight(45); footer.setStyleSheet("background:#f2f2f7; border-top:1px solid #d1d1d6;")
        f_lay = QHBoxLayout(footer); self.st_lbl = QLabel("Ready"); self.pb = QProgressBar()
        self.pb.setFixedWidth(200); self.pb.setFixedHeight(6); self.pb.setTextVisible(False)
        self.pb.setStyleSheet("QProgressBar{background:#d1d1d6;border-radius:3px;border:none;} QProgressBar::chunk{background:#007aff;border-radius:3px;}")
        f_lay.addWidget(self.st_lbl); f_lay.addStretch(); f_lay.addWidget(self.pb)

        main_v.addWidget(toolbar); main_v.addWidget(self.scroll); main_v.addWidget(footer)
        cw = QWidget(); cw.setLayout(main_v); self.setCentralWidget(cw)

        self.add_btn.clicked.connect(self.open_f); self.main_btn.clicked.connect(self.toggle)

    def create_nav_btn(self, txt, color):
        b = QPushButton(); b.setFixedSize(70, 70)
        b.setText(f"{txt}"); b.setStyleSheet(f"QPushButton {{ border: 2px solid {color}; border-radius: 35px; color: {color}; font-weight: bold; font-size: 12px; }} QPushButton:hover {{ background: {color}; color: white; }}")
        return b

    def toggle(self):
        if not self.is_processing:
            if not any(i.status == "waiting" for i in self.container.items): return
            self.is_processing = True
            self.main_btn.setText("Stop"); self.main_btn.setStyleSheet("QPushButton { border: 2px solid #ff3b30; border-radius: 35px; color: #ff3b30; font-weight: bold; } QPushButton:hover { background: #ff3b30; color: white; }")
            self.next()
        else:
            self.is_processing = False
            self.main_btn.setText("Start"); self.main_btn.setStyleSheet("QPushButton { border: 2px solid #34c759; border-radius: 35px; color: #34c759; font-weight: bold; } QPushButton:hover { background: #34c759; color: white; }")

    def open_f(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Add Video Files")
        if fs:
            for f in fs:
                w = FileWidget(f, self.container); self.container.layout.addWidget(w); self.container.items.append(w)
            self.update_status()

    def remove_selected_items(self):
        self.container.remove_selected()

    def contextMenuEvent(self, event):
        # Liste üzerinde sağ tık
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: white; color: black; border: 1px solid #d1d1d6; } QMenu::item:selected { background-color: #007aff; color: white; }")
        rem = menu.addAction("Remove Selected")
        rem.triggered.connect(self.remove_selected_items)
        menu.exec(event.globalPos())

    def update_status(self): self.st_lbl.setText(f"{len(self.container.items)} Files in Queue")

    def next(self):
        waiting = [i for i in self.container.items if i.status == "waiting"]
        if not waiting or not self.is_processing:
            if not waiting: self.toggle(); self.pb.setValue(100)
            return
        item = waiting[0]; item.set_status("working")
        t = ConversionThread(item.full_path, item); t.finished_signal.connect(self.done); t.start()

    def done(self, t): 
        t.widget.set_status("done")
        self.next()

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("macos")
    window = MainWindow(); window.show(); sys.exit(app.exec())

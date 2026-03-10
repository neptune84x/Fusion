import sys, os, subprocess, glob
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QWidget, QLabel, QProgressBar, QScrollArea, 
                             QFrame, QPushButton, QFileDialog, QMenu)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QColor, QBrush, QAction, QKeySequence

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'): return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)
    def __init__(self, full_path, widget):
        super().__init__()
        self.full_path = full_path
        self.widget = widget

    def run(self):
        ffmpeg_path = get_resource_path('ffmpeg')
        base_no_ext = os.path.splitext(self.full_path)[0]
        output_file = f"{base_no_ext}_Fusion.mkv"
        
        # 1. Mevcut dosyayı al
        cmd = [ffmpeg_path, '-i', self.full_path]
        
        # 2. Aynı klasördeki .srt ve .ass dosyalarını tara
        ext_subs = glob.glob(f"{base_no_ext}*.*")
        sub_inputs = [f for f in ext_subs if f.lower().endswith(('.srt', '.ass'))]
        
        for s in sub_inputs:
            cmd.extend(['-i', s])
        
        # 3. Map ayarları (Video, Audio ve tüm altyazılar)
        cmd.extend(['-map', '0:v', '-map', '0:a', '-map', '0:s?'])
        
        # Dışarıdan gelen altyazıları ekle ve dil kodlarını isimden çek
        for i, s in enumerate(sub_inputs, start=1):
            cmd.extend(['-map', f'{i}:s'])
            lang = "eng" # Default
            if ".tr." in s.lower(): lang = "tur"
            elif ".ru." in s.lower(): lang = "rus"
            elif ".jp." in s.lower(): lang = "jpn"
            # Bu dile ait metadata ekle (yeni eklenen track en sonda olur)
            cmd.extend([f'-metadata:s:s:{i+1}', f'language={lang}'])

        cmd.extend(['-c', 'copy', '-map_metadata', '0', '-y', output_file])
        
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except: pass
        self.finished_signal.emit(self)

class FileWidget(QFrame):
    def __init__(self, full_path, parent_list):
        super().__init__()
        self.parent_list, self.full_path = parent_list, full_path
        self.status, self.is_selected = "waiting", False
        self.setFixedHeight(32)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        
        self.status_lbl = QLabel("○")
        self.status_lbl.setFixedWidth(20)
        self.status_lbl.setStyleSheet("color: #8e8e93; font-size: 14px;")
        
        self.name_label = QLabel(os.path.basename(full_path))
        self.name_label.setStyleSheet("font-size: 13px; color: #111;")
        
        layout.addWidget(self.status_lbl)
        layout.addWidget(self.name_label)
        layout.addStretch()

    def set_status(self, mode):
        self.status = mode
        chars = {"working": "●", "done": "✓", "waiting": "○"}
        colors = {"working": "#ff9500", "done": "#34c759", "waiting": "#8e8e93"}
        self.status_lbl.setText(chars.get(mode, "○"))
        self.status_lbl.setStyleSheet(f"color: {colors.get(mode, '#8e8e93')}; font-size: 14px;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier or event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self.parent_list.clear_selection()
            self.is_selected = not self.is_selected
            self.update_style()

    def update_style(self):
        bg = "#007aff" if self.is_selected else "transparent"
        txt = "white" if self.is_selected else "#111"
        self.setStyleSheet(f"background-color: {bg}; border: none;")
        self.name_label.setStyleSheet(f"color: {txt}; font-size: 13px;")

class SublerListWidget(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window, self.items = main_window, []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0); self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def paintEvent(self, event):
        painter = QPainter(self)
        for i in range(0, (self.height() // 32) + 1):
            if i % 2 == 1: painter.fillRect(0, i * 32, self.width(), 32, QBrush(QColor(242, 242, 247)))

    def clear_selection(self):
        for i in self.items: i.is_selected = False; i.update_style()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Queue"); self.resize(650, 450); self.setAcceptDrops(True)
        self.active_threads = [] 
        
        main_v = QVBoxLayout(); main_v.setContentsMargins(0,0,0,0); main_v.setSpacing(0)
        
        # Toolbar
        toolbar = QWidget(); toolbar.setFixedHeight(75); toolbar.setStyleSheet("background: white; border-bottom: 1px solid #d1d1d6;")
        t_lay = QHBoxLayout(toolbar); t_lay.setContentsMargins(20, 5, 20, 5); t_lay.setSpacing(15)
        
        self.start_btn = self.create_nav_item("▶", "Start")
        self.add_btn = self.create_nav_item("＋", "Add Item")
        self.start_btn.clicked.connect(self.start_process)
        self.add_btn.clicked.connect(self.open_f)
        
        t_lay.addStretch(); t_lay.addWidget(self.start_btn); t_lay.addWidget(self.add_btn)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = SublerListWidget(self); self.scroll.set_widget = self.container # Custom scroll support
        self.scroll.setWidget(self.container)

        # Footer
        self.footer = QWidget(); self.footer.setFixedHeight(35); self.footer.setStyleSheet("background: white; border-top: 1px solid #d1d1d6;")
        f_lay = QHBoxLayout(self.footer); f_lay.setContentsMargins(15, 0, 15, 0)
        self.st_lbl = QLabel("0 items in queue."); self.st_lbl.setStyleSheet("font-size: 12px; color: #333;")
        self.pb = QProgressBar(); self.pb.setFixedWidth(150); self.pb.setFixedHeight(5); self.pb.setTextVisible(False)
        self.pb.setStyleSheet("QProgressBar{background:#eee;border-radius:2px;border:none;} QProgressBar::chunk{background:#007aff;}")
        f_lay.addWidget(self.st_lbl); f_lay.addStretch(); f_lay.addWidget(self.pb)

        main_v.addWidget(toolbar); main_v.addWidget(self.scroll); main_v.addWidget(self.footer)
        cw = QWidget(); cw.setLayout(main_v); self.setCentralWidget(cw)

        # Context Menu & Delete
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        rem_sc = QAction(self); rem_sc.setShortcut(QKeySequence("Backspace")); rem_sc.triggered.connect(self.remove_selected); self.addAction(rem_sc)

    def create_nav_item(self, icon, text):
        btn = QPushButton()
        btn.setFixedSize(65, 65)
        btn.setStyleSheet("QPushButton{border:none; background:transparent; border-radius:8px;} QPushButton:hover{background:#f0f0f0;}")
        l = QVBoxLayout(btn); l.setContentsMargins(0,5,0,5); l.setSpacing(0) # Çizgileri kaldırmak için spacing 0
        ic = QLabel(icon); ic.setAlignment(Qt.AlignmentFlag.AlignCenter); ic.setStyleSheet("font-size: 26px; color: #333; border:none;")
        tx = QLabel(text); tx.setAlignment(Qt.AlignmentFlag.AlignCenter); tx.setStyleSheet("font-size: 11px; color: #666; border:none;")
        ic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        tx.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        l.addWidget(ic); l.addWidget(tx)
        return btn

    def show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu{background:white; border:1px solid #ccc;} QMenu::item:selected{background:#007aff; color:white;}")
        rem = menu.addAction("Remove Selected")
        rem.triggered.connect(self.remove_selected)
        menu.exec(self.mapToGlobal(pos))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
    
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov')): self.add_item(path)

    def open_f(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Select Videos")
        for f in fs: self.add_item(f)

    def add_item(self, path):
        w = FileWidget(path, self.container); self.container.layout.addWidget(w); self.container.items.append(w)
        self.update_footer()

    def remove_selected(self):
        for i in [x for x in self.container.items if x.is_selected]:
            self.container.items.remove(i); i.setParent(None)
        self.update_footer()

    def update_footer(self):
        total = len(self.container.items)
        self.st_lbl.setText(f"{total} items in queue.")

    def start_process(self):
        waiting = [i for i in self.container.items if i.status == "waiting"]
        if not waiting: return
        item = waiting[0]; item.set_status("working")
        thread = ConversionThread(item.full_path, item)
        thread.finished_signal.connect(self.on_done)
        self.active_threads.append(thread); thread.start()

    def on_done(self, t):
        t.widget.set_status("done")
        if t in self.active_threads: self.active_threads.remove(t)
        total = len(self.container.items)
        done = len([i for i in self.container.items if i.status == "done"])
        self.pb.setValue(int((done / total) * 100))
        self.start_process()

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("macos")
    w = MainWindow(); w.show(); sys.exit(app.exec())

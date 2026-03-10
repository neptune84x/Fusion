import sys, os, subprocess, json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QWidget, QLabel, QProgressBar, QScrollArea, 
                             QFrame, QPushButton, QFileDialog, QMenu)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QBrush, QAction, QKeySequence

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

    def run(self):
        ffmpeg_path = get_resource_path('ffmpeg')
        base_path = os.path.splitext(self.full_path)[0]
        output_file = f"{base_path}_Fusion.mkv"
        
        # Dil kodlarını ve metadata etiketlerini koruyan en temiz komut
        cmd = [
            ffmpeg_path, '-i', self.full_path,
            '-map', '0', '-c', 'copy',
            '-map_metadata', '0',
            '-map_metadata:s:a', '0:s:a',
            '-map_metadata:s:s', '0:s:s',
            '-y', output_file
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except: pass
        self.finished_signal.emit(self)

class FileWidget(QFrame):
    def __init__(self, full_path, parent_list):
        super().__init__()
        self.parent_list, self.full_path = parent_list, full_path
        self.status, self.is_selected = "waiting", False
        self.setFixedHeight(30) # Subler gibi ince satırlar
        
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
        if not (event.modifiers() & Qt.KeyboardModifier.MetaModifier):
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
        for i in range(0, (self.height() // 30) + 1):
            if i % 2 == 1: painter.fillRect(0, i * 30, self.width(), 30, QBrush(QColor(242, 242, 247)))

    def clear_selection(self):
        for i in self.items: i.is_selected = False; i.update_style()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Queue")
        self.resize(650, 450)
        self.setAcceptDrops(True)
        self.active_threads = [] 
        
        # Shortcuts
        rem_sc = QAction(self); rem_sc.setShortcut(QKeySequence("Backspace"))
        rem_sc.triggered.connect(self.remove_selected); self.addAction(rem_sc)

        main_v = QVBoxLayout(); main_v.setContentsMargins(0,0,0,0); main_v.setSpacing(0)
        
        # Toolbar (Subler stili geniş ikonlar ve metinler)
        toolbar = QWidget(); toolbar.setFixedHeight(75)
        toolbar.setStyleSheet("background: white; border-bottom: 1px solid #d1d1d6;")
        t_lay = QHBoxLayout(toolbar); t_lay.setContentsMargins(20, 5, 20, 5); t_lay.setSpacing(20)
        
        self.start_btn = self.create_nav_item("▶", "Start")
        self.add_btn = self.create_nav_item("＋", "Add Item")
        
        t_lay.addStretch()
        t_lay.addWidget(self.start_btn)
        t_lay.addWidget(self.add_btn)

        # List Area
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = SublerListWidget(self); self.scroll.setWidget(self.container)

        # Footer
        self.footer = QWidget(); self.footer.setFixedHeight(35); self.footer.setStyleSheet("background: white; border-top: 1px solid #d1d1d6;")
        f_lay = QHBoxLayout(self.footer); f_lay.setContentsMargins(15, 0, 15, 0)
        self.st_lbl = QLabel("0 items in queue."); self.st_lbl.setStyleSheet("font-size: 12px; color: #333;")
        self.pb = QProgressBar(); self.pb.setFixedWidth(150); self.pb.setFixedHeight(5); self.pb.setTextVisible(False)
        self.pb.setStyleSheet("QProgressBar{background:#eee; border-radius:2px; border:none;} QProgressBar::chunk{background:#007aff; border-radius:2px;}")
        f_lay.addWidget(self.st_lbl); f_lay.addStretch(); f_lay.addWidget(self.pb)

        main_v.addWidget(toolbar); main_v.addWidget(self.scroll); main_v.addWidget(self.footer)
        cw = QWidget(); cw.setLayout(main_v); self.setCentralWidget(cw)

    def create_nav_item(self, icon, text):
        btn = QPushButton()
        btn.setFixedSize(55, 60)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("QPushButton{border:none; background:transparent;} QPushButton:hover{background:#f0f0f0; border-radius:6px;}")
        
        l = QVBoxLayout(btn); l.setContentsMargins(0,0,0,0); l.setSpacing(2)
        ic_lbl = QLabel(icon); ic_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic_lbl.setStyleSheet("font-size: 22px; color: #444; margin-bottom: 2px;")
        txt_lbl = QLabel(text); txt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        txt_lbl.setStyleSheet("font-size: 11px; color: #555;")
        
        l.addWidget(ic_lbl); l.addWidget(txt_lbl)
        btn.clicked.connect(lambda: self.on_click(text))
        return btn

    def on_click(self, text):
        if text == "Add Item": self.open_f()
        else: self.start_process()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()

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
        to_rem = [i for i in self.container.items if i.is_selected]
        for i in to_rem:
            self.container.items.remove(i); i.setParent(None)
        self.update_footer()

    def update_footer(self):
        total = len(self.container.items)
        self.st_lbl.setText(f"{total} items in queue." if total > 0 else "0 items in queue.")

    def start_process(self):
        waiting = [i for i in self.container.items if i.status == "waiting"]
        if not waiting: return
        self.st_lbl.setText("Working.")
        item = waiting[0]; item.set_status("working")
        thread = ConversionThread(item.full_path, item)
        thread.finished_signal.connect(self.on_done)
        self.active_threads.append(thread); thread.start()

    def on_done(self, t):
        t.widget.set_status("done")
        if t in self.active_threads: self.active_threads.remove(t)
        done_count = len([i for i in self.container.items if i.status == "done"])
        total = len(self.container.items)
        self.pb.setValue(int((done_count / total) * 100))
        self.start_process()

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("macos")
    w = MainWindow(); w.show(); sys.exit(app.exec())

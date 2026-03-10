import sys, os, subprocess, json, glob, re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QWidget, QLabel, QProgressBar, QScrollArea, 
                             QFrame, QPushButton, QFileDialog, QMenu)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPainter, QColor, QBrush, QAction, QKeySequence, QPen, QIcon

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
        ffprobe_path = get_resource_path('ffprobe')
        base_path = os.path.splitext(self.full_path)[0]
        output_file = f"{base_path}_Fusion.mkv"

        # FFmpeg komutu (Judas/Metadata temizleme dahil)
        cmd = [ffmpeg_path, '-i', self.full_path, '-map', '0:v', '-map', '0:a?', '-map', '0:s?', 
               '-map_metadata', '-1', '-map_chapters', '0', '-c', 'copy', '-y', output_file]
        
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
        self.status_lbl.setStyleSheet("color: #8e8e93; font-size: 16px;")
        
        self.name_label = QLabel(os.path.basename(full_path))
        self.name_label.setStyleSheet("font-size: 13px; color: #111;")
        
        layout.addWidget(self.status_lbl)
        layout.addWidget(self.name_label)
        layout.addStretch()

    def set_status(self, mode):
        self.status = mode
        colors = {"working": "#ff9500", "done": "#34c759", "waiting": "#8e8e93"}
        chars = {"working": "●", "done": "✓", "waiting": "○"}
        self.status_lbl.setText(chars.get(mode, "○"))
        self.status_lbl.setStyleSheet(f"color: {colors.get(mode, '#8e8e93')}; font-size: 16px;")

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
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def paintEvent(self, event):
        painter = QPainter(self)
        for i in range(0, (self.height() // 32) + 1):
            if i % 2 == 1: painter.fillRect(0, i * 32, self.width(), 32, QBrush(QColor(242, 242, 247)))

    def clear_selection(self):
        for i in self.items:
            i.is_selected = False
            i.update_style()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion")
        self.resize(700, 500)
        self.setAcceptDrops(True) # Sürükle bırak aktif
        self.active_threads = [] # Çökmeyi önleyen liste

        # UI
        main_v = QVBoxLayout()
        main_v.setContentsMargins(0,0,0,0)
        main_v.setSpacing(0)
        
        # Subler-Style Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet("background: #f8f8f8; border-bottom: 1px solid #d1d1d6;")
        t_lay = QHBoxLayout(toolbar)
        t_lay.setContentsMargins(10, 0, 10, 0)

        self.add_btn = self.create_subler_btn("+", "Add File")
        self.start_btn = self.create_subler_btn("▶", "Start")
        
        t_lay.addWidget(self.add_btn)
        t_lay.addWidget(self.start_btn)
        t_lay.addStretch()

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = SublerListWidget(self)
        self.scroll.setWidget(self.container)

        main_v.addWidget(toolbar)
        main_v.addWidget(self.scroll)
        
        cw = QWidget()
        cw.setLayout(main_v)
        self.setCentralWidget(cw)

        self.add_btn.clicked.connect(self.open_f)
        self.start_btn.clicked.connect(self.start_process)

    def create_subler_btn(self, icon_txt, hint):
        btn = QPushButton(icon_txt)
        btn.setFixedSize(30, 30)
        btn.setToolTip(hint)
        btn.setStyleSheet("""
            QPushButton { border: 1px solid #ccc; border-radius: 4px; background: white; font-size: 16px; color: #555; }
            QPushButton:hover { background: #f0f0f0; border-color: #999; }
            QPushButton:pressed { background: #e0e0e0; }
        """)
        return btn

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov')):
                self.add_item(path)

    def open_f(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Select Videos")
        for f in fs: self.add_item(f)

    def add_item(self, path):
        w = FileWidget(path, self.container)
        self.container.layout.addWidget(w)
        self.container.items.append(w)

    def start_process(self):
        waiting = [i for i in self.container.items if i.status == "waiting"]
        if not waiting: return
        
        item = waiting[0]
        item.set_status("working")
        
        thread = ConversionThread(item.full_path, item)
        thread.finished_signal.connect(self.on_thread_finished)
        self.active_threads.append(thread) # REFERANSI SAKLA (Çökmeyi önler)
        thread.start()

    def on_thread_finished(self, thread):
        thread.widget.set_status("done")
        if thread in self.active_threads:
            self.active_threads.remove(thread)
        self.start_process() # Bir sonrakine geç

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("macos")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

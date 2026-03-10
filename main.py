import sys, os, subprocess, json, glob, re

try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                                 QWidget, QLabel, QProgressBar, QScrollArea, 
                                 QFrame, QPushButton, QFileDialog, QMenu)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtGui import QPainter, QColor, QBrush, QFont, QAction, QKeySequence
except ImportError:
    sys.exit(1)

class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)
    def __init__(self, input_file, widget):
        super().__init__()
        self.input_file = input_file
        self.widget = widget
        self.is_running = True

    def run(self):
        if not self.is_running: return
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

        # Girinti Hatası Düzeltildi
        subs = glob.glob(f"{base_path}*.*")
        ext_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass')) and s != self.input_file]

        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in ext_subs: cmd.extend(['-i', sub])
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        for i in range(len(ext_subs)): cmd.extend(['-map', str(i + 1)])
        cmd.extend(['-map_metadata', '-1', '-map_chapters', '0'])

        for i, lang in enumerate(source_langs['audio']):
            cmd.extend([f'-metadata:s:a:{i}', f'language={lang}'])
        for i, lang in enumerate(source_langs['subtitle']):
            cmd.extend([f'-metadata:s:s:{i}', f'language={lang}'])
        
        start_idx = len(source_langs['subtitle'])
        for i, sub_path in enumerate(ext_subs):
            match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', sub_path.lower())
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
        self.parent_list = parent_list
        self.full_path = full_path
        self.filename = os.path.basename(full_path)
        self.is_selected = False
        self.status = "waiting"
        self.setFixedHeight(28)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(15, 0, 15, 0)
        
        self.status_icon = QLabel("⚪")
        self.status_icon.setFixedWidth(24)
        self.name_label = QLabel(self.filename)
        self.name_label.setStyleSheet("font-size: 13px; color: #111;")
        self.info_icon = QLabel("ⓘ")
        self.info_icon.setStyleSheet("color: #bbb; font-size: 16px;")
        
        self.layout.addWidget(self.status_icon)
        self.layout.addWidget(self.name_label)
        self.layout.addStretch()
        self.layout.addWidget(self.info_icon)

    def set_status(self, mode):
        self.status = mode
        icons = {"working": "🟠", "done": "✅", "error": "❌"}
        self.status_icon.setText(icons.get(mode, "⚪"))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier or event.modifiers() & Qt.KeyboardModifier.MetaModifier):
                self.parent_list.clear_selection()
            self.toggle_selection()
        elif event.button() == Qt.MouseButton.RightButton:
            if not self.is_selected:
                self.parent_list.clear_selection()
                self.toggle_selection()
            self.show_context_menu(event.globalPosition().toPoint())

    def toggle_selection(self):
        self.is_selected = not self.is_selected
        color = "#007aff" if self.is_selected else "transparent"
        text_color = "white" if self.is_selected else "#111"
        self.setStyleSheet(f"background-color: {color}; border: none;")
        self.name_label.setStyleSheet(f"font-size: 13px; color: {text_color};")

    def show_context_menu(self, pos):
        menu = QMenu(self)
        remove_act = menu.addAction("Remove Item")
        remove_act.triggered.connect(self.parent_list.remove_selected)
        menu.exec(pos)

class SublerListWidget(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.items = []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def paintEvent(self, event):
        painter = QPainter(self)
        row_height = 28
        color_alt = QColor(243, 246, 250)
        for i in range(0, (self.height() // row_height) + 1):
            if i % 2 == 1: painter.fillRect(0, i * row_height, self.width(), row_height, QBrush(color_alt))

    def clear_selection(self):
        for item in self.items:
            if item.is_selected: item.toggle_selection()

    def select_all(self):
        for item in self.items:
            if not item.is_selected: item.toggle_selection()

    def remove_selected(self):
        to_remove = [item for item in self.items if item.is_selected]
        for item in to_remove:
            self.items.remove(item)
            item.setParent(None)
        self.main_window.update_status()

    def remove_completed(self):
        to_remove = [item for item in self.items if item.status == "done"]
        for item in to_remove:
            self.items.remove(item)
            item.setParent(None)
        self.main_window.update_status()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            rem_comp = menu.addAction("Remove Completed")
            rem_comp.triggered.connect(self.remove_completed)
            menu.exec(event.globalPosition().toPoint())
        else:
            self.clear_selection()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Queue"); self.resize(700, 600); self.setAcceptDrops(True)
        self.is_processing = False
        
        # Menu Bar (Edit -> Select All)
        menubar = self.menuBar()
        edit_menu = menubar.addMenu("Edit")
        select_all_act = QAction("Select All", self)
        select_all_act.setShortcut(QKeySequence("Ctrl+A"))
        select_all_act.triggered.connect(lambda: self.container.select_all())
        edit_menu.addAction(select_all_act)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0); main_layout.setSpacing(0)
        
        # Toolbar
        toolbar = QWidget(); toolbar.setFixedHeight(110); toolbar.setStyleSheet("background: white; border-bottom: 1px solid #dcdcdc;")
        t_layout = QHBoxLayout(toolbar); t_layout.setContentsMargins(30, 0, 30, 0); t_layout.setSpacing(40)
        
        self.main_btn = self.create_nav_btn("Start", "▶️") 
        self.settings_btn = self.create_nav_btn("Settings", "⚙️")
        self.add_btn = self.create_nav_btn("Add Item", "📥")
        
        t_layout.addStretch()
        t_layout.addWidget(self.main_btn); t_layout.addWidget(self.settings_btn); t_layout.addWidget(self.add_btn)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = SublerListWidget(self); self.container.setStyleSheet("background: white;")
        self.scroll.setWidget(self.container)

        footer = QWidget(); footer.setFixedHeight(50); footer.setStyleSheet("background: #f8f8f8; border-top: 1px solid #ccc;")
        f_layout = QHBoxLayout(footer); f_layout.setContentsMargins(20, 0, 20, 0)
        self.status_label = QLabel("0 items in queue."); self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(240); self.progress_bar.setFixedHeight(8); self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { background: #e0e0e0; border-radius: 4px; border: none; } QProgressBar::chunk { background: #007aff; border-radius: 4px; }")
        f_layout.addWidget(self.status_label); f_layout.addStretch(); f_layout.addWidget(self.progress_bar)

        main_layout.addWidget(toolbar); main_layout.addWidget(self.scroll); main_layout.addWidget(footer)
        cw = QWidget(); cw.setLayout(main_layout); self.setCentralWidget(cw)

        self.threads = []
        self.add_btn.clicked.connect(self.open_files)
        self.main_btn.clicked.connect(self.toggle_process)

    def create_nav_btn(self, text, icon_char):
        btn = QPushButton(); btn.setFixedSize(90, 90)
        btn.setText(f"{icon_char}\n\n{text}")
        btn.setStyleSheet("QPushButton { border: none; font-size: 13px; color: #555; background: transparent; } QPushButton:hover { background-color: #f0f0f0; border-radius: 45px; }")
        font = QFont(); font.setPointSize(36); btn.setFont(font)
        return btn

    def toggle_process(self):
        if not self.is_processing:
            if not any(i.status == "waiting" for i in self.container.items): return
            self.is_processing = True
            self.main_btn.setText("⏹️\n\nStop") # Tek tuş dönüşümü
            self.process_next()
        else:
            self.is_processing = False
            self.main_btn.setText("▶️\n\nStart")
            for t in self.threads: t.is_running = False

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Videos", "", "Videos (*.mp4 *.mkv *.avi)")
        if files: self.add_to_queue(files)

    def add_to_queue(self, paths):
        for p in paths:
            w = FileWidget(p, self.container)
            self.container.layout.addWidget(w)
            self.container.items.append(w)
        self.update_status()

    def update_status(self):
        count = len(self.container.items)
        self.status_label.setText(f"{count} items in queue.")

    def process_next(self):
        waiting = [i for i in self.container.items if i.status == "waiting"]
        if not waiting or not self.is_processing:
            if not waiting:
                self.is_processing = False
                self.main_btn.setText("▶️\n\nStart")
                self.progress_bar.setValue(100)
            return
        
        item = waiting[0]
        item.set_status("working")
        t = ConversionThread(item.full_path, item)
        t.finished_signal.connect(self.on_task_finished)
        self.threads.append(t); t.start()

    def on_task_finished(self, t):
        t.widget.set_status("done")
        if t in self.threads: self.threads.remove(t)
        self.process_next()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()
    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]; self.add_to_queue(files)

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("macos")
    window = MainWindow(); window.show(); sys.exit(app.exec())        subs = glob.glob(f"{base_path}*.*")
        ext_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass')) and s != self.input_file]

        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in ext_subs: cmd.extend(['-i', sub])
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        for i in range(len(ext_subs)): cmd.extend(['-map', str(i + 1)])

        cmd.extend(['-map_metadata', '-1', '-map_chapters', '0']) # Judas silme

        for i, lang in enumerate(source_langs['audio']):
            cmd.extend([f'-metadata:s:a:{i}', f'language={lang}'])
        for i, lang in enumerate(source_langs['subtitle']):
            cmd.extend([f'-metadata:s:s:{i}', f'language={lang}'])
        
        start_idx = len(source_langs['subtitle'])
        for i, sub_path in enumerate(ext_subs):
            match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', sub_path.lower())
            lang = match.group(1) if match else 'und'
            cmd.extend([f'-metadata:s:s:{start_idx + i}', f'language={lang}'])

        cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt', '-y', output_file])
        try: subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
        self.finished_signal.emit(self)

class FileWidget(QFrame):
    def __init__(self, filename, parent_list):
        super().__init__()
        self.parent_list = parent_list
        self.filename = filename
        self.is_selected = False
        self.status = "waiting"
        self.setFixedHeight(28)
        self.setStyleSheet("background: transparent; border: none;")
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(15, 0, 15, 0)
        
        self.status_icon = QLabel("⚪")
        self.status_icon.setFixedWidth(24)
        
        self.name_label = QLabel(filename)
        self.name_label.setStyleSheet("font-size: 13px; color: #111;")
        
        self.info_icon = QLabel("ⓘ")
        self.info_icon.setStyleSheet("color: #bbb; font-size: 16px;")
        
        self.layout.addWidget(self.status_icon)
        self.layout.addWidget(self.name_label)
        self.layout.addStretch()
        self.layout.addWidget(self.info_icon)

    def set_status(self, mode):
        self.status = mode
        icons = {"working": "🟠", "done": "✅", "error": "❌"}
        self.status_icon.setText(icons.get(mode, "⚪"))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier or event.modifiers() & Qt.KeyboardModifier.MetaModifier):
                self.parent_list.clear_selection()
            self.toggle_selection()
        elif event.button() == Qt.MouseButton.RightButton:
            if not self.is_selected:
                self.parent_list.clear_selection()
                self.toggle_selection()
            self.show_context_menu(event.globalPosition().toPoint())

    def toggle_selection(self):
        self.is_selected = not self.is_selected
        color = "#007aff" if self.is_selected else "transparent"
        text_color = "white" if self.is_selected else "#111"
        self.setStyleSheet(f"background-color: {color}; border: none;")
        self.name_label.setStyleSheet(f"font-size: 13px; color: {text_color};")

    def show_context_menu(self, pos):
        menu = QMenu(self)
        remove_act = menu.addAction("Remove Item")
        remove_act.triggered.connect(self.parent_list.remove_selected)
        menu.exec(pos)

class SublerListWidget(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.items = []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def paintEvent(self, event):
        painter = QPainter(self)
        row_height = 28
        color_alt = QColor(243, 246, 250)
        for i in range(0, (self.height() // row_height) + 1):
            if i % 2 == 1: painter.fillRect(0, i * row_height, self.width(), row_height, QBrush(color_alt))

    def clear_selection(self):
        for item in self.items:
            if item.is_selected: item.toggle_selection()

    def select_all(self):
        for item in self.items:
            if not item.is_selected: item.toggle_selection()

    def remove_selected(self):
        to_remove = [item for item in self.items if item.is_selected]
        for item in to_remove:
            self.items.remove(item)
            item.setParent(None)
        self.main_window.update_status()

    def remove_completed(self):
        to_remove = [item for item in self.items if item.status == "done"]
        for item in to_remove:
            self.items.remove(item)
            item.setParent(None)
        self.main_window.update_status()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            rem_comp = menu.addAction("Remove Completed")
            rem_comp.triggered.connect(self.remove_completed)
            menu.exec(event.globalPosition().toPoint())
        else:
            self.clear_selection()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Queue"); self.resize(700, 600); self.setAcceptDrops(True)
        self.is_processing = False
        
        # Menu Bar (Edit -> Select All)
        menubar = self.menuBar()
        edit_menu = menubar.addMenu("Edit")
        select_all_act = QAction("Select All", self)
        select_all_act.setShortcut(QKeySequence("Ctrl+A"))
        select_all_act.triggered.connect(lambda: self.container.select_all())
        edit_menu.addAction(select_all_act)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0); main_layout.setSpacing(0)
        
        # Toolbar
        toolbar = QWidget(); toolbar.setFixedHeight(110); toolbar.setStyleSheet("background: white; border-bottom: 1px solid #dcdcdc;")
        t_layout = QHBoxLayout(toolbar); t_layout.setContentsMargins(30, 0, 30, 0); t_layout.setSpacing(40)
        
        self.main_btn = self.create_nav_btn("Start", "🔘") # Tek tuş start/stop
        self.settings_btn = self.create_nav_btn("Settings", "⚙️")
        self.add_btn = self.create_nav_btn("Add Item", "📥") # Subler tipi ikon
        
        t_layout.addStretch()
        t_layout.addWidget(self.main_btn); t_layout.addWidget(self.settings_btn); t_layout.addWidget(self.add_btn)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = SublerListWidget(self); self.container.setStyleSheet("background: white;")
        self.scroll.setWidget(self.container)

        footer = QWidget(); footer.setFixedHeight(50); footer.setStyleSheet("background: #f8f8f8; border-top: 1px solid #ccc;")
        f_layout = QHBoxLayout(footer); f_layout.setContentsMargins(20, 0, 20, 0)
        self.status_label = QLabel("0 items in queue."); self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(240); self.progress_bar.setFixedHeight(8); self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { background: #e0e0e0; border-radius: 4px; border: none; } QProgressBar::chunk { background: #007aff; border-radius: 4px; }")
        f_layout.addWidget(self.status_label); f_layout.addStretch(); f_layout.addWidget(self.progress_bar)

        main_layout.addWidget(toolbar); main_layout.addWidget(self.scroll); main_layout.addWidget(footer)
        cw = QWidget(); cw.setLayout(main_layout); self.setCentralWidget(cw)

        self.threads = []; self.total_tasks = 0
        self.add_btn.clicked.connect(self.open_files)
        self.main_btn.clicked.connect(self.toggle_process)

    def create_nav_btn(self, text, icon_char):
        btn = QPushButton(); btn.setFixedSize(90, 90)
        btn.setText(f"{icon_char}\n\n{text}")
        btn.setStyleSheet("QPushButton { border: none; font-size: 13px; color: #555; background: transparent; } QPushButton:hover { background-color: #f0f0f0; border-radius: 45px; }")
        font = QFont(); font.setPointSize(36); btn.setFont(font)
        return btn

    def toggle_process(self):
        if not self.is_processing:
            if not self.container.items: return
            self.is_processing = True
            self.main_btn.setText("⏹️\n\nStop")
            self.process_next()
        else:
            self.is_processing = False
            self.main_btn.setText("▶️\n\nStart")
            for t in self.threads: t.is_running = False

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Videos", "", "Videos (*.mp4 *.mkv *.avi)")
        if files: self.add_to_queue(files)

    def add_to_queue(self, paths):
        for p in paths:
            w = FileWidget(os.path.basename(p), self.container)
            self.container.layout.addWidget(w)
            self.container.items.append(w)
        self.update_status()

    def update_status(self):
        self.total_tasks = len(self.container.items)
        self.status_label.setText(f"{self.total_tasks} items in queue.")

    def process_next(self):
        waiting = [i for i in self.container.items if i.status == "waiting"]
        if not waiting or not self.is_processing:
            self.is_processing = False
            self.main_btn.setText("▶️\n\nStart")
            return
        
        item = waiting[0]
        item.set_status("working")
        t = ConversionThread(item.filename, item) # Gerçekte path saklanmalı, basitleştirildi
        t.finished_signal.connect(self.on_task_finished)
        self.threads.append(t); t.start()

    def on_task_finished(self, t):
        t.widget.set_status("done")
        if t in self.threads: self.threads.remove(t)
        self.process_next()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()
    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]; self.add_to_queue(files)

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("macos")
    window = MainWindow(); window.show(); sys.exit(app.exec())        # Dış Altyazılar
        subs = glob.glob(f"{base_path}*.*")
        ext_subs = [s for s in subs if s.lower().endswith(('.srt', '.ass')) and s != self.input_file]

        cmd = [ffmpeg_path, '-i', self.input_file]
        for sub in ext_subs: cmd.extend(['-i', sub])
        cmd.extend(['-map', '0:v', '-map', '0:a?', '-map', '0:s?'])
        for i in range(len(ext_subs)): cmd.extend(['-map', str(i + 1)])

        # Judas ve Metadata Temizliği
        cmd.extend(['-map_metadata', '-1', '-map_chapters', '0'])

        for i, lang in enumerate(source_langs['audio']):
            cmd.extend([f'-metadata:s:a:{i}', f'language={lang}'])
        for i, lang in enumerate(source_langs['subtitle']):
            cmd.extend([f'-metadata:s:s:{i}', f'language={lang}'])
        
        start_idx = len(source_langs['subtitle'])
        for i, sub_path in enumerate(ext_subs):
            match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', sub_path.lower())
            lang = match.group(1) if match else 'und'
            cmd.extend([f'-metadata:s:s:{start_idx + i}', f'language={lang}'])

        cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt', '-y', output_file])
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
        self.finished_signal.emit(self)

class SublerListWidget(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        row_height = 28 # Subler pijama yüksekliği
        color_alt = QColor(243, 246, 250)
        for i in range(0, (self.height() // row_height) + 1):
            if i % 2 == 1: painter.fillRect(0, i * row_height, self.width(), row_height, QBrush(color_alt))

class FileWidget(QFrame):
    def __init__(self, filename):
        super().__init__()
        self.setFixedHeight(28)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self); layout.setContentsMargins(15, 0, 15, 0)
        self.status_icon = QLabel("⚪"); self.status_icon.setFixedWidth(24)
        self.name_label = QLabel(filename); self.name_label.setStyleSheet("font-size: 13px; color: #111;")
        self.info_icon = QLabel("ⓘ"); self.info_icon.setStyleSheet("color: #bbb; font-size: 16px;")
        layout.addWidget(self.status_icon); layout.addWidget(self.name_label); layout.addStretch(); layout.addWidget(self.info_icon)
    def set_status(self, mode):
        icons = {"working": "🟠", "done": "✅", "error": "❌"}
        self.status_icon.setText(icons.get(mode, "⚪"))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Queue"); self.resize(700, 600); self.setAcceptDrops(True)
        main_layout = QVBoxLayout(); main_layout.setContentsMargins(0, 0, 0, 0); main_layout.setSpacing(0)
        
        # Toolbar
        toolbar = QWidget(); toolbar.setFixedHeight(110); toolbar.setStyleSheet("background: white; border-bottom: 1px solid #dcdcdc;")
        t_layout = QHBoxLayout(toolbar); t_layout.setContentsMargins(30, 0, 30, 0); t_layout.setSpacing(40)
        
        self.start_btn = self.create_nav_btn("Start", "▶️")
        self.stop_btn = self.create_nav_btn("Stop", "⏹️")
        self.settings_btn = self.create_nav_btn("Settings", "⚙️")
        self.add_btn = self.create_nav_btn("Add Item", "➕")
        
        t_layout.addStretch()
        t_layout.addWidget(self.start_btn); t_layout.addWidget(self.stop_btn)
        t_layout.addWidget(self.settings_btn); t_layout.addWidget(self.add_btn)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = SublerListWidget(); self.container.setStyleSheet("background: white;")
        self.list_layout = QVBoxLayout(self.container); self.list_layout.setContentsMargins(0, 0, 0, 0); self.list_layout.setSpacing(0); self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.container)

        footer = QWidget(); footer.setFixedHeight(50); footer.setStyleSheet("background: #f8f8f8; border-top: 1px solid #ccc;")
        f_layout = QHBoxLayout(footer); f_layout.setContentsMargins(20, 0, 20, 0)
        self.status_label = QLabel("0 items in queue."); self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(240); self.progress_bar.setFixedHeight(8); self.progress_bar.setTextVisible(False)
        # HATA DÜZELTME: setFrameShape kaldırıldı, stil ile çözüldü
        self.progress_bar.setStyleSheet("QProgressBar { background: #e0e0e0; border-radius: 4px; border: none; } QProgressBar::chunk { background: #007aff; border-radius: 4px; }")
        f_layout.addWidget(self.status_label); f_layout.addStretch(); f_layout.addWidget(self.progress_bar)

        main_layout.addWidget(toolbar); main_layout.addWidget(self.scroll); main_layout.addWidget(footer)
        cw = QWidget(); cw.setLayout(main_layout); self.setCentralWidget(cw)

        self.queue = []; self.threads = []; self.total_tasks = 0
        self.add_btn.clicked.connect(self.open_files); self.start_btn.clicked.connect(self.start_processing)
        self.stop_btn.clicked.connect(self.stop_processing)

    def create_nav_btn(self, text, icon_char):
        btn = QPushButton(); btn.setFixedSize(90, 90)
        btn.setText(f"{icon_char}\n\n{text}")
        btn.setStyleSheet("QPushButton { border: none; font-size: 13px; color: #555; background: transparent; font-weight: 500; } QPushButton:hover { background-color: #f0f0f0; border-radius: 15px; }")
        font = QFont(); font.setPointSize(38); btn.setFont(font)
        return btn

    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Videos", "", "Videos (*.mp4 *.mkv *.avi)")
        if files: self.add_to_queue(files)
    def add_to_queue(self, paths):
        for p in paths:
            w = FileWidget(os.path.basename(p)); self.list_layout.addWidget(w); self.queue.append((p, w))
        self.total_tasks = len(self.queue); self.status_label.setText(f"{self.total_tasks} items in queue.")
    def start_processing(self):
        if not self.queue: return
        self.start_btn.setEnabled(False); self.process_next()
    def stop_processing(self):
        for t in self.threads: t.is_running = False
        self.status_label.setText("Stopped."); self.start_btn.setEnabled(True)
    def process_next(self):
        if not self.queue:
            self.status_label.setText("Completed."); self.start_btn.setEnabled(True); self.progress_bar.setValue(100); return
        self.status_label.setText("Working..."); path, widget = self.queue.pop(0); widget.set_status("working")
        done = self.total_tasks - len(self.queue); self.progress_bar.setValue(int(((done - 1) / self.total_tasks) * 100))
        t = ConversionThread(path, widget); t.finished_signal.connect(self.on_task_finished); self.threads.append(t); t.start()
    def on_task_finished(self, t):
        t.widget.set_status("done"); self.threads.remove(t); self.process_next()
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()
    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]; self.add_to_queue(files)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # HATA DÜZELTME: macintosh -> macos
    app.setStyle("macos")
    window = MainWindow(); window.show(); sys.exit(app.exec())

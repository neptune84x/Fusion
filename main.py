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
        
        # DİL KODLARINI KORUYAN KOMUT:
        # -map_metadata 0: Tüm dosya metadatasını (global) korur
        # -map_metadata:s:a 0:g:a: Ses kanallarındaki dil kodlarını korur
        # -map_metadata:s:s 0:g:s: Altyazı kanallarındaki dil kodlarını korur
        cmd = [
            ffmpeg_path, '-i', self.full_path,
            '-map', '0', # Tüm streamleri al (Video, Audio, Subtitle)
            '-c', 'copy', # Encode etme, direkt kopyala (Hızlı)
            '-map_metadata', '0', 
            '-map_metadata:s:a', '0:s:a', 
            '-map_metadata:s:s', '0:s:s',
            '-movflags', 'use_metadata_tags',
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
        self.setFixedHeight(34)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        
        self.status_lbl = QLabel("○")
        self.status_lbl.setFixedWidth(22)
        self.status_lbl.setStyleSheet("color: #8e8e93; font-size: 15px;")
        
        self.name_label = QLabel(os.path.basename(full_path))
        self.name_label.setStyleSheet("font-size: 13px; font-weight: 500; color: #111;")
        
        self.info_label = QLabel("Loading info...") 
        self.info_label.setStyleSheet("font-size: 11px; color: #8e8e93;")
        
        layout.addWidget(self.status_lbl)
        layout.addWidget(self.name_label)
        layout.addStretch()
        layout.addWidget(self.info_label)
        
        # Dosya eklenince otomatik teknik bilgileri çek (ffprobe)
        self.get_video_info()

    def get_video_info(self):
        ffprobe_path = get_resource_path('ffprobe')
        cmd = [
            ffprobe_path, '-v', 'error', '-show_entries', 
            'stream=codec_type:stream_tags=language', '-of', 'json', self.full_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(result.stdout)
            audio = []
            subs = []
            for s in data.get('streams', []):
                lang = s.get('tags', {}).get('language', 'und')
                if s['codec_type'] == 'audio': audio.append(lang)
                elif s['codec_type'] == 'subtitle': subs.append(lang)
            
            info_str = ""
            if audio: info_str += f"Audio: {', '.join(audio)} "
            if subs: info_str += f"Subs: {', '.join(subs)}"
            self.info_label.setText(info_str if info_str else "No metadata")
        except:
            self.info_label.setText("Unknown info")

    def set_status(self, mode):
        self.status = mode
        chars = {"working": "↻", "done": "✓", "waiting": "○"}
        colors = {"working": "#ff9500", "done": "#34c759", "waiting": "#8e8e93"}
        self.status_lbl.setText(chars.get(mode, "○"))
        self.status_lbl.setStyleSheet(f"color: {colors.get(mode, '#8e8e93')}; font-size: 16px; font-weight: bold;")

    def update_style(self):
        bg = "#007aff" if self.is_selected else "transparent"
        txt = "white" if self.is_selected else "#111"
        info_txt = "#e0e0e0" if self.is_selected else "#8e8e93"
        self.setStyleSheet(f"background-color: {bg}; border: none;")
        self.name_label.setStyleSheet(f"color: {txt}; font-size: 13px;")
        self.info_label.setStyleSheet(f"color: {info_txt}; font-size: 11px;")

    def mousePressEvent(self, event):
        if not (event.modifiers() & Qt.KeyboardModifier.MetaModifier):
            self.parent_list.clear_selection()
        self.is_selected = not self.is_selected
        self.update_style()

# (SublerListWidget ve MainWindow sınıfları önceki kodla aynı kalacak şekilde devam eder...)

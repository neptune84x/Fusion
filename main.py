import sys, os, subprocess, json, glob, re, shutil
try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                                 QWidget, QLabel, QProgressBar, QScrollArea, 
                                 QFrame, QPushButton, QFileDialog, QMenu)
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

    def force_italics_on_text(self, text):
        """
        Metin içinde halihazırda <i> yoksa ve ASS'den geliyorsa 
        Infuse için zorla italik etiketlerini ekler.
        """
        if not text: return ""
        # 1. ASS/SSA temizliği
        text = re.sub(r'\{\\i1\}|\\i1', '<i>', text)
        text = re.sub(r'\{\\i0\}|\\i0', '</i>', text)
        text = re.sub(r'\{[^\}]*\}', '', text)
        
        # 2. Eğer satırda hiç italik etiketi yoksa ama stil 'Italics' ise 
        # (Bu kontrolü process_file_cleaning içinde stile göre yapacağız)
        return text.strip()

    def process_file_cleaning(self, file_path, is_ass_source=False):
        try:
            with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                lines = f.readlines()
            
            new_lines = []
            for line in lines:
                if "-->" not in line and not line.strip().isdigit():
                    # Eğer kaynak ASS ise ve stil isminde Italic geçiyorsa
                    # (Senin dosyanın formatı: Dialogue: ...,Italics,...)
                    if is_ass_source and (",Italics," in line or ",Italic," in line):
                        # Metin kısmını ayır ve italik ekle
                        parts = line.split(",,", 1)
                        if len(parts) > 1:
                            cleaned_content = self.force_italics_on_text(parts[1])
                            if not cleaned_content.startswith("<i>"):
                                cleaned_content = f"<i>{cleaned_content}</i>"
                            new_lines.append(cleaned_content + "\n")
                        else:
                            new_lines.append(self.force_italics_on_text(line) + "\n")
                    else:
                        new_lines.append(self.force_italics_on_text(line) + "\n")
                else:
                    new_lines.append(line)
            
            with open(file_path, 'w', encoding='utf-8-sig') as f:
                f.writelines(new_lines)
        except: pass

    def run(self):
        ffmpeg = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'
        ffprobe = os.path.join(sys._MEIPASS, 'ffprobe') if hasattr(sys, '_MEIPASS') else 'ffprobe'
        base_path = os.path.splitext(self.input_file)[0]
        temp_dir_path = base_path + ".fusiontemp"
        
        if os.path.exists(temp_dir_path): shutil.rmtree(temp_dir_path)
        os.makedirs(temp_dir_path, exist_ok=True)
        
        output_file = base_path + "_Fusion.mkv"

        try:
            probe_cmd = [ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_streams', self.input_file]
            info = json.loads(subprocess.check_output(probe_cmd))
        except: info = {}
        
        internal_subs = []
        for s in info.get('streams', []):
            if s.get('codec_type') == 'subtitle':
                lang = s.get('tags', {}).get('language', 'und')
                internal_subs.append({'index': s['index'], 'lang': lang})

        cleaned_list = []
        # --- İÇ ALTYAZILAR ---
        for i, sub in enumerate(internal_subs):
            temp_sub_path = os.path.join(temp_dir_path, f"int_{i}.srt")
            subprocess.run([ffmpeg, '-y', '-i', self.input_file, '-map', f"0:{sub['index']}", '-f', 'srt', temp_sub_path], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.process_file_cleaning(temp_sub_path, is_ass_source=False)
            cleaned_list.append({'path': temp_sub_path, 'lang': sub['lang']})

        # --- DIŞ ALTYAZILAR (Senin Önerdiğin Çift Aşamalı Dönüşüm) ---
        if self.load_external:
            for f in glob.glob(base_path + "*.*"):
                ext_check = f.lower()
                if (ext_check.endswith('.srt') or ext_check.endswith('.ass')) and f != self.input_file:
                    temp_ext_path = os.path.join(temp_dir_path, f"ext_{len(cleaned_list)}.srt")
                    
                    if ext_check.endswith('.ass'):
                        # 1. Aşama: ASS -> Temizlenmiş ASS (FFmpeg ile)
                        clean_ass = os.path.join(temp_dir_path, "inter_clean.ass")
                        subprocess.run([ffmpeg, '-y', '-i', f, '-f', 'ass', clean_ass], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        # 2. Aşama: Temiz ASS -> SRT
                        subprocess.run([ffmpeg, '-y', '-i', clean_ass, '-f', 'srt', temp_ext_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        # 3. Aşama: Manuel İtalik Enjeksiyonu
                        self.process_file_cleaning(temp_ext_path, is_ass_source=True)
                    else:
                        shutil.copy2(f, temp_ext_path)
                        self.process_file_cleaning(temp_ext_path, is_ass_source=False)
                    
                    match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', ext_check)
                    cleaned_list.append({'path': temp_ext_path, 'lang': match.group(1) if match else 'und'})

        # MUXING
        cmd = [ffmpeg, '-y', '-i', self.input_file]
        for c in cleaned_list: cmd.extend(['-i', c['path']])
        cmd.extend(['-map', '0:v', '-map', '0:a?'])
        
        l_map = {"tr":"tur","en":"eng","ru":"rus","jp":"jpn","de":"ger","fr":"fra","es":"spa","it":"ita"}
        for i, c in enumerate(cleaned_list):
            cmd.extend(['-map', str(i + 1)])
            cmd.extend([f"-c:s:{i}", "subrip", f"-metadata:s:s:{i}", f"language={l_map.get(c['lang'], c['lang'])}", f"-metadata:s:s:{i}", "title="])

        cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-map_metadata', '-1', '-map_chapters', '0', output_file])
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if os.path.exists(temp_dir_path): shutil.rmtree(temp_dir_path, ignore_errors=True)
        self.finished_signal.emit(self)

# (GUI sınıfları: FileWidget, SublerListWidget, MainWindow değişmeden devam eder...)

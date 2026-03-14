import sys, os, subprocess, json, glob, re, shutil
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
    
    def __init__(self, input_file, widget, load_external=True, output_format="mkv"):
        super().__init__()
        self.input_file = input_file
        self.widget = widget
        self.load_external = load_external
        self.output_format = output_format

    def get_bin(self, name):
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, "internal", name)
        return name

    def clean_and_force_srt_italics(self, text):
        if not text: return ""
        text = re.sub(r'\{\\i1\}|\\i1|<i>|<I>', '', text)
        text = re.sub(r'\{\\i0\}|\\i0|</i>|</I>', '', text)
        text = re.sub(r'\{[^\}]*\}', '', text)
        return f"<i>{text.strip()}</i>"

    def convert_to_webvtt(self, srt_path, vtt_path):
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(vtt_path, 'w', encoding='utf-8') as f:
                f.write("WEBVTT\n\n")
                for line in lines:
                    f.write(line.replace(',', '.'))
            return True
        except: return False

    def process_ass_to_srt_with_italics(self, ass_path, srt_output_path):
        try:
            with open(ass_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                lines = f.readlines()
            srt_content = []; counter = 1
            for line in lines:
                if line.startswith("Dialogue:"):
                    parts = line.split(',', 9)
                    if len(parts) >= 10:
                        start_time = parts[1].replace('.', ',') + "0"
                        end_time = parts[2].replace('.', ',') + "0"
                        style = parts[3]
                        text = parts[9].strip()
                        if "italic" in style.lower() or "{\\i1}" in text:
                            text = self.clean_and_force_srt_italics(text)
                        else:
                            text = re.sub(r'\{[^\}]*\}', '', text).strip()
                        if text:
                            srt_content.append(f"{counter}\n0{start_time[:-1]} --> 0{end_time[:-1]}\n{text}\n\n")
                            counter += 1
            with open(srt_output_path, 'w', encoding='utf-8-sig') as f:
                f.writelines(srt_content)
        except:
            ffmpeg = self.get_bin('ffmpeg')
            subprocess.run([ffmpeg, '-y', '-i', ass_path, srt_output_path], capture_output=True)

    def run(self):
        ffmpeg = self.get_bin('ffmpeg')
        ffprobe = self.get_bin('ffprobe')
        mp4box = self.get_bin('mp4box')
        
        base_path = os.path.splitext(self.input_file)[0]
        temp_dir = base_path + ".fusiontemp"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        output_ext = "mp4" if self.output_format == "mp4_vtt" else "mkv"
        output_file = f"{base_path}_Fusion.{output_ext}"
        
        # 1. Analiz
        try:
            probe_cmd = [ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_streams', self.input_file]
            info = json.loads(subprocess.check_output(probe_cmd))
        except: info = {}
        
        internal_subs = [s for s in info.get('streams', []) if s.get('codec_type') == 'subtitle']
        l_map = {"tr":"tur","en":"eng","ru":"rus","jp":"jpn","de":"ger","fr":"fra","es":"spa","it":"ita"}
        
        # 2. Altyazı Hazırlama
        cleaned_list = []
        for i, sub in enumerate(internal_subs):
            lang = sub.get('tags', {}).get('language', 'und')
            temp_srt = os.path.join(temp_dir, f"int_{i}.srt")
            subprocess.run([ffmpeg, '-y', '-i', self.input_file, '-map', f"0:{sub['index']}", '-f', 'srt', temp_srt], capture_output=True)
            
            final_sub = temp_srt
            if self.output_format == "mp4_vtt":
                temp_vtt = temp_srt.replace('.srt', '.vtt')
                if self.convert_to_webvtt(temp_srt, temp_vtt): final_sub = temp_vtt
            cleaned_list.append({'path': final_sub, 'lang': l_map.get(lang, lang)})

        if self.load_external:
            for f in glob.glob(base_path + "*.*"):
                if f.lower().endswith(('.srt', '.ass')) and f != self.input_file:
                    temp_srt = os.path.join(temp_dir, f"ext_{len(cleaned_list)}.srt")
                    if f.lower().endswith('.ass'): self.process_ass_to_srt_with_italics(f, temp_srt)
                    else: shutil.copy2(f, temp_srt)
                    
                    final_sub = temp_srt
                    if self.output_format == "mp4_vtt":
                        temp_vtt = temp_srt.replace('.srt', '.vtt')
                        self.convert_to_webvtt(temp_srt, temp_vtt)
                        final_sub = temp_vtt
                    
                    match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', f.lower())
                    lang = match.group(1) if match else "und"
                    cleaned_list.append({'path': final_sub, 'lang': l_map.get(lang, lang)})

        # 3. Muxing (Chapter ve Metadata Koruma)
        if self.output_format == "mp4_vtt":
            temp_mp4 = os.path.join(temp_dir, "temp_remux.mp4")
            # Adım A: Video, Ses, Chapter ve Metadata aktarımı
            subprocess.run([ffmpeg, '-y', '-i', self.input_file, '-map', '0:v:0', '-map', '0:a?', 
                           '-c', 'copy', '-map_metadata', '0', '-map_chapters', '0', temp_mp4], capture_output=True)
            
            # Adım B: MP4Box ile Apple uyumlu paketleme
            # -ipod bayrağı ve doğru WebVTT eşlemesi Apple cihazlar için kritiktir
            box_cmd = [mp4box, "-ipod", "-add", temp_mp4]
            for c in cleaned_list:
                # 'wvtt' formatı Apple'ın native olarak tanıdığı formattır
                box_cmd.extend(["-add", f"{c['path']}:lang={c['lang']}:fmt=wvtt"])
            box_cmd.extend(["-new", output_file])
            subprocess.run(box_cmd, capture_output=True)
        else:
            # Standart MKV (Tüm metadata ve chapterlar dahil)
            cmd = [ffmpeg, '-y', '-i', self.input_file]
            for c in cleaned_list: cmd.extend(['-i', c['path']])
            cmd.extend(['-map', '0:v:0', '-map', '0:a?'])
            for i, c in enumerate(cleaned_list):
                cmd.extend(['-map', str(i + 1), f"-c:s:{i}", "subrip", f"-metadata:s:s:{i}", f"language={c['lang']}"])
            cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-map_metadata', '0', '-map_chapters', '0', output_file])
            subprocess.run(cmd, capture_output=True)

        if os.path.exists(temp_dir): shutil.rmtree(temp_dir, ignore_errors=True)
        self.finished_signal.emit(self)

# (MainWindow, FileWidget ve SublerListWidget sınıfları bir önceki tam sürümdeki ile aynıdır)
# Sadece MainWindow.show_about içindeki sürüm numarasını v0.1.1 yapman yeterlidir.

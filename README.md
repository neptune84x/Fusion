# 🌀 Fusion

![macOS](https://img.shields.io/badge/platform-macOS-000000.svg?style=for-the-badge&logo=apple&logoColor=white)
![Version](https://img.shields.io/badge/version-0.2.0-blue.svg?style=for-the-badge)
![FFmpeg](https://img.shields.io/badge/engine-FFmpeg-0078D4.svg?style=for-the-badge&logo=ffmpeg&logoColor=white)

**Fusion** is a streamlined macOS utility designed to optimize media containers for the Apple ecosystem (Infuse, Apple TV, and macOS). It focuses on standardizing subtitle formats and media streams to ensure perfect playback without quality loss.

---

## 🆕 What's New in v0.2.0

- **Matroska (SubRip) Support:** Enhanced MKV output format with specialized SubRip subtitle mapping.
- **Improved Chapter Preservation:** Refined logic to ensure chapter titles and markers remain intact during the remuxing process.
- **Stable Release:** Optimized internal processing workflows for faster and more reliable conversion.

---

## ✨ Key Features

### 🛡 Smart Subtitle Handling
- **Italics Preservation:** Automatically detects italic styles in ASS/SSA files and converts them into Infuse-compliant tags.
- **Clean Output:** Strips unnecessary styling and fonts to produce standardized, easy-to-read subtitle tracks.
- **Auto-Mapping:** Automatically pairs external `.srt` or `.ass` files with your video based on language suffixes.

### ⚡ Lossless Remuxing
- **No Quality Loss:** Copies original video and audio streams directly without re-encoding.
- **Metadata Integrity:** Keeps your chapters, audio tags, and global metadata exactly as they should be.

###  Native macOS UI
- **Modern Design:** A clean PyQt6 interface with native macOS aesthetics.
- **Drag & Drop:** Simply drop your files into the app to start building your queue.
- **Batch Actions:** Manage multiple files at once with intuitive selection and a native menu bar.

---

## 🚀 How to Use

1. **Launch:** Open the Fusion app.
2. **Import:** Drag your video files into the window or click **"Add Item"**.
3. **Configure:** Choose your output format (**Matroska (SubRip)** or **Apple MP4**) from the **Settings** menu.
4. **Process:** Click **Start** to optimize your media in seconds.
5. **Clean Up:** Use the **Edit** menu to clear completed tasks or remove items from the list.

---

> **Note:** Fusion is specifically designed to solve common metadata and subtitle issues (like missing italics) encountered by high-fidelity media players on Apple devices.

---
*Optimized for high-fidelity media management on macOS.*

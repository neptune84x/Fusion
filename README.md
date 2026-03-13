🌀 Fusion
Fusion is a high-performance macOS utility designed to optimize media containers for Apple ecosystems (Infuse, Apple TV, macOS). It focuses on standardizing complex subtitle formats and media streams without compromising quality.

✨ Key Features
🛡 Advanced Subtitle Engine

Hard-Coded Italics: Scans ASS/SSA files for italic codes ({\i1}, Italics styles) and injects Infuse-compliant <i> tags directly into the output.

Dynamic Cleanup: Strips unnecessary styling data (fonts, colors, positioning) to produce clean, standardized SRT tracks.

Auto-Discovery: Automatically detects and maps external .ass and .srt files based on language suffixes (e.g., .tr, .en, .ru).

⚡ Lossless Optimization

Zero Transcoding: Muxes original video (HEVC/H.264) and audio (Atmos/AAC/DTS) streams directly (Remuxing).

Metadata Integrity: Preserves chapter markers, audio language tags, and global metadata during the conversion process.

 Native macOS Experience

Modern Interface: Built with PyQt6 featuring a native macOS "Squircle" icon and modern UI aesthetics.

Drag & Drop: Seamless queue management by dropping files directly into the workspace.

Batch Management: Native "Rubber Band" selection logic for managing multiple items simultaneously.

Integrated Menu Bar: Full support for standard macOS menus (File, Edit, Settings).

🛠 Technical Stack
Engine: FFmpeg & FFprobe (Optimized for ARM64 and Intel).

Frontend: Python 3.10+ with an asynchronous PyQt6 architecture.

Build Pipeline: Automated CI/CD via GitHub Actions for .app bundling and .icns generation.

🚀 How to Use
Launch the application.

Drag your video files into the main window or use the "Add Item" button.

Ensure "Load External Subtitles" is enabled in the Settings menu for external tracks.

Click Start and let Fusion handle the optimization in seconds.

Note: Fusion is specifically calibrated to solve the "missing italics" issue often encountered by Infuse users in anime and foreign language content.

This README is updated to reflect the latest stable version of the project.

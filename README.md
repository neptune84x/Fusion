# Fusion 🌀

**Fusion** is a lightweight, high-performance macOS utility designed to optimize media containers for Apple ecosystems (Infuse, Apple TV, macOS). It focuses on high-fidelity batch processing of video files.

## Key Features
- **Batch MKV Optimization:** Seamlessly muxes multiple video files into high-quality MKV containers.
- **Subtitles Management:** - Automatically converts internal and external subtitles (SRT/ASS) into standardized SRT format.
  - **Smart Filtering:** Strips unnecessary styles (bold, colors, fonts) while preserving essential *italics*.
- **Language Awareness:** Preserves and maps audio/subtitle language metadata correctly.
- **High-Fidelity Ready:** Maintains original video (HEVC/H.264) and audio (Atmos/AAC) streams without re-encoding.

## macOS Integration
- Native "Squircle" application icon.
- Standard macOS Menu Bar (File, Edit, Settings).
- Drag & Drop queue management.
- Multi-item "Rubber Band" selection logic.

## Technical Stack
- **Engine:** FFmpeg & FFprobe (Bundled for ARM64/Intel).
- **GUI:** Python 3.10 with PyQt6.
- **Deployment:** Automated CI/CD via GitHub Actions.

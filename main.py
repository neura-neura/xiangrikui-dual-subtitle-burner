# Complete Python program with GUI to play videos with two simultaneous subtitles and export with burned-in subtitles.
# Author: neura-neura
# Date: September 04, 2025.

# Dependency installation instructions:
# 1. Install Python (version 3.8 or higher recommended).
# 2. Install the necessary libraries via pip:
#    pip install pyqt5 pysubs2
# 3. Install FFmpeg manually (required for exporting videos with burned-in subtitles):
#    - On Windows: Download from https://ffmpeg.org/download.html and add to PATH.
#    - On macOS: brew install ffmpeg (if using Homebrew).
#    - On Linux: sudo apt install ffmpeg (on Ubuntu/Debian) or equivalent.
# Note: Ensure FFmpeg is in the system PATH so subprocess can find it.
# Additional (for Windows): If you experience errors playing videos (like 0x80040266), install LAV Filters from https://github.com/Nevcairiel/LAVFilters/releases for codec support.

import sys
import os
import subprocess
import pysubs2
import copy
import platform  # To detect OS and hide subprocess in Windows

from PyQt5 import QtCore, QtGui, QtWidgets, QtMultimedia, QtMultimediaWidgets
from PyQt5.QtWidgets import QMainWindow, QAction, QToolBar, QSlider, QFileDialog, QMessageBox, QDialog, QLabel, QDoubleSpinBox, QPushButton, QVBoxLayout, QColorDialog, QFontDialog, QCheckBox, QProgressDialog, QSpinBox
from PyQt5.QtGui import QColor, QResizeEvent, QFontDatabase, QIcon
from PyQt5.QtCore import QProcess

# To hide subprocess windows in Windows
if platform.system() == 'Windows':
    from subprocess import CREATE_NO_WINDOW

def resource_path(relative_path):
    """Gets the absolute path to the resource, works both in development and in the packaged exe."""
    try:
        # PyInstaller creates a temporary folder and stores the path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class VideoGraphicsView(QtWidgets.QGraphicsView):
    """Subclass of QGraphicsView to adjust the video when resizing the window."""
    def resizeEvent(self, event: QResizeEvent):
        self.fitInView(self.sceneRect(), QtCore.Qt.KeepAspectRatio)
        super().resizeEvent(event)

class SubtitleSettingsDialog(QDialog):
    """Dialog to configure subtitle styles (font, color, size, position, outline)."""
    def __init__(self, parent, sub_style: pysubs2.SSAStyle, margin: int, sub_item: QtWidgets.QGraphicsTextItem, sub_number: int):
        super().__init__(parent)
        self.setWindowTitle(f"Subtitle {sub_number} Settings")
        self.sub_style = sub_style
        self.margin = margin
        self.sub_item = sub_item

        layout = QVBoxLayout()

        # Label and button for font and size
        font_label = QLabel("Font and Size:")
        self.font_button = QPushButton("Select Font")
        self.font_button.clicked.connect(self.select_font)
        layout.addWidget(font_label)
        layout.addWidget(self.font_button)

        # Label and button for color
        color_label = QLabel("Color:")
        self.color_button = QPushButton("Select Color")
        self.color_button.clicked.connect(self.select_color)
        layout.addWidget(color_label)
        layout.addWidget(self.color_button)

        # Checkbox for outline
        self.outline_check = QCheckBox("Enable outline")
        self.outline_check.setChecked(self.sub_style.outline > 0)
        layout.addWidget(self.outline_check)

        # Spinbox for outline thickness (with decimals)
        thickness_label = QLabel("Outline thickness:")
        self.thickness_spin = QDoubleSpinBox()
        self.thickness_spin.setRange(0, 10)
        self.thickness_spin.setSingleStep(0.5)
        self.thickness_spin.setValue(float(self.sub_style.outline))
        layout.addWidget(thickness_label)
        layout.addWidget(self.thickness_spin)

        # Button for outline color
        outline_color_label = QLabel("Outline color:")
        self.outline_color_button = QPushButton("Select Color")
        self.outline_color_button.clicked.connect(self.select_outline_color)
        layout.addWidget(outline_color_label)
        layout.addWidget(self.outline_color_button)

        # Spinbox for vertical margin (position from bottom)
        margin_label = QLabel("Margin from bottom (pixels):")
        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(0, 1000)
        self.margin_spin.setValue(self.margin)
        layout.addWidget(margin_label)
        layout.addWidget(self.margin_spin)

        # Accept button
        ok_button = QPushButton("Accept")
        ok_button.clicked.connect(self.accept)
        layout.addWidget(ok_button)

        self.setLayout(layout)

        # Initial outline color
        oc = self.sub_style.outline_colour
        self.outline_color = QColor(oc.r, oc.g, oc.b)

    def select_font(self):
        font, ok = QFontDialog.getFont(self.sub_item.font(), self)
        if ok:
            self.sub_item.setFont(font)
            self.sub_style.fontname = font.family()
            self.sub_style.fontsize = font.pointSize()
            self.parent().apply_style_to_item(self.sub_item, self.sub_style)

    def select_color(self):
        color = QColorDialog.getColor(self.sub_item.defaultTextColor(), self)
        if color.isValid():
            self.sub_item.setDefaultTextColor(color)
            self.sub_style.primary_colour = pysubs2.Color(color.red(), color.green(), color.blue(), 0)  # Opaque
            self.parent().apply_style_to_item(self.sub_item, self.sub_style)

    def select_outline_color(self):
        color = QColorDialog.getColor(self.outline_color, self)
        if color.isValid():
            self.outline_color = color
            self.sub_style.outline_colour = pysubs2.Color(color.red(), color.green(), color.blue(), 0)

    def accept(self):
        self.margin = self.margin_spin.value()
        self.sub_style.marginv = self.margin
        if self.outline_check.isChecked():
            self.sub_style.outline = self.thickness_spin.value()
        else:
            self.sub_style.outline = 0
        super().accept()

class MainWindow(QMainWindow):
    """Main window of the video player with support for two subtitles."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Xiangrikui - Dual Subtitle Burner")
        self.resize(800, 600)

        # Initialize media player
        self.player = QtMultimedia.QMediaPlayer(self)
        self.video_item = QtMultimediaWidgets.QGraphicsVideoItem()
        self.player.setVideoOutput(self.video_item)

        # Graphic scene for video and subtitles
        self.scene = QtWidgets.QGraphicsScene(self)
        self.scene.addItem(self.video_item)

        # Graphic view (subclass for resize handling)
        self.view = VideoGraphicsView(self.scene)
        self.setCentralWidget(self.view)

        # Items for subtitles (text overlay)
        self.sub1_item = QtWidgets.QGraphicsTextItem()
        self.sub1_item.setAcceptHoverEvents(False)  # Non-interactive
        self.scene.addItem(self.sub1_item)

        self.sub2_item = QtWidgets.QGraphicsTextItem()
        self.sub2_item.setAcceptHoverEvents(False)  # Non-interactive
        self.scene.addItem(self.sub2_item)

        # Detect available fonts
        font_db = QFontDatabase()

        # Initial styles for subtitles (using pysubs2.SSAStyle)
        self.sub1_style = pysubs2.SSAStyle()
        self.sub1_style.fontname = "SimSun" if "SimSun" in font_db.families() else "Arial"
        self.sub1_style.fontsize = 12
        self.sub1_style.primary_colour = pysubs2.Color(255, 255, 255, 0)  # White opaque
        self.sub1_style.outline_colour = pysubs2.Color(0, 0, 0, 0)  # Black opaque for outline
        self.sub1_style.outline = 0.5  # Outline enabled by default
        self.sub1_style.shadow = 0
        self.sub1_style.borderstyle = 1
        self.sub1_style.alignment = 2  # Bottom center
        self.sub1_margin = 35  # Initial margin from bottom
        self.sub1_style.marginv = self.sub1_margin
        self.apply_style_to_item(self.sub1_item, self.sub1_style)

        self.sub2_style = pysubs2.SSAStyle()
        self.sub2_style.fontname = "Gotham Medium" if "Gotham Medium" in font_db.families() else "Arial"
        self.sub2_style.fontsize = 16
        self.sub2_style.primary_colour = pysubs2.Color(255, 255, 255, 0)  # White opaque
        self.sub2_style.outline_colour = pysubs2.Color(0, 0, 0, 0)  # Black opaque for outline
        self.sub2_style.outline = 0.5  # Outline enabled by default
        self.sub2_style.shadow = 0
        self.sub2_style.borderstyle = 1
        self.sub2_style.alignment = 2  # Bottom center
        self.sub2_margin = 5  # Initial margin (lower than the first)
        self.sub2_style.marginv = self.sub2_margin
        self.apply_style_to_item(self.sub2_item, self.sub2_style)

        # Loaded files
        self.video_file = None
        self.subs1 = None
        self.subs2 = None

        # For the export process
        self.export_process = None
        self.video_duration = 0.0

        # Current preset
        self.current_preset = "none"

        # Detect support for hardware acceleration
        self.hardware_encoder = self.detect_hardware_encoder()

        # Create playback controls
        self.create_toolbar()

        # Create menu
        self.create_menu()

        # Connect signals (after creating the slider)
        self.player.positionChanged.connect(self.update_subtitles)
        self.player.metaDataAvailableChanged.connect(self.update_scene_rect)
        self.player.durationChanged.connect(self.update_slider_range)
        self.player.positionChanged.connect(self.slider.setValue)
        self.player.error.connect(self.handle_player_error)  # New connection to handle errors

        # Apply initial preset
        self.set_preset("none")

    def detect_hardware_encoder(self):
        """Detects if there is support for hardware encoders (GPU)."""
        try:
            if platform.system() == 'Windows':
                output = subprocess.check_output(["ffmpeg", "-encoders"], creationflags=CREATE_NO_WINDOW, timeout=5).decode('utf-8', 'ignore')
            else:
                output = subprocess.check_output(["ffmpeg", "-encoders"], timeout=5).decode('utf-8', 'ignore')
            if "h264_nvenc" in output:
                return "nvenc"  # NVIDIA
            elif "h264_amf" in output:
                return "amf"  # AMD
            elif "h264_qsv" in output:
                return "qsv"  # Intel Quick Sync
            else:
                return None
        except Exception:
            return None

    def handle_player_error(self, error):
        """Handles player errors, such as codec issues."""
        if error == QtMultimedia.QMediaPlayer.FormatError:
            QMessageBox.warning(self, "Format Error", "Cannot play the video. Install LAV Filters for codec support on Windows.")
        else:
            QMessageBox.warning(self, "Error", f"Playback error: {self.player.errorString()}")

    def apply_style_to_item(self, item: QtWidgets.QGraphicsTextItem, style: pysubs2.SSAStyle):
        """Applies the SSA style to a QGraphicsTextItem for preview."""
        font = QtGui.QFont(style.fontname, int(style.fontsize))
        item.setFont(font)
        color = style.primary_colour
        item.setDefaultTextColor(QColor(color.r, color.g, color.b))  # Corrected to RGB

        # Note: The outline is not previewed in the interface, only in the export.

    def update_scene_rect(self, available: bool):
        """Updates the scene rectangle based on the video metadata."""
        if available:
            resolution = self.player.metaData(QtMultimedia.QMediaMetaData.Resolution)
            if resolution:
                self.video_item.setSize(QtCore.QSizeF(resolution))
                self.scene.setSceneRect(0, 0, resolution.width(), resolution.height())
                self.view.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)

    def create_toolbar(self):
        """Creates the toolbar with playback controls."""
        toolbar = QToolBar()
        self.addToolBar(QtCore.Qt.BottomToolBarArea, toolbar)

        # Control buttons
        play_action = QAction("Play", self)
        play_action.triggered.connect(self.player.play)
        toolbar.addAction(play_action)

        pause_action = QAction("Pause", self)
        pause_action.triggered.connect(self.player.pause)
        toolbar.addAction(pause_action)

        stop_action = QAction("Stop", self)
        stop_action.triggered.connect(self.player.stop)
        toolbar.addAction(stop_action)

        backward_action = QAction("<< 10s", self)
        backward_action.triggered.connect(lambda: self.player.setPosition(max(0, self.player.position() - 10000)))
        toolbar.addAction(backward_action)

        forward_action = QAction(">> 10s", self)
        forward_action.triggered.connect(lambda: self.player.setPosition(self.player.position() + 10000))
        toolbar.addAction(forward_action)

        # Button to export preview
        preview_action = QAction("Export Preview 10s", self)
        preview_action.triggered.connect(self.export_preview)
        toolbar.addAction(preview_action)

        # Progress bar
        self.slider = QSlider(QtCore.Qt.Horizontal, self)
        self.slider.sliderMoved.connect(self.player.setPosition)
        toolbar.addWidget(self.slider)

    def update_slider_range(self, duration: int):
        """Updates the maximum range of the progress bar."""
        self.slider.setRange(0, duration)

    def create_menu(self):
        """Creates the menu to load files and settings."""
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")

        self.load_video_action = QAction("Load Video", self)
        self.load_video_action.triggered.connect(self.load_video)
        file_menu.addAction(self.load_video_action)

        self.load_sub1_action = QAction("Load Subtitle 1", self)
        self.load_sub1_action.triggered.connect(self.load_sub1)
        file_menu.addAction(self.load_sub1_action)

        self.load_sub2_action = QAction("Load Subtitle 2", self)
        self.load_sub2_action.triggered.connect(self.load_sub2)
        file_menu.addAction(self.load_sub2_action)

        export_action = QAction("Export Video with Subtitles", self)
        export_action.triggered.connect(self.export_video)
        file_menu.addAction(export_action)

        settings_menu = menu_bar.addMenu("Settings")

        self.sub1_settings_action = QAction("Configure Subtitle 1", self)
        self.sub1_settings_action.triggered.connect(self.show_sub1_settings)
        settings_menu.addAction(self.sub1_settings_action)

        self.sub2_settings_action = QAction("Configure Subtitle 2", self)
        self.sub2_settings_action.triggered.connect(self.show_sub2_settings)
        settings_menu.addAction(self.sub2_settings_action)

        # Submenu for position presets
        presets_menu = settings_menu.addMenu("Position Presets")

        none_preset_action = QAction("None (both subtitles)", self)
        none_preset_action.triggered.connect(lambda: self.set_preset("none"))
        presets_menu.addAction(none_preset_action)

        chinese_preset_action = QAction("Video with Chinese subtitles (only Subtitle 2)", self)
        chinese_preset_action.triggered.connect(lambda: self.set_preset("chinese"))
        presets_menu.addAction(chinese_preset_action)

        english_preset_action = QAction("Video with English subtitles (only Subtitle 1)", self)
        english_preset_action.triggered.connect(lambda: self.set_preset("english"))
        presets_menu.addAction(english_preset_action)

    def set_preset(self, preset: str):
        """Adjusts margins and enables/disables options according to the selected preset."""
        self.current_preset = preset
        if preset == "none":
            self.sub1_margin = 35
            self.sub2_margin = 5
            self.sub1_style.marginv = self.sub1_margin
            self.sub2_style.marginv = self.sub2_margin
            self.load_sub1_action.setEnabled(True)
            self.load_sub2_action.setEnabled(True)
            self.sub1_settings_action.setEnabled(True)
            self.sub2_settings_action.setEnabled(True)
        elif preset == "chinese":
            self.sub2_margin = 25
            self.sub2_style.marginv = self.sub2_margin
            self.load_sub1_action.setEnabled(False)
            self.load_sub2_action.setEnabled(True)
            self.sub1_settings_action.setEnabled(False)
            self.sub2_settings_action.setEnabled(True)
            self.subs1 = None  # Reset subtitle 1
            self.sub1_item.setPlainText("")  # Clear text
        elif preset == "english":
            self.sub1_margin = 35
            self.sub1_style.marginv = self.sub1_margin
            self.load_sub1_action.setEnabled(True)
            self.load_sub2_action.setEnabled(False)
            self.sub1_settings_action.setEnabled(True)
            self.sub2_settings_action.setEnabled(False)
            self.subs2 = None  # Reset subtitle 2
            self.sub2_item.setPlainText("")  # Clear text
        # Update preview if necessary
        self.update_subtitles(self.player.position())

    def load_video(self):
        """Loads a video file."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Video", "", "Videos (*.mp4 *.mkv *.avi)")
        if file_path:
            try:
                self.video_file = file_path
                self.player.setMedia(QtMultimedia.QMediaContent(QtCore.QUrl.fromLocalFile(file_path)))
                # Check for immediate error after setMedia
                if self.player.error() != QtMultimedia.QMediaPlayer.NoError:
                    raise RuntimeError(self.player.errorString())
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Error loading video: {str(e)}\nIf error 0x80040266, install LAV Filters for codecs.")

    def load_sub1(self):
        """Loads the first subtitle file."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Subtitle 1", "", "Subtitles (*.srt *.vtt)")
        if file_path:
            try:
                self.subs1 = pysubs2.load(file_path)
                # Apply style
                style_name = "Sub1"
                self.subs1.styles[style_name] = self.sub1_style
                for event in self.subs1:
                    event.style = style_name
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Error loading subtitle 1: {str(e)}")

    def load_sub2(self):
        """Loads the second subtitle file."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Subtitle 2", "", "Subtitles (*.srt *.vtt)")
        if file_path:
            try:
                self.subs2 = pysubs2.load(file_path)
                # Apply style
                style_name = "Sub2"
                self.subs2.styles[style_name] = self.sub2_style
                for event in self.subs2:
                    event.style = style_name
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Error loading subtitle 2: {str(e)}")

    def update_subtitles(self, position: int):
        """Updates subtitle texts based on the current video position."""
        # Subtitle 1
        text1 = ""
        if self.subs1:
            for event in self.subs1:
                if event.start <= position <= event.end:
                    text1 += event.plaintext + "\n"
        self.sub1_item.setPlainText(text1.strip())

        # Subtitle 2
        text2 = ""
        if self.subs2:
            for event in self.subs2:
                if event.start <= position <= event.end:
                    text2 += event.plaintext + "\n"
        self.sub2_item.setPlainText(text2.strip())

        # Position the subtitles
        scene_height = self.scene.height()
        scene_width = self.scene.width()

        if scene_height > 0 and scene_width > 0:
            # Position for sub1 (higher if larger margin, adjusting for outline)
            sub1_rect = self.sub1_item.boundingRect()
            outline_adjust1 = self.sub1_style.outline * 2
            x1 = (scene_width - sub1_rect.width()) / 2
            y1 = scene_height - sub1_rect.height() - self.sub1_margin - outline_adjust1
            self.sub1_item.setPos(x1, y1)

            # Position for sub2
            sub2_rect = self.sub2_item.boundingRect()
            outline_adjust2 = self.sub2_style.outline * 2
            x2 = (scene_width - sub2_rect.width()) / 2
            y2 = scene_height - sub2_rect.height() - self.sub2_margin - outline_adjust2
            self.sub2_item.setPos(x2, y2)

    def show_sub1_settings(self):
        """Shows the settings dialog for subtitle 1."""
        dialog = SubtitleSettingsDialog(self, self.sub1_style, self.sub1_margin, self.sub1_item, 1)
        if dialog.exec_():
            self.sub1_margin = dialog.margin
            self.sub1_style.marginv = self.sub1_margin
            self.apply_style_to_item(self.sub1_item, self.sub1_style)

    def show_sub2_settings(self):
        """Shows the settings dialog for subtitle 2."""
        dialog = SubtitleSettingsDialog(self, self.sub2_style, self.sub2_margin, self.sub2_item, 2)
        if dialog.exec_():
            self.sub2_margin = dialog.margin
            self.sub2_style.marginv = self.sub2_margin
            self.apply_style_to_item(self.sub2_item, self.sub2_style)

    def get_video_duration(self):
        """Gets the video duration in seconds using ffprobe."""
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", self.video_file]
            # Hide window in Windows
            if platform.system() == 'Windows':
                duration_str = subprocess.check_output(cmd, creationflags=CREATE_NO_WINDOW).decode().strip()
            else:
                duration_str = subprocess.check_output(cmd).decode().strip()
            return float(duration_str)
        except Exception:
            return 0.0

    def handle_export_stderr(self, progress):
        data = self.export_process.readAllStandardError().data().decode('utf-8', errors='ignore')
        lines = data.splitlines()
        for line in lines:
            if "time=" in line:
                time_str = line.split("time=")[1].split(" ")[0]
                try:
                    hh, mm, ss = map(float, time_str.split(':'))
                    current_time = hh * 3600 + mm * 60 + ss
                    if self.video_duration > 0:
                        value = int((current_time / self.video_duration) * 100)
                        progress.setValue(value)
                except ValueError:
                    pass

    def on_export_finished(self, exit_code, exit_status, progress: QProgressDialog, out_path: str, temp_sub1: str, temp_sub2: str):
        progress.close()
        self.export_process = None
        if temp_sub1 and os.path.exists(temp_sub1):
            os.remove(temp_sub1)
        if temp_sub2 and os.path.exists(temp_sub2):
            os.remove(temp_sub2)
        if exit_code == 0:
            QMessageBox.information(self, "Success", "Video exported successfully.")
        else:
            QMessageBox.warning(self, "Error", "Error exporting the video.")

    def adjust_subs_for_preview(self, subs, start_time, duration):
        """Adjusts subtitles for preview, shifting times."""
        if subs is None:
            return None
        adjusted_subs = copy.deepcopy(subs)
        adjusted_events = []
        end_time = start_time + duration
        for event in adjusted_subs:
            if event.end > start_time * 1000 and event.start < end_time * 1000:  # Milliseconds
                new_start = max(0, event.start - start_time * 1000)
                new_end = min(duration * 1000, event.end - start_time * 1000)
                event.start = new_start
                event.end = new_end
                adjusted_events.append(event)
        adjusted_subs.events = adjusted_events
        return adjusted_subs

    def prepare_export_command(self, out_path, subs1, subs2, start_time=None, duration=None):
        """Prepares the FFmpeg command for export, with clip options."""
        temp_sub1 = "temp_sub1.ass" if subs1 else None
        temp_sub2 = "temp_sub2.ass" if subs2 else None
        vf_filters = []
        if subs1:
            for event in subs1:
                b = self.sub1_style.primary_colour.b
                g = self.sub1_style.primary_colour.g
                r = self.sub1_style.primary_colour.r
                event.text = r'{\c&H%02X%02X%02X&}' % (b, g, r) + event.text
            subs1.save(temp_sub1)
            vf_filters.append(f"ass={temp_sub1}")

        if subs2:
            for event in subs2:
                b = self.sub2_style.primary_colour.b
                g = self.sub2_style.primary_colour.g
                r = self.sub2_style.primary_colour.r
                event.text = r'{\c&H%02X%02X%02X&}' % (b, g, r) + event.text
            subs2.save(temp_sub2)
            vf_filters.append(f"ass={temp_sub2}")

        if not vf_filters:
            raise ValueError("No subtitles to export.")

        cmd = ["ffmpeg", "-i", self.video_file]

        if start_time is not None:
            cmd.insert(1, "-ss")
            cmd.insert(2, str(start_time))

        if duration is not None:
            cmd.insert(3 if start_time is not None else 1, "-t")
            cmd.insert(4 if start_time is not None else 2, str(duration))

        if self.hardware_encoder == "nvenc":
            cmd.insert(1, "-hwaccel")
            cmd.insert(2, "cuda")
            cmd += ["-c:v", "h264_nvenc", "-preset", "fast", "-cq", "23"]
        elif self.hardware_encoder == "amf":
            cmd.insert(1, "-hwaccel")
            cmd.insert(2, "auto")
            cmd += ["-c:v", "h264_amf", "-usage", "lowlatency"]
        elif self.hardware_encoder == "qsv":
            cmd.insert(1, "-hwaccel")
            cmd.insert(2, "qsv")
            cmd += ["-c:v", "h264_qsv", "-preset", "veryfast"]
        else:
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]

        cmd += ["-vf", ",".join(vf_filters), "-c:a", "copy", "-y", out_path]

        return cmd, temp_sub1, temp_sub2

    def run_export(self, cmd, out_path, temp_sub1, temp_sub2, clip_duration=None):
        """Executes the export process with progress bar if not a clip."""
        self.video_duration = clip_duration if clip_duration else self.get_video_duration()

        progress = QProgressDialog("Exporting...", "Cancel", 0, 100, self)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(0)

        self.export_process = QProcess(self)
        self.export_process.readyReadStandardError.connect(lambda: self.handle_export_stderr(progress))
        self.export_process.finished.connect(lambda code, status: self.on_export_finished(code, status, progress, out_path, temp_sub1, temp_sub2))
        progress.canceled.connect(self.export_process.kill)

        self.export_process.start(cmd[0], cmd[1:])

    def export_video(self):
        """Exports the full video with burned-in subtitles."""
        if not self.video_file:
            QMessageBox.warning(self, "Error", "You must load a video before exporting.")
            return
        if (self.current_preset == "none" and (not self.subs1 or not self.subs2)) or \
           (self.current_preset == "chinese" and not self.subs2) or \
           (self.current_preset == "english" and not self.subs1):
            QMessageBox.warning(self, "Error", "You must load the required subtitles according to the preset before exporting.")
            return

        out_path, _ = QFileDialog.getSaveFileName(self, "Save Exported Video", "", "Videos (*.mp4)")
        if out_path:
            try:
                cmd, temp_sub1, temp_sub2 = self.prepare_export_command(out_path, self.subs1, self.subs2)
                self.run_export(cmd, out_path, temp_sub1, temp_sub2)
            except ValueError as e:
                QMessageBox.warning(self, "Error", str(e))
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Unexpected error: {str(e)}")
                if temp_sub1 and os.path.exists(temp_sub1):
                    os.remove(temp_sub1)
                if temp_sub2 and os.path.exists(temp_sub2):
                    os.remove(temp_sub2)

    def export_preview(self):
        """Exports a 10-second preview from the current position, adjusting subtitles."""
        if not self.video_file:
            QMessageBox.warning(self, "Error", "You must load a video before exporting.")
            return
        if (self.current_preset == "none" and (not self.subs1 or not self.subs2)) or \
           (self.current_preset == "chinese" and not self.subs2) or \
           (self.current_preset == "english" and not self.subs1):
            QMessageBox.warning(self, "Error", "You must load the required subtitles according to the preset before exporting.")
            return

        current_position = self.player.position() / 1000  # In seconds
        preview_duration = 10  # Seconds

        # Adjust subtitles for the preview
        adjusted_subs1 = self.adjust_subs_for_preview(self.subs1, current_position, preview_duration) if self.subs1 else None
        adjusted_subs2 = self.adjust_subs_for_preview(self.subs2, current_position, preview_duration) if self.subs2 else None

        out_path, _ = QFileDialog.getSaveFileName(self, "Save Preview", "preview.mp4", "Videos (*.mp4)")
        if out_path:
            try:
                cmd, temp_sub1, temp_sub2 = self.prepare_export_command(out_path, adjusted_subs1, adjusted_subs2, start_time=current_position, duration=preview_duration)
                self.run_export(cmd, out_path, temp_sub1, temp_sub2, clip_duration=preview_duration)
            except ValueError as e:
                QMessageBox.warning(self, "Error", str(e))
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Unexpected error: {str(e)}")
                if temp_sub1 and os.path.exists(temp_sub1):
                    os.remove(temp_sub1)
                if temp_sub2 and os.path.exists(temp_sub2):
                    os.remove(temp_sub2)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path('assets/img/icon.ico')))  # Set global icon for taskbar and title
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
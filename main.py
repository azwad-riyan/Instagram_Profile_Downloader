import sys
import os
import time
import instaloader
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox, QLabel
from PyQt5.QtCore import QPropertyAnimation, QTimer, Qt, QRunnable, QThreadPool, pyqtSignal, pyqtSlot, QObject
from PyQt5.QtGui import QColor, QPalette
from look_ui import Ui_MainWindow  


#hey
#English or Spanish???


class WorkerSignals(QObject):
    progress = pyqtSignal(int, int, float)
    message = pyqtSignal(str, str)
    error = pyqtSignal(str, str)
    finished = pyqtSignal()

class ValidateWorker(QRunnable):
    def __init__(self, username):
        super().__init__()
        self.username = username
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            loader = instaloader.Instaloader()
            profile = instaloader.Profile.from_username(loader.context, self.username)
            if profile.is_private and not profile.followed_by_viewer:
                self.signals.error.emit("Private Account", "This account is private. Unable to download media.")
                self.signals.finished.emit()
                return
            posts = list(profile.get_posts())
            if not posts:
                self.signals.error.emit("No Posts", "This account has no posts available for download.")
                self.signals.finished.emit()
                return
            self.signals.message.emit("Valid Profile", "The profile is valid and ready for download.")
        except instaloader.exceptions.ProfileNotExistsException:
            self.signals.error.emit("Invalid Username", "The username does not exist. Please try again.")
        except instaloader.exceptions.LoginRequiredException:
            self.signals.error.emit("Login Required", "This seems a private profile. Please try with a public account.")
        except instaloader.exceptions.ConnectionException as e:
            if "redirect" in str(e):
                self.signals.error.emit("Private Account", "This account is private. Unable to download media.")
            else:
                self.signals.error.emit("Connection Error", str(e))
        except Exception as e:
            self.signals.error.emit("Validation Error", str(e))
        finally:
            self.signals.finished.emit()

class DownloadWorker(QRunnable):
    def __init__(self, username, save_location):
        super().__init__()
        self.username = username
        self.save_location = save_location
        self.signals = WorkerSignals()
        self.posts_downloaded = 0

    @pyqtSlot()
    def run(self):
        try:
            loader = instaloader.Instaloader(
                dirname_pattern=os.path.join(self.save_location, '{target}'),
                download_comments=False,
                save_metadata=False,
                download_video_thumbnails=False,
            )
            profile = instaloader.Profile.from_username(loader.context, self.username)
            posts = list(profile.get_posts())
            total_posts = len(posts)
            self.signals.progress.emit(0, total_posts, 0)

            start_time = time.time()
            for i, post in enumerate(posts):
                loader.download_post(post, target=profile.username)
                self.posts_downloaded += 1
                elapsed_time = time.time() - start_time
                avg_time_per_post = elapsed_time / (i + 1)
                self.signals.progress.emit(i + 1, total_posts, avg_time_per_post)

            self.signals.message.emit("Success", "Media of the targated profile downloaded successfully.")
        except Exception as e:
            self.signals.error.emit("Download Error", str(e))
        finally:
            self.signals.finished.emit()

class InstagramDownloader(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        # animated background
        self.setStyleSheet("""
            QWidget#centralwidget {
                background-color: #f0f8ff;
                border: 1px solid #000;
                border-radius: 10px;
            }
            QLabel {
                color: #2E3440;
                font-size: 14px;
            }
            QLineEdit {
                background-color: #FFFFFF;
                color: #2E3440;
                border: 1px solid #2E3440;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton {
                background-color: #81A1C1;
                color: #2E3440;
                border-radius: 5px;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #88C0D0;
            }
            QProgressBar {
                background-color: #E5E9F0;
                color: #2E3440;
                border-radius: 5px;
                text-align: center;
            }
        """)

        self.create_background_animation()

        # default state
        self.save_location = None
        self.btn_choose_location.clicked.connect(self.choose_save_location)
        self.btn_download.clicked.connect(self.start_validation)

        self.threadpool = QThreadPool()

    def create_background_animation(self):
        self.colors = [QColor("#f0f8ff"), QColor("#e6e6fa"), QColor("#f5f5dc"), QColor("#ffe4e1"), QColor("#fafad2")]
        self.current_color_index = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.change_background_color)
        self.timer.start(3000)

    def change_background_color(self):
        self.current_color_index = (self.current_color_index + 1) % len(self.colors)
        palette = self.centralwidget.palette()
        palette.setColor(QPalette.Window, self.colors[self.current_color_index])
        self.centralwidget.setPalette(palette)
        self.centralwidget.setAutoFillBackground(True)

    def choose_save_location(self):
        self.save_location = QFileDialog.getExistingDirectory(self, "Select Directory")

    def start_validation(self):
        username = self.input_username.text().strip()
        if not username:
            self.show_error("Input Error", "Please provide an Instagram username.")
            return

        if not self.save_location:
            self.show_error("Input Error", "Please choose a save location.")
            return

        self.label_message.setText("Validating profile...")
        self.label_message.setStyleSheet("color: #FFFFFF; background-color: #FFA500; border-radius: 5px; padding: 5px;")
        self.label_message.setAlignment(Qt.AlignCenter)
        self.label_message.setVisible(True)
        self.fade_out_message(self.label_message)

        validation_worker = ValidateWorker(username)
        validation_worker.signals.message.connect(self.validation_success)
        validation_worker.signals.error.connect(self.show_error)
        validation_worker.signals.finished.connect(self.validation_finished)

        self.threadpool.start(validation_worker)

    def validation_success(self, title, message):
        self.label_message.setText(message)
        self.label_message.setStyleSheet("color: #FFFFFF; background-color: #32CD32; border-radius: 5px; padding: 5px;")
        self.label_message.setAlignment(Qt.AlignCenter)
        self.label_message.setVisible(True)
        self.fade_out_message(self.label_message)
        self.start_download()

    def validation_finished(self):
        pass  # meo meo

    def start_download(self):
        username = self.input_username.text().strip()
        worker = DownloadWorker(username, self.save_location)
        worker.signals.progress.connect(self.update_progress)
        worker.signals.message.connect(self.show_message)
        worker.signals.error.connect(self.show_error)
        worker.signals.finished.connect(self.download_finished)

        self.threadpool.start(worker)

        self.label_message.setText("Download started!")
        self.label_message.setStyleSheet("color: #FFFFFF; background-color: #32CD32; border-radius: 5px; padding: 5px;")
        self.label_message.setAlignment(Qt.AlignCenter)
        self.label_message.setVisible(True)
        self.fade_out_message(self.label_message)

    @pyqtSlot(int, int, float)
    def update_progress(self, current, total, avg_time_per_post):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.label_file_count.setText(f"{current} / {total} files downloaded")

        if current > 0:
            elapsed_time = avg_time_per_post * current
            remaining_time = avg_time_per_post * (total - current)
            self.label_time_remaining.setText(f"Estimated Time Remaining: {int(remaining_time // 60):02d}:{int(remaining_time % 60):02d}")

    @pyqtSlot()
    def download_finished(self):
        self.show_message("Success", "Media downloaded successfully.")

    def fade_out_message(self, label):
        animation = QPropertyAnimation(label, b"windowOpacity")
        animation.setDuration(5000)
        animation.setStartValue(1)
        animation.setEndValue(0)
        animation.finished.connect(label.hide)
        animation.start()

    @pyqtSlot(str, str)
    def show_message(self, title, message):
        self.label_message.setText(message)
        self.label_message.setStyleSheet("color: #FFFFFF; background-color: #32CD32; border-radius: 5px; padding: 5px;")
        self.label_message.setAlignment(Qt.AlignCenter)
        self.label_message.setVisible(True)
        self.fade_out_message(self.label_message)

    @pyqtSlot(str, str)
    def show_error(self, title, message):
        self.label_message.setText(message)
        self.label_message.setStyleSheet("color: #FFFFFF; background-color: #FF0000; border-radius: 5px; padding: 5px;")
        self.label_message.setAlignment(Qt.AlignCenter)
        self.label_message.setVisible(True)
        self.fade_out_message(self.label_message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    downloader = InstagramDownloader()
    downloader.show()
    sys.exit(app.exec_())

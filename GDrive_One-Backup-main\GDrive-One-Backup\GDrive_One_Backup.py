import sys
import os
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pickle
import json
import hashlib
from datetime import datetime
import win32gui
import win32con
import win32process
import ctypes

SCOPES = ['https://www.googleapis.com/auth/drive.file']

class SyncWorker(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, drive_service, folder_path, parent_id=None):
        super().__init__()
        self.drive_service = drive_service
        self.folder_path = folder_path
        self.parent_id = parent_id
        self.running = True

    def run(self):
        try:
            if not self.parent_id:
                # Create main folder in Google Drive
                folder_metadata = {
                    'name': os.path.basename(self.folder_path),
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                folder = self.drive_service.files().create(
                    body=folder_metadata, fields='id').execute()
                self.parent_id = folder['id']

            total_files = sum([len(files) for _, _, files in os.walk(self.folder_path)])
            processed_files = 0

            for root, _, files in os.walk(self.folder_path):
                for file in files:
                    if not self.running:
                        return
                        
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(root, self.folder_path)
                    
                    # Update progress
                    processed_files += 1
                    progress = int((processed_files / total_files) * 100)
                    self.progress.emit(f"Syncing: {file}", progress)

                    # Upload file
                    self.upload_file(file_path, relative_path)

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))

    def upload_file(self, file_path, relative_path):
        try:
            file_metadata = {
                'name': os.path.basename(file_path),
                'parents': [self.parent_id]
            }

            media = MediaFileUpload(
                file_path,
                resumable=True,
                chunksize=1024*1024
            )

            self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()

        except Exception as e:
            self.error.emit(f"Error uploading {file_path}: {str(e)}")

    def stop(self):
        self.running = False

class GoogleDriveBrowserDialog(QDialog):
    def __init__(self, drive_service, parent=None):
        try:
            super().__init__(parent)
            self.drive_service = drive_service
            self.selected_folder = None
            self.search_timer = QTimer()
            self.search_timer.setSingleShot(True)
            self.search_timer.timeout.connect(self.perform_search)
            self.backup_schedule = {}
            self.sync_workers = []
        
            # Initialize UI
            self.setup_ui()
            
            # Load folders after UI is set up
            QTimer.singleShot(100, self.load_folders)
            
            self.setMinimumSize(500, 600)
            
        except Exception as e:
            print(f"Initialization error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to initialize dialog: {str(e)}")

    def setup_ui(self):
        try:
            self.setWindowTitle("Select Google Drive Destination")
            layout = QVBoxLayout(self)
            
            # Search bar
            search_layout = QHBoxLayout()
            self.search_input = QLineEdit()
            self.search_input.setPlaceholderText("Search folders...")
            self.search_input.textChanged.connect(self.on_search_changed)
            search_layout.addWidget(self.search_input)
            
            # Refresh button
            self.refresh_btn = QPushButton()
            self.refresh_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
            self.refresh_btn.clicked.connect(self.refresh_folders)
            search_layout.addWidget(self.refresh_btn)
            layout.addLayout(search_layout)
            
            # Folder tree
            self.folder_tree = QTreeWidget()
            self.folder_tree.setHeaderLabel("Google Drive Folders")
            self.folder_tree.setAlternatingRowColors(True)
            self.folder_tree.setAnimated(True)
            self.folder_tree.setSortingEnabled(True)
            self.folder_tree.itemClicked.connect(self.on_folder_selected)
            layout.addWidget(self.folder_tree)
            
            # Progress bar
            self.progress = QProgressBar()
            self.progress.setVisible(False)
            layout.addWidget(self.progress)
            
            # Status label
            self.status_label = QLabel("")
            layout.addWidget(self.status_label)
            
            # Buttons
            button_layout = QHBoxLayout()
            
            self.new_folder_btn = QPushButton("Create New Folder")
            self.new_folder_btn.clicked.connect(self.create_new_folder)
            button_layout.addWidget(self.new_folder_btn)
            
            self.delete_folder_btn = QPushButton("Delete Folder")
            self.delete_folder_btn.clicked.connect(self.delete_folder)
            button_layout.addWidget(self.delete_folder_btn)
            
            layout.addLayout(button_layout)
            
            # Dialog buttons
            buttons = QDialogButtonBox(
                QDialogButtonBox.Ok | QDialogButtonBox.Cancel
            )
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)
            
        except Exception as e:
            print(f"UI setup error: {str(e)}")
            raise

class DriveBackupGUI(QMainWindow):
    def __init__(self):
        try:
            super().__init__()
            self.setWindowTitle("Google Drive Backup Tool")
            self.setMinimumSize(800, 600)
            
            self.drive_service = None
            self.credentials = None
            self.sync_workers = []
            self.folder_drives = {}
            self.default_backup_dir = self.ensure_default_backup_dir()
            self.google_drive_destination = None
            
            self.init_ui()
            self.load_config()
            self.load_credentials()
            
        except Exception as e:
            print(f"Initialization error: {str(e)}")
            QMessageBox.critical(None, "Error", f"Failed to initialize application: {str(e)}")
            raise

    def init_ui(self):
        # Previous UI code remains...
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Status and header
        self.status_label = QLabel("Status: Not logged in")
        self.status_label.setStyleSheet("color: #ff9800; padding: 5px;")
        layout.addWidget(self.status_label)
        
        header = QLabel("🎓 Google Drive Backup Tool")
        header.setStyleSheet("font-size: 24px; color: white; padding: 10px;")
        layout.addWidget(header)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.login_btn = QPushButton("Login to Google")
        self.add_folder_btn = QPushButton("Add Folder")
        self.sync_btn = QPushButton("Sync Now")
        self.remove_folder_btn = QPushButton("Remove Selected")
        
        for btn in [self.login_btn, self.add_folder_btn, self.sync_btn, self.remove_folder_btn]:
            btn.setMinimumHeight(40)
        
        layout.addLayout(button_layout)
        
        # Progress bar
        self.progress_label = QLabel("Ready")
        layout.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Folder list
        self.folder_list = QListWidget()
        layout.addWidget(self.folder_list)
        
        # Connect buttons
        self.login_btn.clicked.connect(self.login)
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.sync_btn.clicked.connect(self.sync_now)
        self.remove_folder_btn.clicked.connect(self.remove_folder)
        
        # Initially disable buttons
        self.add_folder_btn.setEnabled(False)
        self.sync_btn.setEnabled(False)
        self.remove_folder_btn.setEnabled(False)
        
        self.apply_dark_theme()
        
        # Add new elements after the existing buttons
        self.destination_label = QLabel("Google Drive Destination: Not selected")
        layout.addWidget(self.destination_label)
            
        self.browse_drive_btn = QPushButton("Browse Google Drive")
        self.browse_drive_btn.clicked.connect(self.browse_google_drive)
        layout.addWidget(self.browse_drive_btn)
        
        # Add default folder to the list
        self.folder_list.addItem(self.default_backup_dir)

    def load_config(self):
        try:
            if os.path.exists('backup_config.json'):
                with open('backup_config.json', 'r') as f:
                    self.folder_drives = json.load(f)
                    for folder in self.folder_drives:
                        self.folder_list.addItem(folder)
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Failed to load config: {str(e)}")

    def save_config(self):
        try:
            with open('backup_config.json', 'w') as f:
                json.dump(self.folder_drives, f)
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Failed to save config: {str(e)}")

    def remove_folder(self):
        curr_item = self.folder_list.currentItem()
        if curr_item:
            folder_path = curr_item.text()
            self.folder_drives.pop(folder_path, None)
            self.folder_list.takeItem(self.folder_list.row(curr_item))
            self.save_config()
            QMessageBox.critical(self, "Error", f"Folder '{folder_path}' removed successfully!")

    def update_progress(self, message, value):
        self.progress_label.setText(message)
        self.progress_bar.setValue(value)

    def sync_complete(self):
        self.progress_bar.setVisible(False)
        self.progress_label.setText("Sync completed!")
        self.sync_btn.setEnabled(True)
        self.save_config()

    def sync_error(self, error_message):
        QMessageBox.critical(self, "Error", f"Sync error: {error_message}")
        self.progress_bar.setVisible(False)
        self.sync_btn.setEnabled(True)

    def ensure_default_backup_dir(self):
        default_dir = os.path.expanduser("~")
        return os.path.join(default_dir, "Google Drive Backup")

    def sync_now(self):
        if not self.folder_list.count():
            QMessageBox.warning(self, "Warning", "No folders to sync!")
            return
        return self.ensure_default_backup_dir()
        self.sync_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

    def closeEvent(self, event):
        if self.tray_icon.isVisible():
            QMessageBox.information(self, "Google Drive Backup Tool",
                "The application will keep running in the system tray. To "
                "terminate the program, choose 'Exit' in the context menu "
                "of the system tray entry.")
            self.hide()
            event.ignore()
        else:
            self.quit_application()

    def login(self):
        try:
            if not os.path.exists('credentials.json'):
                QMessageBox.critical(self, "Error", 
                    "credentials.json not found!\n\nPlease obtain it from Google Cloud Console.")
                return

            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            self.credentials = flow.run_local_server(port=0)

            # Save the credentials
            with open('token.pickle', 'wb') as token:
                pickle.dump(self.credentials, token)

            self.drive_service = build('drive', 'v3', credentials=self.credentials)
            self.status_label.setText("Status: Logged in")
            self.add_folder_btn.setEnabled(True)
            self.sync_btn.setEnabled(True)
            self.browse_drive_btn.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Login failed: {str(e)}")

    def load_credentials(self):
        try:
            if os.path.exists('token.pickle'):
                with open('token.pickle', 'rb') as token:
                    self.credentials = pickle.load(token)

            if self.credentials and self.credentials.valid:
                self.drive_service = build('drive', 'v3', credentials=self.credentials)
                self.status_label.setText("Status: Logged in")
                self.add_folder_btn.setEnabled(True)
                self.sync_btn.setEnabled(True)
                self.browse_drive_btn.setEnabled(True)
                
        except Exception as e:
            print(f"Failed to load credentials: {str(e)}")

    def add_folder(self):
        if not self.drive_service:
            QMessageBox.warning(self, "Warning", "Please login first!")
            return
        
        try:
            # Open folder selection dialog
            folder_path = QFileDialog.getExistingDirectory(
                self,
                "Select Folder to Backup",
                self.default_backup_dir,
                QFileDialog.ShowDirsOnly
            )
            
            if folder_path:
                # Check if folder already exists in list
                for i in range(self.folder_list.count()):
                    if self.folder_list.item(i).text() == folder_path:
                        QMessageBox.warning(self, "Warning", "Folder already added!")
                        return
                
                # Add to list and save
                self.folder_list.addItem(folder_path)
                self.folder_drives[folder_path] = None
                self.save_config()
                
                # Enable sync button if we have folders
                self.sync_btn.setEnabled(True)
                self.remove_folder_btn.setEnabled(True)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add folder: {str(e)}")

    def apply_dark_theme(self):
        """Apply dark theme to the application"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #202124;
            }
            QWidget {
                background-color: #202124;
                color: #e8eaed;
            }
            QPushButton {
                background-color: #3c4043;
                border: 1px solid #5f6368;
                border-radius: 4px;
                padding: 6px 12px;
                color: #e8eaed;
            }
            QPushButton:hover {
                background-color: #5f6368;
            }
            QPushButton:disabled {
                background-color: #3c4043;
                color: #9aa0a6;
            }
            QListWidget {
                border: 1px solid #5f6368;
                border-radius: 4px;
            }
            QProgressBar {
                border: 1px solid #5f6368;
                border-radius: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #8ab4f8;
            }
            QLabel {
                color: #e8eaed;
            }
        """)

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            
    def quit_application(self):
        # Stop all sync workers
        for worker in self.sync_workers:
            worker.stop()
            worker.wait()
        
        # Save any pending configurations
        self.save_config()
        
        # Remove tray icon
        self.tray_icon.hide()
                
        # Quit application
        QApplication.quit()

def hide_console():
    """Hide the console window"""
    whnd = ctypes.windll.kernel32.GetConsoleWindow()
    if whnd != 0:
        ctypes.windll.user32.ShowWindow(whnd, 0)

def main():
    # Enable high DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    window = DriveBackupGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
import sys
import os
import pickle
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QPushButton, QListWidget, 
                            QTextEdit, QProgressBar, QCheckBox, QFileDialog,
                            QMessageBox, QDialog, QTreeWidget, QTreeWidgetItem,
                            QTimeEdit, QComboBox, QSpinBox, QDialogButtonBox, 
                            QFormLayout, QGroupBox, QProgressDialog, QSystemTrayIcon, QMenu, QAction)
from PyQt5.QtCore import Qt, QDateTime, QThread, pyqtSignal, QTime, QTimer
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import time
import mimetypes
import shutil
import ctypes

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Add this at the start of your script to hide the console window on Windows
if sys.platform.startswith('win'):
    try:
        # Hide console window
        whnd = ctypes.windll.kernel32.GetConsoleWindow()
        if whnd != 0:
            ctypes.windll.user32.ShowWindow(whnd, 0)
    except Exception as e:
        print(f"Error hiding console: {e}")

class SyncWorker(QThread):
    progress = pyqtSignal(str, int)  # Message, percentage
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, drive_service, folder_path, parent_id=None):
        super().__init__()
        if drive_service is None:
            raise ValueError("Drive service cannot be None")
        self.drive_service = drive_service
        self.folder_path = folder_path
        self.parent_id = parent_id
        self.running = True

    def run(self):
        """Main sync process"""
        try:
            if not self.parent_id:
                self.error.emit("No destination folder selected")
                return

            total_files = sum([len(files) for _, _, files in os.walk(self.folder_path)])
            processed_files = 0

            for root, _, files in os.walk(self.folder_path):
                if not self.running:
                    break

                # Create folder structure in Google Drive
                relative_path = os.path.relpath(root, self.folder_path)
                current_parent_id = self.create_folder_structure(relative_path)

                # Upload files
                for file_name in files:
                    if not self.running:
                        break

                    file_path = os.path.join(root, file_name)
                    relative_file_path = os.path.relpath(file_path, self.folder_path)
                    
                    try:
                        self.upload_file(file_path, relative_file_path)
                    except Exception as e:
                        self.error.emit(f"Error uploading {file_path}: {str(e)}")
                    
                    processed_files += 1
                    progress = int((processed_files / total_files) * 100)
                    self.progress.emit(f"Processing: {relative_file_path}", progress)

            self.finished.emit()

        except Exception as e:
            self.error.emit(f"Sync error: {str(e)}")

    def create_folder_structure(self, relative_path):
        """Create folder structure in Google Drive"""
        if relative_path == '.':
            return self.parent_id

        current_parent = self.parent_id
        path_parts = relative_path.split(os.sep)

        for folder_name in path_parts:
            if not folder_name:
                continue

            # Check if folder exists
            query = f"name='{folder_name}' and '{current_parent}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.drive_service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()

            if results['files']:
                current_parent = results['files'][0]['id']
            else:
                # Create new folder
                folder_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [current_parent]
                }
                folder = self.drive_service.files().create(
                    body=folder_metadata,
                    fields='id'
                ).execute()
                current_parent = folder['id']

        return current_parent

    def upload_file(self, file_path, relative_path):
        """Upload a file to Google Drive"""
        try:
            file_size = os.path.getsize(file_path)
            mime_type, _ = mimetypes.guess_type(file_path)
            
            if mime_type is None:
                mime_type = 'application/octet-stream'

            file_metadata = {
                'name': os.path.basename(file_path),
                'parents': [self.parent_id]
            }

            media = MediaFileUpload(
                file_path,
                mimetype=mime_type,
                resumable=True,
                chunksize=1024*1024
            )

            request = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            )

            response = None
            retries = 3
            while response is None and retries > 0:
                try:
                    status, response = request.next_chunk()
                    if status:
                        self.progress.emit(f"Uploading: {relative_path}", int(status.progress() * 100))
                except Exception as chunk_error:
                    print(f"Chunk Error (retrying): {chunk_error}")
                    retries -= 1
                    time.sleep(1)
                    if retries == 0:
                        raise

        except Exception as e:
            raise Exception(f"Error uploading {file_path}: {str(e)}")

    def stop(self):
        """Stop the sync process"""
        self.running = False

class ScheduleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Schedule Backup")
        self.setMinimumWidth(300)
        
        # Create layout
        layout = QVBoxLayout(self)
        
        # Create frequency group
        freq_group = QGroupBox("Backup Frequency")
        freq_layout = QFormLayout()
        
        self.freq_combo = QComboBox()
        self.freq_combo.addItems(["Daily", "Weekly", "Monthly"])
        freq_layout.addRow("Frequency:", self.freq_combo)
        
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime(23, 0))  # Default to 11:00 PM
        freq_layout.addRow("Time:", self.time_edit)
        
        self.day_combo = QComboBox()
        self.day_combo.addItems(["Monday", "Tuesday", "Wednesday", "Thursday", 
                                "Friday", "Saturday", "Sunday"])
        self.day_combo.hide()  # Initially hidden, shown for weekly schedule
        freq_layout.addRow("Day:", self.day_combo)
        
        self.date_spin = QSpinBox()
        self.date_spin.setRange(1, 28)
        self.date_spin.hide()  # Initially hidden, shown for monthly schedule
        freq_layout.addRow("Date:", self.date_spin)
        
        freq_group.setLayout(freq_layout)
        layout.addWidget(freq_group)
        
        # Add buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Connect signals
        self.freq_combo.currentTextChanged.connect(self.on_frequency_changed)
        
        # Apply styling
        self.apply_styling()
    
    def apply_styling(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d2d;
                color: #d4d4d4;
            }
            QGroupBox {
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 3px;
                margin-top: 0.5em;
                padding-top: 0.5em;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QComboBox, QTimeEdit, QSpinBox {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 3px;
                padding: 5px;
            }
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #007acc;
                padding: 5px;
                border-radius: 3px;
                color: #d4d4d4;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QLabel {
                color: #d4d4d4;
            }
        """)
    
    def on_frequency_changed(self, frequency):
        """Show/hide controls based on selected frequency"""
        if frequency == "Daily":
            self.day_combo.hide()
            self.date_spin.hide()
        elif frequency == "Weekly":
            self.day_combo.show()
            self.date_spin.hide()
        else:  # Monthly
            self.day_combo.hide()
            self.date_spin.show()
    
    def get_schedule(self):
        """Return the selected schedule settings"""
        return {
            'frequency': self.freq_combo.currentText(),
            'time': self.time_edit.time().toString("HH:mm"),
            'day': self.day_combo.currentText(),
            'date': self.date_spin.value()
        }

class DriveBackupGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Google Drive Backup")
        self.setMinimumSize(800, 600)
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create main horizontal layout
        main_layout = QHBoxLayout(central_widget)
        
        # Create left panel
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Add widgets to left panel with emoji
        self.title_label = QLabel("🔄 Google Drive Backup")
        self.title_label.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #007acc;
        """)
        
        self.status_label = QLabel("Status: Not logged in")
        self.login_btn = QPushButton("Login to Google")
        self.add_folder_btn = QPushButton("Add Folder")
        self.remove_folder_btn = QPushButton("Remove Folder")
        self.folder_list = QListWidget()
        self.destination_label = QLabel("Google Drive Destination: Not selected")
        self.browse_drive_btn = QPushButton("Browse Google Drive")
        self.sync_btn = QPushButton("Sync Now")
        self.schedule_btn = QPushButton("Schedule Backup")
        self.progress_bar = QProgressBar()
        self.progress_label = QLabel("")
        self.auto_backup_checkbox = QCheckBox("Enable Real-time Sync")
        
        # Disable buttons initially
        self.add_folder_btn.setEnabled(False)
        self.remove_folder_btn.setEnabled(False)
        self.sync_btn.setEnabled(False)
        self.browse_drive_btn.setEnabled(False)
        self.schedule_btn.setEnabled(False)
        
        # Add widgets to left layout
        left_layout.addWidget(self.title_label)
        left_layout.addWidget(self.status_label)
        left_layout.addWidget(self.login_btn)
        left_layout.addWidget(self.add_folder_btn)
        left_layout.addWidget(self.remove_folder_btn)
        left_layout.addWidget(self.folder_list)
        left_layout.addWidget(self.destination_label)
        left_layout.addWidget(self.browse_drive_btn)
        left_layout.addWidget(self.sync_btn)
        left_layout.addWidget(self.schedule_btn)
        left_layout.addWidget(self.progress_bar)
        left_layout.addWidget(self.progress_label)
        left_layout.addWidget(self.auto_backup_checkbox)
        
        # Add stretch to push everything up
        left_layout.addStretch()
        
        # Create right panel
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create header layout for error log with minimal margins
        error_header_layout = QHBoxLayout()
        error_header_layout.setContentsMargins(0, 0, 0, 0)
        error_header_layout.setSpacing(0)
        
        # Create error label
        error_label = QLabel("Error Log:")
        error_label.setStyleSheet("color: #ff4444;")
        
        # Create clear log button with increased width
        self.clear_log_btn = QPushButton("🗑️ Clear Log")
        self.clear_log_btn.setFixedWidth(120)
        self.clear_log_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #ff4444;
                border-radius: 3px;
                color: #ff4444;
                padding: 2px 5px;
                margin: 0px;
                margin-left: 10px;
                margin-right: 20px;
                text-align: center;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3c3c3c;
            }
            QPushButton:pressed {
                background-color: #ff4444;
                color: #2d2d2d;
            }
        """)
        
        # Add widgets to header layout
        error_header_layout.addWidget(error_label)
        error_header_layout.addWidget(self.clear_log_btn)
        error_header_layout.addStretch()
        
        # Add header layout and error log to right panel
        right_layout.addLayout(error_header_layout)
        self.error_log = QTextEdit()
        self.error_log.setReadOnly(True)
        self.error_log.setMaximumWidth(300)
        right_layout.addWidget(self.error_log)
        
        # Connect clear log button
        self.clear_log_btn.clicked.connect(self.clear_error_log)
        
        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
        
        # Initialize Google Drive related variables
        self.credentials = None
        self.drive_service = None
        self.google_drive_destination = None
        
        # Load credentials if they exist
        self.load_credentials()
        
        # Initialize placeholder methods
        self.setup_connections()
        self.apply_dark_theme()
        
        # Initialize sync workers list
        self.sync_workers = []
        
        # Add stop sync button
        self.stop_sync_btn = QPushButton("Stop Sync")
        self.stop_sync_btn.setEnabled(False)
        left_layout.addWidget(self.stop_sync_btn)
        
        # Connect stop sync button
        self.stop_sync_btn.clicked.connect(self.stop_sync)
        
        # Add move and delete buttons
        self.move_btn = QPushButton("🔄 Move Files")
        self.delete_completed_btn = QPushButton("🗑️ Delete Completed")
        self.delete_completed_btn.setEnabled(False)  # Initially disabled
        
        # Add buttons to layout
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.move_btn)
        button_layout.addWidget(self.delete_completed_btn)
        left_layout.addLayout(button_layout)
        
        # Track completed and failed files
        self.completed_files = set()
        self.failed_files = set()
        
        # Connect new buttons
        self.move_btn.clicked.connect(self.move_files)
        self.delete_completed_btn.clicked.connect(self.delete_completed_files)

        # Create system tray icon
        self.create_tray_icon()
        
        # Modify close event to minimize to tray instead
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

    def setup_connections(self):
        """Setup signal connections"""
        self.login_btn.clicked.connect(self.authenticate)
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.remove_folder_btn.clicked.connect(self.remove_folder)
        self.sync_btn.clicked.connect(self.sync_now)
        self.browse_drive_btn.clicked.connect(self.browse_google_drive)
        self.schedule_btn.clicked.connect(self.show_schedule_dialog)
        self.auto_backup_checkbox.stateChanged.connect(self.placeholder)

    def load_credentials(self):
        """Load saved credentials if they exist"""
        try:
            if os.path.exists('token.pickle'):
                with open('token.pickle', 'rb') as token:
                    self.credentials = pickle.load(token)

            if self.credentials and self.credentials.valid:
                self.drive_service = build('drive', 'v3', credentials=self.credentials)
                self.status_label.setText("Status: Logged in")
                self.login_btn.setText("Switch Google Account")
                self.enable_buttons()
            elif self.credentials and self.credentials.expired and self.credentials.refresh_token:
                self.credentials.refresh(Request())
                with open('token.pickle', 'wb') as token:
                    pickle.dump(self.credentials, token)
                self.drive_service = build('drive', 'v3', credentials=self.credentials)
                self.status_label.setText("Status: Logged in")
                self.login_btn.setText("Switch Google Account")
                self.enable_buttons()
        except Exception as e:
            self.log_error(f"Error loading credentials: {str(e)}")

    def authenticate(self):
        """Handle Google Drive authentication"""
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            self.credentials = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(self.credentials, token)
            
            self.drive_service = build('drive', 'v3', credentials=self.credentials)
            self.status_label.setText("Status: Logged in")
            self.login_btn.setText("Switch Google Account")
            self.enable_buttons()
            
        except Exception as e:
            self.log_error(f"Authentication error: {str(e)}")

    def enable_buttons(self):
        """Enable buttons after successful login"""
        self.add_folder_btn.setEnabled(True)
        self.browse_drive_btn.setEnabled(True)
        self.sync_btn.setEnabled(True)
        self.schedule_btn.setEnabled(True)

    def add_folder(self):
        """Add a folder to backup list"""
        try:
            folder = QFileDialog.getExistingDirectory(
                self, 
                "Select Folder to Backup",
                os.path.expanduser("~"),
                QFileDialog.ShowDirsOnly
            )
            
            if folder:
                # Check if folder is already in list
                items = [self.folder_list.item(i).text() 
                        for i in range(self.folder_list.count())]
                if folder not in items:
                    self.folder_list.addItem(folder)
                    self.remove_folder_btn.setEnabled(True)
                    
        except Exception as e:
            self.log_error(f"Error adding folder: {str(e)}")

    def remove_folder(self):
        """Remove selected folder from backup list"""
        try:
            current_item = self.folder_list.currentItem()
            if current_item:
                self.folder_list.takeItem(self.folder_list.row(current_item))
                
            if self.folder_list.count() == 0:
                self.remove_folder_btn.setEnabled(False)
                
        except Exception as e:
            self.log_error(f"Error removing folder: {str(e)}")

    def log_error(self, message):
        """Add error message to error log"""
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
        self.error_log.append(f"[{timestamp}] {message}")
        # Auto-scroll to bottom
        scrollbar = self.error_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def browse_google_drive(self):
        """Browse and select Google Drive folder with proper hierarchy"""
        try:
            if not self.drive_service:
                self.log_error("Please login to Google Drive first")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle("Select Google Drive Folder")
            dialog.setMinimumWidth(400)
            dialog.setMinimumHeight(500)

            layout = QVBoxLayout(dialog)

            # Create tree widget for folder hierarchy
            tree = QTreeWidget()
            tree.setHeaderLabel("Google Drive Folders")
            tree.setStyleSheet("""
                QTreeWidget {
                    background-color: #2d2d2d;
                    color: #d4d4d4;
                    border: 1px solid #3c3c3c;
                }
                QTreeWidget::item:hover {
                    background-color: #3c3c3c;
                }
                QTreeWidget::item:selected {
                    background-color: #0078d7;
                }
            """)

            layout.addWidget(tree)

            # Add buttons
            button_layout = QHBoxLayout()
            refresh_btn = QPushButton("Refresh")
            select_btn = QPushButton("Select")
            cancel_btn = QPushButton("Cancel")

            for btn in [refresh_btn, select_btn, cancel_btn]:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #3c3c3c;
                        border: 1px solid #555555;
                        color: #d4d4d4;
                        padding: 5px 15px;
                        border-radius: 3px;
                    }
                    QPushButton:hover {
                        background-color: #505050;
                    }
                    QPushButton:pressed {
                        background-color: #404040;
                    }
                """)
                button_layout.addWidget(btn)

            layout.addLayout(button_layout)

            def load_folders(parent_item=None, parent_id='root'):
                try:
                    query = f"mimeType='application/vnd.google-apps.folder' and trashed=false"
                    if parent_id != 'root':
                        query += f" and '{parent_id}' in parents"
                    
                    results = self.drive_service.files().list(
                        q=query,
                        spaces='drive',
                        fields='files(id, name, parents)',
                        orderBy='name'
                    ).execute()

                    folders = results.get('files', [])
                    
                    for folder in folders:
                        if parent_item is None:
                            item = QTreeWidgetItem(tree)
                        else:
                            item = QTreeWidgetItem(parent_item)
                            
                        item.setText(0, folder['name'])
                        item.setData(0, Qt.UserRole, folder['id'])
                        
                        # Add loading indicator
                        loading = QTreeWidgetItem(item)
                        loading.setText(0, "Loading...")
                        
                except Exception as e:
                    self.log_error(f"Error loading folders: {str(e)}")

            def expand_item(item):
                """Load subfolders when parent is expanded"""
                loading_item = item.child(0)
                if loading_item and loading_item.text(0) == "Loading...":
                    folder_id = item.data(0, Qt.UserRole)
                    item.takeChild(0)  # Remove loading indicator
                    load_folders(item, folder_id)

            # Connect signals
            tree.itemExpanded.connect(expand_item)
            refresh_btn.clicked.connect(lambda: (tree.clear(), load_folders()))
            select_btn.clicked.connect(dialog.accept)
            cancel_btn.clicked.connect(dialog.reject)

            # Initial load of root folders
            load_folders()

            if dialog.exec_() == QDialog.Accepted:
                selected = tree.currentItem()
                if selected:
                    folder_id = selected.data(0, Qt.UserRole)
                    folder_name = selected.text(0)
                    self.google_drive_destination = folder_id
                    self.destination_label.setText(f"Google Drive Destination: {folder_name}")
                    return folder_id

            return None

        except Exception as e:
            self.log_error(f"Error browsing Google Drive: {str(e)}")
            return None

    def sync_now(self):
        """Start the backup process"""
        if not self.drive_service:
            self.log_error("Please login to Google Drive first")
            return
        
        if not self.google_drive_destination:
            self.log_error("Please select a destination folder in Google Drive")
            return
        
        if self.folder_list.count() == 0:
            self.log_error("Please add at least one folder to backup")
            return
        
        try:
            # Disable UI elements during sync
            self.sync_btn.setEnabled(False)
            self.add_folder_btn.setEnabled(False)
            self.remove_folder_btn.setEnabled(False)
            self.browse_drive_btn.setEnabled(False)
            
            # Start sync for each folder
            for i in range(self.folder_list.count()):
                folder_path = self.folder_list.item(i).text()
                
                # Create and start worker thread
                worker = SyncWorker(self.drive_service, folder_path, self.google_drive_destination)
                worker.progress.connect(self.update_progress)
                worker.error.connect(self.log_error)
                worker.finished.connect(self.sync_finished)
                
                self.sync_workers.append(worker)
                worker.start()
                
        except Exception as e:
            self.log_error(f"Error starting sync: {str(e)}")
            self.enable_buttons()

    def update_progress(self, message, value):
        """Update progress bar and label"""
        self.progress_label.setText(message)
        self.progress_bar.setValue(value)

    def sync_finished(self):
        """Handle sync completion"""
        try:
            # Clean up finished workers
            self.sync_workers = [w for w in self.sync_workers if w.isRunning()]
            
            # If all workers are done
            if not self.sync_workers:
                self.progress_label.setText("Sync completed!")
                self.progress_bar.setValue(100)
                self.enable_buttons()
                
                # Enable delete button if there are completed files
                if self.completed_files:
                    self.delete_completed_btn.setEnabled(True)
            
        except Exception as e:
            self.log_error(f"Error in sync completion: {str(e)}")
            self.enable_buttons()

    def stop_sync(self):
        """Stop all running sync operations"""
        try:
            for worker in self.sync_workers:
                worker.stop()
                worker.wait()
            self.sync_workers.clear()
            self.progress_label.setText("Sync stopped")
            self.enable_buttons()
            
        except Exception as e:
            self.log_error(f"Error stopping sync: {str(e)}")

    def enable_buttons(self):
        """Re-enable buttons after sync"""
        self.sync_btn.setEnabled(True)
        self.add_folder_btn.setEnabled(True)
        self.remove_folder_btn.setEnabled(self.folder_list.count() > 0)
        self.browse_drive_btn.setEnabled(True)

    def placeholder(self):
        """Temporary placeholder for button clicks"""
        self.error_log.append("This functionality is not yet implemented.")

    def apply_dark_theme(self):
        """Apply dark theme to the application"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2d2d2d;
            }
            QWidget {
                background-color: #2d2d2d;
                color: #d4d4d4;
            }
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #007acc;
                padding: 5px;
                border-radius: 3px;
                color: #d4d4d4;
                min-height: 25px;
            }
            QPushButton:hover {
                background-color: #505050;
                border: 1px solid #007acc;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
            QPushButton:disabled {
                background-color: #3c3c3c;
                border: 1px solid #666666;
                color: #666666;
            }
            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 3px;
                color: #d4d4d4;
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #094771;
            }
            QListWidget::item:hover {
                background-color: #3c3c3c;
            }
            QProgressBar {
                border: 1px solid #007acc;
                border-radius: 3px;
                text-align: center;
                background-color: #1e1e1e;
            }
            QProgressBar::chunk {
                background-color: #007acc;
            }
            QCheckBox {
                spacing: 5px;
                color: #d4d4d4;
            }
            QCheckBox::indicator {
                width: 13px;
                height: 13px;
                border: 1px solid #007acc;
                border-radius: 2px;
                background-color: #1e1e1e;
            }
            QCheckBox::indicator:checked {
                background-color: #007acc;
            }
            QCheckBox::indicator:hover {
                border: 1px solid #3c3c3c;
            }
            QLabel {
                color: #d4d4d4;
            }
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 3px;
                color: #d4d4d4;
                padding: 5px;
            }
        """)
        
        # Keep error log styling separate
        self.error_log.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ff4444;
                border: 1px solid #3c3c3c;
                border-radius: 3px;
                padding: 5px;
            }
        """)

    def show_schedule_dialog(self):
        """Show the schedule dialog"""
        try:
            dialog = ScheduleDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                schedule = dialog.get_schedule()
                self.setup_schedule(schedule)
                self.log_error(f"Backup scheduled: {self.format_schedule(schedule)}")
        except Exception as e:
            self.log_error(f"Error setting schedule: {str(e)}")

    def setup_schedule(self, schedule):
        """Setup the scheduled backup"""
        try:
            # Clear existing timer if any
            if hasattr(self, 'schedule_timer'):
                self.schedule_timer.stop()
            
            # Calculate next run time
            next_run = self.calculate_next_run(schedule)
            
            # Create and start timer
            self.schedule_timer = QTimer()
            self.schedule_timer.timeout.connect(self.run_scheduled_backup)
            
            # Calculate milliseconds until next run
            current_time = QDateTime.currentDateTime()
            msecs_to_next = current_time.msecsTo(next_run)
            
            self.schedule_timer.start(msecs_to_next)
            self.backup_schedule = schedule
            
        except Exception as e:
            self.log_error(f"Error setting up schedule: {str(e)}")

    def calculate_next_run(self, schedule):
        """Calculate the next run time based on schedule"""
        current = QDateTime.currentDateTime()
        time = QTime.fromString(schedule['time'], "HH:mm")
        next_run = QDateTime(current.date(), time)
        
        if schedule['frequency'] == "Daily":
            if next_run <= current:
                next_run = next_run.addDays(1)
        elif schedule['frequency'] == "Weekly":
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", 
                    "Friday", "Saturday", "Sunday"]
            current_day = current.date().dayOfWeek()
            target_day = days.index(schedule['day']) + 1
            days_until = target_day - current_day
            if days_until <= 0 or (days_until == 0 and next_run <= current):
                days_until += 7
            next_run = next_run.addDays(days_until)
        else:  # Monthly
            target_date = schedule['date']
            next_run = next_run.addMonths(1)
            next_run.setDate(target_date)
        
        return next_run

    def run_scheduled_backup(self):
        """Run the scheduled backup"""
        self.sync_now()
        # Setup next run
        if self.backup_schedule:
            self.setup_schedule(self.backup_schedule)

    def format_schedule(self, schedule):
        """Format schedule for display"""
        if schedule['frequency'] == "Daily":
            return f"Daily at {schedule['time']}"
        elif schedule['frequency'] == "Weekly":
            return f"Weekly on {schedule['day']} at {schedule['time']}"
        else:
            return f"Monthly on day {schedule['date']} at {schedule['time']}"

    def move_files(self):
        """Move files from selected folders to a single destination"""
        try:
            # Create default backup directory if it doesn't exist
            default_dir = os.path.expanduser("~/GDrive_One-Backup")
            if not os.path.exists(default_dir):
                os.makedirs(default_dir)
            
            # Ask user for destination
            destination = QFileDialog.getExistingDirectory(
                self,
                "Select Destination Folder",
                default_dir,
                QFileDialog.ShowDirsOnly
            )
            
            if not destination:
                return
            
            # Get all source folders
            source_folders = [self.folder_list.item(i).text() 
                             for i in range(self.folder_list.count())]
            
            if not source_folders:
                self.log_error("No source folders selected")
                return
            
            # Create progress dialog
            progress = QProgressDialog("Moving files...", "Cancel", 0, 100, self)
            progress.setWindowModality(Qt.WindowModal)
            
            # Count total files
            total_files = sum(len(files) for folder in source_folders 
                             for _, _, files in os.walk(folder))
            processed_files = 0
            moved_files = 0
            failed_files = 0
            
            try:
                for source_folder in source_folders:
                    if not os.path.exists(source_folder):
                        self.log_error(f"Source folder not found: {source_folder}")
                        continue

                    for root, _, files in os.walk(source_folder):
                        if progress.wasCanceled():
                            self.log_error("Move operation cancelled")
                            return
                            
                        # Create corresponding subdirectory structure
                        rel_path = os.path.relpath(root, source_folder)
                        dest_dir = os.path.join(destination, os.path.basename(source_folder), rel_path)
                        
                        for file in files:
                            source_file = os.path.join(root, file)
                            dest_file = os.path.join(dest_dir, file)
                            
                            try:
                                # Create directory if it doesn't exist
                                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                                
                                # Check if destination file exists
                                if os.path.exists(dest_file):
                                    base, ext = os.path.splitext(dest_file)
                                    counter = 1
                                    while os.path.exists(f"{base}_{counter}{ext}"):
                                        counter += 1
                                    dest_file = f"{base}_{counter}{ext}"
                                
                                # Copy file first, then delete original if successful
                                shutil.copy2(source_file, dest_file)
                                os.remove(source_file)
                                moved_files += 1
                                self.log_error(f"Moved: {source_file} -> {dest_file}")
                                
                            except Exception as e:
                                failed_files += 1
                                self.log_error(f"Error moving {source_file}: {str(e)}")
                            
                            processed_files += 1
                            progress.setValue(int((processed_files / total_files) * 100))
                
                    # Remove empty directories
                    try:
                        for root, dirs, files in os.walk(source_folder, topdown=False):
                            for dir_name in dirs:
                                dir_path = os.path.join(root, dir_name)
                                if not os.listdir(dir_path):  # if directory is empty
                                    os.rmdir(dir_path)
                    except Exception as e:
                        self.log_error(f"Error cleaning up empty directories: {str(e)}")
                
                # Show completion message
                QMessageBox.information(
                    self,
                    "Move Complete",
                    f"Move operation completed:\n"
                    f"Successfully moved: {moved_files} files\n"
                    f"Failed: {failed_files} files\n\n"
                    f"See error log for details."
                )
                
            finally:
                progress.close()
                
        except Exception as e:
            self.log_error(f"Error during move operation: {str(e)}")
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred during the move operation:\n{str(e)}"
            )

    def delete_completed_files(self):
        """Delete successfully synced files"""
        try:
            reply = QMessageBox.question(
                self,
                'Confirm Deletion',
                'Are you sure you want to delete all successfully synced files? This cannot be undone.',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                deleted_count = 0
                error_count = 0
                
                for file_path in self.completed_files:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            deleted_count += 1
                            self.log_error(f"Deleted: {file_path}")
                    except Exception as e:
                        error_count += 1
                        self.log_error(f"Error deleting {file_path}: {str(e)}")
                
                self.log_error(f"Deletion complete. {deleted_count} files deleted, {error_count} errors.")
                self.completed_files.clear()
                self.delete_completed_btn.setEnabled(False)
                
        except Exception as e:
            self.log_error(f"Error during deletion: {str(e)}")

    def create_tray_icon(self):
        """Create system tray icon and menu"""
        try:
            # Create tray icon
            self.tray_icon = QSystemTrayIcon(self)
            
            # Set icon (you'll need to add an icon file)
            icon = QIcon("icon.png")  # Add your icon file
            if not icon.isNull():
                self.tray_icon.setIcon(icon)
                self.setWindowIcon(icon)
            
            # Create tray menu
            tray_menu = QMenu()
            
            # Add menu items
            show_action = QAction("Show", self)
            show_action.triggered.connect(self.show)
            
            hide_action = QAction("Hide", self)
            hide_action.triggered.connect(self.hide)
            
            quit_action = QAction("Exit", self)
            quit_action.triggered.connect(self.quit_application)
            
            # Add actions to menu
            tray_menu.addAction(show_action)
            tray_menu.addAction(hide_action)
            tray_menu.addSeparator()
            tray_menu.addAction(quit_action)
            
            # Set the menu
            self.tray_icon.setContextMenu(tray_menu)
            
            # Connect double click to show window
            self.tray_icon.activated.connect(self.tray_icon_activated)
            
            # Show the tray icon
            self.tray_icon.show()
            
            # Show notification on startup
            self.tray_icon.showMessage(
                "Google Drive Backup",
                "Application is running in the system tray",
                QSystemTrayIcon.Information,
                2000
            )
            
        except Exception as e:
            print(f"Error creating tray icon: {e}")

    def tray_icon_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.activateWindow()

    def closeEvent(self, event):
        """Handle window close event"""
        if self.tray_icon.isVisible():
            self.hide()
            self.tray_icon.showMessage(
                "Google Drive Backup",
                "Application minimized to tray",
                QSystemTrayIcon.Information,
                2000
            )
            event.ignore()
        else:
            event.accept()

    def quit_application(self):
        """Properly quit the application"""
        # Stop any running operations
        if hasattr(self, 'file_watcher'):
            for path in list(self.file_watcher.watched_paths):
                self.file_watcher.stop_watching(path)
        
        # Stop any running sync workers
        for worker in self.sync_workers:
            worker.stop()
            worker.wait()
        
        # Remove tray icon
        self.tray_icon.hide()
        
        # Quit application
        QApplication.quit()

    def clear_error_log(self):
        """Clear the error log display"""
        self.error_log.clear()

def main():
    try:
        # Create application
        app = QApplication(sys.argv)
        
        # Set application metadata
        app.setApplicationName("Google Drive Backup")
        app.setApplicationDisplayName("Google Drive Backup")
        app.setOrganizationName("GDrive-One-Backup")
        
        # Check if system tray is available
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, "System Tray",
                               "System tray is not available on this system")
            sys.exit(1)
            
        # Set quit on last window closed to False
        app.setQuitOnLastWindowClosed(False)
        
        # Create and show window
        window = DriveBackupGUI()
        window.show()
        
        sys.exit(app.exec_())
        
    except Exception as e:
        print(f"Application error: {e}")
        QMessageBox.critical(None, "Error", f"Application error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
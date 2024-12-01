import os
import json
import shutil
import webbrowser
import psutil
import time

def create_project_structure():
    # Base directory
    base_dir = "GDrive-One-Backup"
    os.makedirs(base_dir, exist_ok=True)
    
    # Create the main implementation file
    with open(os.path.join(base_dir, 'GDrive_One_Backup.py'), 'w', encoding='utf-8') as f:
        # Reference to full implementation from GDrive_One_Backup.py
        f.write('''import sys
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
''')
        # Reference to SyncWorker class
        f.write('''
class SyncWorker(QThread):
''')
        # Reference lines from GDrive_One_Backup.py
        # startLine: 23
        # endLine: 93

        # Reference to GoogleDriveBrowserDialog class
        f.write('''
class GoogleDriveBrowserDialog(QDialog):
    def __init__(self, drive_service, parent=None):
        super().__init__(parent)
        self.drive_service = drive_service
        self.selected_folder = None
        self.setup_ui()
        self.load_folders()

    def setup_ui(self):
        self.setWindowTitle("Select Google Drive Destination")
        layout = QVBoxLayout(self)
        
        # Folder tree
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderLabel("Google Drive Folders")
        layout.addWidget(self.folder_tree)
        
        # New folder button
        self.new_folder_btn = QPushButton("Create New Folder")
        self.new_folder_btn.clicked.connect(self.create_new_folder)
        layout.addWidget(self.new_folder_btn)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_folders(self):
        try:
            results = self.drive_service.files().list(
                q="mimeType='application/vnd.google-apps.folder'",
                spaces='drive',
                fields='files(id, name, parents)'
            ).execute()
            
            folders = results.get('files', [])

        except Exception as e:
            print(f"An error occurred: {e}")

    def populate_tree(self, folders):
        self.folder_tree.clear()
        folder_map = {}
        root_items = []

        # Create QTreeWidgetItems for all folders
        for folder in folders:
            item = QTreeWidgetItem([folder['name']])
            item.setData(0, Qt.UserRole, folder)
            folder_map[folder['id']] = item
            
            # If folder has no parent, it's a root folder
            if 'parents' not in folder:
                root_items.append(item)
            else:
                # Add to parent if it exists
                parent_id = folder['parents'][0]
                if parent_id in folder_map:
                    folder_map[parent_id].addChild(item)
                else:
                    root_items.append(item)

        # Add root items to tree
        self.folder_tree.addTopLevelItems(root_items)
        self.folder_tree.itemClicked.connect(self.on_folder_selected)

    def on_folder_selected(self, item):
        self.selected_folder = item.data(0, Qt.UserRole)

def hide_console():
    """Hide the console window"""
    whnd = ctypes.windll.kernel32.GetConsoleWindow()
    if whnd != 0:
        ctypes.windll.user32.ShowWindow(whnd, 0)

def main():
    # Hide console window
    hide_console()
    
    # Enable high DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    window = DriveBackupGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
''')

    # Create launcher.pyw
    with open(os.path.join(base_dir, 'launcher.pyw'), 'w', encoding='utf-8') as f:
        # Reference lines from launcher.pyw
        # startLine: 1
        # endLine: 16

    # Create requirements.txt
    with open(os.path.join(base_dir, 'requirements.txt'), 'w', encoding='utf-8') as f:
        # Reference lines from requirements.txt
        # startLine: 1
        # endLine: 5

    # Create empty configuration files
    with open(os.path.join(base_dir, 'backup_config.json'), 'w', encoding='utf-8') as f:
        f.write('{}')
    
    with open(os.path.join(base_dir, 'credentials.json'), 'w', encoding='utf-8') as f:
        f.write('{}')

    # Create __init__.py
    with open(os.path.join(base_dir, '__init__.py'), 'w', encoding='utf-8') as f:
        f.write('from .GDrive_One_Backup import DriveBackupGUI, QApplication, Qt')

    # Create documentation files
    with open(os.path.join(base_dir, 'README.md'), 'w', encoding='utf-8') as f:
        # Reference lines from README.md
        # startLine: 1
        # endLine: 3

    with open(os.path.join(base_dir, 'README.txt'), 'w', encoding='utf-8') as f:
        # Reference lines from README.txt
        # startLine: 1
        # endLine: 84

    with open(os.path.join(base_dir, 'README.html'), 'w', encoding='utf-8') as f:
        # Reference lines from README.html
        # startLine: 1
        # endLine: 116

    # Create docs directory
    docs_dir = os.path.join(base_dir, 'docs', 'images')
    os.makedirs(docs_dir, exist_ok=True)

    print(f"Project structure created in: {os.path.abspath(base_dir)}")
    print("\nNext steps:")
    print("1. Install requirements: pip install -r requirements.txt")
    print("2. Add your Google Cloud credentials to credentials.json")
    print("3. Run launcher.pyw to start the application")

if __name__ == "__main__":
    create_project_structure()
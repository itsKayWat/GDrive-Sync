import PyInstaller.__main__
import sys

if __name__ == "__main__":
    sys.setrecursionlimit(5000)
    PyInstaller.__main__.run([
        'DriveBackupGUI.py',
        '--name=GDrive-One-Backup',
        '--onefile',
        '--windowed',  # This prevents the console window from showing
        '--icon=icon.ico',  # Add your icon file
        '--add-data=credentials.json;.',
        '--noconsole'
    ])
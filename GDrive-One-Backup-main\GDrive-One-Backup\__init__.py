# __init__.py for the main package
from .GDrive_One_Backup import GoogleDriveBrowserDialog, DriveBackupGUI, SyncWorker

__version__ = '1.0.0'
__author__ = 'Your Name'

# Export main classes
__all__ = ['GoogleDriveBrowserDialog', 'DriveBackupGUI', 'SyncWorker']
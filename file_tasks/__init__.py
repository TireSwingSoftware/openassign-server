# PowerReg
import facade

# Register our managers, models and subsystems.
facade.models.add_import('FileDownload', 'file_tasks.models')
facade.models.add_import('FileDownloadAttempt', 'file_tasks.models')
facade.managers.add_import('FileDownloadManager','file_tasks.managers')
facade.managers.add_import('FileDownloadAttemptManager','file_tasks.managers')

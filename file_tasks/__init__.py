# PowerReg
import facade

# Register FileDownload managers and models.
facade.models.add_import('FileDownload', 'file_tasks.models')
facade.models.add_import('FileDownloadAttempt', 'file_tasks.models')
facade.managers.add_import('FileDownloadManager','file_tasks.managers')
facade.managers.add_import('FileDownloadAttemptManager','file_tasks.managers')

# Register FileUpload managers and models.
facade.models.add_import('FileUpload', 'file_tasks.models')
facade.models.add_import('FileUploadAttempt', 'file_tasks.models')
facade.managers.add_import('FileUploadManager','file_tasks.managers')
facade.managers.add_import('FileUploadAttemptManager','file_tasks.managers')

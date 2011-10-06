# PowerReg
import facade

# Register our managers, models and subsystems.
facade.managers.add_import('FileDownloadManager','file_tasks.managers')
facade.models.add_import('FileDownload', 'file_tasks.models')
facade.subsystems.override('Authorizer', 'file_tasks.authorizer')

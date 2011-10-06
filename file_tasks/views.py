# Python
import logging
import traceback

# Django
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse

# PowerReg
import facade
from pr_services import exceptions
from pr_services.utils import upload
from pr_services.utils import Utils

# Upload Queue
from upload_queue import prepare_upload

# File Tasks
from file_tasks.forms import FileDownloadForm

@transaction.commit_manually
def upload_file_for_download(request, auth_token=None):
    """Handle video file uploads

    This method will stick the contents of the uploaded file (of which there
    must be exactly 1) into the database through a Video object.  There is
    currently no validation of the Video.

    :param request: HttpRequest object from Django
    :type request:  HttpRequest

    """
    file_download_manager = facade.managers.FileDownloadManager()
    try:
        if request.method == 'GET':
            transaction.rollback()
            return upload._render_response(request, 'file_tasks/upload_video_for_download.html',
                {'form': FileDownloadForm(initial={'auth_token': auth_token})})
        elif request.method == 'POST':
            form = FileDownloadForm(data=request.POST, files=request.FILES)
            if form.is_valid():
                at = Utils.get_auth_token_object(auth_token or form.cleaned_data['auth_token'])
                at.domain_affiliation.user = at.domain_affiliation.user.downcast_completely()
                file_download = file_download_manager.create(at,
                    form.cleaned_data['name'],
                    form.cleaned_data['description'])
                file_download.file_size = form.files['file_data'].size
                file_download.save()
                # Commit the transaction before queuing a task to work on
                # our new Video object.
                transaction.commit()
                if getattr(settings, 'FILE_TASKS_ENABLE_UPLOAD_WORKFLOW', True):
                    # Queue the task to upload the video to S3.
                    pending = prepare_upload(file_download, 'file_data',
                        'file_downloads/%d.src' % file_download.id,
                        form.files['file_data'])
                    transaction.commit()
                    pending.queue()
                if auth_token:
                    return upload._render_response_ok(request,
                        msg='File upload successful.')
                else:
                    # for plain POST requests (old way), still return the ID.
                    return HttpResponse(str(file_download.id) if file_download else None)
            else:
                logging.info(str(form.errors))
                return upload._render_response(request, 'file_tasks/upload_video_for_download.html',
                    {'form': form}, status=400)
    except exceptions.PrException, p:
        transaction.rollback()
        log_message = u'UploadManager.upload_video: pr exception code %d, msg [%s], details [%s]' %\
            (p.get_error_code(), p.get_error_msg(), unicode(p.get_details()))
        logging.info(log_message)
        if p.error_code == 46: # InternalErrorException
            stack_trace = traceback.format_exc()
            logging.info(stack_trace)
            return upload._render_response_server_error(request, msg=p.get_error_msg())
        elif p.error_code in [17, 23, 49, 114, 115, 128]:
            return upload._render_response_forbidden(request, msg=p.get_error_msg())
        else:
            return upload._render_response_bad_request(request, msg=p.get_error_msg())
    except:
        stack_trace = traceback.format_exc()
        logging.info(stack_trace)
        transaction.rollback()
        return upload._render_response_server_error(request, msg='There was an error processing your request.')

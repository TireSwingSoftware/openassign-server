# Python
import logging
import traceback

# Django
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse

# Decorator
from decorator import decorator

# PowerReg
import facade
from pr_services import exceptions
from pr_services.utils import upload
from pr_services.utils import Utils

# Upload Queue
from upload_queue import prepare_upload

# File Tasks
from file_tasks.forms import FileDownloadForm, FileUploadAttemptForm

@decorator
def handle_pr_exception(f, request, *args, **kwargs):
    """Decorator to handle and log PR exceptions from a Django view method."""
    try:
        response = f(request, *args, **kwargs)
    except exceptions.PrException, p:
        transaction.rollback()
        log_message = u'%s.%s: pr exception code %d, msg [%s], details [%s]' % \
                (__name__, f.__name__, p.get_error_code(), p.get_error_msg(),
                unicode(p.get_details()))
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
    else:
        return response

@transaction.commit_manually
@handle_pr_exception
def upload_file_for_download(request, auth_token=None, pk=None):
    """Handle file uploads for the FileDownload Task.

    :param request:     HttpRequest object from Django
    :type request:      HttpRequest
    :param auth_token:  AuthToken from URL path
    :type auth_token:   string or None
    :param pk           FileDownload PK from URL path
    :type pk            int or None
    """
    file_download_manager = facade.managers.FileDownloadManager()
    if request.method == 'GET':
        transaction.rollback()
        if auth_token and pk:
            at = Utils.get_auth_token_object(auth_token)
            at.domain_affiliation.user = at.domain_affiliation.user.downcast_completely()
            results = file_download_manager.get_filtered(at, {'exact': {'id': pk}},
                ['id', 'name', 'description'])
            instance = facade.models.FileDownload.objects.get(pk=results[0]['id'])
        else:
            instance = None
        return upload._render_response(request, 'file_tasks/upload_file.html',
            {'form': FileDownloadForm(initial={'auth_token': auth_token, 'id': pk}, instance=instance)})
    elif request.method == 'POST':
        form = FileDownloadForm(data=request.POST, files=request.FILES)
        if form.is_valid():
            pk = pk or form.cleaned_data['id']
            at = Utils.get_auth_token_object(auth_token or form.cleaned_data['auth_token'])
            at.domain_affiliation.user = at.domain_affiliation.user.downcast_completely()
            if pk:
                file_download = file_download_manager.update(at, pk, {
                    'name': form.cleaned_data['name'],
                    'description': form.cleaned_data['description'],
                    })
            else:
                file_download = file_download_manager.create(at,
                    form.cleaned_data['name'],
                    form.cleaned_data['description'])
            file_download.file_size = form.files['file_data'].size
            file_download.save()
            transaction.commit()
            pending = prepare_upload(file_download, 'file_data',
                'file_downloads/%d__%s' % (file_download.id, form.files['file_data'].name),
                form.files['file_data'])
            transaction.commit()
            pending.queue()
            if auth_token:
                return upload._render_response_ok(request,
                    msg='File upload successful.')
            else:
                return HttpResponse(str(file_download.id) if file_download else None)
        else:
            logging.info(str(form.errors))
            return upload._render_response(request, 'file_tasks/upload_file.html',
                {'form': form}, status=400)

@transaction.commit_manually
@handle_pr_exception
def upload_file(request, auth_token=None, pk=None):
    """Handle file uploads to complete a FileUploadAttempt.

    :param request:     HttpRequest object from Django
    :type request:      HttpRequest
    :param auth_token:  AuthToken from URL path
    :type auth_token:   string or None
    :param pk:          FileUpload PK from URL path
    :type pk:           int or None
    """
    file_upload_attempt_manager = facade.managers.FileUploadAttemptManager()
    if request.method == 'GET':
        transaction.rollback()
        return upload._render_response(request, 'file_tasks/upload_file.html',
            {'form': FileUploadAttemptForm(initial={'auth_token': auth_token, 'id': pk})})
    elif request.method == 'POST':
        form = FileUploadAttemptForm(data=request.POST, files=request.FILES)
        if form.is_valid():
            pk = pk or form.cleaned_data['id']
            at = Utils.get_auth_token_object(auth_token or form.cleaned_data['auth_token'])
            at.domain_affiliation.user = at.domain_affiliation.user.downcast_completely()
            file_upload_attempt_dict = file_upload_attempt_manager.register_file_upload_attempt(at, pk)
            file_upload_attempt = facade.models.FileUploadAttempt.objects.get(pk=file_upload_attempt_dict['id'])
            file_upload_attempt.file_size = form.files['file_data'].size
            file_upload_attempt.save()
            transaction.commit()
            pending = prepare_upload(file_upload_attempt, 'file_data',
                'file_uploads/%d__%s' % (file_upload_attempt.id, form.files['file_data'].name),
                form.files['file_data'])
            transaction.commit()
            pending.queue()
            if auth_token:
                return upload._render_response_ok(request,
                    msg='File upload successful.')
            else:
                return HttpResponse(str(file_upload_attempt.id) if file_upload_attempt else None)
        else:
            logging.info(str(form.errors))
            return upload._render_response(request, 'file_tasks/upload_file.html',
                {'form': form}, status=400)

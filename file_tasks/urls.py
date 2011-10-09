# Django
from django.conf.urls.defaults import patterns, url

urlpatterns = patterns('file_tasks.views',
    # Upload a file for a FileDownload Task.
    url(r'^upload_file_for_download/(?P<auth_token>[A-Za-z0-9]{32})/(?P<pk>[0-9]+?/)??$',
        'upload_file_for_download', name='upload_file_for_download_form'),
    url(r'^upload_file_for_download/$', 'upload_file_for_download',
        name='upload_file_for_download'),
)

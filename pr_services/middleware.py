# Based on: http://code.djangoproject.com/wiki/CookBookThreadlocalsAndUser

try:
    from threading import local
except ImportError:
    from django.utils._threading_local import local

_thread_locals = local()

def get_current_request():
    """
    Return the current request object from thread local storage.
    """
    return getattr(_thread_locals, 'request', None)

def get_client_ip():
    # adapted from solution at 
    # http://stackoverflow.com/questions/4581789/how-do-i-get-user-ip-address-in-django
    request = get_current_request()
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[-1].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


class ThreadLocal(object):
    """
    Middleware that stores the request object to thread local storage.
    """

    def process_request(self, request):
        """
        Store the request objects on the incoming request.
        """
        _thread_locals.request = request

    def process_response(self, request, response):
        """
        Remove the request object from this thread after the request.
        """
        if hasattr(_thread_locals, 'request'):
            del _thread_locals.request
        return response

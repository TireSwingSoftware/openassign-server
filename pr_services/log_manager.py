import logging
import facade
import exceptions
from pr_services.object_manager import ObjectManager
from pr_services.middleware import get_current_request
from pr_services.rpc.service import public_service_method
from pr_services.authorizer.checks.auth import actor_is_guest

class LogManager(object):
    """
    Allow a client to log to our general logging facilities. Messages are logged
    with a Logger named "client.username". The message will already contain
    the username and IP address.
    """

    authorizer = facade.subsystems.Authorizer()

    @public_service_method
    def critical(self, auth_token, message):
        """
        Log a message with level CRITICAL. Requires a valid auth_token or
        logging permission as a guest.

        @param message  string containing a message to be logged
        """

        self._log(auth_token, logging.CRITICAL, message)

    @public_service_method
    def error(self, auth_token, message):
        """
        Log a message with level ERROR. Requires a valid auth_token or logging
        permission as a guest.

        @param message  string containing a message to be logged
        """

        self._log(auth_token, logging.ERROR, message)

    @public_service_method
    def warning(self, auth_token, message):
        """
        Log a message with level WARNING. Requires a valid auth_token or
        logging permission as a guest.

        @param message  string containing a message to be logged
        """

        self._log(auth_token, logging.WARNING, message)

    @public_service_method
    def info(self, auth_token, message):
        """
        Log a message with level INFO. Requires a valid auth_token or logging
        permission as a guest.

        @param message  string containing a message to be logged
        """

        self._log(auth_token, logging.INFO, message)

    @public_service_method
    def debug(self, auth_token, message):
        """
        Log a message with level DEBUG. Requires a valid auth_token or logging
        permission as a guest.

        @param message  string containing a message to be logged
        """

        self._log(auth_token, logging.DEBUG, message)

    def _log(self, auth_token, level, message):
        """
        Log a message with the specified level.
        """

        if self.authorizer.actor_is_guest(auth_token):
            request = get_current_request()
            if request and 'REMOTE_ADDR' in request.META:
                ip_address = request.META['REMOTE_ADDR']
            else:
                ip_address = '0.0.0.0'
        else:
            ip_address = auth_token.ip
        if isinstance(message, basestring) and isinstance(level, int):
            self._get_logger(auth_token).log(level, '%s: %s' % (ip_address, message))
        else:
            raise exceptions.ValidationException

    def _get_logger(self, auth_token):
        """
        Make sure the user has permission to log, and if so, return a
        Logger instance.
        """

        self.authorizer.check_arbitrary_permissions(auth_token, 'logging')
        if self.authorizer.actor_is_guest(auth_token):
            username = 'guest'
        else:
            username = auth_token.user.username
        return logging.getLogger('client.%s' % (username))


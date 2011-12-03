"""
Note manager class
"""

from object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade

class NoteManager(ObjectManager):
    """
    Manage Notes in the Power Reg system.

    Notes are created here and then associated with
    objects by modifying their 'notes' attributes.
    """
    GETTERS = {
        'text': 'get_general',
        # We don't allow Notes about Notes, but it would be a
        # lot funnier if we did
        'notes': None,
    }
    SETTERS = {
        'text': 'set_general',
        'notes': None,
    }
    def __init__(self):
        """ constructor """
        ObjectManager.__init__(self)
        self.my_django_model = facade.models.Note

    @service_method
    def create(self, auth_token, text):
        """
        Create a new Note.  After creating a note, be sure to associate it with
        the object(s) it pertains to.

        @param auth_token   The authentication token of the acting user
        @type auth_token    unicode
        @param text         The Note text
        @type text          unicode
        @return             The primary key of the new Note
        @rtype              models.Note (as dict)
        """
        n = self.my_django_model(text=text)
        n.save()
        self.authorizer.check_create_permissions(auth_token, n)
        return n

# vim:tabstop=4 shiftwidth=4 expandtab

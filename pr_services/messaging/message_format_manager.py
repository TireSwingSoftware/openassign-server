"""
message format manager class
"""

from pr_services.object_manager import ObjectManager
import facade

class MessageFormatManager(ObjectManager):
    """
    Manage Message Formats in the Power Reg system
    """
    GETTERS = {
        'slug': 'get_general',
    }
    SETTERS = {}
    my_django_model = facade.models.MessageFormat

# vim:tabstop=4 shiftwidth=4 expandtab

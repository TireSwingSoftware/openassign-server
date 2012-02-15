"""
message type manager class
"""

from pr_services.object_manager import ObjectManager
import facade

class MessageTypeManager(ObjectManager):
    """
    Manage Message Types in the Power Reg system
    """
    GETTERS = {
        'description': 'get_general',
        'enabled': 'get_general',
        'name': 'get_general',
        'slug': 'get_general',
    }
    SETTERS = {
        'slug': 'set_general',
    }
    my_django_model = facade.models.MessageType

# vim:tabstop=4 shiftwidth=4 expandtab

"""
message template manager class
"""

from pr_services.object_manager import ObjectManager
from pr_services.utils import Utils
from pr_services.rpc.service import service_method
import facade

class MessageTemplateManager(ObjectManager):
    """
    Manage Message Templates in the Power Reg system
    """
    GETTERS = {
        'body': 'get_general',
        'message_format': 'get_foreign_key',
        'message_type': 'get_foreign_key',
        'subject': 'get_general',
    }
    SETTERS = {
        'body': 'set_general',
        'subject': 'set_general',
    }
    my_django_model = facade.models.MessageTemplate

    @service_method
    def detail_view(self, auth_token, filters, fields=None):
        # merge default fields into provided fields
        fields = list(set(fields or []) | set(['body', 'message_format', 'message_type', 'subject']))
        templates = self.get_filtered(auth_token, filters, fields)

        templates = Utils.merge_queries(templates, facade.managers.MessageTypeManager(),
            auth_token, ['enabled', 'description', 'name', 'slug'], 'message_type')

        return Utils.merge_queries(templates, facade.managers.MessageFormatManager(), auth_token,
            ['slug'], 'message_format')

# vim:tabstop=4 shiftwidth=4 expandtab

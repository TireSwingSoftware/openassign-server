"""
VideoCategoryManager class
"""

__docformat__ = "restructuredtext en"

import facade
from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
from pr_services.utils import Utils

class VideoCategoryManager(ObjectManager):
    """
    Manage VideoCategories in the Power Reg system.
    """
    GETTERS = {
        'category': 'get_foreign_key',
        'category_name': 'get_general',
        'status': 'get_general',
        'video': 'get_foreign_key',
    }
    SETTERS = {
        'status': 'set_general',
    }
    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.my_django_model = facade.models.VideoCategory


# vim:tabstop=4 shiftwidth=4 expandtab

import uuid as _uuid
from pr_messaging import signals as _signals
from . import handlers as _handlers

# Add the dispatch_uid when connecting a signal.
_connect = lambda x, y: x.connect(y, dispatch_uid=str(_uuid.uuid4()))

# Connect handlers to messaging app signals.
_connect(_signals.participant_instance_requested, _handlers.pr_user_instance_requested)
_connect(_signals.participant_contact_requested, _handlers.pr_user_contact_requested)

"""Signal initialization and helper functions."""

from . import signals as _signals

# Helper functions for use by other apps.
def send_message(**kwargs):
    """
    If "sender" is in kwagrs, that is the entity which is sending a message,
    such as would appear in the email's FROM field. This is different from the
    "sender" parameter that must be passed to the signals' send() method. In the
    latter case, this is a required concept of Django Signals. This is why we must
    rename any "sender" parameter found in kwargs to "sender_". However, if the
    calling code wants to specify the Django Signals sender, they can apparently
    pass a value for "_sender". This should probably be renamed to minimize
    confusion.

    Please note that the message sender should almost never be a user, but
    should probably be an email address associated with the system.
    settings.DEFAULT_FROM_EMAIL is the default and usually a good choice. In a
    world with SPF, DKIM, etc., we should not be sending email on behalf of a
    domain we don't control.
    """
    if 'sender' in kwargs:
        kwargs['sender_'] = kwargs.pop('sender')
    sender = kwargs.pop('_sender', send_message)
    responses = _signals.message_ready_to_send.send(sender, **kwargs)
    return any([r[1] for r in responses])

def message_admins(**kwargs):
    from django.conf import settings
    kwargs['sender'] = settings.SERVER_EMAIL
    kwargs['recipients'] = list(settings.ADMINS)
    return send_message(_sender=message_admins, **kwargs)

def message_managers(**kwargs):
    from django.conf import settings
    kwargs['sender'] = settings.SERVER_EMAIL
    kwargs['recipients'] = list(settings.MANAGERS)
    return send_message(_sender=message_managers, **kwargs)

def enable_messages(**kwargs):
    responses = _signals.message_flags_update.send(enable_messages, **kwargs)
    return any([r[1] for r in responses])

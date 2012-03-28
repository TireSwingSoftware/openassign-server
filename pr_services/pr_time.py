"""
This modules deals with time and date conversion
"""

from django.utils import timezone

import datetime
import iso8601
import exceptions

def UTC():
    return timezone.utc

def iso8601_to_datetime(time):
    """
    Convert an ISO8601 string to a python datetime object.

    @param time       ISO8601 string
    @return           python datetime object without tzinfo
    """

    try:
        time_stamp = iso8601.parse(time)
    except ValueError:
        raise exceptions.DatetimeConversionError()

    d = datetime.datetime.utcfromtimestamp(time_stamp)
    return timezone.make_aware(d, timezone.utc)

def is_iso8601(time):
    """
    Return true if time is a valid iso8601 time value.

    @param time   the time we wish to validate
    @return       boolean False if it is invalid, else True
    """

    try:
        iso8601.parse(time)
    except ValueError:
        return False

    return True

# vim:tabstop=4 shiftwidth=4 expandtab

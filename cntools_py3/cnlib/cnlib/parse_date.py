#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
date parsing functionality
"""

# imports
import argparse
import calendar
import datetime
import sys
import time
from .formatting import format_table
from dateutil.parser import parse


__all__ = ['is_dst',
           'timezone',
           'epoch2local',
           'epoch2utc',
           'parse_date',
           'parse_utc',
           'convert_to_timedelta'
       ]


def is_dst(localtime=None):
    """returns if daylight savings time is in effect locally"""
    return time.localtime(localtime).tm_isdst > 0


def timezone(localtime=None):
    """returns name of local timezone"""
    return time.tzname[int(is_dst(localtime))]


def epoch2local(datestamp):
    """convert epoch to local time"""
    return datetime.datetime.fromtimestamp(float(datestamp))


def epoch2utc(datestamp):
    """convert epoch to UTC"""
    return datetime.datetime.utcfromtimestamp(float(datestamp))


def parse_date(datestamp, utc=False):
    """returns seconds since epoch from the supplied date"""

    try:
        # already epoch timestamp
        return float(datestamp)
    except ValueError:
        pass

    # parse the string
    parsed_date = parse(datestamp)

    # convert this to seconds since epoch
    if utc:
        return float(calendar.timegm(parsed_date.timetuple()))
    else:
        return time.mktime(parsed_date.timetuple())


def parse_utc(datestamp):
    """parse a datestamp (string) and return a datetime object in UTC"""
    return epoch2utc(parse_date(datestamp, utc=True))


def convert_to_timedelta(time_val):
    """
    Given a *time_val* (string) such as '5d', returns a timedelta object
    representing the given value (e.g. timedelta(days=5)).  Accepts the
    following '<num><char>' formats:
    =========   ======= ===================
    Character   Meaning Example
    =========   ======= ===================
    s           Seconds '60s' -> 60 Seconds
    m           Minutes '5m'  -> 5 Minutes
    h           Hours   '24h' -> 24 Hours
    d           Days    '7d'  -> 7 Days
    =========   ======= ===================
    From:
    http://code.activestate.com/recipes/577894-convert-strings-like-5d-and-60s-to-timedelta-objec/
    Examples::
        >>> convert_to_timedelta('7d')
        datetime.timedelta(7)
        >>> convert_to_timedelta('24h')
        datetime.timedelta(1)
        >>> convert_to_timedelta('60m')
        datetime.timedelta(0, 3600)
        >>> convert_to_timedelta('120s')
        datetime.timedelta(0, 120)
    """
    num = int(time_val[:-1])
    mapping = {'s': 'seconds',
               'm': 'minutes',
               'h': 'hours',
               'd': 'days'}
    last_char = time_val[-1]
    if last_char not in mapping:
        raise Exception("Cannot convert to timedelta: {}".format(time_val))
    return datetime.timedelta(**{mapping[last_char]: num})



def main(args=sys.argv[1:]):

    # parse command line
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('date', nargs='*',
                        help="local date to parse, or now if none given")
    parser.add_argument('--utc', dest='utc',
                        action='store_true', default=False,
                        help="indicate date is in UTC")
    options = parser.parse_args(args)

    if not options.date:
        options.date = [str(time.time())]

    # parse each date
    epochs = [parse_date(d, options.utc) for d in options.date]

    # display results
    header = ['epoch', 'local', 'UTC']
    print (format_table([[d, '{} {}'.format(epoch2local(d), timezone(d)), epoch2utc(d)] for d in epochs],
                        header=header, joiner='|'))


if __name__ == '__main__':
    main()

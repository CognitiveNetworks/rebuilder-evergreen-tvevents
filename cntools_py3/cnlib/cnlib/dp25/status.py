#!/usr/bin/env python
"""
Status for Data Pipeline 2.5.
"""
import argparse
from datetime import datetime, timedelta
import redis
import sys

from cnlib.cnredis import Clusters, Databases

__author__ = 'Alex Roitman <alex.roitman@cognitivenetworks.com>'

string = (str, unicode)

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
KEY_TEMPLATE = '{zoo}:{hour}:{pipe}'

STATUS_NAMES = {
    True: 'pending',
    False: 'done',
}


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs['description'] = """
        Query the status of the DP25 processing for specific time chunks.

        The response answers the question:
        'Is there anything still pending for the given time chunks?'

        If the exit status is zero, everything is done.
        If the exit status is non-zero, either something is pending,
        or there was an error with the query.
        """
        argparse.ArgumentParser.__init__(self, *args, **kwargs)

        self.add_argument(
            '-z', '--zoo', dest='zoo',
            default=None, required=True,
            help='Zoo name.')

        self.add_argument(
            '-t', '--time-chunk', dest='times',
            default=[], required=True, nargs='+', metavar='time',
            help='Time chunk.  Acceptable chunks are an HOUR or a DAY.\n'
                 'HOUR format must be yyyy-mm-dd_HH, '
                 'e.g. 2015-03-04_17 for the hour between 5pm and 6pm UTC '
                 'on March 4, 2015.\n'
                 'DAY format must be yyyy-mm-dd, '
                 'e.g. 2015-03-04 for the UTC day of March 4, 2015.\n'
                 'If several time chunks are given, '
                 'the resulting status refers to any of them being pending '
                 'versus all done.')

        self.add_argument(
            '-p', '--pipe', dest='pipe',
            choices=('content', 'comm', 'event', 'attr_comm'),
            default='content',
            help='Pipe name [DEFAULT: %(default)s].')
        self.add_argument(
            '--host', dest='host',
            default=Clusters.DATA['read'],
            help='Redis read-only host name [DEFAULT: %(default)s].')
        self.add_argument(
            '--quiet', '-q',
            dest='quiet', action='store_true',
            default=False,
            help='Be quiet, produce no output. '
                 'The caller must rely on the exit status.')

    def parse_args(self, *args, **kwargs):
        options = argparse.ArgumentParser.parse_args(self, *args, **kwargs)
        self.validate(options)
        self.options = options
        return options

    def validate(self, options):
        if not options.zoo:
            self.error('Empty zoo name.')

        if not options.host:
            self.error('Empty host.')

        now = datetime.utcnow()
        for time_str in options.times:
            self.validate_time(time_str, now)

    def validate_time(self, time_str, now):
        try:
            if '_' in time_str:
                date = datetime.strptime(time_str, '%Y-%m-%d_%H')
                end = date + HOUR
            else:
                date = datetime.strptime(time_str, '%Y-%m-%d')
                end = date + DAY

            if end > now:
                self.error(
                    'The end of this time chunk is in the future: {}'.format(
                        time_str))

        except ValueError:
            self.error('Invalid date: {}'.format(time_str))


def query(redis_handler, zoo, pipe, times, quiet=False):
    hour_list = []
    for time_chink in times:
        if '_' in time_chink:
            hour_list.append(
                KEY_TEMPLATE.format(zoo=zoo, pipe=pipe, hour=time_chink))
        else:
            hour_list.extend(make_daily_keys(zoo, pipe, time_chink))

    results = query_keys(redis_handler, hour_list)
    if not quiet:
        for key, result in zip(hour_list, results):
            print ('{}: {}'.format(key, STATUS_NAMES[result]))

    return any(results)


def make_daily_keys(zoo, pipe, day):
    return [
        KEY_TEMPLATE.format(
            zoo=zoo, pipe=pipe, hour='%s_%02d' % (day, hour_num))
        for hour_num in range(24)
    ]


def query_keys(redis_handler, keys):
    redis_pipe = redis_handler.pipeline()

    for key in keys:
        redis_pipe.exists(key)

    return redis_pipe.execute()

def query_pipes(zoo, hours, pipes=('content', 'attr_comm'), redis_handler=None):
    """returns if any of the pipes for hours mentioned are still pending for a given zoo"""
    if redis_handler is None:
        redis_handler = redis.StrictRedis(host=Clusters.DATA['read'], db=Databases.DP25_STATUS)
    _hours = set()
    for hour in hours:
        if isinstance(hour, string):
            _hours.add(hour)
            continue
        elif isinstance(hour, (float, int)):
            hour = datetime.utcfromtimestamp(hour)
        _hours.add(hour.strftime("%Y-%m-%d_%H"))
    keys = [KEY_TEMPLATE.format(zoo=zoo, hour=hour, pipe=pipe)
            for pipe in pipes
            for hour in _hours]
    return any(query_keys(redis_handler, keys))


def main(args=sys.argv[1:]):
    parser = Parser(args)
    options = parser.parse_args()
    redis_handler = redis.StrictRedis(
        host=options.host, db=Databases.DP25_STATUS)
    result = query(
        redis_handler, options.zoo, options.pipe, options.times, options.quiet)
    sys.exit(result)


if __name__ == '__main__':
    main()

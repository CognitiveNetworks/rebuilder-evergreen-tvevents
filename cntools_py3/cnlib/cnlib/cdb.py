#!/usr/bin/env python

"""
Client code for talking to CDB web interface
"""

import argparse
import json
import requests
import sys
import os
from .chunks import chunks
from . import log

__all__ = ['CDBInterface']


region = os.getenv('AWS_REGION')
if region == 'eu-west-1':
    BASE_URL = 'https://mcpinterface-eu.cognet.tv'
else:
    BASE_URL = 'https://mcpinterface.cognet.tv'

override_url = os.getenv('MCPINTERFACE_URL')
if override_url:
    BASE_URL = override_url

logger = log.getLogger(__name__)


class CDBInterface(object):

    base_url = BASE_URL
    chunksize = 1000  # existing deployment returns 413 Request Entity Too Large for too many tokens

    def url(self, path):
        return '{}/{}'.format(self.base_url, path)

    @staticmethod
    def payload(*tokens, **properties):
        pld = list(properties.items())
        pld.extend([('tvid', token) for token in tokens])
        return pld

    def get(self, *tokens, **properties):
        if not tokens:
            return []
        payload = self.payload(*tokens, **properties)
        resp = requests.get(self.url('get'), params=payload)
        try:
            return resp.json()
        except Exception as e:
            logger.error("Unexpected error resp:{} {}".format(resp, e))
            return []

    def set(self, *tokens, **properties):
        if not (properties and tokens):
            return []
        payload = self.payload(*tokens, **properties)
        return requests.post(self.url('set'), data=payload).json()

    def set_chunks_lazy(self, *tokens, **properties):
        """
        This method breaks big uploads into chunks
        and provides an iterator over the responses to each chunk.

        NOTE: THIS METHOD IS LAZY!
        the caller will need to iterate through all responses
        to make sure all requests were sent to the CDB server.
        """
        if properties and tokens:
            for _tokens in chunks(tokens, self.chunksize):
                yield self.set(*_tokens, **properties)


class CDBParser(argparse.ArgumentParser):

    def __init__(self, **kwargs):
        kwargs.setdefault('description', __doc__)
        argparse.ArgumentParser.__init__(self, **kwargs)
        self.add_arguments()

    def add_arguments(self):
        self.add_argument('token')
        self.add_argument('--set', dest='set', nargs='+',
                          type=self.dict_type, metavar='PARAM=VALUE',
                          help="set PARAM for token to VALUE")
        self.add_argument('-v', '--verbose', dest='verbose',
                          action='store_true', default=False)

    def dict_type(self, arg):
        if '=' not in arg:
            self.error("Argument requires a '=' delimeter (You gave: {})".format(arg))
        return arg.split('=', 1)


def main(args=sys.argv[1:]):
    """CLI"""

    # parse command line argument
    parser = CDBParser()
    options = parser.parse_args(args)

    # instantiate cdb interface object
    cdb = CDBInterface()

    # do the query
    params = {}
    if options.verbose:
        params['verbose'] = 'True'
    if options.set:
        params.update(dict(options.set))
        data = cdb.set(options.token, **params)
    else:
        data = cdb.get(options.token, **params)

    # output it
    print (json.dumps(data, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()

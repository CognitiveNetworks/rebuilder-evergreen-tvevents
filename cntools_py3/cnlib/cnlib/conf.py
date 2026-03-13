import json
import io
import os.path
from collections import OrderedDict

import yaml
import six

__all__ = ['parse_conf']

ENCODING = 'utf8'

def parse_conf(conf):
    """
    parse a configuration string of the form::

    key=value
    """
    if isinstance(conf, six.binary_type):
        conf = conf.decode(ENCODING)
    d = OrderedDict()
    for line in conf.strip().splitlines():
        k,v = line.split('=', 1)
        d[k] = v
    return d


def load(path):
    root, ext = os.path.splitext(path)
    ext = ext.lower()
    with io.open(path, 'r', encoding=ENCODING) as configfile:
        if ext == '.yaml':
            return yaml.safe_load(configfile)
        elif ext == '.json':
            return json.load(configfile)
        else:
            raise RuntimeError('unknown file type - {}'.format(path))

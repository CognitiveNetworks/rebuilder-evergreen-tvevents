"""
Convert a string tvid of the form 1234567_55554_987654321 to integer 1234567
"""

from . import log

logger = log.getLogger(__name__)


class TVIDException(Exception):
    pass


def trim_tvid(tvid):
    try:
        return int(tvid.split('_')[0])
    except (IndexError, ValueError) as e:
        logger.exception('Unable to truncate tvid {}.'.format(tvid))
        raise TVIDException(e)

import os
import math
import time

from cnlib import log
from .base_redis import BaseRedis, Clusters, Databases

__author__ = 'Yunfan Luo <yunfan.luo@cognitivenetworks.com>'

logger = log.getLogger(__name__)

# Used by global_async_update to figure out
# which keys in ACTIVE_DB count as 'active'
ACTIVE_WINDOW_SEC = 60 * 25
# Used by TVC and global_async_update to figure out
# when to use a new key for ACTIVE_DB
ACTIVE_MOD_SEC = 60 * 5
# This is how long to keep around the unioned active counts
# per zoo when get_active_user_count, get_active_user_tokens,
# get_active_allowed_user_count, and get_active_allowed_user_tokens
# are called
UNIONED_ACTIVE_EXPIRY_SEC = 60


def active_user_count(domain):
    """
    Function kept here for backward compatibility with Alex's stuff
    """
    return ActiveRedis().get_active_allowed_user_count(domain)


class ActiveRedis(BaseRedis):
    """
    Redis class dealing with the chunked time/active database extends BaseRedis
    Used by: TVC, MCP-Interface, global_redis_async_update
    Has functionality for setting key/value pairs in ACTIVE_DB
    """
    # These override the BaseRedis() Connection variables
    READ_SOCKET_CONNECT_TIMEOUT = float(
        os.getenv('ACTIVE_REDIS_READ_SOCKET_CONNECT_TIMEOUT', 30.0))
    READ_SOCKET_TIMEOUT = float(os.getenv('ACTIVE_REDIS_READ_SOCKET_TIMEOUT', 30.0))
    READ_MAX_CONNECTIONS = int(os.getenv('ACTIVE_REDIS_READ_MAX_CONNECTIONS', 250))
    WRITE_SOCKET_CONNECT_TIMEOUT = float(
        os.getenv('ACTIVE_REDIS_WRITE_SOCKET_CONNECT_TIMEOUT', 30.0))
    WRITE_SOCKET_TIMEOUT = float(os.getenv('ACTIVE_REDIS_WRITE_SOCKET_TIMEOUT', 30.0))
    WRITE_MAX_CONNECTIONS = int(os.getenv('ACTIVE_REDIS_WRITE_MAX_CONNECTIONS', 250))

    def __init__(self, write_host=Clusters.ACTIVE['write'],
                 read_host=Clusters.ACTIVE['read'],
                 db=Databases.ACTIVE, active_mod_seconds=ACTIVE_MOD_SEC,
                 active_window_seconds=ACTIVE_WINDOW_SEC,
                 decode_responses=False,
                 retry_on_timeout=False,
                 health_check_interval=0):
        super(ActiveRedis, self).__init__(write_host,
                                          read_host,
                                          db,
                                          decode_responses=decode_responses,
                                          retry_on_timeout=retry_on_timeout,
                                          health_check_interval=health_check_interval)
        self.active_mod_seconds = active_mod_seconds
        self.active_window_seconds = active_window_seconds

    ###########################################################################
    # Instead of storing each user's date_time field individually and counting
    # we create a new active/zoo/time key every 5 minutes and any user that
    # talks to us in that 5 minutes gets added to the value of that key in the
    # form of a set
    ###########################################################################
    def set(self, zoo_name, token, allowed=True, now=None, pipeline=None, redis_prefix='active'):
        """
        Given the user's token and the zoo it's in, add the token
        to an active:<zoo_name>_<timestamp> key's set
        Also, expire the key when setting it
        """
        now = now or time.time()
        modded_now = int(now - math.floor(now % self.active_mod_seconds))
        writer_pipeline = self._writer.pipeline() if pipeline is None else pipeline

        # Constructing the key of 'active:ZOONAME_MODDEDTIME'
        active_key = '{}:{}_{}'.format(redis_prefix, zoo_name, modded_now)
        writer_pipeline.sadd(active_key, token)
        writer_pipeline.expire(active_key, int(self.active_window_seconds))

        if allowed:
            active_allowed_key = '{}_allowed:{}_{}'.format(redis_prefix, zoo_name,
                modded_now)
            writer_pipeline.sadd(active_allowed_key, token)
            writer_pipeline.expire(active_allowed_key, int(self.active_window_seconds))

        # If pipeline was passed, don't execute here and leave it for
        # whoever gave us the pipeline to execute
        # If the pipeline is our own creation though, execute it
        if pipeline is None:
            writer_pipeline.execute()

        # The redis sadd function returns the number of records
        # that were added to the set
        # But since I'm always adding one token at a time...
        # I'd rather know the active_key I just created
        return active_key

    ###########################################################################
    # The following functions have to do with extracting what "active" means
    # out of the time-as-a-key structure
    # Both get_active_user_count and get_active_user_tokens rely on calling
    # set_active_users to do the actual work
    ###########################################################################
    def _get_unioned_key(self, prefix, zoo_name):
        return '{}:{}'.format(prefix, zoo_name)

    def _get_user_count(self, zoo_name, prefix):
        """
        Return the count of active users for given zoo and prefix.
        Actually calls set_active_users, which does most of the work
        """
        active_key_unioned = self._get_unioned_key(prefix, zoo_name)

        reader_pipeline = self._reader.pipeline(transaction=True)
        reader_pipeline.scard(active_key_unioned)
        reader_pipeline.exists(active_key_unioned)
        key_value, key_exists = reader_pipeline.execute()

        if key_exists:
            return key_value

        return self.set_active_users(zoo_name, prefix=prefix)

    def _get_user_tokens(self, zoo_name, prefix):
        """
        Return the list of active users for given zoo and prefix.
        Actually calls set_active_users, which does most of the work
        """
        active_key_unioned = self._get_unioned_key(prefix, zoo_name)

        reader_pipeline = self._reader.pipeline(transaction=True)
        reader_pipeline.smembers(active_key_unioned)
        reader_pipeline.exists(active_key_unioned)
        key_value, key_exists = reader_pipeline.execute()

        if key_exists:
            return list(key_value)

        return list(
            self.set_active_users(zoo_name, prefix=prefix, return_members=True))

    def get_active_user_count(self, zoo_name):
        return self._get_user_count(zoo_name, 'active')

    def get_active_user_tokens(self, zoo_name):
        return self._get_user_tokens(zoo_name, 'active')

    def get_active_allowed_user_count(self, zoo_name):
        return self._get_user_count(zoo_name, 'active_allowed')

    def get_active_allowed_user_tokens(self, zoo_name):
        return self._get_user_tokens(zoo_name, 'active_allowed')

    def set_active_users(self, zoo_name, prefix='active', now=None,
                         return_members=False):
        """
        Given a zoo, generate the set of user tokens that are considered
        "active" according to self.active_window_seconds by unioning all
        <prefix>:<zoo_name>_<timestamp> values where <timestamp> fits

        <prefix> can be either 'active' or 'active_allowed'

        Store the resulting set in a key named <active:zoo_name>
        or in the case of active_allowed, <active_allowed:zoo_name>

        It also so happens that calling sunionstore in Redis returns a count
        """
        now = now or time.time()
        modded_now = int(now - math.floor(now % self.active_mod_seconds))

        # Figure out how many 5-minute chunks we need to include, given
        # the active_window_seconds that was given to this function
        chunks_backward = int(math.ceil(float(self.active_window_seconds /
                                              self.active_mod_seconds)))

        # This constructs a list of keys in redis to union, e.g.:
        #   ['active:control-zoo-yunfan.tvinteractive.tv_1415055300',
        #   'active:control-zoo-yunfan.tvinteractive.tv_1415056200',
        #   'active:control-zoo-yunfan.tvinteractive.tv_1415055600',
        #   'active:control-zoo-yunfan.tvinteractive.tv_1415056500',
        #   'active:control-zoo-yunfan.tvinteractive.tv_1415055900']
        active_keys = [
            '{}:{}_{}'.format(prefix, zoo_name, modded_now -
                              i * self.active_mod_seconds)
            for i in range(chunks_backward)
        ]

        logger.debug("Active counts, modded_now = {}".format(modded_now))
        logger.debug("Active counts, chunks_backward = {}".format(chunks_backward))
        logger.debug("Active counts, active_keys = {}".format(active_keys))

        # Just like the previous keys, but without timestamp:
        #   active:control-zoo-yunfan.tvinteractive.tv
        active_key_unioned = '{}:{}'.format(prefix, zoo_name)

        writer_pipeline = self._writer.pipeline()
        # sunionstore is the redis function that actually does the union
        writer_pipeline.sunionstore(active_key_unioned, active_keys)
        # And expire that key, so others can get a count without recalculating
        # This is a "get" function, but to make union key, need to do a write
        writer_pipeline.expire(active_key_unioned, int(UNIONED_ACTIVE_EXPIRY_SEC))
        if return_members:
            writer_pipeline.smembers(active_key_unioned)
            count, expire_success, members = writer_pipeline.execute()
            return members
        else:
            count, expire_success = writer_pipeline.execute()
            return count

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

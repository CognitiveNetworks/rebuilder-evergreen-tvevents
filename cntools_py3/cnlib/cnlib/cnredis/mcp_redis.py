from .base_redis import BaseRedis, Clusters, Databases
from .. import log

__author__ = 'Yunfan Luo <yunfan.luo@cognitivenetworks.com>'

logger = log.getLogger(__name__)

# When doing scans over all keys, we're given the option of how
# many keys to access per iteration, this will be our default
SCAN_COUNT = 1000
# This is how long to keep around the unioned set of available
# zoos when MCPRedis.get_status() is called
UNIONED_TARGETS_EXPIRY_SEC = 60 * 5


class MCPRedis(BaseRedis):
    """
    MCP-specific class that extends BaseRedis
    Has functionality for setting/getting the status
    """
    ZOOS_KEY = 'zoos'

    def __init__(self, write_host=Clusters.MCP['write'],
                 read_host=Clusters.MCP['read'],
                 db=Databases.MCP,
                 decode_responses=False,
                 retry_on_timeout=False,
                 health_check_interval=0
                 ):
        super(MCPRedis, self).__init__(write_host,
                                       read_host,
                                       db,
                                       decode_responses=decode_responses,
                                       retry_on_timeout=retry_on_timeout,
                                       health_check_interval=health_check_interval
                                       )

    ###########################################################################
    # New functions for short tvid as token hash now has multiple fields
    ###########################################################################

    def hset(self, token, field, value):
        return super(MCPRedis, self).hset('user:{}'.format(token), field, value)

    def hget(self, token, field):
        return super(MCPRedis, self).hget('user:{}'.format(token), field)

    ###########################################################################
    # The following functions call the parent function's implementation
    # with the appropriate prefix
    # Keeps my base class generic and saves me from having to remember prefixes
    # when using the MCPRedis class in practice
    # NOTE: get() has been changed for short tvid
    ###########################################################################
    def set(self, token, zoo, pipeline=None, tvid=None):
        values = {'target': zoo}
        if tvid is not None:
            values['tvid'] = tvid
        logger.debug('setting values: {}'.format(values))
        return super(MCPRedis, self).set(token, values, prefix='user',
                                         pipeline=pipeline)

    def get(self, token):
        # token hash now has multiple fields, need to specifiy 'target'
        # return super(MCPRedis, self).get(token, prefix='user')
        return super(MCPRedis, self).hget('user:{}'.format(token), 'target')

    def hdel(self, token, field):
        return super(MCPRedis, self).hdel('user:{}'.format(token), field)

    def delete(self, token, pipeline=None):
        return super(MCPRedis, self).delete(token, prefix='user',
                                            pipeline=pipeline)

    def expire(self, token, seconds, pipeline=None):
        return super(MCPRedis, self).expire(token, seconds, prefix='user',
                                            pipeline=pipeline)

    def set_index(self, index_key, token, pipeline=None):
        return super(MCPRedis, self).set_index(index_key, token,
                                               prefix='target',
                                               pipeline=pipeline)

    def get_index(self, index_key):
        return super(MCPRedis, self).get_index(index_key, prefix='target')

    def sizeof_index(self, index_key):
        return super(MCPRedis, self).sizeof_index(index_key, prefix='target')

    def delete_index(self, index_key, pipeline=None):
        return super(MCPRedis, self).delete_index(index_key, prefix='target',
                                                  pipeline=pipeline)

    def delete_from_index(self, value_key, pipeline=None):
        return super(MCPRedis, self).delete_from_index(value_key,
                                                       index_prefix='target',
                                                       pipeline=pipeline)

    def delete_by_index(self, index_key, pipeline=None):
        return super(MCPRedis, self).delete_by_index(index_key,
                                                     pipeline=pipeline)

    ###########################################################################
    # The following functions are specific to the MCPRedis class
    ###########################################################################
    def get_zoos(self):
        """
        Return a list of zoo domains.
        """
        return self._reader.smembers(self.ZOOS_KEY)

    def add_zoos(self, *zoos):
        return self._writer.sadd(self.ZOOS_KEY, *zoos)

    def remove_zoos(self, *zoos):
        return self._writer.srem(self.ZOOS_KEY, *zoos)

    def get_status(self, targets=None, prefix='target', verbose=False):
        """
        Return a dictionary containing all zoos and their populations
        and active counts.
        Optionally, select a subset of zoos, also return a list of tokens
        in addition to just counts.
        """
        # If specific targets are passed into this call,
        # only do reverse lookups on them
        # If not, figure out all reverse-lookup keys and reverse lookup on
        # all of them

        if targets:
            logger.debug("Getting status for targets {}".format(targets))
        else:
            logger.debug("Getting status")
            targets = self.get_zoos()

        status = {}
        for target in targets:
            # If passed verbose, return both a count and a list of tokens
            if verbose:
                tvids = self.get_index(target)
                status[target] = {'count': len(tvids), 'users': tvids}
            # If not, just call the counting function
            else:
                target_count = self.sizeof_index(target)
                status[target] = {'count': target_count}

        return status

    def regenerate_indices(self, targets=None, prefix='target'):
        """
        Iterate through every MCP key/value pair, and regenerate
        associated indices.
        TAKES A LONG TIME!
        """
        if targets:
            logger.debug("Recalculate status for targets {}".format(targets))
        else:
            logger.debug("Recalculate status")
        status = {}

        # Clear out all prefix (target) reverse lookups
        for zoo in self.get_zoos():
            self.delete_index(zoo)

        for key in self._reader.scan_iter(count=SCAN_COUNT):
            t = self._reader.type(key)
            if t == 'hash':
                try:
                    this_users_target = self._reader.hgetall(key)[prefix]
                    if this_users_target not in status.keys():
                        status[this_users_target] = {}

                    if not targets or this_users_target in targets:
                        try:
                            status[this_users_target]['count'] += 1
                        except:
                            status[this_users_target]['count'] = 1
                        token = key.split('user:')[1]
                        try:
                            status[this_users_target]['users'].append(token)
                        except:
                            status[this_users_target]['users'] = [token]

                        reverse_key = '{}:{}'.format(prefix, this_users_target)
                        self._writer.sadd(reverse_key, token)

                except Exception as e:
                    logger.exception("Caught exception trying to"
                                     " return status: {}".format(e))

        return status


    ###############################################################################
    # The following functions moved here from cdb_redis to relocate meta:latest_uid
    ###############################################################################
    def generate_next_uid(self, pipeline=None):
        if pipeline is None:
            return self._writer.incr('meta:latest_uid')
        else:
            return pipeline.incr('meta:latest_uid')

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

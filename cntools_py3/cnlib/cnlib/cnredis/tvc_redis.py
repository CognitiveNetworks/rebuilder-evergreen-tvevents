import os

from .base_redis import BaseRedis, Clusters, Databases
from .. import log

__author__ = 'Yunfan Luo <yunfan.luo@cognitivenetworks.com>'

logger = log.getLogger(__name__)

# TVCRedis should be passing its own value for UMP_ASSIGNMENT_EXPIRY
# on initialization
# This is intended to be gbl.LONGNEXTUPDATE/1000 from TVC,
# the number of seconds before a TV comes back
# TVCRedis sets a key/value pair for all active TVs so that until they
# go inactive, they keep being sent to the same UMP
UMP_ASSIGNMENT_EXPIRY_SEC = 60 * 20
# UMP_ASSIGNMENT_EXPIRY_BUFFER is here to give us some buffer
# before expiring that key
UMP_ASSIGNMENT_EXPIRY_BUFFER_SEC = 60
# Keeping tv_count from SQL in Redis
# between UMP's 30-second updates to SQL
UMP_COUNT_EXPIRY_SEC = 60


class TVCRedis(BaseRedis):
    """
    TVC-specific class that extends BaseRedis
    As of now, here just for convenience in defaulting db to TVC_DB_NUM
    """

    def __init__(self, write_host=Clusters.CONTROL['write'],
                 read_host=Clusters.CONTROL['read'], db=Databases.TVC,
                 ump_assignment_expiry=UMP_ASSIGNMENT_EXPIRY_SEC,
                 decode_responses=False,
                 retry_on_timeout=False,
                 health_check_interval=0):
        super(TVCRedis, self).__init__(write_host,
                                       read_host,
                                       db,
                                       decode_responses=decode_responses,
                                       retry_on_timeout=retry_on_timeout,
                                       health_check_interval=health_check_interval)
        self.ump_assignment_expiry = ump_assignment_expiry + \
                                     UMP_ASSIGNMENT_EXPIRY_BUFFER_SEC

    ###########################################################################
    # The following (mostly) override BaseRedis get/set with TVC-specific ones
    # to keep users on the same UMP for their viewing session,
    # and to grab a new UMP when they turn back on through key expiration
    ###########################################################################
    def set(self, token, host, udp_port, http_port, az, ump_id, ump_private_ip="", pipeline=None):
        """
        TVC-specific implementation of the set function.
        All UMP assignments are set to expire after self.ump_assignment_expiry,
        which defaults to 21 minutes, 1 more than "come-back-in-20-minutes"
        that TVC gives to all TVs
        If a TV comes back in 20 minutes, extend expiry by another 21 minutes.
        If it doesn't come back in 20 minutes, we won't find a key when it
        finally does, and it'll get assigned to a new UMP
        """
        assignment_dict = {
            'host': host,
            'ump_private_ip': ump_private_ip,
            'udp_port': udp_port,
            'http_port': http_port,
            'az': az,
            'ump_id': ump_id
        }
        writer_pipeline = self._writer.pipeline() if pipeline is None else pipeline
        super(TVCRedis, self).set(token, assignment_dict, prefix='user',
                                  pipeline=writer_pipeline)
        self.expire(token, self.ump_assignment_expiry, prefix='user',
                    pipeline=writer_pipeline)
        # If the pipeline was our own creation, execute it
        # If not, assume whoever passed it to us will eventuall execute
        if pipeline is None:
            return writer_pipeline.execute()

    def update(self, token, field_name, value, pipeline=None):
        """
        TVC-specific function to update one of the fields created by
        the hmset that TVCRedis's "set" function calls
        This is "used" in TVC where when the TV hits TVC, TVC updates
        its "date_time" field in the user:token key/value.
        (Nobody really looks at that field right now.)
        """
        update_dict = {field_name: value}
        return super(TVCRedis, self).set(token, update_dict, prefix='user',
                                         pipeline=pipeline)

    def get(self, token):
        """
        TVC-specific implementation of the get function.
        Sorry for the misleading name, but in the case of TVC, "getting"
        a value means a TV hit the server and we need to extend the key's life.
        So every get also calls expire, updating the expiry.
        """
        # Expire before getting, to make sure that we don't get
        # an entry right when it expires, and then attempt to expire
        # a nonexistent key
        # Rather we try to expire a nonexistent key first, as it will
        # just fail gracefully
        self.expire(token, self.ump_assignment_expiry, prefix='user')
        return super(TVCRedis, self).get(token, prefix='user')

    def incr_ump_count(self, hostname, limit, increment, base_count, base_ts,
                       timeout=UMP_COUNT_EXPIRY_SEC):
        """
        This functions attempts to increment the count of users on an UMP,
        given the ump, user limit, increment amount, as well as the base
        count and the time of base count (coming from UMP updates in IPDB).

        Return 1 if the count was incremented, 0 otherwise.
        Returning 0 means that incrementing this UMP by a given increment
        would put it over the limit.
        """
        script = """
            local count, base_count, base_ts = unpack(
                redis.call(
                    'hmget', KEYS[1], 'count', 'base_count', 'base_ts'));

            local cur = tonumber(base_ts or '0') >= tonumber(ARGV[4]);
            local real_count = cur and tonumber(count) or tonumber(ARGV[3]);

            if real_count + tonumber(ARGV[2]) > tonumber(ARGV[1]) then
                return 0;
            end

            if cur then
                redis.call('hincrby', KEYS[1], 'count', ARGV[2]);

            else
                redis.call('hmset', KEYS[1],
                           'count', ARGV[2] + ARGV[3],
                           'base_count', ARGV[3],
                           'base_ts', ARGV[4]);
                redis.call('expire', KEYS[1], ARGV[5]);
            end
            return 1;
        """
        return self._writer.eval(
            ' '.join(script.split()),
            1,
            'ump:{}'.format(hostname),
            limit,
            increment,
            base_count,
            base_ts,
            timeout)

    def __get_queue_suffix(self, name):

        suffix = name

        try:
            zoo = os.environ["ZOO"]
        except KeyError:
            pass
        else:
            suffix += ":{zoo}".format(zoo=zoo)

        return suffix

    def push(self, name, *values):
        """
        Queue key name after base class = "queue:<name>:<zoo>"
        """
        suffix = self.__get_queue_suffix(name)
        return super(TVCRedis, self).push(suffix, *values)

    def push_to(self, key, *values):
        """
        Raw method to push to specified key in case user needs access to
        actual key name
        """
        return super(TVCRedis, self).push_to(key, *values)

    def pop(self, name):
        suffix = self.__get_queue_suffix(name)
        return super(TVCRedis, self).pop(suffix)

    def pop_from(self, key):
        """
        Raw method to pop with specified key in case user needs access to
        actual key name
        """
        return super(TVCRedis, self).pop_from(key)

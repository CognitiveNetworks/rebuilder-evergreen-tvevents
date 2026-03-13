"""
Represents the data objects in active-redis-dai.

ZOO
---
A zoo SET that tracks each zoo which contains activity data.


TVC ACTIVITY DATA
-----------------
TVC stores DAI Activity in a SET:
    tvc_activity:<ZOO>
        (<TV_TOKEN>_<TVID>_<REQUEST_TIMESTAMP>, ...)

We'll consider a SESSION_TOKEN to be: <TV_TOKEN>_<TVID>

DAI Activity Loader pulls the latest requests from the set, to determine session state AND
removes processed activity.


SESSION IN PROGRESS DATA
------------------------
Sessions still being processed are stored in a Redis HASH
    latest_session_states:<ZOO>
        {
            <SESSION_TOKEN> : "[<SESSION_START_TS>, <SESSION_LAST_UPDATED_TS>]"
        }

Since Activity Loader runs periodically, it needs to "remember" where it left off
after it's previous run.
Some sessions will still be active, so we'll need to store them so the activity loader can
process them during it's next iteration.
"""
import os
import time
from itertools import zip_longest
from cnlib import log
from .base_redis import BaseRedis, Clusters, Databases

LOGGER = log.getLogger(__name__)

REDIS_SLEEP_PER_CHUNK = float(os.environ.get('REDIS_SLEEP_PER_CHUNK', 0.5))

SCAN_CHUNK_SIZE = int(os.environ.get('REDIS_SCAN_CHUNK_SIZE', 1000))
SCAN_RECORDS_LIMIT = int(os.environ.get('REDIS_SCAN_RECORDS_LIMIT', 700000))
SREM_CHUNK_SIZE = int(os.environ.get('REDIS_SREM_CHUNK_SIZE', 400000))
HMSET_CHUNK_SIZE = int(os.environ.get('REDIS_HMSET_CHUNK_SIZE', 400000))
HDEL_CHUNK_SIZE = int(os.environ.get('REDIS_HDEL_CHUNK_SIZE', 400000))

def batcher(iterable, batch_size):
    """
    Helper function to iterate a list in batches of size batch_size.
    """
    args = [iter(iterable)] * batch_size
    return zip_longest(*args)


class DAIActiveRedis(BaseRedis):
    """
    Has functionality for setting key/value pairs in DAI_ACTIVE_DB
    """
    ZOO_SET = 'zoo'

    TVC_ACTIVITY_SET_NAME = 'tvc_activity'
    LATEST_SESSION_STATES_HASH_NAME = 'latest_session_states'

    def __init__(self, write_host=Clusters.DAI_ACTIVE['write'],
                 read_host=Clusters.DAI_ACTIVE['read'],
                 db=Databases.DAI_ACTIVE,
                 decode_responses=False,
                 retry_on_timeout=False):
        super(DAIActiveRedis, self).__init__(write_host, read_host, db,
                                             retry_on_timeout=retry_on_timeout,
                                             decode_responses=decode_responses)
    def scan(self, pattern=None):
        """
        Run scan against the DB to get all fields from Cluster.
        """
        for keybatch in batcher(self._reader.scan_iter(match=pattern), SCAN_CHUNK_SIZE):
            for key in filter(lambda x: x is not None, keybatch):
                yield key

    def sscan(self, name, scan_limit=SCAN_RECORDS_LIMIT):
        """
        Run scan against the DB to get all fields from Cluster.
        """
        LOGGER.debug('%s sscan scan limit: %d', name, scan_limit)
        records = []
        for iteration, member in enumerate(self._reader.sscan_iter(name)):
            records.append(member)

            # limiting number of records sscan retrieves.
            # in case there are a large number of records in the set.
            if iteration + 1 >= scan_limit:
                break

        return records

    def zoos(self):
        """
        Pull all active zoo's from zoos Redis Activity Table.
        """
        return self._reader.smembers(self.ZOO_SET)

    def sadd_zoo(self, zoo):
        """
        Add zoo to zoo SET.
        """
        LOGGER.debug("adding zoo '%s' to %s SET", zoo, self.ZOO_SET)
        self._writer.sadd(self.ZOO_SET, zoo)

    def get_latest_tvc_activity(self, zoo):
        """
        Retrieve latest tvc activity from tvc_activity set.
        """
        # using scan so we don't block tvc from adding to the set
        return self.sscan('%s:%s' % (self.TVC_ACTIVITY_SET_NAME, zoo))

    def add_tvc_activity(self, zoo, tv_token, tvid, timestamp):
        """
        Add activity to tvc_activity set for given zoo.
        """
        tvc_activity_set_key = '%s:%s' % (self.TVC_ACTIVITY_SET_NAME, zoo)
        tvc_activity_data = '%s_%s_%d' % (tv_token, tvid, int(timestamp))
        LOGGER.debug("Adding '%s' to %s SET", tvc_activity_data, tvc_activity_set_key)
        self._writer.sadd(tvc_activity_set_key, tvc_activity_data)

    def srem_tvc_activity_members(self, zoo, members_to_remove):
        """
        Remove given members from the tvc activity set.
        """
        # delete from redis in chunks of SREM_CHUNK_SIZE
        for chunk_index in range(0, len(members_to_remove), SREM_CHUNK_SIZE):
            self._writer.srem('%s:%s' % (self.TVC_ACTIVITY_SET_NAME, zoo),
                              *members_to_remove[chunk_index:chunk_index + SREM_CHUNK_SIZE])

            time.sleep(REDIS_SLEEP_PER_CHUNK)

    def get_latest_session_states(self, zoo):
        """
        Get all session time hash data for the given zoo.
        """
        latest_session_states_hash_key = '%s:%s' % (self.LATEST_SESSION_STATES_HASH_NAME, zoo)
        latest_session_states = self._reader.hgetall(latest_session_states_hash_key)
        return {session_token: map(int, session_times.split(',')) \
                for session_token, session_times in latest_session_states.items()}

    def hmset_latest_session_states(self, zoo, sessions):
        """
        Write sessions in latest_session_states HASH for given zoo.
        Update the session times for each session.
        Expected Input Sessions format:
            {
                <SESSION_TOKEN>: (<START_TIME>, <LAST_UPDATED_TIME),
                ...
            }
        """
        latest_session_states_hash_key = '%s:%s' % (self.LATEST_SESSION_STATES_HASH_NAME, zoo)
        LOGGER.debug("Adding %d Sessions to %s SET", len(sessions), latest_session_states_hash_key)

        sessions_for_hmset = {}
        for iteration, (session_token, session_times) in enumerate(sessions.items()):
            sessions_for_hmset[session_token] = '%d,%d' % tuple(session_times)

            # write to redis in chunks of HMSET_CHUNK_SIZE
            if iteration % HMSET_CHUNK_SIZE == HMSET_CHUNK_SIZE - 1:
                self._writer.hmset(latest_session_states_hash_key, sessions_for_hmset)
                sessions_for_hmset = {}
                time.sleep(REDIS_SLEEP_PER_CHUNK)

        if sessions_for_hmset:
            self._writer.hmset(latest_session_states_hash_key, sessions_for_hmset)

    def delete_session_states(self, zoo, session_tokens):
        """
        Remove session token from session_times hash.
        """
        latest_session_states_hash_key = '%s:%s' % (self.LATEST_SESSION_STATES_HASH_NAME, zoo)
        # delete from redis in chunks of HDEL_CHUNK_SIZE
        for chunk_index in range(0, len(session_tokens), HDEL_CHUNK_SIZE):
            self._writer.hdel(latest_session_states_hash_key,
                              *session_tokens[chunk_index:chunk_index + HDEL_CHUNK_SIZE])

            time.sleep(REDIS_SLEEP_PER_CHUNK)

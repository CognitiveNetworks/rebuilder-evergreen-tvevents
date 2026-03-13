"""
 Memcache Cluster Client initialization class
"""
import os
import zlib
from pymemcache.client.hash import HashClient

TIMEOUT = 0.1
CONNECT_TIMEOUT = 0.1
USE_POOLING = True
MAX_POOL_SIZE = 5
IGNORE_EXC = True
NO_DELAY = True
RETRY_ATTEMPTS = 0

HOST_NAME_PATTERN = os.environ.get('MEMCACHE_HOST_NAME_PATTERN', 'tvclient-sessions.zgudit.%04d.use1.cache.amazonaws.com')
HOST_PORT = os.environ.get('MEMCACHE_HOST_PORT', 11211)
NUMBER_OF_HOSTS_IN_CLUSTER = os.environ.get('MEMCACHE_NUMBER_OF_HOSTS_IN_CLUSTER', 4)

EFFECTIVE_COMPRESS_LEN = 180

class MemCacheCluster(object):
    """
    Basic class to handle Memcache Cluster interactions
    """

    def __init__(self, 
                host_name_pattern = HOST_NAME_PATTERN,
                host_port = HOST_PORT,
                number_of_hosts = NUMBER_OF_HOSTS_IN_CLUSTER):

        self.hosts = []

        for i in range(int(number_of_hosts)):
            self.hosts.append( (host_name_pattern % (i + 1), int(HOST_PORT)) )

        self._client = HashClient( self.hosts, 
            timeout = TIMEOUT,
            connect_timeout = CONNECT_TIMEOUT,
            use_pooling = USE_POOLING,
            max_pool_size = MAX_POOL_SIZE,
            ignore_exc = IGNORE_EXC,
            no_delay = NO_DELAY,
            retry_attempts = RETRY_ATTEMPTS,
            serializer=self.zserializer,
            deserializer=self.zdeserializer)

    def get(self, key):
        return self._client.get(key)

    def set(self, key, val, expire):
        return self._client.set(key, val, expire)

    def zserializer(self, key, value):
        if len(value) < EFFECTIVE_COMPRESS_LEN:
            return value, 1

        if isinstance(value, str):
            value = value.encode()
        return zlib.compress(value, zlib.Z_BEST_SPEED), 2

    def zdeserializer(self, key, value, flags):
        if flags == 1:
            return value

        if flags == 2:
            return zlib.decompress(value).decode()
        raise Exception(f"Unknown flags for value: {flags}")

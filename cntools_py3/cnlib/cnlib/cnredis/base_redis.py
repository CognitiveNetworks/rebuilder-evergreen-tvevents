"""
Library for working with redis.
"""
import os
import sys
from datetime import datetime
from collections import OrderedDict

import redis

import redis.cluster as rediscluster
from redis.cluster import ClusterNode

from .. import log

__author__ = 'Yunfan Luo <yunfan.luo@cognitivenetworks.com>'

logger = log.getLogger(__name__)
QUEUE_KEY_PREFIX = "queue"


class BaseRedisException(Exception):
    pass


class Clusters(object):
    MCP = {
        'read': os.getenv('READ_MCP_REDIS', 'read.mcp-redis.cognet.tv'),
        'write': os.getenv('WRITE_MCP_REDIS', 'write.mcp-redis.cognet.tv'),
    }
    # ump-assignment redis
    CONTROL = {
        'read': os.getenv('READ_CONTROL_REDIS', 'read.control-redis.cognet.tv'),
        'write': os.getenv('WRITE_CONTROL_REDIS', 'write.control-redis.cognet.tv')
    }
    DATA = {
        'read': os.getenv('READ_DATA_REDIS', 'read.data-redis.cognet.tv'),
        'write': os.getenv('WRITE_DATA_REDIS', 'write.data-redis.cognet.tv'),
    }
    ACTIVE = {
        'read': os.getenv('READ_ACTIVE_REDIS', 'read.active-redis.cognet.tv'),
        'write': os.getenv('WRITE_ACTIVE_REDIS', 'write.active-redis.cognet.tv'),
    }
    DAI_ACTIVE = {
        'read': os.getenv('READ_DAI_ACTIVE_REDIS', 'read.active-redis-dai.cognet.tv'),
        'write': os.getenv('WRITE_DAI_ACTIVE_REDIS', 'write.active-redis-dai.cognet.tv'),
    }
    RESERVATION = {
        'read': os.getenv("READ_RESERVATION_REDIS", 'read.reservation-redis-production.cognet.tv'),
        'write': os.getenv("WRITE_RESERVATION_REDIS", 'write.reservation-redis-production.cognet.tv'),
    }

    cluster_mode = os.getenv("REDIS_CLUSTER_MODE", "cluster_disabled")

    if cluster_mode == "cluster_disabled":
        CONTROL_USERS = {
            'read': os.getenv('READ_CONTROL_REDIS', 'read.control-redis.cognet.tv'),
            'write': os.getenv('WRITE_CONTROL_REDIS', 'write.control-redis.cognet.tv')
        }
    elif cluster_mode == "cluster_dual":
        CONTROL_USERS = {
            'read': os.getenv('READ_CONTROL_REDIS', 'read.control-redis.cognet.tv'),
            'write': {
                "cluster_disabled": os.getenv('WRITE_CONTROL_REDIS', 'write.control-redis.cognet.tv'),
                "cluster_enabled": os.getenv("WRITE_CONTROL_USERS_REDIS", 'main.control-redis.cognet.tv').split(",")
            }
        }
    elif cluster_mode == "cluster_enabled":
        CONTROL_USERS = {
            'read': {
                "cluster_enabled": os.getenv("READ_CONTROL_USERS_REDIS", 'main.control-redis.cognet.tv').split(",")
            },
            'write': {
                "cluster_enabled": os.getenv("WRITE_CONTROL_USERS_REDIS", 'main.control-redis.cognet.tv').split(",")
            }
        }
    DAI_CONTROL = {
        'read': {
            "cluster_enabled": os.getenv("READ_DAI_CONTROL_REDIS", "main.dai-redis-dev.cognet.tv").split(
                ",")
        },
        'write': {
            "cluster_enabled": os.getenv("WRITE_DAI_CONTROL_REDIS", "main.dai-redis-dev.cognet.tv").split(
                ",")
        }
    }

    @staticmethod
    def rw_equal(write_host, read_host):
        """
        Read and write hosts are equal if their strings are equal or their
        dict/list substructures all contain the same strings.
        """
        if write_host == read_host:
            return True

        if type(write_host) != type(read_host):
            return False

        if type(write_host) == dict:
            if (("cluster_disabled" in write_host)
                    and ("cluster_disabled" in read_host)
                    and write_host["cluster_disabled"] == read_host["cluster_disabled"]):
                return True

            if (("cluster_enabled" in write_host)
                    and ("cluster_enabled" in read_host)
                    and set(write_host["cluster_enabled"]) == set(read_host["cluster_enabled"])):
                return True

        return False


def prepare_dict_for_new_redis(values_dict):
    """
    Redis version 3 doesn't support bool values, this function fixes it
    """
    updated_dict = {}
    for key in values_dict.keys():
        if type(values_dict[key]) is bool:
            values_dict[key] = str(values_dict[key])
        updated_dict.update({key: values_dict[key]})

    return updated_dict


class Databases(object):
    # mcp-redis
    MCP = 0

    # reservation-redis
    RESERVATION = 0

    # control-redis
    TVC = 1

    # active-redis
    ACTIVE = 2

    # dai-active-redis
    DAI_ACTIVE = 2

    # cdb-redis
    CDB = 3

    # dai-redis
    DAI = 0

    # switchcase-redis
    SWITCH_CASE = 4

    # data-redis
    DP25_EVOLUTION_STATUS = 3
    DP25_WARM_STATUS = 4
    DP25_LOCK = 5
    DP25_STATUS = 6  # HOT
    GEO_IP = 7  # maybe
    DP4 = 9  # DP4 ETL status
    DP4_WARM_WATERMARK = 10
    DP4_EVOLUTION_WATERMARK = 11
    DP4_STAGE = 12

    # not sure which cluster
    PENDING_SESSIONS = 8

    # max 16 (15 as value), but attributes with same value may pertain to
    # different clusters


class BaseRedis(object):
    """
    Basic class to handle Redis interactions
    Deals with set/get/delete of key > value pairs and value > key indexes
    """
    DATE_FIELDS = ("date_time", "start", "end")

    READ_SOCKET_CONNECT_TIMEOUT = 30.0
    READ_SOCKET_TIMEOUT = 30.0
    READ_MAX_CONNECTIONS = 250
    WRITE_SOCKET_CONNECT_TIMEOUT = 30.0
    WRITE_SOCKET_TIMEOUT = 30.0
    WRITE_MAX_CONNECTIONS = 250

    def __init__(self, write_host, read_host, db,
                 decode_responses=False,
                 retry_on_timeout=False,
                 health_check_interval=0):

        logger.info('BaseRedis init: {} ; {} ; {}'.format(write_host, read_host, db))

        logger.info('BaseRedis Read Connection Variables: '
                    'socket_connection_timeout=%f, socket_timeout=%f, max_connections=%d',
                    self.READ_SOCKET_CONNECT_TIMEOUT,
                    self.READ_SOCKET_TIMEOUT,
                    self.READ_MAX_CONNECTIONS)
        logger.info('BaseRedis Write Connection Variables: '
                    'socket_connection_timeout=%f, socket_timeout=%f, max_connections=%d',
                    self.WRITE_SOCKET_CONNECT_TIMEOUT,
                    self.WRITE_SOCKET_TIMEOUT,
                    self.WRITE_MAX_CONNECTIONS)

        self._writer = self.__make_client(
            write_host,
            db,
            decode_responses=decode_responses,
            socket_connect_timeout=self.WRITE_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=self.WRITE_SOCKET_TIMEOUT,
            max_connections=self.WRITE_MAX_CONNECTIONS,
            retry_on_timeout=retry_on_timeout,
            health_check_interval=health_check_interval
        )

        if Clusters.rw_equal(write_host, read_host):
            self._reader = self._writer
        else:
            self._reader = self.__make_client(
                read_host,
                db=db,
                decode_responses=decode_responses,
                socket_connect_timeout=self.READ_SOCKET_CONNECT_TIMEOUT,
                socket_timeout=self.READ_SOCKET_TIMEOUT,
                max_connections=self.READ_MAX_CONNECTIONS,
                retry_on_timeout=retry_on_timeout,
                health_check_interval=health_check_interval)

    def __make_client(self, hosts, db, decode_responses=False, retry_on_timeout=False,
                      health_check_interval=0, **kwargs):
        """
        Assume "cluster-disabled" if not specified in dictionary.
        """
        client = None

        if type(hosts) == str:
            # hosts would be singular
            client = redis.StrictRedis(
                hosts,
                db=db,
                decode_responses=decode_responses,
                socket_connect_timeout=kwargs["socket_connect_timeout"],
                socket_timeout=kwargs["socket_timeout"],
                max_connections=kwargs["max_connections"],
                retry_on_timeout=retry_on_timeout,
                health_check_interval=health_check_interval
            )

        elif type(hosts) == dict:
            if len(hosts.keys()) == 1:
                if "cluster_disabled" in hosts:
                    # hosts["cluster_disabled"] should be singular
                    client = redis.StrictRedis(
                        hosts["cluster_disabled"],
                        db=db,
                        decode_responses=decode_responses,
                        socket_connect_timeout=kwargs["socket_connect_timeout"],
                        socket_timeout=kwargs["socket_timeout"],
                        max_connections=kwargs["max_connections"],
                        retry_on_timeout=retry_on_timeout,
                        health_check_interval=health_check_interval
                    )
                else:
                    cluster_startup_nodes = [{"host": host, "port": 6379}
                                             for host in hosts["cluster_enabled"]]

                    client = rediscluster.RedisCluster(
                        startup_nodes=[ClusterNode(**node) for node in cluster_startup_nodes],
                        decode_responses=decode_responses,
                        retry_on_timeout=retry_on_timeout,
                        health_check_interval=health_check_interval,
                        skip_full_coverage_check=True,
                        **{k: v for k, v in list(kwargs.items()) if k != "db"})

            elif len(hosts.keys()) >= 2:
                client = RedisGroup(
                    hosts,
                    db=db,
                    decode_responses=decode_responses,
                    retry_on_timeout=retry_on_timeout,
                    health_check_interval=health_check_interval,
                    socket_connect_timeout=kwargs["socket_connect_timeout"],
                    socket_timeout=kwargs["socket_timeout"],
                    max_connections=kwargs["max_connections"])

        if not client:
            logger.error("Redis client not created: hosts={} db={} kwargs={}".format(
                str(hosts), db, str(kwargs)))

        return client

    # set / get / delete / expire
    # Almost direct translation of the redis library's functions
    def set(self, key, value_dict, prefix=None, pipeline=None):
        encoded_value_dict = self.encode_values(value_dict)
        return self.save(key, encoded_value_dict, prefix, pipeline)

    def hset(self, name, key, value):
        return self._writer.hset(name, key, value)

    def hget(self, name, key):
        return self._reader.hget(name, key)

    def hdel(self, name, key):
        return self._writer.hdel(name, key)

    def save(self, key, encoded_value_dict, prefix=None, pipeline=None):
        prefixed_key = '{}:{}'.format(prefix, key) if prefix else key
        logger.debug("Setting key={} to value={}".format(
            prefixed_key, encoded_value_dict))

        if pipeline is None:
            updated_dict = prepare_dict_for_new_redis(encoded_value_dict)
            return self._writer.hmset(prefixed_key, updated_dict)
        else:
            logger.debug("Passed a pipeline, not executing")
            return pipeline.hmset(prefixed_key, encoded_value_dict)

    def encode_values(self, value_dict):
        return {
            field: self.encode_field(field, value)
            for field, value in list(value_dict.items())
        }

    def encode_field(self, field, value):
        if isinstance(value, datetime):
            # Convert datetime obj to float = seconds since epoch
            value = (value - datetime(1970, 1, 1)).total_seconds()
            logger.debug("Encoded value={}".format(value))
        else:
            logger.debug("Unencoded value={}".format(value))

        return value

    def get(self, key, prefix=None):
        output_dict = {}
        for field, value in list(self.fetch(key, prefix).items()):
            od_key = field.decode("utf-8") if type(field) == bytes else field
            # TODO - replace field with od_key in the future, now it may brake other projects
            od_value = self.parse_field(field, value)
            if type(od_value) == bytes:
                od_value = od_value.decode("utf-8")
            output_dict[od_key] = od_value
        return output_dict

    def fetch(self, key, prefix=None):
        prefixed_key = '{}:{}'.format(prefix, key) if prefix else key
        logger.debug("Getting key {}".format(prefixed_key))
        return self._reader.hgetall(prefixed_key)

    def parse_field(self, field, value):
        parsed = value
        if field in self.DATE_FIELDS:
            # Convert the float stored in redis back into a datetime obj
            try:
                parsed = datetime.utcfromtimestamp(float(value))
            except ValueError as e:
                logger.warning(
                    'Failed to parse field: {}, {}:{}'.format(field, value, e))

        return parsed

    def delete(self, key, prefix=None, pipeline=None):
        prefixed_key = '{}:{}'.format(prefix, key) if prefix else key
        logger.debug("Deleting key {}".format(prefixed_key))
        if pipeline is None:
            return self._writer.delete(prefixed_key)
        else:
            logger.debug("Passed a pipeline, not executing")
            return pipeline.delete(prefixed_key)

    def exists(self, key, prefix=None, pipeline=None):
        prefixed_key = '{}:{}'.format(prefix, key) if prefix else key
        logger.debug("Checking existence of key {}".format(prefixed_key))
        if pipeline is None:
            return self._reader.exists(prefixed_key)
        else:
            logger.debug("Passed a pipeline, not executing")
            return pipeline.exists(prefixed_key)

    def expire(self, key, seconds, prefix=None, pipeline=None):
        prefixed_key = '{}:{}'.format(prefix, key) if prefix else key
        logger.debug("Expiring key {} in {} seconds".format(
            prefixed_key, seconds))
        if pipeline is None:
            return self._writer.expire(prefixed_key, seconds)
        else:
            logger.debug("Passed a pipeline, not executing")
            return pipeline.expire(prefixed_key, seconds)

    # values should be a list, otherwise use set_index
    def set_index_multiple(self, key, values, prefix=None):
        prefixed_key = '{}:{}'.format(prefix, key) if \
            prefix else key
        logger.debug("Adding index for {} values at {} (key)".format(
            len(values), prefixed_key))
        return self._writer.sadd(prefixed_key, *values)

    # set_index / get_index / delete_from_index
    # Matching functions for the plain set/get/delete functions
    def set_index(self, index_key, value, prefix=None, pipeline=None):
        prefixed_key = '{}:{}'.format(prefix, index_key) if \
            prefix else index_key
        logger.debug("Adding index for {} (value) at {} (key)".format(
            value, prefixed_key))
        if pipeline is None:
            return self._writer.sadd(prefixed_key, value)
        else:
            logger.debug("Passed a pipeline, not executing")
            return pipeline.sadd(prefixed_key, value)

    def get_index(self, index_key, prefix=None):
        prefixed_key = '{}:{}'.format(prefix, index_key) if \
            prefix else index_key
        logger.debug("Getting index key {}".format(prefixed_key))
        index_values = self._reader.smembers(prefixed_key)
        return index_values

    def sizeof_index(self, index_key, prefix=None):
        """
        Get the size of the index.
        If we only need the size of the index, e.g. for population counts,
        this is a faster call than getting the entire index and counting.
        Use when possible.
        """
        prefixed_key = '{}:{}'.format(prefix, index_key) if \
            prefix else index_key
        logger.debug("Getting size of index {}".format(prefixed_key))
        count = self._reader.scard(prefixed_key)
        return count

    def delete_index(self, index_key, prefix=None, pipeline=None):
        """
        The exact same function as the plain delete,
        but calling it delete_index for convenience.
        """
        prefixed_key = '{}:{}'.format(prefix, index_key) if \
            prefix else index_key
        logger.debug("Deleting index {}".format(prefixed_key))
        if pipeline is None:
            return self._writer.delete(prefixed_key)
        else:
            logger.debug("Passed a pipeline, not executing")
            return pipeline.delete(prefixed_key)

    def delete_from_index(self, value_key, index_prefix, value_prefix=None,
                          pipeline=None):
        """
        Given a key (TV token), delete its entry from its index.
        CALL THIS BEFORE DELETING THE KEY!
        """
        prefixed_key = '{}:{}'.format(value_prefix, value_key) if \
            value_prefix else value_key
        logger.debug("Deleting index entry for key {}".format(prefixed_key))

        # Get the dictionary stored in Redis for the prefixed_key
        # Should look something like:
        #   {'user:000000':{'target':'control-default.tvinteractive.tv'}}
        # Where 'user:000000' is prefixed_key, and 'target' is index_prefix
        stored_value = self.get(prefixed_key)

        try:
            # prefixed_index_key holds the key name of the index that has
            # the prefixed_key we're looking for as a set member
            index_key = stored_value[index_prefix]
            prefixed_index_key = '{}:{}'.format(index_prefix, index_key)

            # Then delete the prefixed key (user:000000) from the index
            if pipeline is None:
                return self._writer.srem(prefixed_index_key, value_key)
            else:
                logger.debug("Passed a pipeline, not executing")
                return pipeline.srem(prefixed_index_key, value_key)
        except Exception as e:
            logger.error("Failed to delete value {} from index {}: {}".format(
                value_key, index_prefix, e))
            return False

    def delete_by_index(self, index_key, index_prefix=None, value_prefix=None,
                        pipeline=None):
        """
        Delete both the index, and the key/value pairs whose keys
        were set members of in the index.
        THIS IS A BIG DEAL, IT AFFECTS A LOT OF KEYS!
        """
        prefixed_key = '{}:{}'.format(index_prefix, index_key) if \
            index_prefix else index_key
        values = self.get_index(prefixed_key)
        for value_key in values:
            prefixed_value_key = '{}:{}'.format(value_prefix, value_key) if \
                value_prefix else value_key
            self.delete(prefixed_value_key, pipeline=pipeline)
        return self.delete_index(prefixed_key, pipeline=pipeline)

    def pop(self, suffix):
        if not suffix:
            raise BaseRedisException("Queue name suffix not provided")

        queue_key = "{prefix}:{suffix}".format(prefix=QUEUE_KEY_PREFIX, suffix=suffix)
        return self._writer.rpop(queue_key)

    def pop_from(self, key):
        """
        Raw method to pop with specified key in case user needs access to
        actual key name
        """
        return self._writer.rpop(key)

    def push(self, suffix, *values):
        if not suffix:
            raise BaseRedisException("Queue name suffix not provided")

        queue_key = "{prefix}:{suffix}".format(prefix=QUEUE_KEY_PREFIX, suffix=suffix)
        return self._writer.lpush(queue_key, *values)

    def push_to(self, key, *values):
        """
        Raw method to push to specified key in case user needs access to
        actual key name
        """
        return self._writer.lpush(key, *values)


def run_on_objects(objs, instance_function_name):
    """
    Decorator for running (likely) instance methods over multiple things.
    """
    logger.debug("{} instance_function_name={}".format(
        sys._getframe().f_code.co_name, instance_function_name))

    def wrapped_f(*args, **kwargs):
        return_value = None
        for obj_name, obj in list(objs.items()):
            try:
                attr = getattr(obj, instance_function_name)
            except AttributeError:
                logger.warning("Function not found: type={} function_name={}".format(
                    type(obj), instance_function_name))
                continue

            # return the value only from the cluster-disabled object
            if obj_name == "cluster_disabled":
                return_value = getattr(obj, instance_function_name)(*args, **kwargs)
            else:
                getattr(obj, instance_function_name)(*args, **kwargs)

        return return_value

    return wrapped_f


class RedisGroupPipeline(redis.client.Pipeline):
    def __init__(self, clients, *args, **kwargs):
        self.pipelines = OrderedDict([(client_name, client.pipeline(*args, **kwargs))
                                      for client_name, client in clients.items()]
                                     )

    def get_pipeline_cluster_disabled(self):
        return self.pipelines["cluster_disabled"]

    def __getattribute__(self, name):
        if not hasattr(super(RedisGroupPipeline, self), name):
            try:
                # Even though access is via the base class, the attribute is
                # still from the derived class.
                attr = super(RedisGroupPipeline, self).__getattribute__(name)
            except AttributeError:
                pass
            else:
                # logger.debug("returning attr={}".format(name))
                return attr

        pipeline_primary = self.get_pipeline_cluster_disabled()
        attr = getattr(pipeline_primary, name)

        # this instance's self.clients. Infinite loop if not accessed through
        # the base class in this way..
        pipelines = super(RedisGroupPipeline, self).__getattribute__("pipelines")

        if callable(type(attr)):
            return run_on_objects(pipelines, name)
        else:
            # returns instance variable from the primary only
            return attr


class RedisGroup(redis.StrictRedis):

    def __init__(self, hosts, *args, **kwargs):
        cluster_enabled_nodes = [{"host": host, "port": 6379} for host in
                                 hosts["cluster_enabled"]]

        self.clients = OrderedDict([
            ("cluster_disabled", redis.StrictRedis(
                host=hosts["cluster_disabled"],
                *args, **kwargs)),
            ("cluster_enabled", rediscluster.RedisCluster(
                startup_nodes=[ClusterNode(**node) for node in cluster_enabled_nodes],
                skip_full_coverage_check=True,
                **{k: v for k, v in list(kwargs.items()) if k != "db"}))
        ])

    def get_client_cluster_disabled(self):
        return self.clients["cluster_disabled"]

    def pipeline(self, *args, **kwargs):
        return RedisGroupPipeline(self.clients, *args, **kwargs)

    def __getattribute__(self, name):
        """
        RedisGroup acts as an intermediary (like Visitor pattern?) with its own
        attributes for storing general state.

        """
        # if defined in (this) subclass
        # TODO: something less hacky
        if name == "pipeline":
            # logger.debug("defined in this class, using: {}".format(name))
            return super(RedisGroup, self).__getattribute__(name)

        # If attribute is not found in the base/super StrictRedis class
        # (placeholder shell only for method lookups), look it up in the
        # RedisGroup class.
        if not hasattr(super(RedisGroup, self), name):
            try:
                # Even though access is via the base class, the attribute is
                # still from the derived class.
                base_attr = super(RedisGroup, self).__getattribute__(name)
            except AttributeError:
                pass
            else:
                # logger.debug("returning base_attr={}".format(name))
                return base_attr

        # If the attribute is not a pipeline, look directly in the client,
        # which has StrictRedis as a base. Forward attribute access to the base
        # StrictRedis class if found. If it is a pipeline, handle creating state
        # that stores pipelines of both cluster-disabled and -enabled clients.

        # Favor the primary (cluster-disabled) client as the basis for
        # determining whether the attribute is valid.
        client_primary = self.get_client_cluster_disabled()
        attr = getattr(client_primary, name)

        # Idiomatic way of access this instance's self.clients in order to
        # avoid infinite loop using __getattribute__
        clients = super(RedisGroup, self).__getattribute__("clients")

        if callable(type(attr)):
            return run_on_objects(clients, name)
        else:
            # returns instance variable from the primary only
            return attr

"""
imports
"""
import json
import math
import time
import fakeredis
from .. import cnredis
from datetime import datetime


"""
test mocks / fakes
"""
def FakeWrapper(write_host, db=0):
    return fakeredis.FakeStrictRedis(db)
#cnredis.redis = fakeredis
cnredis.base_redis.redis.StrictRedis = FakeWrapper


class TestBaseRedis():
    cnr = cnredis.BaseRedis(write_host='fake_write_host', read_host='fake_read_host', db=0)

    def test_set(self):
        """
        Test that setting a key using a prefix translates to hmset
        """
        self.cnr.set('test_key', {'a':'foo', 'b':2, 'c':3.0}, prefix='test_prefix')
        stored_values = self.cnr._reader.hgetall('test_prefix:test_key')
        # Expect that when numbers are stored in redis, they get converted to strings
        assert stored_values == {'a':'foo', 'b':'2', 'c':'3.0'}
        self.cnr._writer.flushdb()

    def test_get(self):
        """
        Test that getting a key using a prefix translates to hgetall
        """
        self.cnr._writer.hmset('test_prefix:test_key', {'d':'bar', 'e':4, 'f':5.0})
        stored_values = self.cnr.get('test_key', prefix='test_prefix')
        # Expect that numbers stored in redis are saved as strings
        assert stored_values == {'d':'bar', 'e':'4', 'f':'5.0'}
        self.cnr._writer.flushdb()

    def test_delete(self):
        """
        Test that deleting a key using a prefix works
        """
        self.cnr._writer.hmset('test_prefix:test_key', {'g':'blah', 'h':6, 'i':7.0})
        self.cnr.delete('test_key', prefix='test_prefix')
        stored_values = self.cnr._reader.hgetall('test_prefix:test_key')
        assert stored_values == {}
        self.cnr._writer.flushdb()

    def test_expire(self):
        """
        Test that expiring a key using a prefix works [using ttl()]
        """
        self.cnr._writer.hmset('test_prefix:test_key', {'j':'moo', 'k':8, 'l':9.0})
        self.cnr.expire('test_key', 600, prefix='test_prefix')
        stored_ttl = self.cnr._reader.ttl('test_prefix:test_key')
        assert stored_ttl == 600
        self.cnr._writer.flushdb()

    def test_set_index(self):
        """
        Test that adding a member to an index results in a sadd()
        """
        self.cnr.set_index('test_key', 'test_member', prefix='test_prefix')
        stored_index = self.cnr._reader.smembers('test_prefix:test_key')
        assert stored_index == set(['test_member'])
        self.cnr._writer.flushdb()

    def test_get_index(self):
        """
        Test that getting an index returns an smembers()
        """
        self.cnr._writer.sadd('test_prefix:test_key', 'test_token')
        stored_index = self.cnr.get_index('test_key', prefix='test_prefix')
        assert stored_index == set(['test_token'])
        self.cnr._writer.flushdb()

    def test_sizeof_index(self):
        """
        Test that getting the size of an index returns scard()
        """
        self.cnr._writer.sadd('test_prefix:test_key', 'test_token')
        index_size = self.cnr.sizeof_index('test_key', prefix='test_prefix')
        assert index_size == 1
        self.cnr._writer.flushdb()

    def test_delete_index(self):
        """
        Test that deleting an index deletes they key
        """
        self.cnr._writer.sadd('test_prefix:test_key', 'test_token')
        stored_index = self.cnr._reader.smembers('test_prefix:test_key')
        assert stored_index == set(['test_token'])
        #self.cnr._writer.delete('index_prefix:test_delete_index')
        self.cnr.delete_index('test_key', prefix='test_prefix')
        stored_index = self.cnr._reader.smembers('test_prefix:test_key')
        assert stored_index == set()
        self.cnr._writer.flushdb()

    def test_delete_from_index(self):
        """
        Test that deleting a key from its index works
        Pass an 'index_prefix' which is used as the prefix of an index
        key to look for, as well as the hash key in a hash map in redis
        """
        # Bunch of setup
        self.cnr._writer.hmset('test_token1', {'test_prefix': 'test_key'})
        self.cnr._writer.hmset('test_token2', {'test_prefix': 'test_key'})
        self.cnr._writer.sadd('test_prefix:test_key', 'test_token1')
        self.cnr._writer.sadd('test_prefix:test_key', 'test_token2')
        token1 = self.cnr._reader.hget('test_token1', 'test_prefix')
        token2 = self.cnr._reader.hget('test_token2', 'test_prefix')
        assert token1 == 'test_key'
        assert token2 == 'test_key'
        stored_index = self.cnr._reader.smembers('test_prefix:test_key')
        assert stored_index == set(['test_token1', 'test_token2'])
        # Actual test
        self.cnr.delete_from_index('test_token1', 'test_prefix')
        stored_index = self.cnr._reader.smembers('test_prefix:test_key')
        assert stored_index == set(['test_token2'])
        self.cnr._writer.flushdb()
        

    def test_delete_by_index(self):
        """
        Test deleting an index and the values that were mapping
        to this index
        """
        # Bunch of setup
        self.cnr._writer.hmset('test_token1', {'test_prefix': 'test_key'})
        self.cnr._writer.hmset('test_token2', {'test_prefix': 'test_key'})
        self.cnr._writer.sadd('test_prefix:test_key', 'test_token1')
        self.cnr._writer.sadd('test_prefix:test_key', 'test_token2')
        token1 = self.cnr._reader.hget('test_token1', 'test_prefix')
        token2 = self.cnr._reader.hget('test_token2', 'test_prefix')
        assert token1 == 'test_key'
        assert token2 == 'test_key'
        stored_index = self.cnr._reader.smembers('test_prefix:test_key')
        assert stored_index == set(['test_token1', 'test_token2'])
        # Actual test
        self.cnr.delete_by_index('test_key', index_prefix='test_prefix')
        token1 = self.cnr._reader.hget('test_token1', 'test_prefix')
        token2 = self.cnr._reader.hget('test_token2', 'test_prefix')
        assert token1 == None
        assert token2 == None
        stored_index = self.cnr._reader.smembers('test_prefix:test_key')
        assert stored_index == set([])
        self.cnr._writer.flushdb()
        

# Test ActiveRedis
class TestActiveRedis():

    cnr = cnredis.ActiveRedis()

    def test_active_user_count_wrapper(self):
        """
        Test the wrapper function Alex uses
        """
        self.cnr._writer.sadd('active_allowed:test_zoo', 'test_token')
        assert cnredis.active_user_count('test_zoo') == 1
        self.cnr._writer.flushdb()

    def test_set(self):
        """
        Test that calling our own set() function adds a token
        to the 'active' and 'active_allowed' keys
        as well ass setting expirations on both
        """
        now = time.time()
        modded_now = int(now - math.floor(now % self.cnr.active_mod_seconds))
        self.cnr.set('test_zoo', 'test_token', now=modded_now)
        active_key = 'active:test_zoo_{}'.format(modded_now)
        active_allowed_key = 'active_allowed:test_zoo_{}'.format(modded_now)
        assert self.cnr._reader.smembers(active_key) == set(['test_token'])
        assert self.cnr._reader.ttl(active_key) == self.cnr.active_window_seconds
        assert self.cnr._reader.smembers(active_allowed_key) == set(['test_token'])
        assert self.cnr._reader.ttl(active_allowed_key) == self.cnr.active_window_seconds
        self.cnr._writer.flushdb()

    def test_active_users(self):
        """
        Test that the set_active_users function unions the last 5
        existing 'bucket' keys, and no more
        """
        now = time.time()
        modded_now = int(now - math.floor(now % self.cnr.active_mod_seconds))
        self.cnr._writer.sadd('active:test_zoo_{}'.format(modded_now), 'test_token_1')
        self.cnr._writer.sadd('active:test_zoo_{}'.format(modded_now-300), 'test_token_2')
        self.cnr._writer.sadd('active:test_zoo_{}'.format(modded_now-600), 'test_token_3')
        self.cnr._writer.sadd('active:test_zoo_{}'.format(modded_now-900), 'test_token_4')
        self.cnr._writer.sadd('active:test_zoo_{}'.format(modded_now-1200), 'test_token_5')
        # This one should NOT show up in the union
        self.cnr._writer.sadd('active:test_zoo_{}'.format(modded_now-1500), 'test_token_6')
        # Actual test
        self.cnr.set_active_users('test_zoo', now=modded_now, return_members=True)
        active_unioned_key = 'active:test_zoo'
        assert self.cnr._reader.scard(active_unioned_key) == 5
        assert self.cnr._reader.smembers(active_unioned_key) == set(['test_token_1',
            'test_token_2', 'test_token_3', 'test_token_4', 'test_token_5'])
        self.cnr._writer.flushdb()

    def test_active_user_count(self):
        """
        Test that getting counts on the 'active' key works,
        calling the 'set_active_users' function under the hood
        """
        now = time.time()
        modded_now = int(now - math.floor(now % self.cnr.active_mod_seconds))
        active_key = 'active:test_zoo_{}'.format(modded_now)
        self.cnr._writer.sadd(active_key, 'test_token_1')
        self.cnr._writer.sadd(active_key, 'test_token_2')
        active_tokens = self.cnr.get_active_user_count('test_zoo')
        assert active_tokens == 2
        self.cnr._writer.flushdb()

    def test_active_user_tokens(self):
        """
        Test that getting tokens of the 'active' key works,
        calling the 'set_active_users' function under the hood
        """
        now = time.time()
        modded_now = int(now - math.floor(now % self.cnr.active_mod_seconds))
        active_key = 'active:test_zoo_{}'.format(modded_now)
        self.cnr._writer.sadd(active_key, 'test_token_1')
        self.cnr._writer.sadd(active_key, 'test_token_2')
        active_tokens = self.cnr.get_active_user_tokens('test_zoo')
        assert active_tokens == ['test_token_2', 'test_token_1']
        self.cnr._writer.flushdb()

    def test_active_allowed_user_count(self):
        """
        Test that getting counts on the 'active_allowed' key works,
        calling the 'set_active_users' function under the hood
        """
        now = time.time()
        modded_now = int(now - math.floor(now % self.cnr.active_mod_seconds))
        active_allowed_key = 'active_allowed:test_zoo_{}'.format(modded_now)
        self.cnr._writer.sadd(active_allowed_key, 'test_token_1')
        self.cnr._writer.sadd(active_allowed_key, 'test_token_2')
        active_allowed_tokens = self.cnr.get_active_allowed_user_count('test_zoo')
        assert active_allowed_tokens == 2
        self.cnr._writer.flushdb()

    def test_active_allowed_user_tokens(self):
        """
        Test that getting tokens of the 'active_allowed' key works,
        calling the 'set_active_users' function under the hood
        """
        now = time.time()
        modded_now = int(now - math.floor(now % self.cnr.active_mod_seconds))
        active_allowed_key = 'active_allowed:test_zoo_{}'.format(modded_now)
        self.cnr._writer.sadd(active_allowed_key, 'test_token_1')
        self.cnr._writer.sadd(active_allowed_key, 'test_token_2')
        active_allowed_tokens = self.cnr.get_active_allowed_user_tokens('test_zoo')
        assert active_allowed_tokens == ['test_token_2', 'test_token_1']
        self.cnr._writer.flushdb()


# Test TVCRedis
class TestTVCRedis():

    cnr = cnredis.TVCRedis()

    def test_set(self):
        """
        Test that the set() function both sets the hash keys we want
        as well as sets the expiration
        """
        self.cnr.set('test_token', 'test_host', 5558, 8080, 'us-east-1', 'i-fake')
        stored_token = self.cnr._reader.hgetall('user:test_token')
        assert stored_token.get('host') == 'test_host'
        assert stored_token.get('udp_port') == '5558'
        assert stored_token.get('http_port') == '8080'
        assert stored_token.get('az') == 'us-east-1'
        assert stored_token.get('ump_id') == 'i-fake'
        assert self.cnr._reader.ttl('user:test_token') == self.cnr.ump_assignment_expiry
        self.cnr._writer.flushdb()

    def test_update(self):
        """
        Test that the update function works
        """
        self.cnr._writer.hmset('user:test_token', {'host':'test_host', 'udp_port':5558,
            'http_port':8080, 'az':'us-east-1', 'ump_id':'i-fake'})
        stored_token = self.cnr._reader.hgetall('user:test_token')
        assert stored_token.get('host') == 'test_host'
        assert stored_token.get('udp_port') == '5558'
        assert stored_token.get('http_port') == '8080'
        assert stored_token.get('az') == 'us-east-1'
        assert stored_token.get('ump_id') == 'i-fake'
        # Actual test
        self.cnr.update('test_token', 'host', 'test_host_1')
        assert self.cnr._reader.hget('user:test_token', 'host') == 'test_host_1'
        self.cnr._writer.flushdb()


    def test_get(self):
        """
        Test that the get function successfully casts the date_time field
        from the number I get back to a datetime object
        """
        self.cnr._writer.hmset('user:test_token', {'host':'test_host', 'udp_port':5558,
            'http_port':8080, 'az':'us-east-1', 'ump_id':'i-fake', 'date_time':1429568839})
        stored_token = self.cnr._reader.hgetall('user:test_token')
        assert stored_token.get('host') == 'test_host'
        assert stored_token.get('udp_port') == '5558'
        assert stored_token.get('http_port') == '8080'
        assert stored_token.get('az') == 'us-east-1'
        assert stored_token.get('ump_id') == 'i-fake'
        # Actual test
        stored_token_from_get = self.cnr.get('test_token')
        assert stored_token_from_get.get('host') == 'test_host'
        assert stored_token_from_get.get('udp_port') == '5558'
        assert stored_token_from_get.get('http_port') == '8080'
        assert stored_token_from_get.get('az') == 'us-east-1'
        assert stored_token_from_get.get('ump_id') == 'i-fake'
        assert isinstance(stored_token_from_get.get('date_time'), datetime)
        # Make sure there IS a timeout
        # Either correctly or not, the get function sets an expiry of its own
        assert self.cnr._reader.ttl('user:test_token') > -1
        self.cnr._writer.flushdb()

    def test_set_host_count(self):
        """
        Test that set_host_count sets both a count and a base_count
        as well as setting an expiry
        """
        self.cnr.set_host_count('test_host', 10, 5)
        stored_token = self.cnr._reader.hgetall('host:test_host')
        # They are stored as strings in redis
        # I cast them to ints in my own get function, but directly
        # accessing them returns strings as expected
        assert stored_token.get('count') == '10'
        assert stored_token.get('base_count') == '5'
        # Make sure there IS a timeout
        assert self.cnr._reader.ttl('host:test_host') > -1
        self.cnr._writer.flushdb()

    def test_get_host_count(self):
        """
        Test that getting the host count works
        """
        self.cnr._writer.hmset('host:test_host', {'count':10, 'base_count':5})
        count, base_count = self.cnr.get_host_count('test_host')
        assert count == 10
        assert base_count == 5
        self.cnr._writer.flushdb()


# Test MCPRedis
class TestMCPRedis():
    
    cnr = cnredis.MCPRedis()
    cnr._writer = cnr._reader

    def test_set(self):
        self.cnr.set('test_token', 'test_zoo')
        assert self.cnr._reader.hget('user:test_token', 'target') == 'test_zoo'
        self.cnr._writer.flushdb()

    def test_get(self):
        self.cnr._writer.hmset('user:test_token', {'target':'test_zoo'})
        assert self.cnr.get('test_token') == {'target': 'test_zoo'}
        self.cnr._writer.flushdb()

    def test_delete(self):
        self.cnr._writer.hmset('user:test_token', {'target':'test_zoo'})
        self.cnr.delete('test_token')
        assert self.cnr._reader.exists('user:test_token') == False
        self.cnr._writer.flushdb()

    def test_expire(self):
        self.cnr._writer.hmset('user:test_token', {'target':'test_zoo'})
        self.cnr.expire('test_token', 1200)
        assert self.cnr._reader.ttl('user:test_token') > -1
        self.cnr._writer.flushdb()

    def test_set_index(self):
        self.cnr.set_index('test_host', 'test_token')
        assert self.cnr._reader.smembers('target:test_host') == set(['test_token'])
        self.cnr._writer.flushdb()

    def test_get_index(self):
        self.cnr._writer.sadd('target:test_host', 'test_token')
        assert self.cnr.get_index('test_host') == set(['test_token'])
        self.cnr._writer.flushdb()

    def test_sizeof_index(self):
        self.cnr._writer.sadd('target:test_host', 'test_token')
        index_size = self.cnr.sizeof_index('test_host')
        assert index_size == 1
        self.cnr._writer.flushdb()

    def test_delete_index(self):
        self.cnr._writer.sadd('target:test_host', 'test_token')
        stored_index = self.cnr._reader.smembers('target:test_host')
        assert stored_index == set(['test_token'])
        self.cnr.delete_index('test_host')
        stored_index = self.cnr._reader.smembers('target:test_host')
        assert stored_index == set()
        self.cnr._writer.flushdb()

    def test_delete_from_index(self):
        self.cnr._writer.hmset('user:test_token1', {'target': 'test_host'})
        self.cnr._writer.hmset('user:test_token2', {'target': 'test_host'})
        self.cnr._writer.sadd('target:test_host', 'test_token1')
        self.cnr._writer.sadd('target:test_host', 'test_token2')
        token1 = self.cnr._reader.hget('user:test_token1', 'target')
        token2 = self.cnr._reader.hget('user:test_token2', 'target')
        assert token1 == 'test_host'
        assert token2 == 'test_host'
        stored_index = self.cnr._reader.smembers('target:test_host')
        assert stored_index == set(['test_token1', 'test_token2'])
        # Actual test
        self.cnr.delete_from_index('test_token1')
        stored_index = self.cnr._reader.smembers('target:test_host')
        assert stored_index == set(['test_token2'])
        self.cnr._writer.flushdb()

    def test_delete_by_index(self):
        # Bunch of setup
        self.cnr._writer.hmset('user:test_token1', {'target': 'test_host'})
        self.cnr._writer.hmset('user:test_token2', {'target': 'test_host'})
        self.cnr._writer.sadd('target:test_host', 'test_token1')
        self.cnr._writer.sadd('target:test_host', 'test_token2')
        token1 = self.cnr._reader.hget('user:test_token1', 'target')
        token2 = self.cnr._reader.hget('user:test_token2', 'target')
        assert token1 == 'test_host'
        assert token2 == 'test_host'
        stored_index = self.cnr._reader.smembers('target:test_host')
        assert stored_index == set(['test_token1', 'test_token2'])
        # Actual test
        self.cnr.delete_by_index('test_host')
        token1 = self.cnr._reader.hget('test_token1', 'target')
        token2 = self.cnr._reader.hget('test_token2', 'target')
        assert token1 == None
        assert token2 == None
        stored_index = self.cnr._reader.smembers('target:test_host')
        assert stored_index == set([])
        self.cnr._writer.flushdb()

    def test_get_status(self):
        """
        Test get_status() function call, which only looks at indices
        Make a temporary key that holds a set of which zoos exist
        And return the counts of the corresponding indices
        """
        self.cnr._writer.sadd('target:test_host1', 'test_token1')
        self.cnr._writer.sadd('target:test_host2', 'test_token2')
        self.cnr._writer.sadd('target:test_host3', 'test_token3')
        self.cnr._writer.sadd('target:test_host3', 'test_token4')
        status = self.cnr.get_status(verbose=True)
        assert status == {'test_host1':{'count':1, 'users':set(['test_token1'])},
                            'test_host2':{'count':1, 'users':set(['test_token2'])},
                            'test_host3':{'count':2, 'users':set(['test_token3',
                                                                'test_token4'])}}
        assert self.cnr._reader.smembers('all_targets') == set(['test_host1',
            'test_host2', 'test_host3'])
        self.cnr._writer.flushdb()

    def test_regenerate_indices(self):
        # It looks like fakeredis's type() function is broken
        # For this function only, redefine the type() function to 
        # always return 'hash'
        temp = self.cnr._reader.type
        self.cnr._reader.type = lambda key: b'hash'

        self.cnr._writer.hmset('user:test_token1', {'target': 'test_host1'})
        self.cnr._writer.hmset('user:test_token2', {'target': 'test_host2'})
        self.cnr._writer.hmset('user:test_token3', {'target': 'test_host3'})
        self.cnr._writer.hmset('user:test_token4', {'target': 'test_host3'})
        status = self.cnr.regenerate_indices()
        assert self.cnr._reader.smembers('target:test_host1') == set(['test_token1'])
        assert self.cnr._reader.smembers('target:test_host2') == set(['test_token2'])
        assert self.cnr._reader.smembers('target:test_host3') == set(['test_token3',
                                                                    'test_token4'])
        assert status == {'test_host1':{'count':1, 'users':['test_token1']},
                            'test_host2':{'count':1, 'users':['test_token2']},
                            'test_host3':{'count':2, 'users':['test_token4',
                                                                'test_token3']}}
        self.cnr._writer.flushdb()
        # And fix our own hack
        self.cnr._reader.type = temp


# Test CDBRedis
class TestCDBRedis():

    cnr = cnredis.CDBRedis()

    def test_generate_next_uid(self):
        self.cnr._writer.set('meta:latest_uid', 1)
        # The call returns a number
        assert self.cnr.generate_next_uid() == 2
        # But stored as a string
        assert self.cnr._reader.get('meta:latest_uid') == '2'
        self.cnr._writer.flushdb()

    def test_set_last_uid(self):
        self.cnr._writer.set('meta:latest_uid', 1)
        # It looks like when I wrote this function I intended for it to return
        # the current max uid regardless of whether the uid passed is bigger or not
        # In fact, in the case that it was the biggest, a 'True' was returned
        # Need to fix this
        # Test will fail when run on current production library 4/21/2015
        assert self.cnr.set_last_uid(80085) == 80085
        assert self.cnr._reader.get('meta:latest_uid') == '80085'
        self.cnr.set_last_uid(1337)
        assert self.cnr._reader.get('meta:latest_uid') == '80085'
        self.cnr._writer.flushdb()

    def test_set(self):
        self.cnr.set('test_token', 
            {
                "mvpd": None,
                "chipset_subversion": "2013",
                "events_mode": 15,
                "active": 1,
                "channel_change_detection_mode": 38,
                "country_code": "US",
                "detection_on": 1,
                "readonly": "0",
                "city": "San%20Francisco",
                "az": None,
                "debug_flag": 0,
                "sendSnappyUdp": "0",
                "iso_state": "CA",
                "cable_detection_mode": 0,
                "zipcode": "94103",
                "note": None,
                "tv_model_group": None,
                "tos_version": 5,
                "latitude": 37.7758,
                "detect_code": 0,
                "tv_id": "1012966_94102_315304463",
                "tv_firmware_version": "",
                "udp_port": None,
                "ip_address_hash": "98ac0cb5077945416e81a8b926b17296",
                "http_port": None,
                "debug_alert_messages": 0,
                "oem": "LG",
                "ip_id": 0,
                "client_version_string": "",
                "u_id": 1012966,
                "ip_address": "66.181.142.10",
                "points_allowed": 1,
                "frame_debug_dump": 0,
                "dma": "San Francisco-Oak-San Jose",
                "tv_model_name": "",
                "ump_id": None,
                "h": None,
                "region": "California",
                "isp": "Raw%20Bandwidth%20Communications",
                "longitude": -122.4128,
                "external_ip": None,
                "token": "92897baa90070154ba63dd8b3272d3c9e5927850bb965f219b748c93288a78c14f384ebfc3c2f56fd9cac5629956124d9ce37c049426af42eab555026becc884",
                "tv_country": "",
                "dirty": 0,
                "chipset": "MTK_LG",
                "client_version": 63,
                "tv_lang": ""
            })
        # Asserting one, and assuming the rest
        assert self.cnr._reader.hget('user:test_token', 'tv_id') == '1012966_94102_315304463'
        self.cnr._writer.flushdb()

    def test_get(self):
        self.cnr.set('test_token', 
            {
                "mvpd": None,
                "chipset_subversion": "2013",
                "events_mode": 15,
                "active": 1,
                "channel_change_detection_mode": 38,
                "country_code": "US",
                "detection_on": 1,
                "readonly": "0",
                "city": "San%20Francisco",
                "az": None,
                "debug_flag": 0,
                "sendSnappyUdp": "0",
                "iso_state": "CA",
                "cable_detection_mode": 0,
                "zipcode": "94103",
                "note": None,
                "tv_model_group": None,
                "tos_version": 5,
                "latitude": 37.7758,
                "detect_code": 0,
                "tv_id": "1012966_94102_315304463",
                "tv_firmware_version": "",
                "udp_port": None,
                "ip_address_hash": "98ac0cb5077945416e81a8b926b17296",
                "http_port": None,
                "debug_alert_messages": 0,
                "oem": "LG",
                "ip_id": 0,
                "client_version_string": "",
                "u_id": 1012966,
                "ip_address": "66.181.142.10",
                "points_allowed": 1,
                "frame_debug_dump": 0,
                "dma": "San Francisco-Oak-San Jose",
                "tv_model_name": "",
                "ump_id": None,
                "h": None,
                "region": "California",
                "isp": "Raw%20Bandwidth%20Communications",
                "longitude": -122.4128,
                "external_ip": None,
                "token": "92897baa90070154ba63dd8b3272d3c9e5927850bb965f219b748c93288a78c14f384ebfc3c2f56fd9cac5629956124d9ce37c049426af42eab555026becc884",
                "tv_country": "",
                "dirty": 0,
                "chipset": "MTK_LG",
                "client_version": 63,
                "tv_lang": ""
            })
        stored_token = self.cnr.get('test_token')
        assert stored_token.get('tv_id') == '1012966_94102_315304463'
        # Some fields need to be cast to ints
        assert isinstance(stored_token.get('cable_detection_mode'), int)
        # Some fields need to be cast to floats
        assert isinstance(stored_token.get('latitude'), float)
        # 'null' needs to be cast to 'None'
        assert stored_token.get('ump_id') is None
        self.cnr._writer.flushdb()


# Test SwitchCaseRedis
class TestSwitchCaseRedis():
    cnr = cnredis.SwitchCaseRedis()

    def test_set(self):
        # I'm only using this to pass stringified dicts
        # json.dumps will use double quotes
        self.cnr.set('test_key', '{"key1":"value1", "key2":"value2"}')
        stored_key = self.cnr._reader.get('test_key')
        assert json.loads(stored_key) == {'key2':'value2', 'key1':'value1'}
        self.cnr._writer.flushdb()

    def test_get(self):
        self.cnr._writer.set('test_key', '{"key1":"value1", "key2":"value2"}')
        assert self.cnr.get('test_key') == '{"key1":"value1", "key2":"value2"}'
        self.cnr._writer.flushdb()

    def test_set_generic_dict(self):
        """
        Test that dictionaries get turned into strings on the way up
        """
        self.cnr.set_generic_dict('test_key', {'key1':'value1', 'key2':'value2'})
        assert self.cnr._reader.get('switchcase:test_key') == '{"key2": "value2", "key1": "value1"}'
        self.cnr._writer.flushdb()

    def test_get_generic_dict(self):
        """
        Test that strings get turned into dictionaries on the way down
        """
        self.cnr._writer.set('switchcase:test_key', '{"key1":"value1", "key2":"value2"}')
        assert self.cnr.get_generic_dict('test_key') == {'key1':'value1', 'key2':'value2'}
        self.cnr._writer.flushdb()

    def test_get_init_tos(self):

        # Dummy class to surrogate actual User class
        class DummyUser(object):
            def __init__(self, chipset, tv_country):
                self.oem = 'VIZIO'
                self.chipset = chipset
                self.tv_country = tv_country

        init_tos_dict = {
            "oem:VIZIO": [
                {
                    "chipset:SIGMA_SX6": {
                        "action": None
                    }
                },
                {
                    "tv_country:!USA": {
                        "detectionOn": 0
                    }
                }
            ]
        }
        self.cnr._writer.set('switchcase:init_tos', json.dumps(init_tos_dict))
        # SIGMA_SX6 should always get action = None
        test_user = DummyUser('SIGMA_SX6', 'USA')
        assert self.cnr.get_init_tos(test_user).get('action') is None
        # In this test case, USA should not get a detectionOn setting (None)
        test_user = DummyUser('FAKE1', 'USA')
        assert self.cnr.get_init_tos(test_user).get('detectionOn') != 0
        # Non-USA should actively be set to 0
        test_user = DummyUser('FAKE1', 'CAN')
        assert self.cnr.get_init_tos(test_user).get('detectionOn') == 0

    def test_get_init_events_modes(self):

        # Dummy class to surrogate actual User class
        class DummyUser(object):
            def __init__(self, chipset, tv_country):
                self.oem = 'VIZIO'
                self.chipset = chipset
                self.tv_country = tv_country

        init_events_dict = {
            "events_mode": 0,
            "oem:VIZIO": {
                "chipset:MTK9X": {
                    "events_mode": 12
                },
                "chipset:MTK95": {
                    "events_mode": 12
                },
                "chipset:MTK96": {
                    "events_mode": 12
                },
                "chipset:MSERIES": {
                    "events_mode": 40
                },
                "chipset:SIGMA_SX6": {
                    "events_mode": 42
                },
                "chipset:MG121_MG122": {
                    "events_mode": 12
                }
            }
        }
        self.cnr._writer.set('switchcase:init_tos', json.dumps(init_events_dict))
        test_user = DummyUser('MTK9X', 'USA')
        assert self.cnr.get_init_tos(test_user).get('events_mode') == 12
        test_user = DummyUser('MTK95', 'USA')
        assert self.cnr.get_init_tos(test_user).get('events_mode') == 12
        test_user = DummyUser('MTK96', 'USA')
        assert self.cnr.get_init_tos(test_user).get('events_mode') == 12
        test_user = DummyUser('MSERIES', 'USA')
        assert self.cnr.get_init_tos(test_user).get('events_mode') == 40
        test_user = DummyUser('SIGMA_SX6', 'USA')
        assert self.cnr.get_init_tos(test_user).get('events_mode') == 42
        test_user = DummyUser('MG121_MG122', 'USA')
        assert self.cnr.get_init_tos(test_user).get('events_mode') == 12

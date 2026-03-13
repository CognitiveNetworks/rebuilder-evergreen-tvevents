import json
import os

import six
from pkg_resources import resource_filename, resource_string

from .. import log, s3

__author__ = 'Yunfan Luo <yunfan.luo@cognitivenetworks.com>'

logger = log.getLogger(__name__)

SWITCHCASE_DICTIONARY = dict()


def load_switchcase_data_from_s3():
    """
    SwitchCase data was extracted from Redis and loaded to S3
    in separate JSON files
    This function downloads those files and loads them in memory
    """
    s3_handler = s3.SingleBucketS3Handler(os.getenv('SWITCHCASE_BUCKET', 'cn-deploy'))
    switchcase_location = os.getenv('SWITCHCASE_LOCATION', 'PROD/Control/TVC/client/switchcase/')

    descriptor = s3_handler.read_to_string(switchcase_location + 'switchcase.ini')
    if six.PY3 and isinstance(descriptor, bytes):
        descriptor = descriptor.decode('utf8')

    logger.info("populating SWITCHCASE_DICTIONARY from location={}".format(switchcase_location))

    if descriptor:
        for key in descriptor.split('\n'):
            if key:
                if key.endswith('.json'):
                    dkey = key[:-5]
                else:
                    dkey = key

                data = s3_handler.read_to_string(switchcase_location + key)
                if six.PY3 and isinstance(descriptor, bytes):
                    data = data.decode('utf8')

                SWITCHCASE_DICTIONARY[dkey] = data

                if SWITCHCASE_DICTIONARY[dkey]:
                    logger.info("key={} OK".format(dkey))
                else:
                    raise Exception("key={} Empty".format(dkey))

    else:
        raise Exception("Empty SWITCHCASE descriptor in location={}".format(switchcase_location))

    if bool(SWITCHCASE_DICTIONARY):
        logger.info("SWITCHCASE_DICTIONARY populated")
    else:
        raise Exception("Empty SWITCHCASE dictionary with location={}".format(switchcase_location))


def load_switchcase_data_with_default():
    ini_template = resource_filename('cnlib.switchcase', 'switchcase.ini')

    with open(ini_template, 'r') as f:
        content = f.readlines()

    for line in content:
        key = line.rstrip()

        if key:
            if key.endswith('.json'):
                dkey = key[:-5]
            else:
                dkey = key

            SWITCHCASE_DICTIONARY[dkey] = resource_string('cnlib.switchcase', key)

            if SWITCHCASE_DICTIONARY[dkey]:
                logger.info("key={} OK".format(dkey))
            else:
                raise Exception("key={} Empty".format(dkey))

    if bool(SWITCHCASE_DICTIONARY):
        logger.info("SWITCHCASE_DICTIONARY populated")
    else:
        raise Exception("Empty SWITCHCASE dictionary with resource location=switchcase")


def load_switchcase_data():
    try:
        load_switchcase_data_from_s3()
    except Exception as e:
        logger.warning('Failed to load switchcase from s3: {}'.format(e))
        logger.warning("populating SWITCHCASE_DICTIONARY with default config")

        load_switchcase_data_with_default()


load_switchcase_data()


# Depth is how far down to convert strings to ints
# ...we have chipset_subversion values of '2012' and '2013'
# and they need to stay strings T.T
# Defaulting to only converting first level
def convert_int_keys_walk(node, depth=1):
    new_dict = {}

    for key, item in list(node.items()):

        # If the key is a digit, make it an int
        # Unless we're past the max depth we're converting
        # strings to ints
        if depth > 0 and isinstance(key, str) and key.isdigit():
            new_key = int(key)
        else:
            new_key = key

        # HUZZAH RECURSION
        # *jazz hands*
        if isinstance(item, dict):
            new_item = convert_int_keys_walk(item, depth - 1)
        else:
            new_item = item

        new_dict[new_key] = new_item

    return new_dict


def walk_node(node, user):
    ret = {}
    if isinstance(node, list):
        # Find the first and break
        for item in node:
            temp = walk_node(item, user)
            if temp:
                ret.update(temp)
                break

    elif isinstance(node, dict):
        # Look for a key that matches
        # Set any leaves
        # Then recurse through
        for key, item in list(node.items()):
            if isinstance(item, (dict, list)):
                key_attr = key.decode().split(':')[0]
                raw_key_value = key.decode().split(':')[1]

                # If in the definition dict, the value starts with the '!'
                # character, check that the TV's passed value DOESN'T match
                # what's after the !
                if isinstance(raw_key_value, str) and raw_key_value.startswith('!'):
                    match = False
                    key_value = raw_key_value.lstrip('!')
                else:
                    match = True
                    key_value = raw_key_value

                # Chipset subversion is sometimes a year (2012, 2013)
                # but it should not be cast to an int, or it won't match
                if key_attr == "chipset_subversion":
                    pass
                elif key_value.isdigit():
                    key_value = int(raw_key_value)
                else:
                    try:
                        key_value = float(raw_key_value)
                    except ValueError as e:
                        logger.debug("Well, value wasn't a float: {}, {}".format(key_value, e))

                if match and key_value == getattr(user, key_attr):
                    ret.update(walk_node(item, user))
                elif not match and key_value != getattr(user, key_attr):
                    ret.update(walk_node(item, user))
            else:
                ret[key] = item

    return ret


def ascii_encode_dict(data):
    ascii_encode = lambda x: x.encode('ascii') if isinstance(x, str) else x
    return dict(map(ascii_encode, pair) for pair in list(data.items()))


class SwitchCaseRedis():
    """
    The class maintains its old Redis based structure
    so it doesn't break the clients
    It uses local SWITCHCASE_DICTIONARY to store data
    and doesn't require Redis anymore
    """

    def __init__(self, write_host=None,
                 read_host=None, db=None):
        pass

    def set(self, key, value_dict, prefix=None):
        # prefixed_key = '{}:{}'.format(prefix, key) if prefix else key
        # logger.debug("Setting key {} to {}".format(prefixed_key, value_dict))
        # return self._writer.set(prefixed_key, value_dict)
        raise Exception("unsupported operation <set>")

    def get(self, key, prefix=None):
        prefixed_key = '{}:{}'.format(prefix, key) if prefix else key
        logger.debug("Getting key {}".format(prefixed_key))
        return SWITCHCASE_DICTIONARY[prefixed_key]

    # I want to store as JSON in case I want to interact with it
    # using other stuff later. JSON seems more friendly to store
    # than just throwing a python dict at it
    def set_generic_dict(self, key, value_dict):
        # prefix = 'switchcase'
        # override = os.environ.get('SWITCHCASE_OVERRIDE', '')
        # logger.debug("override: {}".format(override))
        # if override:
        #    prefix = prefix + ':' + override
        #    logger.debug("setting to override prefix: {}".format(prefix))
        # json_dict = json.dumps(value_dict)
        # self.set(key, json_dict, prefix)
        raise Exception("unsupported operation <set_generic_dict>")

    # But on the way out, I want to convert the JSON to
    # Using ascii_encode_dict to convert JSON unicode strings
    # to ASCII strings
    def get_generic_dict(self, key):
        prefix = 'switchcase'
        override = os.environ.get('SWITCHCASE_OVERRIDE', '')
        logger.debug("override: {}".format(override))
        if override:
            prefix = prefix + ':' + override
            logger.debug("getting from override prefix: {}".format(prefix))
        # Get the json we stored in Redis
        raw_value = self.get(key, prefix)
        # Convert the json to a dict
        literal_value = json.loads(raw_value, object_hook=ascii_encode_dict)
        # Finally, in my usage I use ints as keys (modes)
        # json.loads gives me strings, so this converts them
        value = convert_int_keys_walk(literal_value)
        return value

    def get_mvpd_modes(self):
        return self.get_generic_dict('mvpd_modes')

    def get_skip_modes(self):
        return self.get_generic_dict('skip_modes')

    def get_events_modes(self):
        return self.get_generic_dict('events_modes')

    def get_color_correct_modes(self):
        return self.get_generic_dict('color_correct_modes')

    def get_flip_mirror_modes(self):
        return self.get_generic_dict('flip_mirror_modes')

    def get_patches(self):
        return self.get_generic_dict('patches')

    def get_init_tos(self, user):
        init_tos_dict = self.get_generic_dict('init_tos')
        parsed_dict = walk_node(init_tos_dict, user)
        return parsed_dict

    def get_init_events_modes(self, user):
        init_events_modes_dict = self.get_generic_dict('init_events_modes')
        parsed_dict = walk_node(init_events_modes_dict, user)
        return parsed_dict

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

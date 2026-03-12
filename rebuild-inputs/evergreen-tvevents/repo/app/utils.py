"""
Util functionality used by the Route control paths.
"""

import json
from concurrent.futures import ThreadPoolExecutor
import os
import datetime

# OTEL Imports
from flask import Blueprint
from opentelemetry import trace

import app
from cnlib.cnlib import firehose, token_hash
from app import dbhelper, meter
from app.event_type import event_type_map

LOGGER = app.configure_logging()

# Setup OTEL trace
bp = Blueprint('routes', __name__)
tracer = trace.get_tracer(__name__)

# Create metrics counters
SND_VLD_FH = meter.create_counter(
    name="send_to_valid_firehoses_counter",
    description="Data Firehose PUT requests",
)


REQUIRED_PARAMS = ('tvid', 'client', 'h', 'EventType', 'timestamp')
SALT_KEY = os.environ.get('T1_SALT')
TVEVENTS_RDS = dbhelper.TvEventsRds()
OBFUSCATED_STR = 'OBFUSCATED'
ZOO = os.getenv('FLASK_ENV')

VALID_TVEVENTS_FIREHOSES = []
VALID_TVEVENTS_DEBUG_FIREHOSES = []

if os.environ.get('SEND_EVERGREEN', 'false').lower() == 'true':
    VALID_TVEVENTS_FIREHOSES.append(os.getenv('EVERGREEN_FIREHOSE_NAME'))
    VALID_TVEVENTS_DEBUG_FIREHOSES.append(os.getenv('DEBUG_EVERGREEN_FIREHOSE_NAME'))

# For Evergreen (Firehose that puts data into the legacy cn-tvevents/<ZOO>/tvevents/ bucket)
if os.environ.get('SEND_LEGACY', 'false').lower() == 'true':
    VALID_TVEVENTS_FIREHOSES.append(os.getenv('LEGACY_FIREHOSE_NAME'))
    VALID_TVEVENTS_DEBUG_FIREHOSES.append(os.getenv('DEBUG_LEGACY_FIREHOSE_NAME'))


class TvEventsDefaultException(Exception):
    """Base Exception object for custom TvEvents Exceptions"""

    status_code = 400


class TvEventsCatchallException(TvEventsDefaultException):
    """Error when something goes wrong within the route execution"""


class TvEventsMissingRequiredParamError(TvEventsDefaultException):
    """Error when required param is not provided"""


class TvEventsSecurityValidationError(TvEventsDefaultException):
    """Error when security hash decryption doesn't match given tvid"""


class TvEventsInvalidPayloadError(TvEventsDefaultException):
    """Error when payload is not valid"""


def verify_required_params(payload, required_params=None):
    """
    Given a dictionary of input params,
    ensure all required params for this service are provided.
    Params:
        payload : dict of payload params
        required_params : iterable of required payload params
    returns - True/Exception
    """
    required = required_params or REQUIRED_PARAMS
    payload_params = payload['TvEvent'] if 'TvEvent' in payload else payload
    for req_param in required:
        if req_param not in payload_params:
            msg = 'Missing Required Param: {}'.format(req_param)
            raise TvEventsMissingRequiredParamError(msg)

    return True


def timestamp_check(ts, tvid, is_ms=True):
    """
    Given a timestamp check if valid or not
    """
    if ts is None or ts == '':
        return None
    try:
        if is_ms:
            datetime.datetime.fromtimestamp(ts / 1000)
        else:
            datetime.datetime.fromtimestamp(ts)
        return True
    except Exception as e:
        # pylint: disable=W0707
        raise TvEventsInvalidPayloadError(
            'Timestamp check failed: tvid={} ts={} with error {}'.format(tvid, ts, e)
        )


def unix_time_to_ms(ts):
    """
    Given a timestamp, convert to milliseconds
    """
    return ts * 1000


def params_match_check(param_name, url_param, payload_param):
    """
    There are duplicate parameters sent in both the URL and the payload.
    This is a convenience method to ensure both are the same value.
    Params:
        param_name: str, name of the param for logging purposes.
        url_param: str, param coming from the url
        payload_param: str, same param coming from the JSON payload
    Returns:
        bool
    """
    if url_param != payload_param:
        LOGGER.warning(
            '{} Mismatch. Request url and payload params do not match [{} != {}]'.format(
                param_name, url_param, payload_param
            )
        )

    return url_param == payload_param


def get_event_type_mapping(event_type):
    """
    Given an event_type, return the EventType it maps to
    Params:
        event_type: str, TvEvent EventType from payload
    Returns:
        EventType or None
    """
    mapping = None
    try:
        mapping = event_type_map[event_type]
    except KeyError as ke:
        LOGGER.warning(
            'generate_output: Mapping for EventType {} does not exist {}'.format(
                event_type, ke
            )
        )

    return mapping


def validate_security_hash(tvid, h_value):
    """
    Validate the security hash for the given tvid and h_value.
    Params:
        tvid: str, the tvid from the request
        h_value: str, the security hash value from the request
    Returns:
        bool: True if hash matches, raises TvEventsSecurityValidationError otherwise
    """
    if not token_hash.security_hash_match(tvid, h_value, SALT_KEY):
        raise TvEventsSecurityValidationError(
            'Security hash decryption failure for tvid={}.'.format(tvid)
        )
    return True


def validate_request(url_params, payload):
    """
    Go through validation checks to ensure input request parameters are valid for this service.
        Check for mismatched values between url and payload params.
        Check that hash is valid
        Check that required params are provided
        Check that timestamp is valid.

    Params:
        url_params : dict of params from request
        payload : dict of payload from request
    returns - True/Exception
    """
    tvid = url_params.get('tvid')

    # validate the required params of TvEvent
    LOGGER.debug('validate_request')
    verify_required_params(payload)

    payload_event_type = payload['TvEvent']['EventType']
    # validate the duplicate params have the same values
    params_match_check('tvid', tvid, payload['TvEvent']['tvid'])
    params_match_check('event_type', url_params.get('event_type'), payload_event_type)

    payload_event_timestamp = payload['TvEvent']['timestamp']
    timestamp_check(payload_event_timestamp, tvid)

    # validate tv hash
    h_value = payload['TvEvent']['h']
    validate_security_hash(tvid, h_value)

    # validate EventData for payload EventType
    et_map = get_event_type_mapping(payload_event_type)
    if et_map:
        et_object = et_map(payload)
        et_object.validate_event_type_payload()
    # Proceed even if no event_type mapping
    LOGGER.debug('validate_request completed')
    return True


# pylint: disable=W0102
def flatten_request_json(request_json, key_prefix='', ignore_keys=[]):
    """
    Flattens nested request_json
    Params:
        request_json : nested json to flatten
        key_prefix : prefix to an output key
        ignore_keys : list of keys to be ignored while flattening nested json
    returns : flat linear json
    """
    out = {}

    for k in request_json:
        if k not in ignore_keys:
            if isinstance(request_json[k], dict):
                out.update(flatten_request_json(request_json[k], key_prefix=k))
            else:
                key = key_prefix + '_' + k if key_prefix else k
                out[key.lower()] = request_json[k]
    return out


def get_payload_namespace(payload):
    """
    Get namespace from payload
    Params:
        payload : dict
    returns : namespace value
    """
    namespace = None
    event_namespace_options = ['Namespace', 'NameSpace', 'namespace']
    for option in event_namespace_options:
        if option in payload:
            namespace = payload[option]

    return namespace


def is_blacklisted_channel(channelid):
    """
    Forms the sql needed to check if the input channelid is blacklisted or not
    Params:
        channelid : string
    returns : True or False
    """
    # channelid value is optional
    if channelid is None:
        return False

    LOGGER.debug('Checking if channel is blacklisted: {}'.format(channelid))
    return str(channelid) in TVEVENTS_RDS.blacklisted_channel_ids()


def send_to_valid_firehoses(data, tvevents_debug_flag=False):
    """
    Send data to all the firehoses with env value = True, in parallel.
    Params:
        data : dict
        tvevents_debug_flag : boolean
    Returns : None
    """
    SND_VLD_FH.add(1)
    with tracer.start_as_current_span('send_to_valid_firehoses'):
        try:
            if tvevents_debug_flag:
                valid_firehoses_of_zoo = VALID_TVEVENTS_DEBUG_FIREHOSES
                valid_fh_msg = (
                    f'valid debug firehoses of {ZOO} zoo: {valid_firehoses_of_zoo}'
                )
                msg = 'payload submitted to all valid debug firehoses.'
            else:
                valid_firehoses_of_zoo = VALID_TVEVENTS_FIREHOSES
                valid_fh_msg = f'valid firehoses of {ZOO} zoo: {valid_firehoses_of_zoo}'
                msg = 'payload submitted to all valid firehoses.'

            LOGGER.info(valid_fh_msg)

            def send(fh):
                fh_handler = firehose.Firehose(fh)
                with tracer.start_as_current_span('cnlib.firehose.Firehose'):
                    try:
                        fh_handler.send_records([{'Data': json.dumps(data)}])
                    except Exception as err:
                        LOGGER.error(
                            f'cnlib.firehose.Firehose error sending to Firehose - {err}'
                        )

            # Send to all firehoses in parallel
            with ThreadPoolExecutor() as executor:
                with tracer.start_as_current_span('tpexec_valid_firehoses_of_zoo'):
                    try:
                        executor.map(send, valid_firehoses_of_zoo)
                    except Exception as e:
                        LOGGER.error(
                            f'tpexec_valid_firehoses_of_zoo failed: tvid={data.get("tvid")} - {e}'
                        )
            LOGGER.debug(f'{msg}: {json.dumps(data)}')
        except Exception as ee:
            LOGGER.error(
                f'send_to_valid_firehoses failed: tvid={data.get("tvid")} - {ee}'
            )


def should_obfuscate_channel(output_json):
    """
    Determines if channel info should be OBFUSCATED
    Params:
        output_json str: flattened json
    returns : Boolean
    """
    channel_id = output_json.get('channelid')
    is_content_blocked = output_json.get('iscontentblocked', False)

    # Handles scenario where payload value is str instead of bool
    if isinstance(is_content_blocked, str):
        is_content_blocked = is_content_blocked.lower() == 'true'

    LOGGER.debug(
        'should_obfuscate_channel: iscontentblocked={}; channelid={}'.format(
            is_content_blocked, channel_id
        )
    )
    return True if is_content_blocked else is_blacklisted_channel(channel_id)


def generate_output_json(request_json):
    """
    generates flattened json for input payload.
    Params:
        request_json dict: Data to send to the firehose.
    returns : String
    """
    try:
        request_event_type = request_json['TvEvent']['EventType']
        output_json = {}
        output_json.update(
            flatten_request_json(
                request_json['TvEvent'], ignore_keys=['h', 'timestamp', 'EventType']
            )
        )
        output_json['tvevent_timestamp'] = request_json['TvEvent']['timestamp']
        output_json['tvevent_eventtype'] = request_event_type
        output_json['zoo'] = ZOO

        et_map = get_event_type_mapping(output_json['tvevent_eventtype'])

        if et_map:
            et_object = et_map(request_json)
            event_type_output_json = et_object.generate_event_data_output_json()
            output_json.update(event_type_output_json)
            output_json['namespace'] = et_object.namespace
            output_json['appid'] = et_object.appid
        else:
            output_json.update(flatten_request_json(request_json['EventData']))

        return output_json
    except KeyError as ke:
        LOGGER.error(
            'generate_output failed: Missing {err}, {request_json}'.format(
                err=ke, request_json=request_json
            )
        )
        raise
    except Exception as e:
        LOGGER.error('Unhandled exception in generate_output: {err}'.format(err=e))
        raise


def push_changes_to_firehose(payload):
    """
    Push request data to firehose.
    Params:
        payload dict: Data to send to the firehose.
    """

    # TODO: Add error handling if not output_json
    output_json = generate_output_json(payload)

    tvevents_debug = os.getenv('TVEVENTS_DEBUG', 'false').lower() == 'true'
    LOGGER.debug('TVEVENTS_DEBUG is: %s', tvevents_debug)

    with tracer.start_as_current_span('push_changes_to_firehose'):
        # TODO: Only do if NATIVEAPP_TELEMETRY
        if should_obfuscate_channel(output_json):
            # send output to valid debug firehoses
            if tvevents_debug:
                send_to_valid_firehoses(output_json, tvevents_debug)

            LOGGER.debug(
                'Obfuscating: tvid={tvid}, channel_id={ch_id}, iscontentblocked={blocked}'.format(
                    tvid=output_json.get('tvid'),
                    ch_id=output_json.get('channelid'),
                    blocked=output_json.get('iscontentblocked'),
                )
            )
            output_json['channelid'] = OBFUSCATED_STR
            output_json['programid'] = OBFUSCATED_STR
            output_json['channelname'] = OBFUSCATED_STR

        # send output to valid firehoses
        send_to_valid_firehoses(output_json)

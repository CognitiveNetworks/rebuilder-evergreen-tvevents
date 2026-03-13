from .base_redis import BaseRedis, Clusters, Databases
from cnlib import log

__author__ = 'Yunfan Luo <yunfan.luo@cognitivenetworks.com>'

logger = log.getLogger(__name__)


class CDBRedis(BaseRedis):
    def __init__(self, write_host=Clusters.CONTROL_USERS['write'],
                 read_host=Clusters.CONTROL_USERS['read'],
                 db=Databases.CDB,
                 decode_responses=False,
                 retry_on_timeout=False,
                 health_check_interval=0):
        super(CDBRedis, self).__init__(write_host, read_host, db,
                                       decode_responses=decode_responses,
                                       retry_on_timeout=retry_on_timeout,
                                       health_check_interval=health_check_interval)

        # These "colors" are an unused classification of the various
        # fields in CDB - an estimation of how frequently they change

        # These are sent by the TV, and should change rarely
        self.tv_fields = (
            'chipset', 'chipset_subversion', 'client_version', 'client_version_string', 'h',
            'ip_address', 'ip_address_hash', 'oem', 'readonly', 'token', 'tos_version',
            'tv_country', 'tv_firmware_version', 'tv_id', 'tv_lang', 'tv_model_group',
            'tv_model_name', 'u_id'
        )
        # These are inferred from the IP address, and change irregularly
        self.geo_fields = (
            'city', 'country_code', 'dma', 'iso_state', 'isp', 'latitude', 'longitude',
            'region', 'time_zone', 'zipcode'
        )
        # These are set by us, whether by a process or human intervention
        # They might change often
        # Also note, external_ip, udp_port, http_port, az, and ump_id
        # are usually None, unless deliberately pointing them at an ump
        self.assigned_fields = (
            'az', 'cable_detection_mode', 'cec_device_osd_name', 'channel_change_detection_mode',
            'dai_enabled', 'debug_alert_messages', 'debug_flag', 'detect_code', 'enableAudioAcr',
            'enableDummyFingerPrint', 'enableMetrics', 'events_mode', 'external_ip', 'frame_debug_dump',
            'frame_dump_format', 'http_port', 'input_source', 'lds_cooldowns', 'lds_mode', 'log_level',
            'metadata_acr_origin', 'mvpd', 'note', 'notify_control', 'points_allowed', 'points_enc', 'sendSnappyUdp',
            'send_gaming', 'tp_panel_on_off_enabled', 'tunerdata_enabled', 'tuner_heartbeat_interval',
            'tvevents_enabled', 'tvmeta_device_map', 'tvMetricsSendInterval', 'udpEncryptPoints', 'udp_port', 'ump_id',
            'wfblklistchannels_enabled', 'wide_mode'
        )
        # Sticking date_time here, even though I'm pretty sure date_time
        # is not being kept in redis, at least not directly
        # I believe NONE of these are actually being used anymore
        self.temporary_fields = (
            'active', 'detection_on', 'dirty', 'ip_id'
        )

        # These two lists determine how to cast return values coming
        # back from Redis
        # Redis always returns strings, and this saves me from having
        # to remember to cast types in the caller
        self.int_fields = (
            'active', 'cable_detection_mode', 'channel_change_detection_mode', 'client_version', 'dai_enabled',
            'debug_alert_messages', 'debug_flag', 'detection_on', 'detect_code', 'dirty', 'disabled',
            'enableAudioAcr', 'enableDummyFingerPrint', 'enableMetrics', 'events_mode', 'frame_debug_dump',
            'frame_dump_format', 'ip_id', 'log_level', 'metadata_acr_origin', 'notify_control', 'points_allowed',
            'points_enc', 'send_gaming', 'sendSnappyUdp', 'tos_version', 'tp_panel_on_off_enabled', 'tunerdata_enabled',
            'tuner_heartbeat_interval', 'tvevents_enabled', 'tvMetricsSendInterval', 'udpEncryptPoints', 'u_id',
            'wfblklistchannels_enabled'
        )
        self.float_fields = (
            'latitude', 'longitude'
        )

        self.user = None

    def generate_next_uid(self, pipeline=None):
        if pipeline is None:
            return self._writer.incr('meta:latest_uid')
        else:
            return pipeline.incr('meta:latest_uid')

    def set_last_uid(self, uid, pipeline=None):
        current_max_uid = int(self._reader.get('meta:latest_uid'))
        if uid > current_max_uid:
            if pipeline is None:
                self._writer.set('meta:latest_uid', uid)
                ret = uid
            else:
                ret = pipeline.set('meta:latest_uid', uid)
        else:
            ret = current_max_uid
        return ret

    def set(self, token, userdict, pipeline=None):
        ret = super(CDBRedis, self).set(token, userdict, prefix=None,
                                        pipeline=pipeline)
        return ret

    def set_tvid(self, tvid, userdict, pipeline=None):
        ret = super(CDBRedis, self).set(tvid, userdict, prefix=None,
                                        pipeline=pipeline)
        return ret

    def set_tvid_token(self, tvid, token, pipeline=None):
        if pipeline is None:
            pipeline = self._writer
        return pipeline.set('tvid:{}'.format(tvid), token)

    def tvid_to_token(self, tvid, pipeline=None):
        if pipeline is None:
            pipeline = self._reader
        return pipeline.get('tvid:{}'.format(tvid))

    def exists(self, token, pipeline=None):
        ret = super(CDBRedis, self).exists(token, prefix=None,
                                           pipeline=pipeline)
        return ret

    def get(self, token):
        return super(CDBRedis, self).get(token, prefix=None)

    def get_tvid(self, tvid):
        return super(CDBRedis, self).get(tvid, prefix=None)

    def parse_field(self, field, value):
        parsed = super(CDBRedis, self).parse_field(field, value)
        try:
            if parsed == 'None':
                parsed = None
            elif field in self.int_fields:
                parsed = int(parsed)
            elif field in self.float_fields:
                parsed = float(parsed)
        except ValueError as e:
            logger.warning(
                'Failed to parse field: {}, {}:{}'.format(field, parsed, e))

        return parsed

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

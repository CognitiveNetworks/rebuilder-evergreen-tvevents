from .base_redis import BaseRedis, Clusters, Databases
from .. import log

LOGGER = log.getLogger(__name__)


def is_bool(field):
    return field in ("0", "1")


def is_int(field):
    return field.isdigit()


EDITABLE_FIELDS = {"chipset": {},
                   "dai_disabled": {'type_check': is_bool},
                   "dai_client_version_string": {},
                   "tv_ad_id": {},
                   "tv_ad_id_type": {},
                   "lmt": {'type_check': is_bool},
                   "notify_count": {'type_check': is_int},
                   "notify_ts": {'type_check': is_int},
                   "notify_result": {},
                   "tv_group": {},
                   "user_profile": {},
                   "encryption_server_url": {},
                   "encryption_token": {},
                   "enable_ad_replacement": {'type_check': is_bool},
                   "dai_log_level": {'type_check': is_int,
                                     'field_restrictions': ('0', '1', '2', '3')},
                   "acr_independent": {'type_check': is_bool},
                   "proxy_tracking_url": {},
                   "proxy_error_url": {},
                   "go_away_next_update": {'type_check': is_int},
                   "metrics_url": {},
                   "metrics_interval": {'type_check': is_int},
                   "metrics_enable": {'type_check': is_int},
                   "volume_level": {'type_check': is_int,
                                    'field_restrictions': tuple(map(str, range(-1, 101)))},
                   "ignore_audio_state": {'type_check': is_bool},
                   "enable_4k": {'type_check': is_bool},
                   "wm_log_level": {'type_check': is_int,
                                    'field_restrictions': ('0', '1', '2', '3')},
                   "sym_reader_log_level": {'type_check': is_int,
                                            'field_restrictions': ('0', '1', '2', '3')},
                   "audio_volume_replacement_threshold":
                       {'type_check': is_int,
                        'field_restrictions': tuple(map(str, range(101)))}}


class DAIRedis(BaseRedis):
    def __init__(self, write_host=Clusters.DAI_CONTROL['write'],
                 read_host=Clusters.DAI_CONTROL['read'],
                 db=Databases.DAI,
                 decode_responses=False,
                 retry_on_timeout=False,
                 health_check_interval=0):
        LOGGER.debug('DAIRedis init: {} ; {} ; {}'.format(write_host, read_host, db))
        super(DAIRedis, self).__init__(write_host,
                                       read_host,
                                       db,
                                       decode_responses,
                                       retry_on_timeout=retry_on_timeout,
                                       health_check_interval=health_check_interval)

    def batch_hget(self, tvids, key):
        pipe = self._reader.pipeline()
        for tvid in tvids:
            pipe.hget(tvid, key)
        return pipe.execute()

    def batch_hgetall(self, tvids):
        pipe = self._reader.pipeline()
        for tvid in tvids:
            pipe.hgetall(tvid)
        return pipe.execute()

    def batch_hmset(self, tvids, dai_data):
        write_pipe = self._writer.pipeline()
        for tvid in tvids:
            write_pipe.hmset(tvid, dai_data)

        return write_pipe.execute()

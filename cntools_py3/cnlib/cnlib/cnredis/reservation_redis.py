import os

from .base_redis import BaseRedis, Clusters, Databases
from .. import log

__author__ = 'James Bartolome <james.bartolome@inscape.tv'

logger = log.getLogger(__name__)


class ReservationRedis(BaseRedis):
    """
    Class to access the reservation-redis cluster to retrieve reservations from
    queue:reservation:<zoo>.
    """

    def __init__(
            self,
            write_host=Clusters.RESERVATION['write'],
            read_host=Clusters.RESERVATION['read'],
            db=Databases.RESERVATION,
            decode_responses=False,
            retry_on_timeout=False,
            health_check_interval=0):
        super(ReservationRedis, self).__init__(write_host,
                                               read_host,
                                               db,
                                               decode_responses=decode_responses,
                                               retry_on_timeout=retry_on_timeout,
                                               health_check_interval=health_check_interval)

    def __get_queue_suffix(self, name):
        suffix = name

        zoo = os.getenv("ZOO")
        if zoo:
            suffix += ":{zoo}".format(zoo=zoo)

        return suffix

    def push(self, name, *values):
        """
        Queue key name after base class = "queue:<name>:<zoo>"
        """
        suffix = self.__get_queue_suffix(name)
        return super(ReservationRedis, self).push(suffix, *values)

    def push_to(self, key, *values):
        """
        Raw method to push to specified key in case user needs access to
        actual key name
        """
        return super(ReservationRedis, self).push_to(key, *values)

    def pop(self, name):
        suffix = self.__get_queue_suffix(name)
        return super(ReservationRedis, self).pop(suffix)

    def pop_from(self, key):
        """
        Raw method to pop with specified key in case user needs access to
        actual key name
        """
        return super(ReservationRedis, self).pop_from(key)

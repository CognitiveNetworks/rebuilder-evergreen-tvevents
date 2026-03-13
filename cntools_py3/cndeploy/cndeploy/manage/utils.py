"""
Management utils.
"""
from datetime import datetime

from boto.utils import get_instance_metadata
from boto.ec2 import connect_to_region

from cnlib import log

__author__ = 'Alex Roitman <alex.roitman@cognitivenetworks.com>'

__all__ = ['get_instance_tags']

logger = log.getLogger(__name__)


PRODUCT_DESCRIPTION = 'Linux/UNIX'


def get_instance_tags(region):
    """
    Return the dictionary with tags that are set on the current instance,
    or log and raise exception if this cannot be done.
    """
    try:
        am = get_instance_metadata()
        conn = connect_to_region(region)
        reservations = conn.get_all_instances(instance_ids=[am['instance-id']])
        return reservations[0].instances[0].tags
    except Exception as msg:
        logger.exception('Could not get tags: {}'.format(msg))
        raise


def get_spot_prices(instance_types, zones, conn=None, region=None):
    """
    Return spot prices, per instance type, per zone within each instance type.
    """
    if conn is None:
        if region is None:
            raise ValueError('Either connection or region must be given.')
        else:
            conn = connect_to_region(region)

    now_str = datetime.utcnow().isoformat()
    ret = {}

    for instance_type in instance_types:
        ret[instance_type] = {}
        for zone in zones:
            price = conn.get_spot_price_history(
                start_time=now_str,
                end_time=now_str,
                instance_type=instance_type,
                availability_zone=zone,
                product_description=PRODUCT_DESCRIPTION)
            ret[instance_type][zone] = price[0].price if price else None

    return ret

#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
spot prices

By default, prints prices for all instance types considered and all zones
considered

See
- http://alestic.com/2009/12/ec2-spot-instance-prices
"""

# imports
import argparse
import boto
import boto.ec2
import datetime
import os
import sys
from collections import OrderedDict

### module globals

__all__ = ['main', 'instance_types', 'zones', 'SpotPricesParser']
string = (str,)

DEFAULT_REGION = "us-east-1" # default region

# AWS instance types
instance_types = ["t1.micro",
                  "m1.small",
                  "m3.medium",
                  "m3.large",
                  "m3.xlarge",
                  "m3.2xlarge",
                 ]

# AWS zones
zones = ['us-east-1b', 'us-east-1c', 'us-east-1d']


def spot_prices(conn, instance_types=instance_types[:], zones=zones[:]):
    """
    returns spot prices
    """
    t = datetime.datetime.utcnow().isoformat()
    retval = OrderedDict()
    for instance_type in instance_types:
        retval[instance_type] = OrderedDict()
        for zone in zones:
            # Get the current price for instance_type/availability_zone combination
            price = conn.get_spot_price_history(start_time=t,
                                                end_time=t,
                                                instance_type=instance_type,
                                                availability_zone=zone,
                                                product_description="Linux/UNIX")
            price = price[0].price # most recent
            retval[instance_type][zone] = price
    return retval


class SpotPrices(object):

    # AWS instance types
    instance_types = ["t1.micro",
                      "m1.small",
                      "m3.medium",
                      "m3.large",
                      "m3.xlarge",
                      "m3.2xlarge",
                  ]

    # AWS zones
    zones = ['us-east-1b', 'us-east-1c', 'us-east-1d']

    def __init__(self, conn, instance_types=None, zones=None):
        self.conn = conn
        self.instance_types = instance_types or self.instance_types[:]
        self.zones = zones or self.zones[:]



class SpotPricesParser(argparse.ArgumentParser):
    """CLI option parser"""

    def __init__(self, **kwargs):
        kwargs.setdefault('description', __doc__)
        argparse.ArgumentParser.__init__(self, **kwargs)
        self.add_argument('-t', '--type', dest='instance_types', nargs='+',
                          help="instance types to consider [DEFAULT: {}]".format(', '.join(instance_types)))
        self.add_argument('-z', '--az', '--zone', dest='zones', nargs='+',
                          help="availability zones to consider [DEFAULT: {}]".format(', '.join(zones)))
        self.add_argument('-r', '--region', dest='region',
                          default=DEFAULT_REGION,
                          help="default region to connect to [DEFAULT: %(default)s]")
        self.options = None

    def parse_args(self, *args, **kw):
        options = argparse.ArgumentParser.parse_args(self, *args, **kw)
        self.validate(options)
        self.options = options
        return options

    def validate(self, options):
        """validate options"""

        # populate defaults
        if options.instance_types is None:
            options.instance_types = instance_types[:]
        if options.zones is None:
            options.zones = zones[:]

    def conn(self):
        """get AWS connection"""
        return boto.ec2.connect_to_region(self.options.region)

    def spot_prices(self):
        return spot_prices(self.conn(),
                           instance_types=self.options.instance_types,
                           zones=self.options.zones)

def format_prices(prices):
    retval = []
    for instance_type, regions in list(prices.items()):
        retval.append("{} :".format(instance_type))
        for region, price in list(regions.items()):
            retval.append(" {} : {}".format(region, price))
    return '\n'.join(retval)

def main(args=sys.argv[1:]):
    """CLI"""

    # parse command line options
    parser = SpotPricesParser()
    options = parser.parse_args(args)

    # get prices
    prices = parser.spot_prices()

    # output prices
    print(format_prices(prices))

if __name__ == '__main__':
    main()

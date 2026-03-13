#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
launch an ec2 instance
"""
import sys

__all__ = ['main', 'EC2LaunchParser']

from .launch.base import BaseLauncher


class ControlLauncher(BaseLauncher):
    SEC_GRP = "control-server"
    I_TYPE = "m1.small"


def main(args=sys.argv[1:]):
    """CLI"""

    # parse command line options
    launcher = ControlLauncher()
    instance = launcher.run(args, apply_tags=True)

    # print instance ID
    print("Instance ID: {}".format(instance.id))
    print("https://console.aws.amazon.com/ec2/v2/home?region={}#Instances:instancesFilter=all-instances;instanceTypeFilter=all-instance-types;search={}".format(launcher.options.region, instance.id))

    # tag instance
    print('Tags::')
    for tag in sorted(instance.tags.keys()):
        print('{} : {}'.format(tag, instance.tags[tag]))
    print("IP: %s" % instance.ip_address)


if __name__ == '__main__':
    main()

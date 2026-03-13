#!/usr/bin/env python
"""
SQS tests.
"""
import os
import time
import unittest

from moto import mock_autoscaling

from cndeploy.launch import AutoScaleGroupLauncher

__author__ = 'Alex Roitman <alex.roitman@cognitivenetworks.com>'

HERE = os.path.abspath(os.path.dirname(__file__))


class FooBarGroupLauncher(AutoScaleGroupLauncher):
    SERVICE = 'FooBar'
    SVC_TYPE = 'BarFoo'
    SEC_GROUP = 'baz'
    IAM_ROLE = 'BarBaz'
    I_TYPE = 'm3.xlarge'


class AutoScaleGroupLauncherTest(unittest.TestCase):
    def setUp(self):
        self.mock = mock_autoscaling()
        self.mock.start()

        token = int(time.time())
        self.as_group_name = 'test_as_group_%s' % token
        self.env = 'test_env_%s' % token
        self.zoo = 'test_zoo_%s' % token
        self.user_data = os.path.join(HERE, 'data', 'user_data.sh')

        # This is what we are testing here
        self.launcher = FooBarGroupLauncher()

    def tearDown(self):
        self.mock.stop()

    def test_launcher(self):
        as_group = self.launcher.run(args=(
            '--prefix', self.as_group_name,
            '--env', self.env,
            '--zoo', self.zoo,
            '--user-data', self.user_data,
        ))

        self.assertEqual(as_group.name, self.as_group_name)
        self.assertEqual(as_group.launch_config_name, self.as_group_name)

        tag_dict = {tag.key: tag.value for tag in as_group.tags}
        self.assertEqual(tag_dict['Name'], self.as_group_name)
        self.assertEqual(tag_dict['Zoo'], self.zoo)
        self.assertEqual(tag_dict['Environment'], self.env)
        self.assertEqual(tag_dict['Service'], 'FooBar')
        self.assertEqual(tag_dict['Type'], 'BarFoo')

    def test_launcher_bad_args(self):
        # There's 4 mandatory arguments:
        #   * name (no option required)
        #   * environment
        #   * zoo
        #   * user_data
        # So this tests just verifies that anything short of those 4
        # will result in SystemExit.
        for args in (
            (self.as_group_name,),
            (
                '--env', self.env,
                '--zoo', self.zoo,
                '--user-data', self.user_data,
            ),
        ):
            self.assertRaises(SystemExit, self.launcher.run, args)


if __name__ == '__main__':
    unittest.main()

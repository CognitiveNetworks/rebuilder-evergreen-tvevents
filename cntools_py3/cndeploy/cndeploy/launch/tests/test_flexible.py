#!/usr/bin/env python
"""
SQS tests.
"""
import os
import time
import unittest

from moto import mock_ec2

from cndeploy.launch import FlexibleLauncher

__author__ = 'Alex Roitman <alex.roitman@cognitivenetworks.com>'

HERE = os.path.abspath(os.path.dirname(__file__))


class FakeLauncher(FlexibleLauncher):
    WAIT_INTERVAL_SEC = 0.1


class FlexibleLauncherTest(unittest.TestCase):
    def setUp(self):
        self.mock = mock_ec2()
        self.mock.start()

        token = int(time.time())
        self.name = 'test_as_group_%s' % token
        self.env = 'test_env_%s' % token
        self.zoo = 'test_zoo_%s' % token
        self.user_data = os.path.join(HERE, 'data', 'user_data.sh')

        # This is what we are testing here
        self.launcher = FakeLauncher()

    def tearDown(self):
        self.mock.stop()

    def test_launcher(self):
        instance_list = self.launcher.run(args=(
            '--prefix', self.name,
            '--number', '3',
            '--price', '0',
            '--env', self.env,
            '--zoo', self.zoo,
            '--user-data', self.user_data,
            '--service', 'bar',
            '--svc_type', 'foo',
            '--sec_group', 'insecure',
            '--iam-profile', 'foobar',
            '--instance-type', 'm3.medium',
        ))

        self.assertEqual(len(instance_list), 3)

        for instance in instance_list:
            self.assertTrue(instance.tags['Name'].startswith(self.name))
            self.assertEqual(instance.tags['Zoo'], self.zoo)
            self.assertEqual(instance.tags['Environment'], self.env)
            self.assertEqual(instance.tags['Service'], 'bar')
            self.assertEqual(instance.tags['Type'], 'foo')

            self.assertEqual(instance.instance_type, 'm3.medium')
            self.assertEqual(instance.region.name, 'us-east-1')
            self.assertEqual(instance.key_name, 'prod2-cmn')

    def test_launcher_bad_args(self):
        # There's 4 mandatory arguments:
        #   * name (no option required)
        #   * environment
        #   * zoo
        #   * user_data
        # So this tests just verifies that anything short of those 4
        # will result in SystemExit.
        for args in (
            (self.name,),
            (
                '--env', self.env,
                '--zoo', self.zoo,
                '--user-data', self.user_data,
            ),
        ):
            self.assertRaises(SystemExit, self.launcher.run, args)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python
"""
Tests for cndeploy.launch module.
"""
import unittest

__author__ = 'Alex Roitman <alex.roitman@cognitivenetworks.com>'

from .test_base import BaseLauncherTest
from .test_flexible import FlexibleLauncherTest
from .test_auto_scale import AutoScaleGroupLauncherTest


if __name__ == '__main__':
    unittest.main()

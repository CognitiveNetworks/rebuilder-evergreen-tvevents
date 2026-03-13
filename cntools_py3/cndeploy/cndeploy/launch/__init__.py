"""
Module with launching utilities.
"""
from cndeploy.launch.base import BaseLauncher, FlexibleLauncher
from cndeploy.launch.auto_scale import AutoScaleGroupLauncher

__author__ = 'Alex Roitman <alex.roitman@cognitivenetworks.com>'

__all__ = [
    'BaseLauncher',
    'FlexibleLauncher',
    'AutoScaleGroupLauncher',
]

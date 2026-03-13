"""
Auto-scale launchers.
"""
from boto.ec2.autoscale import (
    connect_to_region,
    AutoScalingGroup,
    LaunchConfiguration,
    tag,
)

from cndeploy.launch.base import BaseLauncher
from cnlib import log

__author__ = 'Alex Roitman <alex.roitman@cognitivenetworks.com>'

__all__ = ['AutoScaleGroupLauncher']

logger = log.getLogger(__name__)


class AutoScaleGroupLauncher(BaseLauncher):
    """
    Base class for AutoScale Groups.
    This class does not allow changing the following parameters:
        * service
        * service type
        * security group,
        * IAM role
    Instead, subclasses should override the class variables. For example:

        class SmootherGroupLauncher(AutoScaleGroupLauncher):
            SERVICE = 'Data'
            SVC_TYPE = 'Smoother'
            SEC_GRP = 'data-pipe'
            IAM_ROLE = 'data-pipe'

    If you need more flexibility, use generic.GenericLauncher instead.
    """
    MIN_CAP = 1
    MAX_CAP = 1
    DESIRED_CAP = 1

    def setup(self):
        self.conn = connect_to_region(self.options.region)

    def get_tags(self):
        tags = super(AutoScaleGroupLauncher, self).get_tags()
        tags['Name'] = self.options.prefix
        return tags

    def launch(self):
        launch_config_list = self.conn.get_all_launch_configurations(
            names=[self.options.prefix])
        if launch_config_list:
            logger.info('Using existing launch configuration')
            launch_config = launch_config_list[0]
        else:
            launch_config = LaunchConfiguration(
                name=self.options.prefix,
                instance_type=self.options.instance_type,
                image_id=self.options.ami,
                key_name=self.KEY,
                user_data=self.get_user_data(),
                instance_profile_name=self.IAM_ROLE,
                security_groups=[self.SEC_GRP])
            self.conn.create_launch_configuration(launch_config)
            logger.info('Created new launch configuration')

        as_group_list = self.conn.get_all_groups(names=[self.options.prefix])
        if as_group_list:
            logger.info('Found existing auto-scale group.  Exiting.')
        else:
            as_group = AutoScalingGroup(
                name=self.options.prefix,
                availability_zones=self.ZONES,
                launch_config=launch_config,
                min_size=self.MIN_CAP,
                max_size=self.MAX_CAP,
                desired_capactiy=self.DESIRED_CAP,
                connection=self.conn,
                tags=[
                    tag.Tag(
                        key=k,
                        value=v,
                        propagate_at_launch=True,
                        resource_id=self.options.prefix)
                    for k, v in list(self.get_tags().items())
                ],
            )
            self.conn.create_auto_scaling_group(as_group)
            logger.info('Created new auto-scale group')
            return as_group

    def apply_tags(self, instance_list):
        """
        AS Groups are already tagged, nothing to do.
        """

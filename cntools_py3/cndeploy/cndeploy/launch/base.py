"""
Base launcher classes.
"""
import string
import time
import subprocess

import boto
from boto.ec2 import connect_to_region
import boto3
from botocore.exceptions import BotoCoreError
from botocore.exceptions import ClientError

from cnlib import log
from ..manage.utils import get_spot_prices

__author__ = 'Alex Roitman <alex.roitman@cognitivenetworks.com>'

__all__ = ['BaseLauncher', 'FlexibleLauncher']

logger = log.getLogger(__name__)

PENDING = 'pending'
RUNNING = 'running'
TERMINATED = 'terminated'
PRICE_TOO_LOW = 'price-too-low'
FULFILLED = 'fulfilled'
STOPPED = 'stopped'
STOPPING = 'stopping'


class LocalError(Exception):
    """local error object"""
    pass


class RunSSHCmdError(Exception):
    pass


def check_tags(instance, prefix, createdby):
    tags = tags_dict(instance)

    has_name = tags.get('Name', '').startswith(prefix)
    has_service = tags.get('service') in ('Zion', 'Validation', 'data')  # compatibility - Service tag is replacing with Owner
    has_owner = tags.get('createdby') == createdby

    return has_name and (has_service or has_owner)


def get_running_instances(
        ec2,
        prefix,
        svc_type,
        zoo,
        environment,
        createdby,
):
    for tries in range(2):
        try:
            instances = list(ec2.instances.filter(Filters=[
                {'Name': 'tag:service', 'Values': [svc_type]},
                {'Name': 'tag:zoo', 'Values': [zoo]},
                {'Name': 'tag:env', 'Values': [environment]},
                {'Name': 'tag-key', 'Values': ['Name']},
                {'Name': 'instance-state-name', 'Values': [RUNNING]},
            ]))
            break
        except BotoCoreError as e:
            logger.exception(e)
            time.sleep(15)
    else:
        logger.error('Exceeded retries to get_all_instances')
        raise LocalError('Exceeded retries to get_all_instances')

    instances = [i for i in instances if check_tags(i, prefix, createdby)]

    return instances


class BaseLauncher():
    """
    Base class for all launchers.
    """

    FULFILL_TIMEOUT_SEC = 600  # How long to wait for spot request to fulfill
    LAUNCH_TIMEOUT_SEC = 300   # How long to wait for instance to come up
    WAIT_INTERVAL_SEC = 10     # How often check for status updates

    RELAUNCH_SLEEP_SEC = 15

    LEGAL_CHARS = set(string.ascii_letters + string.digits + '_')
    MON_LEGAL_CHARS = set(string.ascii_letters)
    MONITORING_CHOICES = ('production', 'staging', 'development', 'none')

    TERMINATE_AFTER_SEC = 60 * 60 * 6
    TERMINATE_TAG = 'Terminate'

    # Retry up to this many times if the new instance ID is not visible yet.
    SPOT_INSTANCE_MAX_RETRIES = 3

    # Launch retries
    LAUNCH_MAX_RETRIES = 2

    def __init__(
        self,
        environment,
        zoo,
        user_data,
        prefix,
        monitoring,
        region,
        instance_type,
        placement,
        ami,
        svc_type,
        createdby,
        sec_groups,
        iam_profile,
        subnet_id,
        key,
        zones,
        ssh_connect_timeout,
        ssh_execution_timeout,
        amazon_machine_images,
        number=1,
        price=0.1,
        dry_run=False,
    ):
        '''
        environment - environment tag, needed for obtaining configuration
        zoo - zoo name, needed for obtaining configuration
        user_data - user data script
        prefix- meaningful prefix for forming instance names.
        monitoring - set monitoring priority tag
        region - AWS region
        instance-type - AWS instance type to use
        placement - availability zone
        ami - Amazon Machine Image to use
        svc_type - service type tag
        owner - owner tag
        key - the name of the key pair with which to launch instances
        zones - availability_zones
        ssh-connect-timeout- value for ssh option ConnectTimeout when run command on an instance')
        ssh-execution-timeout -set timeout for waiting ssh command on an instance
        '''
        self.amazon_machine_images = amazon_machine_images
        self.amazon_machine_images['instance_types'] = list(self.amazon_machine_images['instance_type_to_ami_bid_limit'].keys())

        self.environment = environment
        self.zoo = zoo
        self.user_data = user_data
        self.prefix = prefix
        self.monitoring = monitoring
        self.region = region
        self.instance_type = instance_type
        self.placement = placement
        self.ami = ami
        self.svc_type = svc_type
        self.createdby = createdby
        self.sec_groups = sec_groups
        self.iam_profile = iam_profile
        self.subnet_id = subnet_id
        self.key = key
        self.zones = zones
        self.ssh_connect_timeout = ssh_connect_timeout
        self.ssh_execution_timeout = ssh_execution_timeout
        self.number = number
        self.price = price
        self.dry_run = dry_run

        self.ec2 = None
        self.prices = None

        self.validate()

    def validate(self):
        """
        Validate options.  Raise exception if they're invalid.
        """
        amis = self.amazon_machine_images['instance_type_to_ami_bid_limit'][
            self.instance_type][0]
        if self.ami not in amis:
            logger.error(
                '{} AMI {} is not in the list of hardcoded AMIs: {}'.format(
                    self.instance_type, self.ami, amis))

        env_illegal = set(self.environment).difference(self.LEGAL_CHARS)
        if env_illegal:
            self.error(
                'Illegal characters in environment name: {}'.format(
                    ', '.join(env_illegal)))

        zoo_illegal = set(self.zoo).difference(self.LEGAL_CHARS)
        if zoo_illegal:
            self.error(
                'Illegal characters in zoo name: {}'.format(
                    ', '.join(zoo_illegal)))

        monitoring_illegal = set(
            self.monitoring).difference(self.MON_LEGAL_CHARS)
        if monitoring_illegal:
            self.error(
                'Illegal characters in monitoring tag name: {}'.format(
                    ', '.join(monitoring_illegal)))
        if self.instance_type not in self.amazon_machine_images['instance_types']:
            self.error(
                'Instance type not found in amazon_machine_images list')

    def get_user_data(self):
        return self.user_data

    def get_instances(self, key=lambda instance: instance.launch_time, reverse=False):
        import pdb;pdb.set_trace()
        instances = get_running_instances(
            ec2=self.ec2,
            prefix=self.prefix,
            svc_type=self.svc_type,
            zoo=self.zoo,
            environment=self.environment,
            createdby=self.createdby
        )

        check_tags = {'monitoring': self.monitoring}
        check_tags.update(self.get_tags())

        check_tags_set = set(check_tags.items())
        instances = [i for i in instances if set(tags_dict(i).items()) >= check_tags_set]
        return sorted(instances, key=key, reverse=reverse)

    def setup(self):
        """
        Set things up in a way specific for this launcher.
        """
        self.key_file = '{}.pem'.format(self.key)
        self.ec2 = boto3.resource('ec2', region_name=self.region)

        if self.price > 0:
            self.get_prices()

    def get_prices(self):
        self.prices = get_spot_prices(
            self.amazon_machine_images['instance_types'], self.zones, self.conn)

    def get_instance_ids_to_kill(self):
        return [instance.id for instance in self.get_instances_to_kill()]

    def check_instance_not_being_terminated(self, instance):
        return self.TERMINATE_TAG not in tags_dict(instance)

    def get_instances_to_kill(self):
        instances = list(filter(
            self.check_instance_not_being_terminated, self.get_instances()))
        return instances[:abs(self.number)]

    def kill(self):
        if self.TERMINATE_AFTER_SEC:
            return self.kill_later()
        else:
            return self.kill_now()

    def kill_now(self):
        instances = self.get_instances_to_kill()

        # output runtime information
        logger.info('Terminating {} instances'.format(len(instances)))

        if not instances:
            return []

        if self.dry_run:
            return []

        return self.terminate_instances(instances)

    def terminate_instances(self, instances):
        instance_ids = []
        for instance in instances:
            if instance.state['Name'] != TERMINATED:
                if self.TERMINATE_TAG not in tags_dict(instance):
                    target = int(time.time()) + self.TERMINATE_AFTER_SEC
                    instance.create_tags(Tags=[
                        {'Key': self.TERMINATE_TAG, 'Value': str(target)}
                    ])
                instance_ids.append(instance.id)

        if instance_ids:
            result = self.ec2.instances.filter(InstanceIds=instance_ids).stop(Force=True)[0]

            return [i_info['InstanceId'] for i_info in result['StoppingInstances']
                        if i_info['CurrentState']['Name'] in (STOPPED, STOPPING)]

        else:
            return []

    def kill_later(self):
        """
        Kill at the later time: an alternative to immediate killing.
        """
        instances = self.get_instances_to_kill()

        # output runtime information
        logger.info(
            'Marking {} instances for termination'.format(len(instances)))

        if self.dry_run:
            return []

        target = int(time.time()) + self.TERMINATE_AFTER_SEC
        for instance in instances:
            self.schedule_shutdown(instance)
            instance.create_tags(Tags=[
                {'Key': self.TERMINATE_TAG, 'Value': str(target)}
            ])
        return instances

    def schedule_shutdown(self, instance):
        raise NotImplementedError('Must be implement in a subclass.')

    def launch(self):
        """
        Launch and return the launched instance/group.
        """
        if self.price > 0:
            self.conn = connect_to_region(self.region)
            return self.launch_spot()
        return self.launch_on_demand()

    def launch_on_demand(self):
        placement = {'AvailabilityZone': self.placement or self.AZ}
        iam_profile = {'Name': self.iam_profile}
        instance_type = self.instance_type

        logger.info('On demand instance in zone {} for {}'.format(
            self.placement, instance_type))

        if self.dry_run:
            return []

        if instance_type.startswith('c4') or instance_type.startswith('r4') or instance_type.startswith('r5.'):

            block_device_map = [
                {'DeviceName': '/dev/sda1',
                 'Ebs': {'DeleteOnTermination': True,
                         'VolumeSize': 8}},
                {'DeviceName': '/dev/sdb',
                 'Ebs': {'DeleteOnTermination': True,
                         'VolumeSize': 40}}
            ]
        else:
            block_device_map = []

        for tries in range(self.LAUNCH_MAX_RETRIES):
            try:
                instances = self.ec2.create_instances(
                    ImageId=self.ami,
                    SubnetId=self.subnet_id,
                    MinCount=self.number,
                    MaxCount=self.number,
                    KeyName=self.key,
                    InstanceType=instance_type,
                    SecurityGroupIds=self.sec_groups,
                    Placement=placement,
                    IamInstanceProfile=iam_profile,
                    BlockDeviceMappings=block_device_map,
                    UserData=self.get_user_data())
                return instances

            except (BotoCoreError, ClientError) as msg:
                logger.exception(msg)
                self.fix_relaunch_on_demand(error=msg)

        logger.error('Exceeded retries to create instances')
        return []

    def fix_relaunch_on_demand(self, error=None):
        """
        Hook for relaunching after exception
        """
        time.sleep(self.RELAUNCH_SLEEP_SEC)

    def launch_spot(self):
        spot_requests = self.request_spot()
        return self.resolve_spot(spot_requests)

    def request_spot(self):
        if self.placement:
            placement = self.placement
        else:
            # choose cheapest zone
            cheapest_list = sorted(
                [
                    (zone, float(price))
                    for zone, price in list(self.prices[self.instance_type].items())
                    if price is not None
                ],
                key=lambda x: x[-1])
            placement, price = \
                cheapest_list[0] if cheapest_list else (self.zones[0], 0)

        price = self.price
        max_price = self.amazon_machine_images['instance_type_to_ami_bid_limit'][
            self.instance_type][1]
        if price > max_price:
            logger.debug('Capping price by {:0.2f}'.format(max_price))
            price = max_price

        price_str = '{:0.2f}'.format(price)
        logger.info('Spot bid: {} in zone {} for {}'.format(
            price_str, placement, self.instance_type))

        if self.dry_run:
            return []

        spot_requests = self.conn.request_spot_instances(
            price_str,
            self.ami,
            count=self.number,
            key_name=self.key,
            instance_type=self.instance_type,
            security_groups=(
                [self.sec_group]
                if isinstance(self.sec_group, str)
                else self.sec_group),
            placement=placement,
            instance_profile_name=self.iam_profile,
            user_data=self.get_user_data())

        logger.info('Placed spot request for {} instances.'.format(
            self.number))
        return spot_requests

    def resolve_spot(self, spot_requests):
        instance_ids, low_price_ids, unresolved_spot_request_ids = \
            self.wait_for_spot_requests(spot_requests)

        logger.debug('Got {} instance IDs:'.format(len(instance_ids)))
        logger.debug(', '.join(instance_ids))

        if any(low_price_ids):
            self.handle_denied_spot_requests(low_price_ids)

        if any(unresolved_spot_request_ids):
            self.handle_missing_spot_requests(unresolved_spot_request_ids)

        instance_ids = list(filter(bool, instance_ids))
        if not instance_ids:
            return []

        for retry_ix in range(self.SPOT_INSTANCE_MAX_RETRIES):
            try:
                time.sleep(self.WAIT_INTERVAL_SEC)
                reservations = self.conn.get_all_instances(instance_ids)
                break
            except Exception as msg:
                logger.exception(msg)
                logger.info(
                    'Failed to get new instances, attempt {}/{}'.format(
                        retry_ix + 1, self.SPOT_INSTANCE_MAX_RETRIES))
        else:
            reservations = []
            logger.error(
                'Could not obtain instances with IDs: %s. '
                % ', '.join(instance_ids))
            logger.error('They must be cleaned up manually.')
        return sum(
            [reservation.instances for reservation in reservations], [])

    def handle_denied_spot_requests(self, low_price_ids):
        """
        Do nothing.  Subclasses may have different action here.
        """

    def handle_missing_spot_requests(self, unresolved_spot_request_ids):
        for req in self.conn.get_all_spot_instance_requests(
                request_ids=unresolved_spot_request_ids):
            req.cancel()
            logger.debug('Canceled un-resolved spot request %s' % req.id)

    def run(self, apply_tags=True, number=None, dry_run=None):
        if number is not None:
            self.number = number
        if dry_run is not None:
            self.dry_run = dry_run
        logger.info('Running %s' % self.__class__.__name__)
        self.setup()
        return self.launch_or_kill(apply_tags)

    def launch_or_kill(self, apply_tags=True):
        if self.number > 0:
            instance_list = self.launch()
            if apply_tags:
                self.apply_tags(instance_list)

            self.post_launch(instance_list)
        elif self.number < 0:
            instance_list = self.kill()

        else:
            instance_list = []

        return instance_list

    def post_launch(self, instance_list):
        """
        A hook for the subclasses to do something with the launched instances.
        """

    def wait_while_pending(self, instance):
        """
        Wait for a given instance to change its status from pending,
        up until the timeout.
        Return True if the status did change from pending, False otherwise.
        """
        deadline = time.time() + self.LAUNCH_TIMEOUT_SEC
        status = PENDING

        while status != RUNNING and time.time() < deadline:
            time.sleep(self.WAIT_INTERVAL_SEC)
            try:
                instance.reload()  # update instance state
                status = instance.state['Name']
            except Exception as e:
                pass

        return status != PENDING

    def wait_for_spot_requests(self, spot_requests):
        """
        Wait for a list of given spot requests ids to
        either get instance ids or reject because of low price,
        up until the timeout.

        Return a list of instance IDs, and a list of low-price requests
        that did not go through.
        """
        request_ids = [req.id for req in spot_requests]
        logger.debug('Request IDs: %s' % request_ids)

        instance_ids = []
        low_price_ids = []

        deadline = time.time() + self.FULFILL_TIMEOUT_SEC

        while any(request_ids) and time.time() < deadline:
            time.sleep(self.WAIT_INTERVAL_SEC)
            spot_requests = self.conn.get_all_spot_instance_requests(
                request_ids=request_ids)
            for req in spot_requests:
                logger.debug('Request status: %s' % req.status.code)
                if req.status.code == PRICE_TOO_LOW:
                    req.cancel()
                    low_price_ids.append(req.id)
                    request_ids.remove(req.id)
                elif req.status.code == FULFILLED:
                    instance_ids.append(req.instance_id)
                    request_ids.remove(req.id)

        return instance_ids, low_price_ids, request_ids

    def apply_tags(self, instance_list):
        """
        Update running instance with the desired tags.
        """
        try:
            existing_list = self.get_instances()
            numbers = list(map(self.index_from_instance, existing_list))
            start = max(numbers) + 1 if numbers else 0
            tags_failed_on = []
            for ix, instance in enumerate(instance_list, start=start):
                tags = self.get_per_instance_tags(ix)
                if not self.apply_tags_to_instance(tags, instance):
                    tags_failed_on.append(instance)
        except Exception as msg:
            logger.exception(msg)
            logger.info('Failed to apply tags!')
            tags_failed_on = instance_list[:]

        if tags_failed_on:
            logger.info('Terminating instances that failed to set tags: %s'
                        % tags_failed_on)
            for failed_instance in tags_failed_on:
                instance_list.remove(failed_instance)
            self.terminate_instances(tags_failed_on)

    def get_tags(self):
        """ overwrite by some child classes like pm2 adding Section tag """
        return {}

    def get_per_instance_tags(self, ix):
        tags = {}
        tags['zoo'] = self.zoo
        tags['env'] = self.environment
        tags['service'] = self.svc_type
        tags['monitoring'] = self.monitoring
        tags['index'] = str(ix)
        tags['Name'] = '%s_%s' % (self.prefix, ix)
        tags['createdby'] = self.createdby
        tags.update(self.get_tags())
        return tags

    def apply_tags_to_instance(self, tags, instance):
        """
        Apply tags to the instance.
        Return boolean of whether that succeeded.
        """
        if not self.wait_while_pending(instance):
            logger.critical('Instance still pending after the timeout')
            return False

        if instance.state['Name'] != RUNNING:
            logger.critical(
                'Cannot apply tags on a non-running instance: {} {}'.format(
                    instance.id, instance.state['Name']))
            return False

        prepared_tags = [{'Key': k, 'Value': v} for k, v in list(tags.items())]
        instance.create_tags(Tags=prepared_tags)
        return True

    def index_from_instance(self, instance):
        try:
            return int(tags_dict(instance).get('Index', -1))
        except Exception:
            return -1

    def list_instances(self):
        instances = self.get_instances()
        print('\n'.join(sorted(map(str, instances))))

    def run_cmd_on_instance(self, instance, cmd):
        """
        SSH onto an instance and run the command.
        The command must not contain un-escaped quotes!
        """
        ssh_command = (
            'ssh -o StrictHostKeyChecking=no -o ConnectTimeout={connect_timeout}'
            ' -i ~/.ssh/{key_file} {host} "{cmd}" '
        ).format(
            key_file=self.key_file,
            host=instance.private_ip_address,
            cmd=cmd,
            connect_timeout=self.ssh_connect_timeout)

        try:
            subprocess.run(
                ssh_command,
                shell=True,
                check=True,
                stderr=subprocess.PIPE,
                timeout=self.ssh_execution_timeout,
                encoding='utf8')
        except subprocess.SubprocessError as e:  # raise if return code != 0 or timeout
            exc_info = str(e) + '\n' + 'stderr: ' + e.stderr
            raise RunSSHCmdError(exc_info)

    def print_instance_data(self, *instances):
        """
        print metadata about the instances
        """

        url = 'https://console.aws.amazon.com/ec2/v2/home?region={}#Instances:search={};sort=instanceState'
        for instance in instances:
            print(url.format(self.region, instance.id))
            print("  {} / {}".format(
                instance.ip_address, instance.private_ip_address))
            tags = instance.tags
            for tag in sorted(tags.keys()):
                print("  {} : {}".format(tag, tags[tag]))
        print()


def tags_dict(instance_obj):
    return {tag['Key']: tag['Value'] for tag in instance_obj.tags}


class FlexibleLauncher(BaseLauncher):
    """
    Flexible instance launcher class, with every bit of flexibility
    we want to allow.  This should not be used much.  The instances
    with known types should instead use the typed.TypedLauncher class.
    """

    def add_optional_args(self):
        super(FlexibleLauncher, self).add_optional_args()

        self.add_argument(
            '--svc_type', dest='svc_type', required=True,
            help="service type tag")
        self.add_argument(
            '--sec_group', dest='sec_group', required=True,
            help="security group")
        self.add_argument(
            '--profile', '--iam-profile', dest='iam_profile',
            required=True,
            help="IAM profile to use")

    def adjust_options(self, options):
        return options

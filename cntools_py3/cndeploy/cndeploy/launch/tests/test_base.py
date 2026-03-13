import time
import os.path

import pytest

import cnlib.conf
from ...launch import BaseLauncher
from ...launch.base import tags_dict


HERE = os.path.abspath(os.path.dirname(__file__))


amis = cnlib.conf.load(os.path.join(HERE, 'data', 'amazon_machine_images.yaml'))
amazon_machine_images = amis['amazon_machine_images']


@pytest.fixture
def params(mock_ec2_fixture):
    token = int(time.time())
    return dict(
        prefix='test_name_%s' % token,
        environment='test_env_%s' % token,
        zoo='test_zoo_%s' % token,
        user_data=os.path.join(HERE, 'data', 'user_data.sh'),
        svc_type='Foo_%s' % token,
        owner='automate',
        sec_groups=[mock_ec2_fixture['sec_group']],
        instance_type='m3.xlarge',
        iam_profile='foo_bar_%s' % token,
        ami=amazon_machine_images['hmv_ssd'],
        price=0,
        monitoring='staging',
        region=mock_ec2_fixture['region'],
        placement=mock_ec2_fixture['az'],
        subnet_id=mock_ec2_fixture['subnet_id'],
        key='fake_key',
        zones=['us-east-2k', 'us-east-3c'],
        ssh_connect_timeout=10,
        ssh_execution_timeout=15,
        amazon_machine_images=amazon_machine_images,
    )


@pytest.fixture
def launcher(params):
    class FooLauncher(BaseLauncher):
        FULFILL_TIMEOUT_SEC = 0.1
        LAUNCH_TIMEOUT_SEC = 0.1
        WAIT_INTERVAL_SEC = 0.1

        def schedule_shutdown(self, instance):
            pass

    return FooLauncher(**params)


def create_instance(ec2, tags=None):
    instances = ec2.create_instances(
        'ami-1234abcd',
        MinCount=1,
        MaxCount=1)
    instance = instances[0]
    if tags is not None:
        prepated_tags = [{'Key': k, 'Value': v} for k, v in list(tags.items())]
        instance.create_tags(Tags=prepated_tags)

    return instance


def test_demand(mock_ec2_fixture, params, launcher):
    # let it has some instances
    init_instance_list = launcher.run(number=2)
    assert len(init_instance_list) == 2

    # this instances will be tested
    instance_list = launcher.run(number=2)

    assert len(instance_list) == 2

    tag_Index_list = sorted([
        int(tags_dict(i)['Index']) for i in instance_list
    ])

    assert tag_Index_list == [2, 3]

    for instance in instance_list:
        tags = tags_dict(instance)
        assert tags['Name'].startswith(params['prefix'])
        assert tags['zoo'] == params['zoo']
        assert tags['Environment'] == params['environment']
        assert tags['Type'] == params['svc_type']
        assert tags['Monitoring'] == params['monitoring']
        assert tags['Owner'] == params['owner']

        assert instance.image_id == params['ami']
        assert instance.instance_type == params['instance_type']
        assert instance.key_name == params['key']
        assert instance.subnet_id == params['subnet_id']
        assert instance.placement['AvailabilityZone'] == params['placement']
        assert [g['GroupId'] for g in instance.security_groups] == params['sec_groups']
    assert launcher.zones == ['us-east-2k', 'us-east-3c']


def test_kill(mock_ec2_fixture, launcher):
    launcher.run(number=3)

    kill_list = launcher.run(number=-2)
    assert len(kill_list) == 2


def test_kill_matching_tags(mock_ec2_fixture, ec2, params, launcher):
    # create some instances which should be matched for killing
    expected_instance = create_instance(ec2, tags={
            'Zoo': params['zoo'],
            'Environment': params['environment'],
            'Type': params['svc_type'],
            'Monitoring': params['monitoring'],
            'Name': params['prefix'],
            'Foo': 'Bar',
            'Owner': 'automate',
        })


    # create some instance which should NOT be matched for killing
    i1 = create_instance(ec2, tags=None)
    i3 = create_instance(ec2, tags={
            'Zoo': params['zoo'],
            'Environment': params['environment'],
            'Monitoring': params['monitoring'],
            'Name': params['prefix'],
        })
    i2 = create_instance(ec2, tags={
            'Zoo': params['zoo'],
            'Environment': params['environment'],
            'Type': params['svc_type'],
            'Monitoring': params['monitoring'],
        })
    i4 = create_instance(ec2, tags={
            'Zoo': params['zoo'],
            'Environment': params['environment'],
            'Type': params['svc_type'],
            'Monitoring': params['monitoring'],
            'Name': params['prefix'],
        })
    i4.stop()
    i4.reload()
    assert i4.state['Name'] == 'stopped'

    i5 = create_instance(ec2, tags={
            'Zoo': params['zoo'],
            'Environment': params['environment'],
            'Type': 'Wrong service type',
            'Monitoring': params['monitoring'],
            'Name': params['prefix'],
        })

    got_instances = launcher.run(number=-10)
    assert len(got_instances) == 1
    got_instance = got_instances[0]

    assert expected_instance == got_instance

    expected_instance.reload()
    assert 'Terminate' in tags_dict(expected_instance)
    assert expected_instance.state['Name'] == 'running'

    # instance which should not be touched
    for instance in [i1, i2, i3, i5]:
        instance.reload()
        assert 'Terminate' not in tags_dict(instance)
        assert instance.state['Name'] == 'running'

    i4.reload()
    assert 'Terminate' not in tags_dict(i4)
    assert i4.state['Name'] == 'stopped'


def test_terminate_instances_method(mock_ec2_fixture, launcher, ec2):
    i1 = create_instance(ec2, tags={'Terminate': '123'})
    i2 = create_instance(ec2, tags=None)
    instances = [i1, i2]
    for instance in instances:
        instance.reload()

    launcher.number = 0
    launcher.setup()
    ids = launcher.terminate_instances(instances)

    assert ids == [i.id for i in instances]


def test_dry_run(mock_ec2_fixture, launcher):
    instance_list = launcher.run(number=2, dry_run=True)
    assert len(instance_list) == 0

    instance_list = launcher.run(number=-2)
    assert len(instance_list) == 0

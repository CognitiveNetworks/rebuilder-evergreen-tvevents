import pytest
import boto3
from moto import mock_ec2


region = 'us-east-2'
az = region + 'k'


@pytest.fixture
def mock_ec2_fixture():
    mock = mock_ec2()
    mock.start()

    ec2 = boto3.resource('ec2', region_name=region)
    default_vpc = list(ec2.vpcs.all())[0]
    assert default_vpc.cidr_block == '172.31.0.0/16', 'moto should have 172.31.0.0/16 as default vpc cidr block'
    subnet1 = ec2.create_subnet(
        VpcId=default_vpc.id, CidrBlock='172.31.0.0/27', AvailabilityZone=az)

    group = ec2.create_security_group(
        GroupName='foo', Description='Test security group foo', VpcId=default_vpc.id)

    yield {
        'region': region,
        'az': az,
        'subnet_id': subnet1.id,
        'sec_group': group.id,
    }
    mock.stop()


@pytest.fixture
def ec2(mock_ec2_fixture):
    return boto3.resource('ec2', region_name=region)

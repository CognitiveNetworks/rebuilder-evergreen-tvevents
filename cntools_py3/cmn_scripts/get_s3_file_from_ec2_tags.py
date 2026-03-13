import argparse
import sys
import boto.utils
import boto.ec2
import os

# Hard coding a default value up here
# I expect to just be using these...forever
# The options to change these are included later in the argparse
BUCKET = 'cn-deploy'
REGION = 'us-east-1'

# Hard coded order for tags to determine key directory-like prefix
TAG_ORDER = ["Environment",
             "Service",
             "Type",
             "Zoo"]


def construct_tag_dir_path(tags, tag_order=TAG_ORDER):
    tag_order_list = []
    for tag_name in tag_order:
        tag = tags.get(tag_name) or None
        if tag is None:
            print("TAG {} DOES NOT EXIST!".format(tag_name))
        tag_order_list.append(tag)
    prefix_file_path = "/".join(tag_order_list)
    return prefix_file_path


def get_src_file_path(tags, s3_filename):
    prefix_file_path = construct_tag_dir_path(tags)
    src_file_key = os.path.join(prefix_file_path, s3_filename)
    return src_file_key


def get_ec2_tags(region):
    am = boto.utils.get_instance_metadata()
    my_instance_id = am['instance-id']
    print("Creating boto ec2 connection using this as my instance ID: {}".format(my_instance_id))

    conn = boto.ec2.connect_to_region(REGION)
    reservations = conn.get_all_instances(instance_ids=[my_instance_id])
    instance = reservations[0].instances[0]
    tags = instance.tags
    print("My instance tags: {}".format(tags))
    # Tags should look like the following:
    #   {u'Environment': u'Zoo1', u'Type': u'TVC', u'Name': u'control-tvc-as-Zoo1', u'Service': u'Control',
    #   u'aws:autoscaling:groupName': u'control-server-asg-Zoo1'}

    return tags


def get_file_from_s3(src_file_key, local_filename, bucket):
    print("Getting this file from s3://cn-deploy, {}".format(src_file_key))
    print("Putting it here: {}".format(local_filename))
    # The tags determine what the prefix
    # is for the bucket, and the filename is passed via arguments
    conn = boto.connect_s3()
    bucket = conn.get_bucket(bucket)
    key = bucket.get_key(src_file_key)
    if key:
        res = key.get_contents_to_filename(local_filename)
    else:
        print("*** KEY (AKA FILE) DOES NOT EXIST IN S3 ***")


def get_file(s3_filename, local_filename, bucket=BUCKET, region=REGION):
    tags = get_ec2_tags(region)

    # The original s3 copy command, before replacing it with this script:
    #   /usr/local/bin/aws s3 cp s3://cn-deploy/Control/TVC/Zoo1/vassal_tvc.ini /etc/uwsgi/vassals/tvc.ini
    src_file_key = get_src_file_path(tags, s3_filename)

    get_file_from_s3(src_file_key, local_filename, bucket)


if __name__ == "__main__":
    args = sys.argv[1:]
    parser = argparse.ArgumentParser(description='This script gets a file from the s3://cn-deploy bucket, using this '
                                                 'instance tag\'s "Service", "Type", and "Environment" tags as prefixes'
                                                 ' after the bucket')
    parser.add_argument('-i', '--infile', default=None, required=True)
    parser.add_argument('-o', '--outfile', default=None, required=True)
    # These two are included in case one day the BUCKET or REGION values change
    # I don't foresee using these
    parser.add_argument('-b', '--bucket', default=BUCKET)
    parser.add_argument('-r', '--region', default=REGION)

    options = parser.parse_args(args)

    get_file(options.infile, options.outfile, options.bucket, options.region)

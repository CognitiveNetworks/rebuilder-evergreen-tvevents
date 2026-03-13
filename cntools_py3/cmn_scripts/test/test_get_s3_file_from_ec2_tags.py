#!/usr/bin/env python
"""
test get_s3_file_from_ec2_tags.py
"""

import boto
from boto.s3.key import Key
import get_s3_file_from_ec2_tags
from moto import mock_s3
import os
import unittest


TEST_CONTENTS="""1st line
THIS IS THE CONTENTS OF THE TEST_FILE
final line
"""

# test w/o ec2 tag self check
def get_file_test(tags, s3_filename, bucket_name, local_filename):
    src_file_key = get_s3_file_from_ec2_tags.get_src_file_path(tags, s3_filename)
    get_s3_file_from_ec2_tags.get_file_from_s3(src_file_key, local_filename, bucket_name)

def set_up_bucket(tags, s3_filename, bucket_name, local_filename):
    conn = boto.connect_s3()
    bucket = conn.create_bucket(bucket_name)
    src_file_key = get_s3_file_from_ec2_tags.get_src_file_path(tags, s3_filename)
    k = Key(bucket)
    k.key = src_file_key
    k.set_contents_from_string(TEST_CONTENTS)

def get_contents(local_filename):
    contents = ""
    with open(local_filename, 'r') as f:
        contents = f.read()
    os.remove(local_filename)
    return contents

class TestTagFileScript(unittest.TestCase):
    """
    test get_s3_file_From_ec2_tags
    """
    @mock_s3
    def test_get_file(self):
        """
        test w/o ec2 self check tag
        """
        tags = {"Environment": "test_ENV",
                "Service": "test_SVC",
                "Type": "test_TYPE",
                "Zoo": "test_ZOO"
                }
        s3_filename = "test_FILE.file"
        bucket_name = "test_bucket"
        filename="/tmp/test_FILE.file"
        set_up_bucket(tags, s3_filename, bucket_name, filename)
        get_file_test(tags, s3_filename, bucket_name, filename)
        contents = get_contents(filename)
        self.assertEqual(contents, TEST_CONTENTS)

if __name__ == '__main__':
    unittest.main()
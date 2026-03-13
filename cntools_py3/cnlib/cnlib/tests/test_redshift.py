import unittest

from .. import conf
from .. import redshift
from .. import s3

_credentials = None

def pull_credentials():
    global _credentials
    if _credentials is None:
        s3_handler = s3.SingleBucketS3Handler('cn-secure')
        _credentials = conf.parse_conf(s3_handler.read_to_string('redshift_stage_credentials.conf'))
    return _credentials


class RedshiftTestCase(unittest.TestCase):
    """
    Note this is a functional test that connects to the redshift stage cluster.
    """

    @classmethod
    def setUpClass(cls):
        credentials = pull_credentials()
        cls.redshift = redshift.RedshiftHandler(
            **pull_credentials()
        )

    def test_basic(self):
        ret = self.redshift("select 1, 'test'")
        self.assertEqual(ret, [(1, 'test'),])
        ret2 = self.redshift("select 1, 'test'", fetch=False)
        self.assertEqual(ret2, None)
        ret3 = self.redshift("select %s, %s", q_args=(1, 'test'))
        self.assertEqual(ret3, [(1, 'test'),])
        self.redshift.close()
        self.redshift.close()


class TempRedshift(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.redshift = redshift.get_temp_redshift_handler(
            cluster_name='stage-redshift',
            user='root',
            database='stagedetection',
        )

    def test_basic(self):
        ret = self.redshift("select 1, 'test'")
        self.assertEqual(ret, [(1, 'test'),])
        ret2 = self.redshift("select 1, 'test'", fetch=False)
        self.assertEqual(ret2, None)
        ret3 = self.redshift("select %s, %s", q_args=(1, 'test'))
        self.assertEqual(ret3, [(1, 'test'),])
        self.redshift.close()
        self.redshift.close()

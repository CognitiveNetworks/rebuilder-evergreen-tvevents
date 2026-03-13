import unittest
from ..trim_tvid import trim_tvid, TVIDException


class TrimTvidTestCase(unittest.TestCase):

    def test_good_tvid(self):
        tvid = '12345_55555_40938282'
        trimed_id = trim_tvid(tvid)
        self.assertEqual(trimed_id, 12345)

        tvid = '12345__40938282'
        trimed_id = trim_tvid(tvid)
        self.assertEqual(trimed_id, 12345)

    def test_bad_tvid(self):
        tvid = 'abc_123_405'
        self.assertRaises(TVIDException, trim_tvid, tvid)

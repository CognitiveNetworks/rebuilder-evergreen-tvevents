"""
Run with: python -m unittest test_dp4redis
"""

from .. import log
logger = log.getLogger(__name__)

import time
import unittest
import fakeredis

from ..cnredis import base_redis
FAKE_REDIS_SERVER = fakeredis.FakeServer()
def FakeWrapper(write_host, db=0, **kwargs):
    return fakeredis.FakeStrictRedis(db, server=FAKE_REDIS_SERVER)
base_redis.redis.StrictRedis = FakeWrapper


from cnlib.cnredis import dp4_redis

REDIS_HOST = "mock.data-redis.cognet.tv"

def mock_get_stream_shards(stream_name="cooker-mock-iad", aws_region='us-east-1'):
    return set(["shardId-000000000001", "shardId-000000000002"])
dp4_redis.get_stream_shards = mock_get_stream_shards

class MockReadinessCooker(dp4_redis.ReadinessCookerClient):
    def __init__(self, zoo="mock", stream_name="cooker-mock-iad", shard_id="shardId-000000000001"):
        super(MockReadinessCooker, self).__init__(
            zoo, stream_name, shard_id, batch_secs=3600,
            write_host=REDIS_HOST, read_host=REDIS_HOST
        )

class MockRedshift():
    def execute(self):
        return [(5)]

    @property
    def host(self):
        return "redshift-new.cognet.tv"

class MockReadinessReport(dp4_redis.ReadinessReportClient):
    def __init__(self, zoo="mock"):
        redshift_handler = MockRedshift()
        super(MockReadinessReport, self).__init__(
            zoo, redshift_handler, write_host=REDIS_HOST, read_host=REDIS_HOST
        )


class TestReadiness(unittest.TestCase):

    def setUp(self):
        self.base_epoch = 1541793600 # 2019-11-08 20:00:00 UTC
        self.hour = 3600
        self.record_count = 5
        self.tv_count = 5

        self.mock = MockReadinessCooker()
        self.mock_report = MockReadinessReport()
        self.mock_report.input_store = self.mock
        #time.sleep(2)

    def tearDown(self):
        logger.debug("tearDown..")
        pipe = self.mock._writer.pipeline()
        for key in self.mock._reader.scan_iter("*:mock_*"):
            pipe.delete(key)

        pipe.execute()

    def test_info(self):
        ok = self.mock.record_info(self.base_epoch)
        self.assertEqual(ok, True)
        info = self.mock.get_info(self.base_epoch)
        logger.debug("info=%s", info)
        ok = self.mock.record_info(self.base_epoch)
        #self.assertEqual(ok, False)

        r = MockReadinessReport().report(self.base_epoch)
        logger.debug("r=%s", r)
        q = r.query_record_count_from_info()
        logger.debug("%s", q)

    def test_info_failure(self):
        # for this to run for real comment out FakeWrapper set in top
        # turn on real
        dp4_redis.get_stream_shards = dp4_redis._get_stream_shards

        logger.debug("1--------------------")
        dp4_redis.mock_aws_describe_failure = True
        ok = self.mock.record_info(self.base_epoch)
        self.assertEqual(ok, False)

        logger.debug("2--------------------")
        ok = self.mock.record_info(self.base_epoch)
        self.assertEqual(ok, False)

        logger.debug("3--------------------")
        dp4_redis.mock_aws_describe_failure = False
        ok = self.mock.record_info(self.base_epoch)
        self.assertEqual(ok, True)

        logger.debug("4--------------------")
        dp4_redis.mock_aws_describe_failure = True
        ok = self.mock.record_info(self.base_epoch)
        self.assertEqual(ok, True)

        logger.debug("5--------------------")
        self.mock._time_between_info_update = 0
        ok = self.mock.record_info(self.base_epoch)
        self.assertEqual(ok, True)

        # cleanup
        self.mock._time_between_info_update = 60
        dp4_redis.get_stream_shards = mock_get_stream_shards


    def test_processed(self):

        self.assertEqual(self.mock.get_processed_count(self.base_epoch, self.mock.shard_id), 0)

        (ok, set_cnt) = self.mock.record_processed(self.base_epoch, self.record_count)
        self.assertEqual(set_cnt, self.record_count)
        (ok, set_cnt) = self.mock.record_processed(self.base_epoch, 1)
        self.assertEqual(set_cnt, self.record_count + 1)
        set_cnt = self.mock.get_processed_count(self.base_epoch, self.mock.shard_id)
        self.assertEqual(set_cnt, self.record_count + 1)

    def test_tvs(self):
        (ok, set_cnt) = self.mock.record_tv_count(self.base_epoch, self.tv_count)
        self.assertEqual(set_cnt, self.tv_count)
        (ok, set_cnt) = self.mock.record_tv_count(self.base_epoch, 1)
        self.assertEqual(set_cnt, self.tv_count + 1)
        set_cnt = self.mock.get_tv_count(self.base_epoch, self.mock.shard_id)
        self.assertEqual(set_cnt, self.tv_count + 1)

    def test_report(self):

        #time.sleep(2)
        ok = self.mock.record_info(self.base_epoch)
        self.assertEqual(ok, True)

        (ok, set_cnt) = self.mock.record_processed(self.base_epoch, self.record_count)
        self.assertEqual(set_cnt, self.record_count)
        (ok, set_cnt) = self.mock.record_tv_count(self.base_epoch, self.tv_count)
        self.assertEqual(set_cnt, self.tv_count)

        r = self.mock_report.report(self.base_epoch)
        logger.debug("r=%s", r)

        for shard_id in r.shards_not_reporting:
            self.mock = MockReadinessCooker(shard_id=shard_id)
            self.mock_report.input_store = self.mock
            (ok, set_cnt) = self.mock.record_processed(self.base_epoch, self.record_count)
            self.assertEqual(set_cnt, self.record_count)
            (ok, set_cnt) = self.mock.record_tv_count(self.base_epoch, self.tv_count)
            self.assertEqual(set_cnt, self.tv_count)

        r = self.mock_report.report(self.base_epoch)
        self.assertEqual(r.all_shards_reporting, True)
        logger.debug("r=%s", r)

    def test_clean_report(self):
        r = self.mock_report.report(self.base_epoch)
        logger.debug("r=%s", r)
        self.assertEqual(r.all_shards_reporting, False)

    def test_watermark_creation(self):

        #time.sleep(2)
        ok = self.mock.record_info(self.base_epoch)
        self.assertEqual(ok, True)

        (ok, set_cnt) = self.mock.record_processed(self.base_epoch, self.record_count)
        self.assertEqual(set_cnt, self.record_count)

        (ok, set_cnt) = self.mock.record_tv_count(self.base_epoch, self.tv_count)
        self.assertEqual(set_cnt, self.tv_count)

        batch_start_epoch = self.base_epoch - self.hour
        self.mock_report.set_reported(batch_start_epoch, self.base_epoch)

        # set_reported should have created a new watermark key
        self.assertIsNotNone(
            self.mock_report.output_store._reader.hgetall(
                "reporting:mock_{}".format(self.base_epoch)
            )
        )

    def test_ready_watermark_single(self):

        batch_start_epoch = self.base_epoch - self.hour

        self.assertFalse(self.mock_report._is_ready_watermark_single(
            batch_start_epoch, self.base_epoch))

        #time.sleep(2)
        ok = self.mock.record_info(self.base_epoch)
        self.assertEqual(ok, True)

        (ok, set_cnt) = self.mock.record_processed(self.base_epoch, self.record_count)
        self.assertEqual(set_cnt, self.record_count)
        (ok, set_cnt) = self.mock.record_tv_count(self.base_epoch, self.tv_count)
        self.assertEqual(set_cnt, self.tv_count)

        # artificially make other shards ready
        r = self.mock_report.report(self.base_epoch)
        for shard_id in r.shards_not_reporting:
            mock_cooker = MockReadinessCooker(shard_id=shard_id)

            (ok, set_cnt) = mock_cooker.record_processed(self.base_epoch, self.record_count)
            self.assertEqual(set_cnt, self.record_count)

            (ok, set_cnt) = mock_cooker.record_tv_count(self.base_epoch, self.tv_count)
            self.assertEqual(set_cnt, self.tv_count)


        self.mock_report.set_reported(batch_start_epoch, self.base_epoch)

        # set_reported should have created a new watermark key
        self.assertTrue(
            self.mock_report._is_ready_watermark_single(
                batch_start_epoch, self.base_epoch
            )
        )
        reporting_keys = filter(
            lambda k: k.startswith("reporting:"),
            self.mock_report.output_store._reader.keys()
        )
        logger.debug("reporting_keys=%s", reporting_keys)
        self.assertEqual(len(reporting_keys), 1)
        logger.debug(
            "reporting_key=%s",
            self.mock_report.output_store._reader.hgetall(reporting_keys[0])
        )

    def test_ready_watermark(self):

        batch_start_epoch = self.base_epoch - self.hour

        # sanity check setup
        (is_complete, reports_to_validate) = self.mock_report._get_reports(
            batch_start_epoch, self.base_epoch)

        self.assertFalse(is_complete)
        self.assertEqual(len(reports_to_validate), 0)

        # placeholder processed records to replace with watermark
        (ok, set_cnt) = self.mock.record_processed(self.base_epoch, self.record_count)
        self.assertEqual(set_cnt, self.record_count)
        (ok, set_cnt) = self.mock.record_tv_count(self.base_epoch, self.record_count)
        self.assertEqual(set_cnt, self.tv_count)
        # create info because watermark creation needs start_ts from it
        ok = self.mock.record_info(self.base_epoch)
        self.assertEqual(ok, True)

        # artificially make other shards ready
        r = self.mock_report.report(self.base_epoch)
        for shard_id in r.shards_not_reporting:
            self.mock = MockReadinessCooker(shard_id=shard_id)
            (ok, set_cnt) = self.mock.record_processed(self.base_epoch, self.record_count)
            self.assertEqual(set_cnt, self.record_count)
            (ok, set_cnt) = self.mock.record_tv_count(self.base_epoch, self.record_count)
            self.assertEqual(set_cnt, self.tv_count)

        # create watermark
        self.mock_report.set_reported(batch_start_epoch, self.base_epoch)

        # actually validate
        (is_complete, reports_to_validate) = self.mock_report._get_reports(
            batch_start_epoch, self.base_epoch)

        self.assertTrue(is_complete)
        self.assertEqual(len(reports_to_validate), 1)

        # sanity check that larger range fails
        (is_complete, reports_to_validate) = self.mock_report._get_reports(
            batch_start_epoch, self.base_epoch + self.hour)

        self.assertFalse(is_complete)
        self.assertEqual(len(reports_to_validate), 1)

    def test_ready_processed(self):

        batch_start_epoch = self.base_epoch - self.hour

        (is_complete, reports_to_validate) = self.mock_report._get_reports(
            batch_start_epoch, self.base_epoch)
        self.assertFalse(is_complete)
        self.assertEqual(len(reports_to_validate), 0)

        # setup
        ok = self.mock.record_info(self.base_epoch)
        self.assertEqual(ok, True)

        (ok, set_cnt) = self.mock.record_processed(self.base_epoch, self.record_count)
        self.assertEqual(set_cnt, self.record_count)

        (is_complete, reports_to_validate) = self.mock_report._get_reports(
            batch_start_epoch, self.base_epoch)
        self.assertFalse(is_complete)
        self.assertEqual(len(reports_to_validate), 0)

        # artificially make other shards ready
        r = self.mock_report.report(self.base_epoch)
        for shard_id in r.shards_not_reporting:
            self.mock = MockReadinessCooker(shard_id=shard_id)
            (ok, set_cnt) = self.mock.record_processed(self.base_epoch, self.record_count)
            self.assertEqual(set_cnt, self.record_count)

        # number of reports should match number of unique epochs, which is one
        (is_complete, reports_to_validate) = self.mock_report._get_reports(
            batch_start_epoch, self.base_epoch)
        self.assertTrue(is_complete)
        self.assertEqual(len(reports_to_validate), 1)

        # sanity check that larger range fails
        (is_complete, reports_to_validate) = self.mock_report._get_reports(
            batch_start_epoch, self.base_epoch + self.hour)
        self.assertFalse(is_complete)
        self.assertEqual(len(reports_to_validate), 1)

    def test_ready_processed_daily(self):

        day_start_epoch = self.base_epoch - (24 * 60 * 60)
        day_end_epoch = self.base_epoch - 60 # minute 59

        # setup
        for available_interval_end in range(day_end_epoch, day_start_epoch, -self.hour):
            ok = self.mock.record_info(available_interval_end)
            self.assertEqual(ok, True)

            (ok, set_cnt) = self.mock.record_processed(available_interval_end, self.record_count)
            self.assertEqual(set_cnt, self.record_count)

            # artificially make other shards ready
            r = self.mock_report.report(available_interval_end)
            for shard_id in r.shards_not_reporting:
                self.mock = MockReadinessCooker(shard_id=shard_id)
                (ok, set_cnt) = self.mock.record_processed(available_interval_end,
                                                     self.record_count)
                self.assertEqual(set_cnt, self.record_count)

        # number of reports should match number of unique epochs, which is one
        (is_complete, reports_to_validate) = self.mock_report._get_reports(
            day_start_epoch, day_end_epoch)
        self.assertTrue(is_complete)
        self.assertEqual(len(reports_to_validate), 24)

        # couldn't get it to fail even with 1k n
    # def test_limit_exceeded(self):
    #     logger.debug("test_limit_exceeded..")
    #     mock = MockReadinessCooker(zoo="dtsprod", stream_name="cooker-dtsprod-iad")
    #     n = 300
    #     for i in range(n):
    #         self._cleanup(i, mock)

    #     for i in range(n):
    #         ok = mock.record_info(i)

    #     for i in range(n):
    #         self._cleanup(i, mock)

    def test_is_range_ready(self):

        interval_groups = [
            [(100, 200)],
            [(100, 150), (150, 200)],
            [(100, 100), (101, 199), (200, 200)],
            [(95, 205)],
            [(95, 105), (105, 195), (195, 205)],
            [(95, 104), (105, 194), (195, 205)],
            [(95, 120), (105, 194), (180, 205)],

            [(95, 100), (101, 199)],
            [(95, 108), (101, 199)],
        ]

        epoch_start = 100
        epoch_end = 200

        for g in interval_groups:
            gx = [dp4_redis.Interval(interval[0], interval[1]) for interval in g]
            logger.info("Testing: {}".format(g))
            self.assertTrue(self.mock_report._is_range_complete(gx, epoch_start, epoch_end))

        interval_groups = [
            [(101, 200)],
            [(101, 199)],
            [(108, 205)],
            [(88, 99)],
            [(88, 100)],
            [(199, 200)],
            [(200, 205)],
            [(210, 205)],
            [(210, 215)],
        ]

        for g in interval_groups:
            gx = [dp4_redis.Interval(interval[0], interval[1]) for interval in g]
            logger.info("Testing: {}".format(g))
            self.assertFalse(self.mock_report._is_range_complete(gx, epoch_start, epoch_end))

        epoch_start = 105
        epoch_end = 195

        interval_groups = [
            [(100, 200)],
        ]
        for g in interval_groups:
            gx = [dp4_redis.Interval(interval[0], interval[1]) for interval in g]
            logger.info("Testing: {}".format(g))
            self.assertTrue(self.mock_report._is_range_complete(gx, epoch_start, epoch_end))

    def test_mix_watermark_processed(self):
        day_start_epoch = self.base_epoch - (24 * 60 * 60)
        day_end_epoch = self.base_epoch

        # setup
        for available_interval_end in range(day_end_epoch, day_start_epoch,
                                            -self.hour):
            ok = self.mock.record_info(available_interval_end)
            self.assertTrue(ok)

            (ok, set_cnt) = self.mock.record_processed(available_interval_end, self.record_count)
            self.assertEqual(set_cnt, self.record_count)
            (ok, set_cnt) = self.mock.record_tv_count(available_interval_end, self.tv_count)
            self.assertEqual(set_cnt, self.tv_count)

            # artificially make other shards ready
            r = self.mock_report.report(available_interval_end)
            for shard_id in r.shards_not_reporting:
                self.mock = MockReadinessCooker(shard_id=shard_id)
                (ok, set_cnt) = self.mock.record_processed(available_interval_end,
                                                     self.record_count)
                self.assertEqual(set_cnt, self.record_count)

        # set watermarking for the earlier half of the period
        self.mock_report.set_reported(day_start_epoch, int((day_end_epoch + day_start_epoch) / 2))

        (is_complete, reports_to_validate) = self.mock_report._get_reports(
            day_start_epoch, day_end_epoch)
        self.assertTrue(is_complete)
        self.assertGreaterEqual(len(reports_to_validate), 1)

        # expire info keys for first half
        for available_interval_end in range(day_start_epoch,
                                            int((day_end_epoch + day_start_epoch) / 2),
                                            self.hour):
            self.mock._writer.delete("{}:{}_{}".format(
                self.mock.info_prefix, self.mock.zoo, available_interval_end))

        (is_complete, reports_to_validate) = self.mock_report._get_reports(
            day_start_epoch, day_end_epoch)
        self.assertTrue(is_complete)
        self.assertGreaterEqual(len(reports_to_validate), 1)



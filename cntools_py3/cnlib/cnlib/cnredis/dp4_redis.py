
from cnlib import log
logger = log.getLogger(__name__)
from ..cnredis import BaseRedis, Clusters, Databases

import boto3
import os
import time
from collections import namedtuple

from datetime import datetime

# scale: [0, 1]
RECORD_DIFFERENCE_THRESHOLD_PCT = float(
    os.getenv("RECORD_DIFFERENCE_THRESHOLD_PCT", 0.005))
TV_DIFFERENCE_THRESHOLD_PCT = float(
    os.getenv("TV_DIFFERENCE_THRESHOLD_PCT", 0.005))

REDIS_SHARD_COUNT_SIZE = 1500

mock_aws_describe_failure = False

class RedshiftClusterNotFound(Exception):
    pass

def epoch_to_string(ts, fmt='%Y-%m-%dT%H:%M:%SZ'):
    if ts is None:
        return 'None'
    return datetime.utcfromtimestamp(int(ts)).strftime(fmt)

# common representation of report statistics for both reporting (watermark)
# hash keys and readiness reports (Info), which expire after 14 days
class ReportSummary(namedtuple(
        "ReportSummary", [
            "type", "batch_start_ts", "batch_end_ts", "record_count", "commercial_record_count", "tv_count"
        ]
    )
):
    def __str__(self):
        return (
            "ReportSummary(type={} batch_start_ts={} batch_start={} "
            "batch_end_ts={} batch_end={} record_count={} commercial_record_count={} tv_count={})".format(
                self.type, self.batch_start_ts, epoch_to_string(self.batch_start_ts),
                self.batch_end_ts, epoch_to_string(self.batch_end_ts),
                self.record_count, self.commercial_record_count, self.tv_count
            )
        )

class Interval(namedtuple("Interval", ["start_ts", "end_ts"])):
    def __str__(self):
        return "Interval(start_ts={} start={} - end_ts={} end={})".format(
            self.start_ts, epoch_to_string(self.start_ts),
            self.end_ts, epoch_to_string(self.end_ts)
        )

class Info():
    def __init__(self, values):
        self.shards=set([])
        self.start_ts = 0
        self.end_ts = 0
        self.batch_secs = 0
        logger.debug("values={}".format(values))
        if not values:
            logger.warning("No values to set Info!")
            return

        shards = values['shards'].split(',')
        self.shards = set(shards)
        self.start_ts = int(values['start_ts'])
        self.batch_secs = int(values['batch_secs'])
        self.end_ts = self.start_ts + self.batch_secs
        try:
            self.created = int(values['created'])
        except:
            self.created = time.time()
        try:
            self.aws_error = values['aws_error'] == 'True'
        except:
            self.aws_error = False

    def __str__(self):
        return "Info(shards={} start_ts={} end_ts={} batch_secs={} aws_error={} created={})".format(
            len(self.shards), self.start_ts, self.end_ts, self.batch_secs, self.aws_error, epoch_to_string(self.created))

class Readiness(BaseRedis):

    processed_prefix = "records"
    reporting_prefix = "reporting"
    commercial_processed_prefix = "commercial"
    tvs_prefix = "tvs"
    info_prefix = "info"

    def __init__(self, zoo,
                 decode_responses=False,
                 write_host=Clusters.DATA['write'],
                 read_host=Clusters.DATA['read'],
                 retry_on_timeout=False):

        BaseRedis.__init__(self, write_host, read_host, Databases.DP4,
                           decode_responses=decode_responses,
                           retry_on_timeout=retry_on_timeout)

        self.aws_region = os.environ.get('AWS_REGION',
                                         boto3.session.Session().region_name)
        if not self.aws_region:
            self.aws_region = 'us-east-1'

        self.zoo = zoo
        self.expire_processed_keys_in = 60 * 60 * 24 * 14 # 14 days.
        self.expire_info_keys_in = 60 * 60 * 24 * 14 # 14 days.

    def __str__(self):
        return "class=Readiness zoo={}".format(
            self.zoo)

    def _build_processed_key(self, batch_end_epoch, shard_id):
        return "{}_{}_{}".format(self.zoo, batch_end_epoch, shard_id)

    def _build_info_key(self, batch_end_epoch):
        return "{}_{}".format(self.zoo, batch_end_epoch)

    """ shard count """
    def remove_info(self, batch_end_epoch):
        prefix = self.info_prefix
        key = self._build_info_key(batch_end_epoch)
        self.delete(key, prefix)

    def get_info(self, batch_end_epoch):
        prefix = self.info_prefix
        key = self._build_info_key(batch_end_epoch)
        values = self.get(key, prefix)
        logger.debug("batch_end_epoch={} key={} prefix={} values={}".format(
                     batch_end_epoch, key, prefix, values))
        if values:
            return Info(values)
        return None

    def get_shards(self, batch_end_epoch):
        info = self.get_info(batch_end_epoch)
        return info.shards

    """ processed count """
    def get_processed_count(self, batch_end_epoch, shard_id):
        prefix = self.processed_prefix
        key = self._build_processed_key(batch_end_epoch, shard_id)
        prefixed_key = '{}:{}'.format(prefix, key)
        value = self._reader.get(prefixed_key)
        logger.debug("prefixed_key=%s value=%s", prefixed_key, value)
        try:
            return int(value)
        except TypeError:
            return 0

    def get_commercial_processed_count(self, batch_end_epoch, shard_id):
        prefix = self.commercial_processed_prefix
        key = self._build_processed_key(batch_end_epoch, shard_id)
        prefixed_key = '{}:{}'.format(prefix, key)
        value = self._reader.get(prefixed_key)
        logger.debug("prefixed_key=%s value=%s", prefixed_key, value)
        try:
            return int(value)
        except TypeError:
            return 0

    def get_tv_count(self, batch_end_epoch, shard_id):
        prefix = self.tvs_prefix
        key = self._build_processed_key(batch_end_epoch, shard_id)
        prefixed_key = '{}:{}'.format(prefix, key)
        value = self._reader.get(prefixed_key)
        logger.debug("prefixed_key=%s value=%s", prefixed_key, value)
        try:
            return int(value)
        except TypeError:
            return 0


class ReadinessReport:
    def __init__(self, batch_end_epoch, zoo):
        self.all_shards_reporting = False
        self.record_count = 0
        self.commercial_record_count = 0
        self.reporting_shards_count = 0
        self.commercial_shards_not_reporting = set([])
        self.shards_not_reporting = set([])
        self.batch_end_epoch = batch_end_epoch
        self.info = None
        self.zoo = zoo
        self.tv_count = 0

    def __str__(self):
        return "ReadinessReport(batch_end_epoch={} {} all_shards_reporting={} records={} commercial_records={} tvs={} reporting_shards_count={} shards_not_reporting={} commercial_shards_not_reporting={} info={})".format(
            self.batch_end_epoch,
            epoch_to_string(self.batch_end_epoch),
            self.all_shards_reporting,
            self.record_count,
            self.commercial_record_count,
            self.tv_count,
            self.reporting_shards_count,
            self.shards_not_reporting,
            self.commercial_shards_not_reporting,
            self.info)

    @staticmethod
    def query_record_count():
        q = ("""SELECT count(*) FROM detection.viewing_content_firehose
WHERE session_start >= %s
AND session_start < %s
AND fk_zoo_id in (
SELECT zoo_id FROM detection.zoo WHERE zoo = %s
 );""")
        return q

    @staticmethod
    def query_commercial_count():
        q = ("""SELECT count(*) FROM detection.viewing_commercials_firehose
    WHERE session_start >= %s
    AND session_start < %s
    AND fk_zoo_id in (
    SELECT zoo_id FROM detection.zoo WHERE zoo = %s
     );""")
        return q

    @staticmethod
    def query_tv_count():
        q = (""" SELECT SUM(tv_count) FROM (
SELECT COUNT(distinct fk_tvid) as tv_count, to_char(session_start, 'YYYY-MM-DD HH24') FROM detection.viewing_content_firehose
WHERE session_start >= %s
AND session_start < %s
AND fk_zoo_id in (
SELECT zoo_id FROM detection.zoo WHERE zoo = %s
 ) group by to_char(session_start, 'YYYY-MM-DD HH24')
);""")
        return q

    def query_record_count_from_info(self):
        if not self.info:
            logger.info("%s can't build redshift_query..")
            return None

        arg_list = [
            epoch_to_string(self.info.start_ts),
            epoch_to_string(self.info.end_ts),
            "control-zoo-{}.tvinteractive.tv".format(self.zoo)
        ]

        return (self.query_record_count(), arg_list)

class ReadinessReportClient(object):
    CLUSTER_MAP = {
        "redshift-warm-live": Databases.DP4_WARM_WATERMARK,
        "redshift-new": Databases.DP4_EVOLUTION_WATERMARK,
        "redshiftstage": Databases.DP4_STAGE,
    }

    def __init__(self, zoo, redshift_zoo, redshift_handler=None, decode_responses=False,
                 write_host=Clusters.DATA['write'],
                 read_host=Clusters.DATA['read']):
        self.zoo = zoo
        self.redshift_zoo = redshift_zoo
        self.redshift_handler = redshift_handler
        self.expire_reporting_keys_in = 60 * 60 * 24 * 730 # 2 years

        self.input_store = Readiness(zoo, decode_responses,
                                     write_host=write_host, read_host=read_host)
        self.output_store = self._set_up_output_store(
            redshift_handler, decode_responses, write_host, read_host
        )

    def _build_reporting_key(self, batch_end_epoch):
        return "{}_{}".format(self.zoo, batch_end_epoch)

    def _set_up_output_store(
            self, redshift_handler, decode_responses,
            write_host=Clusters.DATA['write'],
            read_host=Clusters.DATA['read']):

        redis_db = None
        for cluster, db in list(ReadinessReportClient.CLUSTER_MAP.items()):
            if redshift_handler.host.startswith(cluster):
                redis_db = db
                break

        if not redis_db:
            raise RedshiftClusterNotFound(
                "Cluster not supported: cluster={}".format(redshift_handler.host))

        logger.info("output db={}".format(redis_db))

        return BaseRedis(write_host, read_host, redis_db, decode_responses=decode_responses)

    def __str__(self):
        return "class=ReadinessReportClient zoo={}".format(
            self.zoo)

    def report(self, batch_end_epoch):

        logger.debug("%s batch_end_epoch=%d report..", self.input_store, batch_end_epoch)
        r = ReadinessReport(batch_end_epoch, self.redshift_zoo)

        info = self.input_store.get_info(batch_end_epoch)

        if not info:
            logger.info("%s did not get info..", self.input_store)
            return r

        r.info = info
        r.reporting_shards_count = 0

        records_keys = [
            "{}:{}".format(
                self.input_store.processed_prefix,
                self.input_store._build_processed_key(
                    batch_end_epoch,
                    shard_id)) for shard_id in info.shards]

        commercial_records_keys = [
            "{}:{}".format(
                self.input_store.commercial_processed_prefix,
                self.input_store._build_processed_key(
                    batch_end_epoch,
                    shard_id)) for shard_id in info.shards]

        tvs_keys = [
            "{}:{}".format(
                self.input_store.tvs_prefix,
                self.input_store._build_processed_key(
                    batch_end_epoch,
                    shard_id)) for shard_id in info.shards]

        try:
            records_results = self.input_store._reader.mget(*records_keys)
        except Exception as e:
            logger.exception(
                "%s zoo=%s end=%s e=%s", self.input_store, self.zoo,
                batch_end_epoch, e)
        finally:
            logger.debug(
                "%s records zoo=%s end=%s results=%s", self.input_store, self.zoo,
                batch_end_epoch,
                [(key, count)
                    for key, count in sorted(zip(records_keys, records_results))])

        r.shards_not_reporting = set([
            shard_id
            for shard_id, result in zip(info.shards, records_results)
            if result is None])

        try:
            commercial_records_results = self.input_store._reader.mget(*commercial_records_keys)
        except Exception as e:
            logger.exception(
                "%s zoo=%s end=%s e=%s", self.input_store, self.zoo,
                batch_end_epoch, e)
        finally:
            logger.debug(
                "%s records zoo=%s end=%s results=%s", self.input_store, self.zoo,
                batch_end_epoch,
                [(key, count)
                 for key, count in sorted(zip(commercial_records_keys, commercial_records_results))])

        r.commercial_shards_not_reporting = set([
            shard_id
            for shard_id, result in zip(info.shards, commercial_records_results)
            if result is None])

        try:
            tvs_results = self.input_store._reader.mget(*tvs_keys)
        except Exception as e:
            logger.exception(
                "%s tvs zoo=%s end=%s e=%s", self.input_store, self.zoo,
                batch_end_epoch, e)
        finally:
            logger.debug(
                "%s zoo=%s end=%s results=%s", self.input_store, self.zoo,
                batch_end_epoch,
                [(key, count)
                    for key, count in sorted(zip(tvs_keys, tvs_results))])

        r.reporting_shards_count += len(
            [result for result in records_results if result is not None])
        r.record_count += sum([int(result) for result in records_results if result is not None])
        r.commercial_record_count += sum([int(result) for result in commercial_records_results if result is not None])
        r.tv_count += sum([int(result) for result in tvs_results if result is not None])
        r.all_shards_reporting = (r.reporting_shards_count >= len(info.shards))

        logger.debug(
            "%s zoo=%s end=%s reporting_shards=%s record_count=%s commercial_count=%s"
            "tv_count=%s all_shards_reporting=%s shards_not_reporting=%s",
            self.input_store, self.zoo, batch_end_epoch,
            r.reporting_shards_count, r.record_count, r.commercial_record_count, r.tv_count,
            r.all_shards_reporting, r.shards_not_reporting)

        return r

    """
    look through all batch ends and report about them
    returns a list of reports in ascending by epoch order.
    limit will keep only the last N reports.
    """
    def report_all(self, limit=REDIS_SHARD_COUNT_SIZE):
        logger.debug("%s report_all..", self.input_store)

        reports = []
        epochs = []

        for key in self.input_store._reader.scan_iter(
                'info:{}_*'.format(self.zoo), count=REDIS_SHARD_COUNT_SIZE):

            epoch = int(key.split('_')[1])
            epochs.append(epoch)

        epochs.sort()
        epochs = epochs[-limit:]

        for epoch in epochs:
            key = '{}:{}'.format(self.input_store.info_prefix,
                                 self.input_store._build_info_key(epoch))
            logger.debug("key=%s", key)
            try:
                r = self.report(epoch)
                reports.append(r)
            except:
                logger.exception("report_all")

        for r in reports:
            logger.info("r=%s", r)

        return reports

    @staticmethod
    def _is_range_complete(available_intervals, epoch_start, epoch_end):
        """
        Given a list of intervals and start and end times, determine whether the
        full range between start and end times is fully covered by the list of
        intervals.
        """
        # Sort by the start time of each interval
        intervals_by_start = sorted(available_intervals, key=lambda x: x.start_ts)

        range_remaining_start, range_remaining_end = epoch_start, epoch_end

        #logger.debug(
        #    "Checking range completion: range_start={} range_end={} "
        #    "intervals_by_start=\n{}".format(
        #    range_remaining_start, range_remaining_end,
        #    "\t\n".join([str(i) for i in intervals_by_start])))

        for i in intervals_by_start:
            interval_start, interval_end = i.start_ts, i.end_ts

            if interval_start > interval_end:
                logger.warning(
                    "interval start greater than end, skipping: "
                    "start_ts=%s start=%s end_ts=%s end=%s",
                    interval_start, epoch_to_string(interval_start),
                    interval_end, epoch_to_string(interval_end)
                )
                continue

            if interval_start > range_remaining_start:
                # we've essentially skipped an earlier interval; fail
                logger.info(
                    "gap in time span encountered, range incomplete: "
                    "gap_start_ts=%s gap_start=%s gap_end_ts=%s gap_end=%s",
                    range_remaining_start, epoch_to_string(range_remaining_start),
                    interval_start, epoch_to_string(interval_start)
                )
                break

            # If interval is within the requested range, trim the starting
            # part of the remaining range to what remains to be checked
            if (interval_start <= range_remaining_end
                    and interval_end >= range_remaining_start):
                range_remaining_start = max(range_remaining_start, interval_end + 1)
                range_remaining_start = min(range_remaining_start, range_remaining_end)
            elif (interval_start > range_remaining_end
                    and interval_end > range_remaining_end):
                break

        range_complete = range_remaining_start == range_remaining_end
        if not range_complete:
            logger.info(
                "range incomplete, range remaining to be covered: "
                "start_ts=%s start=%s end_ts=%s end=%s",
                range_remaining_start, epoch_to_string(range_remaining_start),
                range_remaining_end, epoch_to_string(range_remaining_end)
            )

        return range_complete

    def _get_reports(self, epoch_start, epoch_end):

        is_complete = False
        ready_intervals = []
        report_summaries = dict()

        logger.debug(
            "obtaining readiness data for: report_start_ts=%s (%s) report_end_ts=%s (%s)",
            epoch_start, epoch_to_string(epoch_start),
            epoch_end, epoch_to_string(epoch_end)
        )

        for prefix, store in [
                (Readiness.reporting_prefix, self.output_store),
                (Readiness.processed_prefix, self.input_store)
        ]:
            for key in store._reader.scan_iter(
                    '{}:{}*'.format(prefix, self.zoo), count=REDIS_SHARD_COUNT_SIZE):

                try:
                    ready_end_ts = int(key.split("_")[1])
                except KeyError:
                    logger.warning(
                        "epoch not found in key, skipping: store={} key={}".format(
                        store, key))
                    continue

                if ready_end_ts in report_summaries:
                    continue

                if ready_end_ts <= epoch_start:
                    continue

                ready_start_ts = None

                if key.startswith(Readiness.reporting_prefix):
                    watermark_map = store._reader.hgetall(key)
                    try:
                        ready_start_ts = int(watermark_map["start_ts"])
                    except (KeyError, TypeError) as e:
                        logger.warning(
                            "start_ts field invalid, deleting/skipping: key={}".format(key)
                        )
                        store.delete(key)
                        continue

                    # ensure ranges overlap, excluding whether
                    # ready range start == desired end
                    range_overlaps = (epoch_start <= ready_end_ts
                        and ready_start_ts < epoch_end)

                    if not range_overlaps:
                        continue

                    try:
                        record_count = int(watermark_map["record_count"])
                    except (KeyError, TypeError) as e:
                        logger.warning(
                            "record_count field invalid, deleting/skipping: key={}".format(key)
                        )
                        store.delete(key)
                        continue

                    try:
                        tv_count = int(watermark_map["tv_count"])
                    except (KeyError, TypeError) as e:
                        logger.warning(
                            "tv_count field invalid, deleting/skipping: key={}".format(key)
                        )
                        store.delete(key)
                        continue

                    report_summaries[ready_end_ts] = ReportSummary(
                        "watermark",
                        ready_start_ts, ready_end_ts,
                        record_count, tv_count
                    )

                elif key.startswith(Readiness.processed_prefix):
                    report = self.report(ready_end_ts)
                    info = report.info

                    if not report.info:
                        logger.debug("no info available, skipping: end_ts={}".format(ready_end_ts))
                        continue

                    if not report.all_shards_reporting:
                        logger.info("not all shards reporting, skipping: end_ts={}".format(ready_end_ts))
                        continue

                    ready_start_ts = info.start_ts

                    # ensure ranges overlap, excluding whether
                    # ready range start == desired end
                    range_overlaps = (epoch_start <= ready_end_ts
                        and ready_start_ts < epoch_end)

                    #logger.debug(
                    #    "considering if ready: {}-{}, range:{}-{}, overlaps={}".format(
                    #    ready_start_ts, ready_end_ts,
                    #    epoch_start, epoch_end, range_overlaps))

                    if not range_overlaps:
                        continue

                    report_summaries[ready_end_ts] = ReportSummary(
                        "concrete",
                        ready_start_ts, ready_end_ts,
                        report.record_count, report.tv_count
                    )
                else:
                    logger.warning("unexpected key prefix, skipping: {}".format(key))
                    continue

                if not ready_start_ts:
                    continue

                ready_intervals.append(Interval(ready_start_ts, ready_end_ts))

                if ReadinessReportClient._is_range_complete(
                        ready_intervals, epoch_start, epoch_end):

                    is_complete = True
                    break

        intervals_by_start = sorted(ready_intervals, key=lambda x: x[0])
        logger.debug(
            "ready intervals by start=\n\t%s",
            "\n\t".join([str(i) for i in intervals_by_start])
        )

        return (is_complete, report_summaries)

    def _is_ready_watermark_single(self, epoch_start, epoch_end):
        key = self._build_reporting_key(epoch_end)
        if not self.output_store.exists(key, Readiness.reporting_prefix):
            logger.debug(
                "watermark check failed, key dne: store={} start={} end={}".format(
                self.output_store, epoch_start, epoch_end))
            return False

        info = self.input_store.get_info(epoch_end)

        if not info:
            logger.debug(
                "watermark check failed, info dne: store={} start={} end={}".format(
                self.output_store, epoch_start, epoch_end))
            return False

        return info.batch_secs == epoch_end - epoch_start

    def _check_record_counts(self, epoch_start, epoch_end, reports):
        """
        compare record counts between report and source table in redshift
        """
        expected_record_count = sum(r.record_count for _, r in list(reports.items()))
        query = ReadinessReport.query_record_count()
        query_args = (
            epoch_to_string(epoch_start),
            epoch_to_string(epoch_end),
            "control-zoo-{}.tvinteractive.tv".format(self.redshift_zoo)
        )
        try:
            query_results = self.redshift_handler(
                query,
                q_args=query_args,
                commit=False, fetch=True)

        except (TypeError, AttributeError) as e:
            logger.exception("Redshift handler needs to implement __call__(): {}".format(e))
            return False

        actual_record_count = query_results[0][0]
        record_diff_pct = (expected_record_count - actual_record_count) / max(expected_record_count, 1)

        logger.info(
            "Record count comparison: expected={} actual={} diff_pct={} threshold_pct={} "
            "query_args={} results={} reports=\n{}".format(
            expected_record_count, actual_record_count, record_diff_pct,
            RECORD_DIFFERENCE_THRESHOLD_PCT, query_args, query_results,
            "\t\n".join([str(r) for k, r in sorted(reports.items())])))

        if record_diff_pct > RECORD_DIFFERENCE_THRESHOLD_PCT:
            logger.error(
                "Difference between expected={} and actual={} record counts "
                "exceeds threshold={}".format(
                expected_record_count, actual_record_count,
                RECORD_DIFFERENCE_THRESHOLD_PCT))
            return False

        if record_diff_pct < 0:
            logger.warning(
                "More records in Redshift than recorded in Redis. Possible "
                "causes: resharding led to duplicate records, or placeholder keys "
                "expected={} actual={} pct_diff={}".format(
                expected_record_count, actual_record_count, record_diff_pct))

        return True

    def _check_commercial_counts(self, epoch_start, epoch_end, reports):
        """
        compare record counts between report and source table in redshift
        """
        expected_record_count = sum(r.record_count for _, r in list(reports.items()))
        query = ReadinessReport.query_commercial_count()
        query_args = (
            epoch_to_string(epoch_start),
            epoch_to_string(epoch_end),
            "control-zoo-{}.tvinteractive.tv".format(self.redshift_zoo)
        )
        try:
            query_results = self.redshift_handler(
                query,
                q_args=query_args,
                commit=False, fetch=True)

        except (TypeError, AttributeError) as e:
            logger.exception("Redshift handler needs to implement __call__(): {}".format(e))
            return False

        actual_record_count = query_results[0][0]
        record_diff_pct = (expected_record_count - actual_record_count) / max(expected_record_count, 1)

        logger.info(
            "Record count comparison: expected={} actual={} diff_pct={} threshold_pct={} "
            "query_args={} results={} reports=\n{}".format(
                expected_record_count, actual_record_count, record_diff_pct,
                RECORD_DIFFERENCE_THRESHOLD_PCT, query_args, query_results,
                "\t\n".join([str(r) for k, r in sorted(reports.items())])))

        if record_diff_pct > RECORD_DIFFERENCE_THRESHOLD_PCT:
            logger.error(
                "Difference between expected={} and actual={} record counts "
                "exceeds threshold={}".format(
                    expected_record_count, actual_record_count,
                    RECORD_DIFFERENCE_THRESHOLD_PCT))
            return False

        if record_diff_pct < 0:
            logger.warning(
                "More records in Redshift than recorded in Redis. Possible "
                "causes: resharding led to duplicate records, or placeholder keys "
                "expected={} actual={} pct_diff={}".format(
                    expected_record_count, actual_record_count, record_diff_pct))

        return True

    def _check_tv_counts(self, epoch_start, epoch_end, reports):
        expected_tv_count = sum(r.tv_count for _, r in list(reports.items()))
        query = ReadinessReport.query_tv_count()
        query_args = (
            epoch_to_string(epoch_start),
            epoch_to_string(epoch_end),
            "control-zoo-{}.tvinteractive.tv".format(self.redshift_zoo)
        )
        try:
            query_results = self.redshift_handler(
                query,
                q_args=query_args,
                commit=False, fetch=True)

        except (TypeError, AttributeError) as e:
            logger.exception("Redshift handler needs to implement execute(): {}".format(e))
            return False

        actual_tv_count = query_results[0][0]
        tv_diff_pct = (expected_tv_count - actual_tv_count) / expected_tv_count

        logger.info(
            "TV count comparison: expected={} actual={} diff_pct={} threshold_pct={} "
            "query_args={} results={} reports=\n{}".format(
            expected_tv_count, actual_tv_count, tv_diff_pct,
            TV_DIFFERENCE_THRESHOLD_PCT, query_args, query_results,
            "\t\n".join([str(r) for k, r in sorted(reports.items())])))

        if tv_diff_pct > TV_DIFFERENCE_THRESHOLD_PCT:
            logger.error(
                "Difference between expected={} and actual={} tv counts "
                "exceeds threshold={}".format(
                expected_tv_count, actual_tv_count,
                TV_DIFFERENCE_THRESHOLD_PCT))
            return False

        if tv_diff_pct < 0:
            logger.warning(
                "More TVs in Redshift than recorded in Redis. Possible "
                "causes: resharding led to duplicate records, or placeholder keys "
                "expected={} actual={} pct_diff={}".format(
                expected_tv_count, actual_tv_count, tv_diff_pct))

        return True

    def _check_reports(self, epoch_start, epoch_end, reports):
        return (self._check_tv_counts(epoch_start, epoch_end, reports)
            and self._check_record_counts(epoch_start, epoch_end, reports))

    def _check_commercial_reports(self, epoch_start, epoch_end, reports):
        return (self._check_tv_counts(epoch_start, epoch_end, reports)
                and self._check_record_counts(epoch_start, epoch_end, reports)
                and self._check_commercial_counts(epoch_start, epoch_end, reports))

    def is_ready(self, epoch_start, epoch_end):
        """
        Check if watermark exists; otherwise, check deeper
        Then, compare record and tv counts
        """
        logger.info(
            "checking DP4 data readiness: start={} end={}".format(
            epoch_start, epoch_end))

        if not self.redshift_handler:
            logger.warning("can not do is_ready without redshift_handler!")
            return False

        watermark_ready = self._is_ready_watermark_single(epoch_start, epoch_end)
        if watermark_ready:
            logger.info(
                "data ready (watermark): store={} start={} end={}".format(
                self.output_store, epoch_start, epoch_end))
            return True

        is_complete, report_summaries = self._get_reports(epoch_start, epoch_end)

        if not is_complete:
            msg = "\t\n".join([str(r) for k, r in sorted(report_summaries.items())])
            logger.warning("not all data ready. reports:\n{}".format(msg))
            return False

        return self._check_reports(epoch_start, epoch_end, report_summaries)

    def set_reported(self, epoch_range_start, epoch_range_end, metadata={}):
        """
        Delete the per-shard record counts for the time range, and replace
        with a key with properties that summarize the group (watermark)
        """
        # epoch: Info
        epoch_infos = dict()
        output_maps = dict()
        watermark_exists = False

        for input_key in self.input_store._reader.scan_iter(
                '*:{}*'.format(self.zoo), count=REDIS_SHARD_COUNT_SIZE):

            # exclude keys that don't start with "records:" or "tvs:"
            if not any([input_key.startswith(prefix) for prefix in {
                    Readiness.processed_prefix, Readiness.tvs_prefix}]):
                continue

            try:
                epoch = int(input_key.split("_")[1])
                shard_id = input_key.split("_")[2]
            except Exception as e:
                logger.warning("watermarking, error parsing source key: key={} error={}".format(input_key, e))
                continue

            # Consider keys whose epochs are within range.
            # Since key describes end epoch, those keys whose end epochs are
            # after the range end but whose starts are before it should
            # still be considered.
            if not (epoch_range_start < epoch <= epoch_range_end):
                continue

            # reuse info if possible
            if not epoch in epoch_infos:
                info = self.input_store.get_info(epoch)
            else:
                info = epoch_infos[epoch]

            if not info:
                continue

            if not info.start_ts < epoch_range_end:
                continue

            # if watermark/reporting key exists, don't overwrite
            output_key = self._build_reporting_key(epoch)
            output_prefix = Readiness.reporting_prefix
            ## TODO: Possible for multiple jobs to want to set watermark.
            ##       Multiple jobs can succeed their source data checks and
            ##       both be waiting to write the watermark after query is done.
            ##       Proper fix might involve locking the key while writing;
            ##       if a lock is active, don't write it.
            if self.output_store.exists(output_key, prefix=output_prefix):
                full_output_key = "{}:{}".format(output_prefix, output_key)
                logger.info(
                    "watermark already exists, not overwriting: key={}".format(full_output_key)
                )
                watermark_exists = True
                break

            # get or create hash map
            if epoch in output_maps:
                hash_map = output_maps[epoch]
            else:
                hash_map = output_maps[epoch] = dict(start_ts=info.start_ts)

            # get which count to modify
            if input_key.startswith(Readiness.processed_prefix):
                output_field = "record_count"
            else: # input_key.startswith(Readiness.tvs_prefix):
                output_field = "tv_count"

            # increment or initialize the count
            count = int(self.input_store._reader.get(input_key))
            if output_field in hash_map:
                hash_map[output_field] += count
            else:
                hash_map[output_field] = count


        if watermark_exists == False:
            output_pipe = self.output_store._writer.pipeline()
            for epoch, hash_map in list(output_maps.items()):
                output_key = self._build_reporting_key(epoch)
                output_prefix = Readiness.reporting_prefix

                # add remaining hash map keys
                hash_map.update({"_client_{}".format(k): v for k, v in list(metadata.items())})
                hash_map["_created_ts"] = epoch_to_string(int(time.time()))

                logger.info(
                    "creating watermark: key=%s:%s value=%s",
                    output_prefix, output_key, hash_map
                )

                self.output_store.save(output_key, hash_map, prefix=output_prefix,
                                       pipeline=output_pipe)
                self.output_store.expire(output_key, self.expire_reporting_keys_in,
                                         output_prefix, pipeline=output_pipe)

            output_pipe.execute()


def _get_stream_shards(stream_name, aws_region='us-east-1'):

    logger.info("stream_name=%s get_stream_shards..", stream_name)
    client = boto3.session.Session().client('kinesis', region_name=aws_region)

    if mock_aws_describe_failure:
        return set([])

    active_shards = set([])
    all_shards = set([])

    n_shards = 100
    shard_id = '0'

    while n_shards >= 100:

        logger.debug("shard_id=%s", shard_id)

        try:
            response = client.describe_stream(StreamName=stream_name, Limit=100, ExclusiveStartShardId=shard_id)
        except client.exceptions.LimitExceededException:
            logger.error("get_stream_shards client LimitExceededException")
            return set([])

        description = response['StreamDescription']
        shards = description['Shards']
        n_shards =len(shards)

        for shard in shards:
            shard_id = shard['ShardId']
            all_shards.add(shard_id)
            try:
                shard['SequenceNumberRange']['EndingSequenceNumber']
            except KeyError:
                active_shards.add(shard_id)

    logger.debug("shards=%d active_shards=%d", len(shards), len(active_shards))
    return active_shards
get_stream_shards = _get_stream_shards


class ReadinessCookerClient(Readiness):

    def __init__(self, zoo, stream_name, shard_id, batch_secs=3600,
                 write_host=Clusters.DATA['write'],
                 read_host=Clusters.DATA['read'],
                 decode_responses=True):
        Readiness.__init__(self, zoo, write_host=write_host, read_host=read_host, decode_responses=decode_responses)
        self.stream_name = stream_name
        self.shard_id = shard_id
        self.batch_secs = batch_secs
        self._time_between_info_update = 60

    def __str__(self):
        return "class=ReadinessCookerClient zoo={} stream_name={} shard_id={}".format(
            self.zoo, self.stream_name, self.shard_id)

    # report the number of shards found.
    # don't report if already exists and set within the last minute
    # returns true if set, false if not set because already there (for debugging)
    def record_info(self, batch_end_epoch):

        logger.info("%s batch_end_epoch=%d record_shard_count..", self,
            batch_end_epoch)

        info = self.get_info(batch_end_epoch)
        logger.debug("info=%s", info)
        if info:
            logger.debug("%s %s _time_between_info_update=%d", not info.aws_error,
                int(time.time()) - info.created < self._time_between_info_update, self._time_between_info_update)
        if info and not info.aws_error and int(time.time()) - info.created < self._time_between_info_update:
            logger.info("info already set!")
            return True

        key = self._build_info_key(batch_end_epoch)
        prefix = self.info_prefix

        aws_describe_shards_error = False
        active_shards = get_stream_shards(self.stream_name, self.aws_region)
        if not active_shards:
            aws_describe_shards_error = True

        if aws_describe_shards_error and info and not info.aws_error:
            logger.info("don't overwrite good with bad")
            return True

        # logger.debug("response=%s", response)
        # logger.debug("%d shards=%s ", len(shards), shards)
        logger.debug("shard_cnt=%s ", len(active_shards))

        start_ts = batch_end_epoch - self.batch_secs
        if start_ts < 0:
            start_ts = 0

        values = {
            'shards':','.join(active_shards),
            'start_ts':start_ts,
            'batch_secs':self.batch_secs,
            'created':int(time.time()),
            'aws_error':aws_describe_shards_error,
        }

        ok = self.set(key, values, prefix)
        logger.debug("ok=%s", ok)
        self.expire(key, self.expire_info_keys_in, prefix)

        return ok and not aws_describe_shards_error

    def record_processed(self, batch_end_epoch, record_count):
        logger.info("%s batch_end_epoch=%d record_count=%d record_processed..", self,
            batch_end_epoch, record_count)

        previous_cnt = self.get_processed_count(batch_end_epoch, self.shard_id)
        logger.debug("previous_cnt=%d", previous_cnt)
        prefix = self.processed_prefix
        key = self._build_processed_key(batch_end_epoch, self.shard_id)
        prefixed_key = '{}:{}'.format(prefix, key)
        set_cnt = record_count + previous_cnt
        logger.debug("set_cnt=%d prefixed_key=%s", set_cnt, prefixed_key)
        ok = self._writer.set(prefixed_key, set_cnt)
        self.expire(key, self.expire_processed_keys_in, prefix)

        return (ok, set_cnt)

    def record_commercial_processed(self, batch_end_epoch, commercial_count):
        logger.info("%s batch_end_epoch=%d commercial_record_count=%d commercial_record_processed..", self,
                    batch_end_epoch, commercial_count)

        previous_cnt = self.get_commercial_processed_count(batch_end_epoch, self.shard_id)
        logger.debug("previous_cnt=%d", previous_cnt)
        prefix = self.commercial_processed_prefix
        key = self._build_processed_key(batch_end_epoch, self.shard_id)
        prefixed_key = '{}:{}'.format(prefix, key)
        set_cnt = commercial_count + previous_cnt
        logger.debug("set_cnt=%d prefixed_key=%s", set_cnt, prefixed_key)
        ok = self._writer.set(prefixed_key, set_cnt)
        self.expire(key, self.expire_processed_keys_in, prefix)

        return (ok, set_cnt)

    def record_tv_count(self, batch_end_epoch, tv_count):
        logger.info("%s batch_end_epoch=%d tv_count=%d record_tv_count..", self,
            batch_end_epoch, tv_count)

        previous_cnt = self.get_tv_count(batch_end_epoch, self.shard_id)
        logger.debug("previous_cnt=%d", previous_cnt)
        prefix = self.tvs_prefix
        key = self._build_processed_key(batch_end_epoch, self.shard_id)
        prefixed_key = '{}:{}'.format(prefix, key)
        set_cnt = tv_count + previous_cnt
        logger.debug("set_cnt=%d prefixed_key=%s", set_cnt, prefixed_key)
        ok = self._writer.set(prefixed_key, set_cnt)
        self.expire(key, self.expire_processed_keys_in, prefix)

        return (ok, set_cnt)

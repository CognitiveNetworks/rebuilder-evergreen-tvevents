import os
import json
import time
import psycopg2

from opentelemetry import trace
from opentelemetry.semconv.trace import SpanAttributes

from psycopg2.extras import RealDictCursor

import app
from app import meter

LOGGER = app.configure_logging()

tracer = trace.get_tracer(__name__)

# Create metrics counters
DB_CONNECTION_COUNTER = meter.create_counter(
    name="connect_to_db_counter",
    description="Connecting to the database",
)

DB_CONNECTION_ERROR_COUNTER = meter.create_counter(
    name="db_connection_error_counter",
    description="Database connection errors",
)

DB_QUERY_DURATION = meter.create_histogram(
    name="db_query_duration_seconds",
    description="Database query execution time",
)

DB_READ_COUNTER = meter.create_counter(
    name="read_from_db_counter", description="Reading from the db"
)

DB_WRITE_COUNTER = meter.create_counter(
    name="write_to_db_counter", description="Writing data to the db"
)

DB_QUERY_ERROR_COUNTER = meter.create_counter(
    name="db_query_error_counter",
    description="Database query errors",
)

CACHE_READ_COUNTER = meter.create_counter(
    name="read_from_cache_counter", description="Reading from the cache file"
)

CACHE_WRITE_COUNTER = meter.create_counter(
    name="write_to_cache_counter", description="Writing data to the cache file"
)


class TvEventsRds:
    """
    RDS database connection class
    """

    # pylint: disable=invalid-name
    BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH = '/tmp/.blacklisted_channel_ids_cache'

    def __init__(self):
        self._blacklisted_channel_ids = None

        self._channel_id_cache_last_updated = 0

    # pylint: disable=R1710
    def _connect(self):
        """
        Connects to RDS.
        """
        with tracer.start_as_current_span("db.connect") as span:
            try:
                db_host = os.getenv('RDS_HOST')
                db_name = os.getenv('RDS_DB')
                db_user = os.getenv('RDS_USER')
                db_port = os.getenv('RDS_PORT')

                # Add database attributes to span
                span.set_attributes(
                    {
                        SpanAttributes.DB_SYSTEM: "postgresql",
                        SpanAttributes.DB_NAME: db_name,
                        SpanAttributes.DB_USER: db_user,
                        SpanAttributes.NET_PEER_NAME: db_host,
                        SpanAttributes.NET_PEER_PORT: db_port,
                    }
                )

                LOGGER.info(
                    'connecting to RDS with host:{h}, database:{d}, user:{u}, port:{p}'.format(
                        h=db_host, d=db_name, u=db_user, p=db_port
                    )
                )

                # pylint: disable=W1508
                connection = psycopg2.connect(
                    host=db_host,
                    database=db_name,
                    user=db_user,
                    password=os.getenv('RDS_PASS'),
                    port=db_port,
                )

                DB_CONNECTION_COUNTER.add(1)
                LOGGER.info('connected')
                return connection
            except Exception as e:
                DB_CONNECTION_ERROR_COUNTER.add(
                    1, {"error_type": type(e).__name__, "host": db_host}
                )
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                LOGGER.error('RDS connection failed due to error : {err}'.format(err=e))

    def _execute(self, query):
        """
        connects to rds, runs the sql and returns result
        Params:
            sql : sql needed to run
        returns : integer
        """

        cur = None
        connection = None
        start_time = time.time()

        with tracer.start_as_current_span("db.query") as span:
            try:
                # Add database operation attributes
                operation = (
                    "SELECT"
                    if query.strip().upper().startswith("SELECT")
                    else "EXECUTE"
                )
                span.set_attributes(
                    {
                        SpanAttributes.DB_SYSTEM: "postgresql",
                        SpanAttributes.DB_STATEMENT: query,
                        SpanAttributes.DB_OPERATION: operation,
                    }
                )

                connection = self._connect()
                if not connection:
                    DB_QUERY_ERROR_COUNTER.add(
                        1, {"error_type": "connection_failed", "operation": operation}
                    )
                    return []

                # rds cursor
                cur = connection.cursor(cursor_factory=RealDictCursor)

                # execute sql
                LOGGER.info(
                    'Executing RDS query: {q}'.format(
                        q=query[:100] + '...' if len(query) > 100 else query
                    )
                )
                cur.execute(query)
                output = cur.fetchall()

                # Record metrics
                duration = time.time() - start_time
                DB_QUERY_DURATION.record(
                    duration, {"operation": operation, "status": "success"}
                )

                # Add result count to span
                span.set_attribute("db.rows_affected", len(output))
                span.set_attribute("db.query_duration_ms", duration * 1000)

                if operation == "SELECT":
                    DB_READ_COUNTER.add(1)
                else:
                    DB_WRITE_COUNTER.add(1)

                LOGGER.info(
                    'RDS query completed: {rows} rows, {duration:.3f}s'.format(
                        rows=len(output), duration=duration
                    )
                )
                return output

            except Exception as e:
                duration = time.time() - start_time
                DB_QUERY_DURATION.record(
                    duration, {"operation": operation, "status": "error"}
                )
                DB_QUERY_ERROR_COUNTER.add(
                    1, {"error_type": type(e).__name__, "operation": operation}
                )
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                LOGGER.error(
                    'RDS query failed after {duration:.3f}s - error: {err}'.format(
                        duration=duration, err=e
                    )
                )
            finally:
                # close cursor
                if cur:
                    cur.close()
                if connection:
                    connection.close()

            return []

    def store_data_in_channel_ids_cache(self, channel_ids):
        """
        Write given data to the cache file.
        """
        with tracer.start_as_current_span("store_data_in_channel_ids_cache"):
            try:
                with open(
                    self.BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH, 'w', encoding='utf-8'
                ) as blacklist_cache_fh:
                    LOGGER.debug('Wrote blacklisted channel ids to cache')
                    blacklist_cache_fh.write(json.dumps(channel_ids))
                    CACHE_WRITE_COUNTER.add(1)
            except IOError:
                LOGGER.error("Couldn't write to blacklisted channel ids cache file.")

    def read_data_from_channel_ids_cache(self):
        """
        Read from cache and return channel_ids.
        """
        with tracer.start_as_current_span("read_data_from_channel_ids_cache"):
            try:
                with open(
                    self.BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH, 'r', encoding='utf-8'
                ) as blacklist_cache_fh:
                    LOGGER.debug('Read blacklisted channel ids cache')
                    CACHE_READ_COUNTER.add(1)
                    return json.loads(blacklist_cache_fh.read())
            except IOError:
                LOGGER.error("Couldn't open blacklist cache file")

            return None

    def fetchall_channel_ids_from_blacklisted_station_channel_map(self):
        """
        Execute a fetchall against the tvevents_blacklisted_station_channel_map
        for all channel_id's.
        """
        with tracer.start_as_current_span(
            "fetchall_channel_ids_from_blacklisted_station_channel_map"
        ):
            query = """
                SELECT DISTINCT channel_id 
                FROM public.tvevents_blacklisted_station_channel_map;
            """

            DB_READ_COUNTER.add(1)
            return [row.get('channel_id') for row in self._execute(query)]

    def initialize_blacklisted_channel_ids_cache(self):
        """
        Fetch channel IDs from RDS and cache to file at startup.
        If RDS fails, raise exception to prevent pod startup.
        """
        channel_ids = self.fetchall_channel_ids_from_blacklisted_station_channel_map()
        if not channel_ids:
            raise RuntimeError(
                "Failed to fetch blacklisted channel IDs from RDS at startup."
            )
        self.store_data_in_channel_ids_cache(channel_ids)
        self._blacklisted_channel_ids = channel_ids

    def blacklisted_channel_ids(self):
        """
        Retrieves list of blacklisted channel ID's from cache.
        If cache is missing or unreadable, fetch from RDS and update cache.
        """
        with tracer.start_as_current_span("blacklisted_channel_ids"):
            if self._blacklisted_channel_ids is None:
                cached_channel_ids = self.read_data_from_channel_ids_cache()
                if cached_channel_ids is not None:
                    self._blacklisted_channel_ids = cached_channel_ids
                else:
                    rds_channel_ids = (
                        self.fetchall_channel_ids_from_blacklisted_station_channel_map()
                    )
                    if rds_channel_ids:
                        LOGGER.debug(
                            'Fetched blacklisted channel ids from RDS: {}'.format(
                                rds_channel_ids
                            )
                        )
                        self.store_data_in_channel_ids_cache(rds_channel_ids)
                        self._blacklisted_channel_ids = rds_channel_ids
                    else:
                        self._blacklisted_channel_ids = []
                        LOGGER.warning("No blacklisted channel IDs found.")
            return self._blacklisted_channel_ids

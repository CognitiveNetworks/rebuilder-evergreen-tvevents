"""
Database connection via PostgreSQL client

Note: created after redshift.RedshiftHandler. 
TODO: have Redshift Handler inherit from this
"""
import time
import psycopg2 as psql

from . import log
logger = log.getLogger(__name__)


class PsqlException(Exception):
    pass


class PsqlHandler(object):

    def __init__(self, host, database, user, password, port,
                 connect_timeout=1,
                 connect_attempts=1, time_between_connect_attempts=5,
                 query_attempts=1):
        """
        Create connection
        """
        self.host = host
        self.database = database
        self.user = user
        self.password = password
        self.port = port

        self.connect_timeout = connect_timeout
        self.connect_attempts = connect_attempts
        self.time_between_connect_attempts = time_between_connect_attempts
        self.query_attempts = query_attempts

        self.conn = None
        self.cur = None

        self.connect()

    def connect(self):
        while self.connect_attempts > 0:
            try:
                logger.info(
                    'Connecting to {}:{}/{}'.format(
                    self.host, self.port, self.database))

                self.conn = psql.connect(
                    database=self.database,
                    user=self.user,
                    password=self.password,
                    host=self.host,
                    port=self.port,
                    connect_timeout=self.connect_timeout
                )
                self.cur = self.conn.cursor()
                return

            except Exception as e:
                logger.warning(
                    'Unable to connect to database, retrying. e={}'.format(e))
                self.connect_attempts -= 1
                time.sleep(self.time_between_connect_attempts)

        else:
            raise PsqlException('Unable to connect to database!')

    def execute(self, query, q_args, commit, fetch):
        logger.debug('Executing query:\n\t{}\n'.format(query))
        self.cur.execute(query, q_args)
        logger.debug('Executing query:\n\t{}\n'.format(self.cur.query))

        if commit is True:
            self.conn.commit()

        if fetch is True:
            try:
                return self.cur.fetchall()
            except psql.ProgrammingError:
                logger.warning('No results to fetch.')

    def __call__(self, query, q_args=None, commit=True, fetch=True):
        """
        Execute query with q_args
        """
        tries_left = self.query_attempts
        while tries_left:
            try:
                return self.execute(query, q_args, commit, fetch)

            except (psql.DatabaseError, psql.InterfaceError, psql.ProgrammingError) as err:
                logger.exception('Database error: {}'.format(err))
                logger.info('Retrying...')
                self.connect()
                tries_left -= 1

            except Exception as err:
                logger.warning('Unable to execute query: {}'.format(err))
                raise

        logger.error('Tried {} times, giving up.'.format(self.query_attempts))
        raise err

    def close(self):
        """
        Close database Connection
        """
        if self.cur is not None:
            self.cur.close()
            del self.cur
            if self.conn is not None:
                self.conn.close()
            logger.info("Closing database connection")

        else:
            logger.info("Database connection already closed")
    __del__ = close

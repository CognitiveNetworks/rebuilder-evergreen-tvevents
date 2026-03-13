# -*- coding: utf-8 -*-

"""
Library for working with redshift
"""

# imports
import argparse
import csv
import os
import sys
from collections import OrderedDict

import boto
import boto3
import psycopg2 as psql
from six.moves.urllib.parse import urlsplit

from .log import getLogger
from .conf import parse_conf

# module globals
__author__ = 'John Inacay <join.inacay@cognitivenetworks.com>'
__all__ = ['RedshiftHandler', 'RedshiftParser']
logger = getLogger(__name__)


class RedshiftHandler(object):
    NUM_RETRIES = 3

    def __init__(self, host, database, user, password, port):
        """
        Create connection to redshift
        """
        self.host = host
        self.database = database
        self.user = user
        self.password = password
        self.port = port

        self.conn = None
        self.cur = None

        self.connect()

    def connect(self):
        logger.info('Connecting to {}'.format(self.host))
        self.conn = psql.connect(
            database=self.database,
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
        )
        self.cur = self.conn.cursor()

    def execute(self, query, q_args, commit, fetch):
        logger.debug('Executing query:\n\t{}\n'.format(
            self.cur.mogrify(query, q_args)))
        self.cur.execute(query, q_args)

        if commit is True:
            self.conn.commit()

        if fetch is True:
            return self.cur.fetchall()

    def __call__(self, query, q_args=None, commit=True, fetch=True):
        """
        Execute query with q_args
        """
        retries_left = self.NUM_RETRIES
        while retries_left:
            try:
                return self.execute(query, q_args, commit, fetch)

            except (psql.DatabaseError, psql.InterfaceError) as err:
                logger.exception('Database error: {}'.format(err))
                logger.info('Attempting to re-try.')
                self.connect()
                retries_left -= 1
                output_err = err

            except Exception as err:
                logger.warning('Unable to execute query: {}'.format(err))
                output_err = err
                raise

        logger.error('Re-tried {} times, giving up.'.format(self.NUM_RETRIES))
        raise output_err

    def table_exists(self, tablename):
        """
        Wrapper execute function that checks if
        table with tablename is in redshift
        """
        try:
            # this query is so that we won't have to remember
            # this idiosyncrasy of redshift
            query = "SELECT count(relname) from pg_class where relname = %s"
            logger.debug("Checking if {} exists".format(tablename))
            ret = self(query, [tablename], fetch=True)
            return ret[0][0] > 0

        except Exception as e:
            logger.warning("Unable to check table: {}".format(e))
            raise e

    def close(self):
        """
        Close Database Connection
        """
        if self.cur is not None:
            self.cur.close()
            self.cur = None
            if self.conn is not None:
                self.conn.close()
                self.conn = None
            logger.info("Closing redshift connection")

        else:
            logger.info("Redshift connection already closed")
    __del__ = close


def get_temp_redshift_handler(
        cluster_name,
        user,
        database,
        token_duration=3600,
        autocreate=False,
        dbgroups=None,
        port=5439,
    ):
    """
    usage is eg. get_temp_redshift_handler('prod-redshift-warm-live', 'monitoring', 'detectionlive')
    """

    rs = boto3.client('redshift')
    desc = rs.describe_clusters(ClusterIdentifier=cluster_name)['Clusters'][0]

    private_ip = None
    for node in desc['ClusterNodes']:
        if node['NodeRole'] == 'LEADER':
            private_ip = node['PrivateIPAddress']

    if not private_ip:
        raise RuntimeError('leader IP not found')

    params = dict(
        ClusterIdentifier=cluster_name,
        DbUser=user,
        DbName=database,
        DurationSeconds=token_duration,
        AutoCreate=autocreate,
    )
    if dbgroups:
        params['DbGroups'] = dbgroups

    response = rs.get_cluster_credentials(
        **params
    )

    return RedshiftHandler(
        host=private_ip,
        user=response['DbUser'],
        password=response['DbPassword'],
        database=database,
        port=port,
    )

### credentials

# environment variable mapping, for non-interactive authentication
env_mapping = [('PGUSER', 'user'),
               ('PGPASSWORD','password'),
               ('PGDATABASE', 'database'),
               ('PGHOST', 'host'),
               ('PGPORT', 'port'),
           ]


def credentials(**kwargs):
    """return credentials supplied in `kwargs` or in `os.environ`"""
    retval = OrderedDict()
    for env_key, py_key in env_mapping:
        retval[py_key] = kwargs.get(py_key) or os.environ.get(env_key)
    return retval


def add_credentials(parser, **kwargs):
    """add credentials to an parser"""
    for key, value in list(credentials(**kwargs).items()):
        if value:
            parser.add_argument('--'+key, dest=key, default=value,
                                help="{} [DEFAULT: {}]".format(key, value))
        else:
            parser.add_argument(key)


class RedshiftParser(argparse.ArgumentParser):
    """redshift parser"""

    # class defaults
    rs_cls = RedshiftHandler
    database = 'detection'
    host = 'redshift.cognet.tv'
    port = '5439'
    s3_credentials = 's3://cn-secure/redshift_credentials.conf'

    def __init__(self, **kwargs):

        # take default credentials from class
        credentials_args = {}
        for key in ('database', 'host', 'port'):
            value = kwargs.pop(key, getattr(self, key, None))
            if value:
                credentials_args[key] = value

        s3_credentials = kwargs.pop('s3_credentials', self.s3_credentials)
        argparse.ArgumentParser.__init__(self, **kwargs)

        if s3_credentials:
            # add credentials from s3 location
            try:
                parsed_url = urlsplit(s3_credentials)
                if parsed_url.scheme == 's3':
                    conn = boto.connect_s3()
                    bucket = conn.get_bucket(parsed_url.netloc)
                    key = bucket.get_key(parsed_url.path)
                    _dict = parse_conf(key.read())
                    for key, value in list(_dict.items()):
                        os.environ.setdefault(key, value)
                else:
                    self.error("Unsupported credentials scheme: {}".format(parsed_url.scheme))
            except Exception as e:
                print ("Error downloading s3_credentials from {}\n{}".format(s3_credentials, e))

        # add credentials arguments
        add_credentials(self, **credentials_args)
        self.options = None

    def parse_args(self, *args, **kwargs):
        options = argparse.ArgumentParser.parse_args(self, *args, **kwargs)
        self.validate(options)
        self.options = options
        return self.options

    def validate(self, options):
        """validate parsed arguments"""

    def redshift(self):
        """return a redshift connection"""
        assert self.options is not None
        return self.rs_cls(database=self.options.database,
                           user=self.options.user,
                           password=self.options.password,
                           host=self.options.host,
                           port=self.options.port
                       )


def main(args=sys.argv[1:]):
    """example CLI: redshift to CSV"""

    # parse command line arguments
    parser = RedshiftParser(description="output CSV from redshift query")
    parser.add_argument("query", help="SQL query to execute")
    parser.add_argument("-o", "--output", dest="output",
                        type=argparse.FileType('a'), default=sys.stdout,
                        help="CSV file to append to, or stdout by default")
    options = parser.parse_args(args)

    # get redshift connection
    rs = parser.redshift()

    # execute query
    query = options.query.strip()
    if not query.endswith(';'):
        query += ';'
    data = rs(query, commit=True, fetch=True)

    # write CSV output
    writer = csv.writer(options.output)
    for row in data:
        writer.writerow(row)

if __name__ == '__main__':
    main()

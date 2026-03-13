"""
Yet-Another-MYSQL-Front-End
"""

import pymysql
import sys

class MySQL(object):

    def __init__(self, host, user, passwd, db):
        self.host = host
        self.user = user
        self.passwd = passwd
        self.db = db
        self.connect()

    def connect(self):
        self.conn =  pymysql.connect(host=self.host,
                                     user=self.user,
                                     passwd=self.passwd,
                                     db=self.db,
                                     cursorclass=pymysql.cursors.DictCursor)

    def __call__(self, sql):
        with self.conn.cursor() as cursor:
            cursor.execute(sql)
            data = cursor.fetchall()
            self.conn.commit()
            return data

    def close(self):
        try:
            self.conn.commit()
            self.conn.cursor().close()
            self.conn.close()
        except Exception as e:
            sys.stderr.write("Error closing database:\n  {}\n".format(e))

    __del__ = close

"""
TODO:
- remove NATIVE_APP_WHITELIST_DIRNAME var
- remove NATIVE_APP_WHITELIST_BUCKET var
"""
import os
import re
import sys
import html
import json
import urllib.parse
import tempfile
import traceback

from . import log
from . import postgresql
logger = log.getLogger(__name__)


WHITELIST_DETECTION_LOCALFILE = os.getenv(
    "WHITELIST_DETECTION_LOCALFILE", 
    os.path.join(tempfile.gettempdir(), "app_whitelist_detection"))

WHITELIST_METADATA_LOCALFILE = os.getenv(
    "WHITELIST_METADATA_LOCALFILE",
    os.path.join(tempfile.gettempdir(), "app_whitelist_metadata"))

WHITELIST_CHIPSET_LOCALFILE = os.getenv(
    "WHITELIST_CHIPSET_LOCALFILE",
    os.path.join(tempfile.gettempdir(), "app_whitelist_chipset"))


# defined by acr_tvclient/common/TVIS_capture_client_control.h:TVIS_MAX_STRING
APP_NAMES_WHITELIST_DETECTION_MAX_LENGTH = 512
APP_URLS_WHITELIST_DETECTION_MAX_LENGTH = 2048


class AppWhitelist(object):

    def __init__(self, host=None, database=None, user=None, password=None, 
                 port=None, psql_handler=None, localfile=None, **kwargs):

        self.whitelist = {}
        self.chipset_versioning = {}

        self.psql_handler = self._get_db_handler(
            psql_handler, host, database, user, password, port, **kwargs)

        self.localfile = localfile

        logger.info("Generating app whitelist...")

        try:
            self.from_db()
        except Exception as e:
            logger.error("Database error, reading whitelist from disk. e={}".format(e))
            exc_info = sys.exc_info()
            logger.error(traceback.print_exception(*exc_info))

            if not self.whitelist:
                self.from_disk()
        else:
            self.to_disk()

        logger.info("Finished generating app whitelist.")

    def _get_db_handler(self, psql_handler=None, host=None, database=None, 
                        user=None, password=None, port=None, **kwargs):
        if not psql_handler:
            try:
                psql_handler = postgresql.PsqlHandler(
                    host, database, user, password, port, **kwargs)
            except postgresql.PsqlException as e:
                logger.error(e)
                psql_handler = None

        return psql_handler

    def get_lookup_methods(self, chipset_version, chipset_subversion=None):
        if not self.chipset_match(chipset_version, chipset_subversion):
            return []

        return self.whitelist[chipset_version].keys()

    def from_disk(self):
        logger.info("Reading app whitelist from disk: file={}".format(self.localfile))
        try:
            with open(self.localfile, 'r') as f:
                self.whitelist = json.loads(f)
        except Exception as e:
            logger.error("Unable to read localfile. Returning empty whitelist. "
                         "localfile={}".format(self.localfile))
            self.whitelist = {}

        logger.info("Reading chipset whitelist from disk: file={}".format(WHITELIST_CHIPSET_LOCALFILE))
        try:
            with open(WHITELIST_CHIPSET_LOCALFILE, 'r') as f:
                self.chipset_versioning = json.loads(f)
        except Exception as e:
            logger.error("Unable to read localfile. Returning empty chipset versioning. "
                         "localfile={}".format(WHITELIST_CHIPSET_LOCALFILE))
            self.chipset_versioning = {}

    def to_disk(self):
        logger.info("Writing app whitelist to disk: file={}".format(self.localfile))
        with open(self.localfile, 'w') as f:
            json.dump(self.whitelist, f)

        with open(WHITELIST_CHIPSET_LOCALFILE, 'w') as f:
            json.dump(self.chipset_versioning, f)

    def from_db(self):
        raise NotImplementedError

    def chipset_match(self, version, subversion):
        if version not in self.chipset_versioning:
            return False

        subversion = subversion or ""

        subversion_regex = self.chipset_versioning[version]
        return bool(re.match(subversion_regex, subversion))

    def _check_value(self, value, id_type, chipset_name, chipset_subversion=None):
        if not self.chipset_match(chipset_name, chipset_subversion):
            return None

        try:
            result = self.whitelist[chipset_name][id_type][value]
        except KeyError:
            result = None

        return result

    def check_url(self, url, chipset_version, chipset_subversion=None):
        result = None
        base_url = url.rstrip("/")
        for url in [url, url + "/"]:
            result = self._check_value(url, "app_url", chipset_version, chipset_subversion)
            if result:
                break

        return result

    def check_name(self, name, chipset_version, chipset_subversion=None):
        return self._check_value(name, "app_name_short", chipset_version, chipset_subversion)
        
    def check_namespace(self, namespace, app_id, chipset_version, chipset_subversion=None):
        app_ids = [app_id]
        try:
            # hex to dec
            if int(str(namespace)) == 0 and len(str(app_id)) == 8:
                app_id_candidate = int(str(app_id), 16)
                app_ids.append(app_id_candidate)
        except:
            pass

        for id_ in app_ids:
            result = self._check_value("{},{}".format(namespace, id_), 
                                       "app_namespace", chipset_version, 
                                       chipset_subversion)
            if result:
                return result

        return False

    def _get_whitelist_string(self, id_type, delimiter, chipset_name, chipset_subversion=None):
        whitelist_string = ""
        if (self.chipset_match(chipset_name, chipset_subversion)
                and chipset_name in self.whitelist
                and id_type in self.whitelist[chipset_name]):

            # exclude 5580 (MSERIES) from encoding
            if id_type == "app_url" and chipset_name != "MSERIES":
                # For some reason, HTML-encode, then URL-encode each URL.
                whitelist_string = delimiter.join(
                    [urllib.parse.quote(html.escape(url), safe='')
                     for url in self.whitelist[chipset_name][id_type].keys()]
                )
            else:
                whitelist_string = delimiter.join(
                    self.whitelist[chipset_name][id_type].keys())

        return whitelist_string

    def get_name_whitelist_string(self, chipset_name, chipset_subversion=None):
        return self._get_whitelist_string("app_name_short", ",", chipset_name, chipset_subversion)
        
    def get_url_whitelist_string(self, chipset_name, chipset_subversion=None):
        return self._get_whitelist_string("app_url", " ", chipset_name, chipset_subversion)


class AppWhitelistDetection(AppWhitelist):

    def __init__(self, localfile=None, *args, **kwargs):
        localfile = localfile or WHITELIST_DETECTION_LOCALFILE
        super(AppWhitelistDetection, self).__init__(localfile=localfile, *args, **kwargs)

    def from_db(self):
        query = ("""
            SELECT
                'app_name_short' AS lookup_method,
                c.chipset_version AS chipset_name,
                c.chipset_subversion_regex AS chipset_subversion_regex,
                a.app_name_long AS app_name_long,
                a.app_name_short AS app_name_short,
                NULL AS app_url
            FROM chipset_acr_whitelist_name_lookup w 
            JOIN app_id a 
                ON w.app_name_long = a.app_name_long 
            JOIN chipset_id c
                ON w.chipset_version = c.chipset_version

            UNION ALL

            SELECT
                'app_url' AS lookup_method,
                c.chipset_version AS chipset_name,
                c.chipset_subversion_regex AS chipset_subversion_regex,
                a.app_name_long AS app_name_long,
                NULL AS app_name_short,
                u.app_url AS app_url
            FROM chipset_acr_whitelist_url_lookup w 
            JOIN chipset_id c
                ON w.chipset_version = c.chipset_version
            JOIN app_id a 
                ON w.app_name_long = a.app_name_long 
            JOIN chipset_app_url u 
                ON w.chipset_version = u.chipset_version
                    AND w.app_name_long = u.app_name_long
        """)
  
        results = self.psql_handler(query, commit=False) 
        column_dict = {i: c[0] for i, c in enumerate(self.psql_handler.cur.description)}

        self.whitelist = {}

        for record in results:
            row = {column_dict[i]: record[i] for i, v in enumerate(record)}

            # whitelist updates
            chipset_name = row["chipset_name"]
            if not chipset_name in self.whitelist:
                self.whitelist[chipset_name] = {}

            lookup_method = row["lookup_method"]
            if lookup_method in ["app_name_short", "app_url"]:
                for column_name in ["app_name_short", "app_url"]:
                    column_value = row[column_name]
                    if column_value:
                        update = {column_value: row["app_name_long"]}
                        if not column_name in self.whitelist[chipset_name]:
                            self.whitelist[chipset_name][column_name] = update
                        else:
                            self.whitelist[chipset_name][column_name].update(update)

            else:
                logger.warning("Row without lookup method. Discarding. row={}".format(row))

            # chipset versioning
            if not chipset_name in self.chipset_versioning:
                self.chipset_versioning[chipset_name] = row["chipset_subversion_regex"]


class AppWhitelistMetadata(AppWhitelist):

    def __init__(self, localfile=None, *args, **kwargs):
        localfile = localfile or WHITELIST_METADATA_LOCALFILE
        super(AppWhitelistMetadata, self).__init__(localfile=localfile, *args, **kwargs)

    def from_db(self):
        query = ("""
            SELECT
                'app_name_short' AS lookup_method,
                c.chipset_version AS chipset_name,
                c.chipset_subversion_regex AS chipset_subversion_regex,
                a.app_name_long AS app_name_long,
                a.app_name_short AS app_name_short,
                NULL AS app_url,
                CAST(NULL AS INT) AS app_namespace,
                CAST(NULL AS BIGINT) AS app_id
            FROM chipset_metadata_whitelist_name_lookup w 
            JOIN app_id a 
                ON w.app_name_long = a.app_name_long 
            JOIN chipset_id c
                ON w.chipset_version = c.chipset_version

            UNION ALL

            SELECT
                'app_url' AS lookup_method,
                c.chipset_version AS chipset_name,
                c.chipset_subversion_regex AS chipset_subversion_regex,
                a.app_name_long AS app_name_long,
                NULL AS app_name_short,
                u.app_url AS app_url,
                CAST(NULL AS INT) AS app_namespace,
                CAST(NULL AS BIGINT) AS app_id
            FROM chipset_metadata_whitelist_url_lookup w 
            JOIN chipset_id c
                ON w.chipset_version = c.chipset_version
            JOIN app_id a 
                ON w.app_name_long = a.app_name_long 
            JOIN chipset_app_url u 
                ON w.chipset_version = u.chipset_version
                    AND w.app_name_long = u.app_name_long

            UNION ALL

            SELECT
                'app_namespace' AS lookup_method,
                c.chipset_version AS chipset_name,
                c.chipset_subversion_regex AS chipset_subversion_regex,
                a.app_name_long AS app_name_long,
                NULL AS app_name_short,
                NULL AS app_url,
                n.namespace AS app_namespace,
                n.app_id AS app_id
            FROM chipset_metadata_whitelist_namespace_lookup w 
            JOIN app_id a 
                ON w.app_name_long = a.app_name_long 
            JOIN app_namespace n
                ON a.app_name_long = n.app_name_long
            JOIN chipset_id c
                ON w.chipset_version = c.chipset_version
        """)
  
        results = self.psql_handler(query, commit=False) 
        column_dict = {i: c[0] for i, c in enumerate(self.psql_handler.cur.description)}

        self.whitelist = {}

        for record in results:
            row = {column_dict[i]: record[i] for i, v in enumerate(record)}

            # whitelist updates
            chipset_name = row["chipset_name"]
            if not chipset_name in self.whitelist:
                self.whitelist[chipset_name] = {}

            lookup_method = row["lookup_method"]
            if lookup_method in ["app_name_short", "app_url"]:
                for column_name in ["app_name_short", "app_url"]:
                    column_value = row[column_name]
                    if column_value:
                        if column_name == "app_url":
                            # HTML-encode URL to match dynamic metadata file
                            column_value = html.escape(column_value)

                        update = {column_value: row["app_name_long"]}
                        if not column_name in self.whitelist[chipset_name]:
                            self.whitelist[chipset_name][column_name] = update
                        else:
                            self.whitelist[chipset_name][column_name].update(update)

            elif lookup_method == "app_namespace":
                if all([row["app_namespace"] != None, row["app_id"] != None]):
                    
                    namespace_key = "{},{}".format(row["app_namespace"], 
                                                   row["app_id"])
                    update = {namespace_key: row["app_name_long"]}
                    if not "app_namespace" in self.whitelist[chipset_name]:
                        self.whitelist[chipset_name]["app_namespace"] = update
                    else:
                        self.whitelist[chipset_name]["app_namespace"].update(update)
            else:
                logger.warning("Row without lookup method. Discarding. row={}".format(row))

            # chipset versioning
            if not chipset_name in self.chipset_versioning:
                self.chipset_versioning[chipset_name] = row["chipset_subversion_regex"]


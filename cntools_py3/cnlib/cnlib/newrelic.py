import datetime
import logging
import os
import requests
import six
from . import log
from requests.exceptions import Timeout, RequestException

logger = log.getLogger(__name__)

url = 'https://metric-api.newrelic.com/metric/v1'
new_relic_key = os.getenv("NEW_RELIC_KEY")

headers = {
    'Api-Key': new_relic_key,
    'Content-Type': 'application/json'
}


def create_datapoint(
        metric_name,
        value,
        metric_labels=None,
        start_time=None,
        end_time=None,
        resource_name="global",
        resource_labels=None,
        label=''
):
    if isinstance(start_time, float):
        start_time = datetime.datetime.utcfromtimestamp(start_time).timestamp() * 1e3
    if isinstance(end_time, float):
        end_time = datetime.datetime.utcfromtimestamp(end_time).timestamp() * 1e3

    if end_time and start_time is None:
        start_time = end_time

    if start_time and end_time is None:
        end_time = start_time

    if isinstance(value, six.integer_types):
        value = int(value)
    if isinstance(value, str):
        if value.isdigit():
            value = int(value)
        else:
            try:
                value = float(value)
            except Exception as e:
                pass

    return metric_name, value, metric_labels, start_time, end_time, resource_name, resource_labels, label


def datapoints_to_metric(dp):
    value = dp[1]
    new_metric = {}

    metric_labels = dict(dp[2])
    resource_labels = dict(dp[6]) if dp[6] else {}

    attributes = {'resource_name': dp[5]}
    attributes.update(resource_labels)
    attributes.update(metric_labels)

    name = dp[0]
    label = f"{dp[7]}/" if len(dp) > 7 else dp[0]
    if 'custom' in dp[0].lower():
        name = f"Custom/{label}{dp[0]}"

    new_metric['timestamp'] = datetime.datetime.utcnow().timestamp() * 1e3
    new_metric['name'] = name
    new_metric['value'] = value
    new_metric['attributes'] = attributes

    return new_metric


class CustomMetrics:
    def __init__(self, application_name=None, logger=None):
        if logger is None:
            logger = log.getLogger(__name__)
        self.logger = logger

        if not application_name:
            application_name = os.environ.get('SERVICE_NAME', 'unknown')
        self.application_name = application_name

        self.logger.info(f"Initializing NewRelic for {self.application_name}")

    def _create_mock_response_for_issues_with_new_relic(self, status_code, message):
        """
        Creates a mock response object in case of an error or timeout.
        """
        mock_response = requests.Response()
        mock_response.status_code = status_code
        mock_response._content = str.encode(message)  # Convert message to bytes
        return mock_response

    def send_metric(self, datapoint):
        """
        Provide a single metric, and it's name
        """
        result = self.send_multiple_metrics([datapoint])
        return result

    def send_multiple_metrics(self, datapoints):
        """
        Provide multiple metrics in the form of a dictionary.
        Check if the keys start with Custom/, update them if not
        """
        payload = [{
            "metrics": []
        }]

        for dp in datapoints:
            new_metric = datapoints_to_metric(dp)
            payload[0]['metrics'].append(new_metric)

        self.logger.debug(f"Data for NewRelic: {payload}")

        try:
            response = requests.post(url,
                                     json=payload,
                                     headers=headers,
                                     timeout=5)
            # NewRelic
            if response.status_code // 100 == 2:
                self.logger.info(f"Successfully send metrics to NewRelic: {response.text}")
            else:
                self.logger.warning(
                    f"Issue sending metrics to NewRelic with response code {response.status_code}: {response.text}")

            return response

        except Timeout as e:
            self.logger.error("Request to NewRelic timed out")
            return self._create_mock_response_for_issues_with_new_relic(408, "Request Timeout for NewRelic")

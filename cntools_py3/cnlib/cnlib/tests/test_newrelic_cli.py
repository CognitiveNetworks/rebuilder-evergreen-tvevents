"""
Test graphs can be seen in the following URL:
https://one.newrelic.com/dashboards/detail/MzQ2OTU2MnxWSVp8REFTSEJPQVJEfGRhOjQ4MTQxNjE?account=3469562&state=81ab3997-33cb-1236-1548-6834be378b07
"""

import os
import time
from click.testing import CliRunner
from cnlib import newrelic_cli
import json

runner = CliRunner()


def test_new_relic_key_provided():
    new_relic_key = os.getenv("NEW_RELIC_KEY")
    assert new_relic_key


def test_send_custom_metric():
    command = 'send-metric'
    metric_name = 'cntools_py3_test_metric'
    value = 42
    start_time = time.time() * 1000
    resource_name = 'cntools_py3_resource'
    metric_label = ('label1', 'value1')
    resource_label = ('label2', 'value2')
    value_type = 'DOUBLE'

    command_string = f"{command} {metric_name} {value} --start-time {start_time} --resource_name {resource_name} --metric-label {metric_label[0]} {metric_label[1]} --resource-label {resource_label[0]} {resource_label[1]} --value-type {value_type}"
    # command_string = f"send-metric --help"

    res = runner.invoke(newrelic_cli.cli, command_string.split())
    assert json.loads(res.output.replace("\'", "\""))['status_code'] // 100 == 2


def test_send_custom_metric_no_time_provided():
    command = 'send-metric'
    metric_name = 'cntools_py3_test_metric_no_time'
    value = 42
    resource_name = 'cntools_py3_resource'
    metric_label = ('label1', 'value1')
    resource_label = ('label2', 'value2')
    value_type = 'DOUBLE'

    command_string = f"{command} {metric_name} {value} --resource_name {resource_name} --metric-label {metric_label[0]} {metric_label[1]} --resource-label {resource_label[0]} {resource_label[1]} --value-type {value_type}"
    # command_string = f"send-metric --help"

    res = runner.invoke(newrelic_cli.cli, command_string.split())
    assert json.loads(res.output.replace("\'", "\""))['status_code'] // 100 == 2


def test_send_many_metrics():
    data = [{"metric_name": "tests/dummy_4",
             "value": 1.0,
             "start_time": time.time() * 1000,
             "end_time": time.time() * 1000,
             "resource_name": "cntools_tests",
             "resource_labels": {"label_1": "test_lable_1"},
             "metric_labels": {"label_test_1": "test_1", "label_test_2": "test_2"},
             },
            {"metric_name": "tests/dummy_4",
             "value": 2.0,
             "start_time": int(time.time()) * 1000,
             "end_time": int(time.time()) * 1000,
             "resource_name": "cntools_tests",
             "resource_labels": {"label_1": "test_lable_2"},
             "metric_labels": {"label_test_1": "test_2", "label_test_2": "test_2"},
             }
            ]

    json_data = json.dumps(data)

    res = runner.invoke(newrelic_cli.cli, ['send-many-metrics-from-json-data', json_data])

    assert json.loads(res.output.replace("\'", "\""))['status_code'] // 100 == 2


def test_send_from_file():
    json_file = os.path.dirname(__file__) + '/test_data/metrics_file.json'

    res = runner.invoke(newrelic_cli.cli, ['send-many-metrics-from-json-file', json_file])
    assert json.loads(res.output.replace("\'", "\""))['status_code'] // 100 == 2

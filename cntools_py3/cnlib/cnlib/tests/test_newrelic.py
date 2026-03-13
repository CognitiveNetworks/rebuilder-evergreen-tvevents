"""
Test graphs can be seen in the following URL:
https://one.newrelic.com/dashboards/detail/MzQ2OTU2MnxWSVp8REFTSEJPQVJEfGRhOjQ4MTQxNjE?account=3469562&state=81ab3997-33cb-1236-1548-6834be378b07
Working with Pytest V7.2.0
"""

import time

from cnlib import newrelic

nr = newrelic.CustomMetrics()


def test_send_metric(monkeypatch):
    datapoint_result = newrelic.create_datapoint(
        metric_name='cntools_py3_lib_metrics',
        value=84,
        metric_labels={"metric_label_name": "test_metric"},
        start_time=time.time(),
        resource_name="test_resource_name",
        resource_labels={"resource_label_name": "test_resource"})

    result = nr.send_metric(datapoint_result)

    assert result.status_code // 100 == 2


def test_send_multiple_metrics(monkeypatch):
    metric_list = []
    for i in range(1, 4):
        datapoint_result = newrelic.create_datapoint(
            metric_name='cntools_py3_lib_metrics_multiple',
            value=42 * i,
            metric_labels={"metric_label_name": "test_metric"},
            start_time=time.time(),
            resource_name="test_resource_name",
            resource_labels={"resource_label_name": "test_resource"})

        metric_list.append(datapoint_result)

    result = nr.send_multiple_metrics(metric_list)

    assert result.status_code // 100 == 2

import datetime
import os
import time

import requests
import click
from schema import Schema, And, Or, Optional, Use, SchemaError
import json
from six import text_type

url = 'https://metric-api.newrelic.com/metric/v1'
new_relic_key = os.getenv("NEW_RELIC_KEY")

headers = {
    'Api-Key': new_relic_key,
    'Content-Type': 'application/json'
}

sample_payload = [{
    "metrics": []
}]

VALUE_TYPES = {'INT64': int, 'DOUBLE': float, 'BOOL': bool}

schema_json = Schema(
    And(
        Use(json.loads),
        [{
            "metric_name": text_type,
            "value": Or(*VALUE_TYPES.values()),
            Optional("metric_labels", default=None): {
                text_type: text_type
            },
            Optional("start_time", default=None): Or(float, int),
            Optional("end_time", default=None): Or(float, int),
            Optional("resource_name", default='global'): text_type,
            Optional("resource_labels", default=None): {
                text_type: text_type
            }
        }]
    )
)


def cast_value(value, value_type):
    value_for_false = ('0', 0, 'no', 'false', 'No', 'False')
    value_for_true = ('1', 1, 'yes', 'true', 'Yes', 'True')
    if value_type == 'BOOL':
        if value in value_for_false:
            value = False
        elif value in value_for_true:
            value = True
        else:
            raise click.UsageError("for value-type %s value parameter must be one of: %s %s" % (
                value_type, value_for_false, value_for_true))
    else:
        try:
            value = VALUE_TYPES[value_type](value)
        except ValueError as e:
            raise click.UsageError("for value-type %s value parameter is invalid: %s" % (value_type, str(e)))
    return value


@click.group()
def cli():
    pass


def create_metric(metric, value_type):
    value = cast_value(metric['value'], value_type)
    new_metric = {}
    metric_labels = dict(metric['metric_labels'])
    resource_labels = dict(metric['resource_labels']) if metric['resource_labels'] else {}

    attributes = {'resource_name': metric['resource_name']}
    attributes.update(resource_labels)
    attributes.update(metric_labels)
    metric['metric_name'] = f"Custom/{metric['metric_name']}"

    if 'timestamp' not in new_metric:
        new_metric['timestamp'] = datetime.datetime.utcnow().timestamp() * 1e3
    new_metric['name'] = metric['metric_name']
    new_metric['value'] = value
    new_metric['attributes'] = attributes

    return new_metric


@cli.command('send-metric')
@click.argument("metric-name", type=str)
@click.argument("value", type=str)
@click.option('--start-time', default=None, type=float, help='timestamp')
@click.option("--resource_name", default='global')
@click.option('--metric-label', nargs=2, multiple=True)
@click.option('--resource-label', nargs=2, multiple=True)
@click.option('--value-type', type=click.Choice(VALUE_TYPES.keys()),
              default='DOUBLE', help='default: DOUBLE')
def send_custom_metric(metric_name, value, start_time, resource_name,
                       metric_label, resource_label, value_type
                       ):
    global sample_payload
    payload = sample_payload
    metric_labels = dict(metric_label)
    resource_labels = dict(resource_label)
    value = cast_value(value, value_type)

    attributes = {'resource_name': resource_name}
    attributes.update(resource_labels)
    attributes.update(metric_labels)

    new_metric = {'timestamp': datetime.datetime.utcnow().timestamp()*1e3}

    if start_time:
        new_metric['timestamp'] = start_time
    new_metric['name'] = metric_name
    new_metric['value'] = value
    new_metric['attributes'] = attributes

    payload[0]['metrics'].append(new_metric)
    response = requests.post(url,
                             json=payload,
                             headers=headers)

    click.echo({'status_code': response.status_code})


@cli.command('send-many-metrics-from-json-data', help='''json example:\n
[{"metric_name": "type_name_test_1", "value": 1, "metric_labels": {"label_test_1": "test_1", "label_test_2": "test_2"}},
 {"metric_name": "type_name_test_1", "value": 2, "metric_labels": {"label_test_1": "test_2", "label_test_2": "test_2"}}]'''
             )
@click.argument('json-data', type=str)
@click.option('--value-type', type=click.Choice(VALUE_TYPES.keys()),
              default='DOUBLE', help='default: DOUBLE')
def send_many_metrics_from_json_data(json_data, value_type):
    global sample_payload
    payload = sample_payload
    try:
        json_data = schema_json.validate(json_data)
    except SchemaError as e:
        raise click.UsageError("JSON Validation failed:\n" + e.code)

    for metric in json_data:
        new_metric = create_metric(metric, value_type)
        payload[0]['metrics'].append(new_metric)
    response = requests.post(url, json=payload, headers=headers)

    click.echo({'status_code': response.status_code})


@cli.command('send-many-metrics-from-json-file', help='''json example:\n
[{"metric_name": "type_name_test_1", "value": 1, "metric_labels": {"label_test_1": "test_1", "label_test_2": "test_2"}},
 {"metric_name": "type_name_test_1", "value": 2, "metric_labels": {"label_test_1": "test_2", "label_test_2": "test_2"}}]'''
             )
@click.argument('json-file', type=click.File('r'))
@click.option('--value-type', type=click.Choice(VALUE_TYPES.keys()),
              default='DOUBLE', help='default: DOUBLE')
def send_many_metrics_from_json_file(json_file, value_type):
    global sample_payload
    payload = sample_payload
    try:
        json_data = json_file.read()
        json_data = schema_json.validate(json_data)
    except SchemaError as e:
        raise click.UsageError("JSON Validation failed:\n" + e.code)

    for metric in json_data:
        new_metric = create_metric(metric, value_type)
        payload[0]['metrics'].append(new_metric)

    response = requests.post(url,
                             json=payload,
                             headers=headers)

    click.echo({'status_code': response.status_code})


if __name__ == "__main__":
    cli()

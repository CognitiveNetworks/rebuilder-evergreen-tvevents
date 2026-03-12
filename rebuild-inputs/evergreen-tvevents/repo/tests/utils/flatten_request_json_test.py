# pylint: disable=E0401,W0621,R0801

from app.utils import flatten_request_json


def test_flatten_simple_json():
    """
    Test flatten_request_json with a simple JSON object.
    Ensures that a flat JSON object remains unchanged.
    """
    request_json = {'key1': 'value1', 'key2': 'value2'}
    expected_output = {'key1': 'value1', 'key2': 'value2'}
    assert flatten_request_json(request_json) == expected_output


def test_flatten_nested_json():
    """
    Test flatten_request_json with a nested JSON object.
    Ensures that nested keys are flattened correctly.
    """
    request_json = {
        'key1': {'subkey1': 'value1', 'subkey2': 'value2'},
        'key2': 'value2',
    }
    expected_output = {
        'key1_subkey1': 'value1',
        'key1_subkey2': 'value2',
        'key2': 'value2',
    }
    assert flatten_request_json(request_json) == expected_output


def test_flatten_with_key_prefix():
    """
    Test flatten_request_json with a key prefix.
    Ensures that the key prefix is added correctly to all keys.
    """
    request_json = {
        'key1': {'subkey1': 'value1', 'subkey2': 'value2'},
        'key2': 'value2',
    }
    expected_output = {
        'key1_subkey1': 'value1',
        'key1_subkey2': 'value2',
        'key2': 'value2',
    }
    assert flatten_request_json(request_json) == expected_output


def test_flatten_with_ignore_keys():
    """
    Test flatten_request_json with keys to ignore.
    Ensures that specified keys are ignored while flattening.
    """
    request_json = {
        'key1': {'subkey1': 'value1', 'subkey2': 'value2'},
        'key2': 'value2',
        'ignorekey': {'subkey3': 'value3'},
    }
    expected_output = {
        'key1_subkey1': 'value1',
        'key1_subkey2': 'value2',
        'key2': 'value2',
    }

    assert (
        flatten_request_json(request_json, ignore_keys=['ignorekey']) == expected_output
    )


def test_flatten_empty_json():
    """
    Test flatten_request_json with an empty JSON object.
    Ensures that an empty JSON object remains unchanged.
    """
    request_json = {}
    expected_output = {}
    assert flatten_request_json(request_json) == expected_output

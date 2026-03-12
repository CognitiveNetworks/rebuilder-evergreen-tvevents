# pylint: disable=E0401,W0621,R0801
from unittest.mock import patch, MagicMock, call
from app.utils import send_to_valid_firehoses


@patch('app.utils.LOGGER')
@patch('app.utils.firehose.Firehose')
@patch(
    'app.utils.VALID_TVEVENTS_DEBUG_FIREHOSES',
    [
        'DEBUG_WARM_FIREHOSE_NAME',
        'DEBUG_HOTE_FIREHOSE_NAME',
        'DEBUG_HOTC_FIREHOSE_NAME',
    ],
)
@patch('app.utils.ZOO', 'local-testing')
def test_send_to_valid_firehoses_debug(mock_firehose, mock_logger):
    """
    Test send_to_valid_firehoses with debug flag enabled.
    Ensures that data is sent to all valid debug firehoses.
    """
    data = {'key': 'value'}
    send_to_valid_firehoses(data, tvevents_debug_flag=True)

    # pylint: disable=C0301
    mock_logger.info.assert_any_call(
        "valid debug firehoses of local-testing zoo: ['DEBUG_WARM_FIREHOSE_NAME', 'DEBUG_HOTE_FIREHOSE_NAME', 'DEBUG_HOTC_FIREHOSE_NAME']"
    )

    mock_firehose.assert_any_call('DEBUG_WARM_FIREHOSE_NAME')
    mock_firehose.assert_any_call('DEBUG_HOTE_FIREHOSE_NAME')
    mock_firehose.assert_any_call('DEBUG_HOTE_FIREHOSE_NAME')


@patch('app.utils.LOGGER')
@patch('app.utils.firehose.Firehose')
@patch(
    'app.utils.VALID_TVEVENTS_FIREHOSES',
    ['WARM_FIREHOSE_NAME', 'HOTE_FIREHOSE_NAME', 'HOTC_FIREHOSE_NAME'],
)
@patch('app.utils.ZOO', 'local-testing')
def test_send_to_valid_firehoses_non_debug(mock_firehose, mock_logger):
    """
    Test send_to_valid_firehoses with debug flag disabled.
    Ensures that data is sent to all valid firehoses.
    """
    data = {'key': 'value'}
    send_to_valid_firehoses(data, tvevents_debug_flag=False)

    # pylint: disable=C0301
    mock_logger.info.assert_any_call(
        "valid firehoses of local-testing zoo: ['WARM_FIREHOSE_NAME', 'HOTE_FIREHOSE_NAME', 'HOTC_FIREHOSE_NAME']"
    )

    mock_firehose.assert_any_call('WARM_FIREHOSE_NAME')
    mock_firehose.assert_any_call('HOTE_FIREHOSE_NAME')
    mock_firehose.assert_any_call('HOTC_FIREHOSE_NAME')


@patch('app.utils.LOGGER')
@patch('app.utils.firehose.Firehose')
@patch(
    'app.utils.VALID_TVEVENTS_FIREHOSES',
    ['WARM_FIREHOSE_NAME', 'HOTE_FIREHOSE_NAME', 'HOTC_FIREHOSE_NAME'],
)
@patch('app.utils.ZOO', 'local-testing')
@patch('concurrent.futures.ThreadPoolExecutor.map')
def test_send_to_valid_firehoses_exception_tpexec(
    mock_executor_map, mock_firehose, mock_logger
):
    """
    Test send_to_valid_firehoses with an exception during executor.map.
    Ensures that the function logs the error message.
    """
    data = {'key': 'value'}
    mock_executor_map.side_effect = Exception('Test Exception')
    mock_firehose_instance = MagicMock()
    mock_firehose.return_value = mock_firehose_instance

    send_to_valid_firehoses(data, tvevents_debug_flag=False)

    mock_logger.error.assert_called_once_with(
        'tpexec_valid_firehoses_of_zoo failed: tvid=None - Test Exception'
    )


@patch('app.utils.LOGGER')
@patch('app.utils.firehose.Firehose')
@patch(
    'app.utils.VALID_TVEVENTS_FIREHOSES',
    ['HOTC_FIREHOSE_NAME'],
)
@patch('app.utils.ZOO', 'local-testing')
@patch('json.dumps')
def test_send_to_valid_firehoses_exception(mock_json_dumps, mock_firehose, mock_logger):
    """
    Test send_to_valid_firehoses with an exception during json.dumps.
    Ensures that the function logs both error messages.
    """
    data = {'key': 'value'}
    mock_json_dumps.side_effect = Exception('Test Exception')
    mock_firehose_instance = MagicMock()
    mock_firehose.return_value = mock_firehose_instance

    send_to_valid_firehoses(data, tvevents_debug_flag=False)

    # Check for both error logs instead of just one
    expected_calls = [
        call('cnlib.firehose.Firehose error sending to Firehose - Test Exception'),
        call('send_to_valid_firehoses failed: tvid=None - Test Exception'),
    ]
    mock_logger.error.assert_has_calls(expected_calls, any_order=True)
    assert mock_logger.error.call_count == 2


@patch('app.utils.firehose.Firehose')
@patch(
    'app.utils.VALID_TVEVENTS_FIREHOSES',
    ['WARM_FIREHOSE_NAME', 'HOTE_FIREHOSE_NAME', 'HOTC_FIREHOSE_NAME'],
)
@patch('app.utils.ZOO', 'local-testing')
def test_send_to_valid_firehoses_threadpool_parallelism(mock_firehose):
    """
    Test that send_to_valid_firehoses uses ThreadPoolExecutor to send to all firehoses in parallel.
    Ensures that Firehose.send_records is called for each firehose.
    """
    data = {'key': 'value'}
    mock_firehose_instance = MagicMock()
    mock_firehose.return_value = mock_firehose_instance

    send_to_valid_firehoses(data, tvevents_debug_flag=False)

    # Each firehose should get its own Firehose object and send_records call
    expected_calls = [
        call('WARM_FIREHOSE_NAME'),
        call('HOTE_FIREHOSE_NAME'),
        call('HOTC_FIREHOSE_NAME'),
    ]
    mock_firehose.assert_has_calls(expected_calls, any_order=True)
    assert mock_firehose.call_count == 3
    assert mock_firehose_instance.send_records.call_count == 3


@patch('app.utils.firehose.Firehose')
@patch(
    'app.utils.VALID_TVEVENTS_FIREHOSES',
    ['WARM_FIREHOSE_NAME', 'HOTE_FIREHOSE_NAME'],
)
@patch('app.utils.ZOO', 'local-testing')
def test_send_to_valid_firehoses_threadpool_two_streams(mock_firehose):
    """
    Test that send_to_valid_firehoses works with two firehoses and calls send_records for each.
    """
    data = {'key': 'value'}
    mock_firehose_instance = MagicMock()
    mock_firehose.return_value = mock_firehose_instance

    send_to_valid_firehoses(data, tvevents_debug_flag=False)

    expected_calls = [
        call('WARM_FIREHOSE_NAME'),
        call('HOTE_FIREHOSE_NAME'),
    ]
    mock_firehose.assert_has_calls(expected_calls, any_order=True)
    assert mock_firehose.call_count == 2
    assert mock_firehose_instance.send_records.call_count == 2


@patch('app.utils.firehose.Firehose')
@patch(
    'app.utils.VALID_TVEVENTS_FIREHOSES',
    [],
)
@patch('app.utils.ZOO', 'local-testing')
def test_send_to_valid_firehoses_threadpool_empty_streams(mock_firehose):
    """
    Test that send_to_valid_firehoses does nothing if there are no firehoses.
    """
    data = {'key': 'value'}
    send_to_valid_firehoses(data, tvevents_debug_flag=False)
    mock_firehose.assert_not_called()

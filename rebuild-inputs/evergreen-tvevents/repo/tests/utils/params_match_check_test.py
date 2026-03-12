# pylint: disable=E0401,W0621,R0801
import logging
from app.utils import params_match_check

# Configure the logger to capture log messages for testing
LOGGER = logging.getLogger('app.utils')
LOGGER.setLevel(logging.WARNING)
log_handler = logging.StreamHandler()
LOGGER.addHandler(log_handler)


def test_params_match_check_equal():
    """
    Test params_match_check with equal URL and payload parameters.

    The function should return True when both parameters are equal.
    """
    assert params_match_check("testParam", "value", "value") is True


def test_params_match_check_not_equal(caplog):
    """
    Test params_match_check with non-equal URL and payload parameters.

    The function should return False and log a warning message when the parameters are not equal.
    """
    with caplog.at_level(logging.WARNING):
        assert params_match_check("testParam", "value1", "value2") is False
        assert (
            "testParam Mismatch. Request url and payload params do not match [value1 != value2]"
            in caplog.text
        )


def test_params_match_check_log_message(caplog):
    """
    Test params_match_check to ensure the correct warning message is logged.

    The function should log a warning message indicating the
    mismatch between URL and payload parameters.
    """
    with caplog.at_level(logging.WARNING):
        params_match_check("testParam", "value1", "value2")
    assert (
        "testParam Mismatch. Request url and payload params do not match [value1 != value2]"
        in caplog.text
    )

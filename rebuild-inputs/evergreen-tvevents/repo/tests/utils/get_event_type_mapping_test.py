# pylint: disable=E0401,W0621,R0801
import logging
from app.utils import get_event_type_mapping
from app.event_type import (
    NativeAppTelemetryEventType,
    AcrTunerDataEventType,
    PlatformTelemetryEventType,
)

LOGGER = logging.getLogger('app.utils')
LOGGER.setLevel(logging.WARNING)
log_handler = logging.StreamHandler()
LOGGER.addHandler(log_handler)


def test_get_event_type_mapping_valid():
    """
    Test get_event_type_mapping with a valid event type.

    The function should return the corresponding mapped EventType class.
    """
    assert get_event_type_mapping('NATIVEAPP_TELEMETRY') == NativeAppTelemetryEventType
    assert get_event_type_mapping('ACR_TUNER_DATA') == AcrTunerDataEventType
    assert get_event_type_mapping('PLATFORM_TELEMETRY') == PlatformTelemetryEventType


def test_get_event_type_mapping_invalid(caplog):
    """
    Test get_event_type_mapping with an invalid event type.

    The function should return None and log a warning message
    when the event type does not exist in the mapping.
    """
    with caplog.at_level(logging.WARNING):
        assert get_event_type_mapping('INVALID_EVENT_TYPE') is None
        assert (
            'generate_output: Mapping for EventType INVALID_EVENT_TYPE does not exist'
            in caplog.text
        )


def test_get_event_type_mapping_none():
    """
    Test get_event_type_mapping with None as input.

    The function should return None when the input event type is None.
    """
    assert get_event_type_mapping(None) is None


def test_get_event_type_mapping_empty_string():
    """
    Test get_event_type_mapping with an empty string as input.

    The function should return None when the input event type is an empty string.
    """
    assert get_event_type_mapping('') is None

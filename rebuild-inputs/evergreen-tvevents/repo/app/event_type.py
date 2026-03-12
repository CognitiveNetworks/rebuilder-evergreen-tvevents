from abc import abstractmethod
from opentelemetry import trace
from jsonschema import validate
from jsonschema.exceptions import ValidationError

import app
from app import meter, utils

LOGGER = app.configure_logging()

tracer = trace.get_tracer(__name__)

# Create metrics counters
VALIDATE_PAYLOAD_COUNTER = meter.create_counter(
    name="validate_payload_counter",
    description="Validating event type payload data",
)

GENERATE_EVENT_DATA_OUTPUT_COUNTER = meter.create_counter(
    name="generate_event_data_output_counter",
    description="Generate the event data output in JSON",
)

HEARTBEAT_COUNTER = meter.create_counter(
    name="heart_beat_counter",
    description="AcrTunerDataEventType heartbeats",
)

VERIFY_PANEL_DATA_COUNTER = meter.create_counter(
    name="verify_panel_data_counter",
    description="PlatformTelemetryEventType panel data validation",
)


class EventType:
    def __init__(self, payload):
        self.payload = payload
        self.event_type = payload['TvEvent']['EventType']
        self.tvid = payload['TvEvent']['tvid']
        self.event_data_params = self.payload['EventData']

    # pylint: disable=W0107
    @abstractmethod
    def validate_event_type_payload(self):
        """Ensure required fields for event_type are present"""
        pass

    # pylint: disable=W0107
    @abstractmethod
    def generate_event_data_output_json(self):
        """Generate output json for event_type ['EventData']"""
        pass


class NativeAppTelemetryEventType(EventType):
    # pylint: disable=W0246
    def __init__(self, payload):
        with tracer.start_as_current_span("NativeAppTelemetryEventType.__init__"):
            super().__init__(payload)
            self.namespace = utils.get_payload_namespace(self.event_data_params)
            self.appid = self.event_data_params.get('AppId')

    def validate_event_type_payload(self):
        with tracer.start_as_current_span(
            "NativeAppTelemetryEventType.validate_event_type_payload"
        ):
            req_fields = ['Timestamp']
            utils.verify_required_params(self.event_data_params, req_fields)
            utils.timestamp_check(self.event_data_params['Timestamp'], self.tvid)
            VALIDATE_PAYLOAD_COUNTER.add(1)

    def generate_event_data_output_json(self):
        with tracer.start_as_current_span(
            "NativeAppTelemetryEventType.generate_event_data_output_json"
        ):
            event_data_json = self.payload['EventData']
            event_data_output = {}

            event_data_output.update(
                utils.flatten_request_json(event_data_json, ignore_keys='Timestamp')
            )

            event_data_output['eventdata_timestamp'] = event_data_json['Timestamp']
            GENERATE_EVENT_DATA_OUTPUT_COUNTER.add(1)

            return event_data_output


class AcrTunerDataEventType(EventType):
    # pylint: disable=W0246
    def __init__(self, payload):
        with tracer.start_as_current_span("AcrTunerDataEventType.__init__"):
            super().__init__(payload)
            self.namespace = utils.get_payload_namespace(self.payload['TvEvent'])
            self.appid = self.payload['TvEvent'].get('appId')

    def validate_event_type_payload(self):
        with tracer.start_as_current_span(
            "AcrTunerDataEventType.validate_event_type_payload"
        ):
            is_heartbeat_event = 'Heartbeat' in self.event_data_params
            if is_heartbeat_event and self.validate_heartbeat_event():
                ed_params = self.event_data_params['Heartbeat']
            else:
                optional_params = ['channelData', 'programData']
                if not any(
                    param in self.event_data_params for param in optional_params
                ):
                    msg = 'Missing Required Param: {} tvid={} EventType={}'.format(
                        optional_params, self.tvid, self.event_type
                    )
                    raise utils.TvEventsMissingRequiredParamError(msg)

                ed_params = self.event_data_params

        if 'channelData' in ed_params:
            req_channel_data = ['majorId', 'minorId']
            utils.verify_required_params(ed_params['channelData'], req_channel_data)

        if 'resolution' in ed_params:
            req_resolution = ['vRes', 'hRes']
            utils.verify_required_params(ed_params['resolution'], req_resolution)

        VALIDATE_PAYLOAD_COUNTER.add(1)

        return True

    def validate_heartbeat_event(self):
        """Validate heartbeat event"""
        with tracer.start_as_current_span(
            "AcrTunerDataEventType.validate_heartbeat_event"
        ):
            other_params = ['channelData', 'programData']
            if any(param in self.event_data_params for param in other_params):

                # pylint: disable=C0301
                msg = 'Heartbeat cannot be sent with channel/program Data: tvid={} EventType={}'.format(
                    self.tvid, self.event_type
                )

                raise utils.TvEventsInvalidPayloadError(msg)

            hb_params = self.event_data_params['Heartbeat']
            if not any(param in hb_params for param in other_params):
                msg = (
                    'Required Heartbeat Param: {} missing: tvid={} EventType={}'.format(
                        other_params, self.tvid, self.event_type
                    )
                )
                raise utils.TvEventsMissingRequiredParamError(msg)

            HEARTBEAT_COUNTER.add(1)
            return True

    def generate_event_data_output_json(self):
        with tracer.start_as_current_span(
            "AcrTunerDataEventType.generate_event_data_output_json"
        ):
            event_data_json = self.payload['EventData']
            event_data_output = {}
            event_data_output.update(utils.flatten_request_json(event_data_json))

            if 'programdata_starttime' in event_data_output and utils.timestamp_check(
                event_data_output['programdata_starttime'], self.tvid, is_ms=False
            ):
                event_data_output['programdata_starttime'] = utils.unix_time_to_ms(
                    event_data_output['programdata_starttime']
                )

            if event_data_json.get('Heartbeat'):
                LOGGER.debug(f'Heartbeat event received for tvid={self.tvid}')
                event_data_output['eventtype'] = 'Heartbeat'

            GENERATE_EVENT_DATA_OUTPUT_COUNTER.add(1)
            return event_data_output


class PlatformTelemetryEventType(EventType):
    # pylint: disable=W0246
    def __init__(self, payload):
        with tracer.start_as_current_span("PlatformTelemetryEventType.__init__"):
            super().__init__(payload)

    panel_data_schema = {
        'required': ['Timestamp', 'PanelState', 'WakeupReason'],
        'type': 'object',
        'properties': {
            'Timestamp': {'type': 'number'},
            'PanelState': {'type': 'string', 'pattern': '^(ON|OFF|on|off|On|Off)$'},
            'WakeupReason': {'type': 'number', 'minimum': 0, 'maximum': 128},
        },
    }

    platform_telemetry_schema = {
        'required': ['PanelData'],
        'type': 'object',
        'properties': {'PanelData': panel_data_schema},
    }

    def validate_event_type_payload(self):
        with tracer.start_as_current_span(
            "PlatformTelemetryEventType.validate_event_type_payload"
        ):
            try:
                validate(
                    instance=self.event_data_params,
                    schema=self.platform_telemetry_schema,
                )
                self.validate_panel_data()
            except ValidationError as e:

                # pylint: disable=R1720
                if e.validator == 'required':
                    msg = 'Missing Required Param: {} tvid={} EventType={}'.format(
                        e.message.split()[0], self.tvid, self.event_type
                    )
                    raise utils.TvEventsMissingRequiredParamError(msg)
                else:
                    msg = 'Invalid Payload: tvid={} EventType: {}, {}-{}'.format(
                        self.tvid, self.event_type, e.path.pop(), e.message
                    )
                    raise utils.TvEventsInvalidPayloadError(msg)

            VALIDATE_PAYLOAD_COUNTER.add(1)

            return True

    def validate_panel_data(self):
        with tracer.start_as_current_span(
            "PlatformTelemetryEventType.validate_panel_data"
        ):
            pd_params = self.event_data_params['PanelData']
            validate(instance=pd_params, schema=self.panel_data_schema)
            utils.timestamp_check(pd_params['Timestamp'], self.tvid)

            VERIFY_PANEL_DATA_COUNTER.add(1)
            return True

    def generate_event_data_output_json(self):
        with tracer.start_as_current_span(
            "PlatformTelemetryEventType.generate_event_data_output_json"
        ):
            event_data_json = self.payload['EventData']
            event_data_output = {}
            event_data_output.update(utils.flatten_request_json(event_data_json))

            event_data_output['paneldata_panelstate'] = event_data_output[
                'paneldata_panelstate'
            ].upper()

            GENERATE_EVENT_DATA_OUTPUT_COUNTER.add(1)
            return event_data_output


event_type_map = {
    'NATIVEAPP_TELEMETRY': NativeAppTelemetryEventType,
    'ACR_TUNER_DATA': AcrTunerDataEventType,
    'PLATFORM_TELEMETRY': PlatformTelemetryEventType,
}

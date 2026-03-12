import sys
import json
from flask import request, jsonify

# OTEL Imports
from flask import Blueprint
from opentelemetry import trace

from app import meter, utils, configure_logging

LOGGER = configure_logging()

# Setup OTEL trace
bp = Blueprint('routes', __name__)
tracer = trace.get_tracer(__name__)

# Create metrics counters
SND_RQ_FH_COUNTER = meter.create_counter(
    name="send_request_firehose_counter",
    description="Send Data for Firehose Processing",
)


def init_routes(app):
    @app.before_request
    def log_request():
        """
        Capture incoming HTTP request and write it to log.
        """
        try:
            log_data = {
                'incoming_request': 'access_log',
                'method': request.method,
                'path': request.path,
                'remote_client': request.remote_addr,
                'request_args': request.args,
                'request_url': request.url,
                'request_values': request.values,
                'headers': dict(request.headers),
            }
            LOGGER.info(json.dumps(log_data))
        except Exception as catchall_exception:
            LOGGER.error('Exception in before_request: %s', catchall_exception)
            raise utils.TvEventsCatchallException(
                utils.TvEventsCatchallException(catchall_exception)
            ).with_traceback(sys.exc_info()[2])

    @app.route('/status', methods=['GET'])
    def status():
        """
        Simple status OK response for health checks.
        """
        return 'OK'

    @app.route("/", methods=["POST"])
    def send_request_firehose():
        """
        Route all data to this Firehose.
        """
        with tracer.start_as_current_span('send_request_firehose') as span:
            SND_RQ_FH_COUNTER.add(1)
            tvid = request.args.get('tvid')
            payload = request.get_json()

            span.set_attributes(
                {"tvid": tvid, "event_type": request.args.get('event_type', 'unknown')}
            )

            LOGGER.info('JSON Payload: %s', payload)
            try:
                utils.validate_request(request.args, payload)
                utils.push_changes_to_firehose(payload)

            except Exception as catchall_exception:
                msg = 'Exception in send_request_firehose: tvid={} msg={} payload={}'.format(
                    tvid, catchall_exception, payload
                )
                LOGGER.error(json.dumps(msg))
                raise utils.TvEventsCatchallException(
                    utils.TvEventsCatchallException(msg)
                ).with_traceback(sys.exc_info()[2])

            return "OK"

    @app.errorhandler(utils.TvEventsCatchallException)
    def handle_exceptions(error):
        try:
            e_type = error.args[0].__class__.__name__
            message = str(error.args[0])
        except IndexError:
            e_type = 'Unexpected'
            message = 'Unexpected error occurred'
        return jsonify(error=e_type, message=message), error.status_code

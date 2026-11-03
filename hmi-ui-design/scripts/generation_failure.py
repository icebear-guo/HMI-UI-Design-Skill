"""Retain an owned failed batch and write an exclusive diagnostic sidecar."""
import json
from pathlib import Path
import uuid


def preserve_failure(directory, error, **details):
    """Caller must pass a directory belonging to this invocation, never user input."""
    report = Path(directory) / ('.generation-failure-' + uuid.uuid4().hex + '.json')
    payload = {'status': 'failed', 'error': str(error), 'error_type': type(error).__name__,
               'policy': 'retain_partial_outputs; retry_in_a_fresh_directory', **details}
    try:
        with report.open('x', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        error.add_note('Retained failure report: ' + str(report))
    except OSError as report_error:
        error.add_note('Failure evidence could not be written: ' + str(report_error))
    return report

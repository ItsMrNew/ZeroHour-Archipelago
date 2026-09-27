"""Read-only executable evidence for support reports, with no process attachment."""
import hashlib
from pathlib import Path

from .compatibility import resolve
from .version import VERSION, SUPPORT_TARGET


def executable_report(path):
    path = Path(path)
    report = dict(client_version=VERSION, support_target=SUPPORT_TARGET,
                  file_name=path.name, native_layout_verified=False,
                  store_identity='Not inferred from a filename or folder',
                  runtime_modifications='Not checked by this offline report')
    try:
        raw = path.read_bytes()
        report.update(size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        # Hash is diagnostic evidence, never an override of native validation.
        addresses = resolve(raw)
        report.update(native_layout_verified=True, verified_anchors=len(addresses))
    except (OSError, ValueError) as error:
        # Avoid including a user's full local path in a shareable report.
        report['reason'] = str(error) if isinstance(error, ValueError) else f'Could not read file (OS error {error.errno}).'
    report['guidance'] = (
        'Native layout matches. This does not certify a storefront, injected DLLs, mods or live gameplay. '
        'Support for this release is limited to the stock English Steam edition.'
        if report['native_layout_verified'] else
        'Do not bypass validation. Use the stock English Steam edition; other builds need separate compatibility work.'
    )
    return report

class ProcessingCancelled(Exception):
    """Raised when the current OCR batch is cancelled by the user."""


def is_cancelled(cancel_event) -> bool:
    return bool(cancel_event is not None and cancel_event.is_set())


def raise_if_cancelled(cancel_event) -> None:
    if is_cancelled(cancel_event):
        raise ProcessingCancelled()

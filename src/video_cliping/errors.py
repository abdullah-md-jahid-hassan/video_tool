"""Errors a clip can raise. Callers catch EngineError or one subclass."""


class EngineError(Exception):
    """A clip was refused or did not finish."""


class ToolMissing(EngineError):
    """Kept so older callers can still catch it. The current cutter does not raise it."""


class InputNotFound(EngineError):
    """The source path is missing or is not a file."""


class BadRange(EngineError):
    """The start or end time cannot be used."""


class SamePath(EngineError):
    """The output path is the same file as the input."""


class Exists(EngineError):
    """The output file exists and overwrite is off."""


class OutsideEngine(EngineError):
    """The request needs a new encode. This package does not do that."""


class StreamMismatch(EngineError):
    """Files cannot be joined because their streams do not match."""


class ContainerRejected(EngineError):
    """The destination container refused a stream, and dropping it was not allowed."""

    def __init__(self, message: str, command: list[str], stderr: str) -> None:
        super().__init__(message)
        self.command = command
        self.stderr = stderr


class FfmpegFailed(EngineError):
    """PyAV could not read or write the file. stderr is the library message."""

    def __init__(self, message: str, command: list[str], stderr: str) -> None:
        super().__init__(message)
        self.command = command
        self.stderr = stderr


class OutputCheckFailed(EngineError):
    """The new file was written, but it does not match the request."""

    def __init__(self, message: str, command: list[str]) -> None:
        super().__init__(message)
        self.command = command

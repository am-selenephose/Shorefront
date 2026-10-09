"""Single-process atomic command boundary. Not a distributed writer lease."""
from copy import deepcopy
from functools import wraps
from inspect import signature
from threading import RLock


class CommittedOperationError(Exception):
    """A planning conflict whose freshly generated evidence must be committed."""

    def __init__(self, response_error: Exception):
        self.response_error = response_error
        super().__init__(str(response_error))


class OperationBoundary:
    def __init__(self, get_store, get_simulator, set_simulator):
        self._get_store = get_store
        self._get_simulator = get_simulator
        self._set_simulator = set_simulator
        self._lock = RLock()

    def command(self, function):
        @wraps(function)
        def execute(*args, **kwargs):
            with self._lock:
                simulator = self._get_simulator()
                checkpoint = simulator.checkpoint()
                conflict = None
                try:
                    with self._get_store().transaction():
                        try:
                            result = deepcopy(function(*args, **kwargs))
                        except CommittedOperationError as outcome:
                            # Staleness is a planning result, not a half-applied
                            # command. All other errors roll back, including commit.
                            conflict = outcome.response_error
                            result = None
                except BaseException:
                    simulator.restore_checkpoint(checkpoint)
                    self._set_simulator(simulator)
                    raise
                if conflict is not None:
                    raise conflict
                return result

        # Preserve evaluated endpoint types across this module's decorator.
        execute.__signature__ = signature(function, eval_str=True)
        return execute

    def query(self, function):
        @wraps(function)
        def inspect(*args, **kwargs):
            with self._lock:
                # FastAPI serializes after returning from the function; detach
                # models here so the next command cannot change that response.
                return deepcopy(function(*args, **kwargs))

        inspect.__signature__ = signature(function, eval_str=True)
        return inspect

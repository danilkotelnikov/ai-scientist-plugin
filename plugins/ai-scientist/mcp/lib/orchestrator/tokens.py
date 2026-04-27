class _Tracker:
    def __init__(self): self._data = {}
    def reset(self): self._data = {}
    def add(self, **kw):
        p, a = kw["phase"], kw["agent"]
        self._data.setdefault(p, {"prompt": 0, "completion": 0, "thinking": 0})
        self._data[p]["prompt"] += kw["prompt_tok"]
        self._data[p]["completion"] += kw["completion_tok"]
        self._data[p]["thinking"] += kw["thinking_tok"]
    def report(self): return {"by_phase": dict(self._data)}
_GLOBAL_TRACKER = _Tracker()

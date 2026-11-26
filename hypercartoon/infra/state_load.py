"""Tolerant checkpoint loading for models that gained optional control adapters. Pure Python (callables injected), so it is
testable without torch.distributed.

Old checkpoints do not contain the `.control.` parameters; loading them into a model that has the adapters would fail on the
missing keys. We try the strict way first (checkpoints saved with the adapters), then retry without the control keys and keep
the freshly (zero-)initialised adapter values."""
from typing import Callable, Dict

CONTROL_MARK = ".control."


def is_control_key(key: str) -> bool:
    return CONTROL_MARK in "." + key


def load_model_state(get_state: Callable[[], Dict], load_fn: Callable[[Dict, str], None], path: str, wrapped_key: str) -> Dict:
    """-> flat model state dict. Tries {wrapped, bare} x {with, without control keys}; raises the last error if all fail."""
    last = None
    for drop_control in (False, True):
        for wrapped in (True, False):
            full = get_state()
            sd = {k: v for k, v in full.items() if not (drop_control and is_control_key(k))}
            try:
                if wrapped:
                    holder = {wrapped_key: sd}
                    load_fn(holder, path)
                    out = holder[wrapped_key]
                else:
                    load_fn(sd, path)
                    out = sd
            except (RuntimeError, KeyError) as e:
                last = e
                continue
            if drop_control:
                for k, v in full.items():
                    out.setdefault(k, v)  # the adapters stay as initialised (zeros)
            return out
    raise last  # type: ignore[misc]

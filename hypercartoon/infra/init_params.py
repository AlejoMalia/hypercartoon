"""Parameter initialisation (torch only). Modules own their init when they say so: Hyper layers and the zero-initialised
control adapters (their inner Linear layers must never be re-randomised)."""
import torch


def init_parameters(model, hyper_cls, control_cls, initializer_range: float = 0.02) -> None:
    owned = set()
    for module in model.modules():
        if isinstance(module, control_cls):
            module.init_weights()
            owned.update(id(m) for m in module.modules())

    for module in model.modules():
        if id(module) in owned:
            continue

        if isinstance(module, hyper_cls):
            # Let the Hyper module handle its own initialization (it is complicated)
            module.init_weights()
            continue

        for name, param in module.named_parameters(recurse=False):
            if param is None:
                continue

            if "bias" in name:
                torch.nn.init.zeros_(param)
            else:
                torch.nn.init.normal_(param, mean=0.0, std=initializer_range)

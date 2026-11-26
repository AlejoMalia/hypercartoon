"""script-hypercartoon's deterministic screenplay-reading engine, vendored in vendor/script-hypercartoon/ (calqued sources + one
self-contained bundle). Runs with plain Node >= 18: no network, no paid API, no keys, no dependency on the original project. Only
the basic screenplay path is included (scene/camera/dialogue structure, pacing tension, simple open threads); the generic,
cross-domain node-graph reading of arbitrary prose and the passthrough to arbitrary vendored functions are not exposed here."""
import json
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "vendor", "script-hypercartoon", "engines.mjs")


def available() -> bool:
    return bool(shutil.which("node")) and os.path.exists(BUNDLE)


class ScriptEngineBridge:
    def __init__(self):
        if not available():
            raise RuntimeError("Node.js >= 18 or vendor/script-hypercartoon/engines.mjs missing")
        self.p = subprocess.Popen(["node", os.path.join(HERE, "engines_runner.mjs")], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                  env={"PATH": os.environ.get("PATH", "")})  # minimal environment

    def _req(self, **kw) -> dict:
        self.p.stdin.write(json.dumps(kw) + "\n")
        self.p.stdin.flush()
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("engine process ended unexpectedly")
            if line.startswith("@@"):
                r = json.loads(line[2:])
                if not r.get("ok"):
                    raise RuntimeError(r.get("error"))
                return r

    def analyze(self, text: str, language: str = "auto", completion: bool = True) -> dict:
        """Screenplay reading (+ open threads)."""
        return self._req(op="screenplay", text=text, language=language, completion=completion)

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

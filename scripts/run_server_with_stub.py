"""联调用启动器：把 _re/stub_oracle.py 伪装成参考引擎后启动真实服务。

等 pr_engine/reference/oracle.py 真正就绪后，这个文件就不需要了——
直接 `python app/server.py` 即可。
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_stub_oracle", ROOT / "_re" / "stub_oracle.py")
_stub = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stub)  # type: ignore[union-attr]

_pkg = types.ModuleType("pr_engine.reference")
_pkg.__path__ = []  # type: ignore[attr-defined]
_pkg.oracle = _stub  # type: ignore[attr-defined]
sys.modules["pr_engine.reference"] = _pkg
sys.modules["pr_engine.reference.oracle"] = _stub

from app.server import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

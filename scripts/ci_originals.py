"""Standard-library-only entrypoint for reviewed private CI originals."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "ci_originals", Path(__file__).resolve().parents[1] / "src/hbi/ci_originals.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.main()

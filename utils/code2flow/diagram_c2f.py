import subprocess
from pathlib import Path

from code2flow import code2flow

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
_IMAGES = _ROOT / "images" / "code2flow"
_GV = _HERE / "cats_pkg.gv"
_PNG = _IMAGES / "cats_code2flow.png"

code2flow(
    raw_source_paths=[str(_ROOT / "cats")],
    output_file=str(_GV),
    hide_legend=False,
    exclude_namespaces=["CoD", "cod", "legacy"],
)

_IMAGES.mkdir(parents=True, exist_ok=True)
with open(_PNG, "wb") as fh:
    subprocess.run(["dot", "-Tpng", str(_GV)], stdout=fh, check=True)
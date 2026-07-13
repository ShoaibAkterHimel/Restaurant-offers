
from __future__ import annotations

import subprocess
import sys

for script in ("src/scan.py", "src/render.py"):
    print("+", sys.executable, script)
    subprocess.run([sys.executable, script], check=True)
print("Done. Open docs/index.html.")

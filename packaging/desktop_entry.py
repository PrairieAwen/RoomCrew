"""冻结应用的薄入口；功能入口统一留在后端包内。"""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend/src"))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop/src"))

from roomcrew_desktop.__main__ import main

if __name__ == "__main__":
    main()

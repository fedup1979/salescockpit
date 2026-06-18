import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sales_cockpit.db import reset_demo_data


if __name__ == "__main__":
    reset_demo_data()
    print("Sales Cockpit demo scenarios reset.")

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

VIEW_NAMES = [
    "mart_channel_economics",
    "mart_customer_ltv",
    "mart_cohort_retention",
]


def export_views_to_csv() -> None:
    engine = create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', '')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'etl_portfolio')}"
    )

    export_dir = PROJECT_ROOT / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    for view_name in VIEW_NAMES:
        df = pd.read_sql(f'SELECT * FROM "{view_name}"', engine)
        output_path = export_dir / f"{view_name}.csv"
        df.to_csv(output_path, index=False)
        print(f"Saved {output_path}")


if __name__ == "__main__":
    export_views_to_csv()

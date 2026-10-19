import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://extractor:extractor@localhost:5546/extractor")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("MODEL", "qwen2.5:7b")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
# Amounts may differ by this much (absolute) before validation complains,
# to absorb rounding on printed invoices.
AMOUNT_TOLERANCE = float(os.getenv("AMOUNT_TOLERANCE", "1"))

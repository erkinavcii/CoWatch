import os
import sys
import tempfile
from pathlib import Path

# Settings are read once, at first import: point them at a throwaway data folder.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="cowatch-test-")
os.environ["COWATCH_DOTENV"] = ""  # this computer's .env (Funnel, encoder...) stays out of the tests
os.environ["ADDONS_BUILTIN"] = "0"  # no requests to Stremio's add-ons from the tests
os.environ.setdefault("ACCESS_KEY", "test-key")
os.environ["OPENSUBTITLES_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

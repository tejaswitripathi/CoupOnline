import sys
from pathlib import Path

# coup-core is a sibling directory, not an installable package ("coup-core" isn't
# even a valid Python module name due to the hyphen), so make its modules
# importable by flat name instead -- matching how coup-core's own files import
# each other (e.g. resolver.py does `from state import State`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "coup-core"))

from fastapi import FastAPI

from routes import router

app = FastAPI(title="Coup Online")
app.include_router(router)

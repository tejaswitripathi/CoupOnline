import sys
from pathlib import Path

# coup-core is a sibling directory, not an installable package ("coup-core" isn't
# even a valid Python module name due to the hyphen), so make its modules
# importable by flat name instead -- matching how coup-core's own files import
# each other (e.g. resolver.py does `from state import State`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "coup-core"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import router

app = FastAPI(title="Coup Online")

# The renderer runs under Vite (http://127.0.0.1:5173) in dev and under file://
# (origin "null") when packaged into Electron, so allow both to reach the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "null",
    ],
    allow_origin_regex=r"^file://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# conftest.py

import os, sys
root = os.path.dirname(__file__)
if root not in sys.path:
    sys.path.insert(0, root)

# Tell pytest to load the pytest_asyncio plugin
pytest_plugins = ("pytest_asyncio",)
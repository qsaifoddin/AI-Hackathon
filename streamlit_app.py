import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(__file__))

from app.db.database import init_db

# Auto-initialize database on Streamlit Cloud container startup
init_db()

# Run main Streamlit app
from app.ui.main import *

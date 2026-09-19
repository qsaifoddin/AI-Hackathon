import sys
import os

# Add root directory to sys.path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app.db.database import init_db

# Auto-initialize database on startup
init_db()

# Execute main Streamlit UI on EVERY rerun
main_ui_path = os.path.join(root_dir, "app", "ui", "main.py")
with open(main_ui_path, "r", encoding="utf-8") as f:
    code = compile(f.read(), main_ui_path, "exec")
    exec(code, globals())

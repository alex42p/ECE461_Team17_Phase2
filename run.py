# import app_runner_bootstrap
import sys
import os

# Add the project's src folder to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.app import app

if __name__ == "__main__":
    # Initialize database and create default admin user
    app.run(host="0.0.0.0", port=8080)

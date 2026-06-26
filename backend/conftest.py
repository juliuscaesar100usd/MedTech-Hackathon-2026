"""Ensure `import app...` resolves when running pytest from the backend dir."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

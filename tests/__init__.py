"""Main file for tests -- just adds topleveldir to paths."""
import sys
import os

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

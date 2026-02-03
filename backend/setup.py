"""
Setup configuration for intelligent-email-assistant backend package.

This setup.py makes the backend directory installable as a Python package,
enabling proper module imports: from backend.xxx import yyy

Usage:
    pip install -e .        # Editable/development install
    pip install .           # Production install
"""
from setuptools import setup, find_packages
import os

# Read requirements from requirements.txt
def read_requirements():
    """Parse requirements.txt and return list of dependencies."""
    req_file = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    with open(req_file, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name="intelligent-email-assistant",
    version="1.0.0",
    description="AI-powered email assistant with OAuth, NLP, and multi-tenant support",
    author="Iyadh Bouzghiba",
    author_email="",
    python_requires=">=3.9",

    # Package discovery
    packages=find_packages(
        where=".",
        exclude=["tests*", "*.tests", "*.tests.*", "tests.*", "src_backup*"]
    ),

    # Include package data
    include_package_data=True,
    package_data={
        "": ["*.sql", "*.json", "*.yaml", "*.yml"],
    },

    # Dependencies from requirements.txt
    install_requires=read_requirements(),

    # Entry points for CLI commands (optional)
    entry_points={
        "console_scripts": [
            "email-assistant=backend.infrastructure.worker_entry:main",
        ],
    },

    # Classifiers for PyPI (if publishing)
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],

    # Ensure Python 3.9+ compatibility
    zip_safe=False,
)

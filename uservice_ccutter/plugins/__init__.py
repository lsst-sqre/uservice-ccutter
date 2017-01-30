"""Plugins for the Cookiecutter make-me-a-thing service"""
# Actual project types live in the projecttypes directory.
from .finalize import finalize
from .substitute import substitute
__all__ = ["finalize", "substitute"]

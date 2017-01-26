"""Plugins for the Cookiecutter make-me-a-thing service"""
from .finalize import finalize
from .substitute import substitute
__all__ = ["finalize", "substitute"]

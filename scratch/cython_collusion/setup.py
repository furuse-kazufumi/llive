# SPDX-License-Identifier: Apache-2.0
"""Cython build script for collusion_score kernel scratch comparison.

Usage:
    cd scratch/cython_collusion
    .venv/Scripts/python.exe setup.py build_ext --inplace
"""

from setuptools import setup
from Cython.Build import cythonize

setup(
    name="collusion_cython",
    ext_modules=cythonize(
        ["collusion.pyx"],
        compiler_directives={
            "boundscheck": False,
            "wraparound": False,
            "cdivision": True,
            "language_level": 3,
        },
    ),
)

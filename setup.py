# Copyright 2019, Ryan P. Kelly.

from setuptools import setup


setup(
    name="terroir",
    version="0.3",
    description="terraform templating wrapper",
    author="Ryan P. Kelly",
    author_email="ryan@ryankelly.us",
    url="https://github.com/f0rk/terroir",
    install_requires=[
        "pexpect",
        "jinja2",
    ],
    tests_require=[
        "pytest",
    ],
    package_dir={"": "lib"},
    packages=["terroir"],
    scripts=["bin/terroir"],
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3",
    ],
)

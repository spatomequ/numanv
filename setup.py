#!/usr/bin/python

from setuptools import setup, find_packages

tests_require=[
    'nose',
    'mock',
]

setup(
    name="sunspear",
    license='Apache License 2.0',
    version="0.1.0-ALPHA",
    description="Activity streams backed by Riak.",
    zip_safe=False,
    long_description=open('README.rst', 'r').read(),
    author="Numan Sachwani",
    author_email="numan856@gmail.com",
    url="https://github.com/numan/sunspear",
    packages=find_packages(exclude=['tests']),
    test_suite='nose.collector',
    install_requires=[
        'nydus==0.10.4',
        'protobuf==2.4.1',
        'riak==1.5.1',
        'python-dateutil==1.5',
    ],
    dependency_links=[
        'https://github.com/numan/nydus/tarball/0.10.4#egg=nydus-0.10.4',
    ],
    tests_require=tests_require,
    extras_require={"test": tests_require, "nosetests": tests_require},
    include_package_data=True,
    classifiers=[
        "Intended Audience :: Developers",
        'Intended Audience :: System Administrators',
        "Programming Language :: Python",
        "Topic :: Software Development",
        "Topic :: Utilities",
    ],
)

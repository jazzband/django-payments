#!/usr/bin/env python
from setuptools import setup, find_packages

setup(
    name='django-payments',
    author='Mirumee Software',
    author_email='hello@mirumee.com',
    description='Universal payment handling for Django',
    version='0.3.2',
    url='http://github.com/mirumee/django-payments',
    packages=find_packages(),
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Framework :: Django',
    ],
    install_requires=['requests>=1.2.0', 'pycrypto', 'PyJWT'],
    include_package_data=True,
    zip_safe=False)

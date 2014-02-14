#!/usr/bin/env python
from setuptools import setup, find_packages
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_settings')

setup(
    name='django-payments',
    author='Mirumee Software',
    author_email='hello@mirumee.com',
    description='Universal payment handling for Django',
    version='0.4.1',
    url='http://github.com/mirumee/django-payments',
    packages=find_packages(),
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Framework :: Django',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules'],
    install_requires=[
        'braintree>=2.24.1',
        'Django>=1.5',
        'pycrypto>=2.6',
        'PyJWT',
        'requests>=1.2.0',
        'stripe>=1.9.8'],
    include_package_data=True,
    test_suite='payments.tests',
    zip_safe=False)

#!/usr/bin/env python
from setuptools import setup
from setuptools.command.test import test as TestCommand
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_settings')

PACKAGES = [
    'payments',
    'payments.authorizenet',
    'payments.braintree',
    'payments.coinbase',
    'payments.cybersource',
    'payments.dummy',
    'payments.dotpay',
    'payments.paypal',
    'payments.sagepay',
    'payments.sofort',
    'payments.stripe',
    'payments.wallet']

REQUIREMENTS = [
    'braintree>=3.14.0',
    'Django>=2.2',
    'cryptography>=1.1.0',
    'PyJWT>=1.3.0',
    'requests>=1.2.0',
    'stripe>=2.6.0',
    'suds-jurko>=0.6',
    'xmltodict>=0.9.2']


# Braintree does not support Python 2 from version 4.0.0
if sys.version_info[0] <= 2:
    REQUIREMENTS[0] = 'braintree>=3.14.0,<4.0.0'


class PyTest(TestCommand):
    user_options = [('pytest-args=', 'a', "Arguments to pass to py.test")]
    test_args = []

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = []

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(self.pytest_args)
        sys.exit(errno)


setup(
    name='django-payments',
    author='Mirumee Software',
    author_email='hello@mirumee.com',
    description='Universal payment handling for Django',
    version='0.13.0',
    url='http://github.com/mirumee/django-payments',
    packages=PACKAGES,
    include_package_data=True,
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django :: 2.2',
        'Framework :: Django :: 3.0',
        'Framework :: Django :: 3.1',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Framework :: Django',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules'],
    install_requires=REQUIREMENTS,
    cmdclass={
        'test': PyTest},
    tests_require=[
        'pytest',
        'pytest-django'],
    zip_safe=False)

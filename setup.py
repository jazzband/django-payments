#!/usr/bin/env python
from setuptools import setup
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_settings')

PACKAGES = [
    'payments',
    'payments.authorizenet',
    'payments.braintree',
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
    'Django>=1.5',
    'pycrypto>=2.6',
    'PyJWT>=1.3.0',
    'requests>=1.2.0',
    'stripe>=1.9.8',
    'suds-jurko>=0.6',
    'xmltodict>=0.9.2']

setup(
    name='django-payments',
    author='Mirumee Software',
    author_email='hello@mirumee.com',
    description='Universal payment handling for Django',
    version='0.7.0',
    url='http://github.com/mirumee/django-payments',
    packages=PACKAGES,
    include_package_data=True,
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Framework :: Django',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules'],
    install_requires=REQUIREMENTS,
    tests_require=['mock'],
    test_suite='payments.tests',
    zip_safe=False)

#!/usr/bin/env python
from setuptools import setup

PACKAGES = [
    "payments",
    "payments.authorizenet",
    "payments.braintree",
    "payments.coinbase",
    "payments.cybersource",
    "payments.dummy",
    "payments.dotpay",
    "payments.paypal",
    "payments.sagepay",
    "payments.sofort",
    "payments.stripe",
]


setup(
    name="django-payments",
    author="Mirumee Software",
    author_email="hello@mirumee.com",
    description="Universal payment handling for Django",
    long_description=open("README.rst").read(),
    use_scm_version={
        "version_scheme": "post-release",
        "write_to": "payments/version.py",
    },
    setup_requires=["setuptools_scm"],
    url="http://github.com/jazzband/django-payments",
    packages=PACKAGES,
    include_package_data=True,
    classifiers=[
        "Environment :: Web Environment",
        "Framework :: Django :: 2.2",
        "Framework :: Django :: 3.0",
        "Framework :: Django :: 3.1",
        "Framework :: Django :: 3.2",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Framework :: Django",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    install_requires=[
        "Django>=2.2",
        "requests>=1.2.0",
    ],
    extras_require={
        "braintree": ["braintree>=3.14.0"],
        "cybersource": ["suds-jurko>=0.6"],
        "mercadopago": ["mercadopago<1.0.0"],
        "sagepay": ["cryptography>=1.1.0"],
        "sofort": ["xmltodict>=0.9.2"],
        "stripe": ["stripe>=2.6.0"],
    },
    zip_safe=False,
)

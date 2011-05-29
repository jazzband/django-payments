from setuptools import setup, find_packages
 
setup(
    name='django-payments',
    version='0.1',
    description='Django Payments app',
    url='http://github.com/dantium/django-payments',
    packages=find_packages(),
    classifiers=[
        'Development Status :: 0.1 - Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Framework :: Django',
    ],
    include_package_data=True,
    zip_safe=False,
    install_requires=['setuptools'],
    setup_requires=['setuptools_git'],
)
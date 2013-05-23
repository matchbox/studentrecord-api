from setuptools import setup

VERSION = '0.1'

setup(
    name='studentrecord',
    version=VERSION,
    license='MIT',
    author='Paul Swartz',
    author_email='pswartz@matchbox.net',
    description='Python implementation of the StudentRecord.com API',
    py_modules=['studentrecord'],
    platforms='any',
    install_requires=[
        'requests',
        'jinja2',
        'yaml',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
)

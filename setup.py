from setuptools import setup
import studentrecord

VERSION = '0.1'

setup(
    name='studentrecord',
    version=VERSION,
    license='MIT',
    author='Paul Swartz',
    author_email='pswartz@matchbox.net',
    description='Python implementation of the StudentRecord.com API',
    long_description=studentrecord.__doc__,
    py_modules=['studentrecord'],
    platforms='any',
    install_requires=[
        'requests',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
)

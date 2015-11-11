from distutils.core import setup
import subprocess, os

setup(
	name='pymoku',
	version='0.1',
	author='Ben Nizette',
	author_email='ben.nizette@liquidinstruments.com',
	packages=['pymoku',],
	license='Commercial',
	long_description=open('README').read(),
)


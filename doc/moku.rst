
Moku:Lab
========

All interaction with pymoku starts with the creation of a :any:`Moku` object. This can be done directly
if one already knows the IP address of the target, or by using one of the *get_by_* functions to look
up a Moku by Name or Serial Number.

.. note:: Use of the *get_by_* functions require that your platform has access to *libdnssd*. This
	is provided on Linux by the Avahi libdnssd compatibility library. For example, on Ubuntu::

		sudo apt-get install libavahi-compat-libdnssd1

A :any:`Moku` object is useful only for flashing lights until it's bound to an instrument. This process
defines the functionality of the Moku:Lab. For examples on how to bind an instrument, see the examples
on each of the instrument pages below.

.. currentmodule:: pymoku

--------------
The Moku Class
--------------

.. autoclass:: pymoku.Moku
	:members:

------------------
Instrument Classes
------------------

.. autoclass:: pymoku.instruments.MokuInstrument

.. autoclass:: pymoku.instruments.DataFrame

Instruments
^^^^^^^^^^^

.. toctree::
	:maxdepth: 1

	oscilloscope
	siggen

----------
Exceptions
----------

.. Can't get automodule to work properly for this..

.. autoexception:: MokuException
.. autoexception:: MokuNotFound
.. autoexception:: NetworkError
.. autoexception:: DeployException
.. autoexception:: StreamException
.. autoexception:: InvalidOperationException
.. autoexception:: ValueOutOfRangeException
.. autoexception:: NotDeployedException
.. autoexception:: FrameTimeout


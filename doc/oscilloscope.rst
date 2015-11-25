
Moku:Lab Oscilloscope
=====================

The Oscilloscope instrument provides time-domain views of voltages. It contains a built-in Waveform Synthesiser/ Signal Generator that can control the Moku:Lab DAC outputs as well.

In normal operation, the Oscilloscope shows the signal present on the two ADC inputs but it can be set to loop back the signals being synthesised. This loopback takes up a channel (only two signals in total may be viewed at once).  Data is provided at the :any:`framerate` in the form of :any:`DataFrame` objects. These objects contain the channel data and the required metadata to interpret them.

The Oscilloscope instrument also provides a facility for datalogging. The user should put the instrument in to Roll mode and turn the span down such that fewer than 10ksmps are being generated; then the datalogger may be enabled and all raw data points will be saved to the Moku:Lab's SD card.

Many functions or attributes must be :any:`commit()'d <pymoku.instruments.Oscilloscope.commit>` before taking effect. This allows you to set multiple settings across multiple calls and have them take effect atomically (e.g. set all output waveforms and input sampling at once).

.. warning:: The requirement to :any:`commit() <pymoku.instruments.Oscilloscope.commit>` before a change takes effect is the most common cause of program malfunctions when interfacing with the Moku:Lab. Any *set_* or *synth_* function, or any direct manipulation of attributes such as :any:`framerate`, must be explicitly committed.


-------------------
The DataFrame Class
-------------------

.. autoclass:: pymoku.instruments.DataFrame

	.. Don't use :members: as it doesn't handle instance attributes well. Directives in the source code list required attributes directly.


----------------------
The Oscilloscope Class
----------------------

.. autoclass:: pymoku.instruments.Oscilloscope
	:members:
	:inherited-members:


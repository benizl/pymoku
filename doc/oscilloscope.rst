
Moku:Lab Oscilloscope
=====================

The Oscilloscope instrument provides time-domain views of voltages. It contains a built-in Waveform Synthesiser/ Signal Generator that can control the Moku:Lab DAC outputs as well.

In normal operation, the Oscilloscope shows the signal present on the two ADC inputs but it can be set to loop back the signals being synthesised. This loopback takes up a channel (only two signals in total may be viewed at once).  Data is provided at the :any:`framerate` in the form of :any:`DataFrame` objects. These objects contain the channel data and the required metadata to interpret them.

The Oscilloscope instrument also provides a facility for datalogging. The user should put the instrument in to Roll mode and turn the span down such that fewer than 10ksmps are being generated; then the datalogger may be enabled and all raw data points will be saved to the Moku:Lab's SD card.

Many functions or attributes must be :any:`commit()'d <pymoku.instruments.Oscilloscope.commit>` before taking effect. This allows you to set multiple settings across multiple calls and have them take effect atomically (e.g. set all output waveforms and input sampling at once).

.. note:: The requirement to :any:`commit() <pymoku.instruments.Oscilloscope.commit>` before a change takes effect is the most common cause of program malfunctions when interfacing with the Moku:Lab. Any *set_* or *synth_* function, or any direct manipulation of attributes such as :any:`framerate`, must be explicitly committed.

Example Usage
-------------

.. TODO: Move back in to source file?

.. code-block:: python

	from pymoku import Moku
	from pymoku.instruments import *

	import matplotlib.pyplot as plt

	# Get a reference to the Moku:Lab and attach an Oscilloscope instrument
	m = Moku.get_by_name("Example")
	i = Oscilloscope()
	m.attach_instrument(i)
	
	i.set_defaults()
	i.set_timebase(-0.005, 0.005) # 10ms span centred around the trigger point
	i.set_frontend(1, ac=True) # AC-couple channel 1
	i.set_trigger(OSC_TRIG_CH1, OSC_EDGE_RISING, 0.5) # Channel 1 trigger, rising edge, 0.5V. Defaults to AUTO mode, no hysteresis.
	i.commit()

	# Set up a two-trace plot
	line1, = plt.plot([])
	line2, = plt.plot([])
	plt.ion()
	plt.show()
	plt.grid(b=True)
	plt.ylim([-2000, 2000])
	plt.xlim([0,1024])

	try:
		while True:
			# Get frames and plot the data until interrupted
			frame = i.get_frame()

			plt.pause(0.001)
			line1.set_ydata(frame.ch1)
			line2.set_ydata(frame.ch2)
			line1.set_xdata(range(len(frame.ch1)))
			line2.set_xdata(range(len(frame.ch2)))

			plt.draw()
	finally:
		m.close()


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


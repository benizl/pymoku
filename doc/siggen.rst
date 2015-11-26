
Moku:Lab Waveform Generator
===========================


Waveform Synthesis Instrument.

Variously known as Waveform Synthesiser, Waveform Generator, Signal Generator etc.

Supports the generation of Sine and Square waveforms. By manipulation of the Square rise and fall
times, ramp and sawtooth waves can be synthesised as well.

For frequencies over approximately 30MHz, the Square Wave can be subject to edge jitter due to the
DDS technology used in the Moku:Lab. If this is a problem, and you don't need duty-cycle control,
a clipped Sine Wave can provide better performance.

The output waveforms can also me frequency, phase or amplitude modulated. The modulation source can
be another internally-generated Sinewave, the associated ADC input channel or the other output channel.
That other output channel may itself be modulated in some way, allowing the creation of very complex
waveforms.

.. note:: The requirement to :any:`commit() <pymoku.instruments.Oscilloscope.commit>` before a change takes effect is the most common cause of program malfunctions when interfacing with the Moku:Lab. Any *set_* or *synth_* function, or any direct manipulation of attributes such as :any:`framerate`, must be explicitly committed.

Example Usage
-------------

.. TODO: Move back in to the source file?

.. code-block:: python

	from pymoku import Moku
	from pymoku.instruments import SignalGenerator
	m = Moku.get_by_name("Example")
	i = SignalGenerator()
	m.attach_instrument(i)

	i.synth_sinewave(1, 1.0, 1000) # Channel 1 Sine wave, 1Vpp, 1kHz
	i.synth_squarewave(2, 0.5, 2000, duty=0.1) # Channel 2 Square Wave, 0.5Vpp, 2kHz, 10% duty cycle
	i.commit() # Apply changes atomically (both channels will start at once)

	m.close()



The SignalGenerator Class
-------------------------

.. autoclass:: pymoku.instruments.SignalGenerator
	:members:
	:inherited-members:


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

-------------------------
The SignalGenerator Class
-------------------------

.. autoclass:: pymoku.instruments.SignalGenerator
	:members:
	:inherited-members:

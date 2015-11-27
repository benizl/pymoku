
import math
import logging

from pymoku import ValueOutOfRangeException

from _instrument import *
import _instrument
import _frame_instrument

# Annoying that import * doesn't pick up function defs??
_sgn = _instrument._sgn
_usgn = _instrument._usgn

log = logging.getLogger(__name__)

REG_SG_WAVEFORMS	= 96
REG_SG_MODSOURCE	= 123
REG_SG_PRECLIP		= 124

REG_SG_FREQ1_L		= 97
REG_SG_FREQ1_H		= 105
REG_SG_PHASE1		= 98
REG_SG_AMP1			= 99
REG_SG_MODF1_L		= 100
REG_SG_MODF1_H		= 101
REG_SG_T01			= 102
REG_SG_T11			= 103
REG_SG_T21			= 104
REG_SG_RISERATE1_L	= 106
REG_SG_FALLRATE1_L	= 107
REG_SG_RFRATE1_H	= 108
REG_SG_MODA1		= 121

REG_SG_FREQ2_L		= 109
REG_SG_FREQ2_H		= 117
REG_SG_PHASE2		= 110
REG_SG_AMP2			= 111
REG_SG_MODF2_L		= 112
REG_SG_MODF2_H		= 113
REG_SG_T02			= 114
REG_SG_T12			= 115
REG_SG_T22			= 116
REG_SG_RISERATE2_L	= 118
REG_SG_FALLRATE2_L	= 119
REG_SG_RFRATE2_H	= 120
REG_SG_MODA2		= 122

SG_WAVE_SINE		= 0
SG_WAVE_SQUARE		= 1
SG_WAVE_NOISE		= 2

SG_MOD_NONE			= 0
SG_MOD_AMPL			= 1
SG_MOD_FREQ			= 2
SG_MOD_PHASE		= 4

SG_MODSOURCE_INT	= 0
SG_MODSOURCE_ADC	= 1
SG_MODSOURCE_DAC	= 2

_SG_FREQSCALE		= 1e9 / 2**48
_SG_PHASESCALE		= 1.0 / 2**32
_SG_AMPSCALE		= 4.0 / 2**16
_SG_DEPTHSCALE		= 1.0 / 2**15

class SignalGenerator(MokuInstrument):
	"""

	.. automethod:: pymoku.instruments.SignalGenerator.__init__

	.. attribute:: type
		:annotation: = "signal_generator"

		Name of this instrument.

	.. attribute:: out1_enable
		:annotation: = False

		Output 1 On or Off. Automatically turned on when *synth_* is called on this channel


	.. attribute:: out2_enable
		:annotation: = False

		Output 2 On or Off. Automatically turned on when *synth_* is called on this channel

	"""
	def __init__(self):
		""" Create a new SignalGenerator instance, ready to be attached to a Moku."""
		super(SignalGenerator, self).__init__()
		self.id = 4
		self.type = "signal_generator"

	def set_defaults(self):
		""" Set sane defaults.
		Defaults are outputs off, amplitudes and frequencies zero."""
		super(SignalGenerator, self).set_defaults()
		self.out1_enable = False
		self.out2_enable = False
		self.out1_amplitude = 0
		self.out2_amplitude = 0
		self.out1_frequency = 0
		self.out2_frequency = 0

	def synth_sinewave(self, ch, amplitude, frequency, offset=0, clip=0):
		""" Generate a Sine Wave with the given parameters on the given channel.

		:type ch: int
		:param ch: Channel on which to generate the wave

		:type amplitude: float, volts
		:param amplitude: Waveform peak-to-peak amplitude

		:type frequency: float
		:param frequency: Freqency of the wave

		:type offset: float, volts
		:param offset: DC offset applied to the waveform

		:type clip: float, 0-1
		:param clip: Fraction of the waveform to clip off top and bottom. Sine waves with high clipping ratios can be used to generate
			high-quality, high-speed square waves where a normal square would suffer from edge jitter.  If the clipping ratio is non-zero,
			the amplitude field refers to the size of the clipped output waveform."""
		if ch == 1:
			self.out1_waveform = SG_WAVE_SINE
			self.out1_enable = True
			self.out1_amplitude = amplitude
			self.out1_frequency = frequency
			self.out1_offset = offset
			# TODO: Clip
		elif ch == 2:
			self.out2_waveform = SG_WAVE_SINE
			self.out2_enable = True
			self.out2_amplitude = amplitude
			self.out2_frequency = frequency
			self.out2_offset = offset
		else:
			raise ValueOutOfRangeException("Invalid Channel")

	def synth_squarewave(self, ch, amplitude, frequency, offset=0, duty=0.5, riserate=0, fallrate=0):
		""" Generate a Square Wave with given parameters on the given channel.

		:type ch: int
		:param ch: Channel on which to generate the wave

		:type amplitude: float, volts
		:param amplitude: Waveform peak-to-peak amplitude

		:type frequency: float
		:param frequency: Freqency of the wave

		:type offset: float, volts
		:param offset: DC offset applied to the waveform

		:type duty: float, 0-1
		:param duty: Fractional duty cycle

		:type riserate: float, 0-1
		:param riserate: Fraction of a cycle taken for the waveform to rise

		:type fallrate: float 0-1
		:param fallrate: Fraction of a cycle taken for the waveform to fall"""
		if ch == 1:
			self.out1_waveform = SG_WAVE_SQUARE
			self.out1_enable = True
			self.out1_amplitude = amplitude
			self.out1_frequency = frequency
			self.out1_offset = offset
			# TODO: Duty, rise, fall
		elif ch == 2:
			self.out2_waveform = SG_WAVE_SQUARE
			self.out2_enable = True
			self.out2_amplitude = amplitude
			self.out2_frequency = frequency
			self.out2_offset = offset
		else:
			raise ValueOutOfRangeException("Invalid Channel")

	def synth_rampwave(self, ch, amplitude, frequency, offset=0, symmetry=0.5):
		""" Generate a Ramp with the given parameters on the given channel.

		This is a wrapper around the Square Wave generator, using the *riserate* and *fallrate*
		parameters to form the ramp.

		:type ch: int
		:param ch: Channel on which to generate the wave

		:type amplitude: float, volts
		:param amplitude: Waveform peak-to-peak amplitude

		:type frequency: float
		:param frequency: Freqency of the wave

		:type offset: float, volts
		:param offset: DC offset applied to the waveform

		:type symmetry: float, 0-1
		:param symmetry: Fraction of the cycle rising."""
		self.synth_squarewave(ch, amplitude, frequency,
			offset=offset, duty=symmetry,
			riserate=amplitude / frequency / symmetry,
			fallrate=amplitude / frequency / (1 - symmetry))

	def synth_modulate(self, ch, type, source, depth, frequency=0):
		"""
		Set up modulation on an output channel.

		:type ch: int
		:param ch: Channel to modulate

		:type type: SG_MOD_NONE, SG_MOD_AMPL, SG_MOD_FREQ, SG_MOD_PHASE
		:param type:  Modulation type. Respectively Amplitude, Frequency and Phase modulation.

		:type source: SG_MODSOURCE_INT, SG_MODSOURCE_ADC, SG_MODSOURCE_DAC
		:param source: Modulation source. Respectively Internal Sinewave, Associated ADC Channel or Opposite DAC Channel.

		:type depth: float 0-1
		:param depth: Fractional modulation depth

		:type frequency: float
		:param frequency: Frequency of internally-generated sine wave modulation. This parameter is ignored if the source is set to ADC or DAC.
		"""
		if ch == 1:
			self.out1_modulation = type
			self.out1_modsource = source
			self.mod1_frequency = frequency
			self.mod1_amplitude = depth * self.out1_amplitude

_siggen_reg_hdl = [
	('out1_enable',		REG_SG_WAVEFORMS,	lambda s, old: (old & ~1) | int(s) if int(s) in [0, 1] else None,
											lambda rval: rval & 1),
	('out2_enable',		REG_SG_WAVEFORMS,	lambda s, old: (old & ~2) | int(s) << 1 if int(s) in [0, 1] else None,
											lambda rval: rval & 2 >> 1),
	('out1_waveform',	REG_SG_WAVEFORMS,	lambda s, old: (old & ~0x70) | s if s in [SG_WAVE_SINE, SG_WAVE_SQUARE, SG_WAVE_NOISE] else None,
											lambda rval: rval & 0x70 >> 4),
	('out2_waveform',	REG_SG_WAVEFORMS,	lambda s, old: (old & ~0x380) | s if s in [SG_WAVE_SINE, SG_WAVE_SQUARE, SG_WAVE_NOISE] else None,
											lambda rval: rval & 0x380 >> 7),
	('out1_modulation',	REG_SG_WAVEFORMS,	lambda s, old: (old & ~0x00FF0000) | s << 16 if s in range(SG_MOD_NONE, SG_MOD_AMPL | SG_MOD_FREQ | SG_MOD_PHASE) else None,
											lambda rval: rval & 0x00FF0000 >> 16),
	('out2_modulation',	REG_SG_WAVEFORMS,	lambda s, old: (old & ~0xFF000000) | s << 24 if s in range(SG_MOD_NONE, SG_MOD_AMPL | SG_MOD_FREQ | SG_MOD_PHASE) else None,
											lambda rval: rval & 0xFF000000 >> 24),
	('out1_frequency',	(REG_SG_FREQ1_H, REG_SG_FREQ1_L),
											lambda f, old: ((old[0] & 0xFFFF0000) | _usgn(f / _SG_FREQSCALE, 48) >> 32, _usgn(f / _SG_FREQSCALE, 48) & 0xFFFFFFFF),
											lambda rval: _SG_FREQSCALE * (rval[0] << 32 | rval[1])),
	('out2_frequency',	(REG_SG_FREQ2_H, REG_SG_FREQ2_L),
											lambda f, old: ((old[0] & 0xFFFF0000) | _usgn(f / _SG_FREQSCALE, 48) >> 32, _usgn(f / _SG_FREQSCALE, 48) & 0xFFFFFFFF),
											lambda rval: _SG_FREQSCALE * (rval[0] << 32 | rval[1])),
	('out1_offset',		REG_SG_MODF1_H,		lambda o, old: (old & ~0x0000FFFF) | _sgn(o / _SG_AMPSCALE, 16),
											lambda rval: (rval & 0x0000FFFF) * _SG_AMPSCALE),
	('out2_offset',		REG_SG_MODF2_H,		lambda o, old: (old & ~0x0000FFFF) | _sgn(o / _SG_AMPSCALE, 16),
											lambda rval: (rval & 0x0000FFFF) * _SG_AMPSCALE),
	('out1_phase',		REG_SG_PHASE1,		lambda p, old: _usgn(p / _SG_PHASESCALE, 32), lambda rval: _SG_PHASESCALE * rval),
	('out2_phase',		REG_SG_PHASE2,		lambda p, old: _usgn(p / _SG_PHASESCALE, 32), lambda rval: _SG_PHASESCALE * rval),
	('out1_amplitude',	REG_SG_AMP1,		lambda a, old: _usgn(a / _SG_AMPSCALE, 32), lambda rval: _SG_AMPSCALE * rval),
	('out2_amplitude',	REG_SG_AMP2,		lambda a, old: _usgn(a / _SG_AMPSCALE, 32), lambda rval: _SG_AMPSCALE * rval),
	('mod1_frequency',	(REG_SG_MODF1_H, REG_SG_MODF1_L),
											lambda f, old: ((old & 0xFFFF0000) | _usgn(f / _SG_FREQSCALE, 48) >> 32, _usgn(f / _SG_FREQSCALE, 48) & 0xFFFFFFFF),
											lambda rval: _SG_FREQSCALE * (rval[0] << 32 | rval[1])),
	('mod2_frequency',	(REG_SG_MODF2_H, REG_SG_MODF2_L),
											lambda f, old: ((old & 0xFFFF0000) | _usgn(f / _SG_FREQSCALE, 48) >> 32, _usgn(f / _SG_FREQSCALE, 48) & 0xFFFFFFFF),
											lambda rval: _SG_FREQSCALE * (rval[0] << 32 | rval[1])),
	('mod1_offset',		REG_SG_MODF1_H,		lambda o, old: (old & 0x0000FFFF) | _sgn(o, 16) << 16,
											lambda rval: rval >> 16),
	('mod2_offset',		REG_SG_MODF2_H,		lambda o, old: (old & 0x0000FFFF) | _sgn(o, 16) << 16,
											lambda rval: rval >> 16),
	('out1_t0',			REG_SG_T01,			lambda t, old: _usgn(t / _SG_PHASESCALE, 32),
											lambda rval: rval * _SG_PHASESCALE),
	('out1_t1',			REG_SG_T11,			lambda t, old: _usgn(t / _SG_PHASESCALE, 32),
											lambda rval: rval * _SG_PHASESCALE),
	('out1_t2',			REG_SG_T21,			lambda t, old: _usgn(t / _SG_PHASESCALE, 32),
											lambda rval: rval * _SG_PHASESCALE),
	('out2_t0',			REG_SG_T02,			lambda t, old: _usgn(t / _SG_PHASESCALE, 32),
											lambda rval: rval * _SG_PHASESCALE),
	('out2_t1',			REG_SG_T12,			lambda t, old: _usgn(t / _SG_PHASESCALE, 32),
											lambda rval: rval * _SG_PHASESCALE),
	('out2_t2',			REG_SG_T22,			lambda t, old: _usgn(t / _SG_PHASESCALE, 32),
											lambda rval: rval * _SG_PHASESCALE),
	('out1_riserate',	(REG_SG_RFRATE1_H, REG_SG_RISERATE1_L),
											lambda r, old: (old[0] & 0xFFFF0000 | _usgn(r, 48) >> 32, _usgn(r, 48) & 0xFFFFFFFF),
											lambda rval: rval[0] & 0x0000FFFF << 32 | rval[1]),
	('out1_fallrate',	(REG_SG_RFRATE1_H, REG_SG_FALLRATE1_L),
											lambda r, old: (old[0] & 0x0000FFFF | (_usgn(r, 48) >> 32) << 16, _usgn(r, 48) & 0xFFFFFFFF),
											lambda rval: rval[0] & 0xFFFF0000 << 16 | rval[1]),
	('out2_riserate',	(REG_SG_RFRATE2_H, REG_SG_RISERATE2_L),
											lambda r, old: (old[0] & 0xFFFF0000 | _usgn(r, 48) >> 32, _usgn(r, 48) & 0xFFFFFFFF),
											lambda rval: rval[0] & 0x0000FFFF << 32 | rval[1]),
	('out2_fallrate',	(REG_SG_RFRATE2_H, REG_SG_FALLRATE2_L),
											lambda r, old: (old[0] & 0x0000FFFF | (_usgn(r, 48) >> 32) << 16, _usgn(r, 48) & 0xFFFFFFFF),
											lambda rval: rval[0] & 0xFFFF0000 << 16 | rval[1]),
	('mod1_amplitude',	REG_SG_MODA1,		lambda a, old: _usgn(a / _SG_DEPTHSCALE, 15), lambda rval: rval),
	('mod2_amplitude',	REG_SG_MODA2,		lambda a, old: _usgn(a / _SG_DEPTHSCALE, 15),	lambda rval: rval),
	('out1_modsource',	REG_SG_MODSOURCE,	lambda s, old: old & ~0x00000006 | s << 1 if s in [SG_MODSOURCE_INT, SG_MODSOURCE_ADC, SG_MODSOURCE_DAC] else None,
											lambda rval: rval & 0x00000006 >> 1),
	('out2_modsource',	REG_SG_MODSOURCE,	lambda s, old: old & 0x00000018 | s << 3 if s in [SG_MODSOURCE_INT, SG_MODSOURCE_ADC, SG_MODSOURCE_DAC] else None,
											lambda rval: rval & 0x00000018 >> 3),
	('out1_amp_pc',		REG_SG_PRECLIP,		lambda a, old: old & 0xFFFF0000 | _usgn(a / _SG_AMPSCALE, 15),
											lambda rval: rval & 0x0000FFFF * _SG_AMPSCALE),
	('out2_amp_pc',		REG_SG_PRECLIP,		lambda a, old: old & 0x0000FFFF | _usgn(a / _SG_AMPSCALE, 15) << 16,
											lambda rval: rval >> 16 * _SG_AMPSCALE),
]
_instrument._attach_register_handlers(_siggen_reg_hdl, SignalGenerator)


import math
import logging

from pymoku import ValueOutOfRangeException

from ._instrument import *
from ._instrument import _usgn, _sgn
from . import _frame_instrument

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
SG_WAVE_TRIANGLE	= 2
SG_WAVE_PULSE		= 3
SG_WAVE_DC			= 4

SG_MOD_NONE			= 0
SG_MOD_AMPL			= 1
SG_MOD_FREQ			= 2
SG_MOD_PHASE		= 4

SG_MODSOURCE_INT	= 0
SG_MODSOURCE_ADC	= 1
SG_MODSOURCE_DAC	= 2

_SG_FREQSCALE		= 1e9 / 2**48
_SG_PHASESCALE		= 1.0 / (2**32 - 1)
_SG_RISESCALE		= 1e9 / 2**48
_SG_AMPSCALE		= 4.0 / 2**16
_SG_DEPTHSCALE		= 1.0 / 2**15
_SG_MAX_RISE		= 1e9 - 1

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
		self._register_accessors(_siggen_reg_handlers)

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

		# Disable inputs on hardware that supports it
		self.en_in_ch1 = False
		self.en_in_ch2 = False

	def synth_sinewave(self, ch, amplitude, frequency, offset=0):
		""" Generate a Sine Wave with the given parameters on the given channel.

		:type ch: int
		:param ch: Channel on which to generate the wave

		:type amplitude: float, volts
		:param amplitude: Waveform peak-to-peak amplitude

		:type frequency: float
		:param frequency: Freqency of the wave

		:type offset: float, volts
		:param offset: DC offset applied to the waveform"""
		if ch == 1:
			self.out1_waveform = SG_WAVE_SINE
			self.out1_enable = True
			self.out1_amplitude = amplitude
			self.out1_frequency = frequency
			self.out1_offset = offset
		elif ch == 2:
			self.out2_waveform = SG_WAVE_SINE
			self.out2_enable = True
			self.out2_amplitude = amplitude
			self.out2_frequency = frequency
			self.out2_offset = offset
		else:
			raise ValueOutOfRangeException("Invalid Channel")

	def synth_squarewave(self, ch, amplitude, frequency, offset=0, duty=0.5, risetime=0, falltime=0):
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

		:type risetime: float, 0-1
		:param risetime: Fraction of a cycle taken for the waveform to rise

		:type falltime: float 0-1
		:param falltime: Fraction of a cycle taken for the waveform to fall"""

		if duty < risetime:
			raise ValueOutOfRangeException("Duty too small for given rise rate")
		elif duty + falltime > 1:
			raise ValueOutOfRangeException("Duty and fall time too big")

		if ch == 1:
			self.out1_waveform = SG_WAVE_SQUARE
			self.out1_enable = True
			self.out1_amplitude = amplitude
			self.out1_frequency = frequency
			self.out1_offset = offset
			self.out1_clipsine = False # TODO: Should switch to clip depending on freq or user

			# This is overdefined, but saves the FPGA doing a tricky division
			self.out1_t0 = risetime
			self.out1_t1 = duty
			self.out1_t2 = duty + falltime
			self.out1_riserate = frequency / risetime if risetime else _SG_MAX_RISE
			self.out1_fallrate = frequency / falltime if falltime else _SG_MAX_RISE
		elif ch == 2:
			self.out2_waveform = SG_WAVE_SQUARE
			self.out2_enable = True
			self.out2_amplitude = amplitude
			self.out2_frequency = frequency
			self.out2_offset = offset
			self.out2_clipsine = False
			self.out2_t0 = risetime
			self.out2_t1 = duty
			self.out2_t2 = duty + falltime
			self.out2_riserate = frequency / risetime if risetime else _SG_MAX_RISE
			self.out2_fallrate = frequency / falltime if falltime else _SG_MAX_RISE
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
			offset = offset, duty = symmetry,
			risetime = symmetry,
			falltime = 1 - symmetry)

	def synth_modulate(self, ch, type, source, depth, frequency=0):
		"""
		Set up modulation on an output channel.

		:type ch: int
		:param ch: Channel to modulate

		:type type: SG_MOD_NONE, SG_MOD_AMPL, SG_MOD_FREQ, SG_MOD_PHASE
		:param type:  Modulation type. Respectively Off, Amplitude, Frequency and Phase modulation.

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

_siggen_reg_handlers = {
	'out1_enable':		(REG_SG_WAVEFORMS,	to_reg_bool(0),		from_reg_bool(0)),
	'out2_enable':		(REG_SG_WAVEFORMS,	to_reg_bool(1),		from_reg_bool(1)),

	'out1_waveform':	(REG_SG_WAVEFORMS,	to_reg_unsigned(4, 3, allow_set=[SG_WAVE_SINE, SG_WAVE_SQUARE, SG_WAVE_TRIANGLE, SG_WAVE_DC, SG_WAVE_PULSE]),
											from_reg_unsigned(4, 3)),

	'out2_waveform':	(REG_SG_WAVEFORMS,	to_reg_unsigned(8, 3, allow_set=[SG_WAVE_SINE, SG_WAVE_SQUARE, SG_WAVE_TRIANGLE, SG_WAVE_DC, SG_WAVE_PULSE]),
											from_reg_unsigned(8, 3)),

	'out1_clipsine':	(REG_SG_WAVEFORMS,	to_reg_bool(7),		from_reg_bool(7)),
	'out2_clipsine':	(REG_SG_WAVEFORMS,	to_reg_bool(11),		from_reg_bool(11)),

	'out1_modulation':	(REG_SG_WAVEFORMS,	to_reg_unsigned(16, 8, allow_range=[SG_MOD_NONE, SG_MOD_AMPL | SG_MOD_FREQ | SG_MOD_PHASE]),
											from_reg_unsigned(16, 8)),

	'out2_modulation':	(REG_SG_WAVEFORMS,	to_reg_unsigned(24, 8, allow_range=[SG_MOD_NONE, SG_MOD_AMPL | SG_MOD_FREQ | SG_MOD_PHASE]),
											from_reg_unsigned(24, 8)),

	'out1_frequency':	((REG_SG_FREQ1_H, REG_SG_FREQ1_L),
											to_reg_unsigned(0, 48, xform=lambda f:f / _SG_FREQSCALE),
											from_reg_unsigned(0, 48, xform=lambda f: f * _SG_FREQSCALE)),

	'out2_frequency':	((REG_SG_FREQ2_H, REG_SG_FREQ2_L),
											to_reg_unsigned(0, 48, xform=lambda f:f / _SG_FREQSCALE),
											from_reg_unsigned(0, 48, xform=lambda f: f * _SG_FREQSCALE)),

	'out1_offset':		(REG_SG_MODF1_H,	to_reg_signed(0, 16, xform=lambda o:o / _SG_AMPSCALE),
											from_reg_signed(0, 16, xform=lambda o: o * _SG_AMPSCALE)),

	'out2_offset':		(REG_SG_MODF2_H,	to_reg_signed(0, 16, xform=lambda o:o / _SG_AMPSCALE),
											from_reg_signed(0, 16, xform=lambda o: o * _SG_AMPSCALE)),

	'out1_phase':		(REG_SG_PHASE1,		to_reg_unsigned(0, 32, xform=lambda p:p / _SG_PHASESCALE),
											from_reg_unsigned(0, 32, xform=lambda p:p * _SG_PHASESCALE)),

	'out2_phase':		(REG_SG_PHASE2,		to_reg_unsigned(0, 32, xform=lambda p:p / _SG_PHASESCALE),
											from_reg_unsigned(0, 32, xform=lambda p:p * _SG_PHASESCALE)),

	'out1_amplitude':	(REG_SG_AMP1,		to_reg_unsigned(0, 32, xform=lambda p:p / _SG_AMPSCALE),
											from_reg_unsigned(0, 32, xform=lambda p:p * _SG_AMPSCALE)),

	'out2_amplitude':	(REG_SG_AMP2,		to_reg_unsigned(0, 32, xform=lambda p:p / _SG_AMPSCALE),
											from_reg_unsigned(0, 32, xform=lambda p:p * _SG_AMPSCALE)),

	'mod1_frequency':	((REG_SG_MODF1_H, REG_SG_MODF1_L),
											lambda f, old: ((old[0] & 0x0000FFFF) | (_usgn(f/_SG_FREQSCALE, 48) >> 16) & 0xFFFF0000, _usgn(f/_SG_FREQSCALE, 48) & 0xFFFFFFFF),
											lambda rval: _SG_FREQSCALE * ((rval[0] & 0xFFFF0000) << 16 | rval[1])),

	'mod2_frequency':	((REG_SG_MODF2_H, REG_SG_MODF2_L),
											lambda f, old: ((old[0] & 0x0000FFFF) | (_usgn(f/_SG_FREQSCALE, 48) >> 16) & 0xFFFF0000, _usgn(f/_SG_FREQSCALE, 48) & 0xFFFFFFFF),
											lambda rval: _SG_FREQSCALE * ((rval[0] & 0xFFFF0000) << 16 | rval[1])),

	'out1_t0':			(REG_SG_T01,		to_reg_signed(0, 32, xform=lambda o: o / _SG_PHASESCALE),
											from_reg_signed(0, 32, xform=lambda o: o * _SG_PHASESCALE)),

	'out1_t1':			(REG_SG_T11,		to_reg_signed(0, 32, xform=lambda o: o / _SG_PHASESCALE),
											from_reg_signed(0, 32, xform=lambda o: o * _SG_PHASESCALE)),

	'out1_t2':			(REG_SG_T21,		to_reg_signed(0, 32, xform=lambda o: o / _SG_PHASESCALE),
											from_reg_signed(0, 32, xform=lambda o: o * _SG_PHASESCALE)),

	'out2_t0':			(REG_SG_T02,		to_reg_signed(0, 32, xform=lambda o: o / _SG_PHASESCALE),
											from_reg_signed(0, 32, xform=lambda o: o * _SG_PHASESCALE)),

	'out2_t1':			(REG_SG_T12,		to_reg_signed(0, 32, xform=lambda o: o / _SG_PHASESCALE),
											from_reg_signed(0, 32, xform=lambda o: o * _SG_PHASESCALE)),

	'out2_t2':			(REG_SG_T22,		to_reg_signed(0, 32, xform=lambda o: o / _SG_PHASESCALE),
											from_reg_signed(0, 32, xform=lambda o: o * _SG_PHASESCALE)),

	'out1_riserate':	((REG_SG_RFRATE1_H, REG_SG_RISERATE1_L),
											to_reg_unsigned(0, 48, xform=lambda r: r / _SG_FREQSCALE),
											from_reg_unsigned(0, 48, xform=lambda r: r * _SG_FREQSCALE)),

	'out1_fallrate':	((REG_SG_RFRATE1_H, REG_SG_FALLRATE1_L),
											lambda f, old: ((old[0] & 0x0000FFFF) | (_usgn(f/_SG_FREQSCALE, 48) >> 16) & 0xFFFF0000, _usgn(f/_SG_FREQSCALE, 48) & 0xFFFFFFFF),
											lambda rval: _SG_FREQSCALE * ((rval[0] & 0xFFFF0000) << 16 | rval[1])),

	'out2_riserate':	((REG_SG_RFRATE2_H, REG_SG_RISERATE2_L),
											to_reg_unsigned(0, 48, xform=lambda r: r / _SG_FREQSCALE),
											from_reg_unsigned(0, 48, xform=lambda r: r * _SG_FREQSCALE)),

	'out2_fallrate':	((REG_SG_RFRATE2_H, REG_SG_FALLRATE2_L),
											lambda f, old: ((old[0] & 0x0000FFFF) | (_usgn(f/_SG_FREQSCALE, 48) >> 16) & 0xFFFF0000, _usgn(f/_SG_FREQSCALE, 48) & 0xFFFFFFFF),
											lambda rval: _SG_FREQSCALE * ((rval[0] & 0xFFFF0000) << 16 | rval[1])),

	'mod1_amplitude':	(REG_SG_MODA1,		to_reg_unsigned(0, 32, xform=lambda a: a / _SG_DEPTHSCALE),
											from_reg_unsigned(0, 32, xform=lambda a: a * _SG_DEPTHSCALE)),

	'mod2_amplitude':	(REG_SG_MODA2,		to_reg_unsigned(0, 32, xform=lambda a: a / _SG_DEPTHSCALE),
											from_reg_unsigned(0, 32, xform=lambda a: a * _SG_DEPTHSCALE)),

	'out1_modsource':	(REG_SG_MODSOURCE,	to_reg_unsigned(1, 2, allow_set=[SG_MODSOURCE_INT, SG_MODSOURCE_ADC, SG_MODSOURCE_DAC]),
											from_reg_unsigned(1, 2)),

	'out2_modsource':	(REG_SG_MODSOURCE,	to_reg_unsigned(3, 2, allow_set=[SG_MODSOURCE_INT, SG_MODSOURCE_ADC, SG_MODSOURCE_DAC]),
											from_reg_unsigned(3, 2)),

	'out1_amp_pc':		(REG_SG_PRECLIP,	to_reg_unsigned(0, 16, xform=lambda a: a / _SG_AMPSCALE),
											from_reg_unsigned(0, 16, xform=lambda a: a * _SG_AMPSCALE)),

	'out2_amp_pc':		(REG_SG_PRECLIP,	to_reg_unsigned(16, 16, xform=lambda a: a / _SG_AMPSCALE),
											from_reg_unsigned(16, 16, xform=lambda a: a * _SG_AMPSCALE)),
}

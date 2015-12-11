
import math
import logging

from _instrument import *
import _instrument
import _frame_instrument
import _siggen

from struct import unpack

import sys
# Annoying that import * doesn't pick up function defs??
_sgn = _instrument._sgn
_usgn = _instrument._usgn
_upsgn = _instrument._upsgn

log = logging.getLogger(__name__)

REG_PM_INITF1_H = 65
REG_PM_INITF1_L = 64
REG_PM_INITF2_H = 68
REG_PM_INITF2_L = 69
REG_PM_CGAIN = 66
REG_PM_INTSHIFT = 66
REG_PM_CSHIFT = 66
REG_PM_OUTDEC = 67
REG_PM_OUTSHIFT = 67

_PM_FREQSCALE = 2.0**48 / (500.0 * 10e6)

class PhaseMeterDataFrame(_frame_instrument.DataFrame):
	def __init__(self):
		super(PhaseMeterDataFrame, self).__init__()
		self.phase1 = 0.0
		self.phase2 = 0.0
		self.frequency1 = 0.0
		self.frequency2 = 0.0
		self.amplitude1 = 0.0
		self.amplitude2 = 0.0
		self.counter1 = 0
		self.counter2 = 0

	def process_channel(self, raw_data):
		i = 0
		while raw_data[i:i+8] != '\xAA' * 4 + '\x55' * 4:
			i += 1
			if i >= 50: raise Exception("Couldn't find alignment bytes.")
		i += 8

		data = unpack('<IIIIII', raw_data[i:i+24])

		freq = _upsgn(((data[1] & 0xFFFF0000) << 16) | data[0], 48)
		freq = (freq / 2.0**48) * 500.0 * 10e6
		phase = _upsgn(((data[1] & 0xFFFF) << 32) | data[2], 48)
		phase = (phase / 2.0**48) * 500.0
		count = data[3]
		I = _upsgn(data[4], 32)
		Q = _upsgn(data[5], 32)

		return phase, freq, I, Q, count

	def process_complete(self):
		self.phase1, self.frequency1, self.I1, self.Q1, self.counter1 = self.process_channel(self.raw1)
		self.phase2, self.frequency2, self.I2, self.Q2, self.counter2 = self.process_channel(self.raw2)

class PhaseMeter(_frame_instrument.FrameBasedInstrument): #TODO Frame instrument may not be appropriate when we get streaming going.
	""" PhaseMeter instrument object. This should be instantiated and attached to a :any:`Moku` instance.

	.. automethod:: pymoku.instruments.PhaseMeter.__init__

	.. attribute:: hwver

		Hardware Version

	.. attribute:: hwserial

		Hardware Serial Number

	.. attribute:: framerate
		:annotation: = 10

		Frame Rate, range 1 - 30.

	.. attribute:: type
		:annotation: = "phasemeter"

		Name of this instrument.

	"""
	def __init__(self):
		"""Create a new PhaseMeter instrument, ready to be attached to a Moku."""
		super(PhaseMeter, self).__init__(PhaseMeterDataFrame)
		self.id = 3
		self.type = "phasemeter"

	def set_defaults(self):
		super(PhaseMeter, self).set_defaults()
		self.x_mode = _instrument.ROLL
		self.framerate = 10
		self.frame_length = 64
		self.init_freq_ch1 = 10 * 10e6
		self.init_freq_ch2 = 10 * 10e6
		self.control_gain = 100
		self.control_shift = 0
		self.integrator_shift = 5
		self.output_decimation = 512
		self.output_shift = 9
		self.pretrigger = 0
		self.render_deci = 1.0
		self.offset = 64
		self.render_deci_alt = self.render_deci
		self.offset_alt = self.offset
		self.set_frontend(1, fiftyr=True, atten=True, ac=True)
		self.set_frontend(2, fiftyr=True, atten=True, ac=True)

_pm_reg_hdl = [
	('init_freq_ch1',		(REG_PM_INITF1_H, REG_PM_INITF1_L),
											lambda f, old: ((_usgn(f * _PM_FREQSCALE, 48) >> 32) & 0xFFFF, _usgn(f * _PM_FREQSCALE, 48) & 0xFFFFFFFF),
											lambda rval: ((rval[0] << 32) | rval[1]) / _PM_FREQSCALE),
	('init_freq_ch2',		(REG_PM_INITF2_H, REG_PM_INITF2_L),
											lambda f, old: ((_usgn(f * _PM_FREQSCALE, 48) >> 32) & 0xFFFF, _usgn(f * _PM_FREQSCALE, 48) & 0xFFFFFFFF),
											lambda rval: ((rval[0] << 32) | rval[1]) / _PM_FREQSCALE),
	('control_gain',		REG_PM_CGAIN,	lambda f, old: _sgn(f, 8) | (old & ~0xFF),
											lambda rval: rval & 0xFF), #TODO needs sign extension
	('control_shift',		REG_PM_CGAIN,	lambda f, old: (_usgn(f, 4) << 12) | (old & ~0xF000),
											lambda rval: (rval & 0xF000) >> 12),
	('integrator_shift',	REG_PM_INTSHIFT,lambda f, old: (_usgn(f, 4) << 8) | (old & ~0xF00),
											lambda rval: (rval >> 8) & 0xF),
	('output_decimation',	REG_PM_OUTDEC,	lambda f, old: _usgn(f, 10) | (old & ~0x3FF),
											lambda rval: rval & 0x3FF),
	('output_shift',		REG_PM_OUTSHIFT,lambda f, old: (_usgn(f, 4) << 10) | (old & ~0x3C00),
											lambda rval: (rval >> 10) & 0xF),
]
_instrument._attach_register_handlers(_pm_reg_hdl, PhaseMeter)

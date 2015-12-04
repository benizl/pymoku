
import math
import logging

from _instrument import *
import _instrument
import _frame_instrument
import _siggen

# Annoying that import * doesn't pick up function defs??
_sgn = _instrument._sgn
_usgn = _instrument._usgn

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
		super(PhaseMeter, self).__init__()
		self.id = 3
		self.type = "phasemeter"

	def set_defaults(self):
		super(PhaseMeter, self).set_defaults()
		self.x_mode = _instrument.ROLL
		self.framerate = 10
		self.frame_length = 1024
		self.init_freq_ch1 = 10 * 10e6
		self.init_freq_ch2 = 10 * 10e6
		self.control_gain = 100
		self.control_shift = 0
		self.integrator_shift = 5
		self.output_decimation = 50
		self.output_shift = 0

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

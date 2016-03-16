
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
REG_PM_INITF2_L = 68
REG_PM_INITF2_H = 69
REG_PM_CGAIN = 66
REG_PM_INTSHIFT = 66
REG_PM_CSHIFT = 66
REG_PM_OUTDEC = 67
REG_PM_OUTSHIFT = 67

# Phasemeter specific instrument constants
_PM_ADC_SMPS = _instrument.ADC_SMP_RATE
_PM_DAC_SMPS = _instrument.DAC_SMP_RATE
_PM_BUFLEN = _instrument.CHN_BUFLEN
_PM_FREQSCALE = 2.0**48 / _PM_DAC_SMPS
_PM_FREQ_MIN = 2e6
_PM_FREQ_MAX = 200e6
_PM_UPDATE_RATE = 1e6

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
	def _intToCycles(self, rawValue):
	    return 2.0 * pow(2.0, 16.0) * rawValue / pow(2.0, 48.0) * _PM_ADC_SMPS / _PM_UPDATE_RATE
	
	def _intToHertz(self, rawValue):
	    return 2.0 * _PM_ADC_SMPS * rawValue / pow(2.0, 48.0)

	def _intToVolts(self, rawValue, scaleFactor):
	    return 2.0 / (_PM_ADC_SMPS * _PM_ADC_SMPS / _PM_UPDATE_RATE / _PM_UPDATE_RATE) * rawValue * scaleFactor

	def _update_datalogger_params(self):
		# Call this function when any instrument configuration parameters are set
		self.hdrstr = self.get_hdrstr()

	def set_samplerate(self, samplerate):
		""" Manually set the sample rate of the instrument.

		The sample rate is automatically calcluated and set in :any:`set_timebase`; setting it through this
		interface if you've previously set the scales through that will have unexpected results.

		This interface is most useful for datalogging and similar aquisition where one will not be looking
		at data frames.

		:type samplerate: float; *0 < samplerate < 500MSPS*
		:param samplerate: Target samples per second. Will get rounded to the nearest allowable unit.
		"""
		self.output_decimation = _PM_UPDATE_RATE / samplerate
		self.timestep = 1.0 / samplerate
		self._update_datalogger_params()

	def get_samplerate(self):
		"""
		Get the current output sample rate of the phase meter.
		"""
		return _PM_UPDATE_RATE / self.output_decimation

	def get_timestep(self):
		return self.timestep

	def set_initfreq(self, ch, f):
		""" Manually set the initial frequency of the designated channel

		:type ch: int; *{1,2}*
		:param ch: Channel number to set the initial frequency of.

		:type f: int; *2e6 < f < 200e6*
		:param f: Initial locking frequency of the designated channel

		"""
		if _PM_FREQ_MIN < f < _PM_FREQ_MAX:
			if ch == 1:
				self.init_freq_ch1 = int(f);
				self._update_datalogger_params()
			elif ch == 2:
				self.init_freq_ch2 = int(f);
				self._update_datalogger_params()
			else:
				raise ValueError("Invalid channel number")
		else:
			raise ValueError("Initial frequency is not within the valid range.")

	def get_initfreq(self, ch):
		if ch == 1:
			return self.init_freq_ch1
		elif ch == 2:
			return self.init_freq_ch2
		else:
			raise ValeuError("Invalid channel number.")

	def set_controlgain(self, v):
		#TODO: Put limits on the range of 'v'
		self.control_gain = v
		self._update_datalogger_params()

	def get_controlgain(self):
		return self.control_gain

	def set_frontend(self, channel, fiftyr, atten, ac):
		#TODO update the _instrument class to automatically run an update callback on instrument summary
		super(PhaseMeter, self).set_frontend(channel, fiftyr, atten, ac)
		self._update_datalogger_params()

	def get_hdrstr(self):
		# Get relay settings
		r1 = self.get_frontend(1);
		r2 = self.get_frontend(2);

		hdr =  "# Moku:Phasemeter acquisition at {T}\r\n"
		hdr += "# Ch 1 - {} coupling, {} Ohm impedance, {} dB attenuation\r\n".format("AC" if r1[2] else "DC", "50" if r1[0] else "1M", "20" if r1[1] else "0" )
		hdr += "# Ch 2 - {} coupling, {} Ohm impedance, {} dB attenuation\r\n".format("AC" if r2[2] else "DC", "50" if r2[0] else "1M", "20" if r2[1] else "0" )
		hdr += "# Loop gain {:d}, Ch1 frequency = {:.10e}, Ch 2 frequency = {:.10e}\r\n".format(self.get_controlgain(),self.get_initfreq(1),self.get_initfreq(2))
		hdr += "# Acquisition rate: {}\r\n#\r\n".format(self.get_samplerate())
		hdr += "# Time, Frequency offset 1 (Hz), Phase 1 (cyc), I 1 (V), Q 1 (V), Frequency offset 2 (Hz), Phase 2 (cyc), I 2 (V), Q 2 (V)\r\n"
		return hdr

	def set_defaults(self):
		super(PhaseMeter, self).set_defaults()

		# Because we have to deal with a "frame" type instrument
		self.x_mode = _instrument.ROLL
		self.framerate = 0

		# Set basic configurations
		self.set_samplerate(1e3)
		self.set_initfreq(1, 10e6)
		self.set_initfreq(2, 10e6)

		# Set PI controller gains
		self.set_controlgain(100)
		self.control_shift = 0
		self.integrator_shift = 0
		self.output_shift = 9

		# Configuring the relays for impedance, voltage range etc.
		# ?? What config do we want for phasemeter
		self.set_frontend(1, fiftyr=True, atten=True, ac=True)
		self.set_frontend(2, fiftyr=True, atten=True, ac=True)

		self._update_datalogger_params()

	def __init__(self):
		"""Create a new PhaseMeter instrument, ready to be attached to a Moku."""
		super(PhaseMeter, self).__init__(None)
		self.id = 3
		self.type = "phasemeter"
		self.logname = "MokuPhaseMeterData"
		self.set_defaults()

		self.binstr = "<p32,0xAAAAAAAA:p32,0x55555555:s32:s32:s48:s48:s32"
		self.procstr = ["*C*{:.10e} : *C*{:.10e} : *{:.10e} : *{:.10e} : ".format(self._intToVolts(1.0,1.0), self._intToVolts(1.0,1.0), -self._intToHertz(1.0), self._intToCycles(1.0)),
						"*C*{:.10e} : *C*{:.10e} : *{:.10e} : *{:.10e} : ".format(self._intToVolts(1.0,1.0), self._intToVolts(1.0,1.0), -self._intToHertz(1.0), self._intToCycles(1.0))]
		self.fmtstr = "{t:.10e}, {ch1[2]:.10e}, {ch1[3]:.10e}, {ch1[0]:.10e}, {ch1[1]:.10e}, {ch2[2]:.10e}, {ch2[3]:.10e}, {ch2[0]:.10e}, {ch2[1]:.10e}\r\n"
		self.hdrstr = self.get_hdrstr()

_pm_reg_hdl = [
	('init_freq_ch1',		(REG_PM_INITF1_H, REG_PM_INITF1_L),
											lambda f, old: ((_usgn(f * _PM_FREQSCALE, 48) >> 32) & 0xFFFF, _usgn(f * _PM_FREQSCALE, 48) & 0xFFFFFFFF),
											lambda rval: ((rval[0] << 32) | rval[1]) / _PM_FREQSCALE),
	('init_freq_ch2',		(REG_PM_INITF2_H, REG_PM_INITF2_L),
											lambda f, old: ((_usgn(f * _PM_FREQSCALE, 48) >> 32) & 0xFFFF, _usgn(f * _PM_FREQSCALE, 48) & 0xFFFFFFFF),
											lambda rval: ((rval[0] << 32) | rval[1]) / _PM_FREQSCALE),
	('control_gain',		REG_PM_CGAIN,	lambda f, old: _sgn(f, 12) | (old & ~0xFFF),
											lambda rval: _upsgn(rval & 0xFFF, 12)),
	('control_shift',		REG_PM_CGAIN,	lambda f, old: (_usgn(f, 4) << 20) | (old & ~0xF00000),
											lambda rval: (rval >> 20) & 0xF),
	('integrator_shift',	REG_PM_INTSHIFT,lambda f, old: (_usgn(f, 4) << 16) | (old & ~0xF0000),
											lambda rval: (rval >> 16) & 0xF),
	('output_decimation',	REG_PM_OUTDEC,	lambda f, old: _usgn(f, 17) | (old & ~0x1FFFF),
											lambda rval: rval & 0x1FFFF),
	('output_shift',		REG_PM_OUTSHIFT,lambda f, old: (_usgn(f, 4) << 10) | (old & ~0x3C00),
											lambda rval: (rval >> 10) & 0xF),
]
_instrument._attach_register_handlers(_pm_reg_hdl, PhaseMeter)

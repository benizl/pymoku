
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

REG_PM_SG_EN = 96
REG_PM_SG_FREQ1_L = 97
REG_PM_SG_FREQ1_H = 98
REG_PM_SG_FREQ2_L = 99
REG_PM_SG_FREQ2_H = 100
REG_PM_SG_AMP = 105

# Phasemeter specific instrument constants
_PM_ADC_SMPS = _instrument.ADC_SMP_RATE
_PM_DAC_SMPS = _instrument.DAC_SMP_RATE
_PM_BUFLEN = _instrument.CHN_BUFLEN
_PM_FREQSCALE = 2.0**48 / _PM_DAC_SMPS
_PM_FREQ_MIN = 2e6
_PM_FREQ_MAX = 200e6
_PM_UPDATE_RATE = 1e6

# Phasemeter signal generator constants
_PM_SG_AMPSCALE = 2**16 / 4.0
_PM_SG_FREQSCALE = _PM_FREQSCALE

class PhaseMeter_SignalGenerator(MokuInstrument):

	def __init__(self):
		super(PhaseMeter_SignalGenerator, self).__init__()
		self._register_accessors(_pm_siggen_reg_hdl)

	def set_defaults(self):
		# Register values
		self.pm_out1_frequency = 0
		self.pm_out2_frequency = 0
		self.pm_out1_amplitude = 0
		self.pm_out2_amplitude = 0

		# Local/cached values
		self.pm_out1_enable = False
		self.pm_out2_enable = False
		self._pm_out1_amplitude = 0
		self._pm_out2_amplitude = 0

		self.set_frontend(1, fiftyr=True, atten=False, ac=True)
		self.set_frontend(2, fiftyr=True, atten=False, ac=True)

	def synth_sinewave(self, ch, amplitude, frequency):
		if ch == 1:
			self._pm_out1_amplitude = amplitude
			self.pm_out1_frequency = frequency
			self.pm_out1_amplitude = self._pm_out1_amplitude if self.pm_out1_enable else 0
		if ch == 2:
			self._pm_out2_amplitude = amplitude
			self.pm_out2_frequency = frequency
			self.pm_out2_amplitude = self._pm_out2_amplitude if self.pm_out2_enable else 0

	def enable_output(self, ch, enable):
		# Recalculate amplitude if the channel is enabled
		if(ch==1):
			self.pm_out1_enable = enable
			self.pm_out1_amplitude = self._pm_out1_amplitude if enable else 0
		if(ch==2):
			self.pm_out2_enable = enable
			self.pm_out2_amplitude = self._pm_out2_amplitude if enable else 0

_pm_siggen_reg_hdl = {
	'pm_out1_frequency':	((REG_PM_SG_FREQ1_H, REG_PM_SG_FREQ1_L),
											to_reg_unsigned(0, 48, xform=lambda f:f * _PM_SG_FREQSCALE ),
											from_reg_unsigned(0, 48, xform=lambda f: f / _PM_FREQSCALE )),
	'pm_out2_frequency':	((REG_PM_SG_FREQ2_H, REG_PM_SG_FREQ2_L),
											to_reg_unsigned(0, 48, xform=lambda f:f * _PM_SG_FREQSCALE ),
											from_reg_unsigned(0, 48, xform=lambda f: f /_PM_FREQSCALE )),
	'pm_out1_amplitude':	(REG_PM_SG_AMP, to_reg_unsigned(0, 16, xform=lambda a: a * _PM_SG_AMPSCALE),
											from_reg_unsigned(0,16, xform=lambda a: a / _PM_SG_AMPSCALE)),
	'pm_out2_amplitude':	(REG_PM_SG_AMP, to_reg_unsigned(16, 16, xform=lambda a: a * _PM_SG_AMPSCALE),
											from_reg_unsigned(16,16, xform=lambda a: a / _PM_SG_AMPSCALE))
}

class PhaseMeter(_frame_instrument.FrameBasedInstrument, PhaseMeter_SignalGenerator): #TODO Frame instrument may not be appropriate when we get streaming going.
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
		self._register_accessors(_pm_reg_handlers)
		
		self.id = 3
		self.type = "phasemeter"
		self.logname = "MokuPhaseMeterData"

		self.binstr = "<p32,0xAAAAAAAA:u48:u48:s15:p1,0:s48:s32:s32"
		self.procstr = ["*{:.16e} : *{:.16e} : : *{:.16e} : *C*{:.16e} : *C*{:.16e} ".format(self._intToHertz(1.0), self._intToHertz(1.0),  self._intToCycles(1.0), self._intToVolts(1.0,1.0), self._intToVolts(1.0,1.0)),
						"*{:.16e} : *{:.16e} : : *{:.16e} : *C*{:.16e} : *C*{:.16e} ".format(self._intToHertz(1.0), self._intToHertz(1.0),  self._intToCycles(1.0), self._intToVolts(1.0,1.0), self._intToVolts(1.0,1.0))]
		print self.procstr

	def _intToCycles(self, rawValue):
	    return 2.0 * pow(2.0, 16.0) * rawValue / pow(2.0, 48.0) * _PM_ADC_SMPS / _PM_UPDATE_RATE
	
	def _intToHertz(self, rawValue):
	    return 2.0 * _PM_ADC_SMPS * rawValue / pow(2.0, 48.0)

	def _intToVolts(self, rawValue, scaleFactor):
	    return 2.0 / (_PM_ADC_SMPS * _PM_ADC_SMPS / _PM_UPDATE_RATE / _PM_UPDATE_RATE) * rawValue * scaleFactor

	def _update_datalogger_params(self, ch1, ch2):
		self.timestep = 1.0/self.get_samplerate()

		# Call this function when any instrument configuration parameters are set
		self.hdrstr = self.get_hdrstr(ch1,ch2)
		self.fmtstr = self.get_fmtstr(ch1,ch2)

	def set_samplerate(self, samplerate):
		""" Manually set the sample rate of the instrument.

		The sample rate is automatically calcluated and set in :any:`set_timebase`; setting it through this
		interface if you've previously set the scales through that will have unexpected results.

		This interface is most useful for datalogging and similar aquisition where one will not be looking
		at data frames.

		:type samplerate: float; *0 < samplerate < 200Hz*
		:param samplerate: Target samples per second. Will get rounded to the nearest allowable unit.
		"""
		self.output_decimation = _PM_UPDATE_RATE / min(max(1,samplerate),200)

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
		if _PM_FREQ_MIN <= f <= _PM_FREQ_MAX:
			if ch == 1:
				self.init_freq_ch1 = int(f);
			elif ch == 2:
				self.init_freq_ch2 = int(f);
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
			raise ValueError("Invalid channel number.")

	def set_controlgain(self, v):
		#TODO: Put limits on the range of 'v'
		self.control_gain = v

	def get_controlgain(self):
		return self.control_gain

	def set_frontend(self, channel, fiftyr, atten, ac):
		#TODO update the _instrument class to automatically run an update callback on instrument summary
		super(PhaseMeter, self).set_frontend(channel, fiftyr, atten, ac)

	def get_hdrstr(self, ch1, ch2):
		chs = [ch1, ch2]

		hdr =  "# Moku:Phasemeter acquisition at {T}\r\n"
		for i,c in enumerate(chs):
			if c:
				r = self.get_frontend(i+1)
				hdr += "# Ch {i} - {} coupling, {} Ohm impedance, {} dB attenuation\r\n".format("AC" if r[2] else "DC", "50" if r[0] else "1M", "20" if r[1] else "0", i=i+1 )

		hdr += "# Loop gain {:d}".format(self.get_controlgain())

		for i,c in enumerate(chs):
			if c:
				hdr += ", Ch {i} frequency = {:.10e}".format(self.get_initfreq(i+1), i=i+1)
		hdr += "\r\n"

		hdr += "# Acquisition rate: {}\r\n#\r\n".format(self.get_samplerate())
		hdr += "# Time"

		for i,c in enumerate(chs):
			if c:
				hdr += ", Absolute Frequency {i}, Phase {i} (cyc), I {i} (V), Q {i} (V), Seed Frequency {i} (Hz), Ctr {i}".format(i=i+1)

		hdr += "\r\n"

		return hdr

	def get_fmtstr(self, ch1, ch2):
		fmtstr = "{t:.10e}"
		if ch1:
			fmtstr += ", {ch1[1]:.16e}, {ch1[3]:.16e}, {ch1[4]:.16e}, {ch1[5]:.16e}, {ch1[0]:.16e}, {ch1[2]:.16e}"
		if ch2:
			fmtstr += ", {ch1[1]:.16e}, {ch1[3]:.16e}, {ch1[4]:.16e}, {ch1[5]:.16e}, {ch1[0]:.16e}, {ch1[2]:.16e}"
		fmtstr += "\r\n"
		return fmtstr

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
		self.output_shift = math.log(self.output_decimation,2)

		# Configuring the relays for impedance, voltage range etc.
		self.set_frontend(1, fiftyr=True, atten=True, ac=True)
		self.set_frontend(2, fiftyr=True, atten=True, ac=True)

		self.en_in_ch1 = True
		self.en_in_ch2 = True

	def datalogger_start(self, start, duration, use_sd, ch1, ch2, filetype):
		self._update_datalogger_params(ch1, ch2)
		super(PhaseMeter, self).datalogger_start(start=start, duration=duration, use_sd=use_sd, ch1=ch1, ch2=ch2, filetype=filetype)

	def datalogger_start_single(self, use_sd, ch1, ch2, filetype):
		self._update_datalogger_params(ch1, ch2)
		super(PhaseMeter, self).datalogger_start_single(use_sd=use_sd, ch1=ch1, ch2=ch2, filetype=filetype)

_pm_reg_handlers = {
	'init_freq_ch1':		((REG_PM_INITF1_H, REG_PM_INITF1_L), 
											to_reg_unsigned(0,48, xform=lambda f: f * _PM_FREQSCALE),
											from_reg_unsigned(0,48,xform=lambda f: f / _PM_FREQSCALE)),
	'init_freq_ch2':		((REG_PM_INITF2_H, REG_PM_INITF2_L),
											to_reg_unsigned(0,48, xform=lambda f: f * _PM_FREQSCALE),
											from_reg_unsigned(0,48,xform=lambda f: f / _PM_FREQSCALE)),
	'control_gain':			(REG_PM_CGAIN,	to_reg_signed(0,16),
											from_reg_signed(0,16)),
	'control_shift':		(REG_PM_CGAIN,	to_reg_unsigned(20,4),
											from_reg_unsigned(20,4)),
	'integrator_shift':		(REG_PM_INTSHIFT, to_reg_unsigned(16,4),
											from_reg_unsigned(16,4)),
	'output_decimation':	(REG_PM_OUTDEC,	to_reg_unsigned(0,17),
											from_reg_unsigned(0,17)),
	'output_shift':			(REG_PM_OUTSHIFT, to_reg_unsigned(17,5),
											from_reg_unsigned(17,5))
}


import math
import logging

from ._instrument import *
from . import _frame_instrument
from . import _siggen

log = logging.getLogger(__name__)

REG_OSC_OUTSEL		= 65
REG_OSC_TRIGMODE	= 66
REG_OSC_TRIGCTL		= 67
REG_OSC_TRIGLVL		= 68
REG_OSC_ACTL		= 69
REG_OSC_DECIMATION	= 70

### Every constant that starts with OSC_ will become an attribute of pymoku.instruments ###

# REG_OSC_OUTSEL constants
OSC_SOURCE_ADC		= 0
OSC_SOURCE_DAC		= 1

# REG_OSC_TRIGMODE constants
OSC_TRIG_AUTO		= 0
OSC_TRIG_NORMAL		= 1
OSC_TRIG_SINGLE		= 2

# REG_OSC_TRIGLVL constants
OSC_TRIG_CH1		= 0
OSC_TRIG_CH2		= 1
OSC_TRIG_DA1		= 2
OSC_TRIG_DA2		= 3

OSC_EDGE_RISING		= 0
OSC_EDGE_FALLING	= 1
OSC_EDGE_BOTH		= 2

# Re-export the top level attributes so they'll be picked up by pymoku.instruments, we
# do actually want to give people access to these constants directly for Oscilloscope
OSC_ROLL			= ROLL
OSC_SWEEP			= SWEEP
OSC_FULL_FRAME		= FULL_FRAME

_OSC_LB_ROUND		= 0
_OSC_LB_CLIP		= 1

_OSC_AIN_DDS		= 0
_OSC_AIN_DECI		= 1

_OSC_ADC_SMPS		= ADC_SMP_RATE
_OSC_BUFLEN			= CHN_BUFLEN
_OSC_SCREEN_WIDTH	= 1024
_OSC_FPS			= 10

class VoltsFrame(_frame_instrument.DataFrame):
	"""
	Object representing a frame of data in units of Volts. This is the native output format of
	the :any:`Oscilloscope` instrument and similar.

	This object should not be instantiated directly, but will be returned by a supporting *get_frame*
	implementation.

	.. autoinstanceattribute:: pymoku._frame_instrument.VoltsFrame.ch1
		:annotation: = [CH1_DATA]

	.. autoinstanceattribute:: pymoku._frame_instrument.VoltsFrame.ch2
		:annotation: = [CH2_DATA]

	.. autoinstanceattribute:: pymoku._frame_instrument.VoltsFrame.frameid
		:annotation: = n

	.. autoinstanceattribute:: pymoku._frame_instrument.VoltsFrame.waveformid
		:annotation: = n
	"""
	def __init__(self, scales):
		super(VoltsFrame, self).__init__()

		#: Channel 1 data array in units of Volts. Present whether or not the channel is enabled, but the
		#: contents are undefined in the latter case.
		self.ch1 = []

		#: Channel 2 data array in units of Volts.
		self.ch2 = []

		self.scales = scales

	def __json__(self):
		return { 'ch1': self.ch1, 'ch2' : self.ch2 }

	def process_complete(self):
		if self.stateid not in self.scales:
			log.error("Can't render voltage frame, haven't saved calibration data for state %d", self.stateid)
			return

		scale1, scale2 = self.scales[self.stateid]

		try:
			smpls = int(len(self.raw1) / 4)
			dat = struct.unpack('<' + 'i' * smpls, self.raw1)
			dat = [ x if x != -0x80000000 else None for x in dat ]

			self.ch1_bits = [ float(x) if x is not None else None for x in dat[:1024] ]
			self.ch1 = [ x * scale1 if x is not None else None for x in self.ch1_bits]

			smpls = int(len(self.raw2) / 4)
			dat = struct.unpack('<' + 'i' * smpls, self.raw2)
			dat = [ x if x != -0x80000000 else None for x in dat ]

			self.ch2_bits = [ float(x) if x is not None else None for x in dat[:1024] ]
			self.ch2 = [ x * scale2 if x is not None else None for x in self.ch2_bits]
		except (IndexError, TypeError, struct.error):
			# If the data is bollocksed, force a reinitialisation on next packet
			log.exception("Oscilloscope packet")
			self.frameid = None
			self.complete = False

		return True

class Oscilloscope(_frame_instrument.FrameBasedInstrument, _siggen.SignalGenerator):
	""" Oscilloscope instrument object. This should be instantiated and attached to a :any:`Moku` instance.

	.. automethod:: pymoku.instruments.Oscilloscope.__init__

	.. attribute:: hwver

		Hardware Version

	.. attribute:: hwserial

		Hardware Serial Number

	.. attribute:: framerate
		:annotation: = 10

		Frame Rate, range 1 - 30.

	.. attribute:: type
		:annotation: = "oscilloscope"

		Name of this instrument.

	"""

	def __init__(self):
		"""Create a new Oscilloscope instrument, ready to be attached to a Moku."""
		super(Oscilloscope, self).__init__()
		self._register_accessors(_osc_reg_handlers)

		self.id = 1
		self.type = "oscilloscope"
		self.calibration = None

		self.logname = "MokuDataloggerData"
		self.binstr = "<s32"
		self.procstr = ["*C","*C"]
		self.timestep = 1

		self.decimation_rate = 1

		self.scales = {}

		self.set_frame_class(VoltsFrame, scales=self.scales)


	def _optimal_decimation(self, t1, t2):
		# Based on mercury_ipad/LISettings::OSCalculateOptimalADCDecimation
		ts = abs(t1 - t2)
		return math.ceil(_OSC_ADC_SMPS * ts / _OSC_BUFLEN)

	def _buffer_offset(self, t1, t2, decimation):
		# Based on mercury_ipad/LISettings::OSCalculateOptimalBufferOffset
		# TODO: Roll mode

		buffer_smps = _OSC_ADC_SMPS / decimation
		offset_secs = t1
		offset = round(min(max(math.ceil(offset_secs * buffer_smps / 4.0), -2**28), 2**12))

		return offset

	def _render_downsample(self, t1, t2, decimation):
		# Based on mercury_ipad/LISettings::OSCalculateRenderDownsamplingForDecimation
		buffer_smps = _OSC_ADC_SMPS / decimation
		screen_smps = min(_OSC_SCREEN_WIDTH / abs(t1 - t2), _OSC_ADC_SMPS)

		return round(min(max(buffer_smps / screen_smps, 1.0), 16.0))

	def _render_offset(self, t1, t2, decimation, buffer_offset, render_decimation):
		# Based on mercury_ipad/LISettings::OSCalculateFrameOffsetForDecimation
		buffer_smps = _OSC_ADC_SMPS / decimation
		trig_in_buf = 4 * buffer_offset # TODO: Roll Mode
		time_buff_start = -trig_in_buf / buffer_smps
		time_buff_end = time_buff_start + (_OSC_BUFLEN - 1) / buffer_smps
		time_screen_centre = abs(t1 - t2) / 2
		screen_span = render_decimation / buffer_smps * _OSC_SCREEN_WIDTH

		# Allows for scrolling past the end of the trace
		time_left = max(min(time_screen_centre - screen_span / 2, time_buff_end - screen_span), time_buff_start)

		return math.ceil(-time_left * buffer_smps)

		# For now, only support viewing the whole captured buffer
		#return buffer_offset * 4

	def _deci_gain(self):
		if self.decimation_rate == 0:
			return 1

		if self.decimation_rate < 2**20:
			return self.decimation_rate
		else:
			return self.decimation_rate / 2**10

	def _update_datalogger_params(self, ch1, ch2):
		samplerate = _OSC_ADC_SMPS / self.decimation_rate
		self.timestep = 1 / samplerate

		if self.ain_mode == _OSC_AIN_DECI:
			self.procstr[0] = "*C/{:f}".format(self._deci_gain())
			self.procstr[1] = "*C/{:f}".format(self._deci_gain())
		else:
			self.procstr[0] = "*C"
			self.procstr[1] = "*C"
		self.fmtstr = self.get_fmtstr(ch1,ch2)
		self.hdrstr = self.get_hdrstr(ch1,ch2)

	def get_hdrstr(self, ch1, ch2):
		chs = [ch1, ch2]

		hdr = "Moku:Lab Data Logger\r\nStart,{{T}}\r\nSample Rate {} Hz\r\nTime".format(self.get_samplerate())
		for i,c in enumerate(chs):
			if c:
				hdr += ", Channel {i}".format(i=i+1)
		hdr += "\r\n"
		return hdr

	def get_fmtstr(self, ch1, ch2):
		chs = [ch1, ch2]
		fmtstr = "{t}"
		for i,c in enumerate(chs):
			if c:
				fmtstr += ",{{ch{i}:.8e}}".format(i=i+1)
		fmtstr += "\r\n"
		return fmtstr

	def datalogger_start(self, start, duration, use_sd, ch1, ch2, filetype):
		self._update_datalogger_params(ch1, ch2)
		super(Oscilloscope, self).datalogger_start(start=start, duration=duration, use_sd=use_sd, ch1=ch1, ch2=ch2, filetype=filetype)

	def datalogger_start_single(self, use_sd, ch1, ch2, filetype):
		self._update_datalogger_params(ch1, ch2)
		super(Oscilloscope, self).datalogger_start_single(use_sd=use_sd, ch1=ch1, ch2=ch2, filetype=filetype)

	def _set_render(self, t1, t2, decimation):
		self.render_mode = RDR_CUBIC #TODO: Support other
		self.pretrigger = self._buffer_offset(t1, t2, self.decimation_rate)
		self.render_deci = self._render_downsample(t1, t2, self.decimation_rate)
		self.offset = self._render_offset(t1, t2, self.decimation_rate, self.pretrigger, self.render_deci)

		# Set alternates to regular, means we get distorted frames until we get a new trigger
		self.render_deci_alt = self.render_deci
		self.offset_alt = self.offset

		log.debug("Render params: Deci %f PT: %f, RDeci: %f, Off: %f", self.decimation_rate, self.pretrigger, self.render_deci, self.offset)

	def set_timebase(self, t1, t2):
		""" Set the left- and right-hand span for the time axis.
		Units are seconds relative to the trigger point.

		:type t1: float
		:param t1:
			Time, in seconds, from the trigger point to the left of screen. This may be negative (trigger on-screen)
			or positive (trigger off the left of screen).

		:type t2: float
		:param t2: As *t1* but to the right of screen.
		"""
		self.decimation_rate = self._optimal_decimation(t1, t2)
		self._set_render(t1, t2, self.decimation_rate)

	def set_samplerate(self, samplerate):
		""" Manually set the sample rate of the instrument.

		The sample rate is automatically calcluated and set in :any:`set_timebase`; setting it through this
		interface if you've previously set the scales through that will have unexpected results.

		This interface is most useful for datalogging and similar aquisition where one will not be looking
		at data frames.

		:type samplerate: float; *0 < samplerate < 500MSPS*
		:param samplerate: Target samples per second. Will get rounded to the nearest allowable unit.
		"""
		self.decimation_rate = _OSC_ADC_SMPS / samplerate

	def get_samplerate(self):
		return _OSC_ADC_SMPS / self.decimation_rate

	def set_xmode(self, xmode):
		"""
		Set rendering mode for the horizontal axis.

		:type xmode: *OSC_ROLL*, *OSC_SWEEP*, *OSC_FULL_FRAME*
		:param xmode:
			Respectively; Roll Mode (scrolling), Sweep Mode (normal oscilloscope trace sweeping across the screen)
			or Full Frame (Like sweep, but waits for the frame to be completed).
		"""
		self.x_mode = xmode

	def set_precision_mode(self, state):
		""" Change aquisition mode between downsampling and decimation.
		Precision mode, a.k.a Decimation, samples at full rate and applies a low-pass filter to the data. This improves
		precision. Normal mode works by direct downsampling, throwing away points it doesn't need.

		:param state: Select Precision Mode
		:type state: bool """
		self.ain_mode = _OSC_AIN_DECI if state else _OSC_AIN_DDS

	def set_trigger(self, source, edge, level, hysteresis=0, hf_reject=False, mode=OSC_TRIG_AUTO):
		""" Sets trigger source and parameters.

		:type source: OSC_TRIG_CH1, OSC_TRIG_CH2, OSC_TRIG_DA1, OSC_TRIG_DA2
		:param source: Trigger Source. May be either ADC Channel or either DAC Channel, allowing one to trigger off a synthesised waveform.

		:type edge: OSC_EDGE_RISING, OSC_EDGE_FALLING, OSC_EDGE_BOTH
		:param edge: Which edge to trigger on.

		:type level: float, volts
		:param level: Trigger level

		:type hysteresis: float, volts
		:param hysteresis: Hysteresis to apply around trigger point."""
		self.trig_ch = source
		self.trig_edge = edge
		self.hysteresis = hysteresis
		self.hf_reject = hf_reject
		self.trig_mode = mode

	def set_source(self, ch, source):
		""" Sets the source of the channel data to either the ADC input or internally looped-back DAC output.

		This feature allows the user to preview the Signal Generator outputs.

		:type ch: int
		:param ch: Channel Number

		:type source: OSC_SOURCE_ADC, OSC_SOURCE_DAC
		:param source: Data source
		"""
		if ch == 1:
			self.source_ch1 = source
		elif ch == 2:
			self.source_ch2 = source
		else:
			raise ValueOutOfRangeException("Incorrect channel number %d", ch)

	def set_defaults(self):
		""" Reset the Oscilloscope to sane defaults. """
		super(Oscilloscope, self).set_defaults()
		#TODO this should reset ALL registers
		self.framerate = _OSC_FPS
		self.frame_length = _OSC_SCREEN_WIDTH

		self.set_xmode(OSC_FULL_FRAME)
		self.set_timebase(-0.25, 0.25)
		self.set_precision_mode(False)
		self.trig_mode = OSC_TRIG_AUTO
		self.set_trigger(OSC_TRIG_CH1, OSC_EDGE_RISING, 0)
		self.set_frontend(1)
		self.set_frontend(2)
		self.en_in_ch1 = True
		self.en_in_ch2 = True

	def _calculate_scales(self):
		# Returns the bits-to-volts numbers for each channel in the current state

		sect1 = "calibration.AG-%s-%s-%s-1" % ( "50" if self.relays_ch1 & RELAY_LOWZ else "1M",
								  "L" if self.relays_ch1 & RELAY_LOWG else "H",
								  "D" if self.relays_ch1 & RELAY_DC else "A")

		sect2 = "calibration.AG-%s-%s-%s-1" % ( "50" if self.relays_ch2 & RELAY_LOWZ else "1M",
								  "L" if self.relays_ch2 & RELAY_LOWG else "H",
								  "D" if self.relays_ch2 & RELAY_DC else "A")
		try:
			g1 = 1 / float(self.calibration[sect1])
			g2 = 1 / float(self.calibration[sect2])
		except (KeyError, TypeError):
			log.warning("Moku appears uncalibrated")
			g1 = g2 = 1

		log.debug("gain values for sections %s, %s = %f, %f; deci %f", sect1, sect2, g1, g2, self._deci_gain())

		if self.ain_mode == _OSC_AIN_DECI:
			g1 /= self._deci_gain()
			g2 /= self._deci_gain()

		return (g1, g2)

	def commit(self):
		super(Oscilloscope, self).commit()
		self.scales[self._stateid] = self._calculate_scales()

		# TODO: Trim scales dictionary, getting rid of old ids

	# Bring in the docstring from the superclass for our docco.
	commit.__doc__ = MokuInstrument.commit.__doc__

	def attach_moku(self, moku):
		super(Oscilloscope, self).attach_moku(moku)

		try:
			self.calibration = dict(self._moku._get_property_section("calibration"))
		except:
			log.warning("Can't read calibration values.")

	attach_moku.__doc__ = MokuInstrument.attach_moku.__doc__

_osc_reg_handlers = {
	'source_ch1':		(REG_OSC_OUTSEL,	to_reg_unsigned(0, 1, allow_set=[OSC_SOURCE_ADC, OSC_SOURCE_DAC]),
											from_reg_unsigned(0, 1)),

	'source_ch2':		(REG_OSC_OUTSEL,	to_reg_unsigned(1, 1, allow_set=[OSC_SOURCE_ADC, OSC_SOURCE_DAC]),
											from_reg_unsigned(1, 1)),

	'trig_mode':		(REG_OSC_TRIGMODE,	to_reg_unsigned(0, 2, allow_set=[OSC_TRIG_AUTO, OSC_TRIG_NORMAL, OSC_TRIG_SINGLE]),
											from_reg_unsigned(0, 2)),

	'trig_edge':		(REG_OSC_TRIGCTL,	to_reg_unsigned(0, 2, allow_set=[OSC_EDGE_RISING, OSC_EDGE_FALLING, OSC_EDGE_BOTH]),
											from_reg_unsigned(0, 2)),

	'trig_ch':			(REG_OSC_TRIGCTL,	to_reg_unsigned(4, 6, allow_set=[OSC_TRIG_CH1, OSC_TRIG_CH2, OSC_TRIG_DA1, OSC_TRIG_DA2]),
											from_reg_unsigned(4, 6)),

	'hf_reject':		(REG_OSC_TRIGCTL,	to_reg_bool(12),			from_reg_bool(12)),
	'hysteresis':		(REG_OSC_TRIGCTL,	to_reg_unsigned(16, 16),	from_reg_unsigned(16, 16)),
	'trigger_level':	(REG_OSC_TRIGLVL,	to_reg_signed(0, 32),		to_reg_signed(0, 32)),

	'loopback_mode_ch1':	(REG_OSC_ACTL,	to_reg_unsigned(0, 1, allow_set=[_OSC_LB_CLIP, _OSC_LB_ROUND]),
											from_reg_unsigned(0, 1)),
	'loopback_mode_ch2':	(REG_OSC_ACTL,	to_reg_unsigned(1, 1, allow_set=[_OSC_LB_CLIP, _OSC_LB_ROUND]),
											from_reg_unsigned(1, 1)),

	'ain_mode':			(REG_OSC_ACTL,		to_reg_unsigned(16, 2, allow_set=[_OSC_AIN_DDS, _OSC_AIN_DECI]),
											from_reg_unsigned(16, 2)),

	'decimation_rate':	(REG_OSC_DECIMATION,to_reg_unsigned(0, 32),	from_reg_unsigned(0, 32)),
}

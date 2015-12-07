
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
OSC_ROLL			= _instrument.ROLL
OSC_SWEEP			= _instrument.SWEEP
OSC_PAUSE			= _instrument.PAUSE

_OSC_LB_ROUND		= 0
_OSC_LB_CLIP		= 1

_OSC_AIN_DDS		= 0
_OSC_AIN_DECI		= 1

_OSC_ADC_SMPS		= 500e6
_OSC_BUFLEN			= 2**14
_OSC_SCREEN_WIDTH	= 1024
_OSC_FPS			= 10

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
		self.scales = {}

		super(Oscilloscope, self).__init__(_frame_instrument.VoltsFrame, scales=self.scales)
		self.id = 1
		self.type = "oscilloscope"
		self.calibration = None

	def _optimal_decimation(self, t1, t2):
		# Based on mercury_ipad/LISettings::OSCalculateOptimalADCDecimation
		ts = abs(t1 - t2)
		return math.ceil(_OSC_ADC_SMPS * ts / _OSC_BUFLEN)

	def _buffer_offset(self, t1, t2, decimation):
		# Based on mercury_ipad/LISettings::OSCalculateOptimalBufferOffset
		# TODO: Roll mode

		buffer_smps = _OSC_ADC_SMPS / decimation
		offset_secs = t1
		offset = min(max(math.ceil(offset_secs * buffer_smps / 4.0), -2**28), 2**12)

		return offset

	def _render_downsample(self, t1, t2, decimation):
		# Based on mercury_ipad/LISettings::OSCalculateRenderDownsamplingForDecimation
		buffer_smps = _OSC_ADC_SMPS / decimation
		screen_smps = min(_OSC_SCREEN_WIDTH / abs(t1 - t2), _OSC_ADC_SMPS)

		return min(max(buffer_smps / screen_smps, 1.0), 16.0)

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
		self.render_mode = RDR_CUBIC #TODO: Support other
		self.decimation_rate = self._optimal_decimation(t1, t2)
		self.pretrigger = self._buffer_offset(t1, t2, self.decimation_rate)
		self.render_deci = self._render_downsample(t1, t2, self.decimation_rate)
		self.offset = self._render_offset(t1, t2, self.decimation_rate, self.pretrigger, self.render_deci)

		log.debug("Render params: Deci %f PT: %f, RDeci: %f, Off: %f", self.decimation_rate, self.pretrigger, self.render_deci, self.offset)

		self.render_deci = 16

		# Set alternates to regular, means we get distorted frames until we get a new trigger
		self.render_deci_alt = self.render_deci
		self.offset_alt = self.offset
		self.commit()

	def set_xmode(self, xmode):
		"""
		Set rendering mode for the horizontal axis.

		:type xmode: *OSC_ROLL*, *OSC_SWEEP*, *OSC_PAUSE*
		:param xmode:
			Respectively; Roll Mode (scrolling), Sweep Mode (normal oscilloscope trace sweeping across the screen) or Paused (no updates)."""
		self.x_mode = xmode

	def set_precision_mode(self, state):
		""" Change aquisition mode between downsampling and decimation.
		Precision mode, a.k.a Decimation, samples at full rate and applies a low-pass filter to the data. This improves
		precision. Normal mode works by direct downsampling, throwing away points it doesn't need.

		:param state: Select Precision Mode
		:type state: bool """
		self.ain_mode = _OSC_AIN_DECI if state else _OSC_AIN_DDS
		self.commit()

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
		self.commit()

	def set_frontend(self, channel, fiftyr=False, atten=True, ac=False):
		""" Configures gain, coupling and termination for each channel.

		:type channel: int
		:param channel: Channel to which the settings should be applied

		:type fiftyr: bool
		:param fiftyr: 50Ohm termination; default is 1MOhm.

		:type atten: bool
		:param atten: Turn on 10x attenuation. Changes the dynamic range between 1Vpp and 10Vpp.

		:type ac: bool
		:param ac: AC-couple; default DC. """
		relays =  RELAY_LOWZ if fiftyr else 0
		relays |= RELAY_LOWG if atten else 0
		relays |= RELAY_DC if not ac else 0

		if channel == 1:
			self.relays_ch1 = relays
		elif channel == 2:
			self.relays_ch2 = relays

		self.commit()

	def set_defaults(self):
		""" Reset the Oscilloscope to sane defaults. """
		super(Oscilloscope, self).set_defaults()
		#TODO this should reset ALL registers
		self.framerate = _OSC_FPS
		self.frame_length = _OSC_SCREEN_WIDTH

		self.set_timebase(-0.25, 0.25)
		self.trig_mode = OSC_TRIG_AUTO
		self.set_trigger(OSC_TRIG_CH1, OSC_EDGE_RISING, 0)
		self.set_frontend(1)
		self.set_frontend(2)

	def _calculate_scales(self):
		# Returns the bits-to-volts numbers for each channel in the current state

		sect1 = "calibration.AG-%s-%s-%s-1" % ( "50" if self.relays_ch1 & RELAY_LOWZ else "1M",
								  "L" if self.relays_ch1 & RELAY_LOWG else "H",
								  "D" if self.relays_ch1 & RELAY_DC else "A")

		sect2 = "calibration.AG-%s-%s-%s-1" % ( "50" if self.relays_ch2 & RELAY_LOWZ else "1M",
								  "L" if self.relays_ch2 & RELAY_LOWG else "H",
								  "D" if self.relays_ch2 & RELAY_DC else "A")

		g1 = 1 / float(self.calibration[sect1])
		g2 = 1 / float(self.calibration[sect2])

		if self.ain_mode == _OSC_AIN_DECI:
			g1 /= self.decimation_rate
			g2 /= self.decimation_rate

		return (g1, g2)

	def commit(self):
		super(Oscilloscope, self).commit()
		self.scales[self._stateid] = self._calculate_scales()
		# TODO: Trim scales dictionary, getting rid of old ids

	def attach_moku(self, moku):
		super(Oscilloscope, self).attach_moku(moku)

		self.calibration = dict(self._moku._get_property_section("calibration"))

		log.debug("Oscilloscope Calibration: %s", self.calibration)

_osc_reg_hdl = [
	('source_ch1',		REG_OSC_OUTSEL,		lambda s, old: (old & ~1) | s if s in [OSC_SOURCE_ADC, OSC_SOURCE_DAC] else None,
											lambda rval: rval & 1),
	('source_ch2',		REG_OSC_OUTSEL,		lambda s, old: (old & ~2) | s << 1 if s in [OSC_SOURCE_ADC, OSC_SOURCE_DAC] else None,
											lambda rval: rval & 2 >> 1),
	('trig_mode',		REG_OSC_TRIGMODE,	lambda s, old: (old & ~3) | s if s in [OSC_TRIG_AUTO, OSC_TRIG_NORMAL, OSC_TRIG_SINGLE] else None,
											lambda rval: rval & 3),
	('trig_edge',		REG_OSC_TRIGCTL,	lambda s, old: (old & ~3) | s if s in [OSC_EDGE_RISING, OSC_EDGE_FALLING, OSC_EDGE_BOTH] else None,
											lambda rval: rval & 3),
	('trig_ch',			REG_OSC_TRIGCTL,	lambda s, old: (old & ~0x7F0) | s << 4 if s in
												[OSC_TRIG_CH1, OSC_TRIG_CH2, OSC_TRIG_DA1, OSC_TRIG_DA2] else None,
											lambda rval: rval & 0x7F0 >> 4),
	('hf_reject',		REG_OSC_TRIGCTL,	lambda s, old: (old & ~0x1000) | s << 12 if int(s) in [0, 1] else None,
											lambda rval: rval & 0x1000 >> 12),
	('hysteresis',		REG_OSC_TRIGCTL,	lambda s, old: (old & ~0xFFFF0000) | s << 16 if 0 <= s < 2**16 else None,
											lambda rval: rval & 0xFFFF0000 >> 16),
	('trigger_level',	REG_OSC_TRIGLVL,	lambda s, old: _sgn(s, 32),
											lambda rval: rval),
	('loopback_mode',	REG_OSC_ACTL,		lambda m, old: (old & ~0x01) | m if m in [_OSC_LB_CLIP, _OSC_LB_ROUND] else None,
											lambda rval: rval & 0x01),
	('ain_mode',		REG_OSC_ACTL,		lambda m, old: (old & ~0x300) | m << 16 if m in [_OSC_AIN_DDS, _OSC_AIN_DECI] else None,
											lambda rval: (rval & 0x300) >> 16),
	('decimation_rate',	REG_OSC_DECIMATION,	lambda r, old: _usgn(r, 32), lambda rval: rval),
]
_instrument._attach_register_handlers(_osc_reg_hdl, Oscilloscope)

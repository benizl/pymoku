
import math
import logging

from _instrument import *
import _instrument
import _frame_instrument

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

class Oscilloscope(_frame_instrument.FrameBasedInstrument):
	def __init__(self):
		super(Oscilloscope, self).__init__()
		self.id = 1
		self.type = "oscilloscope"

	def _optimal_decimation(self, t1, t2):
		# Based on mercury_ipad/LISettings::OSCalculateOptimalADCDecimation
		ts = abs(t1 - t2)
		bufferspan = min(max(ts, 0.1), ts * 3)
		return math.ceil(_OSC_ADC_SMPS * bufferspan / _OSC_BUFLEN)

	def _buffer_offset(self, t1, t2, decimation):
		# Based on mercury_ipad/LISettings::OSCalculateOptimalBufferOffset
		# TODO: Roll mode

		buffer_smps = _OSC_ADC_SMPS / decimation
		buffer_timespan = _OSC_BUFLEN / buffer_smps
		offset_secs = (abs(t1 - t2) + buffer_timespan) / 2.0

		return min(max(math.ceil(offset_secs * buffer_smps / 4.0), -2**28), 2**12)

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

	def set_timebase(self, t1, t2):
		self.render_mode = RDR_CUBIC #TODO: Support other
		self.decimation_rate = self._optimal_decimation(t1, t2)
		self.pretrigger = self._buffer_offset(t1, t2, self.decimation_rate)
		self.render_deci = self._render_downsample(t1, t2, self.decimation_rate)
		self.offset = self._render_offset(t1, t2, self.decimation_rate, self.pretrigger, self.render_deci)

		# Set alternates to regular, means we get distorted frames until we get a new trigger
		self.render_deci_alt = self.render_deci
		self.offset_alt = self.offset
		self.commit()

	def set_voltage_scale(self, v1, v2):
		pass

	def set_precision_mode(self, state):
		self.ain_mode = _OSC_AIN_DECI if state else _OSC_AIN_DDS
		self.commit()

	def set_trigger(self, source, edge, hysteresis=0, hf_reject=False, mode=OSC_TRIG_AUTO):
		self.trig_ch = source
		self.trig_edge = edge
		self.hysteresis = hysteresis
		self.hf_reject = hf_reject
		self.trig_mode = mode
		self.commit()

	def set_frontend(self, channel, fiftyr=False, atten=True, ac=False):
		relays =  RELAY_LOWZ if fiftyr else 0
		relays |= RELAY_LOWG if atten else 0
		relays |= RELAY_DC if not ac else 0

		if channel == 1:
			self.relays_ch1 = relays
		elif channel == 2:
			self.relays_ch2 = relays

		self.commit()

	def set_defaults(self):
		super(Oscilloscope, self).set_defaults()
		#TODO this should reset ALL registers
		self.framerate = _OSC_FPS
		self.frame_length = _OSC_SCREEN_WIDTH

		self.set_timebase(-0.25, 0.25)
		self.trig_mode = OSC_TRIG_AUTO
		self.set_trigger(OSC_TRIG_CH1, OSC_EDGE_RISING)
		self.set_frontend(1)
		self.set_frontend(2)

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
	('trigger_level',	REG_OSC_TRIGLVL,	lambda s, old: s if -2**31 <= s < 2**31 else None,
											lambda rval: rval),
	('loopback_mode',	REG_OSC_ACTL,		lambda m, old: (old & ~0x01) | m if m in [_OSC_LB_CLIP, _OSC_LB_ROUND] else None,
											lambda rval: rval & 0x01),
	('ain_mode',		REG_OSC_ACTL,		lambda m, old: (old & ~0x300) | m << 16 if m in [_OSC_AIN_DDS, _OSC_AIN_DECI] else None,
											lambda rval: (rval & 0x300) >> 16),
	('decimation_rate',	REG_OSC_DECIMATION,	lambda r, old: int(r), lambda rval: rval),
]
_instrument._attach_register_handlers(_osc_reg_hdl, Oscilloscope)

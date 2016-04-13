import numpy
import math
import logging

from _instrument import *
import _instrument
import _frame_instrument

from bisect import bisect_right

# Annoying that import * doesn't pick up function defs??
_sgn = _instrument._sgn
_usgn = _instrument._usgn

log = logging.getLogger(__name__)

REG_SA_DEMOD		= 64
REG_SA_DECCTL		= 65
REG_SA_RBW			= 66
REG_SA_REFLVL		= 67

REG_SA_SOS0_GAIN	= 68
REG_SA_SOS0_A1		= 69
REG_SA_SOS0_A2		= 70
REG_SA_SOS0_B1		= 71

REG_SA_SOS1_GAIN	= 72
REG_SA_SOS1_A1		= 73
REG_SA_SOS1_A2		= 74
REG_SA_SOS1_B1		= 75

REG_SA_SOS2_GAIN	= 76
REG_SA_SOS2_A1		= 77
REG_SA_SOS2_A2		= 78
REG_SA_SOS2_B1		= 79

SA_WIN_NONE			= 0
SA_WIN_BH			= 1
SA_WIN_HANNING		= 2
SA_WIN_FLATTOP		= 3

_SA_ADC_SMPS		= 500e6
_SA_BUFLEN			= 2**14
_SA_SCREEN_WIDTH	= 1024
_SA_SCREEN_STEPS	= _SA_SCREEN_WIDTH - 1
_SA_FPS				= 10
_SA_FFT_LENGTH		= 8192/2

_SA_FREQ_SCALE		= 2**32 / _SA_ADC_SMPS

_SA_WINDOW_WIDTH = {
	SA_WIN_NONE : 0.89,
	SA_WIN_BH : 1.90,
	SA_WIN_HANNING : 1.44,
	SA_WIN_FLATTOP : 3.77
}

_SA_WINDOW_POWER = {
	SA_WIN_NONE : 131072.0,
	SA_WIN_BH : 47015.48706054688,
	SA_WIN_HANNING : 65527.00146484375,
	SA_WIN_FLATTOP : 28268.48803710938
}

_SA_IIR_COEFFS = [
	[	0,		0,		0,		0,		0,	  	0,		0,		0,		0,		0,		0,		0		],
	[	14944,	-12266,	10294,	30435,	11152,	-9212,	3762,	31497,	19264,	-8012,	1235,	32595	],
	[	4612,	-26499,	13092,	9531,	3316,	-22470,	8647,	17863,	4944,	-20571,	6566,	30281	],
	[	4296,	-28367,	13784,	-5293,	2800,	-24817,	10041,	4845,	3352,	-23031,	8171,	26839	],
	[	5160,	-28938,	14034,	-13960,	3144,	-25574,	10538,	-4659,	3048,	-23807,	8717,	22847	],
	[	4740,	-29854,	14451,	-19218,	2784,	-26946,	11473,	-11323,	2256,	-25371,	9871,	18615	],
	[	4516,	-30420,	14737,	-22588,	2588,	-27862,	12140,	-16025,	1800,	-26448,	10711,	14366	],
	[	4380,	-30803,	14948,	-24860,	2472,	-28522,	12642,	-19408,	1512,	-27240,	11352,	10256	],
	[	4292,	-31080,	15109,	-26457,	2396,	-29022,	13036,	-21899,	1312,	-27851,	11860,	6385	],
	[	4232,	-31289,	15238,	-27620,	2344,	-29415,	13353,	-23773,	1176,	-28337,	12272,	2807	],
	[	4188,	-31453,	15342,	-28491,	2308,	-29732,	13614,	-25214,	1072,	-28734,	12615,	-457	],
	[	4156,	-31584,	15429,	-29159,	2284,	-29993,	13833,	-26341,	1000,	-29064,	12904,	-3408	],
	[	4136,	-31692,	15502,	-29684,	2264,	-30213,	14020,	-27238,	936,	-29344,	13151,	-6059	],
	[	4116,	-31782,	15565,	-30102,	2248,	-30399,	14180,	-27962,	888,	-29584,	13365,	-8433	],
	[	4104,	-31858,	15619,	-30441,	2240,	-30561,	14321,	-28555,	856,	-29792,	13552,	-10553	],
	[	4092,	-31923,	15667,	-30719,	2232,	-30701,	14444,	-29046,	824,	-29974,	13717,	-12446	]
]

'''
_DECIMATIONS_TABLE = sorted([ (d1 * (d2+1) * (d3+1) * (d4+1), d1, d2+1, d3+1, d4+1)
								for d1 in [4]
								for d2 in range(64)
								for d3 in range(16)
								for d4 in range(16)], key=lambda x: (x[0],x[4],x[3]))'''

class SpectrumFrame(_frame_instrument.DataFrame):
	"""
	Object representing a frame of data in units of power vs frequency. This is the native output format of
	the :any:`SpecAn` instrument and similar.

	This object should not be instantiated directly, but will be returned by a supporting *get_frame*
	implementation.

	.. autoinstanceattribute:: pymoku._frame_instrument.SpectrumFrame.ch1
		:annotation: = [CH1_DATA]

	.. autoinstanceattribute:: pymoku._frame_instrument.SpectrumFrame.ch2
		:annotation: = [CH2_DATA]

	.. autoinstanceattribute:: pymoku._frame_instrument.SpectrumFrame.frameid
		:annotation: = n

	.. autoinstanceattribute:: pymoku._frame_instrument.SpectrumFrame.waveformid
		:annotation: = n
	"""
	def __init__(self, scales):
		super(SpectrumFrame, self).__init__()

		#: Channel 1 data array in units of power. Present whether or not the channel is enabled, but the
		#: contents are undefined in the latter case.
		self.ch1 = []

		#: Channel 2 data array in units of power.
		self.ch2 = []

		self.scales = scales

		# TODO: This should associate the frequency span, RBW etc.

		# Assume the same frequency span is associated with both channels
		self.fs = []

	def process_complete(self):

		if self.stateid not in self.scales:
			log.error("Can't render specan frame, haven't saved calibration data for state %d", self.stateid)
			return

		scales = self.scales[self.stateid]
		# Do more processing here based on current instrument state (i.e. rbw, decimation gains)
		scale1 = scales['g1']
		scale2 = scales['g2']
		f1, f2 = scales['fs']

		try:
			smpls = int(len(self.raw1) / 4)
			dat = struct.unpack('<' + 'i' * smpls, self.raw1)
			dat = [ x if x != -0x80000000 else None for x in dat ]

			# SpecAn data is backwards because $(EXPLETIVE), also remove zeros for the sake of common
			# display on a log axis.
			self.ch1_bits = [ max(float(x), 1) if x is not None else None for x in reversed(dat[:1024]) ]
			self.ch1 = [ x * scale1 if x is not None else None for x in self.ch1_bits]

			# Put the frequencies in here
			self.ch1_fs = numpy.linspace(f1,f2,_SA_SCREEN_WIDTH)

			smpls = int(len(self.raw2) / 4)
			dat = struct.unpack('<' + 'i' * smpls, self.raw2)
			dat = [ x if x != -0x80000000 else None for x in dat ]

			self.ch2_bits = [ max(float(x), 1) if x is not None else None for x in reversed(dat[:1024]) ]
			self.ch2 = [ x * scale2 if x is not None else None for x in self.ch2_bits]

			# Put the frequencies in here
			self.ch2_fs = numpy.linspace(f1,f2,_SA_SCREEN_WIDTH)
		except (IndexError, TypeError, struct.error):
			# If the data is bollocksed, force a reinitialisation on next packet
			log.exception("SpecAn packet")
			self.frameid = None
			self.complete = False

		# A valid frame is there's at least one valid sample in each channel
		return any(self.ch1) and any(self.ch2)

	'''
		Plotting helper functions
	'''
	def _get_freqScale(self, f):
		# Returns a scaling factor and units for frequency 'X'
		if(f > 1e6):
			scale_str = 'MHz'
			scale_const = 1e-6
		elif (f > 1e3):
			scale_str = 'kHz'
			scale_const = 1e-3
		elif (f > 1):
			scale_str = 'Hz'
			scale_const = 1
		elif (f > 1e-3):
			scale_str = 'mHz'
			scale_const = 1e3
		else:
			scale_str = 'uHz'
			scale_const = 1e6

		return [scale_str,scale_const]

	def get_freqFmt(self,x,pos):
		if self.stateid not in self.scales:
			log.error("Can't get current frequency format, haven't saved calibration data for state %d", self.stateid)
			return

		scales = self.scales[self.stateid]
		f1, f2 = scales['fs']

		fscale_str, fscale_const = self._get_freqScale(f2)

		return '%.1f %s' % (x*fscale_const, fscale_str)


class SpecAn(_frame_instrument.FrameBasedInstrument):
	""" Spectrum Analyser instrument object. This should be instantiated and attached to a :any:`Moku` instance.

	.. automethod:: pymoku.instruments.SpecAn.__init__

	.. attribute:: hwver

		Hardware Version

	.. attribute:: hwserial

		Hardware Serial Number

	.. attribute:: framerate
		:annotation: = 10

		Frame Rate, range 1 - 30.

	.. attribute:: type
		:annotation: = "specan"

		Name of this instrument.

	"""
	def __init__(self):
		"""Create a new Spectrum Analyser instrument, ready to be attached to a Moku."""
		self.scales = {}

		super(SpecAn, self).__init__(SpectrumFrame, scales=self.scales)
		self.id = 2
		self.type = "specan"
		self.calibration = None

		self.set_span(0, 250e6)
		self.set_rbw(None)
		self.set_window(SA_WIN_BH)

	def _calculate_decimations(self, f1, f2):
		# Computes the decimations given the input span
		# Doesn't guarantee a total decimation of the ideal value, even if such an integer sequence exists
		fspan = f2 - f1
		ideal = math.floor(_SA_ADC_SMPS / 2.0 /  fspan)
		if ideal < 4:
			d1 = 1
			d2 = d3 = d4 = 1
		else:
			# Put some optimal algorithm here to compute the decimations
			'''deci_idx = bisect_right(_DECIMATIONS_TABLE, (ideal,99,99,99,99))
			deci, d1, d2, d3, d4 = _DECIMATIONS_TABLE[deci_idx - 1]

			print "Table entry: %d, %d, %d, %d, %d, %d" % (deci_idx-1, deci, d1, d2, d3, d4)'''

			d1 = 4
			dec = ideal / d1

			d2 = min(max(math.ceil(dec / 16 / 16), 1), 64)
			dec /= d2

			d3 = min(max(math.ceil(dec / 16), 1), 16)
			dec /= d3

			d4 = min(max(math.floor(dec), 1), 16)

		return [d1, d2, d3, d4, ideal]

	def _set_decimations(self):
		d1, d2, d3, d4, ideal = self._calculate_decimations(self.f1, self.f2)

		# d1 can only be x4 decimation
		self.dec_enable = d1 == 4
		self.dec_cic2 = d2
		self.dec_cic3 = d3
		self.dec_iir  = d4

		self.bs_cic2 = math.ceil(2 * math.log(d2, 2))
		self.bs_cic3 = math.ceil(3 * math.log(d3, 2))

		self._total_decimation = d1 * d2 * d3 * d4

		log.debug("Decimations: %d %d %d %d = %d (ideal %f)", d1, d2, d3, d4, self._total_decimation, ideal)

	def _setup_controls(self):
		# This function sets all relevant registers based on chosen settings
		# Set the CIC decimations
		self._set_decimations()

		# Mix the signal down to DC using maximum span frequency
		self.demod = self._f2_full

		fspan = self._f2_full - self._f1_full
		buffer_span = _SA_ADC_SMPS / 2.0 / self._total_decimation

		self.render_dds = min(max(math.ceil(fspan / buffer_span * _SA_FFT_LENGTH/ _SA_SCREEN_STEPS), 1.0), 4.0)
		self.render_dds_alt = self.render_dds

		filter_set = _SA_IIR_COEFFS[self.dec_iir-1]
		self.gain_sos0, self.a1_sos0, self.a2_sos0, self.b1_sos0 = filter_set[0:4]
		self.gain_sos1, self.a1_sos1, self.a2_sos1, self.b1_sos1 = filter_set[4:8]
		self.gain_sos2, self.a1_sos2, self.a2_sos2, self.b1_sos2 = filter_set[8:12]

		# Calculate RBW
		window_factor = _SA_WINDOW_WIDTH[self.window]
		fbin_resolution = _SA_ADC_SMPS / 2.0 / _SA_FFT_LENGTH / self._total_decimation
		# "Auto" RBW is 5 screen points
		rbw = self.rbw or 5 * fspan / _SA_SCREEN_WIDTH
		rbw = min(max(rbw, 17.0 / 16.0 * fbin_resolution * window_factor), 2.0**10.0 * fbin_resolution * window_factor)
		
		self.rbw_ratio = round(rbw / window_factor / fbin_resolution)

		self.ref_level = 6

		log.debug("DM: %f FS: %f, BS: %f, RD: %f, W:%d, RBW: %f, RBR: %f", self.demod, fspan, buffer_span, self.render_dds, self.window, rbw, self.rbw_ratio)

	def set_span(self, f1, f2):
		# TODO: Enforce f2 > f1
		self.f1 = f1
		self.f2 = f2

		# Fullspan variables are cleared
		self._f1_full = f1
		self._f2_full = f2

	def set_fullspan(self,f1,f2):
		# This sets the fullspan frequencies _f1_full, _f2_full to the nearest buffspan
		# Allowing a full FFT frame to be valid data

		# Set the actual input frequencies
		self.f1 = f1
		self.f2 = f2
		fspan = f2 - f1

		# Get the decimations that would be used for this input fspan
		d1, d2, d3, d4, ideal = self._calculate_decimations(f1, f2)
		total_deci = d1 * d2 * d3 * d4

		# Compute the resulting buffspan
		bufspan = _SA_ADC_SMPS / 2.0 / total_deci

		# Force the _f1_full, _f2_full to the nearest bufspan
		# Move f2 up first
		d_span = bufspan - fspan
		# Find out how much spillover there will be
		high_remainder = ((f2 + d_span)%(_SA_ADC_SMPS/2.0)) if(f2 + d_span > _SA_ADC_SMPS/2.0) else 0.0

		new_f2 = min(f2 + d_span, _SA_ADC_SMPS/2.0)
		new_f1 = max(f1 - high_remainder, 0.0)
		log.debug("Setting Full Span: (f1, %f), (f2, %f), (fspan, %f), (bufspan, %f) -> (f1_full, %f), (f2_full, %f), (fspan_full, %f)", f1, f2, fspan, bufspan, new_f1, new_f2, new_f2-new_f1)

		self._f1_full = new_f1
		self._f2_full = new_f2

	def set_rbw(self, rbw=None):
		self.rbw = rbw

	def set_window(self, window):
		self.window = window

	def set_defaults(self):
		""" Reset the Spectrum Analyser to sane defaults. """
		super(SpecAn, self).set_defaults()
		#TODO this should reset ALL registers
		self.framerate = _SA_FPS
		self.frame_length = _SA_SCREEN_WIDTH

		self.offset = -4
		self.offset_alt = -4

		self.render_mode = RDR_DDS
		self.x_mode = FULL_FRAME

		self.set_frontend(1)
		self.set_frontend(2)

	def _calculate_scales(self):
		# Returns the bits-to-volts numbers for each channel in the current state

		# TODO: Centralise the calibration parsing, shared with Oscilloscope

		sect1 = "calibration.AG-%s-%s-%s-1" % ( "50" if self.relays_ch1 & RELAY_LOWZ else "1M",
								  "L" if self.relays_ch1 & RELAY_LOWG else "H",
								  "D" if self.relays_ch1 & RELAY_DC else "A")

		sect2 = "calibration.AG-%s-%s-%s-1" % ( "50" if self.relays_ch2 & RELAY_LOWZ else "1M",
								  "L" if self.relays_ch2 & RELAY_LOWG else "H",
								  "D" if self.relays_ch2 & RELAY_DC else "A")

		try:
			g1 = 1 / float(self.calibration[sect1])
			g2 = 1 / float(self.calibration[sect2])
		except KeyError:
			log.warning("Moku appears uncalibrated")
			g1 = g2 = 1

		filt_gain2 = 2.0 ** (self.bs_cic2 - 2.0 * math.log(self.dec_cic2, 2))
		filt_gain3 = 2.0 ** (self.bs_cic3 - 3.0 * math.log(self.dec_cic3, 2))
		filt_gain4 = 2**8 if self.dec_iir else 1

		filt_gain = filt_gain2 * filt_gain3 * filt_gain4
		window_gain = 1 / _SA_WINDOW_POWER[self.window]

		g1 *= filt_gain * window_gain * self.rbw_ratio
		g2 *= filt_gain * window_gain * self.rbw_ratio

		log.debug("Scales: %f,%f,%f,%f", g1, g2, self._f1_full, self._f2_full)

		return {'g1': g1, 'g2': g2, 'fs': [self._f1_full, self._f2_full]}


	def commit(self):
		# Compute remaining control register values based on window, rbw and fspan
		self._setup_controls()

		# Push the controls through to the device
		super(SpecAn, self).commit()

		# Update the scaling factors for processing of incoming frames
		# stateid allows us to track which scales correspond to which register state
		self.scales[self._stateid] = self._calculate_scales()

		# TODO: Trim scales dictionary, getting rid of old ids

	# Bring in the docstring from the superclass for our docco.
	commit.__doc__ = _instrument.MokuInstrument.commit.__doc__

	def attach_moku(self, moku):
		super(SpecAn, self).attach_moku(moku)

		# The moku contains calibration data for various configurations
		self.calibration = dict(self._moku._get_property_section("calibration"))

	attach_moku.__doc__ = _instrument.MokuInstrument.attach_moku.__doc__

_sa_reg_hdl = [
	('demod',			REG_SA_DEMOD,		lambda r, old: _usgn(r * _SA_FREQ_SCALE, 32), lambda rval: rval / _SA_FREQ_SCALE),
	('dec_enable',		REG_SA_DECCTL,		lambda r, old: (old & ~1) | int(r) if int(r) in [0, 1] else None,
											lambda rval: bool(rval & 1)),
	('dec_cic2',		REG_SA_DECCTL,		lambda r, old: (old & ~0x7E) | _usgn(r - 1, 6) << 1,
											lambda rval: ((rval & 0x7E) >> 1) + 1),
	('bs_cic2',			REG_SA_DECCTL,		lambda r, old: (old & ~0x780) | _usgn(r, 4) << 7,
											lambda rval: rval & 0x780 >> 7),
	('dec_cic3',		REG_SA_DECCTL,		lambda r, old: (old & ~0x7800) | _usgn(r - 1, 4) << 11,
											lambda rval: ((rval & 0x7800) >> 11) + 1),
	('bs_cic3',			REG_SA_DECCTL,		lambda r, old: (old & ~0x78000) | _usgn(r, 4) << 15,
											lambda rval: rval & 0x78000 >> 15),
	('dec_iir',			REG_SA_DECCTL,		lambda r, old: (old & ~0x780000) | _usgn(r - 1, 4) << 19,
											lambda rval: ((rval & 0x780000) >> 19) + 1),
	('rbw_ratio',		REG_SA_RBW,			lambda r, old: (old & ~0xFFFFFF) | _usgn(r * 2**10, 24),
											lambda rval: (rval & 0xFFFFFF) / 2**10),
	('window',			REG_SA_RBW,			lambda r, old: (old & ~0x3000000) | r << 24 if r in [SA_WIN_NONE, SA_WIN_BH, SA_WIN_HANNING, SA_WIN_FLATTOP] else None,
											lambda rval: (rval & 0x3000000) >> 24),
	('ref_level',		REG_SA_REFLVL,		lambda r, old: (old & ~0x0F) | _usgn(r, 4),
											lambda rval: rval & 0x0F),
	('gain_sos0',		REG_SA_SOS0_GAIN,	lambda r, old: _sgn(r, 18),
											lambda rval: rval),
	('a1_sos0',			REG_SA_SOS0_A1,		lambda r, old: _sgn(r, 18),
											lambda rval: rval),
	('a2_sos0',			REG_SA_SOS0_A2,		lambda r, old: _sgn(r, 18),
											lambda rval: rval),
	('b1_sos0',			REG_SA_SOS0_B1,		lambda r, old: _sgn(r, 18),
											lambda rval: rval),
	('gain_sos1',		REG_SA_SOS1_GAIN,	lambda r, old: _sgn(r, 18),
											lambda rval: rval),
	('a1_sos1',			REG_SA_SOS1_A1,		lambda r, old: _sgn(r, 18),
											lambda rval: rval),
	('a2_sos1',			REG_SA_SOS1_A2,		lambda r, old: _sgn(r, 18),
											lambda rval: rval),
	('b1_sos1',			REG_SA_SOS1_B1,		lambda r, old: _sgn(r, 18),
											lambda rval: rval),
	('gain_sos2',		REG_SA_SOS2_GAIN,	lambda r, old: _sgn(r, 18),
											lambda rval: rval),
	('a1_sos2',			REG_SA_SOS2_A1,		lambda r, old: _sgn(r, 18),
											lambda rval: rval),
	('a2_sos2',			REG_SA_SOS2_A2,		lambda r, old: _sgn(r, 18),
											lambda rval: rval),
	('b1_sos2',			REG_SA_SOS2_B1,		lambda r, old: _sgn(r, 18),
											lambda rval: rval),
]
_instrument._attach_register_handlers(_sa_reg_hdl, SpecAn)

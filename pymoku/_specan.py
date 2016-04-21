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

SA_WIN_BH			= 0
SA_WIN_FLATTOP		= 1
SA_WIN_HANNING		= 2
SA_WIN_NONE			= 3

_SA_ADC_SMPS		= 500e6
_SA_BUFLEN			= 2**14
_SA_SCREEN_WIDTH	= 1024
_SA_SCREEN_STEPS	= _SA_SCREEN_WIDTH - 1
_SA_FPS				= 10
_SA_FFT_LENGTH		= 8192/2
_SA_FREQ_SCALE		= 2**32 / _SA_ADC_SMPS
_SA_INT_VOLTS_SCALE = (1.437*pow(2.0,-8.0))

'''
	FILTER GAINS AND CORRECTION FACTORS
'''
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

_SA_ADC_FREQ_RESP_0 = [ 1.0000,
    1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000,
    1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000,
    1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000,
    1.0000, 1.0000, 1.0001, 1.0006, 1.0015, 1.0028, 1.0041, 1.0053, 1.0061, 1.0064, 1.0056, 1.0052, 1.0048, 1.0039, 1.0034, 1.0024,
    1.0012, 0.9999, 0.9983, 0.9971, 0.9953, 0.9936, 0.9922, 0.9910, 0.9894, 0.9877, 0.9866, 0.9860, 0.9863, 0.9862, 0.9868, 0.9867,
    0.9873, 0.9881, 0.9891, 0.9901, 0.9908, 0.9913, 0.9922, 0.9935, 0.9940, 0.9941, 0.9936, 0.9927, 0.9923, 0.9911, 0.9897, 0.9876,
    0.9853, 0.9826, 0.9801, 0.9776, 0.9753, 0.9731, 0.9707, 0.9685, 0.9663, 0.9641, 0.9627, 0.9618, 0.9615, 0.9611, 0.9605, 0.9602,
    0.9601, 0.9604, 0.9607, 0.9609, 0.9613, 0.9613, 0.9616, 0.9615, 0.9606, 0.9602, 0.9593, 0.9586, 0.9570, 0.9554, 0.9536, 0.9518,
    0.9496, 0.9473, 0.9451, 0.9429, 0.9408, 0.9388, 0.9368, 0.9355, 0.9343, 0.9342, 0.9336, 0.9335, 0.9330, 0.9333, 0.9328, 0.9328,
    0.9328, 0.9325, 0.9317, 0.9304, 0.9296, 0.9283, 0.9266, 0.9245, 0.9211, 0.9180, 0.9142, 0.9100, 0.9058, 0.9009, 0.8964, 0.8917,
    0.8875, 0.8829, 0.8788, 0.8748, 0.8713, 0.8687, 0.8661, 0.8644, 0.8626, 0.8618, 0.8617, 0.8625, 0.8631, 0.8650, 0.8663, 0.8678,
    0.8685, 0.8691, 0.8703, 0.8708, 0.8712, 0.8706, 0.8691, 0.8661, 0.8621, 0.8569, 0.8510, 0.8442, 0.8366, 0.8285, 0.8198, 0.8107,
    0.8015, 0.7916, 0.7824, 0.7732, 0.7659, 0.7581, 0.7519, 0.7460, 0.7415, 0.7375, 0.7338, 0.7312, 0.7298, 0.7295, 0.7297, 0.7306,
    0.7322, 0.7341, 0.7362, 0.7381, 0.7403, 0.7417, 0.7425, 0.7420, 0.7406, 0.7378, 0.7338, 0.7283, 0.7219, 0.7138, 0.7049, 0.6945,
    0.6839, 0.6721, 0.6601, 0.6480, 0.6364, 0.6250, 0.6142, 0.6039, 0.5945, 0.5863, 0.5784, 0.5716, 0.5656, 0.5610, 0.5572, 0.5543,
    0.5519, 0.5503, 0.5498, 0.5500, 0.5505, 0.5509, 0.5517, 0.5521, 0.5518, 0.5510, 0.5497, 0.5476, 0.5453, 0.5427, 0.5404, 0.5383 ]
    
_SA_ADC_FREQ_RESP_20 = [ 1.0000,
    1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000,
    1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000,
    1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000,
    1.0000, 1.0000, 0.9999, 0.9993, 0.9996, 1.0003, 1.0008, 1.0010, 1.0004, 1.0007, 1.0006, 1.0003, 0.9999, 0.9993, 0.9984, 0.9978,
    0.9975, 0.9972, 0.9968, 0.9956, 0.9944, 0.9940, 0.9928, 0.9921, 0.9916, 0.9921, 0.9927, 0.9928, 0.9926, 0.9923, 0.9923, 0.9923,
    0.9922, 0.9923, 0.9931, 0.9947, 0.9954, 0.9968, 0.9978, 0.9982, 0.9985, 0.9983, 0.9985, 0.9991, 0.9993, 1.0000, 0.9999, 0.9996,
    0.9989, 0.9986, 0.9982, 0.9981, 0.9976, 0.9973, 0.9970, 0.9962, 0.9957, 0.9950, 0.9944, 0.9940, 0.9940, 0.9939, 0.9940, 0.9937,
    0.9943, 0.9942, 0.9953, 0.9959, 0.9967, 0.9973, 0.9971, 0.9977, 0.9981, 0.9986, 0.9984, 0.9982, 0.9972, 0.9970, 0.9963, 0.9954,
    0.9944, 0.9933, 0.9926, 0.9917, 0.9900, 0.9888, 0.9876, 0.9876, 0.9873, 0.9861, 0.9850, 0.9840, 0.9839, 0.9839, 0.9840, 0.9843,
    0.9842, 0.9836, 0.9821, 0.9818, 0.9819, 0.9820, 0.9810, 0.9794, 0.9776, 0.9760, 0.9741, 0.9720, 0.9698, 0.9674, 0.9654, 0.9621,
    0.9586, 0.9555, 0.9516, 0.9486, 0.9455, 0.9429, 0.9403, 0.9381, 0.9365, 0.9357, 0.9344, 0.9319, 0.9303, 0.9304, 0.9301, 0.9298,
    0.9280, 0.9271, 0.9272, 0.9264, 0.9259, 0.9254, 0.9247, 0.9247, 0.9229, 0.9204, 0.9179, 0.9160, 0.9138, 0.9109, 0.9056, 0.9019,
    0.8952, 0.8893, 0.8830, 0.8773, 0.8732, 0.8694, 0.8627, 0.8562, 0.8468, 0.8389, 0.8318, 0.8258, 0.8225, 0.8173, 0.8135, 0.8088,
    0.8051, 0.8018, 0.7992, 0.7970, 0.7952, 0.7929, 0.7914, 0.7902, 0.7888, 0.7865, 0.7839, 0.7815, 0.7778, 0.7739, 0.7696, 0.7652,
    0.7595, 0.7526, 0.7453, 0.7387, 0.7310, 0.7228, 0.7139, 0.7054, 0.6965, 0.6872, 0.6786, 0.6702, 0.6619, 0.6538, 0.6452, 0.6385,
    0.6320, 0.6270, 0.6211, 0.6158, 0.6107, 0.6061, 0.6016, 0.5972, 0.5929, 0.5895, 0.5863, 0.5832, 0.5814, 0.5794, 0.5780, 0.5765 ]

'''
	IDEAL DECIMATIONS TABLE
	TODO: Use this in _calculate_decimations function so we aren't underutilising the CIC/IIR filters
'''
'''
_DECIMATIONS_TABLE = sorted([ (d1 * (d2+1) * (d3+1) * (d4+1), d1, d2+1, d3+1, d4+1)
								for d1 in [4]
								for d2 in range(64)
								for d3 in range(16)
								for d4 in range(16)], key=lambda x: (x[0],x[4],x[3]))
'''

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

	.. autoinstanceattribute:: pymoku._frame_instrument.SpectrumFrame.fs
		:annotation: = [FREQ]

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

		#: The frequency range associated with both channels
		self.fs = []

		#: Obtain all data scaling factors relevant to current SpecAn configuration
		self.scales = scales

	# convert an RMS voltage to a power level (assuming 50Ohm load)
	def _vrms_to_dbm(self, v):
		return 10.0*math.log(v*v/50.0,10) + 30.0

	def process_complete(self):

		if self.stateid not in self.scales:
			log.error("Can't render specan frame, haven't saved calibration data for state %d", self.stateid)
			return

		# Get scaling/correction factors based on current instrument configuration
		scales = self.scales[self.stateid]
		scale1 = scales['g1']
		scale2 = scales['g2']
		fs = scales['fs']
		f1, f2 = scales['fspan']
		fcorrs = scales['fcorrs']
		dbmscale = scales['dbmscale']

		try:
			# Find the starting index for the valid frame data
			# SpecAn generally gives more than we ask for due to integer decimations
			start_index = bisect_right(fs,f1)

			# Set the frequency range of valid data in the current frame (same for both channels)
			self.ch1_fs = fs[start_index:-1]
			self.ch2_fs = fs[start_index:-1]

			##################################
			# Process Ch1 Data
			##################################
			smpls = int(len(self.raw1) / 4)
			dat = struct.unpack('<' + 'i' * smpls, self.raw1)
			dat = [ x if x != -0x80000000 else None for x in dat ]

			# SpecAn data is backwards because $(EXPLETIVE), also remove zeros for the sake of common
			# display on a log axis.
			self.ch1_bits = [ max(float(x), 1) if x is not None else None for x in reversed(dat[:_SA_SCREEN_WIDTH]) ]

			# Apply frequency dependent corrections
			self.ch1 = [ self._vrms_to_dbm(a*c*scale1) if dbmscale else a*c*scale1 if a is not None else None for a,c in zip(self.ch1_bits, fcorrs)]

			# Trim invalid part of frame
			self.ch1 = self.ch1[start_index:-1]

			##################################
			# Process Ch2 Data
			##################################
			smpls = int(len(self.raw2) / 4)
			dat = struct.unpack('<' + 'i' * smpls, self.raw2)
			dat = [ x if x != -0x80000000 else None for x in dat ]

			self.ch2_bits = [ max(float(x), 1) if x is not None else None for x in reversed(dat[:_SA_SCREEN_WIDTH]) ]

			self.ch2 = [ self._vrms_to_dbm(a*c*scale2) if dbmscale else a*c*scale2 if a is not None else None for a,c in zip(self.ch2_bits, fcorrs)]
			self.ch2 = self.ch2[start_index:-1]

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

	def get_xaxis_fmt(self,x,pos):
		# This function returns a format string for the frequency scale
		# Use this to set an x-axis format during plotting of SpecAn frames

		if self.stateid not in self.scales:
			log.error("Can't get x-axis format, haven't saved calibration data for state %d", self.stateid)
			return

		scales = self.scales[self.stateid]
		f1, f2 = scales['fspan']

		fscale_str, fscale_const = self._get_freqScale(f2)

		return '%.1f %s' % (x*fscale_const, fscale_str)

	def get_yaxis_fmt(self,y,pos):

		if self.stateid not in self.scales:
			log.error("Can't get current frequency format, haven't saved calibration data for state %d", self.stateid)
			return

		scales = self.scales[self.stateid]
		dbm = scales['dbmscale']

		yfmt = {
			'linear' : '%.1f %s' % (y,'V'),
			'log' : '%.1f %s' % (y,'dBm')
		}

		return (yfmt['log'] if dbm else yfmt['linear'])

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

		self.set_dbmscale(True)

	def _calculate_decimations(self, f1, f2):
		# Computes the decimations given the input span
		# Doesn't guarantee a total decimation of the ideal value, even if such an integer sequence exists
		fspan = f2 - f1
		ideal = math.floor(_SA_ADC_SMPS / 8.0 /  fspan)
		if ideal < 2:
			d1 = 1
			d2 = d3 = d4 = 1
		else:

			'''
			# TODO: Use the table of optimal decimations to find d1-d4
			deci_idx = bisect_right(_DECIMATIONS_TABLE, (ideal,99,99,99,99))
			deci, d1, d2, d3, d4 = _DECIMATIONS_TABLE[deci_idx - 1]
			'''

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
		self.bs_cic2 = math.ceil(2 * math.log(d2, 2))
		self.bs_cic3 = math.ceil(3 * math.log(d3, 2))

		self.dec_enable = d1 == 4
		self.dec_cic2 = d2
		self.dec_cic3 = d3
		self.dec_iir  = d4

		self._total_decimation = d1 * d2 * d3 * d4

		log.debug("Decimations: %d %d %d %d = %d (ideal %f)", d1, d2, d3, d4, self._total_decimation, ideal)

	def _set_rbw_ratio(self, fspan):
		# Sets the RBW ratio based on current device settings
		window_factor = _SA_WINDOW_WIDTH[self.window]
		fbin_resolution = _SA_ADC_SMPS / 2.0 / _SA_FFT_LENGTH / self._total_decimation

		# "Auto" RBW is 5 screen points
		rbw = self.rbw or 5 * fspan / _SA_SCREEN_WIDTH
		rbw = min(max(rbw, 17.0 / 16.0 * fbin_resolution * window_factor), 2.0**10.0 * fbin_resolution * window_factor)
		# To match the iPad code, we round the bitshifted ratio, then bitshift back again so the register accessor can do it
		self.rbw_ratio = round(2**10*rbw / window_factor / fbin_resolution)/2**10

		return rbw

	def _setup_controls(self):
		# Set the demodulation frequency to mix down the signal to DC
		self.demod = self._f2_full

		# Set the CIC decimations
		self._set_decimations()

		# Set the filter gains based on the set CIC decimations
		filter_set = _SA_IIR_COEFFS[self.dec_iir-1]
		self.gain_sos0, self.a1_sos0, self.a2_sos0, self.b1_sos0 = filter_set[0:4]
		self.gain_sos1, self.a1_sos1, self.a2_sos1, self.b1_sos1 = filter_set[4:8]
		self.gain_sos2, self.a1_sos2, self.a2_sos2, self.b1_sos2 = filter_set[8:12]

		# Set rendering decimations
		fspan = self._f2_full - self._f1_full
		buffer_span = _SA_ADC_SMPS / 2.0 / self._total_decimation
		self.render_dds = min(max(math.ceil(fspan / buffer_span * _SA_FFT_LENGTH/ _SA_SCREEN_STEPS), 1.0), 4.0)
		self.render_dds_alt = self.render_dds

		# Calculate the Resolution Bandwidth (RBW)
		rbw = self._set_rbw_ratio(fspan)

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

	def window_type(self, name):
		if (name=='BH'):
			win = SA_WIN_BH
		elif (name=='FLATTOP'):
			win = SA_WIN_FLATTOP
		elif (name=='HANNING'):
			win = SA_WIN_HANNING
		elif (name=='NONE'):
			win = SA_WIN_NONE
		else:
			win = SA_WIN_NONE
			log.error('Invalid window type %s. Choose one of {{FLATTOP, HANNING, BH, NONE}}',name)
		return win

	def set_dbmscale(self,dbm=True):
		self.dbmscale = dbm

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

		self.set_frontend(1,fiftyr=False, atten=True, ac=False)
		self.set_frontend(2,fiftyr=False, atten=True, ac=False)

		self.set_dbmscale(True)

	def _calculate_freqStep(self, decimation, render_downsamp):
		bufspan = _SA_ADC_SMPS / 2.0 / decimation
		buf_freq_step = bufspan/_SA_FFT_LENGTH

		return (buf_freq_step * render_downsamp)

	def _calculate_startFreq(self, decimation, demod_freq, render_downsamp, frame_offset):
		freq_step = self._calculate_freqStep(decimation, render_downsamp)

		bufspan = _SA_ADC_SMPS / 2.0 / decimation
		buf_start_freq = demod_freq
		buf_freq_step = bufspan/_SA_FFT_LENGTH

		dev_stop_freq = buf_start_freq + (self.offset+4) * buf_freq_step

		return (dev_stop_freq - _SA_SCREEN_WIDTH * freq_step)

	def _calculate_adc_freq_resp(self, f, atten):
		frac_idx = f/(_SA_ADC_SMPS/2.0)

		floatIndex = (len(_SA_ADC_FREQ_RESP_0) - 1) * min(max(frac_idx,0.0),1.0)
		r = _SA_ADC_FREQ_RESP_20 if atten else _SA_ADC_FREQ_RESP_0

		# Return linear interpolation of table values
		correction = r[int(math.floor(floatIndex))] + (floatIndex - math.floor(floatIndex))*(r[int(math.ceil(floatIndex))] - r[int(math.floor(floatIndex))])
		return correction

	def _calculate_cic_freq_resp(self, f, dec, order):
		freq = f/_SA_ADC_SMPS

		correction = 1.0 if (freq == 0.0) else pow(math.fabs(math.sin(math.pi*freq*dec)/(math.sin(math.pi*freq)*dec)),order)

		return correction

	def _calculate_scales(self):
		"""
			Returns per-channel correction and scaling parameters required for interpretation of incoming bit frames
			Parameters are based on current instrument state
		"""
		# Returns the bits-to-volts numbers for each channel in the current state

		# TODO: Centralise the calibration parsing, shared with Oscilloscope

		sect1 = "calibration.AG-%s-%s-%s-1" % ( "50" if self.relays_ch1 & RELAY_LOWZ else "1M",
								  "L" if self.relays_ch1 & RELAY_LOWG else "H",
								  "D" if self.relays_ch1 & RELAY_DC else "A")

		sect2 = "calibration.AG-%s-%s-%s-1" % ( "50" if self.relays_ch2 & RELAY_LOWZ else "1M",
								  "L" if self.relays_ch2 & RELAY_LOWG else "H",
								  "D" if self.relays_ch2 & RELAY_DC else "A")

		# Compute per-channel constant scaling factors
		try:
			g1 = 1 / float(self.calibration[sect1])
			g2 = 1 / float(self.calibration[sect2])
		except KeyError:
			log.warning("Moku appears uncalibrated")
			g1 = g2 = 1

		filt_gain2 = 2.0 ** (self.bs_cic2 - 2.0 * math.log(self.dec_cic2, 2))
		filt_gain3 = 2.0 ** (self.bs_cic3 - 3.0 * math.log(self.dec_cic3, 2))
		filt_gain4 = pow(2.0,-8.0) if (self.dec_iir-1) else 1.0

		filt_gain = filt_gain2 * filt_gain3 * filt_gain4
		window_gain = 1.0 / _SA_WINDOW_POWER[self.window]

		g1 *= _SA_INT_VOLTS_SCALE * filt_gain * window_gain * self.rbw_ratio * (2**10)
		g2 *= _SA_INT_VOLTS_SCALE * filt_gain * window_gain * self.rbw_ratio * (2**10)

		# Find approximate frequency bin values
		dev_start_freq = self._calculate_startFreq(self._total_decimation,self.demod,self.render_dds,self.offset)
		dev_freq_step = self._calculate_freqStep(self._total_decimation, self.render_dds)
		freqs = [ (dev_start_freq + dev_freq_step*i) for i in range(_SA_SCREEN_WIDTH)]

		# Compute the frequency dependent correction arrays
		# The CIC correction is only for CIC1 which is decimation=4 only, and 10th order
		fcorrs = [ (1/self._calculate_adc_freq_resp(f, True)/self._calculate_cic_freq_resp(f, 4, 10)) for f in freqs]

		return {'g1': g1, 'g2': g2, 'fs': freqs, 'fcorrs': fcorrs, 'fspan': [self._f1_full, self._f2_full], 'dbmscale': self.dbmscale}


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
											lambda rval: (rval & 0x780) >> 7),
	('dec_cic3',		REG_SA_DECCTL,		lambda r, old: (old & ~0x7800) | _usgn(r - 1, 4) << 11,
											lambda rval: ((rval & 0x7800) >> 11) + 1),
	('bs_cic3',			REG_SA_DECCTL,		lambda r, old: (old & ~0x78000) | _usgn(r, 4) << 15,
											lambda rval: (rval & 0x78000) >> 15),
	('dec_iir',			REG_SA_DECCTL,		lambda r, old: (old & ~0x780000) | _usgn(r - 1, 4) << 19,
											lambda rval: ((rval & 0x780000) >> 19) + 1),
	('rbw_ratio',		REG_SA_RBW,			lambda r, old: (old & ~0xFFFFFF) | _usgn(r * 2.0**10.0, 24),
											lambda rval: (rval & 0xFFFFFF)/2.0**10.0 ),
	('window',			REG_SA_RBW,			lambda r, old: (old & ~0x3000000) | r << 24 if r in [SA_WIN_NONE, SA_WIN_BH, SA_WIN_HANNING, SA_WIN_FLATTOP] else SA_WIN_NONE,
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

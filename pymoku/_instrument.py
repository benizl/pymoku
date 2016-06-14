
import threading, collections, time, struct, socket, logging

from functools import partial
from types import MethodType

from pymoku import NotDeployedException, ValueOutOfRangeException

REG_CTL 	= 0
REG_STAT	= 1
REG_ID1		= 2
REG_ID2		= 3
REG_PAUSE	= 4
REG_OUTLEN	= 5
REG_FILT	= 6
REG_FRATE	= 7
REG_SCALE	= 8
REG_OFFSET	= 9
REG_OFFSETA	= 10
REG_STRCTL0	= 11
REG_STRCTL1	= 12
REG_AINCTL	= 13
# 14 was Decimation before that moved in to instrument space
REG_PRETRIG	= 15
REG_CAL1, REG_CAL2, REG_CAL3, REG_CAL4, REG_CAL5, REG_CAL6, REG_CAL7, REG_CAL8 = range(16, 24)
REG_CAL9, REG_CAL10 = range(24, 26)
REG_STATE	= 63

# Common instrument parameters
ADC_SMP_RATE = 500e6
DAC_SMP_RATE = 1e9
CHN_BUFLEN = 2**14

### None of these constants will be exported to pymoku.instruments. If an instrument wants to
### give users access to these (e.g. relay settings) then the Instrument should define their
### own symbols equal to these guys

# REG_CTL Constants
COMMIT		= 0x80000000
INSTR_RST	= 0x00000001

# REG_OUTLEN Constants
ROLL		= 1
SWEEP		= 2
FULL_FRAME	= 0

# REG_FILT Constants
RDR_CUBIC	= 0
RDR_MINMAX	= 1
RDR_DECI	= 2
RDR_DDS		= 3

# REG_AINCTL Constants
RELAY_DC	= 1
RELAY_LOWZ	= 2
RELAY_LOWG	= 4

log = logging.getLogger(__name__)


def _usgn(i, width):
	""" Return i as an unsigned of given width, raising exceptions for out of bounds """
	if 0 <= i < 2**width:
		return int(i)

	raise ValueOutOfRangeException("%d doesn't fit in %d unsigned bits" % (i, width))

def _sgn(i, width):
	""" Return the unsigned that, when interpretted with given width, represents
	    the signed value i """
	if i < -2**(width - 1) or 2**(width - 1) - 1 < i:
		raise ValueOutOfRangeException("%d doesn't fit in %d signed bits" % (i, width))

	if i >= 0:
		return int(i)
		
	return int(2**width + i)

def _upsgn(i, width):
	""" Return the signed integer that comes about by interpretting *i* as a signed
	field of *width* bytes"""

	if i < 0 or i > 2**width:
		raise ValueOutOfRangeException()

	if i < 2**(width - 1):
		return i

	return i - 2**width


def to_reg_signed(_offset, _len, allow_set=None, allow_range=None, xform=lambda x: x):
	""" Returns a callable that will pack a new signed data value in to a register.
	Designed as shorthand for common use in instrument register accessor lists. Supports
	single and compound registers (i.e. data values that span more than one register).

	:param _offset: Offset of data field in the register (set)
	:param _len: Length of data field in the register (set)
	:param allow_set: Set containing all valid values of the data field.
	:param allow_range: a two-tuple specifying the bounds of the data value.
	:param xform: a callable that translates the user value written to the attribute to the register value"""
	# TODO: This signed and the below unsigned share all but one line of code, should consolidate
	def __ss(val, old):
		val = xform(val)
		mask = ((1 << _len) - 1) << _offset

		if allow_set and allow_range:
			raise MokuException("Can't check against both ranges and sets")

		if allow_set and val not in allow_set:
			return None
		elif allow_range and (val < allow_range[0] or val > allow_range[1]):
			return None

		v = _sgn(val, _len) << _offset

		try:
			return (old & ~mask) | v
		except TypeError:
			r = []
			for o in reversed(old):
				r.insert(0, (o & ~mask) | v & 0xFFFFFFFF)

				v = v >> 32
				mask = mask >> 32

			return tuple(r)


	return __ss


def to_reg_unsigned(_offset, _len, allow_set=None, allow_range=None, xform=lambda x: x):
	""" Returns a callable that will pack a new unsigned data value or bitfield in to a register.
	Designed as shorthand for common use in instrument register accessor lists. Supports
	single and compound registers (i.e. data values that span more than one register).

	:param _offset: Offset of data field in the register (set)
	:param _len: Length of data field in the register (set)
	:param allow_set: Set containing all valid values of the data field.
	:param allow_range: a two-tuple specifying the bounds of the data value.
	:param xform: a callable that translates the user value written to the attribute to the register value"""

	def __us(val, old):
		val = xform(val)
		mask = ((1 << _len) - 1) << _offset

		if allow_set and allow_range:
			raise MokuException("Can't check against both ranges and sets")

		if allow_set and val not in allow_set:
			return None
		elif allow_range and (val < allow_range[0] or val > allow_range[1]):
			return None

		v = _usgn(val, _len) << _offset

		try:
			return (old & ~mask) | v
		except TypeError:
			r = []
			for o in reversed(old):
				r.insert(0, (o & ~mask) | v & 0xFFFFFFFF)

				v = v >> 32
				mask = mask >> 32

			return tuple(r)

	return __us


def to_reg_bool(_offset):
	""" Returns a callable that will pack a new boolean data value in to a single bit of a register.
	Designed as shorthand for common use in instrument register accessor lists. Equivalent to
	:any:`to_reg_unsigned(_offset, 1, allow_set=[0, 1], xform=int)`

	:param _offset: Offset of bit in the register (set)"""
	return to_reg_unsigned(_offset, 1, allow_set=[0,1], xform=int)


def from_reg_signed(_offset, _len, xform=lambda x: x):
	""" Returns a callable that will unpack a signed data value from a register bitfield.
	Designed as shorthand for common use in instrument register accessor lists. Supports
	single and compound registers (i.e. data values that span more than one register).

	:param _offset: Offset of data field in the register (set)
	:param _len: Length of data field in the register (set)
	:param xform: a callable that translates the register value to the user attribute's natural units"""
	# TODO: As above, this and the unsigned version share all but one line of code, should consolidate.
	mask = ((1 << _len) - 1) << _offset

	def __sg(reg):
		try:
			return xform(_upsgn((reg & mask) >> _offset, _len))
		except TypeError:
			v = 0
			for r in reg:
				v |= r
				v <<= 32

			return xform(_upsgn((v & mask) >> _offset, _len))

	return __sg


def from_reg_unsigned(_offset, _len, xform=lambda x: x):
	""" Returns a callable that will unpack an unsigned data value from a register bitfield.
	Designed as shorthand for common use in instrument register accessor lists. Supports
	single and compound registers (i.e. data values that span more than one register).

	:param _offset: Offset of data field in the register (set)
	:param _len: Length of data field in the register (set)
	:param xform: a callable that translates the register value to the user attribute's natural units"""
	mask = ((1 << _len) - 1) << _offset

	def __ug(reg):
		try:
			return xform((reg & mask) >> _offset)
		except TypeError:
			v = 0
			for r in reg:
				v <<= 32
				v |= r

			return xform((v & mask) >> _offset)

	return __ug


def from_reg_bool(_offset):
	""" Returns a callable that will unpack a boolean value from a register bit.
	Designed as shorthand for common use in instrument register accessor lists.
	Equivalent to :any:`from_reg_unsigned(_offset, 1, xform=bool)`.

	:param _offset: Offset of data field in the register (set)"""
	return from_reg_unsigned(_offset, 1, xform=bool)



class MokuInstrument(object):
	"""Superclass for all Instruments that may be attached to a :any:`Moku` object.

	Should never be instantiated directly; instead, instantiate the subclass of the instrument
	you wish to run (e.g. :any:`Oscilloscope`, :any:`SignalGenerator`)"""

	def __init__(self):
		""" Must be called as the first line from any child implementations. """
		self._accessor_dict = {}
		self._moku = None
		self._remoteregs = [None]*128
		self._localregs = [None]*128
		self._running = False
		self._stateid = 0

		self.id = 0
		self.type = "Dummy Instrument"

		self._register_accessors(_instr_reg_handlers)

	def _register_accessors(self, accessor_dict):
		self._accessor_dict.update(accessor_dict)

	def _accessor_get(self, reg, get_xform):
		# Return local if present. Support a single register or a tuple of registers
		try:
			c = [ self._localregs[r] if self._localregs[r] is not None else self._remoteregs[r] or 0 for r in reg ]
			if all(i is not None for i in c): return get_xform(c)
		except TypeError:
			c = self._localregs[reg] if self._localregs[reg] is not None else self._remoteregs[reg] or 0
			if c is not None: return get_xform(c)

	def _accessor_set(self, reg, set_xform, data):
		# Support a single register or a tuple of registers
		try:
			old = [ self._localregs[r] if self._localregs[r] is not None else self._remoteregs[r] or 0 for r in reg ]
		except TypeError:
			old = self._localregs[reg] if self._localregs[reg] is not None else self._remoteregs[reg] or 0

		new = set_xform(data, old)
		if new is None:
			raise ValueOutOfRangeException("Reg %d Data %d" % (reg, data))

		try:
			for r, n in zip(reg, new):
				self._localregs[r] = n
		except TypeError:
			self._localregs[reg] = new

	def __getattr__(self, name):
		if name != '_accessor_dict' and name in self._accessor_dict:
			reg, set_xform, get_xform = self._accessor_dict[name]
			return self._accessor_get(reg, get_xform)
		else:
			raise AttributeError("No Attribute %s" % name)

	def __setattr__(self, name, value):
		if name != '_accessor_dict' and name in self._accessor_dict:
			reg, set_xform, get_xform = self._accessor_dict[name]
			return self._accessor_set(reg, set_xform, value)
		else:
			return super(MokuInstrument, self).__setattr__(name, value)

	def set_defaults(self):
		""" Can be extended in implementations to set initial state """

	def attach_moku(self, moku):
		self._moku = moku

	def commit(self):
		"""
		Apply all modified settings.

		.. note::

		    This **must** be called after any *set_* or *synth_* function has been called, or control
		    attributes have been directly set. This allows you to, for example, set multiple attributes
		    controlling rendering or signal generation in separate calls but have them all take effect at once.
		"""
		if self._moku is None: raise NotDeployedException()
		self._stateid = (self._stateid + 1) % 256 # Some statid docco says 8-bits, some 16.
		self.state_id = self._stateid
		self.state_id_alt = self._stateid

		regs = [ (i, d) for i, d in enumerate(self._localregs) if d is not None ]
		# TODO: Save this register set against stateid to be retrieved later
		log.debug("Committing reg set %s", str(regs))
		self._moku._write_regs(regs)
		self._remoteregs = [ l if l is not None else r for l, r in zip(self._localregs, self._remoteregs)]
		self._localregs = [None] * 128

	def sync_registers(self):
		"""
		Reload state from the Moku.

		This should never have to be called explicitly, however in advanced operation where the
		Moku state is being updated outside of pymoku, this will give the user access to those
		modified states through their attributes or accessors
		"""
		if self._moku is None: raise NotDeployedException()
		self._remoteregs = zip(*self._moku._read_regs(range(128)))[1]

	def dump_remote_regs(self):
		"""
		Return the current register state of the Moku.

		This should never have to be called explictly, however in advanced operation where the
		Moku state is being updated outside of pymoku, this gives the user access to the register
		values directly.

		Unlike :any:`sync_registers`, no local state is updated to reflect these register values
		and they are not made available through attributes or accessors.
		"""
		return self._moku._read_regs(range(128))

	def set_running(self, state):
		"""
		Assert or release the intrument reset line.

		This should never have to be called explicitly, as the instrument is correctly reset when
		it is attached and detached. In advanced operation, this can be used to force the instrument
		in to its initial state without a redeploy.
		"""
		self._running = state
		reg = (INSTR_RST if not state else 0)
		self._localregs[REG_CTL] = reg
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

	def get_frontend(self, channel):
		"""
		:type channel: int
		:param channel: Channel for which the relay settings are being retrieved

		Return array of bool with the front end configuration of channels
		[0] 50 Ohm
		[1] 10xAttenuation
		[2] AC Coupling
		"""
		if channel == 1:
			r = self.relays_ch1
		elif channel == 2:
			r = self.relays_ch2

		return [bool(r & RELAY_LOWZ), bool(r & RELAY_LOWG), not bool(r & RELAY_DC)]

_instr_reg_handlers = {
	# Name : Register, set-transform (user to register), get-transform (register to user); either None is W/R-only
	'instr_id':			(REG_ID1, 		None, 						from_reg_unsigned(0, 8)),
	'instr_buildno':	(REG_ID1, 		None,						from_reg_unsigned(8, 8)),
	'hwver':			(REG_ID2, 		None,						from_reg_unsigned(24, 0)),
	'hwserial':			(REG_ID2, 		None,						from_reg_unsigned(0, 24)),
	'pause':			(REG_PAUSE,		to_reg_bool(0),				from_reg_bool(0)),
	'frame_length':		(REG_OUTLEN,	to_reg_unsigned(0, 12),		from_reg_unsigned(0, 12)),
	'keep_last':		(REG_OUTLEN,	to_reg_bool(28),			from_reg_bool(28)),

	'x_mode':			(REG_OUTLEN,	to_reg_unsigned(29, 2, allow_set=[ROLL, SWEEP, FULL_FRAME]),
										from_reg_unsigned(29, 2)),

	'render_mode':		(REG_FILT,		to_reg_unsigned(0, 2, allow_set=[RDR_CUBIC, RDR_MINMAX, RDR_DECI, RDR_DDS]),
										from_reg_unsigned(0, 2)),

	'waveform_avg':		(REG_FILT,		to_reg_unsigned(2, 7),		from_reg_unsigned(2, 7)),

	'framerate':		(REG_FRATE,		to_reg_unsigned(0, 8, xform=lambda f: f * 256.0 / 477.0),
										from_reg_unsigned(0, 8, xform=lambda f: f / 256.0 * 477.0)),

	# Cubic Downsampling accessors
	'render_deci':		(REG_SCALE,		to_reg_unsigned(0, 16, xform=lambda x: 128 * (x - 1)),
										from_reg_unsigned(0, 16, xform=lambda x: (x / 128.0) + 1)),

	'render_deci_alt':	(REG_SCALE,		to_reg_unsigned(16, 16, xform=lambda x: 128 * (x - 1)),
										from_reg_unsigned(16, 16, xform=lambda x: (x / 128.0) + 1)),

	# Direct Downsampling accessors
	'render_dds':		(REG_SCALE,		to_reg_unsigned(0, 16, xform=lambda x: x - 1),
										from_reg_unsigned(0, 16, xform=lambda x: x + 1)),

	'render_dds_alt':	(REG_SCALE,		to_reg_unsigned(16, 16, xform=lambda x: x - 1),
										from_reg_unsigned(16, 16, xform=lambda x: x + 1)),

	'offset':			(REG_OFFSET, 	to_reg_signed(0, 32),		from_reg_signed(0, 32)),

	'offset_alt':		(REG_OFFSETA,	to_reg_signed(0, 32),		from_reg_signed(0, 32)),

	'relays_ch1':		(REG_AINCTL, 	to_reg_unsigned(0, 3),		from_reg_unsigned(0, 3)),
	'relays_ch2':		(REG_AINCTL, 	to_reg_unsigned(3, 3),		from_reg_unsigned(3, 3)),
	'en_in_ch1':		(REG_AINCTL,	to_reg_bool(6),				from_reg_bool(6)),
	'en_in_ch2':		(REG_AINCTL,	to_reg_bool(7),				from_reg_bool(7)),
	'pretrigger':		(REG_PRETRIG,	to_reg_signed(0, 32),		from_reg_signed(0, 32)),

	'state_id':			(REG_STATE,	 	to_reg_unsigned(0, 8),		from_reg_unsigned(0, 8)),
	'state_id_alt':		(REG_STATE,	 	to_reg_unsigned(16, 8),		from_reg_unsigned(16, 8)),
}

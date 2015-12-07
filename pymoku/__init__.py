

import socket, select, struct, logging
import zmq

log = logging.getLogger(__name__)

try:
	from finders import BonjourFinder
except (ImportError, OSError):
	log.warning("Can't import the Bonjour libraries, I won't be able to automatically detect Mokus")

class MokuException(Exception):	"""Base class for other Exceptions""";	pass
class MokuNotFound(MokuException): """Can't find Moku. Raised from discovery factory functions."""; pass
class NetworkError(MokuException): """Network connection to Moku failed"""; pass
class DeployException(MokuException): """Couldn't start instrument. Moku may not be licenced to use that instrument"""; pass
class StreamException(MokuException): """Data logging was interrupted or failed"""; pass
class InvalidOperationException(MokuException): """Can't perform that operation at this time"""; pass
class ValueOutOfRangeException(MokuException): """Invalid value for this operation"""; pass
class NotDeployedException(MokuException): """Tried to perform an action on an Instrument before it was deployed to a Moku"""; pass
class FrameTimeout(MokuException): """No new :any:`DataFrame` arrived within the given timeout"""; pass

class Moku(object):
	"""
	Core class representing a connection to a physical Moku:Lab unit.

	This must always be created first. Once a :any:`Moku` object exists, it can be queried for running instruments
	or new instruments deployed to the device.
	"""
	PORT = 27184

	def __init__(self, ip_addr):
		"""Create a connection to the Moku:Lab unit at the given IP address

		:type ip_addr: string
		:param ip_addr: The address to connect to. This should be in IPv4 dotted notation."""
		self._ip = ip_addr
		self._seq = 0
		self._instrument = None
		self._known_mokus = []

		self._ctx = zmq.Context()
		self._conn = self._ctx.socket(zmq.REQ)
		self._conn.connect("tcp://%s:%d" % (self._ip, Moku.PORT))

		self.name = None
		self.led = None
		self.led_colours = None

	@staticmethod
	def list_mokus():
		""" Discovers all compatible Moku instances on the network.
		This list can be interrogated to find the IP address of the target Moku:Lab hardware, suitable
		to be passed to the :any:`Moku` constructor.

		:rtype: [(ip, serial, name),...]
		:return: List of tuples, one per Moku
		"""
		known_mokus = []
		ips = BonjourFinder().find_all(timeout=0.5)

		for ip in ips:
			try:
				m = Moku(ip)
				name = m.get_name()
				ser = m.get_serial()
				known_mokus.append((ip, ser, name))
			except:
				continue

		return known_mokus

	@staticmethod
	def get_by_ip(ip_addr):
		"""
		Factory function, returns a :any:`Moku` instance with the given IP address.

		This works in a similar way to instantiating the instance manually but will perform
		version and compatibility checks first.

		If none is found, raises :any:`MokuNotFound`"""
		for ip, ser, name in Moku.list_mokus():
			if ip == ip_addr:
				return Moku(ip)

		raise MokuNotFound("Couldn't find Moku:%s" % ip_addr)

	@staticmethod
	def get_by_serial(serial):
		"""
		Factory function, returns a :any:`Moku` instance with the given Serial number.

		If none is found, raises :any:`MokuNotFound`"""
		for ip, ser, name in Moku.list_mokus():
			if ser.lower() == serial.lower():
				return Moku(ip)

		raise MokuNotFound("Couldn't find Moku:%s" % serial)

	@staticmethod
	def get_by_name(name):
		"""
		Factory function, returns a :any:`Moku` instance with the given name.

		If none is found, raises :any:`MokuNotFound`"""
		for ip, ser, nm in Moku.list_mokus():
			if name.lower() == nm.lower():
				return Moku(ip)

		raise MokuNotFound("Couldn't find Moku:%s" % name)


	def _read_regs(self, commands):
		command_data = ''.join([struct.pack('<B', x) for x in commands])
		packet_data = chr(0x47) + chr(0x00) + chr(len(commands)) + command_data

		self._conn.send(packet_data)
		ack = self._conn.recv()

		if ord(ack[0]) != 0x47 or ord(ack[1]) != 0x00 or ord(ack[2]) != len(commands):
			raise NetworkError()

		return [struct.unpack('<BI', ack[x:x + 5]) for x in range(3, len(commands) * 5, 5)]


	def _write_regs(self, commands):
		command_data = ''.join([struct.pack('<BI', x[0] + 0x80, x[1]) for x in commands])
		packet_data = chr(0x47) + chr(0x00) + chr(len(commands)) + command_data

		self._conn.send(packet_data)
		ack = self._conn.recv()

		if ord(ack[0]) != 0x47 or ord(ack[1]) != 0x00 or ord(ack[2]) != 0x00:
			raise NetworkError()


	def _deploy(self):
		if self._instrument is None:
			DeployException("No Instrument Selected")

		self._conn.send(chr(0x43) + chr(self._instrument.id) + chr(0x00))
		ack = self._conn.recv()

		if ord(ack[0]) != 0x43 or ord(ack[1]) != 0x00:
			raise DeployException("Deploy Error %d" % ord(ack[1]))

		self._set_property_single('ipad.name', socket.gethostname())

		# Return bitstream version
		return struct.unpack("<H", ack[3:5])[0]

	def _get_properties(self, properties):
		ret = []

		if len(properties) > 255:
			raise InvalidOperationException("Properties request too long (%d)" % len(properties))
		pkt = struct.pack("<BBB", 0x46, self._seq, len(properties))

		for p in properties:
			pkt += chr(1) # Read action
			pkt += chr(len(p))
			pkt += p
			pkt += chr(0) # No data for reads

		self._conn.send(pkt)
		reply = self._conn.recv()

		hdr, seq, stat, nr = struct.unpack("<BBBB", reply[:4])
		reply = reply[4:]

		if hdr != 0x46 or seq != self._seq:
			raise NetworkError("Bad header %d or sequence %d/%d" %(hdr, seq, self._seq))

		self._seq += 1

		p, d = '', ''
		for n in range(nr):
			print reply, [hex(ord(x)) for x in reply]
			plen = ord(reply[0]); reply = reply[1:]
			p = reply[:plen]; reply = reply[plen:]
			dlen = ord(reply[0]); reply = reply[1:]
			d = reply[:dlen]; reply = reply[dlen:]

			if stat == 0:
				ret.append((p, d))
			else:
				break

		# Reply should just contain the \r\n by this time.

		if stat:
			# An error will have exactly one property reply, the property that caused
			# the error with empty data
			raise InvalidOperationException("Property Read Error, status %d on property %s" % (stat, p))

		return ret

	def _get_property_section(self, section):
		ret = []

		pkt = struct.pack("<BBB", 0x46, self._seq, 1)

		pkt += chr(3) # Multi-read
		pkt += chr(len(section))
		pkt += section
		pkt += chr(0) # No data for reads

		self._conn.send(pkt)
		reply = self._conn.recv()
		hdr, seq, stat, nr = struct.unpack("<BBBB", reply[:4])
		reply = reply[4:]

		if hdr != 0x46 or seq != self._seq:
			raise NetworkError("Bad header %d or sequence %d/%d" %(hdr, seq, self._seq))

		self._seq += 1

		p, d = '',''
		for n in range(nr):
			plen = ord(reply[0]); reply = reply[1:]
			p = reply[:plen]; reply = reply[plen:]
			dlen = ord(reply[0]); reply = reply[1:]
			d = reply[:dlen]; reply = reply[dlen:]

			if stat == 0:
				ret.append((p, d))
			else:
				break

		if stat:
			# An error will have exactly one property reply, the property that caused
			# the error with empty data
			raise InvalidOperationException("Property Read Error, status %d on property %s" % (stat, p))

		return ret

	def _get_property_single(self, prop):
		r = self._get_properties([prop])
		return r[0][1]

	def _set_properties(self, properties):
		ret = []
		if len(properties) > 255:
			raise InvalidOperationException("Properties request too long (%d)" % len(properties))
		pkt = struct.pack("<BBB", 0x46, self._seq, len(properties))

		for p, d in properties:
			pkt += chr(2) # Write action
			pkt += chr(len(p))
			pkt += p
			pkt += chr(len(d))
			pkt += d

		self._conn.send(pkt)
		reply = self._conn.recv()
		hdr, seq, stat, nr = struct.unpack("<BBBB", reply[:4])
		reply = reply[4:]

		if hdr != 0x46 or seq != self._seq:
			raise NetworkError("Bad header %d or sequence %d/%d" %(hdr, seq, self._seq))

		self._seq += 1

		for n in range(nr):
			plen = ord(reply[0]); reply = reply[1:]
			p = reply[:plen]; reply = reply[plen:]
			dlen = ord(reply[0]); reply = reply[1:]
			d = reply[:dlen]; reply = reply[dlen:]

			if stat == 0:
				# Writes have the new value echoed back
				ret.append((p, d))
			else:
				break

		if stat:
			# An error will have exactly one property reply, the property that caused
			# the error with empty data
			raise InvalidOperationException("Property Read Error, status %d on property %s" % (stat, p))

		return ret

	def _set_property_single(self, prop, val):
		r = self._set_properties([(prop, val)])
		return r[0][1]


	def _stream_start(self, ch1=True, ch2=True, ftype='csv', use_sd=True, start=0, end=0, scale=1.0):
		tag = '0001' # TODO: Track and increment
		mp = 'e' if use_sd else 'i'

		ftype = { 'bin' : 0, 'csv' : 1, 'raw' : 2 }[ftype]

		flags = ftype << 2
		flags |= int(ch2) << 1
		flags |= int(ch1)

		pkt = struct.pack("<BBB", 0x53, 0, 1) #TODO: Proper sequence number
		pkt += tag + mp
		pkt += struct.pack("<iifB", start, end, scale, flags)

		self._conn.send(pkt)
		reply = self._conn.recv()

		hdr, seq, ae, stat = struct.unpack("<BBBB", reply[:4])

		if stat not in [ 1, 2 ]:
			raise StreamException("Stream start exception %d" % stat)


	def _stream_stop(self):
		pkt = struct.pack("<BBB", 0x53, 0, 2)
		self._conn.send(pkt)
		reply = self._conn.recv()

		hdr, seq, ae, stat, bt = struct.unpack("<BBBBi", reply[:8])

		if stat != 0:
			raise StreamException("Stream stop exception %d" % stat)

	def _stream_status(self):
		pkt = struct.pack("<BBB", 0x53, 0, 3)
		self._conn.send(pkt)
		reply = self._conn.recv()

		hdr, seq, ae, stat, bt = struct.unpack("<BBBBi", reply[:8])

		return stat, bt

	def get_serial(self):
		""" :return: Serial number of connected Moku:Lab """
		self.serial = self._get_property_single('device.serial')
		return self.serial

	def get_name(self):
		""" :return: Name of connected Moku:Lab """
		self.name = self._get_property_single('system.name')
		return self.name

	def set_name(self, name):
		""" :param name: Set new name for the Moku:Lab. This can make it easier to discover the device if multiple Moku:Labs are on a network"""
		self.name = self._set_property_single('system.name', name)

	def get_led_colour(self):
		""" :return: The colour of the under-Moku "UFO" ring lights"""
		self.led = self._get_property_single('leds.ufo1')
		return self.led

	def set_led_colour(self, colour):
		"""
		:type colour: string
		:param colour: New colour for the under-Moku "UFO" ring lights. Possible colours are listed by :any:`get_colour_list`"""
		if self.led_colours is None:
			self.get_colour_list()

		if not colour in self.led_colours:
			raise InvalidOperationException("Invalid LED colour %s" % colour)

		self.led = self._set_properties([('leds.ufo1', colour),
			('leds.ufo2', colour),
			('leds.ufo3', colour),
			('leds.ufo4', colour)])[0][1]

	def get_colour_list(self):
		"""
		:return: Available colours for the under-Moku "UFO" ring lights"""
		cols = self._get_property_section('colourtable')
		self.led_colours = [ x.split('.')[1] for x in zip(*cols)[0] ]
		return self.led_colours

	def is_active(self):
		""":return: True if the Moku currently is connected and has an instrument deployed and operating"""
		return self._instrument is not None and self._instrument.is_active()

	def attach_instrument(self, instrument):
		"""
		Attaches a :any:`MokuInstrument` subclass to the Moku, deploying and activating an instrument.

		Either this function or :any:`discover_instrument` must be called before an instrument can be manipulated"""
		self._instrument = instrument
		self._instrument.attach_moku(self)
		self._instrument.set_running(False)
		bsv = self._deploy()
		log.debug("Bitstream version %d", bsv)
		self._instrument.sync_registers()
		self._instrument.set_running(True)

	set_instrument = attach_instrument
	""" alias for :any:`attach_instrument`"""

	def get_instrument(self):
		"""
		:return:
			Currently running instrument object. If the user has not deployed the instrument themselves,
			then :any:`discover_instrument` must be called first."""
		return self._instrument

	def discover_instrument(self):
		"""Query a Moku:Lab device to see what instrument, if any, is currently running.

		If an instrument is found, return a new :any:`MokuInstrument` subclass representing that instrument, ready
		to be controlled."""
		import pymoku.instruments
		i = int(self._get_property_single('system.instrument'))
		instr = pymoku.instruments.id_table[i]

		if instr is None: return None

		running = instr()
		running.attach_moku(self)
		running.sync_registers()
		running.set_running(True)
		self._instrument = running
		return running

	def close(self):
		"""Close connection to the Moku:Lab.

		This should be called before any user script terminates."""
		if self._instrument is not None:
			self._instrument.set_running(False)

		self._conn.close()
		self._ctx.destroy()

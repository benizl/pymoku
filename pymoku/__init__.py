

import socket, select, struct, logging
import os.path
import zmq

log = logging.getLogger(__name__)

try:
	from .finders import BonjourFinder
except Exception as e:
	log.warning("Can't import the Bonjour libraries, I won't be able to automatically detect Mokus ({:s})".format(str(e)))

class MokuException(Exception):	"""Base class for other Exceptions""";	pass
class MokuNotFound(MokuException): """Can't find Moku. Raised from discovery factory functions."""; pass
class NetworkError(MokuException): """Network connection to Moku failed"""; pass
class DeployException(MokuException): """Couldn't start instrument. Moku may not be licenced to use that instrument"""; pass
class StreamException(MokuException): """Data logging was interrupted or failed"""; pass
class InvalidOperationException(MokuException): """Can't perform that operation at this time"""; pass
class ValueOutOfRangeException(MokuException): """Invalid value for this operation"""; pass
class NotDeployedException(MokuException): """Tried to perform an action on an Instrument before it was deployed to a Moku"""; pass
class FrameTimeout(MokuException): """No new :any:`DataFrame` arrived within the given timeout"""; pass
class NoDataException(MokuException): """A request has been made for data but none will be generated """; pass

# Chosen to trade off number of network transactions with memory usage.
# 4MB is a little larger than a bitstream so those uploads aren't chunked.
_FS_CHUNK_SIZE = 1024 * 1024 * 4

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
		self._conn.setsockopt(zmq.LINGER, 5000)
		self._conn.connect("tcp://%s:%d" % (self._ip, Moku.PORT))

		self._set_timeout()

		self.serial = self.get_serial()
		self.name = None
		self.led = None
		self.led_colours = None

	@staticmethod
	def list_mokus(timeout=5):
		""" Discovers all compatible Moku instances on the network.

		For most applications, the user should use the *get_by_* functions below. These
		functions are faster to return as they don't have to wait to find and validate
		all Moku devices on the network, they can look for a specific one.

		:type timeout: float
		:param timeout: time for which to search for Moku devices

		:rtype: [(ip, serial, name),...]
		:return: List of tuples, one per Moku
		"""
		known_mokus = []
		ips = BonjourFinder().find_all(timeout=timeout)

		for ip in ips:
			try:
				m = Moku(ip)
				name = m.get_name()
				ser = m.get_serial()
				known_mokus.append((ip, ser, name))
				m.close()
			except:
				continue

		return known_mokus

	@staticmethod
	def get_by_ip(ip_addr, timeout=10):
		"""
		Factory function, returns a :any:`Moku` instance with the given IP address.

		This works in a similar way to instantiating the instance manually but will perform
		version and compatibility checks first.

		:type ip_addr: str
		:param ip_addr: target IP address
		:type timeout: float
		:param timeout: operation timeout
		:raises :any:`MokuNotFound`: if no such Moku is found within the timeout"""
		def _filter(ip):
			return ip == ip_addr

		mokus = BonjourFinder().find_all(max_results=1, filter_callback=_filter, timeout=timeout)

		if len(mokus):
			return Moku(mokus[0])

		raise MokuNotFound("Couldn't find Moku: %s" % ip_addr)

	@staticmethod
	def get_by_serial(serial, timeout=10):
		"""
		Factory function, returns a :any:`Moku` instance with the given Serial number.

		:type ip_addr: str
		:param ip_addr: target serial
		:type timeout: float
		:param timeout: operation timeout
		:raises :any:`MokuNotFound`: if no such Moku is found within the timeout"""
		def _filter(ip):
			m = None
			try:
				m = Moku(ip)
				ser = m.get_serial()
			except zmq.error.Again:
				return False
			finally:
				if m is not None:
					m.close()

			return ser == serial

		mokus = BonjourFinder().find_all(max_results=1, filter_callback=_filter, timeout=timeout)

		if len(mokus):
			return Moku(mokus[0])

		raise MokuNotFound("Couldn't find Moku: %s" % serial)

	@staticmethod
	def get_by_name(name, timeout=10):
		"""
		Factory function, returns a :any:`Moku` instance with the given name.

		:type ip_addr: str
		:param ip_addr: target device name
		:type timeout: float
		:param timeout: operation timeout
		:raises :any:`MokuNotFound`: if no such Moku is found within the timeout"""
		def _filter(ip):
			m = None
			try:
				m = Moku(ip)
				n = m.get_name()
			except zmq.error.Again:
				return False
			finally:
				if m is not None:
					m.close()

			return n == name

		mokus = BonjourFinder().find_all(max_results=1, filter_callback=_filter, timeout=timeout)

		if len(mokus):
			return Moku(mokus[0])

		raise MokuNotFound("Couldn't find Moku: %s" % name)

	def _set_timeout(self, short=True):
		base = 5000

		if not short:
			base *= 2

		self._conn.setsockopt(zmq.SNDTIMEO, base) # A send should always be quick
		self._conn.setsockopt(zmq.RCVTIMEO, 2 * base) # A receive might need to wait on processing


	def _read_regs(self, commands):
		packet_data = bytearray([0x47, 0x00, len(commands)])
		packet_data += b''.join([struct.pack('<B', x) for x in commands])

		self._conn.send(packet_data)
		ack = self._conn.recv()

		t, err, l = struct.unpack('<BBB', ack[:3])

		if t != 0x47 or l != len(commands) or err:
			raise NetworkError()

		return [struct.unpack('<BI', ack[x:x + 5]) for x in range(3, len(commands) * 5, 5)]


	def _write_regs(self, commands):
		packet_data = bytearray([0x47, 0x00, len(commands)])
		packet_data += b''.join([struct.pack('<BI', x[0] + 0x80, x[1]) for x in commands])

		self._conn.send(packet_data)
		ack = self._conn.recv()

		t, err, l = struct.unpack('<BBB', ack[:3])

		if t != 0x47 or err or l:
			raise NetworkError()


	def _deploy(self):
		if self._instrument is None:
			DeployException("No Instrument Selected")

		# Deploy doesn't return until the deploy has completed which can take several
		# seconds on the device. Set an appropriately long timeout for this case.
		self._set_timeout(short=False)

		self._conn.send(bytearray([0x43, self._instrument.id, 0x00]))
		ack = self._conn.recv()

		self._set_timeout(short=True)

		t, err = struct.unpack('<BB', ack[:2])

		if t != 0x43 or err:
			raise DeployException("Deploy Error %d" % err)

		self._set_property_single('ipad.name', socket.gethostname())

		# Return bitstream version
		return struct.unpack("<H", ack[3:5])[0]

	def _get_properties(self, properties):
		ret = []

		if len(properties) > 255:
			raise InvalidOperationException("Properties request too long (%d)" % len(properties))
		pkt = bytearray([0x46, self._seq, len(properties)])

		for p in properties:
			pkt += bytearray([1, len(p)]) # Read action
			pkt += p.encode('ascii')
			pkt += bytearray([0]) # No data for reads

		self._conn.send(pkt)
		reply = self._conn.recv()

		hdr, seq, stat, nr = struct.unpack("<BBBB", reply[:4])
		reply = reply[4:]

		if hdr != 0x46 or seq != self._seq:
			raise NetworkError("Bad header %d or sequence %d/%d" %(hdr, seq, self._seq))

		self._seq += 1

		p, d = '', ''
		for n in range(nr):
			plen = ord(reply[:1]); reply = reply[1:]
			p = reply[:plen].decode('ascii'); reply = reply[plen:]
			dlen = ord(reply[:1]); reply = reply[1:]
			d = reply[:dlen].decode('ascii'); reply = reply[dlen:]

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

		pkt = struct.pack("<BBBBB", 0x46, self._seq, 1, 3, len(section))
		pkt += section.encode('ascii')
		pkt += bytearray([0]) # No data for reads

		self._conn.send(pkt)
		reply = self._conn.recv()
		hdr, seq, stat, nr = struct.unpack("<BBBB", reply[:4])
		reply = reply[4:]

		if hdr != 0x46 or seq != self._seq:
			raise NetworkError("Bad header %d or sequence %d/%d" %(hdr, seq, self._seq))

		self._seq += 1

		p, d = '',''
		for n in range(nr):
			plen = ord(reply[:1]); reply = reply[1:]
			p = reply[:plen].decode('ascii'); reply = reply[plen:]
			dlen = ord(reply[:1]); reply = reply[1:]
			d = reply[:dlen].decode('ascii'); reply = reply[dlen:]

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
			pkt += bytearray([2, len(p)])
			pkt += p.encode('ascii')
			pkt += bytearray([len(d)])
			pkt += d.encode('ascii')

		self._conn.send(pkt)
		reply = self._conn.recv()
		hdr, seq, stat, nr = struct.unpack("<BBBB", reply[:4])
		reply = reply[4:]

		if hdr != 0x46 or seq != self._seq:
			raise NetworkError("Bad header %d or sequence %d/%d" %(hdr, seq, self._seq))

		self._seq += 1

		for n in range(nr):
			plen = ord(reply[:1]); reply = reply[1:]
			p = reply[:plen].decode('ascii'); reply = reply[plen:]
			dlen = ord(reply[:1]); reply = reply[1:]
			d = reply[:dlen].decode('ascii'); reply = reply[dlen:]

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


	def _stream_prep(self, ch1, ch2, start, end, timestep, tag, binstr, procstr, fmtstr, hdrstr, fname, ftype='csv', use_sd=True):
		mp = 'e' if use_sd else 'i'

		if start < 0 or end < start:
			raise ValueOutOfRangeException("Invalid start/end times: %s/%s" %(str(start), str(end)))

		try:
			ftype = { 'bin' : 0, 'csv' : 1, 'net' : 3, 'plot' : 4 }[ftype]
		except KeyError:
			raise ValueOutOfRangeException("Invalid file type %s" % ftype)

		# TODO: Support multiple file types simultaneously
		flags = 1 << (2 + ftype)
		flags |= int(ch2) << 1
		flags |= int(ch1)

		pkt = struct.pack("<BBB", 0x53, 0, 1) #TODO: Proper sequence number
		pkt += tag.encode('ascii')
		pkt += mp.encode('ascii')
		pkt += struct.pack("<IIBd", start, end, flags, timestep)
		pkt += struct.pack("<H", len(fname))
		pkt += fname.encode('ascii')
		pkt += struct.pack("<H", len(binstr))
		pkt += binstr.encode('ascii')

		# Build up a single procstring with "|" as a delimiter
		# TODO: Allow empty procstrings
		procstr_pkt = ''
		for i,ch in enumerate([ch1,ch2]):
			if ch:
				if len(procstr_pkt):
					procstr_pkt += '|'
				procstr_pkt += procstr[i]

		pkt += struct.pack("<H", len(procstr_pkt))
		pkt += procstr_pkt.encode('ascii')

		pkt += struct.pack("<H", len(fmtstr))
		pkt += fmtstr.encode('ascii')
		pkt += struct.pack("<H", len(hdrstr))
		pkt += hdrstr.encode('ascii')

		self._conn.send(pkt)
		reply = self._conn.recv()

		hdr, seq, ae, stat = struct.unpack("<BBBB", reply[:4])

		if stat not in [ 1, 2 ]:
			raise StreamException("Stream start exception %d" % stat)

	def _stream_start(self):
		pkt = struct.pack("<BBB", 0x53, 0, 4)
		self._conn.send(pkt)
		reply = self._conn.recv()

		hdr, seq, ae, stat = struct.unpack("<BBBB", reply[:4])

		return stat		

	def _stream_stop(self):
		pkt = struct.pack("<BBB", 0x53, 0, 2)
		self._conn.send(pkt)
		reply = self._conn.recv()

		hdr, seq, ae, stat, bt = struct.unpack("<BBBBQ", reply[:12])

		return stat

	def _stream_status(self):
		pkt = struct.pack("<BBB", 0x53, 0, 3)
		self._conn.send(pkt)
		reply = self._conn.recv()

		hdr, seq, ae, stat, bt, trems, treme, flags, fname_len = struct.unpack("<BBBBQiiBH", reply[:23])
		fname = reply[23:23 + fname_len].decode('ascii')
		return stat, bt, trems, treme, fname

	def _fs_send_generic(self, action, data):
		pkt = struct.pack("<BQB", 0x49, len(data) + 1, action)
		pkt += data
		self._conn.send(pkt)

	def _fs_receive_generic(self, action):
		reply = self._conn.recv()
		hdr, l = struct.unpack("<BQ", reply[:9])
		pkt = reply[9:]

		if l != len(pkt):
			raise NetworkError("Unexpected file reply length %d/%d" % (l, len(pkt)))

		act, status = struct.unpack("BB", pkt[:2])

		if status:
			raise NetworkError("File receive error %d" % status)

		return pkt[2:]


	def _send_file(self, mp, localname):
		self._set_timeout(short=False)
		i = 0
		with open(localname, 'rb') as f:
			while True:
				data = f.read(_FS_CHUNK_SIZE)

				if not len(data):
					break

				remotename = os.path.basename(localname)

				fname = mp + ":" + remotename

				pkt = bytearray([len(fname)])
				pkt += fname.encode('ascii')
				pkt += struct.pack("<QQ", i, len(data))
				pkt += data

				self._fs_send_generic(2, pkt)
				self._fs_receive_generic(2)

				i += len(data)

		self._set_timeout(short=True)

		# Once all chunks have been uploaded, finalise the file on the
		# device making it available for use
		self._fs_finalise_fromlocal(mp, localname)

		return remotename

	def _receive_file(self, mp, fname, l):
		qfname = mp + ":" + fname
		self._set_timeout(short=False)
		print("Receiving file qfname %s" % qfname)
		i = 0
		with open(fname, "wb") as f:
			if l == 0:
				# A zero length file implies transfer the entire file
				# So we get the the file size
				l = self._fs_size(mp, fname)
			while i < l:
				to_transfer = min(l, _FS_CHUNK_SIZE)
				pkt = bytearray([len(qfname)])
				pkt += qfname.encode('ascii')
				pkt += struct.pack("<QQ", i, to_transfer)

				self._fs_send_generic(1, pkt)

				reply = self._fs_receive_generic(1)
				dl = struct.unpack("<Q", reply[:8])[0]

				f.write(reply[8:])

				i += to_transfer

		self._set_timeout(short=True)


	def _fs_chk(self, mp, fname):
		fname = mp + ":" + fname

		pkt = bytearray([len(fname)])
		pkt += fname.encode('ascii')
		self._fs_send_generic(3, pkt)

		return struct.unpack("<I", self._fs_receive_generic(3))[0]

	def _fs_size(self, mp, fname):
		fname = mp + ":" + fname

		pkt = bytearray([len(fname)])
		pkt += fname.encode('ascii')
		self._fs_send_generic(4, pkt)

		return struct.unpack("<Q", self._fs_receive_generic(4))[0]

	def _fs_list(self, mp, calculate_checksums=False):
		flags = 1 if calculate_checksums else 0

		data = mp.encode('ascii')
		data += bytearray([flags])
		self._fs_send_generic(5, data)

		reply = self._fs_receive_generic(5)

		n = struct.unpack("<H", reply[:2])[0]
		reply = reply[2:]

		names = []

		for i in range(n):
			chk, bl, fl = struct.unpack("<IQB", reply[:13])
			names.append((reply[13 : fl + 13].decode('ascii'), chk, bl))

			reply = reply[fl + 13 :]

		return names

	def _fs_free(self, mp):
		self._fs_send_generic(6, mp.encode('ascii'))

		t, f = struct.unpack("<QQ", self._fs_receive_generic(6))

		return t, f


	def _fs_finalise(self, mp, fname, fsize):
		fname = mp + ":" + fname
		pkt = bytearray([len(fname)])
		pkt += fname.encode('ascii')
		pkt += struct.pack('<Q', fsize)

		self._fs_send_generic(7, pkt)

		reply = self._fs_receive_generic(7)


	def _fs_finalise_fromlocal(self, mp, localname):
		fsize = os.path.getsize(localname)
		remotename = os.path.basename(localname)

		return self._fs_finalise(mp, remotename, fsize)


	def delete_bitstream(self, path):
		self._fs_finalise('b', path, 0)

	def delete_file(self, mp, path):
		self._fs_finalise(mp, path, 0)

	def load_bitstream(self, path):
		"""
		Load a bitstream file to the Moku, ready for deployment.

		:type path: String
		:param path: Local path to bitstream file.

		:raises NetworkError: if the upload fails verification.
		"""
		import zlib
		log.debug("Loading bitstream %s", path)
		rname = self._send_file('b', path)

		log.debug("Verifying upload")

		chk = self._fs_chk('b', rname)

		with open(path, 'rb') as fp:
			chk2 = zlib.crc32(fp.read()) & 0xffffffff

		if chk != chk2:
			raise NetworkError("Bitstream upload failed checksum verification.")

	def _trigger_fwload(self):
		self._conn.send(bytearray([0x52, 0x01]))
		hdr, reply = struct.unpack("<BB", self._conn.recv())

		if reply:
			raise InvalidOperationException("Firmware update failure %d", reply)

	def load_firmware(self, path):
		"""
		Updates the firmware on the Moku.

		The Moku will automatically power off when the update is complete.

		:type path: String
		:param path: Path to compatible *moku.fw*
		:raises InvalidOperationException: if the firmware is not compatible.
		"""
		log.debug("Sending firmware file")
		self._send_file('f', path)
		log.debug("Updating firmware")
		self._trigger_fwload()

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
		self.led_colours = [ x.split('.')[1] for x in list(zip(*cols))[0] ]
		return self.led_colours

	def is_active(self):
		""":return: True if the Moku currently is connected and has an instrument deployed and operating"""
		return self._instrument is not None and self._instrument.is_active()

	def attach_instrument(self, instrument, set_default=True):
		"""
		Attaches a :any:`MokuInstrument` subclass to the Moku, deploying and activating an instrument.

		Either this function or :any:`discover_instrument` must be called before an instrument can be manipulated.

		:type instrument: :any:`MokuInstrument` subclass
		:param instrument: The instrument instance to attach.
		:type set_default: bool
		:param set_default: Set the instrument to its default config upon connection, overwriting user changes before this point."""
		if self._instrument:
			self._instrument.set_running(False)

		self._instrument = instrument
		self._instrument.attach_moku(self)
		self._instrument.set_running(False)
		bsv = self._deploy()
		log.debug("Bitstream version %d", bsv)
		self._instrument.sync_registers()
		self._instrument.set_running(True)

		if set_default:
			self._instrument.set_defaults()
			self._instrument.commit()

	set_instrument = attach_instrument
	""" alias for :any:`attach_instrument`"""

	def detach_instrument(self):
		"""
		Detaches the :any:`MokuInstrument` from this Moku.

		This has little effect usually, as a new Instrument can be attached without detaching the old one. This is mostly
		useful when you want to save network bandwidth between measurements without closing the entire Moku device
		"""
		if self._instrument:
			self._instrument.set_running(False)
			self._instrument = None

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
		i = int(self._get_property_single('system.instrument').split(',')[0])
		try:
			instr = pymoku.instruments.id_table[i]
		except KeyError:
			instr = None

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

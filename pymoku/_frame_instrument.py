
import select, socket, struct, sys
import logging, time, threading
import zmq

from Queue import Queue, Empty
from pymoku import Moku, FrameTimeout, NotDeployedException, InvalidOperationException, NoDataException

import _instrument

log = logging.getLogger(__name__)

class FrameQueue(Queue):
	def put(self, item, block=True, timeout=None):
		""" Behaves the same way as default except that instead of raising Full, it
		    just pushes the item on to the deque anyway, throwing away old frames."""
		self.not_full.acquire()
		try:
			if self.maxsize > 0 and block:
				if timeout is None:
					while self._qsize() == self.maxsize:
						self.not_full.wait()
				elif timeout < 0:
					raise ValueError("'timeout' must be a non-negative number")
				else:
					endtime = _time() + timeout
					while self._qsize() == self.maxsize:
						remaining = endtime - _time()
						if remaining <= 0.0:
							break
						self.not_full.wait(remaining)
			self._put(item)
			self.unfinished_tasks += 1
			self.not_empty.notify()
		finally:
			self.not_full.release()

	def get(self, block=True, timeout=None):
		item = None
		while True:
			try:
				item = Queue.get(self, block=block, timeout=timeout or 1)
			except Empty:
				if timeout is None:
					continue
				else:
					raise
			else:
				return item

class DataFrame(object):
	"""
	Superclass representing a full frame of some kind of data. This class is never used directly,
	but rather it is subclassed depending on the type of data contained and the instrument from
	which it originated. For example, the :any:`Oscilloscope` instrument will generate :any:`VoltsFrame`
	objects, where :any:`VoltsFrame` is a subclass of :any:`DataFrame`.
	"""
	def __init__(self):
		self.complete = False
		self.chs_valid = [False, False]

		#: Channel 1 raw data array. Present whether or not the channel is enabled, but the contents
		#: are undefined in the latter case.
		self.raw1 = []

		#: Channel 2 raw data array.
		self.raw2 = []

		self.stateid = None
		self.trigstate = None

		#: Frame number. Increments monotonically but wraps at 16-bits.
		self.frameid = 0

		#: Incremented once per trigger event. Wraps at 32-bits.
		self.waveformid = 0

		self.flags = None

	def add_packet(self, packet):
		hdr_len = 13
		if len(packet) <= hdr_len:
			log.warning("Corrupt frame recevied")
			return

		data = struct.unpack('<BHBBBBBIB', packet[:hdr_len])
		frameid = data[1]
		instrid = data[2]
		chan = (data[3] >> 4) & 0x0F

		self.stateid = data[4]
		self.trigstate = data[5]
		self.flags = data[6]
		self.waveformid = data[7]

		if self.frameid != frameid:
			self.frameid = frameid
			self.chs_valid = [False, False]

		# For historical reasons the data length is 1026 while there are only 1024
		# valid samples. Trim the fat.
		if chan == 0:
			self.chs_valid[0] = True
			self.raw1 = packet[hdr_len:]
		else:
			self.chs_valid[1] = True
			self.raw2 = packet[hdr_len:]

		self.complete = all(self.chs_valid)

		if self.complete:
			self.process_complete()

	def process_complete(self):
		# Designed to be overridden by subclasses needing to transform the raw data in to Volts etc.
		pass

class VoltsFrame(DataFrame):
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

# Revisit: Should this be a Mixin? Are there more instrument classifications of this type, recording ability, for example?
class FrameBasedInstrument(_instrument.MokuInstrument):
	def __init__(self, frame_class, **frame_kwargs):
		super(FrameBasedInstrument, self).__init__()
		self._buflen = 1
		self._queue = FrameQueue(maxsize=self._buflen)
		self._hb_forced = False
		self._dlserial = 0
		self._dlskt = None

		self.frame_class = frame_class
		self.frame_kwargs = frame_kwargs

	def flush(self):
		""" Clear the Frame Buffer.
		This is normally not required as one can simply wait for the correctly-generated frames to propagate through
		using the appropriate arguments to :any:`get_frame`."""
		with self._queue.mutex:
			self._queue.queue.clear()

	def set_buffer_length(self, buflen):
		""" Set the internal frame buffer length."""
		self._buflen = buflen
		self._queue = FrameQueue(maxsize=buflen)

	def get_buffer_length(self):
		""" Return the current length of the internal frame buffer """
		return self._buflen

	def get_frame(self, timeout=None, wait=True):
		""" Get a :any:`DataFrame` from the internal frame buffer"""
		try:
			# Dodgy hack, infinite timeout gets translated in to just an exceedingly long one
			endtime = time.time() + (timeout or sys.maxint)
			while self._running:
				frame = self._queue.get(block=True, timeout=timeout)
				# Should really just wait for the new stateid to propagte through, but
				# at the moment we don't support stateid and stateid_alt being different;
				# i.e. we can't rerender already aquired data. Until we fix this, wait
				# for a trigger to propagate through so we don't at least render garbage
				if not wait or frame.trigstate == self._stateid:
					return frame
				elif time.time() > endtime:
					raise FrameTimeout()
		except Empty:
			raise FrameTimeout()

	def _dlsub_init(self, tag):
		ctx = zmq.Context.instance()
		self._dlskt = ctx.socket(zmq.SUB)
		self._dlskt.connect("tcp://%s:27186" % self._moku._ip)
		self._dlskt.setsockopt_string(zmq.SUBSCRIBE, unicode(tag))


	def _dlsub_destroy(self):
		if self._dlskt is not None:
			self._dlskt.close()
			self._dlskt = None


	def datalogger_start(self, start=0, duration=0, use_sd=True, filetype='csv'):
		""" Start recording data with the current settings.
		It is up to the user to ensure that the current aquisition rate is sufficiently slow to not loose samples"""
		if self._moku is None: raise NotDeployedException()
		# TODO: rest of the options, handle errors
		self._dlserial += 1

		tag = "%04d" % self._dlserial

		if filetype == 'net':
			self._dlsub_init(tag)

		self._moku._stream_start(start=start, end=start + duration, ftype=filetype, tag=tag, use_sd=use_sd)

	def datalogger_stop(self):
		""" Stop a recording session previously started with :py:func:`datalogger_start`"""
		if self._moku is None: raise NotDeployedException()
		# TODO: Handle errors
		self._moku._stream_stop()

		self._dlsub_destroy()

	def datalogger_status(self):
		""" Return the status of the most recent recording session to be started.
		This is still valid after the stream has stopped, in which case the status will reflect that it's safe
		to start a new session.

		Returns a tuple of state variables:

		- **status** -- Current datalogger state
		- **logged** -- Number of samples recorded so far. If more than one channel is active, this is the sum of all points across all channels.
		- **to start** -- Number of seconds until/since start. Time until start is positive, a negative number indicates that the record has started already.
		- **to end** -- Number of seconds until/since end.

		:rtype: int, int, int, int
		:return: status, logged, to start, to end."""
		if self._moku is None: raise NotDeployedException()
		return self._moku._stream_status()

	def datalogger_remaining(self):
		""" Returns number of seconds from session start and end.

		- **to start** -- Number of seconds until/since start. Time until start is positive, a negative number indicates that the record has started already.
		- **to end** -- Number of seconds until/since end.

		:rtype: int, int
		:return: to start, to end
		d1, d2, start, end = self.datalogger_status()"""
		return start, end

	def datalogger_samples(self):
		""" Returns number of samples captures in this datalogging session.

		:rtype: int
		:returns: sample count"""
		return self.datalogger_status()[1]

	def datalogger_busy(self):
		""" Returns the readiness of the datalogger to start a new session.

		The data logger must not be busy before issuing a :any:`datalogger_start`, otherwise
		an exception will be raised.

		If the datalogger is busy, the time remaining may be queried to see how long it might be
		until it has finished what it's doing, or it can be forcibly stopped with a call to
		:any:`datalogger_stop`."""
		return self.datalogger_status()[0] != 0

	def datalogger_completed(self):
		""" Returns whether or not the datalogger is expecting to log any more data.

		If the log is completed then the results files are ready to be uploaded or simply
		read off the SD card. At most one subsequent :any:`datalogger_get_samples` call
		will return without timeout."""
		return self.datalogger_status()[0] not in [1, 2]

	def datalogger_error(self):
		""" Returns a string representing the current error, or *None* if the session is not in error."""
		code = self.datalogger_status()[0]

		if code in [0, 1, 2, 7]:
			return None
		elif code == 3:
			return "Invalid Parameters for Datalogger Operation"
		elif code == 4:
			return "Target Filesystem Full"
		elif code == 5:
			return "Session overflowed, sample rate too fast."
		elif code == 6:
			return "Tried to start a logging session while one was already running."

	def datalogger_upload(self):
		""" Load most recently recorded data files from the Moku to the local PC.

		:raises NotDeployedException: if the instrument is not yet operational.
		:raises InvalidOperationException: if no files are present."""
		import re

		if self._moku is None: raise NotDeployedException()

		uploaded = 0

		# Check internal and external storage
		for mp in ['i', 'e']:
			for f in self._moku._fs_list(mp):
				if re.match("channel-.*-%04d\.[a-z]{3}" % self._dlserial, f[0]):
					# Data length of zero uploads the whole file
					self._moku._receive_file(mp, f[0], 0)
					uploaded += 1

		if not uploaded:
			raise InvalidOperationException("Log files not present")
		else:
			log.debug("Uploaded %d files", uploaded)

	def datalogger_upload_all(self):
		""" Load all recorded data files from the Moku to the local PC.

		:raises NotDeployedException: if the instrument is not yet operational.
		:raises InvalidOperationException: if no files are present."""
		import re

		if self._moku is None: raise NotDeployedException()

		uploaded = 0

		for mp in ['e', 'i']:
			files = self._moku._fs_list(mp)
			for f in files:
				if re.match("channel-.*-[a-zA-Z0-9]{4}\.[a-z]{3}", f[0]):
					# Data length of zero uploads the whole file
					self._moku._receive_file(mp, f, 0)
					uploaded += 1

		if not uploaded:
			raise InvalidOperationException("Log files not present")
		else:
			log.debug("Uploaded %d files", uploaded)

	def datalogger_get_samples(self, timeout=None):
		""" Returns samples currently being streamed to the network.

		Requires a currently-running data logging session that has been started with the "net"
		file type.

		This function may return any number of samples, or an empty array in the case of timeout.
		In the case of a two-channel datalogging session, the sample array returned from any one
		call will only relate to one channel or the other. The first element of the return tuple
		will identify the channel.

		The second element of the return tuple is the index of the first data point relative to
		the whole log. This can be used to identify missing data and/or fill it from on-disk
		copies if the log is simultaneously hitting the network and disk.

		:type timeout: float
		:param timeout: Timeout in seconds

		:rtype: int, int, [ float, ... ]
		:return: The channel number, starting sample index, sample data array

		:raises NoDataException: if the logging session has stopped
		:raises FrameTimeout: if the timeout expired """
		if self._dlskt in zmq.select([self._dlskt], [], [], timeout)[0]:
			tag, data = self._dlskt.recv_multipart()
			ch = int(tag.split(':')[1]) + 1
			start = int(tag.split(':')[2])

			smps = len(data) / 4
			data = struct.unpack("<" + "f" * smps, data)

			# Special value to indicate the stream has finished
			if ch == 0:
				raise NoDataException("Data log terminated")

			return ch, start, data
		else:
			raise FrameTimeout("Data log timed out")



	def set_running(self, state):
		prev_state = self._running
		super(FrameBasedInstrument, self).set_running(state)
		if state and not prev_state:
			self._fr_worker = threading.Thread(target=self._frame_worker)
			self._hb_worker = threading.Thread(target=self._heartbeat_worker)
			self._fr_worker.start()
			self._hb_worker.start()
		elif not state and prev_state:
			self._fr_worker.join()
			self._hb_worker.join()

	def _send_heartbeat(self, hbs, port):
		try:
			d, a = hbs.recvfrom(1024)
			if len(d) >= 3 and d[0] == '@':
				self._hb_forced = True
		except socket.timeout:
			pass

		try:
			hdr = 0x41 if self._hb_forced else 0x40
			ts = int(time.time() % 2**16)
			hbs.sendto(struct.pack('<BH', hdr, ts), (self._moku._ip, port))
		except:
			# TODO: Catch only what we expect, which is moku disappeared and whatever
			# the network layer can throw at us
			log.exception("HB")

	def _frame_worker(self):
		ctx = zmq.Context.instance()
		skt = ctx.socket(zmq.SUB)
		skt.connect("tcp://%s:27185" % self._moku._ip)
		skt.setsockopt_string(zmq.SUBSCRIBE, u'')
		skt.setsockopt(zmq.CONFLATE, 1)

		fr = self.frame_class(**self.frame_kwargs)

		try:
			while self._running:
				if skt in zmq.select([skt], [], [], 1.0)[0]:
					d = skt.recv()
					fr.add_packet(d)

					if fr.complete:
						self._queue.put_nowait(fr)
						fr = self.frame_class(**self.frame_kwargs)
		finally:
			skt.close()
			ctx.destroy()

	def _heartbeat_worker(self):
		hs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		hs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		hs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
		hs.settimeout(0.1)
		hs.bind(('0.0.0.0', 27183))

		try:
			while self._running:
				self._send_heartbeat(hs, 27183)
				time.sleep(1.0)
		finally:
			hs.close()


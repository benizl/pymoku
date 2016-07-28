
import select, socket, struct, sys
import os, os.path
import logging, time, threading
import zmq

from collections import deque
from Queue import Queue, Empty
from pymoku import Moku, FrameTimeout, NotDeployedException, InvalidOperationException, NoDataException, dataparser

import _instrument

log = logging.getLogger(__name__)

DL_STATE_NONE		= 0
DL_STATE_RUNNING 	= 1
DL_STATE_WAITING 	= 2
DL_STATE_INVAL		= 3
DL_STATE_FSFULL		= 4
DL_STATE_OVERFLOW	= 5
DL_STATE_BUSY		= 6
DL_STATE_STOPPED	= 7

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

	# The default _init for a Queue doesn't actually bound the deque, relying on the
	# put function to bound.
	def _init(self, maxsize):
		self.queue = deque(maxlen=maxsize)


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
		hdr_len = 15
		if len(packet) <= hdr_len:
			# Should be a higher priority but actually seems unexpectedly common. Revisit.
			log.debug("Corrupt frame recevied, len %d", len(packet))
			return

		data = struct.unpack('<BHBBBBBIBH', packet[:hdr_len])
		frameid = data[1]
		instrid = data[2]
		chan = (data[3] >> 4) & 0x0F

		self.stateid = data[4]
		self.trigstate = data[5]
		self.flags = data[6]
		self.waveformid = data[7]
		self.source_serial = data[8]

		if self.frameid != frameid:
			self.frameid = frameid
			self.chs_valid = [False, False]

		log.debug("AP ch %d, f %d, w %d", chan, frameid, self.waveformid)

		# For historical reasons the data length is 1026 while there are only 1024
		# valid samples. Trim the fat.
		if chan == 0:
			self.chs_valid[0] = True
			self.raw1 = packet[hdr_len:-8]
		else:
			self.chs_valid[1] = True
			self.raw2 = packet[hdr_len:-8]

		self.complete = all(self.chs_valid)

		if self.complete:
			if not self.process_complete():
				self.complete = False
				self.chs_valid = [False, False]

	def process_complete(self):
		# Designed to be overridden by subclasses needing to transform the raw data in to Volts etc.
		return True


# Revisit: Should this be a Mixin? Are there more instrument classifications of this type, recording ability, for example?
class FrameBasedInstrument(_instrument.MokuInstrument):
	def __init__(self):
		super(FrameBasedInstrument, self).__init__()
		self._buflen = 1
		self._queue = FrameQueue(maxsize=self._buflen)
		self._hb_forced = False
		self._dlserial = 0
		self._dlskt = None

		self.binstr = ''
		self.procstr = ''
		self.fmtstr = ''
		self.hdrstr = ''

		self.upload_index = {}

		self._strparser = None

	def set_frame_class(self, frame_class, **frame_kwargs):
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
				else:
					log.debug("Incorrect state received: %d/%d", frame.trigstate, self._stateid)
		except Empty:
			raise FrameTimeout()

	def _dlsub_init(self, tag):
		ctx = zmq.Context.instance()
		self._dlskt = ctx.socket(zmq.SUB)
		self._dlskt.connect("tcp://%s:27186" % self._moku._ip)
		self._dlskt.setsockopt_string(zmq.SUBSCRIBE, unicode(tag))

		self._strparser = dataparser.LIDataParser(self.ch1, self.ch2, self.binstr, self.procstr, self.fmtstr, self.hdrstr, self.timestep, time.time(), [0] * self.nch)


	def _dlsub_destroy(self):
		if self._dlskt is not None:
			self._dlskt.close()
			self._dlskt = None


	def datalogger_start(self, start=0, duration=0, use_sd=True, ch1=True, ch2=False, filetype='csv'):
		""" Start recording data with the current settings.

		Device must be in ROLL mode (via a call to :any:`set_xmode`) and the sample rate must be appropriate
		to the file type (see below).

		:raises InvalidOperationException: if the sample rate is too high for the selected filetype or if the
		device *x_mode* isn't set to *ROLL*.

		:note: Start parameter not currently implemented!

		:param start: Start time in seconds from the time of function call
		:param duration: Log duration in seconds
		:type use_sd: bool
		:param use_sd: Log to SD card (default is internal volatile storage)
		:type ch1: bool
		:param ch1: Log from Channel 1
		:type ch2: bool
		:param ch2: Log from Channel 2
		:param filetype: Type of log to start. One of:

		- **csv** -- CSV file, 1ksmps max rate
		- **bin** -- LI Binary file, 10ksmps max rate
		- **net** -- Log to network, retrieve data with :any:`datalogger_get_samples`. 100smps max rate
		- **plt** -- Log to Plot.ly. 10smps max rate

		"""
		from datetime import datetime
		if self._moku is None: raise NotDeployedException()
		# TODO: rest of the options, handle errors
		self._dlserial += 1

		self.tag = "%04d" % self._dlserial

		self.nch = 0
		self.ch1 = bool(ch1)
		self.ch2 = bool(ch2)
		if ch1:
			self.nch += 1
		if ch2:
			self.nch += 1

		fname = datetime.now().strftime(self.logname+"_%Y%m%d_%H%M")

		# Currently the data stream genesis is from the x_mode commit below, meaning that delayed start
		# doesn't work properly. Once this is fixed in the FPGA/daemon, remove this check and the note
		# in the documentation above.
		if start:
			raise InvalidOperationException("Logging start time parameter currently not supported")

		# Logging rates depend on which storage medium, and the filetype as well
		if(ch1 and ch2):
			if(use_sd):
				maxrates = { 'bin' : 150e3, 'csv' : 1e3, 'net' : 20e3, 'plot' : 10}
			else:
				maxrates = { 'bin' : 1e6, 'csv' : 1e3, 'net' : 20e3, 'plot' : 10}
		else:
			if(use_sd):
				maxrates = { 'bin' : 250e3, 'csv' : 3e3, 'net' : 40e3, 'plot' : 10}
			else:
				maxrates = { 'bin' : 1e6, 'csv' : 3e3, 'net' : 40e3, 'plot' : 10}

		if 1 / self.timestep > maxrates[filetype]:
			raise InvalidOperationException("Sample Rate %d too high for file type %s" % (1 / self.timestep, filetype))

		if self.x_mode != _instrument.ROLL:
			raise InvalidOperationException("Instrument must be in roll mode to perform data logging")

		if not all([ len(s) for s in [self.binstr, self.procstr, self.fmtstr, self.hdrstr]]):
			raise InvalidOperationException("Instrument currently doesn't support data logging")

		# We have to be in this mode anyway because of the above check, but rewriting this register and committing
		# is necessary in order to reset the channel buffers on the device and flush them of old data.
		self.x_mode = _instrument.ROLL
		self.commit()

		self._moku._stream_prep(ch1=ch1, ch2=ch2, start=start, end=start + duration, timestep=self.timestep,
			binstr=self.binstr, procstr=self.procstr, fmtstr=self.fmtstr, hdrstr=self.hdrstr,
			fname=fname, ftype=filetype, tag=self.tag, use_sd=use_sd)

		if filetype == 'net':
			self._dlsub_init(self.tag)

		self._moku._stream_start()

	def datalogger_start_single(self, use_sd=True, ch1=True, ch2=False, filetype='csv'):
		""" Grab all currently-recorded data at full rate.

		Unlike a normal datalogger session, this will log only the data that has *already* been aquired through
		normal activities. For example, if the Oscilloscope has aquired a frame and is paused, this function will
		retrieve the data in that frame at the full underlying sample rate.

		:type use_sd: bool
		:param use_sd: Log to SD card (default is internal volatile storage)
		:type ch1: bool
		:param ch1: Log from Channel 1
		:type ch2: bool
		:param ch2: Log from Channel 2
		:param filetype: Type of log to start. One of:

		- **csv** -- CSV file
		- **bin** -- LI Binary file
		- **net** -- Log to network, retrieve data with :any:`datalogger_get_samples`
		- **plt** -- Log to Plot.ly
		"""
		from datetime import datetime
		if self._moku is None: raise NotDeployedException()
		# TODO: rest of the options, handle errors
		self._dlserial += 1

		self.tag = "%04d" % self._dlserial

		self.nch = 0
		self.ch1 = bool(ch1)
		self.ch2 = bool(ch2)
		if ch1:
			self.nch += 1
		if ch2:
			self.nch += 1

		fname = datetime.now().strftime(self.logname+"_%Y%m%d_%H%M")

		if not all([ len(s) for s in [self.binstr, self.procstr, self.fmtstr, self.hdrstr]]):
			raise InvalidOperationException("Instrument currently doesn't support data logging")

		self._moku._stream_prep(ch1=ch1, ch2=ch2, start=0, end=0, timestep=self.timestep,
			binstr=self.binstr, procstr=self.procstr, fmtstr=self.fmtstr, hdrstr=self.hdrstr,
			fname=fname, ftype=filetype, tag=self.tag, use_sd=use_sd)

		if filetype == 'net':
			self._dlsub_init(self.tag)

		self._moku._stream_start()

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
		- **filename** -- Base filename of current log session (without filename)

		Status is one of:

		- **DL_STATE_NONE** -- No session
		- **DL_STATE_RUNNING** -- Session currently running
		- **DL_STATE_WAITING** -- Session waiting to run (delayed start)
		- **DL_STATE_INVAL** -- An attempt was made to start a session with invalid parameters
		- **DL_STATE_FSFULL** -- A session has terminated early due to the storage filling up
		- **DL_STATE_OVERFLOW** -- A session has terminated early due to the sample rate being too high for the storage speed
		- **DL_STATE_BUSY** -- An attempt was made to start a session when one was already running
		- **DL_STATE_STOPPED** -- A session has successfully completed.

		:rtype: int, int, int, int
		:return: status, logged, to start, to end."""
		if self._moku is None: raise NotDeployedException()
		return self._moku._stream_status()

	def datalogger_remaining(self):
		""" Returns number of seconds from session start and end.

		- **to start** -- Number of seconds until/since start. Time until start is positive, a negative number indicates that the record has started already.
		- **to end** -- Number of seconds until/since end.

		:rtype: int, int
		:return: to start, to end"""
		d1, d2, start, end, fname = self.datalogger_status()
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
		return self.datalogger_status()[0] != DL_STATE_NONE

	def datalogger_completed(self):
		""" Returns whether or not the datalogger is expecting to log any more data.

		If the log is completed then the results files are ready to be uploaded or simply
		read off the SD card. At most one subsequent :any:`datalogger_get_samples` call
		will return without timeout."""
		return self.datalogger_status()[0] not in [DL_STATE_RUNNING, DL_STATE_WAITING]

	def datalogger_filename(self):
		""" Returns the current base filename of the logging session.

		The base filename doesn't include the file extension as multiple files might be
		recorded simultaneously with different extensions."""
		return str(self.datalogger_status()[4]).strip()

	def datalogger_error(self):
		""" Returns a string representing the current error, or *None* if the session is not in error."""
		code = self.datalogger_status()[0]

		if code in [DL_STATE_NONE, DL_STATE_RUNNING, DL_STATE_WAITING, DL_STATE_STOPPED]:
			return None
		elif code == DL_STATE_INVAL:
			return "Invalid Parameters for Datalogger Operation"
		elif code == DL_STATE_FSFULL:
			return "Target Filesystem Full"
		elif code == DL_STATE_OVERFLOW:
			return "Session overflowed, sample rate too fast."
		elif code == DL_STATE_BUSY:
			return "Tried to start a logging session while one was already running."

	def datalogger_upload(self):
		""" Load most recently recorded data files from the Moku to the local PC.

		:raises NotDeployedException: if the instrument is not yet operational.
		:raises InvalidOperationException: if no files are present."""
		import re

		if self._moku is None: raise NotDeployedException()

		uploaded = 0
		target = self.datalogger_filename()
		# Check internal and external storage
		for mp in ['i', 'e']:
			for f in self._moku._fs_list(mp):
				if str(f[0]).startswith(target):
					# Don't overwrite existing files of the name name. This would be nicer
					# if we could pass receive_file a local filename to save to, but until
					# that change is made, just move the clashing file out of the way.
					if os.path.exists(f[0]):
						i = 1
						while os.path.exists(f[0] + ("-%d" % i)):
							i += 1

						os.rename(f[0], f[0] + ("-%d" % i))

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
				if re.match("datalog-.*\.[a-z]{2,3}", f[0]):
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

		ch, start, coeff, raw = self._dl_get_samples_raw(timeout)

		self._strparser.set_coeff(ch, coeff)

		self._strparser.parse(raw, ch)
		parsed = self._strparser.processed[ch]
		self._strparser.clear_processed()

		return ch + 1, start, parsed


	def _dl_get_samples_raw(self, timeout):
		if self._dlskt in zmq.select([self._dlskt], [], [], timeout)[0]:
			hdr, data = self._dlskt.recv_multipart()

			tag, ch, start, coeff = hdr.split('|')
			ch = int(ch)
			start = int(start)
			coeff = float(coeff)

			# Special value to indicate the stream has finished
			if ch == -1:
				raise NoDataException("Data log terminated")

			return ch, start, coeff, data
		else:
			raise FrameTimeout("Data log timed out after %d seconds", timeout)



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
		if(getattr(self, 'frame_class', None)):
			ctx = zmq.Context.instance()
			skt = ctx.socket(zmq.SUB)
			skt.connect("tcp://%s:27185" % self._moku._ip)
			skt.setsockopt_string(zmq.SUBSCRIBE, u'')
			skt.setsockopt(zmq.CONFLATE, 1)
			skt.setsockopt(zmq.LINGER, 5000)

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


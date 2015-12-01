
import select, socket, struct, sys
import logging, time, threading
from Queue import Queue, Empty
from pymoku import Moku, FrameTimeout

import _instrument

from pymoku import NotDeployedException

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

class DataFrame(object):
	"""
	.. mysterious undocumented magic.

	.. autoinstanceattribute:: pymoku._frame_instrument.DataFrame.ch1
		:annotation: = [CH1_DATA]

	.. autoinstanceattribute:: pymoku._frame_instrument.DataFrame.ch1
		:annotation: = [CH2_DATA]

	.. autoinstanceattribute:: pymoku._frame_instrument.DataFrame.frameid
		:annotation: = n

	.. autoinstanceattribute:: pymoku._frame_instrument.DataFrame.waveformid
		:annotation: = n
	"""
	def __init__(self):
		self.complete = False
		self.chs_valid = [False, False]

		#: Channel 1 data array. Present whether or not the channel is enabled, but the contents
		#: are undefined in the latter case.
		self.ch1 = []

		#: Channel 2 data array.
		self.ch2 = []

		self.stateid = None
		self.trigstate = None

		#: Frame number. Increments monotonically but wraps at 16-bits.
		self.frameid = 0

		#: Incremented once per trigger event. Wraps at 32-bits.
		self.waveformid = 0

		self.flags = None

	def add_packet(self, packet):
		hdr_len = 13
		smpls = 1026
		d_len = smpls * 4
		if len(packet) != hdr_len + d_len:
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

		dat = struct.unpack('<' + 'i' * smpls, packet[hdr_len:])
		dat = [ x if x != -0x80000000 else None for x in dat ]

		# For historical reasons the data length is 1026 while there are only 1024
		# valid samples. Trim the fat.
		if chan == 0:
			self.chs_valid[0] = True
			self.ch1 = dat[:1024]
		else:
			self.chs_valid[1] = True
			self.ch2 = dat[:1024]

		self.complete = all(self.chs_valid)

# Revisit: Should this be a Mixin? Are there more instrument classifications of this type, recording ability, for example?
class FrameBasedInstrument(_instrument.MokuInstrument):
	""" FrameWaffle """
	def __init__(self):
		super(FrameBasedInstrument, self).__init__()
		self._buflen = 1
		self._queue = FrameQueue(maxsize=self._buflen)
		self._hb_forced = False

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

	def datalogger_start(self, duration=0):
		""" Start recording data with the current settings.
		It is up to the user to ensure that the current aquisition rate is sufficiently slow to not loose samples"""
		if self._moku is None: raise NotDeployedException()
		# TODO: rest of the options, handle errors
		self._moku._stream_start(end=duration)

	def datalogger_stop(self):
		""" Stop a recording session previously started with :py:func:`datalogger_start`"""
		if self._moku is None: raise NotDeployedException()
		# TODO: Handle errors
		self._moku._stream_stop()

	def datalogger_status(self):
		""" Return the status of the most recent recording session to be started.
		This is still valid after the stream has stopped, in which case the status will reflect that it's safe
		to start a new session"""
		if self._moku is None: raise NotDeployedException()
		return self._moku._stream_status()[0]

	def datalogger_transferred(self):
		""" Return the number of samples recorded in the most recent session.
		This is valid both for running sessions and one that has been completed."""
		if self._moku is None: raise NotDeployedException()
		return self._moku._stream_status()[1]

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
		import zmq

		ctx = zmq.Context()
		skt = ctx.socket(zmq.SUB)
		skt.connect("tcp://%s:27185" % self._moku._ip)
		skt.setsockopt_string(zmq.SUBSCRIBE, u'')

		fr = DataFrame()

		try:
			while self._running:
				if skt in zmq.select([skt], [], [], 1.0)[0]:
					d = skt.recv()
					fr.add_packet(d)

					if fr.complete:
						self._queue.put_nowait(fr)
						fr = DataFrame()
		finally:
			skt.close()
			ctx.destroy()

	def _heartbeat_worker(self):
		hs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		hs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		hs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
		hs.settimeout(0.1)
		hs.bind(('0.0.0.0', Moku.PORT + 1))

		try:
			while self._running:
				self._send_heartbeat(hs, Moku.PORT + 1)
				time.sleep(1.0)
		finally:
			hs.close()


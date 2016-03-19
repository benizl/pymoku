#!/usr/bin/env python
import os, time, datetime, math
import logging
import re, struct

log = logging.getLogger(__name__)

class InvalidFormatException(Exception): pass
class InvalidFileException(Exception): pass

class LIDataFileReader(object):
	"""
	Reads LI format data files.

	Data is read from this object in the form of Records. The form of a record depends on the
	instrument with which the data was captured and is decribed by the :any:`headers` field.
	A record may be a scalar in the case of, say, a datalogger; or may be a tuple of elements.
	The Phasemeter for example has records defined as tuples of (frequency, phase, amplitude).

	If multiple channels of data have been recorded, all read methods return time-aligned
	samples from all channels at once. A single channel capture will return single-element
	lists of records.

	Presents the iterator interface and the context manager interface.  For example:

	with LIDataFileReader('input.li') as f:
		for record in f:
			do_something(record)

	:autoinstanceattribute:: pymoku.dataparser.LIDataFileReader.headers

	:autoinstanceattribute:: pymoku.dataparser.LIDataFileReader.nch

	:autoinstanceattribute:: pymoku.dataparser.LIDataFileReader.instr

	:autoinstanceattribute:: pymoku.dataparser.LIDataFileReader.instrv

	:autoinstanceattribute:: pymoku.dataparser.LIDataFileReader.deltat

	:autoinstanceattribute:: pymoku.dataparser.LIDataFileReader.starttime

	"""

	def __init__(self, filename):
		"""

		:raises :any:`InvalidFileException`: when file is corrupted or of the wrong version.
		:type filename: str
		:param filename: Input filename
		"""
		self.records = []
		self.cal = []
		self.proc = []
		self.file = open(filename, 'rb')
		f = self.file

		# Pre-define instance fields so we can attach docstrings.

		#: Column headers describing the contents of the datafile records
		self.headers = []

		#: Number of (valid) channels in input file
		self.nch = 0

		#: Numeric Instrument identifier
		self.instr = 0

		#: Instrument version
		self.instrv = 0

		#: Time step with which the data was captured
		self.deltat = 0

		#: Time at which the recording was started (seconds since Jan 1 1970)
		self.starttime = 0

		if f.read(2) != 'LI':
			raise InvalidFileException("Bad Magic")

		v = f.read(1)
		if v != '1':
			raise InvalidFileException("Unknown File Version %s" % v)

		pkthdr_len = struct.unpack("<H", f.read(2))[0]
		self.chs, self.instr, self.instrv, self.deltat, self.starttime = struct.unpack("<BBHdQ", f.read(20))

		# Extract the ON channels from the flagged bits
		self.nch = 0
		if (self.chs & 0x01):
			self.nch += 1
		if (self.chs & 0x02):
			self.nch += 1

		log.debug("NCH %d INST: %d INSTV: %d DT: %f ST: %f", self.nch, self.instr, self.instrv, self.deltat, self.starttime)

		# Do this nch times
		for i in range(self.nch):
			self.cal.append(struct.unpack("<d", f.read(8))[0])

		log.debug("CAL: %s", self.cal)

		reclen = struct.unpack("<H", f.read(2))[0]
		self.rec = f.read(reclen); log.debug("Rec %s (%d)", self.rec, reclen)

		# One procstring per channel ON
		for i in range(self.nch):
			proclen = struct.unpack("<H", f.read(2))[0]
			self.proc.append(f.read(proclen));

		fmtlen = struct.unpack("<H", f.read(2))[0]
		self.fmt = f.read(fmtlen); log.debug("Fmt %s (%d)", self.fmt, fmtlen)
		hdrlen = struct.unpack("<H", f.read(2))[0]
		self.hdr = f.read(hdrlen); log.debug("Hdr %s (%d)", self.hdr, hdrlen)

		# Assume the last line of the CSV header block is the column headers
		try:
			self.headers = [ s.strip() for s in self.hdr.split('\r\n') if len(s) ][-1].split(',')
		except IndexError:
			self.headers = []

		log.debug("NCH: %d INSTR: %d INSTRV: %d DT: %d", self.nch, self.instr, self.instrv, self.deltat)
		log.debug("B: %s P: %s F: %s H: %s", self.rec, self.proc, self.fmt, self.hdr)

		if f.tell() != pkthdr_len + 5:
			raise InvalidFileException("Incorrect File Header Length (expected %d got %d)" % (pkthdr_len + 5, f.tell()))

		self.parser = LIDataParser(self.ch1, self.ch2, self.rec, self.proc, self.fmt, self.hdr, self.deltat, self.starttime, self.cal)


	def _parse_chunk(self):

		dhdr = self.file.read(3)
		if len(dhdr) != 3:
			return None

		ch, _len = struct.unpack("<BH", dhdr)

		d = self.file.read(_len)

		if len(d) != _len:
			raise InvalidFileException("Unexpected EOF while reading data")

		self.parser.parse(d, ch)

		return ch

	def _process_chunk(self):
		ch = self._parse_chunk()

		if ch is None:
			return False

		self.records[ch].extend(self.parser.processed[ch])

		# Now that we've copied the records in to our own storage, free them from
		# the parser.
		self.parser.clear_processed()

		return True

	def read(self):
		""" Read a single record from the file
		:returns: [ch1_record, ...]
		"""
		while not all([ len(r) >= 1 for r in self.records]):
			if not self._process_chunk():
				break

		# Make sure we have matched samples for all channels
		if not all([ len(r) for r in self.records ]):
			return None

		rec = []
		for r in self.records:
			rec.append(r.pop(0))

		return rec

	def readall(self):
		""" Returns an array containing all the data from the file.

		Be aware that this can be very big in the case of long or high-rate
		captures. """
		ret = []

		for rec in self:
			ret.append(rec)

		return ret

	def close(self):
		""" Safely close the file"""
		self.file.close()

	def to_csv(self, fname):
		""" Dump the contents of this data file as a CSV.

		:param fname: Output CSV filename.
		"""
		try: os.remove(fname)
		except OSError: pass
		# Don't actually care about the chunk contents, just that it's been loaded
		while self._parse_chunk() is not None:
			self.parser.dump_csv(fname)

	def __iter__(self):
		return self

	def __next__(self):
		d = self.read()

		if d is None or not len(d):
			raise StopIteration
		else:
			return d

	next = __next__ # Python 2/3 translation

	def __enter__(self):
		pass

	def __exit__(self):
		self.close()


class LIDataFileWriter(object):
	""" Eases the creation of LI format data files."""
	def __init__(self, filename, instr, instrv, chs, binstr, procstr, fmtstr, hdrstr, calcoeffs, timestep, starttime):
		""" Create object and write the header information.
		Not designed for general use, is likely to only be of utility in the Moku:Lab firmware.

		:param filename: Output file name
		:param instr: Numeric instrument identifier
		:param instrv: Numberic instrument version
		:param chs: Channel ON/OFF flags
		:param binstr: Format string representing the binary data from the instrument
		:param procstr: String array representing the record processing to apply to the data of each channel
		:param fmtstr: Format string describing the transformation from data records to CSV output
		:param hdrstr: Format string describing the header lines on a CSV output
		:param calcoeffs: Array of calibration coefficients for the data being acquired
		:param timestep: Time between records being captured
		:param starttime: Time at which the record was started, seconds since Jan 1 1970
		"""
		self.file = open(filename, 'wb')
		nch = 0
		if (chs & 0x01):
			nch +=1
		if (chs & 0x02):
			nch +=1
		
		self.file.write('LI1')
		hdr = struct.pack("<BBHdQ", chs, instr, instrv, timestep, starttime)

		for i in range(nch):
			hdr += struct.pack('<d', calcoeffs[i])

		hdr += struct.pack("<H", len(binstr)) + binstr

		for i in range(nch):
			hdr += struct.pack("<H", len(procstr[i])) + procstr[i]
			
		hdr += struct.pack("<H", len(fmtstr)) + fmtstr
		hdr += struct.pack("<H", len(hdrstr)) + hdrstr

		self.file.write(struct.pack("<H", len(hdr)))
		self.file.write(hdr)

	def add_data(self, data, ch):
		""" Append a data chunk to the open file.

		:param data: Bytestring of new data
		:param ch: Channel number to which the data belongs (0-indexed)
		"""
		self.file.write(struct.pack("<BH", ch, len(data)))
		self.file.write(data)

	def finalize(self):
		"""
		Save and close the file.
		"""
		self.file.close()

	def __enter__(self):
		pass

	def __exit__(self):
		self.finalize()

class LIDataParser(object):
	""" Backend class that parses raw bytestrings from the instruments according to given format strings.

	Unlikely to be of utility outside the Moku:Lab firmware, an end-user probably wants to instantiate
	an :any:`LIDataFileReader` instead."""

	@staticmethod
	def record_length(binstr):
		""" Returns the bit length of the records decribed by the given binary description string """
		b = LIDataParser._parse_binstr(binstr)
		return sum(zip(*b)[1])

	@staticmethod
	def _parse_binstr(binstr):
		fmt = []

		if binstr[0] == '>':
			raise InvalidFormatException("Big-endian data order currently not supported.")

		for clause in binstr.split(':'):
			try:
				typ, bitlen, literal = re.findall(r'([usfbrp])([0-9]+),*([0-9a-zA-Z]+)*', clause)[0]
				fmt.append((typ, int(bitlen), int(literal, 0) if len(literal) else None))
			except IndexError:
				raise InvalidFormatException("Can't parse binary specifier %s" % clause)

		return fmt

	@staticmethod
	def _parse_procstr(procstr, calcoeff):
		def _eval_lit(lit):
			if lit == '': return None
			elif lit == 'C': return calcoeff

			try: return int(lit, 0)
			except: pass

			try: return float(lit)
			except:
				raise InvalidFormatException("Can't parse literal %s" % lit)

		fmt = []

		for clause in procstr.split(':'):
			ops = re.findall(r'([*/\+\-&s\^fc])(\-?[0-9\.xA-F]+(e\-?[0-9]+)?)?', clause)

			ops = [ (op, _eval_lit(lit)) for op, lit, _ in ops]

			fmt.append(ops)

		return fmt


	def __init__(self, ch1, ch2, binstr, procstr, fmtstr, hdrstr, deltat, starttime, calcoeffs):

		if not len(binstr):
			raise InvalidFormatException("Can't use empty binary record string")

		self.binfmt = LIDataParser._parse_binstr(binstr)
		self.recordlen = sum(zip(*self.binfmt)[1])
		self.procstr = procstr

		self.nch = 0
		self.ch1 = bool(ch1)
		self.ch2 = bool(ch2)

		if self.ch1:
			self.nch += 1
		if self.ch2:
			self.nch += 1

		self.procfmt = []
		for ch in range(self.nch):
			self.procfmt.append(LIDataParser._parse_procstr(procstr[ch], calcoeffs[ch]))

		self.fmtdict = {
			'T' : datetime.datetime.fromtimestamp(starttime).strftime('%c'), # TODO: Nicely formatted datetime string
			't' : 0,
			'd' : deltat,
			'n' : 0,
		}
		self.fmt = fmtstr
		self.dout = hdrstr.format(**self.fmtdict)

		# We should be doing this based on number of channels
		self.dcache 	= ['' for x in range(self.nch)]
		self.records 	= [[] for x in range(self.nch)]
		self.processed 	= [[] for x in range(self.nch)]
		self._currecord = [[] for x in range(self.nch)]
		self._currfmt 	= [[] for x in range(self.nch)]

	def _process_records(self):
		#for ch in [0, 1]:
		for ch in range(self.nch):
			for record in self.records[ch]:
				rec = []
				for field, ops in zip(record, self.procfmt[ch]):
					val = field
					for op, lit in ops:
						if   op == '*': val *= lit
						elif op == '/': val /= lit
						elif op == '+': val += lit
						elif op == '-': val -= lit
						elif op == '&': val &= lit
						elif op == 's': val = math.sqrt(val)
						elif op == 'f': val = int(math.floor(val))
						elif op == 'c': val = int(math.ceil(val))
						elif op == '^': val = val**lit
						else: raise InvalidFormatException("Don't recognize operation %s", op)

					rec.append(val)

				if len(rec) > 1:
					self.processed[ch].append(tuple(rec))
				else:
					self.processed[ch].append(rec[0])

		# Remove all processed records
		self.records = [[] for x in range(self.nch)]

	def _format_records(self):
		new_data = []

		# Single channel logging
		if self.nch == 1:
			for rec in self.processed[0]:
				self.fmtdict['n'] += 1
				self.fmtdict['t'] = (self.fmtdict['n'] - 1) * self.fmtdict['d']
				if self.ch1:
					new_data.append(self.fmt.format(ch1=rec, **self.fmtdict))
				else:
					new_data.append(self.fmt.format(ch2=rec, **self.fmtdict))

			self.dout += ''.join(new_data)

			return len(self.processed[0])
		else:
			i = 0
			print self.processed
			for rec1, rec2 in zip(*self.processed):
				self.fmtdict['n'] += 1
				self.fmtdict['t'] = (self.fmtdict['n'] - 1) * self.fmtdict['d']
				new_data.append(self.fmt.format(ch1=rec1, ch2=rec2, **self.fmtdict))
				i += 1

			self.dout += ''.join(new_data)

			return i

	def set_coeff(self, ch, coeff):
		self.procfmt[ch] = LIDataParser._parse_procstr(self.procstr[ch], coeff)

	def dump_csv(self, fname=None):
		""" Write out incremental CSV output from new data"""
		n_formatted = self._format_records()
		self.clear_processed(n_formatted)

		if not fname:
			d = self.dout
			self.dout = ''
			return d

		with open(fname, 'a') as f:
			f.write(self.dout)

		self.dout = ''

	def clear_processed(self, _len=None):
		""" Flush processed data.

		Called by the data consumer to indicate that it's no longer of use (e.g. has been
		written to a file or otherwise processed)."""
		if _len is None:
			self.processed = [[] for x in range(self.nch)]
		else:
			# Clear out the raw and processed records so we can stream
			# chunk at a time
			for i in range(len(self.processed)):
				self.processed[i] = self.processed[i][_len:]

	def _parse(self, data, ch):
		# Manipulation is done on a string of ASCII '0' and '1'. Tried using
		# the bitarray package but that's ~3x slower than the string version and
		# the bitstring package is around 7x slower.

		# Convert channel number to processing array index
		if ch == 0 or self.nch == 1:
			chidx = 0
		elif ch == 1:
			chidx = 1

		# This is all hard-coded little-endian; we reverse the bitstrings at the
		# byte level here, then reverse them again at the field level below to
		# correctly parse the fields LE.
		self.dcache[chidx] += ''.join([ "{:08b}".format(d)[::-1] for d in bytearray(data) ])

		#print ch
		#print ''.join([ "{:02X}".format(ord(x)) for x in data])

		while True:
			if not len(self._currfmt[chidx]):
				self._currfmt[chidx] = self.binfmt[:]

				if len(self._currecord[chidx]):
					self.records[chidx].append(self._currecord[chidx])
				self._currecord[chidx] = []

			_type, _len, lit = self._currfmt[chidx][0]

			if len(self.dcache[chidx]) < _len:
				break

			# TODO: This is hard-coded little endian. Need to correctly handle the endianness specifier
			# in the binary format string.
			candidate = self.dcache[chidx][:_len][::-1]

			if _type in 'up':
				val = int(candidate, 2)
			elif _type == 's':
				val = int(candidate, 2)

				if candidate[0] == '1':
					val -= (1 << _len)
			elif _type == 'f':
				if _len == 32:
					fmtstr = 'If'
				elif _len == 64:
					fmtstr = 'Qd'
				else:
					raise InvalidFormatException("Can't have a floating point spec with bit length other than 32/64 bits")

				bitpattern = struct.pack(fmtstr[0], int(candidate, 2))
				val = struct.unpack(fmtstr[1], bitpattern)[0]
			elif _type == 'b':
				val = candidate == '1'
			else:
				raise InvalidFormatException("Don't know how to handle '%s' types" % _type)

			if not lit or val == lit:
				if _type != 'p':
					self._currecord[chidx].append(val)
				self._currfmt[chidx] = self._currfmt[chidx][1:]

				# Drop off the whole successfully-matched field.
				self.dcache[chidx] = self.dcache[chidx][_len:]
			else:
				# If we fail a literal match, drop the entire pattern and start again
				log.debug("Literal mismatch (%d != %d), dropped partial record %s", val, lit, str(self._currecord[chidx]))
				self._currecord[chidx] = []
				self._currfmt[chidx] = []

				# Drop off a byte, assuming that that is the base granulatity at which the data has been captured
				self.dcache[chidx] = self.dcache[chidx][8:]
			

		if len(self._currecord[chidx]) and not len(self._currfmt[chidx]):
			self.records[chidx].append(self._currecord[chidx])


	def parse(self, data, ch):
		""" Parse a chunk of data.

		:param data: bytestring of new data
		:param ch: Channel to which the data belongs"""
		self._parse(data, ch)
		self._process_records()

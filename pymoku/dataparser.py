#!/usr/bin/env python
import time, datetime, math
import logging
import re, struct

log = logging.getLogger(__name__)

class InvalidFormatException(Exception): pass
class InvalidFileException(Exception): pass

class LIDataFileReader(object):
	def __init__(self, filename):
		self.records = []
		self.cal = []
		self.file = open(filename, 'rb')
		f = self.file

		if f.read(2) != 'LI':
			raise InvalidFileException("Bad Magic")

		v = f.read(1)
		if v != '1':
			raise InvalidFileException("Unknown File Version %s" % v)

		pkthdr_len = struct.unpack("<H", f.read(2))[0]
		self.nch, self.instr, self.instrv, self.deltat, self.starttime = struct.unpack("<BBHfQ", f.read(16))

		for i in range(self.nch):
			self.cal.append(struct.unpack("<d", f.read(8))[0])

		reclen = struct.unpack("<H", f.read(2))[0]
		self.rec = f.read(reclen)
		proclen = struct.unpack("<H", f.read(2))[0]
		self.proc = f.read(proclen)
		fmtlen = struct.unpack("<H", f.read(2))[0]
		self.fmt = f.read(fmtlen)
		hdrlen = struct.unpack("<H", f.read(2))[0]
		self.hdr = f.read(hdrlen)

		log.debug("NCH: %d INSTR: %d INSTRV: %d DT: %d", self.nch, self.instr, self.instrv, self.deltat)
		log.debug("B: %s P: %s F: %s H: %s", self.rec, self.proc, self.fmt, self.hdr)

		if f.tell() != pkthdr_len + 5:
			raise InvalidFileException("Incorrect File Header Length (expected %d got %d)" % (pkthdr_len + 5, f.tell()))

		for i in range(self.nch): self.records.append([])

		self.fmtdict = {
			'T' : datetime.datetime.fromtimestamp(self.starttime).strftime('%c'), # TODO: Nicely formatted datetime string
			't' : 0,
			'd' : self.deltat,
			'n' : 0,
		}

		self.dout = self.hdr.format(**self.fmtdict)

		self.parser = LIDataParser(self.rec, self.proc, self.cal[:])

	def _format_records(self):
		log.debug(self.parser.processed)

		if self.nch == 1:
			for rec1 in self.parser.processed[0]:
				self.fmtdict['n'] += 1
				self.fmtdict['t'] += self.fmtdict['d']
				self.dout += self.fmt.format(ch1=rec1, ch2=None, **self.fmtdict)
		else:
			for rec1, rec2 in zip(*self.parser.processed):
				self.fmtdict['n'] += 1
				self.fmtdict['t'] += self.fmtdict['d']
				self.dout += self.fmt.format(ch1=rec1, ch2=rec2, **self.fmtdict)

	def _load_chunk(self):

		dhdr = self.file.read(3)
		if len(dhdr) != 3:
			return False

		ch, _len = struct.unpack("<BH", dhdr)

		# Convert channel to zero-index
		ch -= 1

		d = self.file.read(_len)

		if len(d) != _len:
			raise InvalidFileException("Unexpected EOF while reading data")

		self.parser.parse(d, ch)
		self.records[ch].extend(self.parser.processed[ch])

		return True

	def read(self):
		while not all([ len(r) >= 1 for r in self.records]):
			if not self._load_chunk():
				break

		# Make sure we have matched samples for all channels
		if not all([ len(r) for r in self.records ]):
			return None

		rec = []
		for r in self.records:
			rec.append(r.pop(0))

		return rec

	def readall(self):
		ret = []

		for rec in self:
			ret.append(rec)

		return ret

	def to_csv(self, fname=None):
		self._format_records()

		if not fname:
			return self.dout

		with open(fname, 'w') as f:
			f.write(self.dout)

	def close(self):
		self.file.close()

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
	def __init__(self, filename, instr, instrv, nch, binstr, procstr, fmtstr, hdrstr, calcoeffs, timestep, starttime):
		self.file = open(filename, 'wb')

		self.file.write('LI1')
		hdr = struct.pack("<BBHfQ", nch, instr, instrv, timestep, starttime)
		hdr += ''.join([ struct.pack('<d', c) for c in calcoeffs])
		hdr += struct.pack("<H", len(binstr)) + binstr
		hdr += struct.pack("<H", len(procstr)) + procstr
		hdr += struct.pack("<H", len(fmtstr)) + fmtstr
		hdr += struct.pack("<H", len(hdrstr)) + hdrstr

		self.file.write(struct.pack("<H", len(hdr)))
		self.file.write(hdr)

	def add_data(self, data, ch):
		self.file.write(struct.pack("<BH", ch, len(data)))
		self.file.write(data)

	def finalize(self):
		self.file.close()

	def __enter__(self):
		pass

	def __exit__(self):
		self.finalize()

class LIDataParser(object):
	@staticmethod
	def _parse_binstr(binstr):
		fmt = []

		if binstr[0] == '>':
			raise InvalidFormatException("Big-endian data order currently not supported.")

		for clause in binstr.split(':'):
			try:
				typ, bitlen, literal = re.findall(r'([usfbrp])([0-9]+),*([0-9a-zA-Z\-]+)*', clause)[0]
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
			ops = re.findall(r'([*/\+\-&s\^fc])(\-?[0-9\.xA-F]+)?', clause)

			ops = [ (op, _eval_lit(lit)) for op, lit in ops]

			fmt.append(ops)

		return fmt

	@staticmethod
	def _parse_unsigned(bits):
		return int(bits, 2)

	@staticmethod
	def _parse_signed(bits):
		val = LIDataParser._parse_unsigned(bits)

		if bits[0] == '1':
			val -= (1 << len(bits))

		return val
	
	@staticmethod
	def _parse_float(bits):
		import struct

		if len(bits) == 32:
			fmtstr = 'If'
		elif len(bits) == 64:
			fmtstr = 'Qd'
		else:
			raise InvalidFormatException("Can't have a floating point spec with bit length other than 32/64 bits")

		bitpattern = struct.pack(fmtstr[0], LIDataParser._parse_unsigned(bits))

		return struct.unpack(fmtstr[1], bitpattern)[0]

	@staticmethod
	def _parse_boolean(bits):
		if len(bits) != 1:
			raise InvalidFormatException("Boolean that isn't a single bit")

		return bits == '1'

	def __init__(self, binstr, procstr, calcoeffs):

		if not len(binstr):
			raise InvalidFormatException("Can't use empty binary record string")

		self.binfmt = LIDataParser._parse_binstr(binstr)
		self.recordlen = sum(zip(*self.binfmt)[1])

		# This parser assumes two channels but the input file may only be 1
		while len(calcoeffs) < 2:
			calcoeffs.append(0)

		self.procfmt = []
		for ch in range(2):
			self.procfmt.append(LIDataParser._parse_procstr(procstr, calcoeffs[ch]))

		self.dcache = ['', '']

		self.records = [[], []]
		self.processed = [[], []]
		self._currecord = [[], []]
		self._currfmt = [[], []]

	def _process_records(self):
		for ch in [0, 1]:
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


	def parse(self, data, ch):
		# Manipulation is done on a string of ASCII '0' and '1'. Could swap this
		# out for bitarray primitives if performance turns out to be a problem.
		# This is all hard-coded little-endian; we reverse the bitstrings at the
		# byte level here, then reverse them again at the field level below to
		# correctly parse the fields LE.
		self.dcache[ch] += ''.join([ "{:08b}".format(d)[::-1] for d in bytearray(data) ])

		while True:
			if not len(self._currfmt[ch]):
				self._currfmt[ch] = self.binfmt[:]

				if len(self._currecord[ch]):
					self.records[ch].append(self._currecord[ch])
				self._currecord[ch] = []

			_type, _len, lit = self._currfmt[ch][0]

			if len(self.dcache[ch]) < _len:
				break

			# TODO: This is hard-coded little endian. Need to correctly handle the endianness specifier
			# in the binary format string.
			candidate = self.dcache[ch][:_len][::-1]

			if _type in 'up':
				val = LIDataParser._parse_unsigned(candidate)
			elif _type == 's':
				val = LIDataParser._parse_signed(candidate)
			elif _type == 'f':
				val = LIDataParser._parse_float(candidate)
			elif _type == 'b':
				val = LIDataParser._parse_boolean(candidate)
			else:
				raise InvalidFormatException("Don't know how to handle '%s' types" % _type)

			if not lit or val == lit:
				if _type != 'p':
					self._currecord[ch].append(val)
				self._currfmt[ch].pop(0)
			else:
				# If we fail a literal match, drop the entire pattern and start again
				self._currecord[ch] = []
				self._currfmt[ch] = []

			self.dcache[ch] = self.dcache[ch][_len:]

		if len(self._currecord[ch]) and not len(self._currfmt[ch]):
			self.records[ch].append(self._currecord[ch])

		self._process_records()

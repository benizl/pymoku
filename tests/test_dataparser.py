#!/usr/bin/env python


import pytest
import sys, os
sys.path.append('..')

import logging
logging.basicConfig(level=logging.DEBUG)

from pymoku.dataparser import *

binfmt_data = [
	("<s32", "\x00\x00\x00\x00", [[0]]), # Simple signed unpack
	("<s32", "\x00\x00\x00\x00\xFF\xFF\xFF\xFF\x00\x11\x22\x33", [[0], [-1], [0x33221100]]), # Simple signed unpack
	("<u32", "\x00\x00\x00\x00\xFF\xFF\xFF\xFF\x00\x11\x22\x33", [[0], [0xFFFFFFFF], [0x33221100]]), # Simple unsigned unpack
	("<u32:s32", "\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF", [[0xFFFFFFFF, -1], [0xFFFFFFFF, -1]]), # Record unpack
	("<u24:u24", "\x00\x11\x22\x33\x44\x55\x66\x77\x88\x99\xAA\xBB", [[0x221100, 0x554433], [0x887766, 0xBBAA99]]), # Odd length records
	("<u24:u24", "\x00\x11\x22\x33\x44\x55\x66\x77\x88", [[0x221100, 0x554433]]), # Incomplete number of records in input string
	("<f32", "\x00\x00\x80\xBF", [[-1.0]]), # Single precision float
	("<f64", "\x00\x00\x00\x00\x00\x00\xF0\xBF", [[-1.0]]), # Double precision float
	("<b1:u6:b1", "\xFF\x00", [[True, 0x3F, True], [False, 0, False]]), # Booleans, non-byte-length integers
	("<p1:u6:p1", "\xFF\x00", [[0x3F], [0]]), # Padding fields
	("<p8,0xFF:u8", "\x00\x00\xFF\x01\x00\xFF\x02\xFF\x03\x10", [[0x01], [0x02], [0x03]]), # Simple alignment byte
	("<u8,0xFF:u8", "\x00\x00\xFF\x01\x00\xFF\x02\xFF\x03\x10", [[0xFF, 0x01], [0xFF, 0x02], [0xFF, 0x03]]), # Recorded alignment byte
	("<p2,3:u6", "\x00\xFF\x00\xFF\x00\xFF", [[0x3F], [0x3F], [0x3F]]), # Alignment bits
	("<u8:p8,0xFF:u8", "\x01\xFF\x02\xFF\x03\xFF\x00\x00\x00\x04\xFF\x05", [[1, 2], [4, 5]]), # Alignment in the middle of a field
]

@pytest.mark.parametrize("fmt,din,expected", binfmt_data)
def test_binfmts(fmt, din, expected):
	dut = LIDataParser(1, fmt, "", "", "", 0, 0, [1, 1])
	# Use the internal parser method so the records don't get processed and removed before
	# we've had a chance to check them

	for ch in [0, 1]:
		dut._parse(din, ch)
		assert dut.records[ch] == expected

procfmt_data = [
	("<s32", "", "\x01\x00\x00\x00", [1]), # No-op, single element tuple
	("<s32:f32", ":", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(1,-1.0)]), # No-op
	("<s32:f32", "*-1e2:*1e-1", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(-100,-0.1)]), # Exponential notation
	("<s32:f32", "*2:*2", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(2,-2.0)]), # Multiplication
	("<s32:f32", "*-2:*-2", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(-2,2.0)]), # Multiplication by negative
	("<s32:f32", "*C:*C", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(2,-2.0)]), # Multiplication by calibration coefficient (hard-coded to two in the fixture)
	("<s32:f32", "/2:/2", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(0,-0.5)]), # integer division
	("<s32:f32", "/2.0:/2.0", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(0.5,-0.5)]), # fp division
	("<s32:f32", "+0x01:-0x01", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(2, -2)]), # Hex literals, addition and subtraction
	("<s32:f32", "&0:f&0", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(0, 0)]), # Masking and float-to-int conversion by floor operation
	("<s32:f32", "s:*-1s", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(1, 1)]), # Square root, compound operations
	("<s32:f32", "+1^2:-1^2", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(4, 4)]), # Square root, compound operations
	("<s32:f32", "*0.5f:*-0.5c", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(0, 1)]), # Floor and ceiling operations
	("<s32:f32", "+1+1-2:-1-1+2", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(1, -1.0)]), # Multiple operations
	("<s32:f32", "+1+1-2:-1-1+2e-1-5", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(1, -7.8)]), # Multiple operations
	("<s32:f32", "+1 +1 -2:-1 -1 +2e-1 -5", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(1, -7.8)]), # Spaces between operations
	("<s32:f32", "+1+1-2:-1-1+2", "\x01\x00\x00\x00\x00\x00\x80\xBF\x01\x00\x00\x00\x00\x00\x80\xBF\x00\x80\xBF", [(1, -1.0),(1, -1.0)]), # Multiple records, including partial
]

@pytest.mark.parametrize("_bin,proc,din,expected", procfmt_data)
def test_procfmts(_bin, proc, din, expected):
	dut = LIDataParser(1, _bin, proc, "", "", 0, 0, [2, 2])

	for ch in [0, 1]:
		dut.parse(din, ch)
		assert dut.processed[ch] == expected


# File contents are hand-crafted, hence the small number of test cases!
write_binfile_data = [
	(1, 1, 1, "", "", "", "", [1], 1, 0, '',
		'LI1\x20\x00\x01\x01\x01\x00\x00\x00\x80\x3F\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xF0\x3F\x00\x00\x00\x00\x00\x00\x00\x00'),
	(1, 1, 1, "A", "B", "C", "D", [1], 1, 0, '',
		'LI1\x24\x00\x01\x01\x01\x00\x00\x00\x80\x3F\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xF0\x3F\x01\x00A\x01\x00B\x01\x00C\x01\x00D'),
	(1, 1, 1, "", "", "", "", [1], 1, 0, '\x00\x00\x00\x00',
		'LI1\x20\x00\x01\x01\x01\x00\x00\x00\x80\x3F\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xF0\x3F\x00\x00\x00\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x00\x00\x01\x04\x00\x00\x00\x00\x00'),
]

@pytest.mark.parametrize("instr,instrv,nch,binstr,procstr,fmtstr,hdrstr,calcoeffs,timestep,starttime,data,expected", write_binfile_data)
def test_binfile_write(instr, instrv, nch, binstr, procstr, fmtstr, hdrstr, calcoeffs, timestep, starttime, data, expected):
	writer = LIDataFileWriter("test.dat", instr, instrv, nch, binstr, procstr, fmtstr, hdrstr, calcoeffs, timestep, starttime)
	if len(data):
		for ch in [0, 1]:
			writer.add_data(data, ch)

	writer.finalize()

	with open("test.dat") as f:
		assert f.read() == expected

	os.remove("test.dat")


roundtrip_binfile_data = [
	(1, 1, 1, "", "", "", "", [1], 1, 0, [''], [], "", True),
	(1, 1, 1, "<s32", "", "{ch1}\r\n", "Header\r\n", [1], 1, 0, [''], [], "Header\r\n", False),
	(1, 1, 1, "<s32", "", "{ch1}\r\n", "Header\r\n", [1], 1, 0, ['\x00\x00\x00\x00'], [[0]], "Header\r\n0\r\n", False),
	(1, 1, 1, "<s32:f32", "+1+1-2:-1-1+2", "{ch1[0]},{ch1[1]}\r\n", "Header\r\n", [1], 1, 0,
		["\x01\x00\x00\x00\x00\x00\x80\xBF\x01\x00\x00\x00\x00\x00\x80\xBF\x00\x80\xBF"], [[(1, -1.0)],[(1, -1.0)]],
		"Header\r\n1,-1.0\r\n1,-1.0\r\n", False), # Multiple records, including partial
	(1, 1, 1, "<s32:f32", "+1+1-2:-1-1+2", "{ch1[0]},{ch1[1]}\r\n", "Header\r\n", [1], 1, 0,
		["\x01\x00\x00\x00\x00\x00\x80", "\xBF\x01\x00\x00\x00\x00\x00\x80\xBF\x00\x80\xBF"], [[(1, -1.0)],[(1, -1.0)]],
		"Header\r\n1,-1.0\r\n1,-1.0\r\n", False), # same again, split data
	(1, 1, 2, "<s32:f32", "+1+1-2:-1-1+2", "{ch1[0]},{ch1[1]},{ch2[0]},{ch2[1]}\r\n", "Header\r\n", [1, 1], 1, 0,
		["\x01\x00\x00\x00\x00\x00\xA0\xC0\x01\x00\x00\x00\x00\x00\x80\xBF\x00\x80\xBF"], [[(1, -5.0),(1, -5.0)],[(1, -1.0),(1, -1.0)]],
		"Header\r\n1,-5.0,1,-5.0\r\n1,-1.0,1,-1.0\r\n", False), # Two channels
]

@pytest.mark.parametrize("instr,instrv,nch,binstr,procstr,fmtstr,hdrstr,calcoeffs,timestep,starttime,din,dout,csv,supposedtobeborked", roundtrip_binfile_data)
def test_binfile_roundtrip(instr, instrv, nch, binstr, procstr, fmtstr, hdrstr, calcoeffs, timestep, starttime, din, dout, csv, supposedtobeborked):
	writer = LIDataFileWriter("test.dat", instr, instrv, nch, binstr, procstr, fmtstr, hdrstr, calcoeffs, timestep, starttime)

	# Input data format is binary, output format is records
	for d in din:
		for ch in range(nch):
			writer.add_data(d, ch)

	writer.finalize()

	if supposedtobeborked:
		with pytest.raises(InvalidFormatException):
			reader = LIDataFileReader("test.dat")
	else:
		reader = LIDataFileReader("test.dat")

		assert reader.rec == binstr
		assert reader.proc == procstr
		assert reader.fmt == fmtstr
		assert reader.hdr == hdrstr
		assert reader.nch == nch
		assert reader.instr == instr
		assert reader.instrv == instrv
		assert reader.deltat == timestep
		assert reader.starttime == starttime
		assert reader.cal == calcoeffs

		assert reader.readall() == dout

		# No CSV will get written if there's no output data (not even header)
		if len(dout) > 0:
			# Reinitialise the reader from the beginning of the data file
			reader = LIDataFileReader("test.dat")
			reader.to_csv("test.csv")
			assert open("test.csv").read() == csv

# TODO: Two-channel tests


stream_csv_data = [
	(1, "<s32:f32", "+1+1-2:-1-1+2", "{ch1[0]},{ch1[1]}\r\n", "Header\r\n", [1], 1, 0,
		["\x01\x00\x00\x00\x00\x00\x80\xBF\x01\x00\x00\x00\x00\x00\x80\xBF\x00\x80\xBF"],
		"Header\r\n1,-1.0\r\n1,-1.0\r\n"), # Multiple records, including partial
	(1, "<s32:f32", "+1+1-2:-1-1+2", "{ch1[0]},{ch1[1]}\r\n", "Header\r\n", [1], 1, 0,
		["\x01\x00\x00\x00\x00\x00", "\x80\xBF\x02\x00\x00\x00","\x00\x00\x80\xBF\x00\x80\xBF"],
		"Header\r\n1,-1.0\r\n2,-1.0\r\n"), # same again, split data, non-record aligned
	(2, "<s32:f32", "+1+1-2:-1-1+2", "{ch1[0]},{ch1[1]},{ch2[0]},{ch2[1]}\r\n", "Header\r\n", [1], 1, 0,
		["\x01\x00\x00\x00\x00\x00", "\x80\xBF\x02\x00\x00\x00","\x00\x00\x80\xBF\x00\x80\xBF"],
		"Header\r\n1,-1.0,1,-1.0\r\n2,-1.0,2,-1.0\r\n"), # Two channels
]

@pytest.mark.parametrize("nch,binstr,procstr,fmtstr,hdrstr,calcoeffs,timestep,starttime,din,csv", stream_csv_data)
def test_stream_csv(nch, binstr, procstr, fmtstr, hdrstr, calcoeffs, timestep, starttime, din, csv):
	parser = LIDataParser(nch, binstr, procstr, fmtstr, hdrstr, timestep, starttime, calcoeffs)

	try: os.remove("test.csv")
	except OSError: pass

	for d in din:
		for ch in range(nch):
			parser.parse(d, ch)

		parser.dump_csv("test.csv")

	with open("test.csv") as f:
		assert f.read() == csv

	os.remove("test.csv")

if __name__ == '__main__':
	pytest.main()

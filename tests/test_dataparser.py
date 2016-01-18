#!/usr/bin/env python


import pytest
import sys
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
	dut = LIDataParser(fmt, "", [1, 1])
	dut.parse(din, 0)

	assert dut.records[0] == expected

procfmt_data = [
	("<s32", "", "\x01\x00\x00\x00", [1]), # No-op, single element tuple
	("<s32:f32", ":", "\x01\x00\x00\x00\x00\x00\x80\xBF", [(1,-1.0)]), # No-op
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
	("<s32:f32", "+1+1-2:-1-1+2", "\x01\x00\x00\x00\x00\x00\x80\xBF\x01\x00\x00\x00\x00\x00\x80\xBF\x00\x80\xBF", [(1, -1.0),(1, -1.0)]), # Multiple records, including partial
]

@pytest.mark.parametrize("_bin,fmt,din,expected", procfmt_data)
def test_procfmts(_bin, fmt, din, expected):
	dut = LIDataParser(_bin, fmt, [2, 2])
	dut.parse(din, 0)

	assert dut.processed[0] == expected


# File contents are hand-crafted, hence the small number of test cases!
write_binfile_data = [
	(1, 1, 1, "", "", "", "", [1], 1, 0, '',
		'LI1\x20\x00\x01\x01\x01\x00\x00\x00\x80\x3F\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xF0\x3F\x00\x00\x00\x00\x00\x00\x00\x00'),
	(1, 1, 1, "A", "B", "C", "D", [1], 1, 0, '',
		'LI1\x24\x00\x01\x01\x01\x00\x00\x00\x80\x3F\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xF0\x3F\x01\x00A\x01\x00B\x01\x00C\x01\x00D'),
	(1, 1, 1, "", "", "", "", [1], 1, 0, '\x00\x00\x00\x00',
		'LI1\x20\x00\x01\x01\x01\x00\x00\x00\x80\x3F\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xF0\x3F\x00\x00\x00\x00\x00\x00\x00\x00\x01\x04\x00\x00\x00\x00\x00'),
]

@pytest.mark.parametrize("instr,instrv,nch,binstr,procstr,fmtstr,hdrstr,calcoeffs,timestep,starttime,data,expected", write_binfile_data)
def test_binfile_write(instr, instrv, nch, binstr, procstr, fmtstr, hdrstr, calcoeffs, timestep, starttime, data, expected):
	writer = LIDataFileWriter("test.dat", instr, instrv, nch, binstr, procstr, fmtstr, hdrstr, calcoeffs, timestep, starttime)
	if len(data):
		writer.add_data(data, 1)

	writer.finalize()

	with open("test.dat") as f:
		assert f.read() == expected


roundtrip_binfile_data = [
	(1, 1, 1, "", "", "", "", [1], 1, 0, '', [], True),
	(1, 1, 1, "<s32", "", "{ch1[0]}\r\n", "Header", [1], 1, 0, '', [], False),
	(1, 1, 1, "<s32", "", "{ch1[0]}\r\n", "Header", [1], 1, 0, '\x00\x00\x00\x00', [[0]], False),

	(1, 1, 1, "<s32:f32", "+1+1-2:-1-1+2", "{ch1[0]}\r\n", "Header", [1], 1, 0,
		"\x01\x00\x00\x00\x00\x00\x80\xBF\x01\x00\x00\x00\x00\x00\x80\xBF\x00\x80\xBF", [[(1, -1.0)],[(1, -1.0)]], False), # Multiple records, including partial
]

@pytest.mark.parametrize("instr,instrv,nch,binstr,procstr,fmtstr,hdrstr,calcoeffs,timestep,starttime,din,dout,supposedtobeborked", roundtrip_binfile_data)
def test_binfile_roundtrip(instr, instrv, nch, binstr, procstr, fmtstr, hdrstr, calcoeffs, timestep, starttime, din, dout, supposedtobeborked):
	writer = LIDataFileWriter("test.dat", instr, instrv, nch, binstr, procstr, fmtstr, hdrstr, calcoeffs, timestep, starttime)

	# Input data format is binary, output format is records
	if len(din):
		writer.add_data(din, 1)

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


# TODO: Test output all the way to CSV

if __name__ == '__main__':
	pytest.main()

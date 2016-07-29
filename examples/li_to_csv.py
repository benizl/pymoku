#!/usr/bin/env python

import sys
import pymoku.dataparser

if len(sys.argv) != 3:
	print("Usage: li_to_csv.py infile.li outfile.csv")
	exit(1)

reader = pymoku.dataparser.LIDataFileReader(sys.argv[1])
reader.to_csv(sys.argv[2])

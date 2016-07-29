#!/usr/bin/env python

import sys
from datetime import datetime

import pymoku.dataparser
import h5py

if len(sys.argv) != 3:
	print("Usage: li_to_csv.py infile.li outfile.hd5")
	exit(1)

reader = pymoku.dataparser.LIDataFileReader(sys.argv[1])
writer = h5py.File(sys.argv[2], 'w')
ncols = reader.nch

set_name = 'moku:datalog'

# Start with storage for 100 items, it'll be expanded as we add data. We don't know the
# length of the data set to begin with.
writer.create_dataset(set_name, (100,ncols), maxshape=(None,ncols))
writer[set_name].attrs['timestep'] = reader.deltat
writer[set_name].attrs['start_secs'] = reader.starttime
writer[set_name].attrs['start_time'] = datetime.fromtimestamp(reader.starttime).strftime('%c')
writer[set_name].attrs['instrument'] = reader.instr
writer[set_name].attrs['instrument_version'] = reader.instrv

i = 0
for record in reader:
	curlen = len(writer[set_name])
	if curlen <= i:
		# Exponential allocation strategy, works fairly well for different sized files.
		# We truncate to the correct length at the end anyway.
		writer[set_name].resize((2*curlen, ncols))

	writer[set_name][i,:] = record[:ncols]
	i += 1

# Truncate the file to the correct length
writer[set_name].resize((i, ncols))
writer.close()

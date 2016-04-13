from pymoku import Moku
from pymoku.instruments import *
import time, logging

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.DEBUG)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku('192.168.1.106')

i = m.discover_instrument()
if i is None or i.type != 'specan':
	print "No or wrong instrument deployed"
	i = SpecAn()
	m.attach_instrument(i)
else:
	print "Attached to existing Spectrum Analyser"

# Initial SpecAn setup
i.set_defaults()
i.set_buffer_length(4)
i.framerate = 3

# Set frequency span here
i.set_fullspan(15e3, 36e3)

# Push all new configuration to the Moku device
i.commit()

'''
regs =  i.dump_remote_regs()
for idx, r in regs:
	print "({:d} : {:8X})".format(idx,r)
'''

# Set up plot
line1, = plt.plot([])
line2, = plt.plot([])
plt.yscale('log')
plt.ion()
plt.show()
plt.grid(b=True)
plt.ylim([0, 1000000])
plt.autoscale(axis='x',tight=True)

try:
	# Get an initial frame to set any frame-specific plot parameters
	frame = i.get_frame()

	# Format the x-axis as a frequency scale 
	ax = plt.gca()
	formatter = FuncFormatter(frame.get_freqFmt)
	ax.xaxis.set_major_formatter(formatter)

	# Start drawing new frames
	while True:
		frame = i.get_frame()

		plt.pause(0.001)
		line1.set_ydata(frame.ch1)
		line2.set_ydata(frame.ch2)
		line1.set_xdata(frame.ch1_fs)
		line2.set_xdata(frame.ch2_fs)
		ax.relim()
		ax.autoscale_view()
		plt.draw()
finally:
	m.close()

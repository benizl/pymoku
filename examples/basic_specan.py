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

#################################
# BEGIN Instrument Configuration
# ------------------------------
# Set these parameters
#################################
# Set power scale to dBm
dbm = True

# Set window type {NONE, BH, FLATTOP, HANNING}
windowType = i.window_type('NONE')

# Set FFT frequency span (Hz)
start_freq = 10e6
stop_freq = 24.32e6
#################################
# END Instrument Configuration
#################################

# Apply parameter settings to instrument class
i.set_defaults()
i.set_buffer_length(4)
i.framerate = 2
i.set_dbmscale(dbm)
i.set_window(windowType)
i.set_span(start_freq, stop_freq)

# Push all new configuration to the Moku device
i.commit()

# Set up basic plot configurations
line1, = plt.plot([])
line2, = plt.plot([])
plt.ion()
plt.show()
plt.grid(b=True)
if(dbm):
	plt.ylim([-200, 100])
else:
	plt.ylim([-0.5,1])
plt.autoscale(axis='x',tight=True)

try:
	# Get an initial frame to set any frame-specific plot parameters
	frame = i.get_frame()

	# Format the x-axis as a frequency scale 
	ax = plt.gca()
	ax.xaxis.set_major_formatter(FuncFormatter(frame.get_xaxis_fmt))
	ax.yaxis.set_major_formatter(FuncFormatter(frame.get_yaxis_fmt))
	ax.fmt_xdata = frame.get_xcoord_fmt
	ax.fmt_ydata = frame.get_ycoord_fmt

	# Start drawing new frames
	while True:
		frame = i.get_frame()
		plt.pause(0.001)

		# Set the frame data for each channel plot
		line1.set_ydata(frame.ch1)
		line2.set_ydata(frame.ch2)
		# Frequency axis shouldn't change, but to be sure
		line1.set_xdata(frame.ch1_fs)
		line2.set_xdata(frame.ch2_fs)
		# Ensure the frequency axis is a tight fit
		ax.relim()
		ax.autoscale_view()

		# Redraw the lines
		plt.draw()
finally:
	m.close()

#
# pymoku example: Phasemeter networking streaming
#
# This example provides a network stream of Phasemeter
# data samples from Channel 1 and Channel 2. These samples
# are output in the form (I,Q,F,phi,counter) for each channel.
#
# (c) 2016 Liquid Instruments Pty. Ltd.
#
from pymoku import Moku, NoDataException
from pymoku.instruments import *
import time, logging, math, numpy
import matplotlib.pyplot as plt

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.DEBUG)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku('192.168.1.121')

i = m.discover_instrument()

if i is None or i.type != 'phasemeter':
	print "No or wrong instrument deployed"
	i = PhaseMeter()
	m.attach_instrument(i)
else:
	print "Attached to existing Phasemeter"

try:
	# It's recommended to set default values for the instrument, otherwise the user
	# has to go ahead and explicitly set up many values themselves.
	i.set_defaults()

	# Set the initial phase-lock loop frequency for both channels
	# Channel 1: 6 MHz
	# Channel 2: 6 MHz
	i.set_initfreq(1, 2e6)
	i.set_initfreq(2, 6e6)

	# The sample rate must be set <=100Hz to avoid data loss so we set it to 100Hz
	i.set_samplerate(10)

	# Channel 2: 0.5Vp-p Sine Wave, 2Hz.
	i.synth_sinewave(1, 1.5, 2e6)

	# Atomically apply all instrument settings above
	i.commit()

	# Allow time for commit to flow down
	time.sleep(0.8)

	# Stop any existing data logging sessions and begin a new session
	# Logging session: 
	# 		Start time - 0 sec
	#		Duration - 20 sec
	#		Channel 1 - ON, Channel 2 - ON
	#		Log file type - Network Stream
	i.datalogger_stop()
	i.datalogger_start(start=0, duration=100, use_sd=True, ch1=True, ch2=True, filetype='net')

	# Set up basic plot configurations
	data1 = [None] * 1024
	data2 = [None] * 1024
	xdata1 = numpy.linspace(-1*(i.get_timestep()*1023), 0, 1024)
	xdata2 = numpy.linspace(-1*(i.get_timestep()*1023), 0, 1024)

	line1, = plt.plot(data1)
	line2, = plt.plot(data2)

	plt.ion()
	plt.show()
	plt.grid(b=True)
	ax = plt.gca()
	plt.xlim([-1*(i.get_timestep()*1023), 0])
	
	while True:
		# Get samples
		try:
			ch, idx, samp = i.datalogger_get_samples(timeout=5)
		except NoDataException as e:
			print "Data stream complete"
			break

		print "Ch: %d, Idx: %d, #Samples: %s" % (ch, idx, len(samp))

		# Append new samples on to the current ones
		if ch==1:
			datalen = len(samp)
			# Process the amplitudes
			data1 = data1[(datalen-1):-1]
			#xdata1 = xdata1[(len(xdata1)-1):-1]
			for s in samp:
				data1 = data1 + [math.sqrt(s[0]**2 + s[1]**2)]

			line1.set_ydata(data1)
			line1.set_xdata(xdata1)

		ax.relim()
		ax.autoscale_view()
		plt.draw()

	# Check if there were any errors
	e = i.datalogger_error()

	if e:
		print "Error occured: %s" % e

	i.datalogger_stop()
except Exception as e:
	print e
finally:
	m.close()
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
m = Moku.get_by_name('example')

i = m.discover_instrument()

if i is None or i.type != 'phasemeter':
	print "No or wrong instrument deployed"
	i = PhaseMeter()
	m.attach_instrument(i)
else:
	print "Attached to existing Phasemeter"

try:
	#################################
	# BEGIN Instrument Configuration
	# ------------------------------
	# Set these parameters
	#################################
	'''
		Which channels are ON?
	'''
	ch1 = True
	ch2 = True

	'''
		Initial channel scan frequencies
	'''
	ch1_freq = 10e6
	ch2_freq = 10e6

	'''
		Ouput sinewaves
	'''
	ch1_out_enable = True
	ch1_out_freq = 10e6
	ch1_out_amp = 1

	ch2_out_enable = True
	ch2_out_freq = 10e6
	ch2_out_amp = 1

	'''
		Log duration (sec)
	'''
	duration = 100
	#################################
	# END Instrument Configuration
	#################################

	# It's recommended to set default values for the instrument, otherwise the user
	# has to go ahead and explicitly set up many values themselves.
	i.set_defaults()

	# Set the initial phase-lock loop frequency for both channels
	i.set_initfreq(1, ch1_freq)
	i.set_initfreq(2, ch2_freq)

	# The sample rate must be set <=100Hz to avoid data loss so we set it to 10Hz
	i.set_samplerate(PM_LOGRATE_SLOW)

	# Set up signal generator for enabled channels
	if(ch1_out_enable):
		i.synth_sinewave(1, ch1_out_amp, ch1_out_freq)
		i.enable_output(1,ch1_out_enable)
	if(ch2_out_enable):
		i.synth_sinewave(2, ch2_out_amp, ch2_out_freq)
		i.enable_output(2,ch2_out_enable)

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
	i.datalogger_start(start=0, duration=duration, use_sd=True, ch1=ch1, ch2=ch2, filetype='net')

	# Set up basic plot configurations
	if ch1:
		ydata1 = [None] * 1024
		line1, = plt.plot(ydata1)
	if ch2:
		ydata2 = [None] * 1024
		line2, = plt.plot(ydata2)

	xdata = numpy.linspace(-1*(i.get_timestep()*1023), 0, 1024)

	plt.ion()
	plt.show()
	plt.grid(b=True)
	ax = plt.gca()
	ax.get_yaxis().get_major_formatter().set_useOffset(False)
	plt.xlim([-1*(i.get_timestep()*1023), 0])
	plt.ylabel('Amplitude (V)')
	plt.xlabel('Time (s)')
	
	while True:
		# Get samples
		try:
			ch, idx, samp = i.datalogger_get_samples(timeout=5)
		except NoDataException as e:
			print "Data stream complete"
			break
		print "Ch: %d, Idx: %d, #Samples: %s" % (ch, idx, len(samp))

		# Process the retrieved samples
		if ch1 & (ch==1):
			datalen = len(samp)
			ydata1 = ydata1[(datalen-1):-1]
			for s in samp:
				# Process individual sample 's' here. Output format [I,Q,f,phase]
				#
				#

				# Convert I,Q to amplitude and append to line graph
				ydata1 = ydata1 + [math.sqrt(s[4]**2 + s[5]**2)]

		elif ch2 & (ch==2):
			datalen = len(samp)
			ydata2 = ydata2[(datalen-1):-1]
			for s in samp:
				# Process individual sample 's' here. Output format [I,Q,f,phase]
				#
				#

				# Convert I,Q to amplitude and append to line graph
				ydata2 = ydata2 + [math.sqrt(s[4]**2 + s[5]**2)]

		# Must set lines for each draw loop
		if ch1:
			line1.set_ydata(ydata1)
			line1.set_xdata(xdata)
		if ch2:
			line2.set_ydata(ydata2)
			line2.set_xdata(xdata)

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
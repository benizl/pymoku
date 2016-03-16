#
# pymoku example: Phasemeter networking streaming
#
# This example provides a network stream of Phasemeter
# data samples from Channel 1 and Channel 2. These samples
# are output in the form (I,Q,F,phi,counter) for each channel.
#
# (c) 2016 Liquid Instruments Pty. Ltd.
#
from pymoku import Moku
from pymoku.instruments import *
import time, logging

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.INFO)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku('192.168.1.108')

#i = m.discover_instrument()
i = PhaseMeter()
m.attach_instrument(i)

'''if i is None or i.type != 'phasemeter':
	print "No or wrong instrument deployed"
	i = PhaseMeter()
	m.attach_instrument(i)
else:
	print "Attached to existing Phasemeter"'''

try:
	# It's recommended to set default values for the instrument, otherwise the user
	# has to go ahead and explicitly set up many values themselves.
	i.set_defaults()

	# Set the initial phase-lock loop frequency for both channels
	# Channel 1: 6 MHz
	# Channel 2: 6 MHz
	i.set_initfreq(1, 6e6)
	i.set_initfreq(2, 6e6)

	# The sample rate must be set <=100Hz to avoid data loss so we set it to 100Hz
	i.set_samplerate(10)

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
	i.datalogger_start(start=0, duration=20, use_sd=True, ch1=True, ch2=True, filetype='net')
	print "Sample rate: %.10e, Timestep: %.10e" % (i.get_samplerate(), i.get_timestep())


	while True:
		# Give Moku device time to accrue samples
		#time.sleep(1)

		# Get samples
		ch, idx, samp = i.datalogger_get_samples()
		print "Ch: %d, Idx: %d, Samples: %s" % (ch, idx, len(samp))

		# Print current session info
		trems, treme = i.datalogger_remaining()
		samples = i.datalogger_samples()
		print "Captured (%d samples); %d seconds from start, %d from end" % (samples, trems, treme)

		# Process the samples here
		
		for s in samp:
			# Do something with s[0:3]
			print s
		

		# Check if the logging session has finished
		if i.datalogger_completed():
			break

	# Check if there were any errors
	e = i.datalogger_error()

	if e:
		print "Error occured: %s" % e

	i.datalogger_stop()
except Exception as e:
	print e
finally:
	m.close()

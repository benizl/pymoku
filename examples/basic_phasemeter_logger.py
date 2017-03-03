#
# pymoku example: Phasemeter Binary/CSV datalogger
#
# This example provides a log file (binary or CSV) of Phasemeter
# data samples from Channel 1. The output log file will be
# timestamped and saved to the current working directory
#
# (c) 2016 Liquid Instruments Pty. Ltd.
#
from pymoku import Moku
from pymoku.instruments import *
import time, logging

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.INFO)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku('192.168.XXX.XXX')
i = m.discover_instrument()

if i is None or i.type != 'phasemeter':
	print("No or wrong instrument deployed. Re-deploying.")
	i = PhaseMeter()
	m.attach_instrument(i)
else:
	print("Attached to existing Phasemeter")

try:
	######################################################
	# BEGIN Configuration parameters
	# Set logging session and instrument configuration here
	######################################################
	# Samplerate (Hz)
	samplerate = 100

	# Set approximate log duration (sec)
	duration = 10

	# Output log file type {'csv,'bin'}
	filetype = 'csv'

	# Phasemeter initial frequency (Hz)
	ch1_initial_freq = 10e6

	######################################################
	# END Configuration parameters
	######################################################

	# The sample rate must be set <=200hz to avoid data loss so we set it to 100Hz
	i.set_samplerate(samplerate)

	# Set initial frequency for Channel 1
	i.set_initfreq(1,ch1_initial_freq)

	# Atomically apply all instrument settings above
	i.commit()

	# Cease any previous datalogging session
	i.datalogger_stop()

	# Begin new datalogging session
	# Set filetype to be one of {'csv', 'bin'}
	i.datalogger_start(start=0, duration=duration, use_sd=True, ch1=True, ch2=False, filetype=filetype)

	while True:
		time.sleep(0.5)
		trems, treme = i.datalogger_remaining()
		samples = i.datalogger_samples()
		print("Captured (%d samples); %d seconds from start, %d from end" % (samples, trems, treme))

		if i.datalogger_completed():
			break

	e = i.datalogger_error()

	if e:
		print("Error occured: %s" % e)

	i.datalogger_stop()
	i.datalogger_upload()
	
except Exception as e:
	print(e)
finally:
	m.close()

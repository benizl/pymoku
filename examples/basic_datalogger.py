from pymoku import Moku
from pymoku.instruments import *
import time, logging

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.INFO)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku.get_by_name('example')

i = Oscilloscope()
m.attach_instrument(i)

try:
	i.set_samplerate(10)
	i.set_xmode(OSC_ROLL)
	i.commit()
	i.datalogger_stop()

	i.datalogger_start(start=0, duration=10, use_sd=True, ch1=True, ch2=True, filetype='bin')

	while True:
		time.sleep(1)
		trems, treme = i.datalogger_remaining()
		samples = i.datalogger_samples()
		print "Captured (%d samples); %d seconds from start, %d from end" % (samples, trems, treme)

		if i.datalogger_completed():
			break

	e = i.datalogger_error()

	if e:
		print "Error occured: %s" % e

	i.datalogger_stop()
	i.datalogger_upload()
except Exception as e:
	print e
finally:
	m.close()

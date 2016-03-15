from pymoku import Moku
from pymoku.instruments import *
import time, logging

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.INFO)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku('192.168.1.104')

i = PhaseMeter()
m.attach_instrument(i)

try:
	i.set_defaults()
	i.set_initfreq(1, 6e6)
	i.set_initfreq(2, 6e6)

	i.commit()
	time.sleep(0.8)
	i.datalogger_stop()

	i.datalogger_start(start=0, duration=20, use_sd=True, ch1=True, ch2=True, filetype='net')

	while True:
		time.sleep(1)
		ch, idx, samp = i.datalogger_get_samples()
		print "Ch: %d, Idx: %d, Samples: %s" % (ch, idx, samp)

		trems, treme = i.datalogger_remaining()
		samples = i.datalogger_samples()
		print "Captured (%d samples); %d seconds from start, %d from end" % (samples, trems, treme)

		if i.datalogger_completed():
			break

	e = i.datalogger_error()

	if e:
		print "Error occured: %s" % e

	i.datalogger_stop()
except Exception as e:
	print e
finally:
	m.close()

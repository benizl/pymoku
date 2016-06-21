from pymoku import Moku, MokuException, NoDataException
from pymoku.instruments import *
import time, logging, traceback

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.INFO)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku.get_by_name('example')
i = Oscilloscope()
m.attach_instrument(i)

try:
	i.set_defaults()
	i.set_samplerate(10)
	i.set_xmode(OSC_ROLL)
	i.commit()
	time.sleep(1)

	i.datalogger_stop()

	i.datalogger_start(start=0, duration=100, use_sd=False, ch1=True, ch2=False, filetype='net')

	while True:
		ch, idx, d = i.datalogger_get_samples(timeout=5)

		print "Received samples %d to %d from channel %d" % (idx, idx + len(d) - 1, ch)
except NoDataException as e:
	# This will be raised if we try and get samples but the session has finished.
	print e
except Exception as e:
	print traceback.format_exc()
finally:
	i.datalogger_stop()
	m.close()

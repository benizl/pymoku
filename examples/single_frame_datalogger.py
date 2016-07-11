from pymoku import Moku, MokuException, NoDataException
from pymoku.instruments import *
import time, logging, traceback

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.DEBUG)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku.get_by_name('example')

i = m.discover_instrument()

if i is None or i.type != 'oscilloscope':
	print("No or wrong instrument deployed")
	i = Oscilloscope()
	m.attach_instrument(i)
else:
	print("Attached to existing Oscilloscope")

try:
	# In this case, we set the underlying oscilloscope in to Roll mode then wait a bit to
	# acquire samples. One could also leave the oscilloscope in whatever other X Mode they
	# wished, pause the acquisition then stream from there to retrieve the full-rate version
	# of a normal oscilloscope frame.
	i.set_defaults()
	i.set_samplerate(10)
	i.set_xmode(OSC_ROLL)
	i.commit()
	i.datalogger_stop()

	time.sleep(5)

	# Could also save to a file then use datalogger_upload(), but grabbing the data directly
	# from the network is cleaner
	i.datalogger_start_single(filetype='net')

	while True:
		ch, idx, d = i.datalogger_get_samples(timeout=5)

		print("Received samples %d to %d from channel %d" % (idx, idx + len(d), ch))
except NoDataException as e:
	# This will be raised if we try and get samples but the session has finished.
	print(e)
except Exception as e:
	print(traceback.format_exc())
finally:
	i.datalogger_stop()
	m.close()

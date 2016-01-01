from pymoku import Moku, MokuException
from pymoku.instruments import *
import time, logging, traceback

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.DEBUG)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku('192.168.1.106')#.get_by_name('example')

i = m.discover_instrument()

if i is None or i.type != 'oscilloscope':
	print "No or wrong instrument deployed"
	i = Oscilloscope()
	m.attach_instrument(i)
else:
	print "Attached to existing Oscilloscope"

i.set_defaults()
i.set_samplerate(1000) #10ksps
i.set_xmode(OSC_ROLL)
i.commit()

# TODO: Symbolic constants, simplify this logic in the underlying driver.
if i.datalogger_status() in  [1, 2, 6]:
	i.datalogger_stop()

i.datalogger_start(start=0, duration=10, filetype='net')

try:
	while True:
		ch, idx, d = i.datalogger_get_samples(timeout=5)

		print "Received samples %d to %d from channel %d" % (idx, idx + len(d), ch)
except MokuException as e:
	print e
except Exception as e:
	print traceback.format_exc()
finally:
	i.datalogger_stop()
	m.close()

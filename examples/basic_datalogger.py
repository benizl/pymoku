from pymoku import Moku
from pymoku.instruments import *
import time, logging

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.DEBUG)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku.get_by_name('example')

i = m.discover_instrument()

if i is None or i.type != 'oscilloscope':
	print "No or wrong instrument deployed"
	i = Oscilloscope()
	m.attach_instrument(i)
else:
	print "Attached to existing Oscilloscope"

i.set_defaults()
i.set_samplerate(10e3) #10ksps
i.set_xmode(OSC_ROLL)
i.commit()

# TODO: Symbolic constants, simplify this logic in the underlying driver.
if i.datalogger_status() in  [1, 2, 6]:
	i.datalogger_stop()

i.datalogger_start(start=10, duration=10, use_sd=False)

try:
	while True:
		time.sleep(1)
		s, b, trem = i.datalogger_status()
		print "Status %d (%d samples); %d seconds remaining" % (s, b, trem)
		# TODO: Symbolic constants
		if s not in [1, 2]:
			break

	i.datalogger_stop()
	i.datalogger_upload()
except Exception as e:
	print e
finally:
	m.close()

from pymoku import Moku
from pymoku.instruments import *
import time, logging

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.DEBUG)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku('192.168.1.117')

i = m.discover_instrument()

if i is None or i.type != 'oscilloscope':
	print "No or wrong instrument deployed"
	i = Oscilloscope()
	m.attach_instrument(i)
else:
	print "Attached to existing Oscilloscope"

i.set_defaults()

i.datalogger_start(1)

while True:
	time.sleep(1)
	s = i.datalogger_status()
	b = i.datalogger_transferred()
	print "Status %d (%d samples)" % (s, b)
	# TODO: Symbolic constants
	if s == 0 or s == 7:
		break

i.datalogger_stop()
m.close()

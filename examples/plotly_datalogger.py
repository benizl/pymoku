from pymoku import Moku, MokuException
from pymoku.instruments import *

import pymoku.plotly as pmp

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
i.set_samplerate(10)
i.set_xmode(OSC_ROLL)

i.synth_sinewave(1, 0.5, 0.5)
i.synth_sinewave(2, 0.5, 0.5)
i.commit()

# TODO: Symbolic constants, simplify this logic in the underlying driver.
#if i.datalogger_status() in  [1, 2, 6]:
i.datalogger_stop()

pmp.init(m, 'benizl.anu', 'na8qic5nqw', 'kdi5h54dhl', 'v7qd9o6bcq')

i.datalogger_start(start=0, duration=60*10, filetype='plot')

print "Plotly URL is: %s" % pmp.url(m)

try:
	while True:
		time.sleep(1)
		s, b, trem = i.datalogger_status()
		print "Status %d (%d samples); %d seconds remaining" % (s, b, trem)
		# TODO: Symbolic constants
		if s not in [1, 2]:
			break

except Exception as e:
	print e
finally:
	i.datalogger_stop()
	m.close()
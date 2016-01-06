from pymoku import Moku
from pymoku.instruments import *
import pymoku.plotly_support as ppy

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

try:
	i.set_defaults()
	i.commit()

	frame = i.get_frame()
	print "Plot URL is %s" % ppy.plot_frame(frame)

finally:
	m.close()

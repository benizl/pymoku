from pymoku import Moku
from pymoku.instruments import *
import time, logging

import matplotlib
import matplotlib.pyplot as plt

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.DEBUG)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku('192.168.69.245')

i = m.discover_instrument()

if i is None or i.type != 'oscilloscope':
	print "No or wrong instrument deployed"
	i = Oscilloscope()
	m.attach_instrument(i)
else:
	print "Attached to existing Oscilloscope"

i.set_defaults()
i.set_buffer_length(4)
i.set_source(1,OSC_SOURCE_DAC)
i.set_trigger(OSC_TRIG_DA1, OSC_EDGE_RISING, 0)
i.synth_sinewave(1,0.5,10,0)
#i.synth_squarewave(1, 0.5, 10, risetime=0.001, falltime=0.001, duty=0.3)
i.commit()

line1, = plt.plot([])
line2, = plt.plot([])
plt.ion()
plt.show()
plt.grid(b=True)
plt.ylim([-10, 10])
plt.xlim([0,1024])

try:
	last = 0
	while True:
		frame = i.get_frame()
		line1.set_ydata(frame.ch1)
		line2.set_ydata(frame.ch2)
		line1.set_xdata(range(1024))
		line2.set_xdata(range(1024))

		plt.draw()
finally:
	m.close()

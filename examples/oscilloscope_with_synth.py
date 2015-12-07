from pymoku import Moku, FrameTimeout
from pymoku.instruments import *
import time, logging

import matplotlib
import matplotlib.pyplot as plt

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.DEBUG)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku('192.168.1.104')

i = m.discover_instrument()

if i is None or i.type != 'oscilloscope':
	print "No or wrong instrument deployed"
	i = Oscilloscope()
	m.attach_instrument(i)
else:
	print "Attached to existing Oscilloscope"

i.set_defaults()
i.set_buffer_length(4)

i.synth_squarewave(1, 1.0, 1, risetime=0.1, falltime=0.1, duty=0.4)
i.synth_sinewave(2, 0.5, 2)

i.commit()

line1, = plt.plot([])
line2, = plt.plot([])
plt.ion()
plt.show()
plt.grid(b=True)
plt.ylim([-2000, 2000]) # TODO: Get these from the instrument
plt.xlim([0,1024])

try:
	last = 0
	while True:
		try:
			frame = i.get_frame(timeout=0.1)
		except FrameTimeout:
			time.sleep(0.1)
			continue

		plt.pause(0.001)
		line1.set_ydata(frame.ch1)
		line2.set_ydata(frame.ch2)
		line1.set_xdata(range(1024))
		line2.set_xdata(range(1024))

		plt.draw()
finally:
	m.close()

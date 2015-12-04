from pymoku import Moku
from pymoku.instruments import *
import time, logging

import matplotlib
import matplotlib.pyplot as plt

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.DEBUG)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku.get_by_name('Aqua')
print m._ip
i = m.discover_instrument()

if i is None or i.type != 'phasemeter':
	print "No or wrong instrument deployed"
	i = PhaseMeter()
	m.attach_instrument(i)
else:
	print "Attached to existing Phase Meter"

i.set_defaults()
i.set_buffer_length(4)

# i.render_mode = RDR_CUBIC #TODO: Support other
i.pretrigger = 0
i.render_deci = 1.0
i.offset = 500
i.render_deci_alt = i.render_deci
i.offset_alt = i.offset
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
		frame = i.get_frame(timeout=10.0)

		plt.pause(0.001)
		line1.set_ydata(frame.ch1)
		line2.set_ydata(frame.ch2)
		line1.set_xdata(range(1024))
		line2.set_xdata(range(1024))

		# plt.draw()
finally:
	m.close()

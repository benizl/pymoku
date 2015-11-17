from pymoku import Moku, ValueOutOfRangeException
from pymoku.instruments import *
import time, logging

import matplotlib
import matplotlib.pyplot as plt

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.DEBUG)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku.get_by_name("Aqua")

i = m.discover_instrument()

if i is None or i.type != 'signal_generator':
	print "No or wrong instrument deployed"
	i = SignalGenerator()
	m.attach_instrument(i)
else:
	print "Attached to existing Signal Generator"

i.set_defaults()

i.out1_enable = True
i.out1_frequency = 10000
i.out1_amplitude = 1
i.out1_waveform = SG_WAVE_SINE
i.commit()

try:
	while True:
		try:
			i.out1_offset += 0.05
		except ValueOutOfRangeException:
			i.out1_offset = -1

		print i.out1_offset

		i.commit()
finally:
	m.close()

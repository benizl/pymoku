from pymoku import Moku
from pymoku.instruments import *
import time, logging

import matplotlib
import matplotlib.pyplot as plt

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.DEBUG)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku('10.0.1.4')

i = m.discover_instrument()

if i is None or i.type != 'phasemeter':
	print "No or wrong instrument deployed"
	i = PhaseMeter()
	m.attach_instrument(i)
else:
	print "Attached to existing Phase Meter"

i.set_defaults()
i.set_buffer_length(4)

i.init_freq_ch1 = 10 * 10e6
i.init_freq_ch2 = 10 * 10e6
i.control_gain = 100
i.control_shift = 0
i.framerate = 10 #TODO should remove this when we figure out network buffering

i.commit()

t = [0.1 * x for x in range(100)]

plt.subplot(311)
ch1_freq = [0x00] * len(t)
ch2_freq = [0x00] * len(t)
freq_line1, = plt.plot(t, ch1_freq)
# freq_line2, = plt.plot(t, ch2_freq)
plt.grid(b=True)
# plt.ylim([-2**47, 2**47])
plt.ylim([-5e6, 5e6])
plt.xlim([0, t[-1]*1.1])
plt.ylabel("Frequency")

plt.subplot(312)
ch1_I = [0x00] * len(t)
ch1_Q = [0x00] * len(t)
ch2_I = [0x00] * len(t)
ch2_Q = [0x00] * len(t)
I_line1, = plt.plot(t, ch1_I)
# I_line2, = plt.plot(t, ch2_Q)
Q_line1, = plt.plot(t, ch1_I)
# Q_line2, = plt.plot(t, ch2_Q)
plt.grid(b=True)
# plt.ylim([-2**31, 2**31])
plt.ylim([-10e6, 10e6])
plt.xlim([0, t[-1]*1.1])
plt.ylabel("I & Q")

plt.subplot(313)
ch1_phase = [0x00] * len(t)
ch2_phase = [0x00] * len(t)
phase_line1, = plt.plot(t, ch1_phase)
# phase_line2, = plt.plot(t, ch2_phase)
plt.grid(b=True)
plt.ylim([-2**47, 2**47])
# plt.ylim([-5e10, 5e10])
plt.xlim([0, t[-1]*1.1])
plt.ylabel("Phase")

plt.ion()
plt.show()

import sys
try:
	last = 0
	while True:
		frame = i.get_frame(timeout=10.0)

		plt.pause(0.001)

		ch1_freq = ch1_freq[1:] + [frame.frequency1]
		ch1_I = ch1_I[1:] + [frame.I1]
		ch1_Q = ch1_Q[1:] + [frame.Q1]

		freq_line1.set_ydata(ch1_freq)
		I_line1.set_ydata(ch1_I)
		Q_line1.set_ydata(ch1_Q)

		# ch2_freq = ch2_freq[1:] + [frame.frequency2]
		# freq_line2.set_ydata(ch2_freq)
		# plt.subplot(311)
		# plt.autoscale(True, 'y')


		# ch2_Q = ch2_Q[1:] + [frame.Q1]
		# ch2_Q = ch2_Q[1:] + [frame.Q2]
		# I_line2.set_ydata(ch2_I)
		# Q_line2.set_ydata(ch2_Q)

		ch1_phase = ch1_phase[1:] + [frame.phase1]
		# ch2_phase = ch2_phase[1:] + [frame.phase2]
		phase_line1.set_ydata(ch1_phase)
		# phase_line2.set_ydata(ch2_phase)

		plt.draw()
finally:
	m.close()

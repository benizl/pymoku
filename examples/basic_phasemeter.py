from pymoku import Moku
from pymoku.instruments import *
import time, logging

import matplotlib
import matplotlib.pyplot as plt

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.DEBUG)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku('192.168.1.114')

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

i.commit()

t = range(1024)

plt.subplot(311)
ch1_freq = [0x00] * 1024
ch2_freq = [0x00] * 1024
freq_line1, = plt.plot(t, ch1_freq)
freq_line2, = plt.plot(t, ch2_freq)
plt.grid(b=True)
plt.ylim([-2**47, 2**47])
plt.xlim([0,1050])
plt.ylabel("Frequency")

plt.subplot(312)
ch1_amp = [0x00] * 1024
ch2_amp = [0x00] * 1024
amp_line1, = plt.plot(t, ch1_amp)
amp_line2, = plt.plot(t, ch2_amp)
plt.grid(b=True)
plt.ylim([-2**15, 2**15])
plt.xlim([0,1050])
plt.ylabel("Amplitude")

plt.subplot(313)
ch1_phase = [0x00] * 1024
ch2_phase = [0x00] * 1024
phase_line1, = plt.plot(t, ch1_phase)
phase_line2, = plt.plot(t, ch2_phase)
plt.grid(b=True)
plt.ylim([-2**47, 2**47])
plt.xlim([0,1050])
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
		ch2_freq = ch2_freq[1:] + [frame.frequency2]
		freq_line1.set_ydata(ch1_freq)
		freq_line2.set_ydata(ch2_freq)

		ch1_amp = ch1_amp[1:] + [frame.amplitude1]
		ch2_amp = ch2_amp[1:] + [frame.amplitude2]
		amp_line1.set_ydata(ch1_amp)
		amp_line2.set_ydata(ch2_amp)

		ch1_phase = ch1_phase[1:] + [frame.phase1]
		ch2_phase = ch2_phase[1:] + [frame.phase2]
		phase_line1.set_ydata(ch1_phase)
		phase_line2.set_ydata(ch2_phase)

		plt.draw()
finally:
	m.close()

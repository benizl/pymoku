#
# pymoku example: Oscilloscope with Waveform Synthesizer
#
# This example shows how to use the waveform synthesizer embedded within
# the Oscilloscope instrument. It also has more advanced plotting, using
# the blit functions of Matplotlib to accelerate the drawing process so
# we can increase the frame rate.
#
# (c) 2015 Liquid Instruments Pty. Ltd.
#


from pymoku import Moku, FrameTimeout
from pymoku.instruments import *
import time, logging

import matplotlib
import matplotlib.pyplot as plt

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
logging.getLogger('pymoku').setLevel(logging.DEBUG)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku.get_by_name('example')

i = m.discover_instrument()

if i is None or i.type != 'oscilloscope':
	print("No or wrong instrument deployed")
	i = Oscilloscope()
	m.attach_instrument(i)
else:
	print("Attached to existing Oscilloscope")

# Channe 1: 1Vp-p Square Wave, 1Hz, 40% duty cycle with 10% slew rate limit on both edges
i.synth_squarewave(1, 1.0, 1, risetime=0.1, falltime=0.1, duty=0.4)

# Channel 2: 0.5Vp-p Sine Wave, 2Hz.
i.synth_sinewave(2, 0.5, 2)

# The default is 10fps but the blitting below means we can actually
# run much faster.
i.framerate = 24

# Atomically apply all the settings above.
i.commit()


fig, ax = plt.subplots(1, 1)

# Re-capture the background box every time the window is resized.
def resize(event):
	global bg
	bg = fig.canvas.copy_from_bbox(ax.bbox)

fig.canvas.mpl_connect('resize_event', resize)

ax.grid(b=True)
ax.set_ylim([-10, 10])
ax.set_xlim([0,1024])
plt.ion()
plt.show(False)
plt.draw()

# Capture the background for the first time. This can be blit'd back in to place, saving
# all the time that would usually be spent redrawing axes, tick marks, grid lines and so on.
bg = fig.canvas.copy_from_bbox(ax.bbox)

line1, = ax.plot([])
line2, = ax.plot([])

try:
	frames = 0
	last = time.time()
	while True:
		try:
			frame = i.get_frame(timeout=0.1)
		except FrameTimeout:
			time.sleep(0.1)
			continue

		line1.set_data(list(range(len(frame.ch1))), frame.ch1)
		line2.set_data(list(range(len(frame.ch2))), frame.ch2)

		plt.pause(0.0001)

		fig.canvas.restore_region(bg)
		ax.draw_artist(line1)
		ax.draw_artist(line2)
		fig.canvas.blit(ax.bbox)

		frames += 1

		# Print FPS values against the current requested value (which is rounded to the
		# nearest achievable value to the above).
		if time.time() - last >= 1:
			print(frames, i.framerate)
			frames = 0
			last = time.time()
finally:
	plt.close(fig)
	m.close()

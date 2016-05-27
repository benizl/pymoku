import pytest
from pymoku import Moku
from pymoku.instruments import *

# Set up Moku with Oscilloscope instrument
m = Moku('10.0.1.17')
i = Oscilloscope()
m.attach_instrument(i)
i.set_defaults()
#i.synth_sinewave(1,1.0,2e6)
i.commit()

def test_trigger():

	def in_bounds(v, center, err):
		return abs(v - center) < abs(err)

	i.set_defaults()
	i.set_timebase(0,2e-6)
	i.set_trigger(OSC_TRIG_CH1, OSC_EDGE_RISING, 0.7, hysteresis=0, hf_reject = False, mode=OSC_TRIG_NORMAL)
	i.commit()
	print "Got here"
	frame = i.get_frame(timeout=5)
	print "Got frame length %d" % (len(frame.ch1))
	#assert 1 == 1
	print frame.ch1[0]
	assert in_bounds(frame.ch1[0], 0.7,0.1) == True #Frame trigger value in range of 0.7V?
	m.close()
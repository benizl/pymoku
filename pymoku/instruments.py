import sys

import _oscilloscope
import _frame_instrument

''' Preferred import point. Aggregates the separate instruments and helper classes
    to flatten the import heirarchy (e.g. pymoku.instruments.Oscilloscope rather
    than pymoku.instruments._oscilloscope.Oscilloscope)
'''
_this_module = sys.modules[__name__]

DataFrame = _frame_instrument.DataFrame

Oscilloscope = _oscilloscope.Oscilloscope

# Re-export all constants from Oscilloscope that start with OSC_
for attr, val in _oscilloscope.__dict__.iteritems():
	if attr.startswith('OSC_'):
		setattr(_this_module, attr, val)

id_table = {
	0: None,
	1: Oscilloscope,
}

# Plotly integration for the Moku:Lab Datalogger

# Copyright 2016 Liquid Instruments Pty. Ltd.

def init(moku, uname, api_key, str_id1, str_id2, npoints=100):
	settings = [
		('plotly.uname', uname),
		('plotly.api_key', api_key),
		('plotly.strid1', str_id1),
		('plotly.strid2', str_id2),
		('plotly.displaysize', str(npoints))
	]

	moku._set_properties(settings)

def url(moku):
	return moku._get_property_single('plotly.url')

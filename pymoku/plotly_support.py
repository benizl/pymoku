# Plotly integration for the Moku:Lab Datalogger

# Copyright 2016 Liquid Instruments Pty. Ltd.

from pymoku import InvalidOperationException

def init(moku, uname, api_key, str_id1, str_id2, npoints=100):
	settings = [
		('plotly.uname', uname),
		('plotly.api_key', api_key),
		('plotly.strid1', str_id1),
		('plotly.strid2', str_id2),
		('plotly.displaysize', str(npoints))
	]

	moku._set_properties(settings)

def stream_url(moku):
	return moku._get_property_single('plotly.url')

def plot_frame(dataframe):
	try:
		import plotly.plotly as ply
		import plotly.tools as ptls
		from plotly.graph_objs import *
	except ImportError:
		raise InvalidOperationException("Please install the Python plotly bindings")

	c1 = dataframe.ch1
	c2 = dataframe.ch2
	x = range(len(c1))

	t1 = Scatter(x=x, y=c1)
	t2 = Scatter(x=x, y=c2)

	layout = Layout(title="Moku:Lab Frame Grab")
	data = Data([t1, t2])

	fig = Figure(data=data, layout=layout)

	return ply.plot(fig)
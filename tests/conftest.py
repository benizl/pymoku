from pymoku import Moku
from pymoku.instruments import *
import pytest

def pytest_addoption(parser):
	parser.addoption("--ip", help="Serial number of the device to test against.")

@pytest.fixture(scope="module")
def conn_instr(request):
	'''
		Per test module setup function
	'''
	print "Connecting to Moku"
	ip = pytest.config.getoption("--ip")
	m = Moku(ip)

	i = Oscilloscope()
	m.attach_instrument(i)

	i.set_buffer_length(4)

	request.addfinalizer(m.close)
	return i

@pytest.fixture(scope="function")
def base_instr(conn_instr):
	'''
		Per test setup function
	'''
	print "Setting defaults."
	conn_instr.set_defaults()
	return conn_instr

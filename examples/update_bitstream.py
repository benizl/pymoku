from pymoku import Moku
import sys, logging

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
log = logging.getLogger()
log.setLevel(logging.DEBUG)

if len(sys.argv) != 3:
	print "Usage %s <ip> <bitstream>" % sys.argv[0]
	exit(1)

# Use Moku.get_by_serial() or get_by_name() if you don't know the IP
m = Moku(sys.argv[1])

try:
	m.load_bitstream(sys.argv[2])
except:
	log.exception("Update Failed")
finally:
	m.close()

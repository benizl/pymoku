from pymoku import Moku
import sys, logging
import os.path

logging.basicConfig(format='%(asctime)s:%(name)s:%(levelname)s::%(message)s')
log = logging.getLogger()
log.setLevel(logging.DEBUG)

if len(sys.argv) != 3:
	print("Usage %s <ip> <package.hgp>" % sys.argv[0])
	exit(1)

m = Moku(sys.argv[1])

f = sys.argv[2]
fsha = f + '.sha256'

if not f.endswith('.hgp'):
	log.error("Not an HGP file")
	exit(1)

if not os.path.exists(fsha):
	log.warning("No signing information")

try:
	m.load_persistent(f)

	if os.path.exists(fsha):
		m.load_persistent(fsha)
finally:
	m.close()

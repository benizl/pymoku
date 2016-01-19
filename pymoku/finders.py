
import pybonjour, select, socket, time

class BonjourFinder(object):
	def __init__(self):
		self.moku_list = []
		self.resolved = []
		self.queried = []
		self.pversion = ''
		self.timeout = 5

	def query_record_callback(self, sdRef, flags, interfaceIndex, errorCode, fullname,
							  rrtype, rrclass, rdata, ttl):
		if errorCode == pybonjour.kDNSServiceErr_NoError:
			self.moku_list.append(socket.inet_ntoa(rdata))
			self.queried.append(True)


	def resolve_callback(self, sdRef, flags, interfaceIndex, errorCode, fullname,
						 hosttarget, port, txtRecord):
		if errorCode != pybonjour.kDNSServiceErr_NoError:
			return

		hw, pver, dummy = hosttarget.split('_')
		if hw != 'moku10' or pver != self.pversion:
			return

		query_sdRef = \
			pybonjour.DNSServiceQueryRecord(interfaceIndex = interfaceIndex,
											fullname = hosttarget,
											rrtype = pybonjour.kDNSServiceType_A,
											callBack = self.query_record_callback)

		try:
			while not self.queried:
				ready = select.select([query_sdRef], [], [], self.timeout)
				if query_sdRef not in ready[0]:
					break
				pybonjour.DNSServiceProcessResult(query_sdRef)
			else:
				self.queried.pop()
		finally:
			query_sdRef.close()

		self.resolved.append(True)


	def browse_callback(self, sdRef, flags, interfaceIndex, errorCode, serviceName,
						regtype, replyDomain):
		if errorCode != pybonjour.kDNSServiceErr_NoError:
			return

		if not (flags & pybonjour.kDNSServiceFlagsAdd):
			return

		resolve_sdRef = pybonjour.DNSServiceResolve(0,
													interfaceIndex,
													serviceName,
													regtype,
													replyDomain,
													self.resolve_callback)

		try:
			while not self.resolved:
				ready = select.select([resolve_sdRef], [], [], self.timeout)
				if resolve_sdRef not in ready[0]:
					break
				pybonjour.DNSServiceProcessResult(resolve_sdRef)
			else:
				self.resolved.pop()
		finally:
			resolve_sdRef.close()


	def find_all(self, protocol_version='6', timeout=5):
		self.pversion = protocol_version
		self.timeout = timeout
		self.moku_list = []

		browse_sdRef = pybonjour.DNSServiceBrowse(regtype = '_moku._tcp',
												  callBack = self.browse_callback)

		start = time.time()
		try:
			try:
				while time.time() - start < timeout:
					ready = select.select([browse_sdRef], [], [], self.timeout)
					if browse_sdRef in ready[0]:
						pybonjour.DNSServiceProcessResult(browse_sdRef)
			except KeyboardInterrupt:
				pass
		finally:
			browse_sdRef.close()

		return self.moku_list

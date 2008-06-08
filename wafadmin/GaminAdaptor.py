#!/usr/bin/env python
# encoding: utf-8
# Oscar Blumberg 2006 (nael)
# Matthias Jahn <jahn.matthias@freenet.de>

"""Depends on python gamin and on gamin demon"""

import select, errno
try:
	import gamin
except ImportError:
	support = False
else:
	# check if gamin runs and accepts connections
	test = gamin.WatchMonitor()
	test.disconnect()
	test = None
	support = True

import DirWatch

class GaminAdaptor(DirWatch.adaptor):
	def __init__(self, eventHandler):
		DirWatch.adaptor.__init__(self, event_handler)

		self._gamin = gamin.WatchMonitor()
		self._watchHandler = {} # {name : famId}

	def __del__(self):
		"""clean remove"""
		if self._gamin:
			for handle in self._watchHandler.keys():
				self.stop_watch(handle)
			self._gamin.disconnect()
			self._gamin = None

	def check_init(self):
		"""is gamin connected"""
		if self._gamin == None:
			raise "gamin not init"

	def _code2str(self, event):
		"""convert event numbers to string"""
		gaminCodes = {
			1:"changed",
			2:"deleted",
			3:"StartExecuting",
			4:"StopExecuting",
			5:"created",
			6:"moved",
			7:"acknowledge",
			8:"exists",
			9:"endExist"
		}
		try:
			return gaminCodes[event]
		except KeyError:
			return "unknown"

	def _eventhandler_helper(self, pathName, event, idxName):
		"""local eventhandler helps to convert event numbers to string"""
		self._eventHandler(pathName, self._code2str(event), idxName)

	def watch_directory(self, name, idxName):
		self.check_init()
		if self._watchHandler.has_key(name):
			raise "dir already watched"
		# set gaminId
		self._watchHandler[name] = self._gamin.watch_directory(name, self._eventhandler_helper, idxName)
		return self._watchHandler[name]

	def watch_file(self, name, idxName):
		self.check_init()
		if self._watchHandler.has_key(name):
			raise "file already watched"
		# set famId
		self._watchHandler[name] = self._gamin.watch_directory(name, self._eventhandler_helper, idxName)
		return self._watchHandler[name]

	def stop_watch(self, name):
		self.check_init()
		if self._watchHandler.has_key(name):
			self._gamin.stop_watch(name)
			del self._watchHandler[name]
		return None

	def wait_for_event(self):
		self.check_init()
		try:
			select.select([self._gamin.get_fd()], [], [])
		except select.error, er:
			errnumber, strerr = er
			if errnumber != errno.EINTR:
				raise strerr

	def event_pending(self):
		self.check_init()
		return self._gamin.event_pending()

	def handle_events(self):
		self.check_init()
		self._gamin.handle_events()


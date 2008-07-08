#!/usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005 (ita)

"Execute the tasks"

import sys, random, time, threading, Queue, traceback
import Build, Utils, Logs, Options
import pproc as subprocess
from Logs import debug, error
from Constants import *

g_quiet = 0
"do not output anything"

def print_log(msg, nl='\n'):
	f = Build.bld.log
	if f:
		f.write(msg)
		f.write(nl)
		f.flush()

def printout(s):
	if not Build.bld.log:
		sys.stdout.write(s)
		sys.stdout.flush()
	print_log(s, nl='')

def exec_command(s, shell=1):
	debug('runner: system command -> %s' % s)
	log = Build.bld.log
	if log or Logs.verbose: printout(s+'\n')
	proc = subprocess.Popen(s, shell=shell, stdout=log, stderr=log)
	stat = proc.wait()
	if stat & 0xff: return stat | 0x80
	return stat >> 8

if sys.platform == "win32":
	old_log = exec_command
	def exec_command(s, shell=1):
		# TODO very long command-lines are unlikely to be used in the configuration
		if len(s) < 2000: return old_log(s, shell=shell)

		log = Build.bld.log
		if log or Logs.verbose: printout(s+'\n')
		startupinfo = subprocess.STARTUPINFO()
		startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		proc = subprocess.Popen(s, shell=False, startupinfo=startupinfo)
		stat = proc.wait()
		if stat & 0xff: return stat | 0x80
		return stat >> 8

class Serial(object):
	def __init__(self, bld):
		self.manager = bld.task_manager
		self.outstanding = []

		# progress bar
		self.total = self.manager.total()
		self.processed = 0
		self.error = 0

		self.switchflag = 1 # postpone
		# self.manager.debug()

	# warning, this one is recursive ..
	def get_next(self):
		if self.outstanding:
			t = self.outstanding.pop(0)
			self.processed += 1
			return t

		# handle case where only one wscript exist
		# that only install files
		if not self.manager.groups:
			return None

		(_, self.outstanding) = self.manager.get_next_set()
		if not self.outstanding: return None

		return self.get_next()

	def postpone(self, tsk):
		self.processed -= 1
		self.switchflag *= -1
		# this actually shuffle the list
		if self.switchflag>0: self.outstanding.insert(0, tsk)
		else:                 self.outstanding.append(tsk)

	def start(self):
		global g_quiet
		debug('runner: Serial start called')
		while 1:
			# get next Task
			tsk = self.get_next()
			if tsk is None: break

			if Logs.verbose: debug('runner: retrieving %r' % tsk)

			if tsk.runnable_status() == ASK_LATER:
				debug('runner: postponing %r' % tsk)
				self.postpone(tsk)
				#tsk = None
				continue
			# # =======================

			#debug("m_sig is "+str(tsk.sig), 'runner')
			#debug("obj output m_sig is "+str(tsk.outputs[0].get_sig()), 'runner')

			#continue
			if tsk.runnable_status() == SKIP_ME:
				tsk.hasrun = SKIPPED
				self.manager.add_finished(tsk)
				continue

			# display the command that we are about to run
			if not g_quiet:
				tsk.position = (self.processed, self.total)
				printout(tsk.display())

			# run the command
			if tsk.__class__.stat: tsk.__class__.stat()
			else: ret = tsk.run()
			self.manager.add_finished(tsk)

			# non-zero means something went wrong
			if ret:
				self.error = 1
				tsk.hasrun = CRASHED
				tsk.err_code = ret
				if Options.options.keep: continue
				else: return -1

			try:
				tsk.post_run()
			except OSError:
				self.error = 1
				tsk.hasrun = MISSING
				if Options.options.keep: continue
				else: return -1
			else:
				tsk.hasrun = SUCCESS

		if self.error:
			return -1

class TaskConsumer(threading.Thread):
	def __init__(self, i, m):
		threading.Thread.__init__(self)
		self.setDaemon(1)
		self.id     = i
		self.master = m
		self.start()

	def run(self):
		m = self.master

		while 1:
			tsk = m.ready.get()
			if m.failed and not m.running:
				m.out.put(tsk)
				continue

			try:
				printout(tsk.display())
				if tsk.__class__.stat: tsk.__class__.stat()
				else: ret = tsk.run()
			except Exception:
				exc_type, exc_value, tb = sys.exc_info()
				traceback.print_exception(exc_type, exc_value, tb)
				ret = CRASHED

			if ret:
				tsk.err_code = ret
				tsk.hasrun = CRASHED
			else:
				try:
					tsk.post_run()
				except OSError:
					tsk.hasrun = MISSING
				else:
					tsk.hasrun = SUCCESS
			if tsk.hasrun != SUCCESS: # TODO for now, do no keep running in parallel  and not Options.options.keep:
				m.failed = 1

			m.out.put(tsk)

class Parallel(object):
	"""
	The following is a small scheduler for making as many tasks available to the consumer threads
	It uses the serial shuffling system
	"""
	def __init__(self, bld, j=2):

		# number of consumers
		self.numjobs = j

		self.manager = bld.task_manager

		self.total = self.manager.total()

		# tasks waiting to be processed - IMPORTANT
		self.outstanding = []
		self.maxjobs = 100

		# tasks that are awaiting for another task to complete
		self.frozen = []

		# tasks waiting to be run by the consumers
		self.ready = Queue.Queue(0)
		self.out = Queue.Queue(0)

		self.count = 0 # tasks not in the producer area
		self.failed = 0 # some task has failed
		self.running = 0 # keep running ?
		self.processed = 0 # progress indicator

	def start(self):
		self.consumers = [TaskConsumer(i, self) for i in range(self.numjobs)]

		# the current group
		#group = None

		def get_out():
			self.manager.add_finished(self.out.get())
			self.count -= 1

		lastfailput = 0

		# iterate over all tasks at most one time for each task run
		penalty = 0
		maxjobs = 0
		#loop=0
		while 1:
			#loop += 1
			if self.failed and not self.running:
				while self.count > 0: get_out()
				if self.failed: return -1

			if 1 == maxjobs:
				# TODO
				while self.count > 0: get_out()
			else:
				# not too many jobs in the queue
				while self.count > self.numjobs + 10: get_out()

			# empty the returned tasks as much as possible
			while not self.out.empty(): get_out()

			if not self.outstanding:
				if self.count > 0: get_out()
				self.outstanding = self.frozen
				self.frozen = []
			if not self.outstanding:
				while self.count > 0: get_out()
				(maxjobs, self.outstanding) = self.manager.get_next_set()
				#if self.outstanding: random.shuffle(self.outstanding)
				if maxjobs is None: break

			# consider the next task
			tsk = self.outstanding.pop(0)
			if tsk.runnable_status() == ASK_LATER:
				if random.randint(0,1): self.frozen.insert(0, tsk)
				else: self.frozen.append(tsk)
			else:
				self.processed += 1
				if tsk.runnable_status() == SKIP_ME:
					tsk.hasrun = SKIPPED
					self.manager.add_finished(tsk)
					continue
				tsk.position = (self.processed, self.total)
				self.count += 1
				self.ready.put(tsk)
		#print loop

def get_instance(bld, njobs):
	if njobs <= 1: executor = Serial(bld)
	else: executor = Parallel(bld, njobs)
	return executor


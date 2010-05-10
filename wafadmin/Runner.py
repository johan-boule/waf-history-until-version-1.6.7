#!/usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005-2008 (ita)

"Execute the tasks"

import os, shutil, sys, re, random, time, threading, traceback, datetime
try:
	from queue import Queue
except:
	from Queue import Queue
import Build, Utils, Node, Logs, Options
from Logs import debug, warn, error
from Base import WafError
from Constants import *
from collections import defaultdict
from Utils import md5


GAP = 15

run_old = threading.Thread.run
def run(*args, **kwargs):
	try:
		run_old(*args, **kwargs)
	except (KeyboardInterrupt, SystemExit):
		raise
	except:
		sys.excepthook(*sys.exc_info())
threading.Thread.run = run

class TaskConsumer(threading.Thread):
	ready = Queue(0)
	consumers = []

	def __init__(self):
		threading.Thread.__init__(self)
		self.setDaemon(1)
		self.start()

	def run(self):
		try:
			self.loop()
		except:
			pass

	def loop(self):
		while 1:
			tsk = TaskConsumer.ready.get()
			m = tsk.master
			if m.stop:
				m.out.put(tsk)
				continue

			try:
				tsk.generator.bld.printout(tsk.display())
				if tsk.__class__.stat: ret = tsk.__class__.stat(tsk)
				# actual call to task's run() function
				else: ret = tsk.call_run()
			except Exception as e:
				tsk.err_msg = Utils.ex_stack()
				tsk.hasrun = EXCEPTION

				# TODO cleanup
				m.error_handler(tsk)
				m.out.put(tsk)
				continue

			if ret:
				tsk.err_code = ret
				tsk.hasrun = CRASHED
			else:
				try:
					tsk.post_run()
				except Base.WafError:
					pass
				except Exception:
					tsk.err_msg = Utils.ex_stack()
					tsk.hasrun = EXCEPTION
				else:
					tsk.hasrun = SUCCESS
			if tsk.hasrun != SUCCESS:
				m.error_handler(tsk)

			m.out.put(tsk)

class Parallel(object):
	"""
	keep the consumer threads busy, and avoid consuming cpu cycles
	when no more tasks can be added (end of the build, etc)
	"""
	def __init__(self, bld, j=2):

		# number of consumers
		self.numjobs = j

		self.manager = bld.task_manager
		self.manager.current_group = 0

		self.total = self.manager.total()

		# tasks waiting to be processed - IMPORTANT
		self.outstanding = []
		self.maxjobs = MAXJOBS

		# tasks that are awaiting for another task to complete
		self.frozen = []

		# tasks waiting to be run by the consumers
		self.out = Queue(0)

		self.count = 0 # tasks not in the producer area

		self.processed = 1 # progress indicator

		self.stop = False # error condition to stop the build
		self.error = False # error flag

	def get_next(self):
		"override this method to schedule the tasks in a particular order"
		if not self.outstanding:
			return None
		return self.outstanding.pop(0)

	def postpone(self, tsk):
		"override this method to schedule the tasks in a particular order"
		# TODO consider using a deque instead
		if random.randint(0, 1):
			self.frozen.insert(0, tsk)
		else:
			self.frozen.append(tsk)

	def refill_task_list(self):
		"called to set the next group of tasks"

		while self.count > self.numjobs + GAP or self.count >= self.maxjobs:
			self.get_out()

		while not self.outstanding:
			if self.count:
				self.get_out()

			if self.frozen:
				self.outstanding += self.frozen
				self.frozen = []
			elif not self.count:
				self.outstanding += self.manager.get_next_set()
				break

	def get_out(self):
		"the tasks that are put to execute are all collected using get_out"
		ret = self.out.get()
		self.manager.add_finished(ret)
		if not self.stop and getattr(ret, 'more_tasks', None):
			self.outstanding += ret.more_tasks
			self.total += len(ret.more_tasks)
		self.count -= 1

	def error_handler(self, tsk):
		"by default, errors make the build stop (not thread safe so be careful)"
		if not Options.options.keep:
			self.stop = True
		self.error = True

	def start(self):
		"execute the tasks"

		while not self.stop:

			self.refill_task_list()

			# consider the next task
			tsk = self.get_next()
			if not tsk:
				if self.count:
					# tasks may add new ones after they are run
					continue
				else:
					# no tasks to run, no tasks running, time to exit
					break

			if tsk.hasrun:
				# if the task is marked as "run", just skip it
				self.processed += 1
				self.manager.add_finished(tsk)
				continue

			try:
				st = tsk.runnable_status()
			except Exception as e:
				tsk.err_msg = Utils.ex_stack()
				tsk.hasrun = EXCEPTION
				self.processed += 1
				self.error_handler(tsk)
				self.manager.add_finished(tsk)
				continue

			if st == ASK_LATER:
				self.postpone(tsk)
			elif st == SKIP_ME:
				self.processed += 1
				tsk.hasrun = SKIPPED
				self.manager.add_finished(tsk)
			else:
				# run me: put the task in ready queue
				tsk.position = (self.processed, self.total)
				self.count += 1
				tsk.master = self
				TaskConsumer.ready.put(tsk)
				self.processed += 1

				# create the consumer threads only if there is something to consume
				if not TaskConsumer.consumers:
					TaskConsumer.consumers = [TaskConsumer() for i in range(self.numjobs)]

		# self.count represents the tasks that have been made available to the consumer threads
		# collect all the tasks after an error else the message may be incomplete
		while self.error and self.count:
			self.get_out()

		#print loop
		assert (self.count == 0 or self.stop)

class TaskManager(object):
	"""The manager is attached to the build context, it holds a list of TaskGroup"""
	def __init__(self):
		self.groups = []
		self.tasks_done = []
		self.current_group = 0
		self.groups_names = {}

	def get_next_set(self):
		"""return the next set of tasks to execute
		the first parameter is the maximum amount of parallelization that may occur"""

		while self.current_group < len(self.groups):
			ret = self.groups[self.current_group].get_next_set()
			if ret:
				return ret
			else:
				self.groups[self.current_group].process_install()
				self.current_group += 1
		return []

	def add_group(self, name=None, set=True):
		#if self.groups and not self.groups[0].tasks:
		#	error('add_group: an empty group is already present')
		g = TaskGroup()

		if name and name in self.groups_names:
			error('add_group: name %s already present' % name)
		self.groups_names[name] = g
		self.groups.append(g)
		if set:
			self.current_group = len(self.groups) - 1

	def set_group(self, idx):
		if isinstance(idx, str):
			g = self.groups_names[idx]
			for x in range(len(self.groups)):
				if id(g) == id(self.groups[x]):
					self.current_group = x
		else:
			self.current_group = idx

	def add_task_gen(self, tgen):
		if not self.groups:
			self.add_group()
		self.groups[self.current_group].tasks_gen.append(tgen)

	def add_task(self, task):
		if not self.groups:
			self.add_group()
		self.groups[self.current_group].tasks.append(task)

	def total(self):
		total = 0
		for group in self.groups:
			total += len(group.tasks)
		return total

	def add_finished(self, tsk):
		self.tasks_done.append(tsk)
		bld = tsk.generator.bld
		if bld.is_install:
			f = None
			if 'install' in tsk.__dict__:
				f = tsk.__dict__['install']
				# install=0 to prevent installation
				if f: f(tsk)
			else:
				tsk.install()

class TaskGroup(object):
	"the compilation of one group does not begin until the previous group has finished (in the manager)"
	def __init__(self):
		self.tasks = [] # this list will be consumed
		self.tasks_gen = []

		self.cstr_groups = defaultdict(list) # tasks having equivalent constraints
		self.cstr_order = defaultdict(set) # partial order between the cstr groups
		self.temp_tasks = [] # tasks put on hold
		self.post_funs = []

	def reset(self):
		"clears the state of the object (put back the tasks into self.tasks)"
		for x in self.cstr_groups:
			self.tasks += self.cstr_groups[x]
		self.tasks = self.temp_tasks + self.tasks
		self.temp_tasks = []
		self.cstr_groups = defaultdict(list)
		self.cstr_order = defaultdict(set)

	def process_install(self):
		for (f, k, kw) in self.post_funs:
			f(*k, **kw)

	def make_cstr_groups(self):
		"join the tasks that have similar constraints"
		self.cstr_groups = defaultdict(list)
		for x in self.tasks:
			h = x.hash_constraints()
			self.cstr_groups[h].append(x)

	def set_order(self, a, b):
		self.cstr_order[a].add(b)

	def compare_exts(self, t1, t2):
		"extension production"
		x = "ext_in"
		y = "ext_out"
		in_ = t1.attr(x, ())
		out_ = t2.attr(y, ())
		for k in in_:
			if k in out_:
				return -1
		in_ = t2.attr(x, ())
		out_ = t1.attr(y, ())
		for k in in_:
			if k in out_:
				return 1
		return 0

	def compare_partial(self, t1, t2):
		"partial relations after/before"
		m = "after"
		n = "before"
		name = t2.__class__.__name__
		if name in Utils.to_list(t1.attr(m, ())): return -1
		elif name in Utils.to_list(t1.attr(n, ())): return 1
		name = t1.__class__.__name__
		if name in Utils.to_list(t2.attr(m, ())): return 1
		elif name in Utils.to_list(t2.attr(n, ())): return -1
		return 0

	def extract_constraints(self):
		"extract the parallelization constraints from the tasks with different constraints"
		keys = list(self.cstr_groups.keys())
		max = len(keys)
		# hopefully the length of this list is short
		for i in range(max):
			t1 = self.cstr_groups[keys[i]][0]
			for j in range(i + 1, max):
				t2 = self.cstr_groups[keys[j]][0]

				# add the constraints based on the comparisons
				val = (self.compare_exts(t1, t2)
					or self.compare_partial(t1, t2)
					)
				if val > 0:
					self.set_order(keys[i], keys[j])
				elif val < 0:
					self.set_order(keys[j], keys[i])

	def get_next_set(self):
		"next list of tasks that may be executed in parallel"

		if not getattr(self, 'ready_iter', None):

			# if the constraints are set properly (ext_in/ext_out, before/after)
			# the method set_file_constraints is not necessary (can be 15% penalty on no-op rebuilds)
			#
			# the constraint extraction thing is splitting the tasks by groups of independent tasks that may be parallelized
			# this is slightly redundant with the task manager groups
			#
			# if the tasks have only files, set_file_constraints is required but extract_constraints is not necessary
			#
			self.set_file_constraints(self.tasks)
			self.make_cstr_groups()
			self.extract_constraints()

			self.ready_iter = True

		keys = self.cstr_groups.keys()

		unconnected = []
		remainder = []

		for u in keys:
			for k in self.cstr_order.values():
				if u in k:
					remainder.append(u)
					break
			else:
				unconnected.append(u)

		toreturn = []
		for y in unconnected:
			toreturn.extend(self.cstr_groups[y])

		# remove stuff only after
		for y in unconnected:
				try: self.cstr_order.__delitem__(y)
				except KeyError: pass
				self.cstr_groups.__delitem__(y)

		if not toreturn:
			self.ready_iter = False
			if remainder:
				raise WafError("Circular order constraint detected %r" % remainder)

		return toreturn

	def set_file_constraints(self, tasks):
		"will set the run_after constraints on all tasks (may cause a slowdown with lots of tasks)"
		ins = {}
		outs = {}
		for x in tasks:
			for a in getattr(x, 'inputs', []):
				try:
					ins[id(a)].append(x)
				except KeyError:
					ins[id(a)] = [x]
			for a in getattr(x, 'outputs', []):
				try:
					outs[id(a)].append(x)
				except KeyError:
					outs[id(a)] = [x]

		links = set(ins.keys()).intersection(outs.keys())
		for k in links:
			for a in ins[k]:
				for b in outs[k]:
					a.set_run_after(b)


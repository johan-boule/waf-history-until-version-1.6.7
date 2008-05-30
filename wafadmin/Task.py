#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005-2008 (ita)

"""
Running tasks in parallel is a simple problem, but in practice it is more complicated:
* dependencies discovered during the build (dynamic task creation)
* dependencies discovered after files are compiled
* the amount of tasks and dependencies (graph size) can be huge

This is why the dependency management is split on three different levels:
1. groups of tasks that run all after another group of tasks
2. groups of tasks that can be run in parallel
3. tasks that can run in parallel, but with possible unknown ad-hoc dependencies

The point #1 represents a strict sequential order between groups of tasks, for example a compiler is produced
and used to compile the rest, whereas #2 and #3 represent partial order constraints where #2 applies to the kind of task
and #3 applies to the task instances.

#1 is held by the task manager (ordered list of TaskGroups)
#2 is held by the task groups (constraint extraction and topological sort) and the actions (priorities)
#3 is held by the tasks individually (attribute m_run_after),
   and the scheduler (Runner.py) use Task::may_start to reorder the tasks


To simplify the system a little bit, the part #2 only applies to dependencies between actions,
and priorities or order constraints can only be applied to actions, not to tasks anymore

"""

import os, types, shutil, sys
from Utils import md5
import Params, Action, Runner, Common, Scan
from Params import debug, error, warning
from Constants import *

g_algotype = NORMAL
"""
TODO (not implemented)
Enable different kind of dependency algorithms:
1 make groups: first compile all cpps and then compile all links (NORMAL)
2 parallelize all (each link task run after its dependencies) (MAXPARALLEL)
3 like 1 but provide additional constraints for the parallelization (MAXJOBS)

In theory 1. will be faster than 2 for waf, but might be slower for builds
The scheme 2 will not allow for running tasks one by one so it can cause disk thrashing on huge builds
"""

class TaskManager(object):
	"""The manager is attached to the build object, it holds a list of TaskGroup
	Each TaskGroup contains a map(priority, list of tasks)"""
	def __init__(self):
		self.groups = []
		self.idx = 0 # task counter, for debugging (allocating 5000 integers for nothing is a bad idea but well)
		self.tasks_done = []

		self.current_group = 0

	def get_next_set(self):
		"""return the next set of tasks to execute
		the first parameter is the maximum amount of parallelization that may occur"""
		ret = None
		while not ret and self.current_group < len(self.groups):
			ret = self.groups[self.current_group].get_next_set()
			if ret: return ret
			else: self.current_group += 1
		return (None, None)

	def add_group(self, name=''):
		if not name:
			size = len(self.groups)
			name = 'group-%d' % size
		if not self.groups:
			self.groups = [TaskGroup(name)]
			return
		if not self.groups[0].tasks:
			warning('add_group: an empty group is already present')
			return
		self.groups = self.groups + [TaskGroup(name)]
	def add_task(self, task):
		if not self.groups: self.add_group('group-0')
		task.m_idx = self.idx
		self.idx += 1
		self.groups[-1].add_task(task)
	def total(self):
		total = 0
		if not self.groups: return 0
		for group in self.groups:
			total += len(group.tasks)
			#for p in group.prio:
			#	total += len(group.prio[p])
		return total
	def debug(self):
		for i in self.groups:
			print "-----group-------", i.name
			for j in i.prio:
				print "prio: ", j, str(i.prio[j])
	def add_finished(self, tsk):
		self.tasks_done.append(tsk)
		# TODO we could install using threads here
		if Params.g_install and hasattr(tsk, 'install'):
			d = tsk.install

			if type(d) is types.FunctionType:
				d(tsk)
			elif type(d) is types.StringType:
				if not tsk.env()[d]: return
				lst = [a.relpath_gen(Params.g_build.m_srcnode) for a in tsk.m_outputs]
				Common.install_files(tsk.env()[d], '', lst, chmod=0644, env=tsk.env())
			else:
				if not d['var']: return
				lst = [a.relpath_gen(Params.g_build.m_srcnode) for a in tsk.m_outputs]
				if d.get('src', 0): lst += [a.relpath_gen(Params.g_build.m_srcnode) for a in tsk.m_inputs]
				# TODO ugly hack
				if d.get('as', ''):
					Common.install_as(d['var'], d['dir']+d['as'], lst[0], chmod=d.get('chmod', 0644), env=tsk.env())
				else:
					Common.install_files(d['var'], d['dir'], lst, chmod=d.get('chmod', 0644), env=tsk.env())

class TaskGroup(object):
	"A TaskGroup maps priorities (integers) to lists of tasks"
	def __init__(self, name):
		self.name = name
		self.tasks = [] # this list will be consumed

		self.cstr_groups = {} # tasks having equivalent constraints
		self.cstr_order = {} # partial order between the cstr groups
		self.temp_tasks = [] # tasks put on hold
		self.ready = 0

	def reset(self):
		"clears the state of the object (put back the tasks into self.tasks)"
		for x in self.cstr_groups:
			self.tasks += self.cstr_groups[x]
		self.tasks = self.temp_tasks + self.tasks
		self.temp_tasks = []
		self.cstr_groups = []
		self.cstr_order = {}
		self.ready = 0

	def prepare(self):
		"prepare the scheduling"
		self.ready = 1
		self.make_cstr_groups()
		self.extract_constraints()

	def get_next_set(self):
		"next list of tasks to execute using max job settings, returns (priority, task_list)"
		# TODO without -j, fallback to NORMAL
		if g_algotype == NORMAL:
			"this should be ready"
			tasks = self.tasks_in_parallel()
			if not tasks: return ()
			# in parallel mode, look at the parallelization constraint of the first item in the list
			# TODO this cannot work well, the first task may not be a linking
			try: maxjobs = tasks[0].m_action.maxjobs
			except (IndexError, AttributeError): maxjobs = sys.maxint
			return (maxjobs, tasks)
		elif g_algotype == JOBCONTROL:
			return self.tasks_by_max_jobs()
		elif g_algotype == MAXPARALLEL:
			return (sys.maxint, self.tasks_with_inner_constraints())
		else:
			pass

	def make_cstr_groups(self):
		"unite the tasks that have similar constraints"
		self.cstr_groups = {}
		for x in self.tasks:
			h = x.hash_constraints()
			try: self.cstr_groups[h].append(x)
			except KeyError: self.cstr_groups[h] = [x]

	def add_task(self, task):
		try: self.tasks.append(task)
		except KeyError: self.tasks = [task]

	def set_order(self, a, b):
		try: self.cstr_order[a].add(b)
		except KeyError: self.cstr_order[a] = set([b,])


	def compare_prios(self, t1, t2, a1, a2):
		x = "priority system (old)"
		p1 = getattr(t1, x, getattr(a1, x, None))
		p2 = getattr(t2, x, getattr(a2, x, None))

		if not p1 is None and not p2 is None:
			if p1 < p2:
				return 1
			elif p1 > p2:
				return -1
		return 0

	def compare_exts(self, t1, t2, a1, a2):
		"extension production"
		x = "in_exts"
		y = "out_exts"
		in_exts = getattr(t1, x, getattr(a1, x, ()))
		out_exts = getattr(t2, y, getattr(a2, y, ()))
		for k in in_exts:
			if k in out_exts:
				return -1
		else:
			in_exts = getattr(t2, x, getattr(a2, x, ()))
			out_exts = getattr(t1, y, getattr(a1, y, ()))
			for k in in_exts:
				if k in out_exts:
					return 1
			else:
				pass
		return 0

	def compare_partial(self, t1, t2, a1, a2):
		"partial relations after/before"
		m = "after"
		n = "before"
		if a2:
			if a2.m_name in getattr(t1, m, getattr(a1, m, ())): return -1
			elif a2.m_name in getattr(t1, n, getattr(a1, n, ())): return 1
		if a1:
			#print a1, "after", getattr(t2, m, getattr(a2, m, ()))
			#print  a1, "before", getattr(t2, n, getattr(a2, n, ()))
			if a1.m_name in getattr(t2, m, getattr(a2, m, ())): return 1
			elif a1.m_name in getattr(t2, n, getattr(a2, n, ())): return -1
		return 0

	def extract_constraints(self):
		"extract the parallelization constraints from the tasks with different constraints"
		keys = self.cstr_groups.keys()
		max = len(keys)
		a = "m_action"
		# hopefully the lenght of this list is short
		for i in xrange(max):
			t1 = self.cstr_groups[keys[i]][0]
			a1 = getattr(t1, a, None)
			for j in xrange(i + 1, max):
				t2 = self.cstr_groups[keys[j]][0]
				a2 = getattr(t2, a, None)

				# add the constraints based on the comparisons

				val = (0
					or self.compare_prios(t1, t2, a1, a2)
					or self.compare_exts(t1, t2, a1, a2)
					or self.compare_partial(t1, t2, a1, a2)
					)
				if val > 0:
					self.set_order(keys[i], keys[j])
					continue
				elif val < 0:
					self.set_order(keys[j], keys[i])
					continue

		#print "the constraint groups are:", self.cstr_groups, "and the constraints ", self.cstr_order
		# TODO extract constraints by file extensions on the actions

	def tasks_in_parallel(self):
		"(NORMAL) next list of tasks that may be executed in parallel"

		if not self.ready: self.prepare()

		#print [(a.m_name, cstrs[a].m_name) for a in cstrs]
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

		#print "unconnected tasks: ", unconnected, "tasks", [eq_groups[x] for x in unconnected]

		toreturn = []
		for y in unconnected:
			toreturn.extend(self.cstr_groups[y])

		# remove stuff only after
		for y in unconnected:
				try: self.cstr_order.__delitem__(y)
				except KeyError: pass
				self.cstr_groups.__delitem__(y)

		if not toreturn and remainder:
			Params.fatal("circular dependency detected %r" % remainder)

		#print "returning", toreturn
		return toreturn

	def tasks_by_max_jobs(self):
		"(JOBCONTROL) returns the tasks that can run in parallel with the max amount of jobs"
		if not self.ready: self.prepare()
		# TODO
		if not self.temp_tasks: self.temp_tasks = []

	def tasks_with_inner_constraints(self):
		"(MAXPARALLEL) returns all tasks in this group, but add the constraints on each task instance"
		# TODO

class TaskBase(object):
	"TaskBase is the base class for task objects"
	def __init__(self, normal=1):
		self.m_display = ''
		self.m_hasrun=0

		manager = Params.g_build.task_manager
		if normal:
			manager.add_task(self)
		else:
			self.m_idx = manager.idx
			manager.idx += 1
	def hash_constraints(self):
		sum = 0
		names = ('prio', 'before', 'after', 'in_exts', 'out_exts')
		act = getattr(self, "m_action", None)
		if act:
			sum = hash((sum, getattr(self, 'm_name', sys.maxint),))
		for x in names:
			# hash the attribute on the task, and fallback to the one of the action if not present
			sum = hash((sum, getattr(self, x, getattr(act, x, sys.maxint)),))
		sum = hash((sum, getattr(act, 'maxjobs', None)))
		return sum
	def may_start(self):
		"non-zero if the task is ready"
		return 1
	def must_run(self):
		"0 if the task does not need to run"
		return 1
	def prepare(self):
		"prepare the task for further processing"
		pass
	def update_stat(self):
		"update the dependency tree (node stats)"
		pass
	def debug_info(self):
		"return debug info"
		return ''
	def debug(self):
		"prints the debug info"
		pass
	def run(self):
		"process the task"
		pass
	def color(self):
		"color to use for the console messages"
		return 'BLUE'
	def set_display(self, v):
		self.m_display = v
	def get_display(self):
		return self.m_display

class Task(TaskBase):
	"The most common task, it has input and output nodes"
	def __init__(self, action_name, env, normal=1, prio=None):
		TaskBase.__init__(self, normal=normal)

		# name of the action associated to this task type
		self.m_action = Action.g_actions[action_name]
		if not (prio is None): self.prio = prio

		# environment in use
		self.m_env = env

		# inputs and outputs are nodes
		# use setters when possible
		self.m_inputs  = []
		self.m_outputs = []

		self.m_deps_nodes = []
		self.m_run_after = []

		# Additionally, you may define the following
		#self.dep_vars  = 'PREFIX DATADIR'
		#self.m_scanner = some_scanner_object

	def env(self):
		# TODO IDEA in the future, attach the task generator instead of the env
		return self.m_env

	def __repr__(self):
		return "".join(['\n\t{task: ', self.m_action.m_name, " ", ",".join([x.m_name for x in self.m_inputs]), " -> ", ",".join([x.m_name for x in self.m_outputs]), '}'])

	def set_inputs(self, inp):
		if type(inp) is types.ListType: self.m_inputs += inp
		else: self.m_inputs.append(inp)

	def set_outputs(self, out):
		if type(out) is types.ListType: self.m_outputs += out
		else: self.m_outputs.append(out)

	def set_run_after(self, task):
		"set (scheduler) dependency on another task"
		# TODO: handle list or object
		assert isinstance(task, TaskBase)
		self.m_run_after.append(task)

	def get_run_after(self):
		try: return self.m_run_after
		except AttributeError: return []

	def add_file_dependency(self, filename):
		"TODO user-provided file dependencies"
		node = Params.g_build.m_current.find_resource(filename)
		self.m_deps_nodes.append(node)

	#------------ users are probably less interested in the following methods --------------#

	def signature(self):
		# compute the result one time, and suppose the scanner.get_signature will give the good result
		try: return self.sign_all
		except AttributeError: pass

		env = self.env()
		tree = Params.g_build

		m = md5()

		# TODO maybe we could split this dep sig into two parts (nodes, dependencies)
		# this would only help for debugging though
		dep_sig = SIG_NIL
		scan = getattr(self, 'm_scanner', None)
		if scan:
			dep_sig = scan.get_signature(self)
			try: m.update(dep_sig)
			except TypeError: raise Scan.ScannerError, "failure to compute the signature"
		else:
			# compute the signature from the inputs (no scanner)
			for x in self.m_inputs:
				v = tree.m_tstamp_variants[x.variant(env)][x.id]
				dep_sig = hash( (dep_sig, v) )
				m.update(v)

		# manual dependencies, they can slow down the builds
		try:
			additional_deps = tree.deps_man
			for x in self.m_inputs + self.m_outputs:
				try:
					d = additional_deps[x]
				except KeyError:
					continue
				if callable(d): d = d() # dependency is a function, call it
				dep_sig = hash( (dep_sig, d) )
				m.update(d)
		except AttributeError:
			pass

		# dependencies on the environment vars
		fun = getattr(self.m_action, 'signature', None)
		if fun: act_sig = self.m_action.signature(self)
		else: act_sig = env.sign_vars(self.m_action.m_vars)
		m.update(act_sig)

		# additional variable dependencies, if provided
		var_sig = None
		dep_vars = getattr(self, 'dep_vars', None)
		if dep_vars:
			var_sig = env.sign_vars(dep_vars)
			m.update(var_sig)

		# additional nodes to depend on, if provided
		node_sig = SIG_NIL
		dep_nodes = getattr(self, 'dep_nodes', [])
		for x in dep_nodes:
			variant = x.variant(env)
			v = tree.m_tstamp_variants[variant][x.id]
			node_sig = hash( (node_sig, v) )
			m.update(v)

		# we now have the array of signatures
		ret = m.digest()
		self.cache_sig = (ret, dep_sig, act_sig, var_sig, node_sig)

		self.sign_all = ret
		return ret

	def may_start(self):
		"wait for other tasks to complete"
		if (not self.m_inputs) or (not self.m_outputs):
			if not (not self.m_inputs) and (not self.m_outputs):
				error("potentially grave error, task is invalid : no inputs or outputs")
				self.debug()

		# the scanner has its word to say
		scan = getattr(self, 'm_scanner', None)
		if scan:
			fun = getattr(scan, 'may_start', None)
			if fun:
				if not fun(self):
					return 0

		# this is a dependency using the scheduler, as opposed to hash-based ones
		for t in self.get_run_after():
			if not t.m_hasrun:
				return 0
		return 1

	def must_run(self):
		"see if the task must be run or not"
		#return 0 # benchmarking

		env = self.env()
		tree = Params.g_build

		# tasks that have no inputs or outputs are run each time
		if not self.m_inputs and not self.m_outputs:
			self.m_dep_sig = SIG_NIL
			return 1

		# look at the previous signature first
		node = self.m_outputs[0]
		variant = node.variant(env)
		try:
			time = tree.m_tstamp_variants[variant][node.id]
		except KeyError:
			debug("task #%d should run as the first node does not exist" % self.m_idx, 'task')
			try: new_sig = self.signature()
			except KeyError:
				print "TODO - computing the signature failed"
				return 1

			ret = self.can_retrieve_cache(new_sig)
			return not ret

		key = hash( (variant, node.m_name, time, getattr(self, 'm_scanner', self).__class__.__name__) )
		prev_sig = tree.bld_sigs[key][0]
		#print "prev_sig is ", prev_sig
		new_sig = self.signature()

		# debug if asked to
		if Params.g_zones: self.debug_why(tree.bld_sigs[key])

		if new_sig != prev_sig:
			# try to retrieve the file from the cache
			ret = self.can_retrieve_cache(new_sig)
			return not ret

		return 0

	def update_stat(self):
		"called after a successful task run"
		tree = Params.g_build
		env = self.env()
		sig = self.signature()

		cnt = 0
		for node in self.m_outputs:
			variant = node.variant(env)
			#if node in tree.m_tstamp_variants[variant]:
			#	print "variant is ", variant
			#	print "self sig is ", Params.view_sig(tree.m_tstamp_variants[variant][node])

			# check if the node exists ..
			os.stat(node.abspath(env))

			# important, store the signature for the next run
			tree.m_tstamp_variants[variant][node.id] = sig

			# We could re-create the signature of the task with the signature of the outputs
			# in practice, this means hashing the output files
			# this is unnecessary
			if Params.g_cache_global:
				ssig = sig.encode('hex')
				dest = os.path.join(Params.g_cache_global, ssig+'-'+str(cnt))
				try: shutil.copy2(node.abspath(env), dest)
				except IOError: warning('could not write the file to the cache')
				cnt += 1

		# keep the signatures in the first node
		node = self.m_outputs[0]
		variant = node.variant(env)
		time = tree.m_tstamp_variants[variant][node.id]
		key = hash( (variant, node.m_name, time, getattr(self, 'm_scanner', self).__class__.__name__) )
		val = self.cache_sig
		tree.set_sig_cache(key, val)

		self.m_executed=1

	def can_retrieve_cache(self, sig):
		"""Retrieve build nodes from the cache - the file time stamps are updated
		for cleaning the least used files from the cache dir - be careful when overriding"""
		if not Params.g_cache_global: return None
		if Params.g_options.nocache: return None

		env = self.env()
		sig = self.signature()

		cnt = 0
		for node in self.m_outputs:
			variant = node.variant(env)

			ssig = sig.encode('hex')
			orig = os.path.join(Params.g_cache_global, ssig+'-'+str(cnt))
			try:
				shutil.copy2(orig, node.abspath(env))
				os.utime(orig, None)
				# mark the cache file as used recently (modified)
			except (OSError, IOError):
				debug("failed retrieving file", 'task')
				return None
			else:
				cnt += 1
				Params.g_build.m_tstamp_variants[variant][node.id] = sig
				if not Runner.g_quiet: Params.pprint('GREEN', 'restored from cache %s' % node.bldpath(env))
		return 1

	def prepare(self):
		try: self.m_action.prepare(self)
		except AttributeError: pass

	def run(self):
		return self.m_action.run(self)

	def get_display(self):
		if self.m_display: return self.m_display
		self.m_display = self.m_action.get_str(self)
		return self.m_display

	def color(self):
		return self.m_action.m_color

	def debug_info(self):
		ret = []
		ret.append('-- task details begin --')
		ret.append('action: %s' % str(self.m_action))
		ret.append('idx:    %s' % str(self.m_idx))
		ret.append('source: %s' % str(self.m_inputs))
		ret.append('target: %s' % str(self.m_outputs))
		ret.append('-- task details end --')
		return '\n'.join(ret)

	def debug(self, level=0):
		fun = Params.debug
		if level>0: fun = Params.error
		fun(self.debug_info())

	def debug_why(self, old_sigs):
		"explains why a task is run"

		new_sigs = self.cache_sig
		v = Params.view_sig

		debug("Task %s must run: %s" % (self.m_idx, old_sigs[0] != new_sigs[0]), 'task')
		if (new_sigs[1] != old_sigs[1]):
			debug(' -> A source file (or a dependency) has changed %s %s' % (v(old_sigs[1]), v(new_sigs[1])), 'task')
		if (new_sigs[2] != old_sigs[2]):
			debug(' -> An environment variable has changed %s %s' % (v(old_sigs[2]), v(new_sigs[2])), 'task')
		if (new_sigs[3] != old_sigs[3]):
			debug(' -> A manual dependency has changed %s %s' % (v(old_sigs[3]), v(new_sigs[3])), 'task')
		if (new_sigs[4] != old_sigs[4]):
			debug(' -> A user-given environment variable has changed %s %s' % (v(old_sigs[4]), v(new_sigs[4])), 'task')

class TaskCmd(TaskBase):
	"TaskCmd executes commands. Instances always execute their function"
	def __init__(self, fun, env):
		TaskBase.__init__(self)
		self.fun = fun
		self.m_env = env
	def prepare(self):
		self.m_display = "* executing: %s" % self.fun.__name__
	def debug_info(self):
		return 'TaskCmd:fun %s' % self.fun.__name__
	def debug(self):
		return 'TaskCmd:fun %s' % self.fun.__name__
	def run(self):
		self.fun(self)
	def env(self):
		return self.m_env


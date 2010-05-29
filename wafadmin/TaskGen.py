#!/usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005-2010 (ita)

"""
The class task_gen encapsulates the creation of task objects (low-level code)
The instances can have various parameters, but the creation of task nodes (Task.py)
is always postponed. To achieve this, various methods are called from the method "apply"

The class task_gen contains lots of methods, and a configuration table:
* the methods to call (self.meths) can be specified dynamically (removing, adding, ..)
* the order of the methods (self.prec or by default task_gen.prec) is configurable
* new methods can be inserted dynamically without pasting old code

Additionally, task_gen provides the method "process_source"
* file extensions are mapped to methods: def meth(self, name_or_node)
* if a mapping is not found in self.mappings, it is searched in task_gen.mappings
* when called, the functions may modify self.source to append more source to process
* the mappings can map an extension or a filename (see the code below)

WARNING: subclasses must reimplement the clone method
"""

import traceback, copy
import Task, Utils, Logs, Base

feats = Utils.defaultdict(set)
"""remember the methods declaring features"""

class task_gen(object):
	"""
	generate task objects which may be executed in parallel by the scheduler
	"""

	mappings = {}
	prec = Utils.defaultdict(list)

	def __init__(self, *kw, **kwargs):

		# so we will have to play with directed acyclic graphs
		# detect cycles, etc

		self.source = ''
		self.target = ''

		# list of methods to execute - does not touch it by hand unless you know
		self.meths = []

		# precedence table for sorting the methods
		self.prec = Utils.defaultdict(list)

		# list of mappings extension -> function
		self.mappings = {}

		# list of methods to execute (by name)
		self.features = []

		# not always a good idea
		self.tasks = []

		self.bld = kwargs['bld']
		self.env = self.bld.env.derive()

		self.path = self.bld.path # emulate chdir when reading scripts
		self.name = '' # give a name to the target (static+shlib with the same targetname ambiguity)

		# provide a unique id
		try:
			self.idx = self.bld.idx[id(self.path)] = self.bld.idx.get(id(self.path), 0) + 1
		except AttributeError:
			self.bld.idx = {}
			self.idx = self.bld.idx[id(self.path)] = 0

		for key, val in kwargs.items():
			setattr(self, key, val)

	def __str__(self):
		return ("<task_gen '%s' declared in %s>" % (self.name or self.target, self.path))

	def to_list(self, value):
		"helper: returns a list"
		if isinstance(value, str): return value.split()
		else: return value

	def apply(self):
		"order the methods to execute using self.prec or task_gen.prec"
		keys = set(self.meths)

		# add the methods listed in the features
		self.features = Utils.to_list(self.features)
		for x in self.features + ['*']:
			st = feats[x]
			if not st:
				Logs.warn('feature %r does not exist - bind at least one method to it' % x)
			keys.update(st)

		# copy the precedence table
		prec = {}
		prec_tbl = self.prec or task_gen.prec
		for x in prec_tbl:
			if x in keys:
				prec[x] = prec_tbl[x]

		# elements disconnected
		tmp = []
		for a in keys:
			for x in prec.values():
				if a in x: break
			else:
				tmp.append(a)

		# topological sort
		out = []
		while tmp:
			e = tmp.pop()
			if e in keys: out.append(e)
			try:
				nlst = prec[e]
			except KeyError:
				pass
			else:
				del prec[e]
				for x in nlst:
					for y in prec:
						if x in prec[y]:
							break
					else:
						tmp.append(x)

		if prec:
			raise Base.WafError("graph has a cycle %s" % str(prec))
		out.reverse()
		self.meths = out

		# then we run the methods in order
		Logs.debug('task_gen: posting %s %d' % (self, id(self)))
		for x in out:
			try:
				v = getattr(self, x)
			except AttributeError:
				raise Base.WafError("tried to retrieve %s which is not a valid method" % x)
			Logs.debug('task_gen: -> %s (%d)' % (x, id(self)))
			v()

	def post(self):
		"runs the code to create the tasks, do not subclass"
		if not self.name:
			if isinstance(self.target, list):
				self.name = ' '.join(self.target)
			else:
				self.name = self.target

		if getattr(self, 'posted', None):
			#error("OBJECT ALREADY POSTED" + str( self))
			return False
		self.posted = True
		self.apply()
		Logs.debug('task_gen: posted %s' % self.name)
		return True

	def get_hook(self, node):
		"""
		get a function able to process an extension
		"""
		ext = node.suffix()
		try:
			return self.mappings[ext]
		except KeyError:
			try:
				return task_gen.mappings[ext]
			except KeyError:
				return None

	def create_task(self, name, src=None, tgt=None):
		task = Task.classes[name](env=self.env.derive(), generator=self)
		if src:
			task.set_inputs(src)
		if tgt:
			task.set_outputs(tgt)
		self.tasks.append(task)
		return task

	def clone(self, env):
		""
		newobj = self.bld()
		for x in self.__dict__:
			if x in ['env', 'bld']:
				continue
			elif x in ['path', 'features']:
				setattr(newobj, x, getattr(self, x))
			else:
				setattr(newobj, x, copy.copy(getattr(self, x)))

		newobj.posted = False
		if isinstance(env, str):
			newobj.env = self.bld.all_envs[env].derive()
		else:
			newobj.env = env.derive()

		return newobj

def declare_chain(name='', rule=None, reentrant=True, color='BLUE',
	ext_in=[], ext_out=[], before=[], after=[], decider=None, scan=None):
	"""
	see Tools/flex.py for an example
	while i do not like such wrappers, some people really do
	"""

	if isinstance(rule, str):
		act = Task.simple_task_type(name, rule, color=color)
	else:
		act = Task.task_type_from_func(name, rule, color=color)

	act.ext_in = Utils.to_list(ext_in)
	act.ext_out = Utils.to_list(ext_out)
	act.before = Utils.to_list(before)
	act.after = Utils.to_list(after)
	act.scan = scan

	def x_file(self, node):
		if decider:
			ext = decider(self, node)
		elif isinstance(act.ext_out, str):
			ext = act.ext_out

		out_source = [node.change_ext(x) for x in act.ext_out]
		if reentrant:
			for i in range(reentrant):
				self.source.append(out_source[i])
		tsk = self.create_task(name, node, out_source)

	for x in Utils.to_list(act.ext_in):
		task_gen.mappings[x] = x_file
	return x_file

def taskgen_method(func):
	"""
	register a method as a task generator method
	"""
	setattr(task_gen, func.__name__, func)
	return func

def feature(*k):
	"""
	declare a task generator method that will be executed when the
	object attribute 'feature' contains the corresponding key(s)
	"""
	def deco(func):
		setattr(task_gen, func.__name__, func)
		for name in k:
			feats[name].update([func.__name__])
		return func
	return deco

def before(*k):
	"""
	declare a task generator method which will be executed
	before the functions of given name(s)
	"""
	def deco(func):
		setattr(task_gen, func.__name__, func)
		for fun_name in k:
			if not func.__name__ in task_gen.prec[fun_name]:
				task_gen.prec[fun_name].append(func.__name__)
		return func
	return deco

def after(*k):
	"""
	declare a task generator method which will be executed
	after the functions of given name(s)
	"""
	def deco(func):
		setattr(task_gen, func.__name__, func)
		for fun_name in k:
			if not fun_name in task_gen.prec[func.__name__]:
				task_gen.prec[func.__name__].append(fun_name)
		return func
	return deco

def extension(*k):
	"""
	declare a task generator method which will be invoked during
	the processing of source files for the extension given
	"""
	def deco(func):
		setattr(task_gen, func.__name__, func)
		for x in k:
			task_gen.mappings[x] = func
		return func
	return deco

# ---------------------------------------------------------------
# The following methods are task generator methods commonly used
# they are almost examples, the rest of waf core does not depend on them

@feature('*')
def process_source(self):
	"""
	Process each element in the attribute 'source', assuming it represents
	a list of source (nodes or file names)
	process the files by extension"""

	if isinstance(self.source, str):
		self.source = Utils.to_list(self.source)

	lst = []
	find = self.path.find_resource
	for el in self.source:
		if isinstance(el, str):
			node = find(el)
			if not node:
				raise Base.WafError("source not found: '%s' in '%s'" % (el, self.path))
		else:
			node = el
		lst.append(node)
	self.source = lst

	for node in self.source:
		# self.mappings or task_gen.mappings map the file extension to a function
		x = self.get_hook(node)
		if not x:
			raise Base.WafError("File %r has no mapping in %r (did you forget to load a waf tool?)" % (node, self.__class__.mappings.keys()))
		x(self, node)

@feature('*')
@before('process_source')
def process_rule(self):
	"""
	Process the attribute rule, when provided the method process_source will be disabled
	"""
	if not getattr(self, 'rule', None):
		return

	try:
		self.meths.remove('process_source')
	except ValueError:
		# already removed?
		pass

	# get the function and the variables
	func = self.rule
	vars2 = []
	if isinstance(func, str):
		# use the shell by default for user-defined commands
		(func, vars2) = Task.compile_fun('', self.rule, shell=getattr(self, 'shell', True))
		func.code = self.rule

	vars = getattr(self, 'vars', vars2)
	if not vars:
		if isinstance(self.rule, str):
			vars = self.rule
		else:
			vars = Utils.h_fun(self.rule)

	# create the task class
	name = getattr(self, 'name', None) or self.target or self.rule
	cls = Task.task_type_from_func(name, func, vars)

	# now create one instance
	tsk = self.create_task(name)

	# we assume that the user knows that without inputs or outputs
	#if not getattr(self, 'target', None) and not getattr(self, 'source', None):
	#	cls.quiet = True

	if getattr(self, 'target', None):
		cls.quiet = True

		if not isinstance(self.target, list):
			self.target = [self.target]
		tsk.outputs = [isinstance(x, str) and self.path.find_or_declare(x) or x for x in self.target]

	if getattr(self, 'source', None):
		cls.quiet = True
		tsk.inputs = []
		for x in self.to_list(self.source):
			y = self.path.find_resource(x)
			if not y:
				raise Base.WafError('input file %r could not be found (%r)' % (x, self.path.abspath()))
			tsk.inputs.append(y)

	if getattr(self, 'always', None):
		Task.always_run(cls)

	if getattr(self, 'scan', None):
		cls.scan = self.scan

	if getattr(self, 'cwd', None):
		tsk.cwd = self.cwd

	if getattr(self, 'on_results', None):
		Task.update_outputs(cls)

	for x in ['after', 'before', 'ext_in', 'ext_out']:
		setattr(cls, x, getattr(self, x, []))

@feature('seq')
def sequence_order(self):
	"""
	Add a strict sequential constraint between the tasks generated by task generators
	It works because task generators are posted in order
	it will not post objects which belong to other folders

	This is more an example than a widely-used solution

	Note that the method is executed in last position

	to use:
	bld(features='javac seq')
	bld(features='jar seq')

	to start a new sequence, set the attribute seq_start, for example:
	obj.seq_start = True
	"""
	if self.meths and self.meths[-1] != 'sequence_order':
		self.meths.append('sequence_order')
		return

	if getattr(self, 'seq_start', None):
		return

	# all the tasks previously declared must be run before these
	if getattr(self.bld, 'prev', None):
		self.bld.prev.post()
		for x in self.bld.prev.tasks:
			for y in self.tasks:
				y.set_run_after(x)

	self.bld.prev = self


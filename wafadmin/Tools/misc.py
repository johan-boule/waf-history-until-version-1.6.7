#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2006 (ita)

"""
Custom objects:
 - execute a function everytime
 - copy a file somewhere else
"""

import shutil, re, os, types, subprocess, md5
import Object, Action, Node, Params, Utils, Task
from Params import fatal, debug

def copy_func(task):
	"Make a file copy. This might be used to make other kinds of file processing (even calling a compiler is possible)"
	env = task.m_env
	infile = task.m_inputs[0].abspath(env)
	outfile = task.m_outputs[0].abspath(env)
	try:
		shutil.copy2(infile, outfile)
		if task.chmod: os.chmod(outfile, task.chmod)
		return 0
	except:
		return 1

def action_process_file_func(task):
	"Ask the function attached to the task to process it"
	if not task.fun: fatal('task must have a function attached to it for copy_func to work!')
	return task.fun(task)

class cmdobj(Object.genobj):
	"This object will call a command everytime"
	def __init__(self, type='none'):
		Object.genobj.__init__(self, 'other')
		self.m_type = type
		self.prio   = 1
		self.fun    = None

	def apply(self):
		# create a task
		if not self.fun: fatal('cmdobj needs a function!')
		import Task
		Task.TaskCmd(self.fun, self.env, self.prio)

class copyobj(Object.genobj):
	"By default, make a file copy, if fun is provided, fun will make the copy (or call a compiler, etc)"
	def __init__(self, type='none'):
		Object.genobj.__init__(self, 'other')

		self.source = ''
		self.target = ''
		self.chmod  = ''
		self.fun = copy_func

		self.env = Params.g_build.m_allenvs['default'].copy()

	def apply(self):

		lst = self.to_list(self.source)

		for filename in lst:
			node = self.path.find_source(filename)
			if not node: fatal('cannot find input file %s for processing' % filename)

			target = self.target
			if not target or len(lst)>1: target = node.m_name

			# TODO the file path may be incorrect
			newnode = self.path.find_build(target)

			task = self.create_task('copy', self.env, 10)
			task.set_inputs(node)
			task.set_outputs(newnode)
			task.m_env = self.env
			task.fun = self.fun
			task.chmod = self.chmod

			if not task.m_env:
				task.debug()
				fatal('task witout an environment')

def subst_func(task):
	"Substitutes variables in a .in file"

	m4_re = re.compile('@(\w+)@', re.M)

	env = task.m_env
	infile = task.m_inputs[0].abspath(env)
	outfile = task.m_outputs[0].abspath(env)

	file = open(infile, 'r')
	code = file.read()
	file.close()

	s = m4_re.sub(r'%(\1)s', code)

	dict = task.dict
	if not dict:
		names = m4_re.findall(code)
		for i in names:
			if task.m_env[i] and type(task.m_env[i]) is types.ListType :
				dict[i] = " ".join( task.m_env[i] )
			else: dict[i] = task.m_env[i]

	file = open(outfile, 'w')
	file.write(s % dict)
	file.close()

	return 0

class substobj(Object.genobj):
	def __init__(self, type='none'):
		Object.genobj.__init__(self, 'other')
		self.fun = subst_func
		self.dict = {}
		self.prio = 8
	def apply(self):

		lst = self.to_list(self.source)

		for filename in lst:
			node = self.path.find_source(filename)
			if not node: fatal('cannot find input file %s for processing' % filename)

			newnode = node.change_ext('')

			task = self.create_task('copy', self.env, self.prio)
			task.set_inputs(node)
			task.set_outputs(newnode)
			task.m_env = self.env
			task.fun = self.fun
			task.dict = self.dict

			if not task.m_env:
				task.debug()
				fatal('task witout an environment')


class CommandOutputTask(Task.Task):

	def __init__(self, env, priority, command, command_node, command_args, stdin, stdout):
		Task.Task.__init__(self, 'command-output', env, priority, normal=1)
		self.command = command
		self.command_node = command_node
		self.command_args = command_args
		self.stdin = stdin
		self.stdout = stdout

	def must_run(self):
		#return 0
		ret = 0
		if not self.m_inputs and not self.m_outputs:
			self.m_dep_sig = Params.sig_nil
			return 1

		self.m_dep_sig = self.m_scanner.get_signature(self)

		## --- everything above this line should be the same as in the parent class
		## in addition, check to see if the command script has been modified
		if self.command_node:
			variant = self.command_node.variant(self.m_env)
			cmd_sig = Params.g_build.m_tstamp_variants[variant][self.command_node]
			m = md5.new()
			m.update(self.m_dep_sig)
			m.update(cmd_sig)
			self.m_dep_sig = m.digest()
		## --- everything below this line should be the same as in the parent class

		sg = self.signature()

		node = self.m_outputs[0]

		# TODO should make a for loop as the first node is not enough
		variant = node.variant(self.m_env)

		if not node in Params.g_build.m_tstamp_variants[variant]:
			debug("task #%d should run as the first node does not exist" % self.m_idx, 'task')
			ret = self.can_retrieve_cache(sg)
			return not ret

		outs = Params.g_build.m_tstamp_variants[variant][node]

		if Params.g_zones:
			i1 = Params.vsig(self.m_sig)
			i2 = Params.vsig(self.m_dep_sig)
			a1 = Params.vsig(sg)
			a2 = Params.vsig(outs)
			debug("must run %d: task #%d signature:%s - node signature:%s (sig:%s depsig:%s)" \
				% (int(sg != outs), self.m_idx, a1, a2, i1, i2), 'task')

		if sg != outs:
			ret = self.can_retrieve_cache(sg)
			return not ret
		return 0


class CommandOutput(Object.genobj):

	CMD_ARGV_INPUT, CMD_ARGV_OUTPUT = range(2)

	def __init__(self, env=None):
		Object.genobj.__init__(self, 'other')
		self.env = env
		if not self.env:
			self.env = Params.g_build.m_allenvs['default']

		## file to use as stdin
		self.stdin = None

		## file to use as stdout
		self.stdout = None
		
		## the command to execute
		self.command = None

		## whether it is an external command; otherwise it is assumed
		## to be an excutable binary or script that lives in the
		## source or build tree.
		self.command_is_external = False

		## extra parameters (argv) to pass to the command (excluding
		## the command itself)
		self.argv = []

		## task priority
		self.priority = 100

		## dependencies to other objects
		## values must be 'genobj' instances (not names!)
		self.dependencies = []

	def _command_output_func(task):
		assert len(task.m_inputs) > 0
		inputs = [inp.bldpath(task.m_env) for inp in task.m_inputs]
		outputs = [out.bldpath(task.m_env) for out in task.m_outputs]

		argv = [task.command]
		for arg in task.command_args:
			if isinstance(arg, str):
				argv.append(arg)
			else:
				role, node = arg
				if role == CommandOutput.CMD_ARGV_INPUT:
					argv.append(node.srcpath(task.m_env))
				elif role == CommandOutput.CMD_ARGV_OUTPUT:
					argv.append(node.bldpath(task.m_env))
				else:
					raise AssertionError

		if task.stdin:
			stdin = file(task.stdin.srcpath(task.m_env))
		else:
			stdin = None

		if task.stdout:
			stdout = file(task.stdout.bldpath(task.m_env), "w")
		else:
			stdout = None

		Params.debug("command-output: stdin=%r, stdout=%r, argv=%r" %
					 (stdin, stdout, argv))
		command = subprocess.Popen(argv, stdin=stdin, stdout=stdout)
		return command.wait()

	_command_output_func = staticmethod(_command_output_func)

	def apply(self):
		if self.command_is_external:
			cmd = self.command
			cmd_node = None
		else:
			cmd_node = self.path.find_source(self.command)
			assert cmd_node is not None,\
				   ("Could not find command '%s' in source tree.\n"
					"Hint: if this is an external command, "
					"use command_is_external=True") % (self.command,)
 			cmd = cmd_node.bldpath(self.env)

		args = []
		inputs = []
		outputs = []
		
		for arg in self.argv:
			if isinstance(arg, str):
				args.append(arg)
			else:
				role, file_name = arg
				if role == CommandOutput.CMD_ARGV_INPUT:
					input_node = self.path.find_source(file_name)
					inputs.append(input_node)
					args.append((role, input_node))
				elif role == CommandOutput.CMD_ARGV_OUTPUT:
					output_node = self.path.find_build(file_name)
					outputs.append(output_node)
					args.append((role, output_node))
				else:
					raise AssertionError

		if self.stdout is None:
			stdout = None
		else:
			stdout = self.path.find_build(self.stdout)
			outputs.append(stdout)

		if self.stdin is None:
			stdin = None
		else:
			stdin = self.path.find_source(self.stdin)
			inputs.append(stdin)

		if not inputs:
			Params.fatal("command-output objects must have at least one input file")

		task = CommandOutputTask(self.env, self.priority,
								 cmd, cmd_node, args,
								 stdin, stdout)
		self.m_tasks.append(task)

		task.set_inputs(inputs)
		task.set_outputs(outputs)

		for dep in self.dependencies:
			assert dep is not self
			if not dep.m_posted:
				dep.post()
			for dep_task in dep.m_tasks:
				task.m_run_after.append(dep_task)

	def input_file(self, file_name):
		"""Returns an object to be used as argv element that instructs
		the task to use a file from the input vector at the given
		position as argv element."""
		return (CommandOutput.CMD_ARGV_INPUT, file_name)

	def output_file(self, file_name):
		"""Returns an object to be used as argv element that instructs
		the task to use a file from the output vector at the given
		position as argv element."""
		return (CommandOutput.CMD_ARGV_OUTPUT, file_name)

	def install(self):
		pass

def setup(env):
	Object.register('cmd', cmdobj)
	Object.register('copy', copyobj)
	Object.register('subst', substobj)
	Action.Action('copy', vars=[], func=action_process_file_func)
	Action.Action('command-output', func=CommandOutput._command_output_func, color='BLUE')
	Object.register('command-output', CommandOutput)

def detect(conf):
	return 1


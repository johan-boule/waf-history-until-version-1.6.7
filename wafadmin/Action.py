#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005 (ita)

import Object, Runner
from Params import debug, trace, fatal

g_actions={}
"global actions"

class Action:
	"Base class for all Actions"
	def __init__(self, name, vars=[], func=None, color='GREEN'):
		"""If the action is simple, func is not defined, else a function can be attached
		and will be launched instead of running the string generated by 'setstr' see Runner
		for when this is used - a parameter is given, it is the task. Each action must name"""

		self.m_name = name
		self.m_vars = vars # variables that should trigger a rebuild
		self.m_function_to_run = func
		self._add_action()
		self.m_color = color

	def __str__(self):
		return self.m_name

	def _add_action(self):
		global g_actions
		if self.m_name in g_actions: trace('overriding action '+self.m_name)
		g_actions[self.m_name] = self
		trace("action added: %s" % self.m_name)

	def get_str(self, task):
		"string to display to the user"
		try:
			src_str = " ".join(map(lambda a:a.bldpath(task.m_env), task.m_inputs))
			tgt_str = " ".join(map(lambda a:a.bldpath(task.m_env), task.m_outputs))
			return "* %s : %s -> %s" % (self.m_name, src_str, tgt_str)
		except:
			print "exception"
			task.debug(level=1)
			raise

	def prepare(self, task):
		"prepare the compilation"
		task.m_sig = Object.sign_env_vars(task.m_env, self.m_vars)

	def run(self, task):
		"run the compilation"
		if not self.m_function_to_run:
			fatal(self.m_name+" action has no function !")
		return self.m_function_to_run(task)

class alex:
	"""
	Actions declared using a string are compiled before use:

	A class with the necessary functions is created (so the string is parsed only once)
	All variables (CXX, ..) can be strings or lists of strings (only)
	The keywords TGT and SRC cannot be overridden (they represent the task input and output nodes)

	Example:
	str = '${CXX} -o ${TGT[0]} ${SRC[0]} -I ${SRC[0].m_parent.bldpath()}'
	act = simple_action('name', str)
	"""
	def __init__(self, s):
		self.str = s
		self.out = []
		self.params = []
		self.m_vars = []

		self.i = 0
		self.size = len(self.str)

	def start(self):
		while self.i < self.size:
			# quoted '$'
			c = self.str[self.i]
			if c == '\\':
				if self.i < self.size - 1 and self.str[self.i+1]=='$':
					self.out.append('$')
					self.i += 1
				else:
					self.out.append(c)
			elif c == '$':
				if self.str[self.i+1]=='{':
					self.i += 2
					self.varmatch()
				else:
					self.out.append(c)
			else:
				self.out.append(c)
			self.i += 1
	def varmatch(self):
		name = []
		meth = []

		cur = self.i
		while cur < self.size:
			if self.str[cur] == '}':
				s = ''.join(name)
				self.params.append( (''.join(name), ''.join(meth)) )
				self.out.append('%s')

				self.i = cur
				break
			else:
				c = self.str[cur]
				if meth:
					meth.append(c)
				else:
					if c=='.' or c =='[':
						meth.append(c)
					else:
						name.append(c)
			cur += 1
	def res(self):
		lst = ['def f(task):\n\tenv=task.m_env\n\tp=Object.flatten\n\t']

		#lst.append('print task.m_inputs\n\t')
		#lst.append('print task.m_outputs\n\t')

		lst.append('try: cmd = "')
		lst += self.out
		lst.append('"')

		alst=[]
		for (name, meth) in self.params:
			if name == 'SRC':
				if meth: alst.append('task.m_inputs%s' % meth)
				else: alst.append('" ".join(map(lambda a:a.srcpath(env), task.m_inputs))')
			elif name == 'TGT':
				if meth: alst.append('task.m_outputs%s' % meth)
				else: alst.append('" ".join(map(lambda a:a.bldpath(env), task.m_outputs))')
			else:
				self.m_vars.append(name)
				alst.append("p(env, '%s')" % name)
		if alst:
			lst.append(' % (\\\n\t\t')
			lst += ", \\\n\t\t".join(alst)
			lst.append(')\n')

		#lst.append('\texcept: task.debug()\n')
		lst.append('\texcept:\n')
		lst.append('\t\ttask.debug()\n')
		lst.append('\t\traise\n')

		lst.append('\treturn Runner.exec_command(cmd)\n')

		return "".join(lst)

	def fun(self):
		exec(self.res())
		return eval('f')

def simple_action(name, line, color='GREEN'):
	"helper provided for convenience"
	obj = alex(line)
	obj.start()
	f = obj.fun()
	debug(obj.res())
	act = Action(name, color=color)
	act.m_function_to_run = f
	act.m_vars = obj.m_vars


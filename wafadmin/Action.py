#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005 (ita)

import Object, Params

def trace(msg):
	Params.trace(msg, 'Action')
def debug(msg):
	Params.debug(msg, 'Action')
def error(msg):
	Params.error(msg, 'Action')

def add_action(act):
	Params.g_actions[act.m_name] = act
	trace( "action added: %s" % (act) )

class Action:
	def __init__(self, name, cmd=None, sig=None, str=None):
		self.m_name    = name
		self.mf_setcmd = cmd
		self.mf_setsig = sig
		self.mf_setstr = str

		# TRICK_2
		self.m_isMulti = 0

		# if the action is simple, this is not defined, else a function
		# can be attached and will be launched instead of running the string generated by 'setstr'
		# see Runner for when this is used - a parameter is given, it is the task
		self.m_function_to_run = None

		# register ourselves
		add_action(self)

	def __str__(self):
		return self.m_name

	def prepare(self, task):
		if self != task.m_action:
			print "action called for the wrong task (paranoid check)"
			return
		self.setsig(task)
		self.setstr(task)

		if not self.m_function_to_run:
			self.setcmd(task)

	def setcmd(self, task):
		if self.mf_setcmd:  self.mf_setcmd(task)
		else: print "attach a function or reimplement"
	def setsig(self, task):
		if self.mf_setsig:  self.mf_setsig(task)
		else: print "attach a function or reimplement"
	def setstr(self, task):
		if self.mf_setstr: self.mf_setstr(task)
		else: print "attach a function or reimplement"

# most actions contain only one well-defined command-line taking sources as input and targets as output
class GenAction(Action):
	def __init__(self, name, vars, src_only=0):
		Action.__init__(self, name)
		self.m_vars     = vars
		self.m_src_only = src_only

	def get_str(self, task):
		src_str = " ".join(  map(lambda a:a.bldpath(), task.m_inputs)  )
		tgt_str = " ".join(  map(lambda a:a.bldpath(), task.m_outputs)  )
		return "* %s : %s -> %s" % (self.m_name, src_str, tgt_str)

	def get_cmd(self, task):

		if Params.g_fake:
			tgt_str = " ".join(  map(lambda a:a.bldpath(), task.m_outputs)  )
			return "%s %s" % ('touch', tgt_str)
		else:
			# the command should contain two '%s' for adding the source and the target
			if not task.m_env:
				error("task has no environment")

			cmd_list = Object.list_to_env_list( task.m_env, self.m_vars )

			#print cmd_list
			#l = task.m_env['LINK_ST']
			#print l
			#print task.m_env

			command = " ".join( cmd_list )

			# obtain the strings "file1.o file2.o" and "programname"
			src_str = " ".join(  map(lambda a:a.bldpath(), task.m_inputs)  )
			tgt_str = " ".join(  map(lambda a:a.bldpath(), task.m_outputs)  )

			# uncomment this for debugging purposes
			#print command, "      ",  self.m_vars

			# if the action processes only sources, return 'command %s' % src_str
			if self.m_src_only:
				print command
				return command % (src_str)

			# obtain the command-line "command %s -o %s" % (str, str) -> command file1.o file2.o -o programname
			#print " action is %s" % command
			return command % (src_str, tgt_str)

	# set the program strings using the methods right above
	def prepare(self, task):
		task.m_sig = Object.sign_env_vars(task.m_env, self.m_vars)
		task.m_str = self.get_str(task)
		if not self.m_function_to_run:
			task.m_cmd = self.get_cmd(task)

def create_action(name, cmd, sig, str):
	act = Action(name, cmd, sig, str)

def space_join(list, env):
	cmd_list = Object.list_to_env_list( list )
	return " ".join( cmd_list )


